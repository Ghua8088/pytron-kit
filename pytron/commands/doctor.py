import os
import sys
import shutil
import subprocess
import platform
import argparse
from pathlib import Path
from ..console import console, print_rule


def check_command(cmd, version_args=["--version", "-v", "version"]):
    """Check if a command exists and return its version."""
    path = shutil.which(cmd)
    if not path:
        return None, None

    # Try common version flags
    for arg in version_args:
        try:
            # We use shell=False for better security
            result = subprocess.run(
                [cmd, arg], capture_output=True, text=True, timeout=3, shell=False
            )  # nosec B603
            output = (result.stdout + result.stderr).strip()
            if output:
                # Keep only the first line of version output
                version = output.split("\n")[0].strip()
                return path, version
        except Exception:
            continue

    return path, "Found"


def get_python_info():
    return sys.version.split("\n")[0], platform.architecture()[0]


def cmd_doctor(args: argparse.Namespace) -> int:
    print_rule("Pytron Doctor - System Diagnostic")

    # 1. Core Python Info
    py_ver, py_arch = get_python_info()
    console.print(f"[bold]Python Environment[/bold]")
    console.print(f"  [success]✓[/success] Python: {py_ver} ({py_arch})")
    console.print(
        f"  [success]✓[/success] Platform: {platform.system()} {platform.release()}"
    )

    # Check if in VENV
    is_venv = sys.prefix != sys.base_prefix
    if is_venv:
        console.print(
            f"  [success]✓[/success] Status: Running inside a virtual environment"
        )
    else:
        # Check for env/ in CWD
        if Path("env").exists() or Path(".venv").exists():
            console.print(
                f"  [info]i[/info] Status: Global Python (local environment detected but not active)"
            )
        else:
            console.print(
                f"  [warning]![/warning] Status: Global Python (no local environment detected)"
            )

    console.print("")

    # 2. Web Application Dependencies
    console.print(f"[bold]Web & Frontend Tools[/bold]")
    from .helpers import get_config

    config = get_config()
    configured_provider = config.get("frontend_provider", "npm")

    node_path, node_ver = check_command("node")
    if node_path:
        console.print(f"  [success]✓[/success] Node.js: {node_ver}")
    else:
        console.print(
            f"  [error]✗[/error] Node.js: Not found (Only required for 'npm/yarn/pnpm')"
        )

    providers = ["npm", "yarn", "pnpm", "bun"]
    for p in providers:
        p_path, p_ver = check_command(p)
        status = "[success]✓[/success]" if p_path else "[dim]✗[/dim]"
        configured_tag = (
            " [cyan](Configured)[/cyan]" if p == configured_provider else ""
        )
        if p_path:
            console.print(f"  {status} {p}: {p_ver}{configured_tag}")
        elif p == configured_provider:
            console.print(f"  [error]✗[/error] {p}: Not found{configured_tag}")
        else:
            console.print(f"  {status} {p}: Not found")

    console.print("")

    # 3. Packaging Tools
    console.print(f"[bold]Packaging Tools[/bold]")
    pi_path, pi_ver = check_command("pyinstaller")
    if pi_path:
        console.print(f"  [success]✓[/success] PyInstaller: {pi_ver}")
    else:
        # Check if installed but not in PATH
        try:
            from importlib.metadata import version as get_pkg_version

            console.print(
                f"  [success]✓[/success] PyInstaller: {get_pkg_version('pyinstaller')} (accessible via module)"
            )
        except Exception:
            console.print(
                f"  [error]✗[/error] PyInstaller: Not found (Required for 'pytron package')"
            )

    if platform.system() == "Windows":
        # Check NSIS
        from .package import find_makensis

        makensis = find_makensis()
        if makensis:
            console.print(f"  [success]✓[/success] NSIS: Found ({makensis})")
        else:
            console.print(
                f"  [warning]![/warning] NSIS: Not found (Required for creating installers)"
            )

        # Check SignTool
        signtool = shutil.which("signtool")
        if signtool:
            console.print(f"  [success]✓[/success] SignTool: Found ({signtool})")
        else:
            console.print(
                f"  [dim]i[/dim] SignTool: Not found (Optional: needed for code signing)"
            )

    console.print("")

    # 4. Android Development
    console.print(f"[bold]Android Development[/bold]")
    java_path, java_ver = check_command("java")
    adb_path, adb_ver = check_command("adb")
    android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")

    if java_path:
        console.print(f"  [success]✓[/success] Java/JDK: {java_ver}")
    else:
        console.print(
            f"  [error]✗[/error] Java/JDK: Not found (Required for 'pytron android')"
        )

    if android_home and os.path.exists(android_home):
        console.print(f"  [success]✓[/success] Android SDK: {android_home}")
    else:
        console.print(
            f"  [error]✗[/error] Android SDK: ANDROID_HOME environment variable not set or invalid"
        )

    if adb_path:
        # Clean up adb version (Android Debug Bridge version 1.0.41 -> 1.0.41)
        v_clean = adb_ver.replace("Android Debug Bridge version ", "").strip()
        console.print(f"  [success]✓[/success] ADB: {v_clean}")
    else:
        console.print(
            f"  [warning]![/warning] ADB: Not found (Needed to run on physical devices)"
        )

    console.print("")

    # 5. Project Integrity
    if Path("settings.json").exists():
        console.print(f"[bold]Project Context[/bold]")
        req_json = Path("requirements.json")
        if req_json.exists():
            console.print(f"  [success]✓[/success] requirements.json: Found")
        else:
            console.print(
                f"  [warning]![/warning] requirements.json: Missing (Run 'pytron init' or create it)"
            )
        console.print("")

    # 6. Pytron Bridge Check
    console.print(f"[bold]Pytron Core[/bold]")
    try:
        import pytron

        pkg_root = Path(pytron.__file__).parent
        console.print(f"  [success]✓[/success] Pytron Location: {pkg_root.parent}")

        # Check for native dynamic libraries
        # Check for native dynamic libraries
        from ..pack.utils import get_native_engine_binaries

        needed = get_native_engine_binaries()
        missing = []

        for name in needed:
            dll_path = pkg_root / "dependencies" / name
            if not dll_path.exists():
                missing.append(name)

        if not missing:
            console.print(
                f"  [success]✓[/success] Native Bridge: Found all required binaries ({', '.join(needed)})"
            )
        else:
            console.print(
                f"  [error]✗[/error] Native Bridge: MISSING ({', '.join(missing)}) from {pkg_root / 'dependencies'}"
            )

    except Exception as e:
        console.print(f"  [error]✗[/error] Pytron Core: Failed to inspect ({e})")

    print_rule("Diagnostic Complete", style="bold green")

    console.print(
        "\n[dim]If you have many [error]✗[/error], please refer to the documentation at https://pytron-kit.github.io/docs/[/dim]"
    )
    return 0
