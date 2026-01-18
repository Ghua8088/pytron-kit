import os
import sys
import shutil
import subprocess  # nosec B404
import platform
from pathlib import Path
from ..console import log, run_command_with_output, console, Rule
from ..commands.helpers import get_python_executable, get_venv_site_packages
from .installers import build_installer


def run_nuitka_build(
    args,
    script,
    out_name,
    settings,
    app_icon,
    package_dir,
    add_data,
    frontend_dist,
    progress,
    task,
    package_context=None,
):
    log("Packaging using Nuitka (Native Compilation)...", style="info")

    # Context handling
    extra_plugin_args = []
    if package_context:
        extra_plugin_args.extend(package_context.get("extra_args", []))
        # Nuitka uses different flags for hidden imports and assets
        # For simplicity, we'll try to map common ones
        for imp in package_context.get("hidden_imports", []):
            extra_plugin_args.append(f"--include-module={imp}")
        for dat in package_context.get("add_data", []):
            # add_data usually is src;dest
            if os.pathsep in dat:
                src, dest = dat.split(os.pathsep, 1)
                extra_plugin_args.append(f"--include-data-files={src}={dest}")

    log(f"Debug: Nuitka block entered. Script: {script}", style="dim")

    # Check for Nuitka
    if (
        not shutil.which("nuitka")
        and not get_venv_site_packages(get_python_executable())
        .joinpath("nuitka")
        .exists()
    ):
        log("Nuitka not found. Installing...", style="warning")
        subprocess.check_call(
            [get_python_executable(), "-m", "pip", "install", "nuitka", "zstandard"]
        )  # nosec B603

    # NOTE: Using 'out_name' calculated earlier in the function (which is sanitized from settings.get('title'))
    log(f"Debug: Resolving output name: {out_name}", style="dim")

    # Basic Nuitka Command
    cmd = [
        get_python_executable(),
        "-m",
        "nuitka",
        "--standalone",
        "--onefile",
        "--assume-yes-for-downloads",
        (
            f"--output-filename={out_name}.exe"
            if sys.platform == "win32"
            else f"--output-filename={out_name}.bin"
        ),
        "--output-dir=dist",
    ]

    # Metadata & Versioning
    # Nuitka allows embedding this info directly into the EXE
    title = settings.get("title") or args.name or script.stem.capitalize()
    version = settings.get("version", "1.0.0")
    author = settings.get("author") or settings.get("company") or "Pytron User"
    desc = settings.get("description", title)
    copyright_text = settings.get("copyright", f"Copyright © {author}")

    cmd.extend(
        [
            f"--company-name={author}",
            f"--product-name={title}",
            f"--file-version={version}",
            f"--product-version={version}",
            f"--file-description={desc}",
            f"--copyright={copyright_text}",
        ]
    )

    # Add Icon
    # Use app_icon (resolved) instead of args.icon (raw CLI arg)
    if app_icon:
        if sys.platform == "win32":
            cmd.append(f"--windows-icon-from-ico={app_icon}")
        elif sys.platform == "linux":
            cmd.append(f"--linux-icon={app_icon}")

    # Hiding Console
    # Nuitka defaults to visible console. We now default to HIDDEN.
    # User must pass --console to see it.
    if getattr(args, "console", False):
        if sys.platform == "win32":
            cmd.append("--windows-console-mode=force")
    else:
        if sys.platform == "win32":
            cmd.append("--windows-console-mode=disable")

    # Include Webview DLLs (Critical for runtime)
    dll_name = "webview.dll"
    if sys.platform == "linux":
        dll_name = "libwebview.so"
    elif sys.platform == "darwin":
        dll_name = (
            "libwebview_arm64.dylib"
            if platform.machine() == "arm64"
            else "libwebview_x64.dylib"
        )

    dll_src = os.path.join(package_dir, "pytron", "dependancies", dll_name)
    if os.path.exists(dll_src):
        # Ensure it is placed where bindings.py expects it (pytron/dependancies/)
        cmd.append(f"--include-data-file={dll_src}=pytron/dependancies/{dll_name}")
        log(f"Debug: Inclusion of DLL: {dll_src}", style="dim")
    else:
        log(f"Warning: Could not find webview binary at {dll_src}", style="warning")

    # Process --add-data (gathered earlier)
    # Format in add_data is "src;dest" (win) or "src:dest"
    for item in add_data:
        if os.pathsep in item:
            src, dst = item.split(os.pathsep, 1)  # Split only on first occurrence
            # Nuitka expects src=dst
            # If src is dir, use --include-data-dir
            if os.path.isdir(src):
                cmd.append(f"--include-data-dir={src}={dst}")
            else:
                # Fix for Nuitka: dst cannot be just '.'
                if dst == ".":
                    dst = os.path.basename(src)
                cmd.append(f"--include-data-file={src}={dst}")
    # Add extra plugin args from package_context
    if extra_plugin_args:
        cmd.extend(extra_plugin_args)

    # Run It
    cmd.append(str(script))
    log(f"Running Nuitka: {' '.join(cmd)}", style="dim")

    ret_code = run_command_with_output(cmd, style="dim")

    if ret_code == 0:
        if args.installer:
            # Move the onefile binary to a folder structure for Installer
            target_dir = Path("dist") / out_name
            target_dir.mkdir(exist_ok=True, parents=True)

            src_exe = Path("dist") / (
                f"{out_name}.exe" if sys.platform == "win32" else f"{out_name}.bin"
            )
            dst_exe = target_dir / (
                f"{out_name}.exe" if sys.platform == "win32" else f"{out_name}.exe"
            )

            if src_exe.exists():
                if dst_exe.exists():
                    os.remove(dst_exe)
                shutil.move(str(src_exe), str(dst_exe))

            # Manual Side-Load: Copy settings.json to output dir
            # Nuitka bundling is tricky, side-loading is safer and allows user config.
            src_settings = script.parent / "settings.json"
            if src_settings.exists():
                shutil.copy(str(src_settings), str(target_dir / "settings.json"))
                shutil.copy(str(src_settings), str(target_dir / "settings.json"))
                log("Side-loaded settings.json to output directory", style="dim")

            # Side-Load Icon
            if app_icon and os.path.exists(app_icon):
                try:
                    shutil.copy(app_icon, str(target_dir / os.path.basename(app_icon)))
                    log(
                        f"Side-loaded icon: {os.path.basename(app_icon)}",
                        style="dim",
                    )
                except Exception as e:
                    log(f"Warning side-loading icon: {e}", style="warning")

            # Side-Load Frontend
            # We need to replicate the folder structure (e.g. frontend/dist)
            if frontend_dist and frontend_dist.exists():
                # We assume 'rel' path from earlier calculation is what we want (e.g. frontend/dist)
                # Or just mirror it clearly. Usually relative to script parent.
                rel_fe = frontend_dist.relative_to(script.parent)
                dest_fe = target_dir / rel_fe
                if dest_fe.exists():
                    shutil.rmtree(dest_fe)
                shutil.copytree(frontend_dist, dest_fe)
                log(f"Side-loaded frontend assets to {rel_fe}", style="dim")

            # Now run installer
            progress.update(task, description="Building Installer...", completed=80)
            ret_code = build_installer(out_name, script.parent, args.icon)

    progress.stop()
    if ret_code == 0:
        console.print(Rule("[bold green]Success (Nuitka)"))
        log(f"App packaged successfully (Nuitka)", style="bold green")
    return ret_code
