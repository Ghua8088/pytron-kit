import argparse
import sys
import os
import json


def cmd_info(args: argparse.Namespace) -> int:
    try:
        from pytron import __version__  # type: ignore
    except Exception:
        __version__ = "Unknown"

    print("Pytron CLI Info")
    print("---------------")
    print(f"Installed Pytron Version: {__version__}")
    print(f"Python Version: {sys.version.splitlines()[0]}")
    print(f"Platform: {sys.platform}")

    # Check for project settings
    cwd = os.getcwd()
    settings_path = os.path.join(cwd, "settings.json")

    if os.path.exists(settings_path):
        print("\nProject Details (from settings.json)")
        print("------------------------------------")
        try:
            with open(settings_path, "r") as f:
                settings = json.load(f)

            project_version = settings.get("pytron_version", "Not specified")
            frontend = settings.get("frontend_framework", "Not specified")
            title = settings.get("title", "Not specified")

            print(f"Project Name: {title}")
            print(f"Project Pytron Version: {project_version}")
            print(f"Frontend Framework: {frontend}")

            if project_version != "Not specified" and project_version != __version__:
                print(
                    f"\nWarning: Project version ({project_version}) differs from installed version ({__version__})"
                )

        except Exception as e:
            print(f"Error reading settings.json: {e}")
    else:
        print(
            "\nNo settings.json found in current directory (not a Pytron project root?)"
        )

    return 0
