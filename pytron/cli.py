"""Simple CLI for Pytron: run, init, package, and frontend build helpers.

This implementation uses only the standard library so there are no extra
dependencies. It provides convenience commands to scaffold a minimal app,
run a Python entrypoint, run `pyinstaller` to package, and run `npm run build`
for frontend folders.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import json
import time
from pathlib import Path

try:
    from watchgod import watch, DefaultWatcher
except ImportError:
    DefaultWatcher = object  # Fallback for type hinting if needed, though we check in run_dev_mode


TEMPLATE_APP = '''from pytron import App

def main():
    app = App()
    window = app.create_window()
    app.run()

if __name__ == '__main__':
    main()
'''

TEMPLATE_SETTINGS = '''{
    "title": "My Pytron App",
    "width": 800,
    "height": 600,
    "resizable": true,
    "frameless": false,
    "easy_drag": true,
    "url": "frontend/dist/index.html"
}
'''


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve()
    if target.exists():
        print(f"Target '{target}' already exists")
        return 1

    print(f"Creating new Pytron app at: {target}")
    target.mkdir(parents=True)

    # Create app.py
    app_file = target / 'app.py'
    app_file.write_text(TEMPLATE_APP)

    # Create settings.json
    settings_file = target / 'settings.json'
    settings_file.write_text(TEMPLATE_SETTINGS)

    # Initialize Vite React app in frontend folder
    print("Initializing Vite React app...")
    # Using npx to create vite app non-interactively
    # We need to be inside the target directory or specify path
    # npx create-vite frontend --template react
    # On Windows, npx needs shell=True
    try:
        subprocess.run(['npx', '-y', 'create-vite', 'frontend', '--template', 'react'], cwd=str(target), shell=True, check=True)
        
        # Install dependencies including pytron-client
        print("Installing dependencies...")
        subprocess.run(['npm', 'install'], cwd=str(target / 'frontend'), shell=True, check=True)
        # We should probably add pytron-client here if it was published, but for now user has to add it manually or we link it?
        # Let's just leave it as standard vite app for now as per request "vite frontend by default"
        
    except subprocess.CalledProcessError as e:
        print(f"Failed to initialize Vite app: {e}")
        # Fallback to creating directory if failed
        frontend = target / 'frontend'
        if not frontend.exists():
            frontend.mkdir()
            (frontend / 'index.html').write_text('<!doctype html><html><body><h1>Pytron App (Vite Init Failed)</h1></body></html>')

    # Create README
    (target / 'README.md').write_text('# My Pytron App\n\nBuilt with Pytron CLI init template.\n\n## Structure\n- `app.py`: Main Python entrypoint\n- `settings.json`: Application configuration\n- `frontend/`: Vite React Frontend')

    print('Scaffolded app files:')
    print(f' - {app_file}')
    print(f' - {settings_file}')
    print(f' - {target}/frontend')
    print('Run `pytron run` inside the folder to start the app (defaults to app.py).')
    print('Note: You need to build the frontend first with `cd frontend && npm run build` or use `pytron run --dev app.py`')
    return 0


    print('Run `pytron run <path/to/app.py>` to start the app.')
    return 0


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

    # Find frontend folder
    frontend_dir = None
    # Check current directory and subdirectories for package.json
    candidates = [Path('.')] + [x for x in Path('.').iterdir() if x.is_dir()]
    
    for d in candidates:
        pkg = d / 'package.json'
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text())
                # Check if it has a build script
                if 'scripts' in data and 'build' in data['scripts']:
                    frontend_dir = d.resolve()
                    break
            except Exception:
                pass
    
    npm_proc = None
    if frontend_dir:
        print(f"[Pytron] Found frontend in: {frontend_dir}")
        DevWatcher.frontend_dir = frontend_dir
        
        npm = shutil.which('npm')
        if npm:
            # Check for watch script
            pkg_data = json.loads((frontend_dir / 'package.json').read_text())
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
        app_proc = subprocess.Popen([sys.executable, str(script)] + extra_args)

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

    if args.dev:
        return run_dev_mode(path, args.extra_args)

    cmd = [sys.executable, str(path)] + (args.extra_args or [])
    print(f"Running: {' '.join(cmd)}")
    return subprocess.call(cmd)


def cmd_package(args: argparse.Namespace) -> int:
    script_path = args.script
    if not script_path:
        script_path = 'app.py'

    script = Path(script_path)
    if not script.exists():
        print(f"Script not found: {script}")
        return 1

    out_name = args.name or script.stem
    cmd = [sys.executable, '-m', 'PyInstaller', '--onefile', '--name', out_name, str(script)]
    if args.noconsole:
        cmd.append('--noconsole')

    if args.add_data:
        # Expect add-data entries like src;dest (platform-specific). User must ensure correct separator.
        for item in args.add_data:
            cmd.extend(['--add-data', item])

    print(f"Packaging with: {' '.join(cmd)}")
    return subprocess.call(cmd)


def cmd_build_frontend(args: argparse.Namespace) -> int:
    folder = Path(args.folder)
    if not folder.exists():
        print(f"Folder not found: {folder}")
        return 1

    # Prefer npm if available
    npm = shutil.which('npm')
    if not npm:
        print('npm not found in PATH')
        return 1

    print(f"Running npm run build in {folder}")
    return subprocess.call([npm, 'run', 'build'], cwd=str(folder))


def cmd_info(args: argparse.Namespace) -> int:
    try:
        from pytron import __version__  # type: ignore
    except Exception:
        __version__ = None

    print('Pytron CLI')
    if __version__:
        print(f'Version: {__version__}')
    print(f'Python: {sys.version.splitlines()[0]}')
    print(f'Platform: {sys.platform}')
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='pytron', description='Pytron CLI')
    sub = parser.add_subparsers(dest='command')

    p_init = sub.add_parser('init', help='Scaffold a minimal Pytron app')
    p_init.add_argument('target', help='Target directory for scaffold')
    p_init.set_defaults(func=cmd_init)

    p_run = sub.add_parser('run', help='Run a Python entrypoint script')
    p_run.add_argument('script', nargs='?', help='Path to Python script to run (default: app.py)')
    p_run.add_argument('--dev', action='store_true', help='Enable dev mode (hot reload + frontend watch)')
    p_run.add_argument('extra_args', nargs=argparse.REMAINDER, help='Extra args to forward to script', default=[])
    p_run.set_defaults(func=cmd_run)

    p_pkg = sub.add_parser('package', help='Package app using PyInstaller')
    p_pkg.add_argument('script', nargs='?', help='Python entrypoint to package (default: app.py)')
    p_pkg.add_argument('--name', help='Output executable name')
    p_pkg.add_argument('--noconsole', action='store_true', help='Hide console window')
    p_pkg.add_argument('--add-data', nargs='*', help='Additional data to include (format: src;dest)')
    p_pkg.set_defaults(func=cmd_package)

    p_build = sub.add_parser('build-frontend', help='Run npm build in a frontend folder')
    p_build.add_argument('folder', help='Frontend folder (contains package.json)')
    p_build.set_defaults(func=cmd_build_frontend)

    p_info = sub.add_parser('info', help='Show environment info')
    p_info.set_defaults(func=cmd_info)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, 'func'):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print('\nCancelled')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
