import argparse
import sys
import shutil
import subprocess
from pathlib import Path
from .helpers import locate_frontend_dir
from ..console import log, run_command_with_output, get_progress


def cmd_frontend_install(args: argparse.Namespace) -> int:
    """
    Installs libraries into the frontend project.
    """
    # Try to find frontend dir
    # Use current directory as robust start
    frontend_dir = locate_frontend_dir(Path("."))

    if not frontend_dir:
        log("Could not locate a frontend directory (package.json).", style="error")
        return 1

    log(f"Found frontend in: {frontend_dir}", style="dim")

    # Check for package manager
    npm = shutil.which("npm")
    if not npm:
        log("npm is not installed or not in PATH.", style="error")
        return 1

    packages = args.packages
    prog = get_progress()
    prog.start()
    if not packages:
        # Just run install
        task = prog.add_task("Installing JS dependencies...", total=None)
        cmd = ["npm", "install"]
    else:
        task = prog.add_task(f"Installing {len(packages)} JS packages...", total=None)
        cmd = ["npm", "install"] + packages

    ret = run_command_with_output(cmd, cwd=str(frontend_dir))
    prog.stop()

    if ret == 0:
        log("Frontend dependencies installed successfully.", style="success")
    else:
        log("Error installing frontend packages.", style="error")
        return 1

    return 0
