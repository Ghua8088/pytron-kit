import argparse
import sys
import shutil
import subprocess
import json
import os
import platform
from pathlib import Path
from ..console import console, log, get_progress, print_rule, run_command_with_output, Rule
from .harvest import generate_nuclear_hooks
from .helpers import get_python_executable, get_venv_site_packages, locate_frontend_dir, run_frontend_build



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
            log(f"Auto-including asset: {rel_path}", style="dim")

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
    log("Building Windows installer (NSIS)...", style="info")
    makensis = find_makensis()
    if not makensis:
        log("NSIS (makensis) not found.", style="warning")
        # Try to find bundled installer
        try:
            import pytron
            if pytron.__file__:
                pkg_root = Path(pytron.__file__).resolve().parent
                nsis_setup = pkg_root / 'nsis-setup.exe'
                
                if nsis_setup.exists():
                    log(f"Found bundled NSIS installer at {nsis_setup}")
                    log("Launching NSIS installer... Please complete the installation.", style="warning")
                    try:
                        # Run the installer and wait
                        subprocess.run([str(nsis_setup)], check=True)
                        log("NSIS installer finished. Checking for makensis again...")
                        makensis = find_makensis()
                    except Exception as e:
                        log(f"Error running NSIS installer: {e}", style="error")
        except Exception as e:
            log(f"Error checking for bundled installer: {e}", style="error")

    if not makensis:
        log("Error: makensis not found. Please install NSIS and add it to PATH.", style="error")
        return 1
        
    # Locate the generated build directory and exe
    dist_dir = Path('dist')
    # In onedir mode, output is dist/AppName
    build_dir = dist_dir / out_name
    exe_file = build_dir / f"{out_name}.exe"
    
    if not build_dir.exists() or not exe_file.exists():
            log(f"Error: Could not find generated build directory or executable in {dist_dir}", style="error")
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
    
    # Get metadata from settings
    version = "1.0"
    author = "Pytron User"
    description = f"{out_name} Application"
    copyright = f"Copyright © 2025 {author}"
    signing_config = {}

    try:
        settings_path = script_dir / 'settings.json'
        if settings_path.exists():
            settings = json.loads(settings_path.read_text())
            version = settings.get('version', "1.0")
            author = settings.get('author', author)
            description = settings.get('description', description)
            copyright = settings.get('copyright', copyright)
            signing_config = settings.get('signing', {})
    except Exception as e:
        log(f"Warning reading settings: {e}", style="warning")

    cmd_nsis = [
        makensis,
        f"/DNAME={out_name}",
        f"/DVERSION={version}",
        f"/DCOMPANY={author}",
        f"/DDESCRIPTION={description}",
        f"/DCOPYRIGHT={copyright}",
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
    log(f"Running NSIS: {' '.join(cmd_nsis)}", style="dim")
    
    ret = run_command_with_output(cmd_nsis, style="dim")
    if ret != 0:
        return ret
        
    # Installer path (based on NSIS script logic)
    installer_path = script_dir / f"{out_name}_Installer_{version}.exe"
    
    # Signing Logic
    if signing_config and installer_path.exists():
        if 'certificate' in signing_config:
            cert_path = script_dir / signing_config['certificate']
            password = signing_config.get('password')
            
            if cert_path.exists():
                log(f"Signing installer: {installer_path.name}")
                # Try to find signtool
                signtool = shutil.which('signtool')
                
                # Check common paths if not in PATH
                if not signtool:
                    common_sign_paths = [
                        r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\signtool.exe",
                        r"C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe",
                        r"C:\Program Files (x86)\Windows Kits\8.1\bin\x64\signtool.exe"
                    ]
                    for p in common_sign_paths:
                        if os.path.exists(p):
                            signtool = p
                            break
                            
                if signtool:
                    sign_cmd = [signtool, 'sign', '/f', str(cert_path), '/fd', 'SHA256', '/tr', 'http://timestamp.digicert.com', '/td', 'SHA256']
                    if password:
                        sign_cmd.extend(['/p', password])
                    sign_cmd.append(str(installer_path))
                    
                    try:
                        subprocess.run(sign_cmd, check=True)
                        log("Installer signed successfully!", style="success")
                    except Exception as e:
                        log(f"Signing failed: {e}", style="error")
                else:
                    log("Warning: 'signtool' not found. Cannot sign the installer.", style="warning")
            else:
                log(f"Warning: Certificate not found at {cert_path}", style="warning")
    
    return ret

def build_mac_installer(out_name: str, script_dir: Path, app_icon: str | None) -> int:
    log("Building macOS installer (DMG)...")
    
    # Check for dmgbuild
    if not shutil.which('dmgbuild'):
        log("'dmgbuild' not found. Attempting to install it...", style="warning")
        try:
            subprocess.check_call([get_python_executable(), '-m', 'pip', 'install', 'dmgbuild'])
            log("'dmgbuild' installed successfully.", style="success")
        except subprocess.CalledProcessError:
            log("Failed to install 'dmgbuild'. Please install it manually: pip install dmgbuild", style="error")
            log("Skipping DMG creation. Your .app bundle is in dist/", style="warning")
            return 0

    app_bundle = Path('dist') / f"{out_name}.app"
    if not app_bundle.exists():
        log(f"Error: .app bundle not found at {app_bundle}", style="error")
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
    log(f"Running: {' '.join(cmd)}", style="dim")
    return subprocess.call(cmd)

def build_linux_installer(out_name: str, script_dir: Path, app_icon: str | None) -> int:
    log("Building Linux installer (.deb package)...")
    
    # Check for dpkg-deb
    if not shutil.which('dpkg-deb'):
        log("Error: 'dpkg-deb' not found. Cannot build .deb package.", style="error")
        log("Ensure you are on a Debian-based system (Ubuntu, Kali, Pop!_OS, etc.)", style="warning")
        return 1

    # Get metadata
    version = "1.0"
    author = "Pytron User"
    description = f"{out_name} Application"
    try:
        settings_path = script_dir / 'settings.json'
        if settings_path.exists():
            settings = json.loads(settings_path.read_text())
            version = settings.get('version', "1.0")
            author = settings.get('author', author)
            description = settings.get('description', description)
    except Exception:
        pass

    # Clean version for Debian (digits, dots, plus, tilde)
    deb_version = "".join(c for c in version if c.isalnum() or c in '.-+~')
    if not deb_version[0].isdigit(): deb_version = "0." + deb_version

    # Prepare directories
    package_name = out_name.lower().replace(' ', '-').replace('_', '-')
    build_root = Path('build') / 'deb_package'
    if build_root.exists(): shutil.rmtree(build_root)
    
    install_dir = build_root / 'opt' / package_name
    bin_dir = build_root / 'usr' / 'bin'
    desktop_dir = build_root / 'usr' / 'share' / 'applications'
    debian_dir = build_root / 'DEBIAN'
    
    for d in [install_dir, bin_dir, desktop_dir, debian_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. Copy Application Files
    # Source is dist/out_name (onedir mode)
    src_dir = Path('dist') / out_name
    if not src_dir.exists():
         log(f"Error: Source build dir {src_dir} not found.", style="error")
         return 1
         
    log(f"Copying files to {install_dir}...")
    shutil.copytree(src_dir, install_dir, dirs_exist_ok=True)

    # 2. Create Symlink in /usr/bin
    # relative symlink: ../../opt/package_name/out_name
    # But we are creating the structure, so we just create a broken link or a script. 
    # Actually, a wrapper script is safer for environment variables.
    wrapper_script = bin_dir / package_name
    wrapper_script.write_text(f'#!/bin/sh\nexec /opt/{package_name}/{out_name} "$@"\n')
    wrapper_script.chmod(0o755)

    # 3. Create .desktop file
    icon_name = package_name
    if app_icon and Path(app_icon).exists():
        # Install icon to /usr/share/icons/hicolor/256x256/apps/
        icon_path = Path(app_icon)
        icon_dest_dir = build_root / 'usr' / 'share' / 'icons' / 'hicolor' / '256x256' / 'apps'
        icon_dest_dir.mkdir(parents=True, exist_ok=True)
        # Convert if needed? explicit .png is best. Assume user provided decent icon or we just copy.
        ext = icon_path.suffix
        if ext == '.ico':
             # Try simple copy, Linux often handles it, but png preferred.
             pass
        shutil.copy(icon_path, icon_dest_dir / (package_name + ext))
        icon_name = package_name # without extension works usually if matched name
    
    desktop_content = f"""[Desktop Entry]
Name={out_name}
Comment={description}
Exec=/opt/{package_name}/{out_name}
Icon={icon_name}
Terminal=false
Type=Application
Categories=Utility;
"""
    (desktop_dir / f"{package_name}.desktop").write_text(desktop_content)

    # 4. Control File
    control_content = f"""Package: {package_name}
Version: {deb_version}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: {author}
Description: {description}
 Built with Pytron.
"""
    (debian_dir / 'control').write_text(control_content)

    # 5. Build .deb
    deb_filename = f"{package_name}_{deb_version}_amd64.deb"
    output_deb = script_dir / deb_filename
    
    cmd = ['dpkg-deb', '--build', str(build_root), str(output_deb)]
    log(f"Running: {' '.join(cmd)}", style="dim")
    result = subprocess.call(cmd)
    
    if result == 0:
        log(f"Linux .deb package created: {output_deb}", style="success")
    else:
        log("Failed to create .deb package.", style="error")
        
    return result

def build_installer(out_name: str, script_dir: Path, app_icon: str | None) -> int:
    if sys.platform == 'win32':
        return build_windows_installer(out_name, script_dir, app_icon)
    elif sys.platform == 'darwin':
        return build_mac_installer(out_name, script_dir, app_icon)
    elif sys.platform == 'linux':
        return build_linux_installer(out_name, script_dir, app_icon)
    else:
        log(f"Installer creation not supported on {sys.platform} yet.", style="warning")
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

    log(f"Optimizing build directory: {dist_path}")
    
    # Walk top-down so we can modify dirs in-place to skip traversing removed dirs
    for root, dirs, files in os.walk(dist_path, topdown=True):
        # Remove directories
        # Modify dirs in-place to avoid traversing into removed directories
        dirs_to_remove = [d for d in dirs if d in remove_names]
        for d in dirs_to_remove:
            full_path = Path(root) / d
            try:
                shutil.rmtree(full_path)
                console.print(f"  - Removed directory: {d}", style="dim")
                dirs.remove(d)
            except Exception as e:
                console.print(f"  ! Failed to remove {d}: {e}", style="error")

        # Remove files
        for f in files:
            if f in remove_names or f.endswith('.pdb'): # Also remove debug symbols if any
                full_path = Path(root) / f
                try:
                    os.remove(full_path)
                    console.print(f"  - Removed file: {f}", style="dim")
                except Exception as e:
                    console.print(f"  ! Failed to remove {f}: {e}", style="error")


def cmd_package(args: argparse.Namespace) -> int:
    script_path = args.script
    if not script_path:
        script_path = 'app.py'

    script = Path(script_path)
    if not script.exists():
        log(f"Script not found: {script}", style="error")
        return 1

    console.print(Rule("[bold cyan]Pytron Builder"))
    
    requested_engine = 'pyside6' if getattr(args, 'pyside6', False) else getattr(args, 'engine', None)
    dist_dir = 'dist'
    
    progress = get_progress()
    task = progress.add_task("Starting...", total=100)
    progress.start()


    # If the user provided a .spec file, use it directly
    if script.suffix == '.spec':
        log(f"Packaging using spec file: {script}")
        progress.update(task, description="Building from Spec...", completed=10)
        # When using a spec file, most other arguments are ignored by PyInstaller
        # as the spec file contains the configuration.
        # Prepare and optionally generate hooks from the current venv so PyInstaller
        # includes missing dynamic imports/binaries. Only generate hooks if user
        # requested via CLI flags (`--collect-all` or `--force-hooks`).
        temp_hooks_dir = None
        env = None
        try:
            if getattr(args, 'collect_all', False) or getattr(args, 'force_hooks', False):
                temp_hooks_dir = script.parent / 'build' / 'nuclear_hooks'
                collect_mode = getattr(args, 'collect_all', False)
                
                # Get venv site-packages to ensure we harvest the correct environment
                python_exe = get_python_executable()
                site_packages = get_venv_site_packages(python_exe)
                
                generate_nuclear_hooks(temp_hooks_dir, collect_all_mode=collect_mode, search_path=site_packages)
        except Exception as e:
            log(f"Warning: failed to generate nuclear hooks: {e}", style="warning")

        cmd = [get_python_executable(), '-m', 'PyInstaller']
        cmd.append(str(script))
        cmd.append('--noconfirm')

        log(f"Running: {' '.join(cmd)}", style="dim")
        
        if env is not None:
             ret_code = run_command_with_output(cmd, env=env, style="dim")
        else:
             ret_code = run_command_with_output(cmd, style="dim")
        
        # Cleanup
        if ret_code == 0:
             out_name = args.name or script.stem
             cleanup_dist(Path('dist') / out_name)

        # If installer was requested, we still try to build it
        if ret_code == 0 and args.installer:
            progress.update(task, description="Building Installer...", completed=80)
            out_name = args.name or script.stem
            ret_code = build_installer(out_name, script.parent, args.icon)
            
        progress.update(task, description="Done!", completed=100)
        progress.stop()
        if ret_code == 0:
            console.print(Rule("[bold green]Success"))
            log(f"App packaged successfully: dist/{out_name}", style="bold green")
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
        log("Error: Cannot determine pytron installation location.", style="error")
        log("This may happen if pytron is installed as a namespace package.", style="error")
        log("Try reinstalling pytron: pip install --force-reinstall pytron", style="error")
        progress.stop()
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
                        log(f"Converting {possible_icon.name} to .ico for packaging...", style="dim")
                        img = Image.open(possible_icon)
                        ico_path = possible_icon.with_suffix('.ico')
                        img.save(ico_path, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
                        app_icon = str(ico_path)
                    except ImportError:
                        log("Warning: Icon is .png but Pillow is not installed. Cannot convert to .ico.", style="warning")
                        log("Install Pillow (pip install Pillow) or provide an .ico file.", style="warning")
                    except Exception as e:
                        log(f"Warning: Failed to convert .png to .ico: {e}", style="warning")
                elif possible_icon.suffix.lower() == '.ico':
                    app_icon = str(possible_icon)
                else:
                    log(f"Warning: Icon file must be .ico (or .png with Pillow installed). Ignoring {possible_icon.name}", style="warning")

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
    if possible_manifest.exists():
        manifest_path = possible_manifest.resolve()
        log(f"Found Windows UTF-8 manifest: {manifest_path}", style="dim")
    
    progress.update(task, description="Gathering Assets...", completed=20)

    # Auto-detect and include assets (settings.json + frontend build)
    add_data = []
    if args.add_data:
        add_data.extend(args.add_data)

    # Automatically include the icon file in the build output
    # This ensures tray icons (which load from file) work in packaged builds
    if app_icon and os.path.exists(app_icon):
        add_data.append(f"{app_icon}{os.pathsep}.")
        log(f"Auto-including icon file: {Path(app_icon).name}", style="dim")

    script_dir = script.parent

    # 1. settings.json
    settings_path = script_dir / 'settings.json'
    if settings_path.exists():
        add_data.append(f"{settings_path}{os.pathsep}.")
        log("Auto-including settings.json", style="dim")

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
        log(f"Auto-including frontend assets from {rel_path}", style="dim")

    # 3. Auto-include non-Python files and directories at the project root
    #    Only if --smart-assets is provided
    if getattr(args, 'smart_assets', False):
        try:
            smart_assets = get_smart_assets(script_dir, frontend_dist=frontend_dist)
            if smart_assets:
                add_data.extend(smart_assets)
        except Exception as e:
            log(f"Warning: failed to auto-include project assets: {e}", style="warning")

    # --------------------------------------------------
    # Create a .spec file with the UTF-8 bootloader option
    # --------------------------------------------------
    try:
        log("Generating spec file...", style="info")
        progress.update(task, description="Generating Spec...", completed=30)
        
        dll_name = 'webview.dll'
        if sys.platform == 'linux':
             dll_name = 'libwebview.so'
        elif sys.platform == 'darwin':
             dll_name = 'libwebview_arm64.dylib' if platform.machine() == 'arm64' else 'libwebview_x64.dylib'
             
        dll_src = os.path.join(package_dir, "pytron", "dependancies", dll_name)
        dll_dest = os.path.join("pytron", "dependancies")
        
        requested_engine = 'pyside6' if getattr(args, 'pyside6', False) else getattr(args, 'engine', 'webview2')
        is_native = (requested_engine == 'webview2')
        browser_data = []
        
        makespec_cmd = [
            get_python_executable(), '-m', 'PyInstaller.utils.cliutils.makespec',
            '--name', out_name,
            '--onedir',
            '--noconsole',
        ]
        
        hidden_imports = ['pytron']
        if requested_engine == 'pyside6':
             hidden_imports.extend([
                 'PySide6', 'PySide6.QtCore', 'PySide6.QtGui', 
                 'PySide6.QtWidgets', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore',
                 'PySide6.QtWebChannel', 'PySide6.QtNetwork', 'PySide6.QtPrintSupport',
                 'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.QtQml',
                 'shiboken6'
             ])
             # Optimization: Aggressively exclude massive unused modules
             # QML, Quick, 3D, Charts, DataVis, Designer, Help, Labs, Multimedia, Positioning, 
             # RemoteObjects, Scxml, Sensors, SerialPort, Sql, Svg, Test, TextToSpeech, 
             # UiTools, WebSockets, Xml
             
             excludes = [
                 'PySide6.Qt3DCore', 'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 
                 'PySide6.Qt3DRender', 'PySide6.Qt3DExtras', 'PySide6.Qt3DAnimation',
                 'PySide6.QtCharts', 'PySide6.QtDataVisualization', 
                 'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtLabs',
                 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
                 'PySide6.QtLocation', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
                 'PySide6.QtRemoteObjects', 'PySide6.QtScxml', 
                 'PySide6.QtSensors', 'PySide6.QtSerialPort', 'PySide6.QtSerialBus',
                 'PySide6.QtSql', 'PySide6.QtSvg', 'PySide6.QtSvgWidgets',
                 'PySide6.QtTest', 'PySide6.QtTextToSpeech', 
                 'PySide6.QtUiTools', 'PySide6.QtWebSockets', 'PySide6.QtXml',
                 'PySide6.QtNfc', 'PySide6.QtBluetooth', 'PySide6.QtGamepad',
                 'PySide6.QtVirtualKeyboard', 'PySide6.QtShaderTools',
             ]
             
             for exc in excludes:
                 makespec_cmd.append(f'--exclude-module={exc}')

             # Force OS-specific libs if needed, but PyInstaller usually handles it via hooks
        
        if requested_engine == 'webview2' and not is_native:
             # Legacy fallback for webview2 bundled
             browser_src = os.path.join(package_dir, "pytron", "dependancies", "browser")
             if os.path.exists(browser_src):
                 browser_data.append(f"{browser_src}{os.pathsep}{os.path.join('pytron', 'dependancies', 'browser')}")

        # makespec_cmd already initialized

        
        for imp in hidden_imports:
             makespec_cmd.append(f'--hidden-import={imp}')
             
        makespec_cmd.append(f'--add-binary={dll_src}{os.pathsep}{dll_dest}')
        makespec_cmd.append(str(script))
        
        # Add browser engine to data if not native
        for item in browser_data:
            makespec_cmd.extend(['--add-data', item])
        
        # Windows-specific options
        if sys.platform == 'win32':
             makespec_cmd.append(f'--runtime-hook={package_dir}/pytron/utf8_hook.py')
             # Pass manifest to makespec so spec may include it (deprecated shorthand supported by some PyInstaller versions)
             if manifest_path:
                makespec_cmd.append(f'--manifest={manifest_path}')

        # Set engine if provided (persistent in packaged app)
        if requested_engine:
            log(f"Setting default engine in bundle: {requested_engine}", style="dim")
            # Generate a runtime hook to set the engine
            engine_hook_dir = script.parent / 'build' / 'pytron_hooks'
            engine_hook_dir.mkdir(parents=True, exist_ok=True)
            engine_hook_path = engine_hook_dir / f'engine_hook_{requested_engine}.py'
            engine_hook_path.write_text(f"import os\nos.environ.setdefault('PYTRON_ENGINE', '{requested_engine}')\n")
            makespec_cmd.append(f'--runtime-hook={engine_hook_path.resolve()}')

        if app_icon:
            makespec_cmd.extend(['--icon', app_icon])
            log(f"Using icon: {app_icon}", style="dim")
            
        # Splash Screen Support
        splash_image = settings.get('splash_image')
        if splash_image:
            # Check relative to script dir
            splash_path = script.parent / splash_image
            if splash_path.exists():
                makespec_cmd.append(f'--splash={splash_path.resolve()}')
                log(f"Bundling splash screen: {splash_path}", style="dim")
            else:
                log(f"Warning: configured splash image not found at {splash_path}", style="warning")

        for item in add_data:
            makespec_cmd.extend(['--add-data', item])

        log(f"Running makespec: {' '.join(makespec_cmd)}", style="dim")
        # subprocess.run(makespec_cmd, check=True) # Old way
        makespec_ret = run_command_with_output(makespec_cmd, style="dim")
        if makespec_ret != 0:
            log("Error running makespec", style="error")
            progress.stop()
            return 1

        spec_file = Path(f"{out_name}.spec")
        if not spec_file.exists():
            log(f"Error: expected spec file {spec_file} not found after makespec.", style="error")
            progress.stop()
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
            log(f"Warning: failed to generate nuclear hooks: {e}", style="warning")

        build_cmd = [get_python_executable(), '-m', 'PyInstaller', '--noconfirm', '--clean', str(spec_file)]

        # If hooks were generated, add the hooks dir to PYTHONPATH for this subprocess
        env = None
        if temp_hooks_dir is not None:
            env = os.environ.copy()
            old = env.get('PYTHONPATH', '')
            new = str(temp_hooks_dir.resolve())
            env['PYTHONPATH'] = new + (os.pathsep + old if old else '')

        progress.update(task, description="Compiling...", completed=50)
        log(f"Building from Spec: {' '.join(build_cmd)}", style="dim")
        
        # progress.stop() # No longer stopping!
        if env is not None:
             # run_command_with_output streams the logs properly above the bar
             ret_code = run_command_with_output(build_cmd, env=env, style="dim")
        else:
             ret_code = run_command_with_output(build_cmd, style="dim")
        # progress.start() # No longer restarting!

        if ret_code != 0:
            progress.stop()
            return ret_code

        # -------------------------------------------------------------------------
        # POST-BUILD OPTIMIZATION (PySide6 Specific)
        # -------------------------------------------------------------------------
        if requested_engine == 'pyside6':
            inner_dist = os.path.join(dist_dir, out_name, "_internal")
            pyside_dir = os.path.join(inner_dist, "PySide6")
            
            log("Performing aggressive PySide6 cleanup...", style="dim")
            
            if os.path.exists(pyside_dir):
                # 1. Remove Translations (Qt *.qm files) - huge savings
                trans_dir = os.path.join(pyside_dir, "translations")
                if os.path.exists(trans_dir):
                    shutil.rmtree(trans_dir)
                    console.print(f"  - Removed translations from {trans_dir}", style="dim")

                # 2. Remove Unused Plugins
                plugins_dir = os.path.join(pyside_dir, "plugins")
                if os.path.exists(plugins_dir):
                    # Keep only: platforms, styles, imageformats, tls
                    # Remove: iconengines, generic, networkinformation, position, sensors, texttospeech, etc.
                    
                    keep = {'platforms', 'styles', 'imageformats', 'tls'}
                    for p in os.listdir(plugins_dir):
                        if p not in keep:
                            p_path = os.path.join(plugins_dir, p)
                            # 3. Remove QML folder bloat (keep only essentials)
                qml_dir = os.path.join(pyside_dir, "qml")
                if os.path.exists(qml_dir):
                    log("Pruning QML modules...", style="dim")
                    # We only need core QML engines for WebEngine
                    keep_qml = {'QtQuick', 'Qt', 'QtCore'} # Minimal requirements
                    for d in os.listdir(qml_dir):
                        if d not in keep_qml:
                            d_path = os.path.join(qml_dir, d)
                            if os.path.isdir(d_path):
                                shutil.rmtree(d_path)
                                console.print(f"  - Removed QML module: {d}", style="dim")

                # 4. Blacklist specific massive DLLs that PyInstaller often misses
                blacklist = {
                    'Qt6Pdf.dll', 'Qt6PdfWidgets.dll', 'Qt6VirtualKeyboard.dll',
                    'Qt6ShaderTools.dll', 'Qt6Quick3D', 'Qt63D'
                }
                
                if os.path.exists(inner_dist):
                    for f in os.listdir(inner_dist):
                        for b in blacklist:
                            if f.startswith(b):
                                try:
                                    os.remove(os.path.join(inner_dist, f))
                                    console.print(f"  - Blacklist Pruned: {f}", style="dim")
                                except Exception:
                                    pass
                
                # 5. Prune Resources folder (.debug and redundant .pak)
                res_dir = os.path.join(pyside_dir, "resources")
                if not os.path.exists(res_dir):
                     # Sometimes it's in a different spot depending on PySide version
                     res_dir = os.path.join(inner_dist, "resources")
                
                if os.path.exists(res_dir):
                    log("Pruning Resources folder...", style="dim")
                    for f in os.listdir(res_dir):
                        # Always remove .debug files
                        if f.endswith('.debug'):
                            try:
                                os.remove(os.path.join(res_dir, f))
                                console.print(f"  - Removed debug file: {f}", style="dim")
                            except Exception: pass
                    
                    # Handle locales folder inside resources (usually full of .pak files)
                    locales_dir = os.path.join(res_dir, "qtwebengine_locales")
                    if os.path.exists(locales_dir):
                        log("Pruning locales (keeping en-US only)...", style="dim")
                        for f in os.listdir(locales_dir):
                            if f.endswith('.pak') and f != 'en-US.pak':
                                try:
                                    os.remove(os.path.join(locales_dir, f))
                                except Exception: pass

                # 6. Remove PySide6 .pyi and .py source files
                for root, _, files in os.walk(pyside_dir):
                    for f in files:
                        if f.endswith(('.pyi', '.py')):
                            try:
                                os.remove(os.path.join(root, f))
                            except Exception:
                                pass

        # Cleanup
        cleanup_dist(Path('dist') / out_name)

    except subprocess.CalledProcessError as e:
        log(f"Error generating spec or building: {e}", style="error")
        progress.stop()
        return 1

    if args.installer:
        progress.update(task, description="Building Installer...", completed=90)
        ret = build_installer(out_name, script.parent, app_icon)
        if ret != 0:
            progress.stop()
            return ret

    progress.update(task, description="Done!", completed=100)
    progress.stop()
    console.print(Rule("[bold green]Success"))
    log(f"App packaged successfully: dist/{out_name}", style="bold green")
    return 0
