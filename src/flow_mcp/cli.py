import argparse
import asyncio
import json
import sys

from flow_mcp import server
from flow_mcp.browser import BrowserError, browser_command, native_setup


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] not in {"setup", "browser"}:
        if args in (["--help"], ["-h"]):
            print(
                "Managed browser (experimental):\n"
                "  openflow setup                   Open manual login window\n"
                "  openflow browser start           Keep browser open (headless)\n"
                "  openflow browser inspect         Inspect saved session and exit\n"
                "  openflow browser --help          Browser command options\n\n"
                "Default MCP server options:"
            )
        server.main()
        return

    parser = argparse.ArgumentParser(prog="openflow")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup", help="Open a dedicated browser for manual Flow login")
    browser = commands.add_parser("browser", help="Experimental browser without extension")
    actions = browser.add_subparsers(dest="action", required=True)
    for name in ("start", "inspect"):
        action = actions.add_parser(name)
        modes = action.add_mutually_exclusive_group()
        modes.add_argument("--headed", action="store_true", help="Show browser window")
        modes.add_argument("--headless", action="store_false", dest="headed")
        action.set_defaults(headed=False)
    parsed = parser.parse_args(args)
    is_setup = parsed.command == "setup"
    inspect = not is_setup and parsed.action == "inspect"
    headless = not is_setup and not parsed.headed
    if not inspect:
        print(
            "Opening dedicated Flow browser. Log in manually in headed mode.\n"
            "Close the browser window or press Ctrl+C to save and exit.",
            file=sys.stderr,
        )
    try:
        if is_setup:
            asyncio.run(native_setup())
            return
        result = asyncio.run(browser_command(headless=headless, inspect=inspect))
    except (KeyboardInterrupt, asyncio.CancelledError):
        return
    except (BrowserError, OSError):
        # BrowserError contains only our sanitized, actionable messages.
        error = sys.exception()
        message = str(error) if isinstance(error, BrowserError) else "Cannot access browser data."
        parser.exit(1, f"openflow: {message}\n")
    if result is not None:
        print(json.dumps(result.to_dict()))
        if result.state == "navigation_failed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
