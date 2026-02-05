import os
import sys
import json
import shutil
from pathlib import Path
from .pipeline import BuildModule, BuildContext
from ..console import log, console
from .assets import get_smart_assets
from .metadata import MetadataEditor


class AssetModule(BuildModule):
    def prepare(self, context: BuildContext):
        log("Gathering project assets...", style="dim")

        # 1. settings.json
        settings_path = context.script_dir / "settings.json"
        if settings_path.exists():
            # Force debug=False for production
            clean_settings = context.settings.copy()
            if clean_settings.get("debug") is True:
                clean_settings["debug"] = False

            temp_settings_dir = context.build_dir / "pytron_assets"
            temp_settings_dir.mkdir(parents=True, exist_ok=True)
            temp_settings_path = temp_settings_dir / "settings.json"
            temp_settings_path.write_text(json.dumps(clean_settings, indent=4))

            context.add_data.append(f"{temp_settings_path}{os.pathsep}.")

        # 2. Frontend Dist
        possible_dists = [
            context.script_dir / "frontend" / "dist",
            context.script_dir / "frontend" / "build",
        ]
        frontend_dist = None
        for d in possible_dists:
            if d.exists() and d.is_dir():
                frontend_dist = d
                break

        if frontend_dist:
            rel_path = frontend_dist.relative_to(context.script_dir)
            context.add_data.append(f"{frontend_dist}{os.pathsep}{rel_path}")

        # 3. Smart Assets
        # (This is a simplified version of what was in package.py)
        if getattr(context, "smart_assets", False):
            try:
                smart = get_smart_assets(
                    context.script_dir,
                    frontend_dist=frontend_dist,
                    include_patterns=context.settings.get("include_patterns"),
                    exclude_patterns=context.settings.get("exclude_patterns"),
                )
                if smart:
                    context.add_data.extend(smart)
            except Exception as e:
                log(f"Warning: Smart assets failed: {e}", style="warning")

        # 4. Mandatory Resources Folder
        resources_path = context.script_dir / "resources"
        if resources_path.exists() and resources_path.is_dir():
            log(f"Bundling mandatory resources: {resources_path.name}", style="dim")
            context.add_data.append(f"{resources_path}{os.pathsep}resources")


class EngineModule(BuildModule):
    def prepare(self, context: BuildContext):
        if context.engine != "chrome":
            return

        log(f"Configuring {context.engine} engine...", style="dim")

        # Global engine path
        global_engine_path = Path.home() / ".pytron" / "engines" / "chrome"
        if global_engine_path.exists():
            log(f"Auto-bundling Chrome Engine binaries", style="dim")
            # Bundle into pytron/dependencies/chrome
            dest_dep = os.path.join("pytron", "dependencies", "chrome")
            context.add_data.append(f"{global_engine_path}{os.pathsep}{dest_dep}")

            # Bundle shell source
            shell_src = context.package_dir / "pytron" / "engines" / "chrome" / "shell"
            if shell_src.exists():
                shell_dest = os.path.join("pytron", "engines", "chrome", "shell")
                context.add_data.append(f"{shell_src}{os.pathsep}{shell_dest}")
        else:
            log(
                "Error: Chrome engine not found. Run 'pytron engine install chrome'",
                style="error",
            )

    def post_build(self, context: BuildContext):
        if context.engine != "chrome" or sys.platform != "win32":
            return

        # Refactored Chrome Engine renaming/patching
        engine_exe = context.dist_dir / "pytron" / "engines" / "chrome" / "electron.exe"
        target_name = f"{context.out_name}.exe"
        renamed_exe = engine_exe.parent / target_name

        if engine_exe.exists():
            log(f"Patching engine binary: {target_name}", style="dim")
            if renamed_exe.exists():
                os.remove(renamed_exe)
            os.rename(engine_exe, renamed_exe)

            # Apply metadata to the renamed electron binary
            editor = MetadataEditor(package_dir=context.package_dir)
            editor.update(renamed_exe, context.app_icon, context.settings)


class MetadataModule(BuildModule):
    def post_build(self, context: BuildContext):
        log("Applying application metadata...", style="dim")
        main_exe_name = (
            f"{context.out_name}.exe" if sys.platform == "win32" else context.out_name
        )
        main_exe = context.dist_dir / main_exe_name

        if main_exe.exists():
            editor = MetadataEditor(package_dir=context.package_dir)
            editor.update(
                main_exe, context.app_icon, context.settings, dist_dir=context.dist_dir
            )


class InstallerModule(BuildModule):
    def post_build(self, context: BuildContext):
        if not getattr(context, "build_installer", False):
            return

        log("Building NSIS installer...", style="info")
        context.progress.update(
            context.task_id, description="Building Installer...", completed=90
        )

        from .installers import build_installer

        ret_code = build_installer(
            context.out_name, context.script_dir, context.app_icon
        )

        if ret_code != 0:
            log("Installer build failed.", style="error")


class PluginModule(BuildModule):
    def prepare(self, context: BuildContext):
        from ..plugin import discover_plugins

        plugins_dir_name = "plugins"
        plugins_path = context.script_dir / plugins_dir_name

        # Respect custom plugins_dir from settings
        custom_plugins_dir = context.settings.get("plugins_dir")
        if custom_plugins_dir:
            # Resolve relative to script dir
            plugins_path = context.script_dir / custom_plugins_dir
            plugins_dir_name = Path(custom_plugins_dir).name

        if not plugins_path.exists():
            return

        # Automatically bundle the plugins directory
        log(f"Bundling plugins directory: {plugins_path.name}", style="dim")
        # Always bundle into 'plugins' at root of dist so App can find them easily
        context.add_data.append(f"{plugins_path}{os.pathsep}plugins")

        log("Evaluating plugins for packaging hooks...", style="dim")
        plugin_objs = discover_plugins(str(plugins_path))

        # Robust mock app for hook context
        class MockObject:
            def __call__(self, *args, **kwargs):
                return self

            def __iter__(self):
                return iter([])

            def __bool__(self):
                return False

            def __getattr__(self, name):
                return self

            def __getitem__(self, key):
                return self

            def __len__(self):
                return 0

            def to_dict(self):
                return {}

        class PackageAppMock:
            def __init__(self, settings_data, folder):
                self.config = settings_data
                self.app_root = folder
                self.storage_path = str(folder / "build" / "storage")
                self.logger = log
                self.state = MockObject()

            def __getattr__(self, name):
                return MockObject()

            def expose(self, *args, **kwargs):
                pass

            def broadcast(self, *args, **kwargs):
                pass

            def publish(self, *args, **kwargs):
                pass

            def on_exit(self, func):
                return func

        mock_app = PackageAppMock(context.settings, context.script_dir)

        # Build context for plugins to modify
        package_context = {
            "add_data": context.add_data,
            "hidden_imports": context.hidden_imports,
            "binaries": context.binaries,
            "extra_args": context.extra_args,
            "script": context.script,
            "out_name": context.out_name,
            "settings": context.settings,
            "package_dir": context.package_dir,
            "app_icon": context.app_icon,
        }

        for p in plugin_objs:
            try:
                # 1. Load Plugin for Hooks
                p.load(mock_app)
                p.invoke_package_hook(package_context)

                # 2. Auto-Harvest Dependencies (Crucial for Frozen Apps)
                # Since plugin code is loaded dynamically, PyInstaller won't see its imports.
                # We must explicitly tell it to bundle the declared dependencies.
                deps = p.python_dependencies
                if deps:
                    log(
                        f"  + Auto-injecting dependencies for {p.name}: {deps}",
                        style="dim",
                    )
                    package_context["hidden_imports"].extend(deps)

            except Exception as e:
                log(
                    f"Warning: Build analysis for plugin '{p.name}' failed: {e}",
                    style="warning",
                )

        # Sync back modified values
        context.out_name = package_context["out_name"]
        context.app_icon = package_context["app_icon"]
        context.settings = package_context["settings"]
        log(f"Build context updated by plugins", style="dim")


class HookModule(BuildModule):
    def prepare(self, context: BuildContext):
        # Enable if:
        # 1. --collect-all or --force-hooks CLI flag
        # 2. "force_hooks": true in settings.json
        should_run = (
            getattr(context, "collect_all", False)
            or getattr(context, "force_hooks", False)
            or context.settings.get("force_hooks", False)
        )

        if not should_run:
            return

        from .pipeline import log
        from ..commands.harvest import generate_nuclear_hooks
        from ..commands.helpers import get_python_executable, get_venv_site_packages

        log("Generating nuclear build hooks...", style="info")
        temp_hooks_dir = context.build_dir / "nuclear_hooks"
        temp_hooks_dir.mkdir(parents=True, exist_ok=True)

        python_exe = get_python_executable()
        site_packages = get_venv_site_packages(python_exe)

        collect_mode = getattr(context, "collect_all", False)

        # Check for requirements.json to seed the whitelist
        whitelist = None
        req_file = context.script_dir / "requirements.json"

        # If the user explicitly requested force_hooks without a list,
        # or if they have collecting all mode on, we might default to everything (blacklist only).
        # BUT, if requirements.json exists, we should probably use it to be smarter.

        # NOTE: The user asked to use requirements.json specifically to "hard do hidden imports".
        # So we prioritize that if it exists.

        if req_file.exists():
            # Check for Crystal Mode (Dynamic Audit)
            crystal_active = context.settings.get("crystal_mode", False)

            # --- VIRTUAL ENTRY POINT (VEP) GENERATION ---
            # If enabled, we generate a synthetic root based on app.expose
            use_vep = context.settings.get(
                "virtual_entry_point", True
            )  # Default to True for Crystal users

            if crystal_active and use_vep:
                try:
                    from .virtual_root import VirtualRootGenerator

                    vep_gen = VirtualRootGenerator(context.script_dir)
                    vep_gen.scan()

                    # Generate VEP file
                    vep_path = context.script_dir / "_virtual_root.py"
                    vep_gen.generate(vep_path)

                    # CRITICAL: Switch the context script to the VEP!
                    # This means audit AND build will focus on this file.
                    log(
                        f"Switched build target to Virtual Entry Point: {vep_path.name}",
                        style="warning",
                    )
                    context.script = vep_path

                except Exception as e:
                    log(f"VEP Generation Failed: {e}", style="warning")

            if crystal_active:
                try:
                    # UX: Warn the user that we are about to execute their code
                    from rich.prompt import Confirm

                    log(
                        "[bold yellow]Crystal Mode Activated[/bold yellow]",
                        style="none",
                    )
                    console.print(
                        "Pytron needs to [bold red]EXECUTE[/bold red] your application to map the true dependency graph."
                    )
                    console.print(
                        "This ensures 100% accuracy but requires trust in the code you are packaging."
                    )

                    if Confirm.ask("Proceed with execution audit?", default=True):
                        from .crystal import AppAuditor

                        auditor = AppAuditor(context.script)
                        manifest = auditor.run_audit()
                    else:
                        log(
                            "Audit skipped by user. Dependency detection may be incomplete.",
                            style="warning",
                        )
                        manifest = None

                    if manifest:
                        live_modules = manifest.get("modules", [])
                        live_files = manifest.get("files", [])

                        log(
                            f"Crystal Manifest Loaded: {len(live_modules)} modules confirmed alive.",
                            style="info",
                        )

                        # Feed the Truth to PyInstaller
                        # 1. Hidden Imports: Anything audit saw that isn't statically obvious
                        # We just dump everything into hidden imports to be safe?
                        # Or checking "top level" vs "submodule".
                        # Safest is to ensure top-level packages are collected.

                        # Also check for known tough guys in the live list
                        audit_flags = []
                        for mod in live_modules:
                            # If we see skimage.feature._texture, we ensure 'skimage' is collected
                            root = mod.split(".")[0]
                            # Simple heuristic: if we see a module loaded, we can hint PyInstaller
                            # context.hidden_imports.append(mod)
                            # However, adding 5000 hidden imports might be slow.
                            pass

                        # For now, let's keep the Intelligent Introspection (Smart Harvest) running
                        # as it's cleaner for flags, but let's use the Audit to VALIDATE or AUGMENT it.

                        # Specifically for the user's issue:
                        # If 'skimage' was seen in audit, we force collect it.
                        seen_roots = {m.split(".")[0] for m in live_modules}
                        for root in seen_roots:
                            # If it matches a complex package, force collect
                            if root in [
                                "skimage",
                                "pandas",
                                "numpy",
                                "scipy",
                                "torch",
                                "cv2",
                            ]:
                                flag = f"--collect-all={root}"
                                if flag not in context.extra_args:
                                    context.extra_args.append(flag)
                                    log(
                                        f"Crystal Audit: Saw {root} running -> Enforcing {flag}",
                                        style="success",
                                    )

                except Exception as e:
                    log(f"Crystal Audit Failed: {e}", style="warning")

            # Use Intelligent Introspection (AI Oracle)
            try:
                from .graph import GraphBuilder, DependencyOracle

                log("Spawning Dependency Oracle (ML Brain)...", style="info")
                builder = GraphBuilder(context.script_dir)
                graph = builder.scan_project()

                oracle = DependencyOracle(graph)
                oracle.predict()

                smart_flags = []

                # Convert Graph Predictions to PyInstaller Flags
                for edge in graph.edges:
                    if edge.type == "predicted":
                        # Handle different prediction types
                        if edge.target.endswith(".*"):
                            # Wildcard -> Collect Submodules
                            pkg = edge.target[:-2]
                            flag = f"--collect-submodules={pkg}"
                            smart_flags.append(flag)
                        elif edge.target == "<resource_data>":
                            # Generic Data -> Collect All (Safest for now)
                            pkg = edge.source.split(".")[
                                0
                            ]  # Assuming source is module name
                            flag = f"--collect-all={pkg}"
                            smart_flags.append(flag)
                        elif edge.target.startswith("collect_"):
                            # Oracle explicit instruction "collect_all:pkg" etc
                            # But our edge target usually is just the dependency
                            pass
                        else:
                            # Standard hidden import
                            flag = f"--hidden-import={edge.target}"
                            smart_flags.append(flag)

                # Deduplicate
                smart_flags = list(set(smart_flags))

                if smart_flags:
                    log(
                        f"Oracle: Predicted {len(smart_flags)} missing dependencies.",
                        style="success",
                    )
                    for f in smart_flags:
                        log(f"  + {f}", style="dim")
                    context.extra_args.extend(smart_flags)

                # We can still pass the whitelist to the nuclear hook generator if we want absolute redundancy,
                # but --collect-all usually supersedes hook generation for specific packages.
                # However, for non-collect-all packages, the hook generator is still useful for standard hidden imports.

                # Let's rebuild the whitelist for the hook generator (standard safe fallback)
                import json

                if req_file.exists():
                    data = json.loads(req_file.read_text())
                    deps = data.get("dependencies", [])
                    if deps:
                        whitelist = set()
                        for d in deps:
                            clean = d.split("==")[0].split(">")[0].split("<")[0].strip()
                            if "/" not in clean and "\\" not in clean and clean:
                                whitelist.add(clean)
                        whitelist = list(whitelist)
            except Exception as e:
                log(f"Oracle prediction failed: {e}", style="warning")

        generate_nuclear_hooks(
            temp_hooks_dir,
            collect_all_mode=collect_mode,
            search_path=site_packages,
            whitelist=whitelist,
        )

        # PyInstaller expects hook paths. We'll pass it via extra_args or a dedicated field.
        # For now, let's add it to extra_args for PyInstaller.
        context.extra_args.append(f"--additional-hooks-dir={temp_hooks_dir}")
        log(f"Added nuclear hooks dir: {temp_hooks_dir}", style="dim")


class IconModule(BuildModule):
    """
    Handles icon resolution and high-quality conversion.
    Ensures that PNGs are converted to multi-size high-res ICO/ICNS.
    """

    def prepare(self, context: BuildContext):
        icon_path = context.app_icon

        # 1. Fallback to settings if not provided in CLI
        if not icon_path:
            config_icon = context.settings.get("icon")
            if config_icon:
                possible = context.script_dir / config_icon
                if possible.exists():
                    icon_path = str(possible)

        # 2. Hard fallback to Pytron default
        if not icon_path:
            pytron_icon = context.package_dir / "pytron" / "installer" / "pytron.ico"
            if pytron_icon.exists():
                icon_path = str(pytron_icon)

        if not icon_path or not os.path.exists(icon_path):
            log(
                "Warning: No app icon found. Using generic executable icon.",
                style="warning",
            )
            return

        icon_path = Path(icon_path)

        # 3. High-Res Conversion & Platform Specifics
        if icon_path.suffix.lower() == ".png":
            try:
                from PIL import Image

                log(f"Processing high-resolution icon: {icon_path.name}", style="dim")
                img = Image.open(icon_path)

                # --- Windows (ICO) ---
                if (
                    sys.platform == "win32" or True
                ):  # Generate ICO as a general fallback
                    ico_dir = context.build_dir / "icons"
                    ico_dir.mkdir(parents=True, exist_ok=True)
                    ico_path = ico_dir / f"{context.out_name}.ico"

                    sizes = [256, 128, 64, 48, 32, 16]
                    icon_images = []
                    resample = getattr(Image, "Resampling", Image).LANCZOS
                    for s in sizes:
                        if img.width >= s:
                            icon_images.append(img.resize((s, s), resample=resample))

                    if icon_images:
                        # Save with PNG compression for the 256px layer
                        icon_images[0].save(
                            ico_path,
                            format="ICO",
                            append_images=icon_images[1:],
                            bitmap_format=(
                                "png" if icon_images[0].width >= 256 else "bmp"
                            ),
                        )
                        if sys.platform == "win32":
                            context.app_icon = str(ico_path.resolve())

                # --- macOS (ICNS) ---
                if sys.platform == "darwin":
                    icns_path = ico_dir / f"{context.out_name}.icns"
                    try:
                        # Pillow supports ICNS saving
                        img.save(icns_path, format="ICNS")
                        context.app_icon = str(icns_path.resolve())
                        log(f"Generated high-res ICNS for macOS", style="dim")
                    except Exception as e:
                        log(f"Warning: ICNS conversion failed: {e}", style="warning")

                # --- Linux (PNG) ---
                if sys.platform == "linux":
                    # Just ensure we use the PNG directly
                    context.app_icon = str(icon_path.resolve())

            except ImportError:
                log(
                    "Warning: Pillow not installed. Icons may be low resolution.",
                    style="warning",
                )
                log(
                    "Install Pillow for high-res support: pip install Pillow",
                    style="warning",
                )
                context.app_icon = str(icon_path.resolve())
            except Exception as e:
                log(f"Warning: Icon processing failed: {e}", style="warning")
                context.app_icon = str(icon_path.resolve())
        else:
            # Already an ICO, ICNS, etc.
            context.app_icon = str(icon_path.resolve())

        # 4. Auto-include icon in bundle is dangerous because PyInstaller usually handles it.
        # If we explicitly add it as data to '.' (root), and PyInstaller *also* puts it there or
        # tries to use it as the exe icon, it causes the "File already exists" crash.
        # PyInstaller automatically embeds the icon into the EXE metadata via --icon.
        # If the user needs to load it at runtime (e.g., tray icon), they should use a different name
        # or rely on the embedded resource.
        # For now, let's DISABLE this implicit copy or rename it to avoid collision.

        if context.app_icon and os.path.exists(context.app_icon):
            # We rename it in the bundle to avoid collision with the directory or other files
            # context.add_data.append(f"{context.app_icon}{os.pathsep}resources/app_icon.ico")
            pass
