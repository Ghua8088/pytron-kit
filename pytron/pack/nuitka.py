import os
import sys
import shutil
import subprocess  # nosec B404
import platform
from pathlib import Path
from ..console import log, run_command_with_output, console, Rule
from ..commands.helpers import get_python_executable, get_venv_site_packages
from .installers import build_installer


from .pipeline import BuildContext


def run_nuitka_build(context: BuildContext):
    """
    Core Nuitka compiler stage.
    """
    log("Packaging using Nuitka (Native Compilation)...", style="info")

    # 1. Check for Nuitka
    import shutil
    from .pipeline import BuildContext
    from ..commands.helpers import get_python_executable, get_venv_site_packages

    python_exe = get_python_executable()
    if (
        not shutil.which("nuitka")
        and not get_venv_site_packages(python_exe).joinpath("nuitka").exists()
    ):
        log("Nuitka not found. Installing...", style="warning")
        subprocess.check_call(
            [python_exe, "-m", "pip", "install", "nuitka", "zstandard"]
        )

    # 2. Build Nuitka Command
    cmd = [
        python_exe,
        "-m",
        "nuitka",
        "--standalone",
        "--assume-yes-for-downloads",
        "--output-dir=dist",
    ]

    if context.is_onefile:
        cmd.append("--onefile")
        ext = ".exe" if sys.platform == "win32" else ".bin"
        cmd.append(f"--output-filename={context.out_name}{ext}")

    # Metadata
    title = context.settings.get("title") or context.out_name
    version = context.settings.get("version", "1.0.0")
    author = context.settings.get("author") or "Pytron User"

    cmd.extend(
        [
            f"--company-name={author}",
            f"--product-name={title}",
            f"--file-version={version}",
            f"--product-version={version}",
        ]
    )

    if context.app_icon:
        if sys.platform == "win32":
            cmd.append(f"--windows-icon-from-ico={context.app_icon}")
        elif sys.platform == "linux":
            cmd.append(f"--linux-icon={context.app_icon}")

    if context.settings.get("console"):
        if sys.platform == "win32":
            cmd.append("--windows-console-mode=force")
    else:
        if sys.platform == "win32":
            cmd.append("--windows-console-mode=disable")

    # Assets
    # Native Engine Binaries
    from .utils import get_native_engine_binaries

    binaries = get_native_engine_binaries()

    for bin_name in binaries:
        bin_src = context.package_dir / "pytron" / "dependencies" / bin_name
        if bin_src.exists():
            cmd.append(f"--include-data-file={bin_src}=pytron/dependencies/{bin_name}")

    for item in context.add_data:
        if os.pathsep in item:
            src, dst = item.split(os.pathsep, 1)
            if os.path.isdir(src):
                cmd.append(f"--include-data-dir={src}={dst}")
            else:
                if dst == ".":
                    dst = os.path.basename(src)
                cmd.append(f"--include-data-file={src}={dst}")

    # Hidden Imports
    for imp in context.hidden_imports:
        cmd.append(f"--include-module={imp}")

    cmd.append(str(context.script))

    log(f"Running Nuitka: {' '.join(cmd)}", style="dim")
    ret_code = run_command_with_output(cmd, style="dim")

    return ret_code
