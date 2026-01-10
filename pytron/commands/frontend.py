import argparse
import sys
import shutil
import subprocess
from pathlib import Path
from .helpers import locate_frontend_dir, get_config
from ..console import log, run_command_with_output, get_progress


def cmd_frontend(args: argparse.Namespace) -> int:
    """
    Proxy command that runs '<provider> <args>' in the frontend directory.
    """
    # Try to find frontend dir
    frontend_dir = locate_frontend_dir(Path("."))

    if not frontend_dir:
        log("Could not locate a frontend directory (package.json).", style="error")
        return 1

    # Order of precedence: CLI Arg > settings.json > default 'npm'
    config = get_config()
    default_provider = config.get("frontend_provider", "npm")
    provider = getattr(args, "provider", None) or default_provider

    # Check for provider binary
    provider_bin = shutil.which(provider)
    if not provider_bin:
        log(f"'{provider}' is not installed or not in PATH.", style="error")
        return 1

    npm_args = args.npm_args
    if not npm_args:
        # Default to 'install' if no args provided
        npm_args = ["install"]

    # Special case: 'install' gets the progress bar for better UX
    if "install" in npm_args:
        prog = get_progress()
        prog.start()
        task_msg = (
            f"[{provider}] Installing packages..."
            if len(npm_args) > 1
            else f"[{provider}] Installing JS dependencies..."
        )
        task = prog.add_task(task_msg, total=None)
        cmd = [provider_bin] + npm_args
        ret = run_command_with_output(
            cmd, cwd=str(frontend_dir), shell=(sys.platform == "win32")
        )
        prog.stop()
    else:
        # For 'run dev', 'build', etc., just stream the output directly
        cmd = [provider_bin] + npm_args
        log(f"Running: {provider} {' '.join(npm_args)}", style="dim")
        ret = run_command_with_output(
            cmd, cwd=str(frontend_dir), shell=(sys.platform == "win32")
        )

    if ret == 0:
        log(f"Frontend command ({provider}) completed successfully.", style="success")
    else:
        log(f"Command failed ({provider} {' '.join(npm_args)})", style="error")
        return 1

    return 0
