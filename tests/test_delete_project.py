"""Synthetic fixtures only. No browser/account/live RPC traffic."""
import asyncio
import hashlib
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from test_managed import driver_at

from flow_mcp.api import create_app
from flow_mcp.jobs import Jobs
from flow_mcp.manager import BridgeError
from flow_mcp.models import Observation
from flow_mcp.server import create_server
from flow_mcp.service import Operations

TARGET = "11111111-2222-3333-4444-555555555555"
OTHER = "11111111-2222-3333-4444-666666666666"
EMAIL = "synthetic@example.test"


def setup_delete():
    manager, driver, page = driver_at()
    session = driver.session
    scope = session.selected
    jobs = Jobs()
    ops = Operations(manager, jobs)
    driver.prepare_project = AsyncMock()
    driver.verify_scope = AsyncMock()
    driver.observe = AsyncMock(return_value=Observation(
        scope=scope, email=EMAIL, email_confirmed=True, source="google_account_aria",
        observed_at="2026-10-18T00:00:00.000Z",
    ))

    async def request(session, operation, params, **kwargs):
        if operation == "list_projects":
            return {"scope": scope.model_dump(), "state": "completed", "projects": [
                {"project_id": TARGET, "title": "Synthetic disposable"},
                {"project_id": OTHER, "title": "Other disposable"},
            ]}
        assert operation == "delete_project"
        return {"scope": scope.model_dump(), "state": "completed", "deleted_project_id": TARGET}

    manager.request = AsyncMock(side_effect=request)
    return manager, driver, page, scope, jobs, ops


async def test_preview_private_identity_and_completed_replay():
    manager, driver, page, scope, jobs, ops = setup_delete()
    preview = await ops.delete_project(driver.session.id, TARGET)
    digest = hashlib.sha256(EMAIL.encode()).hexdigest()
    assert manager.request.await_count == 1
    assert manager.request.await_args.args[1] == "list_projects"
    assert preview["preview"]["rpc"] == "QI2zvc"
    assert EMAIL not in json.dumps(preview) and digest not in json.dumps(preview)
    assert jobs.get(preview["job_id"])["input"]["account_sha256"] == digest
    result = await ops.delete_project(driver.session.id, TARGET, True, preview["job_id"])
    assert result["state"] == "completed"
    assert driver.session.selected is None
    assert len([c for c in manager.request.await_args_list if c.args[1] == "delete_project"]) == 1
    replay = await ops.delete_project(driver.session.id, TARGET, True, preview["job_id"])
    assert replay["not_resubmitted"]
    cached = await ops.get(preview["job_id"], driver.session.id, TARGET, True)
    assert cached["state"] == "completed"
    page.evaluate.assert_not_awaited()


@pytest.mark.parametrize(
    "change", ["account", "unknown", "title", "document", "target", "connection"]
)
async def test_changed_bindings_fail_before_delete(change):
    manager, driver, _, scope, jobs, ops = setup_delete()
    preview = await ops.delete_project(driver.session.id, TARGET)
    connection, target = driver.session.id, TARGET
    if change == "account":
        driver.observe.return_value = driver.observe.return_value.model_copy(
            update={"email": "different@example.test"}
        )
    elif change == "unknown":
        driver.observe.return_value = Observation(scope=scope)
    elif change == "title":
        manager.request.side_effect = None
        manager.request.return_value = {"scope": scope.model_dump(), "state": "completed",
                                       "projects": [{"project_id": TARGET, "title": "Changed"}]}
    elif change == "document":
        driver.session.selected = scope.model_copy(update={"document_id": "other-document"})
    elif change == "target":
        target = OTHER
    else:
        connection = OTHER
    with pytest.raises(BridgeError):
        await ops.delete_project(connection, target, True, preview["job_id"])
    assert jobs.get(preview["job_id"])["state"] == "preview"
    assert not any(c.args[1] == "delete_project" for c in manager.request.await_args_list)


@pytest.mark.parametrize("title", [None, "x" * 200, "x" * 201])
async def test_limited_list_and_truncated_title_fail_closed(title):
    manager, driver, _, scope, _, ops = setup_delete()
    manager.request.side_effect = None
    manager.request.return_value = {"scope": scope.model_dump(), "state": "completed",
                                   "projects": [] if title is None else [
                                       {"project_id": TARGET, "title": title}], "has_more": True}
    with pytest.raises(BridgeError, match="limited_list|truncated"):
        await ops.delete_project(driver.session.id, TARGET)


async def test_unknown_submission_blocks_only_same_target_and_no_retry():
    manager, driver, _, scope, jobs, ops = setup_delete()
    preview = await ops.delete_project(driver.session.id, TARGET)
    original = manager.request.side_effect

    async def request(session, operation, params, **kwargs):
        if operation == "delete_project":
            raise BridgeError("request_timeout")
        return await original(session, operation, params, **kwargs)

    manager.request.side_effect = request
    result = await ops.delete_project(driver.session.id, TARGET, True, preview["job_id"])
    assert result["state"] == "submitted_unverified"
    replay = await ops.delete_project(driver.session.id, TARGET, True, preview["job_id"])
    assert replay["not_resubmitted"]
    driver.session.selected = scope
    with pytest.raises(BridgeError, match="do_not_retry"):
        await ops.delete_project(driver.session.id, TARGET)
    assert (await ops.delete_project(driver.session.id, OTHER))["state"] == "preview"
    assert jobs.get(preview["job_id"])["state"] == "submitted_unverified"


async def test_concurrent_confirmation_one_delete():
    manager, driver, _, _, _, ops = setup_delete()
    preview = await ops.delete_project(driver.session.id, TARGET)
    results = await asyncio.gather(*[
        ops.delete_project(driver.session.id, TARGET, True, preview["job_id"]) for _ in range(2)
    ], return_exceptions=True)
    assert sum(isinstance(r, dict) and r["state"] == "completed" for r in results) >= 1
    assert len([c for c in manager.request.await_args_list if c.args[1] == "delete_project"]) == 1


async def test_cross_database_claim_and_restart(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    first = Jobs(path)
    _, _, _, scope, _, _ = setup_delete()
    a = first.create(OTHER, scope, "delete_project", {"project_id": TARGET})
    b = first.create(OTHER, scope, "delete_project", {"project_id": TARGET})
    second = Jobs(path)
    assert first.claim_delete(a, OTHER, TARGET)
    with pytest.raises(ValueError, match="do_not_retry"):
        second.claim_delete(b, OTHER, TARGET)
    restarted = Jobs(path)
    assert restarted.get(a)["state"] == "submitted_unverified"
    assert restarted.delete_in_flight(OTHER, TARGET)


async def test_extension_unsupported_before_observation():
    manager, driver, page, _, _, ops = setup_delete()
    driver.supports_project_deletion = False
    with pytest.raises(BridgeError, match="unsupported_managed_browser_only"):
        await ops.delete_project(driver.session.id, TARGET)
    manager.request.assert_not_awaited()
    page.evaluate.assert_not_awaited()


@pytest.mark.parametrize("target", ["invalid", None, "", "../project"])
async def test_managed_dispatch_invalid_target(target):
    manager, driver, page, scope, _, _ = setup_delete()
    with pytest.raises(BridgeError, match="invalid_request"):
        await driver.dispatch("delete_project", {"scope": scope.model_dump(), "input": {
            "project_id": target, "expected_title": "Synthetic", "account_sha256": "a" * 64,
        }})
    page.evaluate.assert_not_awaited()


async def test_api_and_mcp_surface():
    manager, driver, _, _, jobs, _ = setup_delete()
    app = create_app(manager, 9233, jobs, backend="browser")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(f"/projects/{TARGET}/delete", json={
            "connection_id": driver.session.id,
        })
        assert response.status_code == 200
        assert response.json()["state"] == "preview"
        assert (await client.post("/projects/not-uuid/delete", json={
            "connection_id": driver.session.id,
        })).status_code == 422
    tools = await create_server(manager, 9233, jobs).list_tools()
    tool = next(t for t in tools if t.name == "delete_project")
    assert tool.annotations.destructiveHint is True
    assert set(tool.inputSchema["properties"]) == {
        "connection_id", "project_id", "confirm", "preview_id",
    }
