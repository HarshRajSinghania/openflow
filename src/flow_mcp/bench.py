import argparse
import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from flow_mcp.bridge import bridge, load_secret
from flow_mcp.jobs import Jobs
from flow_mcp.manager import BridgeError, Manager
from flow_mcp.models import Scope, StrictModel
from flow_mcp.operations import ImageInput, ImageUpscaleInput, VideoInput, VideoUpscaleInput
from flow_mcp.pairing import Pairings
from flow_mcp.service import Operations, upload_input


def source_fingerprint() -> dict[str, object]:
    """Hash the running source files so a stale process is detectable.

    The value is computed from the files *currently imported in this process*
    (``module.__file__``), so it reflects what the loaded process actually runs,
    not merely what is on disk. A restart after an edit changes it; a stale
    process keeps the old digest.
    """
    modules = ("flow_mcp.service", "flow_mcp.manager", "flow_mcp.operations")
    digest = hashlib.sha256()
    files: dict[str, float] = {}
    for name in modules:
        module = __import__(name, fromlist=["__file__"])
        location = getattr(module, "__file__", None)
        if not location:
            raise BridgeError("source_fingerprint_unavailable")
        path = Path(location)
        digest.update(path.read_bytes())
        files[name] = round(path.stat().st_mtime, 3)
    return {"digest": digest.hexdigest()[:16], "files": files}


class Bench:
    def __init__(self, manager: Manager, jobs: Jobs, secret: str, port: int) -> None:
        self.manager = manager
        self.operations = Operations(manager, jobs)
        self.secret = secret
        self.port = port
        self.stopped = asyncio.Event()

    async def _await_connection(self, connection_id: str,
                                deadline_seconds: float = 45.0) -> None:
        """Block until the given connection id is paired again after a socket drop.

        A tab reload can tear down the extension's WS; the background worker reconnects
        with exponential backoff (up to ~30 s with the first-retry alarm), and it keeps
        the same installation identity, so the connection id is stable.
        """
        deadline = asyncio.get_running_loop().time() + deadline_seconds
        while connection_id not in self.manager.sessions:
            if asyncio.get_running_loop().time() >= deadline:
                raise BridgeError("connection_closed")
            await asyncio.sleep(0.25)

    async def _await_new_document(self, connection_id: str, previous: str,
                                  deadline_seconds: float = 60.0,
                                  expected: Scope | None = None) -> str:
        """Return the new document_id once the selected tab re-resolves past a reload.

        Waits for the socket to come back, then polls ``snapshot`` until the extension
        reports a selection whose document_id differs from ``previous``. Raises
        ``scope_changed`` if the deadline passes with the same document still selected
        (the reload did not actually navigate, or the content script never re-ran).
        """
        deadline = asyncio.get_running_loop().time() + deadline_seconds
        last_error: str | None = None
        saw_connection = connection_id in self.manager.sessions
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            # Bound the reconnect wait by the remaining deadline, so a short timeout is
            # honored rather than being masked by the inner 5 s connect wait.
            try:
                await self._await_connection(connection_id, deadline_seconds=min(5.0, remaining))
            except BridgeError:
                if asyncio.get_running_loop().time() >= deadline:
                    break
                await asyncio.sleep(0.25)
                continue
            saw_connection = True
            try:
                snapshot = await self.manager.snapshot(connection_id)
            except BridgeError as error:
                last_error = str(error)
                await asyncio.sleep(0.25)
                continue
            selected = snapshot.get("selected")
            if isinstance(selected, dict):
                if expected is not None and any(
                    selected.get(key) != getattr(expected, key)
                    for key in ("tab_id", "origin", "project_id")
                ):
                    raise BridgeError("scope_changed")
                document_id = selected.get("document_id")
                if isinstance(document_id, str) and document_id and document_id != previous:
                    return document_id
            await asyncio.sleep(0.25)
        # Distinguish "the extension never came back" (connection_closed) from "it came back
        # but the document never changed" (scope_changed: the reload did not navigate).
        if not saw_connection:
            raise BridgeError("connection_closed")
        raise BridgeError(last_error or "scope_changed")

    async def dispatch(self, command: str, data: dict[str, Any]) -> dict[str, object]:
        allowed = {
            "connections": set(), "snapshot": {"connection_id"},
            "account": {"connection_id"}, "page_ready": {"connection_id"},
            "select": {"connection_id", "tab_id"},
            "create-preview": {"connection_id"},
            "create-confirm": {"connection_id", "preview_id", "approved"},
            "rpc-read": {"connection_id", "project_id"}, "stop": set(),
            "home-read": {"connection_id"}, "list-projects": {"connection_id"},
            "health": set(), "capabilities": {"connection_id"},
            "reload-extension": {"connection_id"}, "reload-tab": {"connection_id"},
            "captcha-probe": {"connection_id"},
            "plan": {"connection_id"},
            "image": {"connection_id", "project_id", "input", "preview_id", "approved"},
            "video": {"connection_id", "project_id", "input", "preview_id", "approved"},
            "upload": {"connection_id", "project_id", "file_path", "name",
                       "preview_id", "approved"},
            "job": {"connection_id", "project_id", "job_id", "refresh"},
            "wait": {"connection_id", "project_id", "job_id"},
            "download": {"connection_id", "project_id", "job_id", "destination", "index"},
        }
        allowed["upscale-image"] = allowed["image"]
        allowed["upscale-video"] = allowed["video"]
        if command not in allowed or data.keys() - allowed[command]:
            raise BridgeError("invalid_request")
        connection = data.get("connection_id")
        if connection is not None and not isinstance(connection, str):
            raise BridgeError("invalid_request")
        if command == "connections":
            return {"connections": [
                {"connection_id": s.id} for s in self.manager.sessions.values()
            ]}
        if command == "stop":
            self.stopped.set()
            return {"stopping": True}
        if command == "health":
            return {"build": "operational-bench-2", "source": source_fingerprint(),
                    "capabilities": sorted(allowed),
                    "connections": len(self.manager.sessions)}
        if command in {"capabilities", "reload-extension"}:
            session = self.manager.resolve(connection)
            async with session.lock:
                return await self.manager.request(
                    session, "capabilities" if command == "capabilities" else "reload_extension",
                    {} if command == "capabilities" else {"marker": "openflow-dev-reload"})
        if command == "reload-tab":
            await self.manager.snapshot(connection)
            session = self.manager.resolve(connection)
            async with session.lock:
                if session.selected is None:
                    raise BridgeError("select_flow_tab_required")
                reload_scope = session.selected
                previous = reload_scope.document_id
                result = await self.manager.request(
                    session, "reload_tab", {"scope": reload_scope.model_dump()}, 60)
                if (result.get("reloading") != reload_scope.tab_id
                        or result.get("project_id") != reload_scope.project_id
                        or result.get("previous_document_id") != previous):
                    raise BridgeError("scope_changed")
            # The reply above was delivered BEFORE the navigation was scheduled, so the
            # socket is still up. A reload destroys the document; wait for the selection to
            # re-resolve to a NEW document_id, tolerating a socket drop + reconnect.
            return {
                "reloading": result.get("reloading"),
                "project_id": result.get("project_id"),
                "previous_document_id": result.get("previous_document_id", previous),
                "document_id": await self._await_new_document(
                    session.id, previous, expected=reload_scope),
            }
        if command == "captcha-probe":
            await self.manager.snapshot(connection)
            session = self.manager.resolve(connection)
            async with session.lock:
                scope = session.selected
                epoch = session.generation
                if scope is None:
                    raise BridgeError("select_flow_tab_required")
                result = await self.manager.request(session, "captcha_probe",
                                                     {"scope": scope.model_dump()}, 60)
                reply_scope = Scope.model_validate(result.get("scope"))
                if epoch != session.generation or reply_scope != scope:
                    raise BridgeError("scope_changed")
                return {**result, "scope": reply_scope.model_dump()}
        if command in {"home-read", "list-projects"}:
            await self.manager.snapshot(connection)
            session = self.manager.resolve(connection)
            async with session.lock:
                scope = session.selected
                epoch = session.generation
                if scope is None or (command == "list-projects" and scope.project_id is not None):
                    raise BridgeError("select_flow_home_tab_required")
                result = await self.manager.request(session, command.replace("-", "_"), {
                    "scope": scope.model_dump()}, 200)
                reply_scope = Scope.model_validate(result.get("scope"))
                if epoch != session.generation or reply_scope != scope:
                    raise BridgeError("scope_changed")
                return result
        if command == "rpc-read":
            from uuid import UUID

            project = data.get("project_id")
            if not isinstance(project, str):
                raise BridgeError("invalid_request")
            try:
                if str(UUID(project)) != project.lower():
                    raise ValueError
            except ValueError:
                raise BridgeError("invalid_request") from None
            await self.manager.snapshot(connection)
            session = self.manager.resolve(connection)
            async with session.lock:
                scope = session.selected
                epoch = session.generation
                if scope is None:
                    raise BridgeError("select_flow_tab_required")
                result = await self.manager.request(session, "probe", {
                    "scope": scope.model_dump(), "input": {"project_id": project},
                    "diagnostics": True}, 200)
                reply_scope = Scope.model_validate(result.get("scope"))
                if epoch != session.generation or reply_scope != scope:
                    raise BridgeError("scope_changed")
                return {**result, "scope": reply_scope.model_dump()}
        if command == "snapshot":
            return await self.manager.snapshot(connection)
        if command == "select":
            tab = data.get("tab_id")
            if type(tab) is not int or tab < 0:
                raise BridgeError("invalid_request")
            return await self.manager.select(connection, tab)
        if command in {"account", "page_ready"}:
            observation = await self.manager.account(connection)
            if command == "page_ready":
                return {"stage": "isolated_world_inspection", "page_ready": True,
                        "scope": observation["scope"], "rpc_verified": False}
            return observation
        if not connection:
            raise BridgeError("connection_id_required")
        if command == "plan":
            session = self.manager.resolve(connection)
            return {
                "connection_id": connection,
                "scope": session.selected.model_dump() if session.selected else None,
                "approval": "not_recorded; approve each resolved preview separately",
                "confirm": False, "cost_credits": None,
                "coverage": "implemented model keys, not all Google models or variants",
                "image_schema": ImageInput.model_json_schema(),
                "video_schema": VideoInput.model_json_schema(),
                "steps": [
                    {"id": "project", "command": "create-preview", "title": "OpenFlow project"},
                    *[{"id": model, "command": "image", "depends_on": ["project"],
                       "input": {"model": model, "prompt": "A red cube on a white table",
                                 "ratio": "16:9"}}
                      for model in ("nano_banana_pro", "nano_banana_2", "nano_banana_lite")],
                    {"id": "download-image", "command": "download",
                     "depends_on": ["nano_banana_2"]},
                    {"id": "upload", "command": "upload", "depends_on": ["download-image"]},
                    *[{"id": model, "command": "video", "depends_on": ["upload"],
                       "input": {"model": model, "prompt": "The cube rotates slowly",
                                 "ratio": "16:9", "duration": 8, "resolution": "720p"},
                       "resolve": {"start": "upload.result.assets[0].media_id"}}
                      for model in ("omni", "veo_lite")],
                    {"id": "download-videos", "command": "download",
                     "depends_on": ["omni", "veo_lite"]},
                    *[{"id": "upscale-image-" + resolution, "command": "upscale-image",
                       "depends_on": ["nano_banana_2"], "input": {"resolution": resolution},
                       "resolve": {"media_id": "nano_banana_2.result.assets[0].media_id"},
                       "experimental": True} for resolution in ("2K", "4K")],
                    {"id": "upscale-video-1080p", "command": "upscale-video",
                     "depends_on": ["omni"], "input": {"resolution": "1080p", "ratio": "16:9"},
                     "resolve": {"media_id": "omni.result.assets[0].media_id",
                                 "scene_id": "explicit scene UUID required before preview"},
                     "experimental": True},
                ],
                "suggested_counts": {"projects": 1, "images": 3, "uploads": 1,
                                     "videos": 2, "generation_calls": 5},
                "execution": "sequential; resolve dependencies only from completed exact-scope "
                             "jobs, then request and review a new bound preview; never resubmit "
                             "failed or unverified submissions",
                "upscale": {"image": ImageUpscaleInput.model_json_schema(),
                            "video": VideoUpscaleInput.model_json_schema(),
                            "status": "experimental; migrated captured requests, live responses "
                                      "unverified; video 4K unsupported",
                            "suggested_additional_calls": 3,
                            "steps": ["image 2K", "image 4K", "video 1080p"]},
            }
        if command in {"image", "video", "upload", "job", "wait", "download",
                       "upscale-image", "upscale-video"}:
            project = data.get("project_id")
            if not isinstance(project, str) or not project:
                raise BridgeError("invalid_request")
            if command in {"job", "wait", "download"}:
                identity = data.get("job_id")
                if not isinstance(identity, str):
                    raise BridgeError("invalid_request")
                if command == "wait":
                    latest = await self.operations.get(identity, connection, project, False)
                    try:
                        async with asyncio.timeout(180):
                            while latest["state"] == "pending":
                                latest = await self.operations.get(identity, connection,
                                                                   project, True)
                                if latest.get("poll_error") or latest.get("poll_unavailable"):
                                    break
                                if latest["state"] == "pending":
                                    await asyncio.sleep(5)
                    except TimeoutError:
                        return {**latest, "wait_status": "timeout_unverified",
                                "not_resubmitted": True}
                    return latest
                if command == "job":
                    refresh = data.get("refresh", False)
                    if type(refresh) is not bool:
                        raise BridgeError("invalid_request")
                    return await self.operations.get(identity, connection, project, refresh)
                destination, index = data.get("destination"), data.get("index", 0)
                if not isinstance(destination, str) or type(index) is not int:
                    raise BridgeError("invalid_request")
                return await self.operations.download(identity, connection, project,
                                                      destination, index)
            approved = data.get("approved", False)
            preview = data.get("preview_id")
            if type(approved) is not bool or (approved and not isinstance(preview, str)):
                raise BridgeError("explicit_approval_required")
            if preview is not None and not isinstance(preview, str):
                raise BridgeError("invalid_request")
            value: StrictModel
            if command == "upload":
                file_path, name = data.get("file_path"), data.get("name", "bench-upload")
                if not isinstance(file_path, str) or not isinstance(name, str):
                    raise BridgeError("invalid_request")
                value = upload_input(file_path, None, name)
            else:
                models: dict[str, type[StrictModel]] = {
                    "image": ImageInput, "video": VideoInput,
                    "upscale-image": ImageUpscaleInput, "upscale-video": VideoUpscaleInput,
                }
                value = models[command].model_validate(data.get("input"))
            operation = {"image": "generate_image", "video": "generate_video", "upload": "upload",
                         "upscale-image": "upscale_image", "upscale-video": "upscale_video"}
            return await self.operations.submit(operation[command], connection, project,
                                                value, approved, preview)
        confirm = command == "create-confirm"
        preview = data.get("preview_id")
        if confirm and (data.get("approved") is not True or not isinstance(preview, str)):
            raise BridgeError("explicit_approval_required")
        return await self.operations.create_project(connection, confirm, preview, True)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        status = 400
        result: dict[str, object] = {"error": "invalid_request", "stage": "control"}
        try:
            async with asyncio.timeout(220):
                raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)
                lines = raw.decode("ascii").split("\r\n")
                method, target, version = lines[0].split(" ")
                headers: dict[str, str] = {}
                for line in lines[1:-2]:
                    key, value = line.split(":", 1)
                    key = key.lower()
                    if key in headers:
                        raise ValueError
                    headers[key] = value.strip()
                if (headers.get("host") != f"127.0.0.1:{self.port}"
                        or "origin" in headers or "transfer-encoding" in headers
                        or version != "HTTP/1.1" or method != "POST"
                        or not target.startswith("/v1/")
                        or headers.get("content-type") != "application/json"):
                    raise ValueError
                if not hmac.compare_digest(headers.get("authorization", ""),
                                           "Bearer " + self.secret):
                    status, result = 401, {"error": "unauthorized", "stage": "control"}
                else:
                    length = int(headers.get("content-length", "-1"))
                    if not 0 <= length <= 65536:
                        raise ValueError
                    body = json.loads(await asyncio.wait_for(reader.readexactly(length), 3))
                    if not isinstance(body, dict):
                        raise ValueError
                    try:
                        result = await self.dispatch(target[4:], body)
                        status = 200
                    except BridgeError as error:
                        code = str(error)
                        safe = {"connection_id_required", "connection_not_found", "scope_changed",
                                "tab_unavailable", "inspection_failed", "invalid_request",
                                "invalid_response", "invalid_response:python_parse",
                                "invalid_response:extension_error", "request_timeout",
                                "connection_closed",
                                "select_flow_tab_required", "select_flow_home_tab_required",
                                "explicit_approval_required", "preview_scope_or_input_mismatch"}
                        result = {"error": code if code in safe else "operation_rejected",
                                  "stage": target[4:]}
                        status = 409
                    except (ValidationError, ValueError, OSError):
                        status, result = 409, {"error": "invalid_request", "stage": target[4:]}
                    except Exception:
                        status, result = 500, {"error": "internal_error", "stage": target[4:]}
        except (ValueError, TimeoutError, UnicodeError, asyncio.IncompleteReadError,
                asyncio.LimitOverrunError):
            pass
        finally:
            encoded = json.dumps(result).encode()
            writer.write(f"HTTP/1.1 {status} Result\r\nContent-Type: application/json\r\n"
                         f"Content-Length: {len(encoded)}\r\nConnection: close\r\n\r\n".encode()
                         + encoded)
            try:
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()


async def serve(directory: Path, ws_port: int, control_port: int) -> None:
    legacy = load_secret(directory) if (directory / "secret").exists() else ""
    manager = Manager(legacy, pairings=Pairings(directory))
    async with bridge(manager, ws_port):
        bench = Bench(manager, Jobs(directory / "jobs.sqlite3"),
                      load_secret(directory / "bench-control"), control_port)
        server = await asyncio.start_server(bench.handle, "127.0.0.1", control_port, limit=8192)
        async with server:
            await bench.stopped.wait()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["serve", "connections", "snapshot", "select",
                        "account", "page_ready", "rpc-read", "home-read",
                        "list-projects", "create-preview", "create-confirm",
                        "stop", "health", "capabilities", "reload-extension", "reload-tab", "plan",
                        "captcha-probe",
                        "image", "video", "upload", "job", "wait", "download",
                        "upscale-image", "upscale-video"])
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    parser.add_argument("--pairing-dir", type=Path, default=base / "openflow")
    parser.add_argument("--port", type=int, default=9234)
    parser.add_argument("--ws-port", type=int, default=9233)
    parser.add_argument("--connection-id")
    parser.add_argument("--tab-id", type=int)
    parser.add_argument("--preview-id")
    parser.add_argument("--project-id")
    parser.add_argument("--input", type=json.loads)
    parser.add_argument("--file-path")
    parser.add_argument("--name")
    parser.add_argument("--job-id")
    parser.add_argument("--destination")
    parser.add_argument("--index", type=int)
    parser.add_argument("--refresh", action="store_true", default=None)
    parser.add_argument("--approve", action="store_true")
    args = parser.parse_args()
    if any(not 1024 <= p <= 65535 or p == 9222 for p in (args.port, args.ws_port)):
        parser.error("invalid_port")
    try:
        if args.command == "serve":
            asyncio.run(serve(args.pairing_dir, args.ws_port, args.port))
            return
        secret = (args.pairing_dir / "bench-control" / "secret").read_text(encoding="ascii").strip()
        data = {k: v for k, v in {"connection_id": args.connection_id,
                "tab_id": args.tab_id, "preview_id": args.preview_id,
                "project_id": args.project_id, "input": args.input, "file_path": args.file_path,
                "name": args.name, "job_id": args.job_id, "destination": args.destination,
                "index": args.index, "refresh": args.refresh}.items() if v is not None}
        if args.approve:
            data["approved"] = True
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=225) as client:
            response = client.post(f"http://127.0.0.1:{args.port}/v1/{args.command}",
                                   headers={"Authorization": "Bearer " + secret}, json=data)
            print(json.dumps(response.json(), indent=2))
            if response.status_code != 200:
                raise SystemExit(1)
    except (OSError, httpx.HTTPError):
        print(json.dumps({"error": "bench_unavailable", "stage": args.command}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
