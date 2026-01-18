import argparse
import shutil
import subprocess
from pathlib import Path
from .helpers import get_config



def cmd_build_frontend(args: argparse.Namespace) -> int:
    folder = Path(args.folder)
    if not folder.exists():
        print(f"Folder not found: {folder}")
        return 1

    config = get_config()
    provider = config.get("frontend_provider", "npm")
    provider_bin = shutil.which(provider)
    if not provider_bin:
        print(f"{provider} not found in PATH")
        return 1

    print(f"Running {provider} run build in {folder}")
    return subprocess.call(
        [provider_bin, "run", "build"],
        cwd=str(folder),
        shell=False,
    )  # nosec B603
