from ..console import log
from ..engines.chrome.forge import setup_engine
import os
import sys


def cmd_engine(args):
    """Entry point for 'pytron engine' commands."""
    if not args.engine_command:
        log("Usage: pytron engine <command> [args]", style="warning")
        return 0

    if args.engine_command == "install":
        if args.name == "chrome":
            log(f"Installing Chrome Mojo Engine...", style="info")
            try:
                target = setup_engine()
                log(f"Engine Forge Successful: {target}", style="success")
            except Exception as e:
                log(f"Engine Forge Failed: {e}", style="error")
                return 1
        else:
            log(f"Unsupported engine: {args.name}", style="error")
            return 1
    return 0
