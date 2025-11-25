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


def locate_frontend_dir(start_dir: Path | None = None) -> Path | None:
    base = (start_dir or Path('.')).resolve()
    if not base.exists():
        return None
    candidates = [base]
    candidates.extend([p for p in base.iterdir() if p.is_dir()])
    for candidate in candidates:
        pkg = candidate / 'package.json'
        if not pkg.exists():
            continue
        try:
            data = json.loads(pkg.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(data.get('scripts'), dict) and 'build' in data['scripts']:
            return candidate.resolve()
    return None


def run_frontend_build(frontend_dir: Path) -> bool | None:
    npm = shutil.which('npm')
    if not npm:
        print('[Pytron] npm not found, skipping frontend build.')
        return None
    print(f"[Pytron] Building frontend at: {frontend_dir}")
    try:
        subprocess.run(['npm', 'run', 'build'], cwd=str(frontend_dir), shell=True, check=True)
        return True
    except subprocess.CalledProcessError as exc:
        print(f"[Pytron] Frontend build failed: {exc}")
        return False


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

    frontend_dir = locate_frontend_dir(Path('.'))
    
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

    if not args.dev and not getattr(args, 'no_build', False):
        frontend_dir = locate_frontend_dir(path.parent)
        if frontend_dir:
            result = run_frontend_build(frontend_dir)
            if result is False:
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

    out_name = args.name
    if not out_name:
        # Try to get name from settings.json
        try:
            settings_path = script.parent / 'settings.json'
            if settings_path.exists():
                settings = json.loads(settings_path.read_text())
                title = settings.get('title')
                if title:
                    # Sanitize title to be a valid filename
                    # Replace non-alphanumeric (except - and _) with _
                    out_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in title)
                    # Remove duplicate underscores and strip
                    while '__' in out_name:
                        out_name = out_name.replace('__', '_')
                    out_name = out_name.strip('_')
        except Exception:
            pass

    if not out_name:
        out_name = script.stem

    # Ensure pytron is found by PyInstaller
    import pytron
    # Dynamically find where pytron is installed on the user's system
    if pytron.__file__ is None:
        print("Error: Cannot determine pytron installation location.")
        print("This may happen if pytron is installed as a namespace package.")
        print("Try reinstalling pytron: pip install --force-reinstall pytron")
        return 1
    package_dir = Path(pytron.__file__).resolve().parent.parent
    
    # Icon handling
    # Icon handling
    app_icon = args.icon
    
    # Check settings.json for icon
    if not app_icon:
        # We already loaded settings earlier to get the title
        # But we need to make sure 'settings' variable is available here
        # It was loaded in a try-except block above, let's re-ensure we have it or reuse it
        # The previous block defined 'settings' inside try, so it might not be bound if exception occurred.
        # Let's re-load safely or assume it's empty if not found.
        pass # We will use the 'settings' dict if it exists from the block above
        
    # Re-load settings safely just in case scope is an issue or to be clean
    settings = {}
    try:
        settings_path = script.parent / 'settings.json'
        if settings_path.exists():
            settings = json.loads(settings_path.read_text())
    except Exception:
        pass

    if not app_icon:
        config_icon = settings.get('icon')
        if config_icon:
            possible_icon = script.parent / config_icon
            if possible_icon.exists():
                # Check extension
                if possible_icon.suffix.lower() == '.png':
                    # Try to convert to .ico
                    try:
                        from PIL import Image
                        print(f"[Pytron] Converting {possible_icon.name} to .ico for packaging...")
                        img = Image.open(possible_icon)
                        ico_path = possible_icon.with_suffix('.ico')
                        img.save(ico_path, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
                        app_icon = str(ico_path)
                    except ImportError:
                        print(f"[Pytron] Warning: Icon is .png but Pillow is not installed. Cannot convert to .ico.")
                        print(f"[Pytron] Install Pillow (pip install Pillow) or provide an .ico file.")
                    except Exception as e:
                        print(f"[Pytron] Warning: Failed to convert .png to .ico: {e}")
                elif possible_icon.suffix.lower() == '.ico':
                    app_icon = str(possible_icon)
                else:
                    print(f"[Pytron] Warning: Icon file must be .ico (or .png with Pillow installed). Ignoring {possible_icon.name}")

    # Fallback to Pytron icon
    pytron_icon = package_dir / 'installer' / 'pytron.ico'
    if not app_icon and pytron_icon.exists():
        app_icon = str(pytron_icon)

    cmd = [
        sys.executable, '-m', 'PyInstaller', 
        '--onedir', 
        '--hidden-import=pytron',
        '--paths', str(package_dir),
        '--name', out_name, 
        str(script)
    ]
    
    if app_icon:
        cmd.extend(['--icon', app_icon])
        print(f"[Pytron] Using icon: {app_icon}")

    cmd.append('--noconsole')

    # Auto-detect and include assets
    add_data = []
    if args.add_data:
        add_data.extend(args.add_data)

    script_dir = script.parent
    
    # 1. settings.json
    settings_path = script_dir / 'settings.json'
    if settings_path.exists():
        # Format: source;dest (Windows) or source:dest (Unix)
        # We want settings.json to be at the root of the bundle
        add_data.append(f"{settings_path}{os.pathsep}.")
        print(f"[Pytron] Auto-including settings.json")

    # 2. Frontend assets
    # Check for frontend/dist or frontend/build
    frontend_dist = None
    possible_dists = [
        script_dir / 'frontend' / 'dist',
        script_dir / 'frontend' / 'build'
    ]
    for d in possible_dists:
        if d.exists() and d.is_dir():
            frontend_dist = d
            break
            
    if frontend_dist:
        # We want the *contents* of dist to be in a folder named 'frontend/dist' or similar?
        # Usually settings.json points to "frontend/dist/index.html"
        # So we should preserve the structure "frontend/dist" inside the bundle.
        # PyInstaller add-data "src;dest" puts src INSIDE dest.
        # So "frontend/dist;frontend/dist"
        
        # Let's verify the relative path from script
        rel_path = frontend_dist.relative_to(script_dir)
        add_data.append(f"{frontend_dist}{os.pathsep}{rel_path}")
        print(f"[Pytron] Auto-including frontend assets from {rel_path}")

    for item in add_data:
        cmd.extend(['--add-data', item])

    print(f"Packaging with: {' '.join(cmd)}")
    ret_code = subprocess.call(cmd)
    if ret_code != 0:
        return ret_code

    if args.installer:
        print("[Pytron] Building installer...")
        makensis = find_makensis()
        if not makensis:
            print("[Pytron] NSIS (makensis) not found.")
            # Try to find bundled installer
            try:
                import pytron
                if pytron.__file__:
                    pkg_root = Path(pytron.__file__).resolve().parent
                    nsis_setup = pkg_root / 'nsis-setup.exe'
                    
                    if nsis_setup.exists():
                        print(f"[Pytron] Found bundled NSIS installer at {nsis_setup}")
                        print("[Pytron] Launching NSIS installer... Please complete the installation.")
                        try:
                            # Run the installer and wait
                            subprocess.run([str(nsis_setup)], check=True)
                            print("[Pytron] NSIS installer finished. Checking for makensis again...")
                            makensis = find_makensis()
                        except Exception as e:
                            print(f"[Pytron] Error running NSIS installer: {e}")
            except Exception as e:
                print(f"[Pytron] Error checking for bundled installer: {e}")

        if not makensis:
            print("Error: makensis not found. Please install NSIS and add it to PATH.")
            return 1
            
        # Locate the generated build directory and exe
        dist_dir = Path('dist')
        # In onedir mode, output is dist/AppName
        build_dir = dist_dir / out_name
        exe_file = build_dir / f"{out_name}.exe"
        
        if not build_dir.exists() or not exe_file.exists():
             print(f"Error: Could not find generated build directory or executable in {dist_dir}")
             return 1
        
        # Locate the NSIS script
        nsi_script = Path('installer.nsi')
        if not nsi_script.exists():
             if Path('installer/Installation.nsi').exists():
                 nsi_script = Path('installer/Installation.nsi')
             else:
                 # Check inside the pytron package
                 if pytron.__file__ is not None:
                     pkg_root = Path(pytron.__file__).resolve().parent
                     pkg_nsi = pkg_root / 'installer' / 'Installation.nsi'
                     if pkg_nsi.exists():
                         nsi_script = pkg_nsi
                 
                 if not nsi_script.exists():
                     print("Error: installer.nsi not found. Please create one or place it in the current directory.")
                     return 1

        build_dir_abs = build_dir.resolve()
        
        # Get version from settings if available, else default
        version = "1.0"
        try:
            settings_path = script.parent / 'settings.json'
            if settings_path.exists():
                settings = json.loads(settings_path.read_text())
                version = settings.get('version', "1.0")
        except Exception:
            pass

        cmd_nsis = [
            makensis,
            f"/DNAME={out_name}",
            f"/DVERSION={version}",
            f"/DBUILD_DIR={build_dir_abs}",
            f"/DMAIN_EXE_NAME={out_name}.exe",
            f"/DOUT_DIR={script.parent.resolve()}",
        ]
        
        # Pass icon to NSIS if available
        if app_icon:
            abs_icon = Path(app_icon).resolve()
            cmd_nsis.append(f'/DMUI_ICON={abs_icon}')
            cmd_nsis.append(f'/DMUI_UNICON={abs_icon}')
            
        cmd_nsis.append(str(nsi_script))
        
        print(f"Running NSIS: {' '.join(cmd_nsis)}")
        return subprocess.call(cmd_nsis)

    return 0


def find_makensis() -> str | None:
    path = shutil.which('makensis')
    if path:
        return path
    common_paths = [
        r"C:\Program Files (x86)\NSIS\makensis.exe",
        r"C:\Program Files\NSIS\makensis.exe",
    ]
    for p in common_paths:
        if os.path.exists(p):
            return p
    return None


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
    p_run.add_argument('--no-build', action='store_true', help='Skip automatic frontend build before running')
    p_run.add_argument('extra_args', nargs=argparse.REMAINDER, help='Extra args to forward to script', default=[])
    p_run.set_defaults(func=cmd_run)

    p_pkg = sub.add_parser('package', help='Package app using PyInstaller')
    p_pkg.add_argument('script', nargs='?', help='Python entrypoint to package (default: app.py)')
    p_pkg.add_argument('--name', help='Output executable name')
    p_pkg.add_argument('--icon', help='Path to app icon (.ico)')
    p_pkg.add_argument('--noconsole', action='store_true', help='Hide console window')
    p_pkg.add_argument('--add-data', nargs='*', help='Additional data to include (format: src;dest)')
    p_pkg.add_argument('--installer', action='store_true', help='Build NSIS installer after packaging')
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
