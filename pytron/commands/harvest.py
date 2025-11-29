import os
import pkg_resources
from pathlib import Path
from typing import Iterable


def generate_nuclear_hooks(output_dir: Path, collect_all_mode: bool = True, blacklist: Iterable[str] | None = None) -> None:
    """
    Scans the current Python environment and writes PyInstaller hook files that
    call `collect_all` (or `collect_submodules` if `collect_all_mode` is False)
    for each installed distribution. Hooks are written as `hook-<package>.py`.

    Parameters:
    - output_dir: directory to place generated hook files
    - collect_all_mode: if True use `collect_all`, else use `collect_submodules`
    - blacklist: optional iterable of package names to skip (case-insensitive)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[Pytron]  Initiating Complete Hook Generation in {output_dir}...")

    if blacklist is None:
        blacklist = [
            'pyinstaller', 'pytron-kit', 'setuptools', 'pip', 'wheel',
            'altgraph', 'pefile', 'pyinstaller-hooks-contrib'
        ]

    bl = {n.lower() for n in blacklist}

    count = 0
    for dist in pkg_resources.working_set:
        name = dist.project_name
        if name.lower() in bl:
            continue

        safe_name = name.replace('-', '_')

        func = 'collect_all' if collect_all_mode else 'collect_submodules'

        hook_content = f"""
# Auto-generated nuclear hook for {name}
from PyInstaller.utils.hooks import {func}

try:
    {"binaries, hiddenimports, datas = collect_all('{0}')".format(name) if collect_all_mode else "hiddenimports = collect_submodules('{0}')\n    binaries, datas = [], []"}
except Exception:
    # Fallback on any error to keep build moving
    binaries, hiddenimports, datas = [], [], []
"""

        hook_file = output_dir / f"hook-{safe_name}.py"
        try:
            hook_file.write_text(hook_content, encoding='utf-8')
            count += 1
        except Exception as e:
            print(f"[Pytron] Warning: failed to write hook for {name}: {e}")

    print(f"[Pytron]  Generated {count} complete hooks. PyInstaller can't miss anything now.")


if __name__ == '__main__':
    generate_nuclear_hooks(Path('temp_hooks'))
