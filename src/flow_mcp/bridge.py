import asyncio
import ipaddress
import json
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from secrets import token_urlsafe

from pydantic import ValidationError
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from flow_mcp.manager import BridgeError, Manager, Session
from flow_mcp.models import Heartbeat, Hello, Invalidated, PairingRequest, Reply


def load_secret(directory: Path) -> str:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / "secret"
    try:
        with path.open("x", encoding="ascii") as stream:
            path.chmod(0o600)
            stream.write(token_urlsafe(48))
    except FileExistsError:
        pass
    secret = path.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{64}", secret):
        raise BridgeError("invalid_pairing_file")
    return secret


async def handle(manager: Manager, socket: ServerConnection) -> None:
    session: Session | None = None
    if len(manager.bridge_sockets) >= 32:
        await socket.close(1008, "bridge_limit")
        return
    manager.bridge_sockets.add(socket)
    try:
        origin = socket.request.headers.get("Origin", "") if socket.request else ""
        if (
            not re.fullmatch(r"chrome-extension://[a-p]{32}", origin)
            or not socket.remote_address
            or not ipaddress.ip_address(socket.remote_address[0]).is_loopback
        ):
            raise BridgeError("origin_rejected")
        async with asyncio.timeout(5):
            initial = await socket.recv()
            if len(initial) > 32768:
                raise ValueError
            data = json.loads(initial)
        if not isinstance(data, dict):
            raise ValueError
        if data.get("type") == "pair":
            request = PairingRequest.model_validate(data)
            identity = request.identity()
            if identity in manager.sessions:
                raise BridgeError("duplicate_connection")
            pending = manager.pairings.request(identity, origin, socket)
            await socket.send(json.dumps({"type": "pairing_pending", **pending.metadata()}))
            async with asyncio.timeout(manager.pairings.ttl):
                while True:
                    data = json.loads(await socket.recv())
                    if isinstance(data, dict) and data.get("type") == "ping":
                        Heartbeat.model_validate(data)
                        await socket.send('{"type":"pong"}')
                        continue
                    hello = Hello.model_validate(data)
                    if not pending.approved or hello.identity() != identity:
                        raise BridgeError("pairing_rejected")
                    break
        else:
            hello = Hello.model_validate(data)
        session = manager.pair(hello, socket, origin)
        await socket.send(json.dumps({"type": "paired", "connection_id": session.id}))
        async for message in socket:
            data = json.loads(message)
            if not isinstance(data, dict):
                raise ValueError
            if data.get("type") == "ping":
                Heartbeat.model_validate(data)
                await socket.send('{"type":"pong"}')
            elif data.get("type") == "invalidated":
                Invalidated.model_validate(data)
                manager.invalidate(session)
            else:
                manager.receive(session, Reply.model_validate(data))
    except (BridgeError, ValidationError, ValueError, TimeoutError):
        await socket.close(1008, "bridge_rejected")
    except ConnectionClosed:
        pass
    finally:
        manager.bridge_sockets.discard(socket)
        manager.pairings.remove_socket(socket)
        if session is not None:
            manager.disconnected(session)


@asynccontextmanager
async def bridge(manager: Manager, port: int) -> AsyncIterator[None]:
    logger = logging.getLogger("flow_mcp.websocket")
    logger.handlers = [logging.NullHandler()]
    logger.propagate = False
    logger.disabled = True
    async with serve(
        lambda socket: handle(manager, socket),
        "127.0.0.1",
        port,
        origins=[re.compile(r"chrome-extension://[a-p]{32}")],
        max_size=24000000,
        max_queue=8,
        compression=None,
        close_timeout=1,
        logger=logger,
    ):
        yield
