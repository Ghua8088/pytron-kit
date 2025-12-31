import argparse
import sys
import shutil
import subprocess
import json
import os
import re

from pathlib import Path
from ..console import log, console
from .helpers import (
    locate_frontend_dir,
    run_frontend_build,
    get_python_executable,
    ensure_next_config,
)

try:
    from watchgod import watch, DefaultWatcher
except ImportError:
    DefaultWatcher = (
        object  # Fallback for type hinting if needed, though we check in run_dev_mode
    )


class DevWatcher(DefaultWatcher):
    frontend_dir = None

    def should_watch_dir(self, entry):
        # Robust ignores for common build artifacts and heavy directories
        if entry.name in {
            ".git",
            "__pycache__",
            "node_modules",
            "dist",
            "build",
            ".next",
            ".output",
            "coverage",
        }:
            return False

        if self.frontend_dir:
            try:
                entry_path = Path(entry.path).resolve()
                # If we are inside the frontend directory
                if (
                    self.frontend_dir in entry_path.parents
                    or self.frontend_dir == entry_path
                ):
                    rel = entry_path.relative_to(self.frontend_dir)
                    # Ignore source files in frontend to let HMR handle them
                    # We also ignore public/assets as those presumably don't affect the backend logic
                    if str(rel).startswith(("src", "public", "assets")):
                        return False
            except ValueError:
                pass
        return super().should_watch_dir(entry)


def run_dev_mode(script: Path, extra_args: list[str], engine: str = None) -> int:
    try:
        from watchgod import watch
    except ImportError:
        log(
            "watchgod is required for --dev mode. Install it with: pip install watchgod",
            style="error",
        )
        return 1

    frontend_dir = locate_frontend_dir(Path("."))

    npm_proc = None
    dev_server_url = None

    if frontend_dir:
        log(f"Found frontend in: {frontend_dir}")
        DevWatcher.frontend_dir = frontend_dir

        npm = shutil.which("npm")
        if npm:
            pkg_path = frontend_dir / "package.json"
            pkg_data = json.loads(pkg_path.read_text())
            scripts = pkg_data.get("scripts", {})

            if "dev" in scripts:
                log(
                    "Found 'dev' script. Starting development server...",
                    style="success",
                )
                # We need to capture output to find the port, so PIPE it.
                # But we also want the user to see it.
                # We'll use a thread to read stdout and look for the URL.
                npm_proc = subprocess.Popen(
                    ["npm", "run", "dev"],
                    cwd=str(frontend_dir),
                    shell=(sys.platform == "win32"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )

                # Scan for URL in a background thread
                import threading
                import re

                url_found_event = threading.Event()

                def scan_output():
                    nonlocal dev_server_url
                    # Regex for Local: http://localhost:PORT
                    url_regex = re.compile(r"http://localhost:\d+")
                    # Regex to strip ANSI codes (colors)
                    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

                    while npm_proc and npm_proc.poll() is None:
                        try:
                            line = npm_proc.stdout.readline()
                            if not line:
                                break
                            console.print(
                                f"[dim][npm][/dim] {line.strip()}", style="dim"
                            )  # Echo to console

                            if not dev_server_url:
                                # Strip ANSI codes to ensure clean matching
                                clean_line = ansi_escape.sub("", line)
                                match = url_regex.search(clean_line)
                                if match:
                                    dev_server_url = match.group(0)
                                    log(
                                        f"Detected Dev Server URL: {dev_server_url}",
                                        style="success",
                                    )
                                    url_found_event.set()
                        except Exception as e:
                            log(f"Error reading npm output: {e}", style="error")
                            break

                t = threading.Thread(target=scan_output, daemon=True)
                t.start()

                # Wait for a bit to find the URL
                print("[Pytron] Waiting for dev server to start...")
                url_found_event.wait(timeout=10)

                if not dev_server_url:
                    log(
                        "Warning: Could not detect dev server URL. Python app might load old build.",
                        style="warning",
                    )

            else:
                # Fallback to old behavior (build --watch)
                # Check for watch script
                try:
                    if "next" in pkg_data.get(
                        "dependencies", {}
                    ) or "next" in pkg_data.get("devDependencies", {}):
                        ensure_next_config(frontend_dir)
                except Exception:
                    pass
                args = ["run", "build"]

                if "watch" in scripts:
                    log("Found 'watch' script, using it.", style="success")
                    args = ["run", "watch"]
                else:
                    # We'll try to append --watch to build if it's vite
                    cmd_str = scripts.get("build", "")
                    if "vite" in cmd_str and "--watch" not in cmd_str:
                        log("Adding --watch to build command.")
                        args = ["run", "build", "--", "--watch"]
                    else:
                        log(
                            "No 'watch' script found, running build once.",
                            style="warning",
                        )

                log(f"Starting frontend watcher: npm {' '.join(args)}", style="dim")
                # Use shell=True for Windows compatibility with npm
                npm_proc = subprocess.Popen(
                    ["npm"] + args,
                    cwd=str(frontend_dir),
                    shell=(sys.platform == "win32"),
                )
        else:
            log("npm not found, skipping frontend watch.", style="warning")

    app_proc = None

    def kill_app():
        nonlocal app_proc
        if app_proc:
            if sys.platform == "win32":
                # Force kill process tree on Windows to ensure no lingering windows
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(app_proc.pid)],
                    capture_output=True,
                )
            else:
                app_proc.terminate()
                try:
                    app_proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    app_proc.kill()
            app_proc = None

    def start_app():
        nonlocal app_proc
        kill_app()
        log("Starting app...", style="info")
        # Start as a subprocess we control
        python_exe = get_python_executable()

        env = os.environ.copy()
        if dev_server_url:
            env["PYTRON_DEV_URL"] = dev_server_url
        if engine:
            env["PYTRON_ENGINE"] = engine

        app_proc = subprocess.Popen([python_exe, str(script)] + extra_args, env=env)

    try:
        start_app()
        log(f"Watching for changes in {Path.cwd()}...", style="success")
        for changes in watch(str(Path.cwd()), watcher_cls=DevWatcher):
            log(f"Detected changes: {changes}", style="dim")
            # Filter out non-code changes manually if needed, but DevWatcher handles most
            start_app()

    except KeyboardInterrupt:
        pass
    except Exception as e:
        log(f"Error in dev loop: {e}", style="error")
    finally:
        kill_app()
        if npm_proc:
            log("Stopping frontend watcher...", style="dim")
            if sys.platform == "win32":
                # Need to be careful killing npm on windows, often it spawns node
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(npm_proc.pid)],
                    capture_output=True,
                )
            else:
                npm_proc.terminate()

    return 0


def cmd_run(args: argparse.Namespace) -> int:
    script_path = args.script
    if not script_path:
        # Default to app.py in current directory
        script_path = "app.py"

    path = Path(script_path)
    if not path.exists():
        log(f"Script not found: {path}", style="error")
        return 1

    if not args.dev and not getattr(args, "no_build", False):
        frontend_dir = locate_frontend_dir(path.parent)
        if frontend_dir:
            result = run_frontend_build(frontend_dir)
            if result is False:
                return 1

    if args.dev:
        engine = args.engine
        return run_dev_mode(path, args.extra_args, engine=engine)

    python_exe = get_python_executable()
    env = os.environ.copy()
    if args.engine:
        env["PYTRON_ENGINE"] = args.engine

    cmd = [python_exe, str(path)] + (args.extra_args or [])
    log(f"Running: {' '.join(cmd)}", style="dim")
    return subprocess.call(cmd, env=env)
