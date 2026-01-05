import os
from pathlib import Path
from ..console import log

def get_smart_assets(script_dir: Path, frontend_dist: Path | None = None):
    """Recursively collect project assets to include with PyInstaller.

    - Skips known unwanted directories (venv, node_modules, .git, build, dist, etc.)
    - Skips files with Python/source extensions and common dev files
    - Prunes traversal to avoid descending into excluded folders
    - Skips frontend folder since it's handled separately
    Returns a list of strings in the "abs_path{os.pathsep}rel_path" format
    expected by PyInstaller's `--add-data`.
    """
    add_data = []
    EXCLUDE_DIRS = {
        "venv",
        ".venv",
        "env",
        ".env",
        "node_modules",
        ".git",
        ".vscode",
        ".idea",
        "build",
        "dist",
        "__pycache__",
        "site",
        ".pytest_cache",
        "installer",
        "frontend",
    }
    EXCLUDE_SUFFIXES = {".py", ".pyc", ".pyo", ".spec", ".md", ".map"}
    EXCLUDE_FILES = {
        ".gitignore",
        "package-lock.json",
        "npm-debug.log",
        ".DS_Store",
        "thumbs.db",
        "settings.json",
    }

    root_path = str(script_dir)
    for root, dirs, files in os.walk(root_path):
        # Prune directories we never want to enter
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]

        # If this path is part of frontend, skip (we handle frontend separately)
        if frontend_dist and str(frontend_dist) in root:
            continue

        for filename in files:
            if filename in EXCLUDE_FILES:
                continue
            file_path = os.path.join(root, filename)
            _, ext = os.path.splitext(filename)
            if ext.lower() in EXCLUDE_SUFFIXES:
                continue

            rel_path = os.path.relpath(file_path, root_path)
            add_data.append(f"{file_path}{os.pathsep}{rel_path}")
            log(f"Auto-including asset: {rel_path}", style="dim")

    return add_data
