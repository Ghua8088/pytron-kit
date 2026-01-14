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

try:
    from PyInstaller.utils.win32.icon import CopyIcons
except ImportError:
    CopyIcons = None


def run_pyinstaller_build(
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
    package_context=None,
):
    # --------------------------------------------------
    # Create a .spec file with the UTF-8 bootloader option
    # --------------------------------------------------
    try:
        log("Generating spec file...", style="info")
        progress.update(task, description="Generating Spec...", completed=30)

        # Merge context if provided
        hidden_imports = ["pytron"]
        binaries = []
        extra_makespec_args = []

        if package_context:
            hidden_imports.extend(package_context.get("hidden_imports", []))
            binaries.extend(package_context.get("binaries", []))
            extra_makespec_args.extend(package_context.get("extra_args", []))

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
        if getattr(args, "chrome", False):
            requested_engine = "chrome"

        # Default to native if nothing specified
        if not requested_engine:
            requested_engine = "webview2"

        browser_data = []

        # If using Chrome Mojo Engine, we MUST bundle the binaries
        if requested_engine == "chrome":
            global_engine_path = os.path.expanduser("~/.pytron/engines/chrome")
            if os.path.exists(global_engine_path):
                log(
                    f"Auto-bundling Chrome Mojo Engine from: {global_engine_path}",
                    style="info",
                )
                # We package it into dependancies/chrome inside the app
                browser_data.append(
                    f"{global_engine_path}{os.pathsep}{os.path.join('pytron', 'dependancies', 'chrome')}"
                )

                # FIX: Also bundle the Shell Source (shell.js, package.json)
                # The adapter looks for 'shell' adjacent to itself in pytron/engines/chrome
                shell_src = os.path.join(
                    package_dir, "pytron", "engines", "chrome", "shell"
                )
                if os.path.exists(shell_src):
                    shell_dest = os.path.join("pytron", "engines", "chrome", "shell")
                    browser_data.append(f"{shell_src}{os.pathsep}{shell_dest}")
                    log(
                        f"Auto-bundling Chrome Shell Source from: {shell_src}",
                        style="dim",
                    )
                else:
                    log(
                        f"Warning: Chrome Shell source not found at {shell_src}",
                        style="warning",
                    )
            else:
                log(
                    "Warning: Chrome engine binaries not found locally. Bundle might fail to start.",
                    style="error",
                )
                log(
                    "Run 'pytron engine install chrome' before packaging.",
                    style="error",
                )

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

        # PySide6 logic removed.
        # If user really needs hidden imports, they can use spec files.

        # Force OS-specific libs if needed, but PyInstaller usually handles it via hooks

        if requested_engine == "webview2" and not getattr(args, "chrome", False):
            # Note: Checking getattr arg again because native var isn't defined here cleanly
            # Legacy fallback for webview2 bundled
            browser_src = os.path.join(package_dir, "pytron", "dependancies", "browser")
            if os.path.exists(browser_src):
                browser_data.append(
                    f"{browser_src}{os.pathsep}{os.path.join('pytron', 'dependancies', 'browser')}"
                )

        # makespec_cmd already initialized

        splash_image = settings.get("splash_image")
        if splash_image:
            possible_splash = script.parent / splash_image
            if possible_splash.exists():
                makespec_cmd.extend(["--splash", str(possible_splash)])
                if "pyi_splash" not in hidden_imports:
                    hidden_imports.append("pyi_splash")

                # IMPORTANT: PyInstaller splash requires Tcl/Tk DLLs.
                # If they were excluded or not collected, the splash will fail with a DLL error.
                makespec_cmd.append("--collect-all=tkinter")

                log(
                    f"Injected splash screen: {splash_image} (Ensuring Tcl/Tk dependencies)",
                    style="success",
                )
            else:
                log(f"Warning: Splash image not found: {splash_image}", style="warning")

        for imp in hidden_imports:
            makespec_cmd.append(f"--hidden-import={imp}")

        for bin_pair in binaries:
            makespec_cmd.append(f"--add-binary={bin_pair}")

        makespec_cmd.append(f"--add-binary={dll_src}{os.pathsep}{dll_dest}")
        makespec_cmd.append(str(script))

        # Add browser engine to data if not native
        for item in browser_data:
            makespec_cmd.extend(["--add-data", item])

        # Add plugin-requested data if any
        for item in add_data:
            makespec_cmd.extend(["--add-data", item])

        # Add extra args from plugins
        makespec_cmd.extend(extra_makespec_args)

        # Windows-specific options
        if sys.platform == "win32":
            makespec_cmd.append(f"--runtime-hook={package_dir}/pytron/utf8_hook.py")
            # Pass manifest to makespec so spec may include it
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

        # Handle include_patterns (globs)
        include_patterns = settings.get("include_patterns", [])
        if include_patterns:
            log(f"Processing include_patterns: {include_patterns}", style="dim")
            for pattern in include_patterns:
                # Use Path.glob to find matches
                try:
                    # Recursive glob if pattern contains **
                    for matched_path in script.parent.glob(pattern):
                        # Skip if it's the dist/build dir to avoid loops
                        if (
                            "dist" in matched_path.parts
                            or "build" in matched_path.parts
                        ):
                            continue

                        target_rel = matched_path.relative_to(script.parent)

                        if matched_path.is_file():
                            # Valid file
                            dest = target_rel.parent
                            item = f"{matched_path}{os.pathsep}{dest}"
                            makespec_cmd.extend(["--add-data", item])
                        elif matched_path.is_dir():
                            # Valid directory
                            item = f"{matched_path}{os.pathsep}{target_rel}"
                            makespec_cmd.extend(["--add-data", item])
                except Exception as e:
                    log(f"Error processing pattern '{pattern}': {e}", style="warning")

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
        has_splash = bool(settings.get("splash_image"))
        cleanup_dist(Path("dist") / out_name, preserve_tk=has_splash)

    except subprocess.CalledProcessError as e:
        log(f"Error generating spec or building: {e}", style="error")
        progress.stop()
        return 1

    # --------------------------------------------------
    # POST-BUILD: Chrome Engine Icon Patching (Windows Only)
    # --------------------------------------------------
    if sys.platform == "win32" and requested_engine == "chrome":
        dist_root = Path("dist") / out_name
        base_electron = dist_root / "pytron" / "engines" / "chrome" / "electron.exe"

        # RENAME STEP: Create a unique engine binary for process grouping
        target_name = f"{out_name}-Engine.exe"
        renamed_electron = dist_root / "pytron" / "engines" / "chrome" / target_name

        if base_electron.exists():
            log(f"Renaming engine to unique binary: {target_name}", style="dim")
            try:
                # Use move to rename
                # If target exists (re-run), delete it first
                if renamed_electron.exists():
                    os.remove(renamed_electron)
                os.rename(base_electron, renamed_electron)

                # Update variable for patching
                dist_electron = renamed_electron
            except Exception as e:
                log(f"Failed to rename engine binary: {e}", style="warning")
                dist_electron = base_electron  # Fallback
        else:
            # It might have already been renamed in a previous run?
            if renamed_electron.exists():
                dist_electron = renamed_electron
            else:
                dist_electron = base_electron

        if dist_electron.exists() and app_icon:
            log("Attempting to patch Electron icon...", style="dim")

            # Method 1: PyInstaller Internal Utils (Preferred, No Dep)
            patched_icon = False
            if CopyIcons:
                try:
                    # CopyIcons(dst, src)
                    # Note: PyInstaller signature varies. Try standard first.
                    try:
                        CopyIcons(str(dist_electron), str(app_icon))
                    except TypeError:
                        # Newer PyInstallers might need workpath?
                        CopyIcons(str(dist_electron), str(app_icon), ".")

                    patched_icon = True
                    log(
                        f"Successfully patched Electron icon (Native): {dist_electron}",
                        style="success",
                    )
                except Exception as e:
                    log(f"Native icon patch failed: {e}", style="warning")

            # Method 2: Rcedit (For Metadata + Icon Fallback)
            import shutil

            rcedit = shutil.which("rcedit")

            if rcedit:
                try:
                    if not patched_icon:
                        cmd_icon = [rcedit, str(dist_electron), "--set-icon", app_icon]
                        run_command_with_output(cmd_icon, style="dim")

                    # Patch Metadata (if available)
                    if "version" in settings:
                        cmd_ver = [
                            rcedit,
                            str(dist_electron),
                            "--set-file-version",
                            settings["version"],
                            "--set-product-version",
                            settings["version"],
                        ]
                        run_command_with_output(cmd_ver, style="dim")

                    # Patch Names
                    author = settings.get("author", "Pytron App")
                    copyright = settings.get("copyright", "")
                    cmd_meta = [
                        rcedit,
                        str(dist_electron),
                        "--set-version-string",
                        "FileDescription",
                        out_name,
                        "--set-version-string",
                        "ProductName",
                        out_name,
                        "--set-version-string",
                        "CompanyName",
                        author,
                        "--set-version-string",
                        "LegalCopyright",
                        copyright,
                    ]
                    run_command_with_output(cmd_meta, style="dim")
                    log(
                        "Successfully patched Electron metadata (rcedit)",
                        style="success",
                    )

                except Exception as e:
                    log(f"Rcedit patching failed: {e}", style="warning")
            else:
                if not patched_icon and not CopyIcons:
                    log(
                        "Warning: Could not patch Electron icon (Missing PyInstaller utils and rcedit).",
                        style="warning",
                    )

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
