import hashlib
import json
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from flow_mcp.manager import BridgeError, Socket


@dataclass
class Pending:
    id: str
    installation_id: str
    origin: str
    socket: Socket
    expires: float
    approved: bool = False
    created_at: float = field(default_factory=time.time)

    def metadata(self) -> dict[str, object]:
        return {
            "pairing_id": self.id,
            "installation_id": self.installation_id,
            "extension_origin": self.origin,
            "expires_in_seconds": max(0, int(self.expires - time.monotonic())),
            "state": "awaiting_approval",
            "label": "Browser connection",
        }


class Pairings:
    def __init__(self, directory: Path | None = None, ttl: float = 120, limit: int = 16):
        self.directory = directory
        self.ttl = ttl
        self.limit = limit
        self.pending: dict[str, Pending] = {}
        self.credentials: dict[str, dict[str, str]] = {}
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = directory / "installations.json"
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or len(data) > 256:
                    raise BridgeError("invalid_credentials_file")
                for identity, record in data.items():
                    if (
                        not re.fullmatch(r"[a-f0-9-]{36}", identity)
                        or not isinstance(record, dict)
                        or set(record) != {"origin", "digest"}
                        or not re.fullmatch(r"chrome-extension://[a-p]{32}", record["origin"])
                        or not re.fullmatch(r"[a-f0-9]{64}", record["digest"])
                    ):
                        raise BridgeError("invalid_credentials_file")
                self.credentials = data

    def save(self) -> None:
        if self.directory is None:
            return
        path = self.directory / "installations.json"
        temporary = self.directory / "installations.tmp"
        with temporary.open("w", encoding="utf-8") as stream:
            temporary.chmod(0o600)
            json.dump(self.credentials, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)

    def cleanup(self) -> None:
        now = time.monotonic()
        for key, pending in list(self.pending.items()):
            if pending.expires <= now:
                del self.pending[key]

    def remove_socket(self, socket: Socket) -> None:
        for key, pending in list(self.pending.items()):
            if pending.socket is socket:
                del self.pending[key]

    def request(self, identity: str, origin: str, socket: Socket) -> Pending:
        self.cleanup()
        if len(self.pending) >= self.limit or (
            len(self.credentials) >= 256 and identity not in self.credentials
        ):
            raise BridgeError("pairing_limit")
        if any(p.installation_id == identity for p in self.pending.values()):
            raise BridgeError("pairing_already_pending")
        pending = Pending(
            secrets.token_urlsafe(18), identity, origin, socket, time.monotonic() + self.ttl
        )
        self.pending[pending.id] = pending
        return pending

    def listed(self) -> list[dict[str, object]]:
        self.cleanup()
        return [p.metadata() for p in self.pending.values()]

    def authenticate(self, identity: str, origin: str, credential: str) -> bool:
        record = self.credentials.get(identity)
        return bool(
            record
            and record["origin"] == origin
            and secrets.compare_digest(
                record["digest"], hashlib.sha256(credential.encode()).hexdigest()
            )
        )

    async def approve(self, pairing_id: str) -> dict[str, object]:
        self.cleanup()
        pending = self.pending.pop(pairing_id, None)
        if pending is None:
            raise BridgeError("pairing_not_found_or_expired")
        credential = secrets.token_urlsafe(48)
        previous = self.credentials.get(pending.installation_id)
        self.credentials[pending.installation_id] = {
            "origin": pending.origin,
            "digest": hashlib.sha256(credential.encode()).hexdigest(),
        }
        try:
            self.save()
            await pending.socket.send(json.dumps({"type": "provisioned", "secret": credential}))
        except Exception:
            if previous is None:
                self.credentials.pop(pending.installation_id, None)
            else:
                self.credentials[pending.installation_id] = previous
            self.save()
            raise BridgeError("pairing_delivery_failed") from None
        pending.approved = True
        return {"approved": True, "connection_id": pending.installation_id}

    def migrate(self, identity: str, origin: str, credential: str) -> None:
        self.credentials[identity] = {
            "origin": origin,
            "digest": hashlib.sha256(credential.encode()).hexdigest(),
        }
        self.save()

    def revoke(self, identity: str) -> None:
        record = self.credentials.get(identity)
        if record is not None:
            record["digest"] = "0" * 64
        self.save()
