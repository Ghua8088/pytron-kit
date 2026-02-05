import argparse
import subprocess
import venv
import json
import re
from pathlib import Path
from ..console import (
    log,
    get_progress,
    run_command_with_output,
)
import shutil

from .helpers import get_venv_python_path
from .plugin import perform_plugin_install

REQUIREMENTS_JSON = Path("requirements.json")


def load_requirements() -> dict:
    if REQUIREMENTS_JSON.exists():
        try:
            data = json.loads(REQUIREMENTS_JSON.read_text())
            if "plugins" not in data:
                data["plugins"] = []
            return data
        except json.JSONDecodeError:
            log(
                f"Warning: {REQUIREMENTS_JSON} is invalid JSON. Using empty defaults.",
                style="warning",
            )
    return {"dependencies": [], "plugins": []}


def save_requirements(data: dict):
    REQUIREMENTS_JSON.write_text(json.dumps(data, indent=4))


def get_installed_packages(venv_python) -> dict[str, str]:
    """Returns a dict of {package_name: version} for all installed packages."""
    try:
        cmd = [str(venv_python), "-m", "pip", "list", "--format=json"]
        output = subprocess.check_output(cmd, text=True).strip()
        data = json.loads(output)
        return {item["name"].lower(): item["version"] for item in data}
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return {}


def get_package_name_from_source(path: Path) -> str | None:
    """Attempts to read package name from pyproject.toml."""
    try:
        pyproject = path / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text(encoding="utf-8")
            # Rudimentary TOML parsing for [project] name = "..."
            match = re.search(r'(?m)^name\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1).lower()
    except Exception:
        pass
    return None


def cmd_install(args: argparse.Namespace) -> int:
    """
    Creates a virtual environment (if not exists) and installs dependencies.
    If packages are provided, installs them and adds to requirements.json.
    If no packages provided, installs from requirements.json.
    """
    venv_dir = Path("env")

    # 1. Create virtual environment if it doesn't exist
    if not venv_dir.exists():
        log(f"Creating virtual environment in {venv_dir}...", style="info")
        venv.create(venv_dir, with_pip=True)
    else:
        # Only print if we are doing a full install or explicit install to reassure user
        pass

    venv_python = get_venv_python_path(venv_dir)
    if not venv_python.exists():
        log(f"Error: Python executable not found at {venv_python}", style="error")
        return 1

    packages_to_install = args.packages
    req_data = load_requirements()
    current_deps = req_data.get("dependencies", [])
    current_plugins = req_data.get("plugins", [])

    if packages_to_install:
        if getattr(args, "plugin", False):
            # Handle Plugin Installation
            for plugin_id in packages_to_install:
                ret = perform_plugin_install(plugin_id)
                if ret == 0:
                    if plugin_id not in current_plugins:
                        current_plugins.append(plugin_id)
                else:
                    return 1

            req_data["plugins"] = sorted(list(set(current_plugins)))
            save_requirements(req_data)
            log(f"Added plugins to {REQUIREMENTS_JSON}", style="success")
            return 0

        # Warn about versionless packages
        for pkg in packages_to_install:
            # Check if it's a local path
            if Path(pkg).exists():
                pass  # Local path
            elif not any(op in pkg for op in ["==", ">=", "<=", "<", ">", "@"]):
                log(
                    f"Warning: No version specified for '{pkg}'. Installing latest version.",
                    style="warning",
                )

        log(f"Installing: {', '.join(packages_to_install)}")

        # Snapshot before
        before_state = get_installed_packages(venv_python)

        try:
            # Install packages
            progress = get_progress()
            progress.start()
            task = progress.add_task("Installing...", total=None)

            # Use run_command_with_output to stream logs cleanly above the progress bar
            ret = run_command_with_output(
                [str(venv_python), "-m", "pip", "install", "--no-build-isolation"]
                + packages_to_install
            )

            progress.stop()
            if ret != 0:
                log("pip install failed", style="error")
                return 1

            # Snapshot after
            after_state = get_installed_packages(venv_python)

            updated = False

            for pkg_arg in packages_to_install:
                # Resolve package name
                resolved_name = None

                # Case 1: Local Path (e.g., D:\lib or ./lib)
                if Path(pkg_arg).exists():
                    # Strategy A: Try to read name from source (pyproject.toml)
                    resolved_name = get_package_name_from_source(Path(pkg_arg))

                    if not resolved_name:
                        # Strategy B: Heuristic from pip list diff
                        candidates = []
                        for name, ver in after_state.items():
                            if name not in before_state:
                                candidates.append(name)
                            elif before_state.get(name) != ver:
                                candidates.append(name)

                        if len(candidates) == 1:
                            resolved_name = candidates[0]
                        elif len(candidates) > 1:
                            # Fuzzy match guess
                            guess = (
                                Path(pkg_arg)
                                .name.replace("-", "_")
                                .split(".")[0]
                                .lower()
                            )
                            for cand in candidates:
                                if guess in cand or cand in guess:
                                    resolved_name = cand
                                    break

                    # Strategy C: Check folder name against installed packages
                    if not resolved_name:
                        folder_name = Path(pkg_arg).name.lower()
                        if folder_name in after_state:
                            resolved_name = folder_name
                        else:
                            norm_folder = folder_name.replace("-", "_")
                            if norm_folder in after_state:
                                resolved_name = norm_folder

                # Case 2: Package Name (e.g., "requests")
                else:
                    match = re.split(r"[=<>@]", pkg_arg)
                    resolved_name = match[0].strip().lower()

                # Get Version & Update Config
                if resolved_name and resolved_name in after_state:
                    resolved_version = after_state[resolved_name]
                    entry = f"{resolved_name}=={resolved_version}"

                    # Remove old entry if exists (replacement logic)
                    new_deps = []
                    replaced = False
                    for dep in current_deps:
                        dep_name = re.split(r"[=<>@]", dep)[0].strip().lower()
                        if dep_name == resolved_name:
                            new_deps.append(entry)
                            replaced = True
                        else:
                            new_deps.append(dep)

                    if not replaced:
                        new_deps.append(entry)

                    current_deps = new_deps
                    updated = True
                else:
                    log(
                        f"Warning: Could not resolve installed version for '{pkg_arg}'. Skipping requirement update.",
                        style="warning",
                    )

            if updated:
                req_data["dependencies"] = sorted(list(set(current_deps)))
                save_requirements(req_data)
                log(f"Added to {REQUIREMENTS_JSON}", style="success")

        except subprocess.CalledProcessError as e:
            log(f"Error installing packages: {e}", style="error")
            return 1
    else:
        # Install from requirements.json
        current_plugins = req_data.get("plugins", [])

        if not current_deps and not current_plugins:
            log(
                f"No dependencies or plugins found in {REQUIREMENTS_JSON}.",
                style="warning",
            )
            return 0

        if current_deps:
            log(f"Installing dependencies from {REQUIREMENTS_JSON}...")
            try:
                progress = get_progress()
                progress.start()
                task = progress.add_task("Syncing Dependencies...", total=None)

                ret = run_command_with_output(
                    [str(venv_python), "-m", "pip", "install", "--no-build-isolation"]
                    + current_deps
                )

                progress.stop()
                if ret == 0:
                    log("Dependencies installed successfully.", style="success")
                else:
                    log("Failed to install dependencies.", style="error")
                    return 1
            except Exception as e:
                if "progress" in locals():
                    progress.stop()
                log(f"Error installing dependencies: {e}", style="error")
                return 1

        if current_plugins:
            log(f"Installing plugins from {REQUIREMENTS_JSON}...")
            for plugin_id in current_plugins:
                ret = perform_plugin_install(plugin_id)
                if ret != 0:
                    log(f"Failed to install plugin: {plugin_id}", style="error")
                    return 1

        # 3. Frontend Dependencies (NPM/Yarn/Bun)
        frontend_dir = Path("frontend")
        if frontend_dir.exists() and (frontend_dir / "package.json").exists():
            log(f"Detected frontend in {frontend_dir}. Syncing NPM dependencies...")
            provider = req_data.get("provider", "npm")
            provider_bin = shutil.which(provider)

            if provider_bin:
                try:
                    # Run install in the frontend directory
                    subprocess.check_call([provider_bin, "install"], cwd=frontend_dir)
                    log(
                        "Frontend dependencies installed successfully.", style="success"
                    )
                except subprocess.CalledProcessError as e:
                    log(f"Failed to install frontend dependencies: {e}", style="error")
                    return 1
            else:
                log(
                    f"Warning: '{provider}' not found. Please install '{provider}' to sync frontend dependencies.",
                    style="warning",
                )

    return 0
