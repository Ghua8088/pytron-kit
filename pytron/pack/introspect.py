import os
import sys
import ast
import shutil
import json
import importlib.metadata
from pathlib import Path
from typing import List, Set, Dict, Any, Optional
from ..console import log


class DependencyIntrospector:
    """
    The 'Site-Package Surveyor' that performs deep analysis of installed packages
    to determine the optimal packaging strategy.
    """

    def __init__(self, script_dir: Path):
        self.script_dir = script_dir
        self.venv_site_packages = self._detect_site_packages()
        self.analyzed = set()

    def _detect_site_packages(self) -> Path:
        # Priority 1: Local venv in project directory
        # Pytron standardized environment name is "env"
        venv_name = "env"
        venv_path = self.script_dir / venv_name

        if venv_path.exists():
            if sys.platform == "win32":
                sp = venv_path / "Lib" / "site-packages"
                if sp.exists():
                    log(f"  [Introspect] Locked to project venv: {sp}", style="dim")
                    return sp
            else:
                # Unix: lib/pythonX.Y/site-packages
                lib = venv_path / "lib"
                if lib.exists():
                    for child in lib.iterdir():
                        if (
                            child.name.startswith("python")
                            and (child / "site-packages").exists()
                        ):
                            sp = child / "site-packages"
                            log(
                                f"  [Introspect] Locked to project venv: {sp}",
                                style="dim",
                            )
                            return sp

        # Priority 2: Current environment (sys.path)
        paths = sys.path
        for p in paths:
            if "site-packages" in p and os.path.exists(p):
                return Path(p)
        return Path(sys.prefix) / "lib" / "site-packages"

    def resolve_package_path(self, package_name: str) -> Optional[Path]:
        """Locates the physical installation directory of a package."""
        # 1. Strict Venv Lookup
        candidates = [
            self.venv_site_packages / package_name,
            self.venv_site_packages / (package_name + ".py"),
            self.venv_site_packages / package_name.replace("-", "_"),
        ]

        for c in candidates:
            if c.exists():
                return c

        # 2. Try importlib metadata lookup (constrained to venv if possible)
        try:
            # We explicitly search only in our determined site-packages to avoid global leakage
            dists = importlib.metadata.distributions(
                path=[str(self.venv_site_packages)]
            )
            for dist in dists:
                if dist.metadata["Name"] == package_name or dist.name == package_name:
                    files = dist.files
                    if files:
                        p = files[0].locate()
                        path = Path(p)
                        # Ensure it's within our venv (safety check)
                        if str(self.venv_site_packages) in str(path):
                            return path.parent
        except Exception:
            # Fallback to default lookup if strict lookup fails (e.g. egg-info weirdness)
            try:
                files = importlib.metadata.files(package_name)
                if files:
                    p = files[0].locate()
                    return Path(p).parent
            except Exception:
                pass

        return None

    def get_recursive_dependencies(self, seeds: List[str]) -> Set[str]:
        """
        Level 1: Recursive DNS
        Builds a full list of dependencies starting from seeds.
        """
        universe = set()
        queue = list(seeds)

        while queue:
            pkg = queue.pop(0)
            clean_pkg = pkg.split("==")[0].split(">")[0].split("<")[0].strip().lower()

            if clean_pkg in universe:
                continue

            universe.add(clean_pkg)

            # Lookup requirements
            try:
                requires = importlib.metadata.requires(clean_pkg)
                if requires:
                    for req in requires:
                        # Extract name from "requests (>=2.0)"
                        req_name = req.split(" ")[0].split(";")[0].strip()
                        if req_name and req_name.lower() not in universe:
                            queue.append(req_name)
            except importlib.metadata.PackageNotFoundError:
                # Might be a stdlib or uninstalled package
                pass

        return universe

    def analyze_package(self, package_name: str) -> str:
        """
        Level 2: Deep Scan
        Returns a strategy: 'STANDARD' or 'COLLECT_ALL'
        """
        path = self.resolve_package_path(package_name)
        if not path or not path.is_dir():
            return "STANDARD"

        # Heuristic 1: Stub Detection (.pyi)
        # REMOVED: Too noisy. Many modern packages (numpy, pillow, torch) ship stubs
        # but don't require them at runtime unless lazy_loader is involved.
        # We now rely on Heuristic 3/3.5 to detect lazy_loader usage specifically.

        # Heuristic 2: Mixed Native Extensions
        # If we see .pyd/.so files mixed deeply, strict collection is safer
        # Count them
        native_count = len(list(path.rglob("*.pyd"))) + len(list(path.rglob("*.so")))
        # Increased threshold to 15 to allow standard libs like numpy/torch (which have hooks) to pass
        if native_count > 15:
            # Arbitrary threshold for "complex native package"
            log(
                f"  [Introspect] {package_name}: High native complexity ({native_count} exts) -> COLLECT_ALL",
                style="dim",
            )
            return "COLLECT_ALL"

        # Heuristic 3: Source Code Triggers (AST/Text)
        # Quick scan of top-level __init__.py
        init_py = path / "__init__.py"
        if init_py.exists():
            try:
                content = init_py.read_text(errors="ignore")

                # Strict check for lazy_loader (The root cause of the user's issue)
                # We apply this globally to any package using lazy_loader, as it universally requires stubs/data
                if "lazy_loader" in content:
                    log(
                        f"  [Introspect] {package_name}: Detects lazy_loader -> COLLECT_ALL",
                        style="dim",
                    )
                    return "COLLECT_ALL"

                # REFINED: Only flag suspicious dynamic imports if not a well-known package
                well_known_safe = {
                    "numpy",
                    "torch",
                    "pandas",
                    "matplotlib",
                    "setuptools",
                    "pkg_resources",
                }
                if package_name.lower() not in well_known_safe:
                    if "importlib.import_module" in content or "__import__" in content:
                        log(
                            f"  [Introspect] {package_name}: Detects dynamic imports -> COLLECT_ALL",
                            style="dim",
                        )
                        return "COLLECT_ALL"
            except Exception:
                pass

        # Heuristic 3.5: Bytecode Analysis (IMPORT_NAME / CALL_FUNCTION check)
        # Scan __init__.pyc if available or compile source to check for import calls
        if init_py.exists():
            try:
                import dis

                with open(init_py, "r", encoding="utf-8", errors="ignore") as f:
                    source_code = f.read()
                    code_obj = compile(source_code, str(init_py), "exec")

                    found_sus = False
                    for instr in dis.get_instructions(code_obj):
                        # Only trigger specifically on lazy_loader for now to be safe
                        if (
                            instr.opname == "LOAD_GLOBAL"
                            and instr.argval == "lazy_loader"
                        ):
                            found_sus = True

                    if found_sus:
                        log(
                            f"  [Introspect] {package_name}: Bytecode reveals lazy_loader usage -> COLLECT_ALL",
                            style="dim",
                        )
                        return "COLLECT_ALL"
            except Exception:
                pass

        # Heuristic 4: C-Transpilation Analysis (The "X-Ray")
        # If still unsure, and we want to be paranoid (nuclear mode), we can check explicitly.
        # This is expensive, so maybe we only do it if explicitly requested or for known complex packages?
        # For now, let's keep it as a reserve tool or if we see certain red flags.

        return "STANDARD"

    def _transpile_and_scan(self, module_path: Path) -> List[str]:
        """
        Uses Cython to transpile a module to C, then regex-scans the C code
        for PyImport calls. This reveals 'true' imports that might be obfuscated.
        """
        try:
            import subprocess

            # Check for Cython
            python_exe = sys.executable
            # Create temp C file
            c_file = module_path.with_suffix(".c")

            cmd = [
                python_exe,
                "-m",
                "cython",
                "-3",
                str(module_path),
                "-o",
                str(c_file),
            ]

            # Run Cython (silent)
            subprocess.run(cmd, capture_output=True, check=True)

            if not c_file.exists():
                return []

            content = c_file.read_text(errors="ignore")

            # Cleanup
            try:
                os.remove(c_file)
            except:
                pass

            # Scan for standard C-API import calls
            # PyImport_ImportModule("name")
            # __Pyx_Import(name_obj, ...)

            found_imports = []

            # Regex for PyImport_ImportModule("string_literal")
            import re

            matches = re.findall(r'PyImport_ImportModule\(\s*"([^"]+)"\s*\)', content)
            found_imports.extend(matches)

            return found_imports

        except Exception as e:
            # log(f"Transpilation failed: {e}", style="dim")
            return []

    def determine_packaging_strategy(self, requirements_file: Path) -> List[str]:
        """
        Main Entry Point.
        Reads requirements.json -> Returns list of --collect-all flags.
        """
        collect_all_targets = []

        if not requirements_file.exists():
            return []

        try:
            data = json.loads(requirements_file.read_text())
            seeds = data.get("dependencies", [])

            # Clean seeds
            clean_seeds = []
            for s in seeds:
                c = s.split("==")[0].split(">")[0].split("<")[0].strip()
                if "/" not in c and "\\" not in c:
                    clean_seeds.append(c)

            log(f"Introspecting {len(clean_seeds)} seed packages...", style="info")

            # Level 1: Expand
            universe = self.get_recursive_dependencies(clean_seeds)
            log(
                f"  Dependency Universe Expanded: {len(universe)} packages", style="dim"
            )

            # Level 2: Scan & Strategy Determination
            lock_data = {
                "source": "pytron-smart-harvest",
                "seeds": clean_seeds,
                "universe": list(universe),
                "packages": {},
            }

            # CRITICAL: We must scan the ENTIRE universe, not just seeds.
            # InsightFace depends on skimage, so skimage is in universe but not seeds.
            # Skimage uses lazy_loader -> needs collect-all.

            for pkg in universe:
                strategy = self.analyze_package(pkg)

                resolved_path = self.resolve_package_path(pkg)

                # Store analysis in lock file
                lock_data["packages"][pkg] = {
                    "strategy": strategy,
                    "path": str(resolved_path or "unknown"),
                }

                if strategy == "COLLECT_ALL":
                    # KEY FIX: We must use the IMPORT NAME (directory name), not the distribution name
                    # e.g. 'scikit-image' (dist) -> 'skimage' (import)
                    # If we pass 'scikit-image' to PyInstaller/collect_all, it fails to find the module.
                    if resolved_path:
                        import_name = resolved_path.name
                        collect_all_targets.append(f"--collect-all={import_name}")
                    else:
                        # Fallback if path lookup failed but we still want to try
                        collect_all_targets.append(f"--collect-all={pkg}")

            # Write Lock File
            lock_file = requirements_file.parent / "requirements.lock.json"
            try:
                lock_file.write_text(json.dumps(lock_data, indent=4))
                log(f"Locked dependency state written to {lock_file.name}", style="dim")
            except Exception as e:
                log(f"Warning: Could not write lock file: {e}", style="warning")

        except Exception as e:
            log(f"Introspection failed: {e}", style="warning")
            return []

        return collect_all_targets
