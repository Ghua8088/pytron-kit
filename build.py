import argparse
import os
import runpy
import subprocess
import sys

if __name__ == '__main__' and globals().get('__spec__') and __spec__.name == 'build':
    # Delegate to the real PEP 517 `build` package so `python -m build` keeps working
    paths = sys.path.copy()
    try:
        # Remove the current working directory so the local build.py is not re-imported
        trimmed = [p for p in paths if p and os.path.abspath(p) != os.getcwd()]
        sys.path[:] = trimmed
        runpy.run_module('build', run_name='__main__')
    finally:
        sys.path[:] = paths
    raise SystemExit()
def build_app(script_path, app_name=None, onefile=True, noconsole=True, add_data=None):
    """
    Builds a Pytron application using PyInstaller.
    """
    if not os.path.exists(script_path):
        print(f"Error: Script not found at {script_path}")
        return

    if app_name is None:
        app_name = os.path.splitext(os.path.basename(script_path))[0]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        script_path,
        "--name", app_name,
        "--clean",
        "--noconfirm", # Overwrite output directory
        "--paths", os.getcwd()
    ]

    if onefile:
        cmd.append("--onefile")
    
    if noconsole:
        cmd.append("--noconsole")
        
    if add_data:
        for data in add_data:
            cmd.extend(["--add-data", data])

    # Add any necessary hidden imports here if pywebview or other libs need them
    # cmd.extend(["--hidden-import", "module_name"])

    print(f"Building {app_name} from {script_path}...")
    print(f"Command: {' '.join(cmd)}")

    try:
        subprocess.check_call(cmd)
        print(f"Build successful! Executable should be in the 'dist' folder.")
    except subprocess.CalledProcessError as e:
        print(f"Build failed with error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a Pytron application.")
    parser.add_argument("script", help="Path to the Python script to build.")
    parser.add_argument("--name", help="Name of the output executable.", default=None)
    parser.add_argument("--console", help="Show console window (useful for debugging).", action="store_true")
    parser.add_argument("--dir", help="Build to a directory instead of a single file.", action="store_true")
    parser.add_argument("--add-data", help="Add data files (format: SRC;DEST). Can be used multiple times.", action="append")

    args = parser.parse_args()

    build_app(
        args.script,
        app_name=args.name,
        onefile=not args.dir,
        noconsole=not args.console,
        add_data=args.add_data
    )
