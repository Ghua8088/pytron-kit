import argparse
import sys
import shutil
import subprocess
import json
import os
import re

from pathlib import Path
from ..console import log, console
from rich.text import Text
from .helpers import (
    locate_frontend_dir,
    run_frontend_build,
    get_python_executable,
    ensure_next_config,
    get_config,
)

try:
    from watchfiles import watch, DefaultFilter
except ImportError:
    DefaultFilter = object


class PytronFilter(DefaultFilter):
    def __init__(self, frontend_dir: Path = None, **kwargs):
        self.frontend_dir = frontend_dir.resolve() if frontend_dir else None
        self.ignore_dirs = {
            ".git",
            "__pycache__",
            "node_modules",
            "dist",
            "build",
            ".next",
            ".output",
            "coverage",
            "env",
            "venv",
        }
        super().__init__(**kwargs)

    def __call__(self, change, path):
        path_obj = Path(path).resolve()

        # 1. Ignore common heavy or build directories
        if any(part in self.ignore_dirs for part in path_obj.parts):
            return False

        # 2. Frontend specific ignores
        if self.frontend_dir:
            try:
                if (
                    self.frontend_dir in path_obj.parents
                    or self.frontend_dir == path_obj
                ):
                    rel = path_obj.relative_to(self.frontend_dir)
                    # Ignore source and assets to let HMR handle it
                    if any(
                        str(rel).startswith(p)
                        for p in ["src", "public", "assets", "node_modules"]
                    ):
                        return False
            except ValueError:
                pass

        # 3. Default filter (ignores binary files, etc.)
        return super().__call__(change, path)


def run_dev_mode(script: Path, extra_args: list[str], engine: str = None) -> int:
    try:
        from watchfiles import watch
    except ImportError:
        log(
            "watchfiles is required for --dev mode. Install it with: pip install watchfiles",
            style="error",
        )
        return 1

    frontend_dir = locate_frontend_dir(Path("."))
    watcher_filter = PytronFilter(frontend_dir=frontend_dir)

    npm_proc = None
    dev_server_url = None

    if frontend_dir:
        config = get_config()
        provider = config.get("frontend_provider", "npm")
        provider_bin = shutil.which(provider)

        if provider_bin:
            pkg_path = frontend_dir / "package.json"
            pkg_data = json.loads(pkg_path.read_text())
            scripts = pkg_data.get("scripts", {})

            if "dev" in scripts:
                log(
                    f"Found 'dev' script. Starting development server using {provider}...",
                    style="success",
                )

                # Setup Environment
                proc_env = os.environ.copy()
                dev_port = config.get("dev_port")
                if dev_port:
                    proc_env["PORT"] = str(dev_port)
                    # Force color for nicer output
                    proc_env["FORCE_COLOR"] = "1"

                # We need to capture output to find the port, so PIPE it.
                # But we also want the user to see it.
                # We'll use a thread to read stdout and look for the URL.
                npm_proc = subprocess.Popen(
                    [provider_bin, "run", "dev"],
                    cwd=str(frontend_dir),
                    shell=(sys.platform == "win32"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=proc_env,
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
                            # Use Text.from_ansi to handle colors correctly
                            prefix = Text(f"[{provider}] ", style="dim")
                            content = Text.from_ansi(line.strip())
                            console.print(prefix + content)

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
                            log(f"Error reading {provider} output: {e}", style="error")
                            break

                t = threading.Thread(target=scan_output, daemon=True)
                t.start()

                # Wait for a bit to find the URL
                print(f"[Pytron] Waiting for {provider} dev server to start...")
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

                log(
                    f"Starting frontend watcher: {provider} {' '.join(args)}",
                    style="dim",
                )
                # Use shell=True for Windows compatibility
                npm_proc = subprocess.Popen(
                    [provider_bin] + args,
                    cwd=str(frontend_dir),
                    shell=(sys.platform == "win32"),
                )
        else:
            log(f"{provider} not found, skipping frontend watch.", style="warning")

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
        for changes in watch(str(Path.cwd()), watch_filter=watcher_filter):
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
                # Force kill the process tree to avoid "Terminate batch job (Y/N)?"
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(npm_proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                try:
                    npm_proc.terminate()
                    npm_proc.wait(timeout=2)
                except Exception:
                    npm_proc.kill()

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
        engine = "chrome" if getattr(args, "chrome", False) else args.engine
        return run_dev_mode(path, args.extra_args, engine=engine)

    python_exe = get_python_executable()
    env = os.environ.copy()
    if getattr(args, "chrome", False):
        env["PYTRON_ENGINE"] = "chrome"
    elif args.engine:
        env["PYTRON_ENGINE"] = args.engine

    cmd = [python_exe, str(path)] + (args.extra_args or [])
    log(f"Running: {' '.join(cmd)}", style="dim")
    return subprocess.call(cmd, env=env)
