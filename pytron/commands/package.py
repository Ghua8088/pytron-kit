import argparse
import sys
import shutil
import subprocess
import json
import os
from pathlib import Path
from .harvest import generate_nuclear_hooks
from .helpers import get_python_executable, get_venv_site_packages


def get_smart_assets(script_dir: Path, frontend_dist: Path | None = None):
    """Recursively collect project assets to include with PyInstaller.

    - Skips known unwanted directories (venv, node_modules, .git, build, dist, etc.)
    - Skips files with Python/source extensions and common dev files
    - Prunes traversal to avoid descending into excluded folders
    - Skips frontend folder since it's handled separately
    Returns a list of strings in the "abs_path{os.pathsep}rel_path" format
    expected by PyInstaller's `--add-data`.
    """
    add_data = []
    EXCLUDE_DIRS = {
        'venv', '.venv', 'env', '.env',
        'node_modules', '.git', '.vscode', '.idea',
        'build', 'dist', '__pycache__', 'site',
        '.pytest_cache', 'installer', 'frontend'
    }
    EXCLUDE_SUFFIXES = {'.py', '.pyc', '.pyo', '.spec', '.md', '.map'}
    EXCLUDE_FILES = {'.gitignore', 'package-lock.json', 'npm-debug.log', '.DS_Store', 'thumbs.db', 'settings.json'}

    root_path = str(script_dir)
    for root, dirs, files in os.walk(root_path):
        # Prune directories we never want to enter
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]

        # If this path is part of frontend, skip (we handle frontend separately)
        if frontend_dist and str(frontend_dist) in root:
            continue

        for filename in files:
            if filename in EXCLUDE_FILES:
                continue
            file_path = os.path.join(root, filename)
            _, ext = os.path.splitext(filename)
            if ext.lower() in EXCLUDE_SUFFIXES:
                continue

            rel_path = os.path.relpath(file_path, root_path)
            add_data.append(f"{file_path}{os.pathsep}{rel_path}")
            print(f"[Pytron] Auto-including asset: {rel_path}")

    return add_data

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

def build_windows_installer(out_name: str, script_dir: Path, app_icon: str | None) -> int:
    print("[Pytron] Building Windows installer (NSIS)...")
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
                try:
                    import pytron
                    if pytron.__file__ is not None:
                        pkg_root = Path(pytron.__file__).resolve().parent
                        pkg_nsi = pkg_root / 'installer' / 'Installation.nsi'
                        if pkg_nsi.exists():
                            nsi_script = pkg_nsi
                except ImportError:
                    pass
                
                if not nsi_script.exists():
                    print("Error: installer.nsi not found. Please create one or place it in the current directory.")
                    return 1

    build_dir_abs = build_dir.resolve()
    
    # Get version from settings if available, else default
    version = "1.0"
    try:
        settings_path = script_dir / 'settings.json'
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
        f"/DOUT_DIR={script_dir.resolve()}",
    ]
    
    
    # Pass icon to NSIS if available
    if app_icon:
        abs_icon = Path(app_icon).resolve()
        cmd_nsis.append(f'/DMUI_ICON={abs_icon}')
        cmd_nsis.append(f'/DMUI_UNICON={abs_icon}')    
    # NSIS expects switches (like /V4) before the script filename; place verbosity
    # flag before the script so it's honored.
    cmd_nsis.append(f'/V4')
    cmd_nsis.append(str(nsi_script))
    print(f"Running NSIS: {' '.join(cmd_nsis)}")
    return subprocess.call(cmd_nsis)

def build_mac_installer(out_name: str, script_dir: Path, app_icon: str | None) -> int:
    print("[Pytron] Building macOS installer (DMG)...")
    
    # Check for dmgbuild
    if not shutil.which('dmgbuild'):
        print("[Pytron] 'dmgbuild' not found. Attempting to install it...")
        try:
            subprocess.check_call([get_python_executable(), '-m', 'pip', 'install', 'dmgbuild'])
            print("[Pytron] 'dmgbuild' installed successfully.")
        except subprocess.CalledProcessError:
            print("[Pytron] Failed to install 'dmgbuild'. Please install it manually: pip install dmgbuild")
            print("[Pytron] Skipping DMG creation. Your .app bundle is in dist/")
            return 0

    app_bundle = Path('dist') / f"{out_name}.app"
    if not app_bundle.exists():
        print(f"[Pytron] Error: .app bundle not found at {app_bundle}")
        return 1

    dmg_name = f"{out_name}.dmg"
    dmg_path = Path('dist') / dmg_name
    
    # Generate settings file for dmgbuild
    settings_file = Path('build') / 'dmg_settings.py'
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(settings_file, 'w') as f:
        f.write(f"files = [r'{str(app_bundle)}']\n")
        f.write("symlinks = {'Applications': '/Applications'}\n")
        if app_icon and Path(app_icon).suffix == '.icns':
             f.write(f"icon = r'{app_icon}'\n")
        f.write(f"badge_icon = r'{app_icon}'\n")
    
    cmd = ['dmgbuild', '-s', str(settings_file), out_name, str(dmg_path)]
    print(f"Running: {' '.join(cmd)}")
    return subprocess.call(cmd)

def build_installer(out_name: str, script_dir: Path, app_icon: str | None) -> int:
    if sys.platform == 'win32':
        return build_windows_installer(out_name, script_dir, app_icon)
    elif sys.platform == 'darwin':
        return build_mac_installer(out_name, script_dir, app_icon)
    else:
        print(f"[Pytron] Installer creation not supported on {sys.platform} yet.")
        return 0



def cleanup_dist(dist_path: Path):
    """
    Removes unnecessary files (node_modules, node.exe, etc) from the build output
    to optimize the package size.
    """
    target_path = dist_path
    # On macOS, if we built a bundle, the output is .app
    if sys.platform == 'darwin':
        app_path = dist_path.parent / f"{dist_path.name}.app"
        if app_path.exists():
            target_path = app_path

    if not target_path.exists():
        return

    # Items to remove (names)
    remove_names = {
        'node_modules', 'node.exe', 'npm.cmd', 'npx.cmd', 
        '.git', '.gitignore', '.vscode', '.idea',
        'package.json', 'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
        '__pycache__', '.env', 'venv', '.venv', 'env'
    }

    print(f"[Pytron] Optimizing build directory: {dist_path}")
    
    # Walk top-down so we can modify dirs in-place to skip traversing removed dirs
    for root, dirs, files in os.walk(dist_path, topdown=True):
        # Remove directories
        # Modify dirs in-place to avoid traversing into removed directories
        dirs_to_remove = [d for d in dirs if d in remove_names]
        for d in dirs_to_remove:
            full_path = Path(root) / d
            try:
                shutil.rmtree(full_path)
                print(f"  - Removed directory: {d}")
                dirs.remove(d)
            except Exception as e:
                print(f"  ! Failed to remove {d}: {e}")

        # Remove files
        for f in files:
            if f in remove_names or f.endswith('.pdb'): # Also remove debug symbols if any
                full_path = Path(root) / f
                try:
                    os.remove(full_path)
                    print(f"  - Removed file: {f}")
                except Exception as e:
                    print(f"  ! Failed to remove {f}: {e}")


def cmd_package(args: argparse.Namespace) -> int:
    script_path = args.script
    if not script_path:
        script_path = 'app.py'

    script = Path(script_path)
    if not script.exists():
        print(f"Script not found: {script}")
        return 1

    # If the user provided a .spec file, use it directly
    if script.suffix == '.spec':
        print(f"[Pytron] Packaging using spec file: {script}")
        # When using a spec file, most other arguments are ignored by PyInstaller
        # as the spec file contains the configuration.
        # Prepare and optionally generate hooks from the current venv so PyInstaller
        # includes missing dynamic imports/binaries. Only generate hooks if user
        # requested via CLI flags (`--collect-all` or `--force-hooks`).
        temp_hooks_dir = None
        try:
            if getattr(args, 'collect_all', False) or getattr(args, 'force_hooks', False):
                temp_hooks_dir = script.parent / 'build' / 'nuclear_hooks'
                collect_mode = getattr(args, 'collect_all', False)
                
                # Get venv site-packages to ensure we harvest the correct environment
                python_exe = get_python_executable()
                site_packages = get_venv_site_packages(python_exe)
                
                generate_nuclear_hooks(temp_hooks_dir, collect_all_mode=collect_mode, search_path=site_packages)
        except Exception as e:
            print(f"[Pytron] Warning: failed to generate nuclear hooks: {e}")

        cmd = [get_python_executable(), '-m', 'PyInstaller']
        cmd.append(str(script))
        cmd.append('--noconfirm')

        print(f"Running: {' '.join(cmd)}")
        ret_code = subprocess.call(cmd)
        env = None
        if temp_hooks_dir is not None:
            env = os.environ.copy()
            old = env.get('PYTHONPATH', '')
            new = str(temp_hooks_dir.resolve())
            env['PYTHONPATH'] = new + (os.pathsep + old if old else '')

        print(f"Running: {' '.join(cmd)}")
        if env is not None:
            ret_code = subprocess.call(cmd, env=env)
        else:
            ret_code = subprocess.call(cmd)
        
        # Cleanup
        if ret_code == 0:
             out_name = args.name or script.stem
             cleanup_dist(Path('dist') / out_name)

        # If installer was requested, we still try to build it
        if ret_code == 0 and args.installer:
            # We need to deduce the name from the spec file or args
            # This is tricky if we don't parse the spec. 
            # Let's try to use args.name if provided, else script stem
            out_name = args.name or script.stem
            return build_installer(out_name, script.parent, args.icon)
            
        return ret_code

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
    # Runtime hooks shipped with the pytron package (e.g. our UTF-8/stdio hook)
    # `package_dir` points to the pytron package root (one level above the 'pytron' package dir)
    path_to_pytron_hooks = str(Path(package_dir) )

    # Manifest support: prefer passing a manifest on the PyInstaller CLI
    manifest_path = None
    possible_manifest = Path(package_dir)/'pytron' / 'manifests' / 'windows-utf8.manifest'
    print(possible_manifest)
    if possible_manifest.exists():
        print("Manif")
        manifest_path = possible_manifest.resolve()
        print(f"[Pytron] Found Windows UTF-8 manifest: {manifest_path}")

    # Auto-detect and include assets (settings.json + frontend build)
    add_data = []
    if args.add_data:
        add_data.extend(args.add_data)

    script_dir = script.parent

    # 1. settings.json
    settings_path = script_dir / 'settings.json'
    if settings_path.exists():
        add_data.append(f"{settings_path}{os.pathsep}.")
        print(f"[Pytron] Auto-including settings.json")

    # 2. Frontend assets
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
        rel_path = frontend_dist.relative_to(script_dir)
        add_data.append(f"{frontend_dist}{os.pathsep}{rel_path}")
        print(f"[Pytron] Auto-including frontend assets from {rel_path}")

    # 3. Auto-include non-Python files and directories at the project root
    #    Only if --smart-assets is provided
    if getattr(args, 'smart_assets', False):
        try:
            smart_assets = get_smart_assets(script_dir, frontend_dist=frontend_dist)
            if smart_assets:
                add_data.extend(smart_assets)
        except Exception as e:
            print(f"[Pytron] Warning: failed to auto-include project assets: {e}")

    # --------------------------------------------------
    # Create a .spec file with the UTF-8 bootloader option
    # --------------------------------------------------
    try:
        print("[Pytron] Generating spec file...")
        dll_name = "webview.dll" 
        if sys.platform == "darwin": dll_name = "libwebview_x64.dylib" # or arm64
        if sys.platform == "linux": dll_name = "libwebview.so"

        dll_src = os.path.join(package_dir, "pytron", "dependancies", dll_name)
        dll_dest = os.path.join("pytron", "dependancies")
        makespec_cmd = [
            get_python_executable(), '-m', 'PyInstaller.utils.cliutils.makespec',
            '--name', out_name,
            '--onedir',
            '--noconsole',
            '--hidden-import=pytron',
            f'--add-binary={dll_src}{os.pathsep}{dll_dest}',
            str(script)
        ]
        
        # Windows-specific options
        if sys.platform == 'win32':
             makespec_cmd.append(f'--runtime-hook={package_dir}/pytron/utf8_hook.py')
             # Pass manifest to makespec so spec may include it (deprecated shorthand supported by some PyInstaller versions)
             if manifest_path:
                makespec_cmd.append(f'--manifest={manifest_path}')

        if app_icon:
            makespec_cmd.extend(['--icon', app_icon])
            print(f"[Pytron] Using icon: {app_icon}")

        for item in add_data:
            makespec_cmd.extend(['--add-data', item])

        print(f"[Pytron] Running makespec: {' '.join(makespec_cmd)}")
        subprocess.run(makespec_cmd, check=True)

        spec_file = Path(f"{out_name}.spec")
        if not spec_file.exists():
            print(f"[Pytron] Error: expected spec file {spec_file} not found after makespec.")
            return 1
        # Build from the generated spec. Do not attempt to inject or pass CLI-only
        # makespec options here; makespec was already called with the manifest/runtime-hook.

        # Generate nuclear hooks only when user requested them. Defaults to NO hooks.
        temp_hooks_dir = None
        try:
            if getattr(args, 'collect_all', False) or getattr(args, 'force_hooks', False):
                temp_hooks_dir = script.parent / 'build' / 'nuclear_hooks'
                collect_mode = getattr(args, 'collect_all', False)
                
                # Get venv site-packages to ensure we harvest the correct environment
                python_exe = get_python_executable()
                site_packages = get_venv_site_packages(python_exe)
                
                generate_nuclear_hooks(temp_hooks_dir, collect_all_mode=collect_mode, search_path=site_packages)
        except Exception as e:
            print(f"[Pytron] Warning: failed to generate nuclear hooks: {e}")

        build_cmd = [get_python_executable(), '-m', 'PyInstaller', '--noconfirm', '--clean', str(spec_file)]

        # If hooks were generated, add the hooks dir to PYTHONPATH for this subprocess
        env = None
        if temp_hooks_dir is not None:
            env = os.environ.copy()
            old = env.get('PYTHONPATH', '')
            new = str(temp_hooks_dir.resolve())
            env['PYTHONPATH'] = new + (os.pathsep + old if old else '')

        if env is not None:
            print(f"[Pytron] Building from Spec with hooks via PYTHONPATH: {' '.join(build_cmd)}")
            ret_code = subprocess.call(build_cmd, env=env)
        else:
            print(f"[Pytron] Building from Spec: {' '.join(build_cmd)}")
            ret_code = subprocess.call(build_cmd)
        if ret_code != 0:
            return ret_code

        # Cleanup
        cleanup_dist(Path('dist') / out_name)

    except subprocess.CalledProcessError as e:
        print(f"[Pytron] Error generating spec or building: {e}")
        return 1

    if args.installer:
        return build_installer(out_name, script.parent, app_icon)

    return 0
