import os
from pathlib import Path
from ..console import log


def get_smart_assets(
    script_dir: Path,
    frontend_dist: Path | None = None,
    include_patterns: list | None = None,
    exclude_patterns: list | None = None,
):
    """Recursively collect project assets to include with PyInstaller.

    - Skips known unwanted directories (venv, node_modules, .git, build, dist, etc.)
    - Skips files with Python/source extensions and common dev files
    - respects include_patterns (overrides defaults) and exclude_patterns
    - Skips frontend folder since it's handled separately
    Returns a list of strings in the "abs_path{os.pathsep}rel_path" format
    expected by PyInstaller's `--add-data`.
    """
    import fnmatch

    add_data = []
    # Default Excludes
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
        "pnpm-lock.yaml",
        "bun.lockb",
    }

    include_patterns = include_patterns or []
    exclude_patterns = exclude_patterns or []

    root_path = str(script_dir)
    for root, dirs, files in os.walk(root_path):
        # Prune directories we never want to enter
        # We always exclude invalid dirs unless explicitly included
        # But for directories, "including" is tricky in os.walk.
        # We'll stick to default prune for safety, but check user patterns.

        # Filter dirs in-place
        i = 0
        while i < len(dirs):
            d = dirs[i]
            d_path = os.path.join(root, d)
            d_rel = os.path.relpath(d_path, root_path)

            # Check user excludes for folders
            is_user_excluded = False
            for pat in exclude_patterns:
                if fnmatch.fnmatch(d, pat) or fnmatch.fnmatch(d_rel, pat):
                    is_user_excluded = True
                    break

            if is_user_excluded:
                del dirs[i]
                continue

            # Default excludes (only if not explicitly included?)
            # For simplicity, we enforce default folder excludes unless strictly needed.
            if d in EXCLUDE_DIRS or d.startswith("."):
                del dirs[i]
                continue

            i += 1

        # If this path is part of frontend, skip (we handle frontend separately)
        if frontend_dist and str(frontend_dist) in root:
            continue

        for filename in files:
            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, root_path)

            # 1. User Exclude (Highest Priority)
            is_user_excluded = False
            for pat in exclude_patterns:
                if fnmatch.fnmatch(filename, pat) or fnmatch.fnmatch(rel_path, pat):
                    is_user_excluded = True
                    break
            if is_user_excluded:
                continue

            # 2. User Include (Overrides defaults)
            is_user_included = False
            for pat in include_patterns:
                if fnmatch.fnmatch(filename, pat) or fnmatch.fnmatch(rel_path, pat):
                    is_user_included = True
                    break

            if is_user_included:
                add_data.append(f"{file_path}{os.pathsep}{rel_path}")
                log(f"Explicitly included asset: {rel_path}", style="cyan")
                continue

            # 3. Default Checks
            if filename in EXCLUDE_FILES:
                continue

            _, ext = os.path.splitext(filename)
            if ext.lower() in EXCLUDE_SUFFIXES:
                continue

            # If passed all checks
            add_data.append(f"{file_path}{os.pathsep}{rel_path}")
            log(f"Auto-including asset: {rel_path}", style="dim")

    return add_data
