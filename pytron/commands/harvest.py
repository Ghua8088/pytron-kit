from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Iterable


def generate_nuclear_hooks(
    output_dir: Path,
    collect_all_mode: bool = True,
    blacklist: Iterable[str] | None = None,
    search_path: list[str] | None = None,
    whitelist: Iterable[str] | None = None,
) -> None:
    """
    Scans the current Python environment and writes PyInstaller hook files that
    call `collect_all` (or `collect_submodules` if `collect_all_mode` is False)
    for each installed distribution. Hooks are written as `hook-<package>.py`.

    Parameters:
    - output_dir: directory to place generated hook files
    - collect_all_mode: if True use `collect_all`, else use `collect_submodules`
    - blacklist: optional iterable of package names to skip (case-insensitive)
    - search_path: optional list of paths to search for distributions (defaults to sys.path)
    - whitelist: optional iterable of package names to ONLY include (overrides scan)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[Pytron]  Initiating Complete Hook Generation in {output_dir}...")

    if blacklist is None:
        blacklist = [
            "pyinstaller",
            "pytron-kit",
            "setuptools",
            "pip",
            "wheel",
            "altgraph",
            "pefile",
            "pyinstaller-hooks-contrib",
        ]

    bl = {n.lower() for n in blacklist}
    wl = {n.lower() for n in whitelist} if whitelist else None

    count = 0
    # Use the provided search_path if available
    dists = (
        importlib_metadata.distributions(path=search_path)
        if search_path
        else importlib_metadata.distributions()
    )

    for dist in dists:
        # Try to obtain a project/distribution name comparable to pkg_resources' project_name
        name = None
        try:
            # metadata is an email.message.Message mapping; 'Name' is the canonical key
            name = dist.metadata.get("Name") or getattr(dist, "name", None)
        except Exception:
            try:
                name = getattr(dist, "name", None)
            except Exception:
                name = None

        if not name:
            # fallback: try the package root name derived from the distribution path
            try:
                name = Path(dist.locate_file("")).name
            except Exception:
                continue

        if wl is not None:
            # If whitelist is provided, skip if not in it
            if name.lower() not in wl:
                continue

        if name.lower() in bl:
            continue

        safe_name = name.replace("-", "_")

        func = "collect_all" if collect_all_mode else "collect_submodules"

        if collect_all_mode:
            body = f"binaries, hiddenimports, datas = collect_all('{name}')"
        else:
            body = f"hiddenimports = collect_submodules('{name}')\n    binaries, datas = [], []"

        hook_content = f"""
# Auto-generated nuclear hook for {name}
from PyInstaller.utils.hooks import {func}

try:
    {body}
except Exception:
    # Fallback on any error to keep build moving
    binaries, hiddenimports, datas = [], [], []
"""

        hook_file = output_dir / f"hook-{safe_name}.py"
        try:
            hook_file.write_text(hook_content, encoding="utf-8")
            count += 1
        except Exception as e:
            print(f"[Pytron] Warning: failed to write hook for {name}: {e}")

    print(
        f"[Pytron] Generated {count} complete hooks. PyInstaller can't miss anything now."
    )


if __name__ == "__main__":
    generate_nuclear_hooks(Path("temp_hooks"))
