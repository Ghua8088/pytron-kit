import argparse
import sys
import shutil
import subprocess
import json

from pathlib import Path
from .helpers import locate_frontend_dir, run_frontend_build, get_python_executable, ensure_next_config

try:
    from watchgod import watch, DefaultWatcher
except ImportError:
    DefaultWatcher = object  # Fallback for type hinting if needed, though we check in run_dev_mode

class DevWatcher(DefaultWatcher):
    frontend_dir = None
    
    def should_watch_dir(self, entry):
        if 'node_modules' in entry.name:
            return False
        if self.frontend_dir:
             try:
                 entry_path = Path(entry.path).resolve()
                 if self.frontend_dir in entry_path.parents or self.frontend_dir == entry_path:
                     rel = entry_path.relative_to(self.frontend_dir)
                     if str(rel).startswith('src'):
                         return False
             except ValueError:
                 pass
        return super().should_watch_dir(entry)


def run_dev_mode(script: Path, extra_args: list[str]) -> int:
    try:
        from watchgod import watch
    except ImportError:
        print("watchgod is required for --dev mode. Install it with: pip install watchgod")
        return 1

    frontend_dir = locate_frontend_dir(Path('.'))
    
    npm_proc = None
    if frontend_dir:
        print(f"[Pytron] Found frontend in: {frontend_dir}")
        DevWatcher.frontend_dir = frontend_dir
        
        npm = shutil.which('npm')
        if npm:
            # Check for watch script
            pkg_data = json.loads((frontend_dir / 'package.json').read_text())
            # If this looks like a Next.js app, ensure a next.config.js suitable for static export
            try:
                if 'next' in pkg_data.get('dependencies', {}) or 'next' in pkg_data.get('devDependencies', {}):
                    ensure_next_config(frontend_dir)
            except Exception:
                pass
            args = ['run', 'build']
            
            if 'watch' in pkg_data.get('scripts', {}):
                print("[Pytron] Found 'watch' script, using it.")
                args = ['run', 'watch']
            else:
                # We'll try to append --watch to build if it's vite
                cmd_str = pkg_data.get('scripts', {}).get('build', '')
                if 'vite' in cmd_str and '--watch' not in cmd_str:
                     print("[Pytron] Adding --watch to build command.")
                     args = ['run', 'build', '--', '--watch']
                else:
                     print("[Pytron] No 'watch' script found, running build once.")
                
            print(f"[Pytron] Starting frontend watcher: npm {' '.join(args)}")
            # Use shell=True for Windows compatibility with npm
            npm_proc = subprocess.Popen(['npm'] + args, cwd=str(frontend_dir), shell=True)
        else:
            print("[Pytron] npm not found, skipping frontend watch.")

    app_proc = None

    def kill_app():
        nonlocal app_proc
        if app_proc:
            if sys.platform == 'win32':
                # Force kill process tree on Windows to ensure no lingering windows
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(app_proc.pid)], capture_output=True)
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
        print("[Pytron] Starting app...")
        # Start as a subprocess we control
        python_exe = get_python_executable()
        app_proc = subprocess.Popen([python_exe, str(script)] + extra_args)

    try:
        start_app()
        print(f"[Pytron] Watching for changes in {Path.cwd()}...")
        for changes in watch(str(Path.cwd()), watcher_cls=DevWatcher):
            print(f"[Pytron] Detected changes: {changes}")
            start_app()
            
    except KeyboardInterrupt:
        pass
    finally:
        kill_app()
        if npm_proc:
            print("[Pytron] Stopping frontend watcher...")
            if sys.platform == 'win32':
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(npm_proc.pid)], capture_output=True)
            else:
                npm_proc.terminate()
    
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    script_path = args.script
    if not script_path:
        # Default to app.py in current directory
        script_path = 'app.py'
        
    path = Path(script_path)
    if not path.exists():
        print(f"Script not found: {path}")
        return 1

    if not args.dev and not getattr(args, 'no_build', False):
        frontend_dir = locate_frontend_dir(path.parent)
        if frontend_dir:
            result = run_frontend_build(frontend_dir)
            if result is False:
                return 1

    if args.dev:
        return run_dev_mode(path, args.extra_args)

    python_exe = get_python_executable()
    cmd = [python_exe, str(path)] + (args.extra_args or [])
    print(f"Running: {' '.join(cmd)}")
    return subprocess.call(cmd)
