import re
import subprocess
import argparse
import json
from pathlib import Path
from ..console import log, get_progress, run_command_with_output
from .helpers import get_venv_python_path

REQUIREMENTS_JSON = Path("requirements.json")


def load_requirements():
    if REQUIREMENTS_JSON.exists():
        try:
            return json.loads(REQUIREMENTS_JSON.read_text())
        except Exception:
            return {"dependencies": []}
    return {"dependencies": []}


def save_requirements(data):
    REQUIREMENTS_JSON.write_text(json.dumps(data, indent=4))


def get_installed_packages(venv_python) -> dict[str, str]:
    """Returns a dict of {package_name: version} for all installed packages."""
    try:
        cmd = [str(venv_python), "-m", "pip", "list", "--format=json"]
        output = subprocess.check_output(
            cmd, text=True, stderr=subprocess.DEVNULL
        ).strip()
        data = json.loads(output)
        return {item["name"].lower(): item["version"] for item in data}
    except Exception:
        return {}


def get_package_name_from_source(path: Path) -> str | None:
    """Attempts to read package name from pyproject.toml."""
    try:
        pyproject = path / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text(encoding="utf-8")
            match = re.search(r'(?m)^name\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1).lower()
    except Exception:
        pass
    return None


def cmd_uninstall(args: argparse.Namespace) -> int:
    """
    Uninstalls dependencies from the project environment and updates requirements.json.
    """
    packages_to_uninstall = args.packages
    if not packages_to_uninstall:
        log("No packages specified to uninstall.", style="warning")
        return 0

    venv_dir = Path("env")
    venv_python = get_venv_python_path(venv_dir)

    # Resolve names for requirements.json removal
    resolved_names = []
    for pkg in packages_to_uninstall:
        name = pkg.lower()
        if Path(pkg).exists():
            source_name = get_package_name_from_source(Path(pkg))
            if source_name:
                name = source_name
            else:
                # Last ditch: check if it's the current pytron-kit folder itself
                name = Path(pkg).name.lower()
        resolved_names.append(name)

    if not venv_python.exists():
        log(
            f"Virtual environment not found at {venv_dir}. Only updating {REQUIREMENTS_JSON}.",
            style="warning",
        )
    else:
        log(f"Uninstalling: {', '.join(packages_to_uninstall)}")

        progress = get_progress()
        progress.start()
        task = progress.add_task("Uninstalling...", total=None)

        # -y for non-interactive uninstall
        # We pass original args to pip because pip handles paths if it knows the package name is installed from it
        # but usually it prefers the name.
        pip_args = []
        for pkg in packages_to_uninstall:
            if Path(pkg).exists():
                # If user passed a path, we try to use the resolved name for pip uninstall
                # because pip uninstall <path> usually doesn't work (it wants the DIST name)
                name = get_package_name_from_source(Path(pkg)) or Path(pkg).name.lower()
                pip_args.append(name)
            else:
                pip_args.append(pkg)

        cmd = [str(venv_python), "-m", "pip", "uninstall", "-y"] + pip_args
        ret = run_command_with_output(cmd, style="dim")

        progress.stop()

        if ret == 0:
            log("Packages uninstalled from environment successfully.", style="success")
        else:
            log("Some packages failed to uninstall or were not found.", style="warning")

    # Update requirements.json
    req_data = load_requirements()
    current_deps = req_data.get("dependencies", [])

    updated_deps = []
    removed_count = 0

    for dep in current_deps:
        base_name = (
            dep.split("==")[0]
            .split(">=")[0]
            .split("<=")[0]
            .split("<")[0]
            .split(">")[0]
            .strip()
            .lower()
        )

        should_remove = False
        for name in resolved_names:
            if name == base_name:
                should_remove = True
                break

        if should_remove:
            removed_count += 1
        else:
            updated_deps.append(dep)

    if removed_count > 0:
        req_data["dependencies"] = updated_deps
        save_requirements(req_data)
        log(f"Removed {removed_count} packages from {REQUIREMENTS_JSON}", style="info")
    else:
        log(f"No changes made to {REQUIREMENTS_JSON}", style="dim")

    return 0

    return 0
