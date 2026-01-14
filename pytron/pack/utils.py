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

    # Items to remove (names)
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
        "msvcrt.dll",  # Nuclear Pruning
    }

    if not preserve_tk:
        remove_names.update({"tcl86t.dll", "tk86t.dll", "tcl", "tk", "tcl8.6", "tk8.6"})
    else:
        log("Preserving Tcl/Tk dependencies (required for splash screen)", style="info")

    config = get_config()
    exclude_patterns = config.get("exclude_patterns", [])

    log(f"Optimizing build directory: {target_path}")

    # Walk top-down so we can modify dirs in-place to skip traversing removed dirs
    for root, dirs, files in os.walk(target_path, topdown=True):
        # Remove directories
        # Modify dirs in-place to avoid traversing into removed directories
        dirs_to_remove = [d for d in dirs if d in remove_names]
        for d in dirs_to_remove:
            full_path = Path(root) / d
            try:
                shutil.rmtree(full_path)
                console.print(f"  - Removed directory: {d}", style="dim")
                dirs.remove(d)
            except Exception as e:
                console.print(f"  ! Failed to remove {d}: {e}", style="error")

        # Remove files
        for f in files:
            should_remove = f in remove_names or f.endswith(".pdb")

            if not should_remove and exclude_patterns:
                for pat in exclude_patterns:
                    if fnmatch.fnmatch(f, pat):
                        should_remove = True
                        break

            if should_remove:
                # SAFETY: Protect Electron Shell package.json
                # The Chrome engine REQUIRES package.json in its shell folder to boot.
                if f == "package.json":
                    # Check consistency of path
                    norm_root = os.path.normpath(root).replace("\\", "/")
                    # If we are inside the chrome shell directory, DO NOT DELETE.
                    if "pytron/engines/chrome/shell" in norm_root:
                        console.print(
                            f"  - Preserved critical entry point: {f}", style="dim"
                        )
                        continue

                full_path = Path(root) / f
                try:
                    os.remove(full_path)
                    console.print(f"  - Removed file: {f}", style="dim")
                except Exception as e:
                    console.print(f"  ! Failed to remove {f}: {e}", style="error")
