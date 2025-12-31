import argparse
import shutil
import subprocess
from pathlib import Path


def cmd_build_frontend(args: argparse.Namespace) -> int:
    folder = Path(args.folder)
    if not folder.exists():
        print(f"Folder not found: {folder}")
        return 1

    # Prefer npm if available
    npm = shutil.which("npm")
    if not npm:
        print("npm not found in PATH")
        return 1

    print(f"Running npm run build in {folder}")
    return subprocess.call([npm, "run", "build"], cwd=str(folder))
