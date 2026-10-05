import asyncio
import json
import socket
import sys
from uuid import uuid4

import httpx
import pytest
from websockets.asyncio.client import connect

from flow_mcp.bench import Bench
from flow_mcp.bridge import bridge, load_secret
from flow_mcp.jobs import Jobs
from flow_mcp.manager import Manager


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def test_http_websocket_roundtrip_and_guards():
    manager = Manager("x" * 64)
    port, ws_port = free_port(), free_port()
    bench = Bench(manager, Jobs(), "y" * 64, port)
    async with bridge(manager, ws_port):
        server = await asyncio.start_server(bench.handle, "127.0.0.1", port)
        async with server, httpx.AsyncClient(trust_env=False) as client:
            url = f"http://127.0.0.1:{port}/v1/"
            headers = {"Authorization": "Bearer " + "y" * 64}
            assert (await client.post(url + "connections", json={})).status_code == 401
            for extra in ({"Origin": "http://evil.test"}, {"Host": "evil.test"}):
                reply = await client.post(url + "connections", json={}, headers=headers | extra)
                assert reply.status_code == 400
            for command, data in (("fetch", {}), ("snapshot", {"url": "http://evil.test"}),
                                  ("create-confirm", {"connection_id": str(uuid4())})):
                reply = await client.post(url + command, json=data, headers=headers)
                assert reply.status_code == 409
            async with connect(f"ws://127.0.0.1:{ws_port}",
                               origin="chrome-extension://" + "a" * 32) as ws:
                await ws.send(json.dumps({"type": "hello", "version": 1,
                                          "secret": "x" * 64, "installation_id": str(uuid4())}))
                assert json.loads(await ws.recv())["type"] == "paired"
                task = asyncio.create_task(client.post(url + "snapshot", json={}, headers=headers))
                request = json.loads(await ws.recv())
                assert request["operation"] == "snapshot"
                await ws.send(json.dumps({"type": "reply", "id": request["id"],
                                          "result": {"tabs": [], "selected": None}}))
                assert (await task).json()["tabs"] == []
                task = asyncio.create_task(client.post(url + "snapshot", json={}, headers=headers))
                request = json.loads(await ws.recv())
                await ws.send(json.dumps({"type": "reply", "id": request["id"],
                                          "error": "inspection_failed"}))
                assert (await task).json() == {"error": "inspection_failed", "stage": "snapshot"}
                reply = await client.post(url + "rpc-read", json={}, headers=headers)
                assert reply.status_code == 409
                assert reply.json()["error"] == "invalid_request"
                task = asyncio.create_task(client.post(
                    url + "capabilities", json={}, headers=headers))
                request = json.loads(await ws.recv())
                assert request["operation"] == "capabilities"
                assert request["params"] == {}
                await ws.send(json.dumps({"type": "reply", "id": request["id"], "result": {
                    "build": "readonly-probe-1", "operations": ["probe", "reload_extension"]}}))
                assert (await task).json()["build"] == "readonly-probe-1"
                project = str(uuid4())
                scope = {"tab_id": 7, "origin": "https://flow.google.com",
                         "project_id": None, "document_id": "doc"}
                task = asyncio.create_task(client.post(
                    url + "rpc-read", json={"project_id": project}, headers=headers))
                request = json.loads(await ws.recv())
                assert request["operation"] == "snapshot"
                await ws.send(json.dumps({"type": "reply", "id": request["id"], "result": {
                    "tabs": [{"tab_id": 7, "origin": scope["origin"], "project_id": None}],
                    "selected": scope}}))
                request = json.loads(await ws.recv())
                assert request["operation"] == "probe"
                assert request["params"] == {"scope": scope, "input": {"project_id": project},
                                              "diagnostics": True}
                await ws.send(json.dumps({"type": "reply", "id": request["id"], "result": {
                    "scope": scope, "state": "completed", "rpc_verified": True}}))
                assert (await task).json()["rpc_verified"] is True
                health = await client.post(url + "health", json={}, headers=headers)
                assert health.json()["build"] == "operational-bench-2"
                assert "rpc-read" in health.json()["capabilities"]


@pytest.mark.parametrize("changed", [False, True])
async def test_probe_home_reply_normalizes_null_but_pins_document(changed):
    from flow_mcp.manager import BridgeError
    from flow_mcp.models import Hello, Reply

    manager = Manager("x" * 64)
    scope = {"tab_id": 7, "origin": "https://flow.google.com",
             "project_id": None, "document_id": "doc"}
    project = str(uuid4())

    class Socket:
        async def send(self, message):
            request = json.loads(message)
            if request["operation"] == "snapshot":
                result = {"tabs": [], "selected": scope}
            else:
                assert request["operation"] == "probe"
                assert request["params"]["scope"] == scope
                assert request["params"]["input"] == {"project_id": project}
                result = {"scope": {k: v for k, v in scope.items() if k != "project_id"},
                          "rpc_verified": False, "error": "rpc_rejected"}
                if changed:
                    result["scope"]["document_id"] = "different"
            manager.receive(session, Reply(type="reply", id=request["id"], result=result))

    session = manager.pair(Hello(type="hello", version=1, secret="x" * 64,
                                 installation_id=str(uuid4())), Socket())
    bench = Bench(manager, Jobs(), "y" * 64, 9234)
    if changed:
        with pytest.raises(BridgeError, match="scope_changed"):
            await bench.dispatch("rpc-read", {"project_id": project})
    else:
        result = await bench.dispatch("rpc-read", {"project_id": project})
        assert result["scope"] == scope
        assert result["rpc_verified"] is False
        assert result["error"] == "rpc_rejected"
        assert session.selected.project_id is None


@pytest.mark.parametrize("project", [None, "00000000-0000-4000-8000-000000000010"])
@pytest.mark.parametrize("changed", [False, True])
async def test_home_read_pins_document_and_does_not_derive_project(changed, project):
    from flow_mcp.manager import BridgeError
    from flow_mcp.models import Hello, Reply

    manager = Manager("x" * 64)
    scope = {"tab_id": 7, "origin": "https://flow.google.com",
             "project_id": project, "document_id": "doc"}

    class Socket:
        async def send(self, message):
            request = json.loads(message)
            if request["operation"] == "snapshot":
                result = {"tabs": [], "selected": scope}
            else:
                assert request["operation"] == "home_read"
                assert request["params"] == {"scope": scope}
                result = {"scope": dict(scope), "links": [], "scripts": []}
                if changed:
                    result["scope"]["document_id"] = "different"
            manager.receive(session, Reply(type="reply", id=request["id"], result=result))

    session = manager.pair(Hello(type="hello", version=1, secret="x" * 64,
                                 installation_id=str(uuid4())), Socket())
    bench = Bench(manager, Jobs(), "y" * 64, 9234)
    if changed:
        with pytest.raises(BridgeError, match="scope_changed"):
            await bench.dispatch("home-read", {})
    else:
        assert (await bench.dispatch("home-read", {}))["links"] == []
        assert session.selected.project_id == project
    with pytest.raises(BridgeError, match="invalid_request"):
        await bench.dispatch("home-read", {"url": "https://example.com"})


async def test_operational_previews_require_exact_inputs_and_never_send(tmp_path):
    from test_operations import setup

    from flow_mcp.manager import BridgeError

    manager, session, socket, scope, jobs, _ = setup(tmp_path)
    bench = Bench(manager, jobs, "y" * 64, 9234)
    binding = {"connection_id": session.id, "project_id": scope.project_id}
    for command, value in (("image", {"prompt": "cube"}), ("video", {"prompt": "rotate"})):
        preview = await bench.dispatch(command, {**binding, "input": value})
        assert preview["state"] == "preview"
        with pytest.raises(BridgeError, match="input_mismatch"):
            await bench.dispatch(command, {**binding, "input": {"prompt": "changed"},
                                           "preview_id": preview["job_id"], "approved": True})
        with pytest.raises(BridgeError, match="explicit_approval"):
            await bench.dispatch(command, {**binding, "input": value, "approved": True})
    plan = await bench.dispatch("plan", {"connection_id": session.id})
    assert plan["confirm"] is False and plan["cost_credits"] is None
    assert plan["suggested_counts"]["generation_calls"] == 5
    with pytest.raises(BridgeError, match="connection_id_required"):
        await bench.dispatch("create-preview", {})
    with pytest.raises(BridgeError, match="invalid_request"):
        await bench.dispatch("plan", {"connection_id": session.id, "approved": True})
    assert socket.sent.empty()
    file = tmp_path / "upload.png"
    file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"test")
    upload = await bench.dispatch("upload", {**binding, "file_path": str(file)})
    assert upload["state"] == "preview" and "data" not in upload["preview"]
    file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"changed")
    with pytest.raises(BridgeError, match="input_mismatch"):
        await bench.dispatch("upload", {**binding, "file_path": str(file),
                                        "approved": True, "preview_id": upload["job_id"]})
    result = await bench.dispatch("wait", {**binding, "job_id": upload["job_id"]})
    assert result["state"] == "preview" and socket.sent.empty()


@pytest.mark.parametrize("command,rpc", [("image", "ogiZ0b"), ("video", "YhhmEf"),
                                         ("upscale-image", "SPrCad")])
async def test_bench_job_read_exposes_sanitized_rejected_diagnostics(tmp_path, command, rpc):
    from test_manager import reply
    from test_operations import rejected_diagnostics, setup

    manager, session, socket, scope, jobs, _ = setup(tmp_path)
    bench = Bench(manager, jobs, "y" * 64, 9234)
    binding = {"connection_id": session.id, "project_id": scope.project_id}
    value = {"prompt": "cube"} if command != "upscale-image" else {"resolution": "2K"}
    if command == "upscale-image":
        media = str(uuid4())
        source = jobs.create(session.id, scope, "upload", {})
        jobs.update(source, "completed", {"assets": [{"media_id": media, "kind": "image"}]})
        value = {"media_id": media, "resolution": "2K"}
    preview = await bench.dispatch(command, {**binding, "input": value})
    task = asyncio.create_task(bench.dispatch(command, {
        **binding, "input": value, "preview_id": preview["job_id"], "approved": True}))
    request = await socket.sent.get()
    reply(manager, session, request, {
        "id": request["id"], "scope": scope.model_dump(), "state": "submitted_unverified",
        "error": "rpc_rejected", "diagnostics": rejected_diagnostics(rpc)})
    submitted = await task
    assert submitted["state"] == "submitted_unverified"
    read = await bench.dispatch("job", {**binding, "job_id": preview["job_id"]})
    diagnostics = read["result"]["diagnostics"]
    assert diagnostics["rpc"] == rpc and diagnostics["rpc_code"] == 8
    assert diagnostics["rpc_error_shape"]["type"] == "array"
    assert "private" not in json.dumps(read)
    again = await bench.dispatch("job", {**binding, "job_id": preview["job_id"]})
    assert again["state"] == "submitted_unverified"
    assert socket.sent.empty()


async def test_cli_lifecycle(tmp_path):
    port, ws_port = free_port(), free_port()
    load_secret(tmp_path)
    args = [sys.executable, "-m", "flow_mcp.bench"]
    flags = ["--pairing-dir", str(tmp_path), "--port", str(port), "--ws-port", str(ws_port)]
    process = await asyncio.create_subprocess_exec(*args, "serve", *flags)
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            for _ in range(100):
                try:
                    await client.post(f"http://127.0.0.1:{port}/v1/connections", json={})
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(0.05)
            else:
                pytest.fail("bench did not start")
        for command, expected in (("connections", "connections"), ("stop", "stopping")):
            cli = await asyncio.create_subprocess_exec(
                *args, command, *flags, stdout=asyncio.subprocess.PIPE)
            stdout, _ = await cli.communicate()
            assert cli.returncode == 0
            assert expected in json.loads(stdout)
            assert load_secret(tmp_path / "bench-control").encode() not in stdout
        assert await asyncio.wait_for(process.wait(), 5) == 0
    finally:
        if process.returncode is None:
            process.terminate()
            await process.wait()


async def test_reload_tab_returns_before_reload_and_bench_waits_for_new_document():
    # The reload_tab op must reply BEFORE the navigation so the reply cannot be lost, and
    # the bench must then wait until the selection re-resolves to a NEW document_id.
    from flow_mcp.models import Hello, Reply

    manager = Manager("x" * 64)
    old = {"tab_id": 7, "origin": "https://flow.google.com",
           "project_id": None, "document_id": "old-doc"}
    new = {**old, "document_id": "new-doc"}
    tab = {k: v for k, v in old.items() if k != "document_id"}
    seen_operations = []
    reloaded = False

    class Socket:
        async def send(self, message):
            request = json.loads(message)
            seen_operations.append(request["operation"])
            if request["operation"] == "reload_tab":
                assert request["params"] == {"scope": old}
                nonlocal reloaded
                reloaded = True
                result = {"reloading": 7, "project_id": None, "previous_document_id": "old-doc"}
            elif request["operation"] == "snapshot":
                # Before the reload the tab still has the old document; afterwards it has a
                # freshly-navigated one.
                result = {"tabs": [tab], "selected": new if reloaded else old}
            else:  # pragma: no cover - guard against unexpected ops
                raise AssertionError(request["operation"])
            manager.receive(session, Reply(type="reply", id=request["id"], result=result))

    session = manager.pair(Hello(type="hello", version=1, secret="x" * 64,
                                 installation_id=str(uuid4())), Socket())
    bench = Bench(manager, Jobs(), "y" * 64, 9234)
    # Seed the selected scope so reload-tab has something to reload.
    session.selected = None
    await bench.dispatch("snapshot", {})
    assert session.selected is not None
    result = await bench.dispatch("reload-tab", {})
    assert result["reloading"] == 7
    assert result["previous_document_id"] == "old-doc"
    assert result["document_id"] == "new-doc"
    assert seen_operations.count("reload_tab") == 1
    assert "snapshot" in seen_operations


async def test_await_new_document_tolerates_disconnect_then_reconnect():
    # A tab reload can drop the extension WS. The bench's wait must tolerate the gap and
    # return the new document once the same connection id re-pairs, not raise
    # connection_closed, and must never accept the stale document_id.
    from flow_mcp.manager import BridgeError
    from flow_mcp.models import Hello, Reply

    identity = str(uuid4())
    new = {"tab_id": 7, "origin": "https://flow.google.com",
           "project_id": None, "document_id": "fresh-doc"}
    tab = {k: v for k, v in new.items() if k != "document_id"}
    manager = Manager("x" * 64)
    bench = Bench(manager, Jobs(), "y" * 64, 9234)
    state = {"session": None}

    class Socket:
        async def send(self, message):
            request = json.loads(message)
            assert request["operation"] == "snapshot"
            result = {"tabs": [tab], "selected": new}
            manager.receive(state["session"], Reply(type="reply", id=request["id"], result=result))

    def connect():
        state["session"] = manager.pair(Hello(type="hello", version=1, secret="x" * 64,
                                              installation_id=identity, nickname="t"), Socket())
        return state["session"]

    connect()

    # No connection for a while: the wait must block, not fail immediately.
    manager.disconnected(state["session"])
    with pytest.raises(BridgeError, match="connection_closed"):
        await asyncio.wait_for(
            bench._await_new_document(identity, "old-doc", deadline_seconds=0.5), 2.0)

    # With the socket back, the wait resolves to the fresh document.
    connect()
    assert await asyncio.wait_for(
        bench._await_new_document(identity, "old-doc", deadline_seconds=5.0), 3.0) == "fresh-doc"


async def test_await_new_document_rejects_unchanged_document():
    # If the reload did not actually navigate, the document_id never changes; the wait must
    # fail with scope_changed instead of silently accepting the stale document.
    from flow_mcp.manager import BridgeError
    from flow_mcp.models import Hello, Reply

    identity = str(uuid4())
    stale = {"tab_id": 7, "origin": "https://flow.google.com",
             "project_id": None, "document_id": "old-doc"}
    tab = {k: v for k, v in stale.items() if k != "document_id"}
    manager = Manager("x" * 64)
    bench = Bench(manager, Jobs(), "y" * 64, 9234)
    state = {"session": None}

    class Socket:
        async def send(self, message):
            request = json.loads(message)
            result = {"tabs": [tab], "selected": stale}
            manager.receive(state["session"], Reply(type="reply", id=request["id"], result=result))

    state["session"] = manager.pair(Hello(type="hello", version=1, secret="x" * 64,
                                          installation_id=identity, nickname="t"), Socket())
    with pytest.raises(BridgeError, match="scope_changed"):
        await asyncio.wait_for(
            bench._await_new_document(identity, "old-doc", deadline_seconds=1.0), 3.0)


async def test_captcha_probe_pins_scope_and_surfaces_native_restriction():
    from flow_mcp.manager import BridgeError
    from flow_mcp.models import Hello, Reply

    manager = Manager("x" * 64)
    scope = {"tab_id": 7, "origin": "https://flow.google.com",
             "project_id": "00000000-0000-4000-8000-000000000010", "document_id": "doc-1"}
    captcha = {"native_restriction": True,
               "reasons": ["native_recaptcha_automation_unsupported"],
               "document_ready_state": "complete"}

    class Socket:
        async def send(self, message):
            request = json.loads(message)
            if request["operation"] == "snapshot":
                result = {"tabs": [], "selected": scope}
            else:
                assert request["operation"] == "captcha_probe"
                assert request["params"] == {"scope": scope}
                result = {"scope": scope, "captcha": captcha}
            manager.receive(session, Reply(type="reply", id=request["id"], result=result))

    session = manager.pair(Hello(type="hello", version=1, secret="x" * 64,
                                 installation_id=str(uuid4())), Socket())
    bench = Bench(manager, Jobs(), "y" * 64, 9234)
    result = await bench.dispatch("captcha-probe", {})
    assert result["captcha"] == captcha
    assert result["scope"] == scope
    with pytest.raises(BridgeError, match="invalid_request"):
        await bench.dispatch("captcha-probe", {"url": "https://evil.test"})
