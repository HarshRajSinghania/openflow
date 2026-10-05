import asyncio
import json
from uuid import uuid4

import pytest
from test_manager import Socket
from test_protocol import free_port
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from flow_mcp.bridge import bridge
from flow_mcp.manager import BridgeError, Manager
from flow_mcp.pairing import Pairings

ORIGIN = "chrome-extension://" + "a" * 32


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "null",
        "https://flow.google.com",
        ORIGIN + "/",
        ORIGIN + ".evil",
        "chrome-extension://" + "z" * 32,
    ],
)
async def test_origin_rejected(origin):
    port = free_port()
    async with bridge(Manager(), port):
        with pytest.raises(InvalidStatus):
            async with connect(f"ws://127.0.0.1:{port}", origin=origin):
                pytest.fail("untrusted origin accepted")


async def test_approval_bound_to_socket_identity_origin_and_persisted(tmp_path):
    store = Pairings(tmp_path)
    manager = Manager(pairings=store)
    port = free_port()
    identity = str(uuid4())
    request = {"type": "pair", "version": 1, "installation_id": identity}
    async with bridge(manager, port):
        async with connect(f"ws://127.0.0.1:{port}", origin=ORIGIN) as ws:
            await ws.send(json.dumps(request))
            pending = json.loads(await ws.recv())
            assert not manager.sessions
            assert "secret" not in json.dumps(store.listed())
            result = await store.approve(pending["pairing_id"])
            assert result == {"approved": True, "connection_id": identity}
            provisioned = json.loads(await ws.recv())
            token = provisioned["secret"]
            assert token not in json.dumps(store.listed())
            hello = {**request, "type": "hello", "secret": token}
            await ws.send(json.dumps(hello))
            assert json.loads(await ws.recv())["type"] == "paired"
        await asyncio.sleep(0.02)
        loaded = Pairings(tmp_path)
        assert loaded.authenticate(identity, ORIGIN, token)
        assert not loaded.authenticate(str(uuid4()), ORIGIN, token)
        assert not loaded.authenticate(identity, "chrome-extension://" + "b" * 32, token)
        async with connect(f"ws://127.0.0.1:{port}", origin=ORIGIN) as ws:
            await ws.send(json.dumps(hello))
            assert json.loads(await ws.recv())["type"] == "paired"
        await asyncio.sleep(0.02)
        store.revoke(identity)
        async with connect(f"ws://127.0.0.1:{port}", origin=ORIGIN) as ws:
            await ws.send(json.dumps(hello))
            with pytest.raises(ConnectionClosed):
                await ws.recv()
        assert not Pairings(tmp_path).authenticate(identity, ORIGIN, token)
        assert not store.pending


async def test_pairing_cannot_send_rpc_or_spoof_approval():
    manager = Manager()
    port = free_port()
    async with bridge(manager, port):
        async with connect(f"ws://127.0.0.1:{port}", origin=ORIGIN) as ws:
            await ws.send(
                json.dumps({"type": "pair", "version": 1, "installation_id": str(uuid4())})
            )
            pending = json.loads(await ws.recv())
            await ws.send('{"type":"approve"}')
            with pytest.raises(ConnectionClosed):
                await ws.recv()
        await asyncio.sleep(0.02)
        with pytest.raises(BridgeError):
            await manager.pairings.approve(pending["pairing_id"])
        assert not manager.sessions


async def test_pending_expiry_duplicate_limit_and_delivery_failure(tmp_path):
    store = Pairings(tmp_path, ttl=0.01, limit=1)
    identity = str(uuid4())
    ws = Socket()
    pending = store.request(identity, ORIGIN, ws)
    with pytest.raises(BridgeError):
        store.request(identity, ORIGIN, Socket())
    with pytest.raises(BridgeError):
        store.request(str(uuid4()), ORIGIN, Socket())
    await asyncio.sleep(0.02)
    with pytest.raises(BridgeError):
        await store.approve(pending.id)
    assert not store.listed()
    pending = store.request(identity, ORIGIN, ws)
    store.remove_socket(ws)
    with pytest.raises(BridgeError):
        await store.approve(pending.id)

    class BrokenSocket(Socket):
        async def send(self, message):
            raise OSError("closed")

    broken = BrokenSocket()
    pending = store.request(identity, ORIGIN, broken)
    with pytest.raises(BridgeError, match="pairing_delivery_failed"):
        await store.approve(pending.id)
    assert identity not in Pairings(tmp_path).credentials


async def test_different_identity_after_provisioning_rejected():
    manager = Manager()
    port = free_port()
    async with bridge(manager, port):
        async with connect(f"ws://127.0.0.1:{port}", origin=ORIGIN) as ws:
            await ws.send(
                json.dumps({"type": "pair", "version": 1, "installation_id": str(uuid4())})
            )
            pending = json.loads(await ws.recv())
            await manager.pairings.approve(pending["pairing_id"])
            token = json.loads(await ws.recv())["secret"]
            await ws.send(
                json.dumps(
                    {
                        "type": "hello",
                        "version": 1,
                        "secret": token,
                        "installation_id": str(uuid4()),
                    }
                )
            )
            with pytest.raises(ConnectionClosed):
                await ws.recv()
            assert not manager.sessions
