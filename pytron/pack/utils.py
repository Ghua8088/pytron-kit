import os
import sys
import shutil
from pathlib import Path
from ..console import console, log
import fnmatch
from ..commands.helpers import get_config


def cleanup_dist(dist_path: Path, preserve_tk: bool = False):
    """
    Removes unnecessary files (node_modules, node.exe, etc) from the build output
    to optimize the package size.
    """
    target_path = dist_path
    # On macOS, if we built a bundle, the output is .app
    if sys.platform == "darwin":
        app_path = dist_path.parent / f"{dist_path.name}.app"
        if app_path.exists():
            target_path = app_path

    if not target_path.exists():
        return

    # Items to remove (exact names)
    remove_names = {
        "node_modules",
        "node.exe",
        "npm.cmd",
        "npx.cmd",
        ".git",
        ".gitignore",
        ".vscode",
        ".idea",
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "__pycache__",
        ".env",
        "venv",
        ".venv",
        "python.exe",
        "pythonw.exe",
        "lib2to3",
        "idle_test",
        "test",
        "tests",
        "unit_test",
        "include",
        "msvcrt.dll",
        "LICENSE",
        "README.md",
        "CHANGELOG.md",
    }

    if not preserve_tk:
        remove_names.update({"tcl86t.dll", "tk86t.dll", "tcl", "tk", "tcl8.6", "tk8.6"})

    log(f"Aggressively optimizing: {target_path}")

    for root, dirs, files in os.walk(target_path, topdown=True):
        # 1. PRUNE DIRECTORIES
        dirs_to_remove = []
        for d in dirs:
            # Remove exact matches OR metadata patterns
            if d in remove_names or d.endswith((".dist-info", ".egg-info")):
                dirs_to_remove.append(d)

        for d in dirs_to_remove:
            full_path = Path(root) / d
            try:
                shutil.rmtree(full_path)
                console.print(f"  - Pruned: {d}", style="dim")
                dirs.remove(d)
            except Exception:
                pass

        # 2. PRUNE FILES
        for f in files:
            # We remove common clutter names and development artifacts like .pdb and .pyi
            # We DON'T remove all .txt files globally because they are often legitimate assets (e.g. certificates, data).
            should_remove = f in remove_names or f.endswith((".pdb", ".pyi"))

            if should_remove:
                # SAFETY: Protect critical entry points in embedded engines
                if (
                    f == "package.json"
                    and "pytron/engines/chrome/shell" in root.replace("\\", "/")
                ):
                    continue

                full_path = Path(root) / f
                try:
                    os.remove(full_path)
                except Exception:
                    pass


def get_native_engine_binaries() -> list[str]:
    """Returns the names of the native engine binary artifacts."""
    binaries = []
    if sys.platform == "win32":
        binaries.append("pytron_native.pyd")
        binaries.append("WebView2Loader.dll")
    elif sys.platform == "darwin":
        binaries.append("pytron_native.so")
    else:
        binaries.append("pytron_native.so")
    return binaries
