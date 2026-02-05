import os
import sys
import shutil
import subprocess
import platform
import re
from pathlib import Path
from .pipeline import BuildModule, BuildContext
from ..console import log
from ..commands.helpers import get_python_executable


class RustEngine(BuildModule):
    """
    The 'God Mode' Build Engine.
    Replaces PyInstaller with a native Rust Bootloader + Cython Compiled Entry Point.
    """

    def __init__(self):
        super().__init__()
        self.compiled_pyd = None

    def build(self, context: BuildContext):
        """
        Main entry point for the Rust Engine build process.
        """
        log("Initialize Rust Engine (God Mode)...", style="cyan")

        # 1. Compile the Entry Point (VEP) to Native Code
        self._compile_entry_point(context)

        # 2. Deploy Rust Bootloader
        self._deploy_bootloader(context)

        # 3. Assemble Dependencies (The Pure Python Libs)
        self._assemble_libs(context)

        # 4. Process Assets (Copy Context Data)
        self._process_assets(context)

        return 0  # Success

    def _process_assets(self, context: BuildContext):
        """
        Copies assets defined in context.add_data (src;dest_dir structure).
        """
        log("Processing assets...", style="dim")
        for item in context.add_data:
            # Format is usually "src_path;dest_dir" (Windows) or "src_path:dest_dir" (Unix)
            # PyInstaller uses os.pathsep
            parts = item.split(os.pathsep)
            if len(parts) != 2:
                continue

            src, dest_rel = parts
            src_path = Path(src)
            dest_path = context.dist_dir / dest_rel

            if not src_path.exists():
                continue

            dest_path.parent.mkdir(parents=True, exist_ok=True)

            if src_path.is_dir():
                # Copy tree
                if dest_path.exists():
                    shutil.rmtree(dest_path)
                shutil.copytree(src_path, dest_path)
            else:
                # Copy file
                shutil.copy2(src_path, dest_path)

    def _compile_entry_point(self, context: BuildContext):
        """
        Compiles the context.script to app.pyd using the shared compiler.
        """
        from .compilers import compile_script

        build_dir = context.build_dir / "rust_build"
        build_dir.mkdir(parents=True, exist_ok=True)

        log(f"Compiling entry point: {context.script.name} -> app.pyd", style="dim")

        output_pyd = compile_script(context.script, build_dir)

        if output_pyd and output_pyd.exists():
            log(f"Native compilation successful: {output_pyd.name}", style="success")
            self.compiled_pyd = output_pyd
        else:
            raise RuntimeError("Native compilation failed.")

    def _deploy_bootloader(self, context: BuildContext):
        """
        Copies the pre-compiled Rust Bootloader to dist.
        """
        log("Deploying Rust Bootloader...", style="info")

        # Bootloader binary name
        ext = ".exe" if sys.platform == "win32" else ""
        loader_name = f"pytron_rust_bootloader{ext}"

        # Source path
        loader_src = (
            context.package_dir
            / "pytron"
            / "pack"
            / "secure_loader"
            / "bin"
            / loader_name
        )

        if not loader_src.exists():
            raise RuntimeError(f"Rust Bootloader not found at {loader_src}")

        # Dest path (Renamed to output name)
        dest_exe = context.dist_dir / f"{context.out_name}{ext}"

        shutil.copy2(loader_src, dest_exe)
        log(f"Bootloader deployed: {dest_exe}", style="success")

        # Also deploy the app.pyd next to it
        if self.compiled_pyd:
            shutil.copy2(self.compiled_pyd, context.dist_dir / self.compiled_pyd.name)

    def _assemble_libs(self, context: BuildContext):
        """
        Copies required python libraries modules to dist folder using Crystal Manifest.
        """
        log("Assembling dependencies from Crystal Manifest...", style="cyan")

        manifest_path = context.script.parent / "requirements.lock.json"

        # Fallback if VEP was used, the manifest might be named after VEP or original?
        # Crystal creates manifest at script.parent / "requirements.lock.json"

        if not manifest_path.exists():
            log(
                "Warning: Requirements Lock not found. Skipping dependency assembly.",
                style="warning",
            )
            return

        import json

        try:
            data = json.loads(manifest_path.read_text())
        except Exception:
            data = {}

        # Support both new "modules" style and old list style if any
        # But Crystal now emits {modules:[], files:[]}
        files = data.get("files", [])

        # Resolve paths for classification
        files = [Path(f).resolve() for f in files]

        # 1. Identify Environment Locations
        from ..commands.helpers import get_python_executable, get_venv_site_packages

        python_exe = get_python_executable()
        site_packages = get_venv_site_packages(python_exe).resolve()

        # Project Root
        project_root = context.script_dir.resolve()

        # Destination for libraries
        lib_dir = context.dist_dir / "libs"
        lib_dir.mkdir(parents=True, exist_ok=True)

        count = 0
        copied_roots = set()

        for f in files:
            if not f.exists() or f.is_dir():
                continue

            # A. Site Packages (Third Party)
            if site_packages in f.parents:
                rel = f.relative_to(site_packages)
                dest = lib_dir / rel

                # Handling __pycache__: Skip
                if "__pycache__" in dest.parts:
                    continue

                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
                count += 1
                copied_roots.add(rel.parts[0])
                continue

            # B. Project Code (User Scripts)
            if project_root in f.parents:
                # Don't copy the VEP script (it's compiled to app.pyd)
                if f == context.script.resolve():
                    continue
                # Don't copy Crystal runner artifacts
                if f.name in [
                    "crystal_runner.py",
                    "crystal_manifest.json",
                    "_virtual_root.py",
                ]:
                    continue

                rel = f.relative_to(project_root)
                dest = lib_dir / rel  # We treat user code as library to keep root clean

                if "__pycache__" in dest.parts:
                    continue

                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
                count += 1
                continue

            # C. Standard Library
            # We ignore files in base_prefix (e.g. C:\Python39\Lib\...) because we will rely on pythonXX.zip

        log(f"Assembled {count} dependency files into dist/libs", style="success")
        log(f"Roots captured: {', '.join(list(copied_roots)[:10])}", style="dim")

        # 4. Deploy Runtime
        self._deploy_python_runtime(context, python_exe)

    def _deploy_python_runtime(self, context: BuildContext, python_exe: str):
        """
        Deploys python DLLs and Standard Library (minimal).
        """
        log("Deploying Python Runtime...", style="dim")

        # Find Python DLLs
        # usually next to python executable or in system
        py_root = Path(python_exe).parent

        # Copy DLLs (python3.dll, python311.dll, etc)
        for f in py_root.glob("python*.dll"):
            shutil.copy2(f, context.dist_dir / f.name)

        # Copy Standard Lib Zip if exists
        # Many embedded distributions have python3x.zip
        found_zip = False
        for f in py_root.glob("python*.zip"):
            shutil.copy2(f, context.dist_dir / f.name)
            found_zip = True

        if not found_zip:
            log(
                "Warning: pythonXX.zip not found. Bundling 'Lib' folder may be required for StdLib.",
                style="warning",
            )
            # In a full venv, we might need to copy Lib excluding site-packages
            # For this "Pure" implementation, strictly we'd unzip or copy.
            # To keep it safe, let's copy the Lib folder to dist/Lib if zip is missing
            try:
                sys_lib = py_root / "Lib"
                if sys_lib.exists():
                    dest_lib = context.dist_dir / "Lib"
                    log(f"Copying Standard Library from {sys_lib}...", style="dim")
                    # Copy everything EXCEPT site-packages and test
                    shutil.copytree(
                        sys_lib,
                        dest_lib,
                        ignore=shutil.ignore_patterns(
                            "site-packages", "test", "__pycache__"
                        ),
                    )
            except Exception as e:
                log(f"Failed to copy StdLib: {e}", style="error")

    # --- Helpers (Migrated from secure.py) ---

    # --- Helpers ---
    # Compilation logic moved to pytron.pack.compilers
