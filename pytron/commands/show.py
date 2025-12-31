import argparse
import subprocess
from pathlib import Path
from .helpers import get_venv_python_path
from ..console import log, run_command_with_output


def cmd_show(args: argparse.Namespace) -> int:
    """
    Shows list of installed packages in the virtual environment.
    """
    venv_dir = Path("env")
    venv_python = get_venv_python_path(venv_dir)

    if not venv_python.exists():
        log(
            f"Virtual environment not found at {venv_dir}. Run 'pytron install' first.",
            style="error",
        )
        return 1

    log(f"Installed packages in {venv_dir}:")
    ret = run_command_with_output([str(venv_python), "-m", "pip", "list"])
    return ret
