import argparse
import sys
import json
import os
from pathlib import Path
from ..console import (
    console,
    log,
    get_progress,
    print_rule,
    run_command_with_output,
    Rule,
)
from .harvest import generate_nuclear_hooks
from .helpers import (
    get_python_executable,
    get_venv_site_packages,
)
from ..pack.assets import get_smart_assets
from ..pack.installers import build_installer
from ..pack.utils import cleanup_dist
from ..pack.nuitka import run_nuitka_build
from ..pack.pyinstaller import run_pyinstaller_build
from ..pack.secure import run_secure_build


def cmd_package(args: argparse.Namespace) -> int:
    script_path = args.script
    if not script_path:
        script_path = "app.py"

    script = Path(script_path)
    # Resolve script path early for reliable relative lookups
    script = script.resolve()
    if not script.exists():
        log(f"Script not found: {script}", style="error")
        return 1

    console.print(Rule("[bold cyan]Pytron Builder"))

    progress = get_progress()
    task = progress.add_task("Starting...", total=100)
    progress.start()

    # If the user provided a .spec file, use it directly
    if script.suffix == ".spec":
        log(f"Packaging using spec file: {script}")
        progress.update(task, description="Building from Spec...", completed=10)
        # When using a spec file, most other arguments are ignored by PyInstaller
        # as the spec file contains the configuration.
        # Prepare and optionally generate hooks from the current venv so PyInstaller
        # includes missing dynamic imports/binaries. Only generate hooks if user
        # requested via CLI flags (`--collect-all` or `--force-hooks`).
        temp_hooks_dir = None
        env = None
        try:
            if getattr(args, "collect_all", False) or getattr(
                args, "force_hooks", False
            ):
                temp_hooks_dir = script.parent / "build" / "nuclear_hooks"
                collect_mode = getattr(args, "collect_all", False)

                # Get venv site-packages to ensure we harvest the correct environment
                python_exe = get_python_executable()
                site_packages = get_venv_site_packages(python_exe)

                generate_nuclear_hooks(
                    temp_hooks_dir,
                    collect_all_mode=collect_mode,
                    search_path=site_packages,
                )
        except Exception as e:
            log(f"Warning: failed to generate nuclear hooks: {e}", style="warning")

        cmd = [get_python_executable(), "-m", "PyInstaller"]
        cmd.append(str(script))
        cmd.append("--noconfirm")

        log(f"Running: {' '.join(cmd)}", style="dim")

        if env is not None:
            ret_code = run_command_with_output(cmd, env=env, style="dim")
        else:
            ret_code = run_command_with_output(cmd, style="dim")

        # Cleanup
        if ret_code == 0:
            out_name = args.name or script.stem
            cleanup_dist(Path("dist") / out_name)

        # If installer was requested, we still try to build it
        if ret_code == 0 and args.installer:
            progress.update(task, description="Building Installer...", completed=80)
            out_name = args.name or script.stem
            ret_code = build_installer(out_name, script.parent, args.icon)

        progress.update(task, description="Done!", completed=100)
        progress.stop()
        if ret_code == 0:
            console.print(Rule("[bold green]Success"))
            log(f"App packaged successfully: dist/{out_name}", style="bold green")
        return ret_code

    out_name = args.name
    if not out_name:
        # Try to get name from settings.json
        try:
            settings_path = script.parent / "settings.json"
            if settings_path.exists():
                settings = json.loads(settings_path.read_text())
                title = settings.get("title")
                if title:
                    # Sanitize title to be a valid filename
                    # Replace non-alphanumeric (except - and _) with _
                    out_name = "".join(
                        c if c.isalnum() or c in ("-", "_") else "_" for c in title
                    )
                    # Remove duplicate underscores and strip
                    while "__" in out_name:
                        out_name = out_name.replace("__", "_")
                    out_name = out_name.strip("_")
        except Exception:
            pass

    if not out_name:
        out_name = script.stem

    # Ensure pytron is found by PyInstaller
    import pytron

    # Dynamically find where pytron is installed on the user's system
    if pytron.__file__ is None:
        log("Error: Cannot determine pytron installation location.", style="error")
        log(
            "This may happen if pytron is installed as a namespace package.",
            style="error",
        )
        log(
            "Try reinstalling pytron: pip install --force-reinstall pytron",
            style="error",
        )
        progress.stop()
        return 1
    package_dir = Path(pytron.__file__).resolve().parent.parent

    # Icon handling
    app_icon = args.icon

    # Re-load settings safely just in case scope is an issue or to be clean
    settings = {}
    try:
        settings_path = script.parent / "settings.json"
        if settings_path.exists():
            settings = json.loads(settings_path.read_text())
    except Exception:
        pass

    if not app_icon:
        config_icon = settings.get("icon")
        if config_icon:
            possible_icon = script.parent / config_icon
            if possible_icon.exists():
                # Check extension
                if possible_icon.suffix.lower() == ".png":
                    # Try to convert to .ico
                    try:
                        from PIL import Image

                        log(
                            f"Converting {possible_icon.name} to .ico for packaging...",
                            style="dim",
                        )
                        img = Image.open(possible_icon)
                        ico_path = possible_icon.with_suffix(".ico")
                        img.save(
                            ico_path,
                            format="ICO",
                            sizes=[
                                (256, 256),
                                (128, 128),
                                (64, 64),
                                (48, 48),
                                (32, 32),
                                (16, 16),
                            ],
                        )
                        app_icon = str(ico_path)
                    except ImportError:
                        log(
                            "Warning: Icon is .png but Pillow is not installed. Cannot convert to .ico.",
                            style="warning",
                        )
                        log(
                            "Install Pillow (pip install Pillow) or provide an .ico file.",
                            style="warning",
                        )
                    except Exception as e:
                        log(
                            f"Warning: Failed to convert .png to .ico: {e}",
                            style="warning",
                        )
                elif possible_icon.suffix.lower() == ".ico":
                    app_icon = str(possible_icon)
                else:
                    log(
                        f"Warning: Icon file must be .ico (or .png with Pillow installed). Ignoring {possible_icon.name}",
                        style="warning",
                    )

    # Fallback to Pytron icon
    pytron_v_icon = Path(pytron.__file__).resolve().parent / "installer" / "pytron.ico"
    if not app_icon and pytron_v_icon.exists():
        app_icon = str(pytron_v_icon)

    # Manifest support: prefer passing a manifest on the PyInstaller CLI
    manifest_path = None
    possible_manifest = (
        Path(package_dir) / "pytron" / "manifests" / "windows-utf8.manifest"
    )
    if possible_manifest.exists():
        manifest_path = possible_manifest.resolve()
        log(f"Found Windows UTF-8 manifest: {manifest_path}", style="dim")

    # --- Plugin Build Hooks ---
    package_context = {
        "add_data": args.add_data or [],
        "hidden_imports": [],
        "binaries": [],
        "extra_args": [],
        "script": script,
        "out_name": out_name,
        "settings": settings,
        "package_dir": package_dir,
        "app_icon": app_icon,
    }

    # Discover and run Plugin on_package hooks
    from ..plugin import discover_plugins

    plugins_dir = script.parent / "plugins"
    if plugins_dir.exists():
        log("Evaluating plugins for packaging hooks...", style="dim")
        plugin_objs = discover_plugins(str(plugins_dir))

        # Robust mock app for hook context
        class PackageAppMock:
            class MockState:
                def __getattr__(self, name):
                    return None

                def __setattr__(self, name, value):
                    pass

            def __init__(self, settings_data, folder):
                self.config = settings_data
                self.app_root = folder
                self.storage_path = str(folder / "build" / "storage")
                self.logger = log
                self.state = self.MockState()

            def expose(self, *args, **kwargs):
                pass

            def broadcast(self, *args, **kwargs):
                pass

            def publish(self, *args, **kwargs):
                pass

            def on_exit(self, func):
                return func

        mock_app = PackageAppMock(settings, script.parent)

        for p in plugin_objs:
            try:
                # We perform a minimal load
                p.load(mock_app)
                p.invoke_package_hook(package_context)
            except Exception as e:
                log(
                    f"Warning: Build hook for plugin '{p.name}' skipped: {e}",
                    style="warning",
                )

        # Sync back modified values from plugins (Shenanigans support)
        out_name = package_context["out_name"]
        app_icon = package_context["app_icon"]
        settings = package_context["settings"]
        log(f"Build context updated by plugins (Name: {out_name})", style="dim")

    progress.update(task, description="Gathering Assets...", completed=20)

    # Auto-detect and include assets (settings.json + frontend build)
    add_data = package_context["add_data"]

    # Automatically include the icon file in the build output
    # This ensures tray icons (which load from file) work in packaged builds
    if app_icon and os.path.exists(app_icon):
        add_data.append(f"{app_icon}{os.pathsep}.")
        log(f"Auto-including icon file: {Path(app_icon).name}", style="dim")

    script_dir = script.parent

    # 1. settings.json (Sanitized for Production)
    settings_path = script_dir / "settings.json"
    if settings_path.exists():
        try:
            # Ensure build directory exists
            build_dir = script_dir / "build"
            build_dir.mkdir(parents=True, exist_ok=True)

            # Force debug=False for production
            if settings.get("debug") is True:
                log("Auto-disabling 'debug' mode for production build.", style="dim")
                settings["debug"] = False

            # Write sanitized settings to temp location
            temp_settings_path = build_dir / "settings.json"
            temp_settings_path.write_text(json.dumps(settings, indent=4))

            # Include the sanitized file, placing it at root (.)
            add_data.append(f"{temp_settings_path}{os.pathsep}.")
            log("Auto-including settings.json (optimized)", style="dim")
        except Exception as e:
            # Fallback to original if something fails
            log(f"Warning optimizing settings.json: {e}", style="warning")
            add_data.append(f"{settings_path}{os.pathsep}.")

    # 2. Frontend assets
    frontend_dist = None
    possible_dists = [
        script_dir / "frontend" / "dist",
        script_dir / "frontend" / "build",
    ]
    for d in possible_dists:
        if d.exists() and d.is_dir():
            frontend_dist = d
            break

    if frontend_dist:
        rel_path = frontend_dist.relative_to(script_dir)
        add_data.append(f"{frontend_dist}{os.pathsep}{rel_path}")
        log(f"Auto-including frontend assets from {rel_path}", style="dim")

    use_smart_assets = getattr(args, "smart_assets", False)

    if use_smart_assets:
        try:
            smart_assets = get_smart_assets(script_dir, frontend_dist=frontend_dist)
            if smart_assets:
                add_data.extend(smart_assets)
        except Exception as e:
            log(f"Warning: failed to auto-include project assets: {e}", style="warning")

    # --- Nuitka Compilation Logic ---
    if getattr(args, "nuitka", False):
        return run_nuitka_build(
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
            package_context=package_context,
        )

    # --- Rust Bootloader (Secure) Logic ---
    if getattr(args, "secure", False):
        return run_secure_build(
            args,
            script,
            out_name,
            settings,
            app_icon,
            package_dir,
            add_data,
            progress,
            task,
            package_context=package_context,
        )

    # --- PyInstaller Compilation Logic ---
    return run_pyinstaller_build(
        args,
        script,
        out_name,
        settings,
        app_icon,
        package_dir,
        add_data,
        manifest_path,
        progress,
        task,
        package_context=package_context,
    )
