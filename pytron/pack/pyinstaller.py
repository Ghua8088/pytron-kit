import os
import sys
import subprocess
import platform
from pathlib import Path
from ..console import log, run_command_with_output, console, Rule
from ..commands.helpers import get_python_executable, get_venv_site_packages
from ..commands.harvest import generate_nuclear_hooks
from .installers import build_installer
from .utils import cleanup_dist

def run_pyinstaller_build(args, script, out_name, settings, app_icon, package_dir, add_data, manifest_path, progress, task):
    # --------------------------------------------------
    # Create a .spec file with the UTF-8 bootloader option
    # --------------------------------------------------
    try:
        log("Generating spec file...", style="info")
        progress.update(task, description="Generating Spec...", completed=30)

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
        dll_dest = os.path.join("pytron", "dependancies")

        requested_engine = getattr(args, "engine", None)
        is_native = (
            requested_engine != "webview2" and requested_engine != None
        ) == False  # i.e. default or webview2

        # Default to native if nothing specified
        if not requested_engine:
            requested_engine = "webview2"

        browser_data = []

        makespec_cmd = [
            get_python_executable(),
            "-m",
            "PyInstaller.utils.cliutils.makespec",
            "--name",
            out_name,
            "--onedir",
        ]

        if getattr(args, "console", False):
            makespec_cmd.append("--console")
        else:
            makespec_cmd.append("--noconsole")

        hidden_imports = ["pytron"]

        # PySide6 logic removed.
        # If user really needs hidden imports, they can use spec files.

        # Force OS-specific libs if needed, but PyInstaller usually handles it via hooks

        if requested_engine == "webview2" and not is_native:
            # Legacy fallback for webview2 bundled
            browser_src = os.path.join(package_dir, "pytron", "dependancies", "browser")
            if os.path.exists(browser_src):
                browser_data.append(
                    f"{browser_src}{os.pathsep}{os.path.join('pytron', 'dependancies', 'browser')}"
                )

        # makespec_cmd already initialized

        for imp in hidden_imports:
            makespec_cmd.append(f"--hidden-import={imp}")

        makespec_cmd.append(f"--add-binary={dll_src}{os.pathsep}{dll_dest}")
        makespec_cmd.append(str(script))

        # Add browser engine to data if not native
        for item in browser_data:
            makespec_cmd.extend(["--add-data", item])

        # Windows-specific options
        if sys.platform == "win32":
            makespec_cmd.append(f"--runtime-hook={package_dir}/pytron/utf8_hook.py")
            # Pass manifest to makespec so spec may include it (deprecated shorthand supported by some PyInstaller versions)
            if manifest_path:
                makespec_cmd.append(f"--manifest={manifest_path}")

        # Set engine if provided (persistent in packaged app)
        if requested_engine:
            log(f"Setting default engine in bundle: {requested_engine}", style="dim")
            # Generate a runtime hook to set the engine
            engine_hook_dir = script.parent / "build" / "pytron_hooks"
            engine_hook_dir.mkdir(parents=True, exist_ok=True)
            engine_hook_path = engine_hook_dir / f"engine_hook_{requested_engine}.py"
            engine_hook_path.write_text(
                f"import os\nos.environ.setdefault('PYTRON_ENGINE', '{requested_engine}')\n"
            )
            makespec_cmd.append(f"--runtime-hook={engine_hook_path.resolve()}")

        if app_icon:
            makespec_cmd.extend(["--icon", app_icon])
            log(f"Using icon: {app_icon}", style="dim")

        # Splash Screen Support
        splash_image = settings.get("splash_image")
        if splash_image:
            # Check relative to script dir
            splash_path = script.parent / splash_image
            if splash_path.exists():
                makespec_cmd.append(f"--splash={splash_path.resolve()}")
                log(f"Bundling splash screen: {splash_path}", style="dim")
            else:
                log(
                    f"Warning: configured splash image not found at {splash_path}",
                    style="warning",
                )

        for item in add_data:
            makespec_cmd.extend(["--add-data", item])

        # Force Package logic (apply --collect-all for libraries specified in settings.json)
        force_pkgs = settings.get("force-package", [])
        # Handle string input just in case user put "lib1,lib2" instead of list
        if isinstance(force_pkgs, str):
            force_pkgs = [p.strip() for p in force_pkgs.split(",")]

        for pkg in force_pkgs:
            if pkg:
                if "-" in pkg:
                    log(
                        f"Warning: 'force-package' entry '{pkg}' contains hyphens.",
                        style="error",
                    )
                    log(
                        f"PyInstaller expects the IMPORT name (e.g. 'llama_cpp' not 'llama-cpp-python').",
                        style="error",
                    )
                    log(
                        f"Please update settings.json to avoid build errors.",
                        style="error",
                    )
                    log(f"Ignoring '{pkg}'", style="error")
                    continue

                makespec_cmd.append(f"--collect-all={pkg}")
                log(f"Forcing full collection of package: {pkg}", style="dim")

        log(f"Running makespec: {' '.join(makespec_cmd)}", style="dim")
        # subprocess.run(makespec_cmd, check=True) # Old way
        makespec_ret = run_command_with_output(makespec_cmd, style="dim")
        if makespec_ret != 0:
            log("Error running makespec", style="error")
            progress.stop()
            return 1

        spec_file = Path(f"{out_name}.spec")
        if not spec_file.exists():
            log(
                f"Error: expected spec file {spec_file} not found after makespec.",
                style="error",
            )
            progress.stop()
            return 1
        # Build from the generated spec. Do not attempt to inject or pass CLI-only
        # makespec options here; makespec was already called with the manifest/runtime-hook.

        # Generate nuclear hooks only when user requested them. Defaults to NO hooks.
        temp_hooks_dir = None
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

        build_cmd = [
            get_python_executable(),
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(spec_file),
        ]

        # If hooks were generated, add the hooks dir to PYTHONPATH for this subprocess
        env = None
        if temp_hooks_dir is not None:
            env = os.environ.copy()
            old = env.get("PYTHONPATH", "")
            new = str(temp_hooks_dir.resolve())
            env["PYTHONPATH"] = new + (os.pathsep + old if old else "")

        progress.update(task, description="Compiling...", completed=50)
        log(f"Building from Spec: {' '.join(build_cmd)}", style="dim")

        # progress.stop() # No longer stopping!
        if env is not None:
            # run_command_with_output streams the logs properly above the bar
            ret_code = run_command_with_output(build_cmd, env=env, style="dim")
        else:
            ret_code = run_command_with_output(build_cmd, style="dim")
        # progress.start() # No longer restarting!

        if ret_code != 0:
            progress.stop()
            return ret_code

        # Cleanup
        cleanup_dist(Path("dist") / out_name)

    except subprocess.CalledProcessError as e:
        log(f"Error generating spec or building: {e}", style="error")
        progress.stop()
        return 1

    if args.installer:
        progress.update(task, description="Building Installer...", completed=90)
        ret = build_installer(out_name, script.parent, app_icon)
        if ret != 0:
            progress.stop()
            return ret

    progress.update(task, description="Done!", completed=100)
    progress.stop()
    console.print(Rule("[bold green]Success"))
    log(f"App packaged successfully: dist/{out_name}", style="bold green")
    return 0
