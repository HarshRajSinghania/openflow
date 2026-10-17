import asyncio
import sys
from unittest.mock import AsyncMock, Mock

import pytest

from flow_mcp import cli
from flow_mcp.browser import BrowserError, BrowserState


@pytest.mark.parametrize("args", [[], ["--port", "9240"], ["--transport", "stdio"]])
def test_legacy_dispatch_preserves_arguments(monkeypatch, args, capsys):
    argv = ["openflow", *args]
    monkeypatch.setattr(sys, "argv", argv)
    server = Mock()
    monkeypatch.setattr(cli.server, "main", server)
    cli.main()
    server.assert_called_once_with()
    assert sys.argv is argv
    assert capsys.readouterr().out == ""


def test_setup_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["openflow", "setup"])
    setup_mock = AsyncMock()
    monkeypatch.setattr(cli, "native_setup", setup_mock)
    cli.main()
    setup_mock.assert_awaited_once_with()
    err = capsys.readouterr().err
    assert "Opening dedicated Flow browser" in err
    assert "Close the browser window or press Ctrl+C to save and exit" in err


@pytest.mark.parametrize("exc", [KeyboardInterrupt, asyncio.CancelledError])
def test_setup_interrupted_silently(monkeypatch, exc):
    monkeypatch.setattr(sys, "argv", ["openflow", "setup"])
    monkeypatch.setattr(cli, "native_setup", AsyncMock(side_effect=exc))
    # Must exit cleanly without exception
    cli.main()


@pytest.mark.parametrize(
    "args,headless,inspect",
    [
        (["browser", "start"], True, False),
        (["browser", "start", "--headed"], False, False),
        (["browser", "inspect"], True, True),
        (["browser", "inspect", "--headed"], False, True),
    ],
)
def test_browser_dispatch(monkeypatch, args, headless, inspect, capsys):
    monkeypatch.setattr(sys, "argv", ["openflow", *args])
    command = AsyncMock(return_value=BrowserState("unknown", headless) if inspect else None)
    monkeypatch.setattr(cli, "browser_command", command)
    cli.main()
    command.assert_awaited_once_with(headless=headless, inspect=inspect)
    output = capsys.readouterr()
    assert ('"state": "unknown"' in output.out) == inspect


@pytest.mark.parametrize("target", ["native_setup", "browser_command"])
def test_browser_error_is_actionable(monkeypatch, capsys, target):
    argv = ["openflow", "setup"] if target == "native_setup" else ["openflow", "browser", "inspect"]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(
        cli, target, AsyncMock(side_effect=BrowserError("Install extra"))
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    assert "Install extra" in capsys.readouterr().err


async def test_missing_optional_dependency(monkeypatch):
    from flow_mcp.browser import browser_command, native_setup

    monkeypatch.setitem(sys.modules, "playwright.async_api", None)
    with pytest.raises(BrowserError, match="uv sync --extra browser"):
        await browser_command(headless=True, inspect=True)
    with pytest.raises(BrowserError, match="uv sync --extra browser"):
        await native_setup()
