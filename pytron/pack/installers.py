import os
import sys
import shutil
import subprocess
import json
from pathlib import Path
from ..console import log, run_command_with_output
from ..commands.helpers import get_python_executable


def find_makensis() -> str | None:
    path = shutil.which("makensis")
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


def build_windows_installer(
    out_name: str, script_dir: Path, app_icon: str | None
) -> int:
    log("Building Windows installer (NSIS)...", style="info")
    makensis = find_makensis()
    if not makensis:
        log(
            "NSIS (makensis) not found. Checking for bundled installer...",
            style="warning",
        )

        # Try to find bundled installer in pytron root
        # We need to find package root. Assuming this file is in pytron/pack/
        # So parent.parent is pytron package dir.
        # But we need the root of the repo/install.
        # Let's use import to find package location
        import pytron

        if pytron.__file__:
            pkg_root = Path(pytron.__file__).resolve().parent.parent
        else:
            pkg_root = Path.cwd()  # Fallback

        possible_installers = [
            pkg_root / "nsis-setup.exe",
        ]

        nsis_setup = None
        for installer in possible_installers:
            if installer.exists():
                nsis_setup = installer
                break

        if nsis_setup:
            log(f"Found bundled NSIS installer at {nsis_setup}")
            log(
                "Launching NSIS installer... Please complete the installation to proceed.",
                style="warning",
            )
            try:
                # Run the installer and wait
                subprocess.run([str(nsis_setup)], check=True)
                log("NSIS installer finished. Re-checking for makensis...")
                makensis = find_makensis()
                if makensis:
                    log(
                        f"NSIS successfully installed and found at: {makensis}",
                        style="success",
                    )
            except Exception as e:
                log(f"Error running NSIS installer: {e}", style="error")
        else:
            log("Bundled NSIS installer NOT found.", style="dim")

    if not makensis:
        log(
            "Error: makensis not found. Please install NSIS and add it to PATH.",
            style="error",
        )
        return 1

    # Locate the generated build directory and exe
    dist_dir = Path("dist")
    # In onedir mode, output is dist/AppName
    build_dir = dist_dir / out_name
    exe_file = build_dir / f"{out_name}.exe"

    if not build_dir.exists() or not exe_file.exists():
        log(
            f"Error: Could not find generated build directory or executable in {dist_dir}",
            style="error",
        )
        return 1

    # Locate the NSIS script
    nsi_script = Path("installer.nsi")
    if not nsi_script.exists():
        if Path("installer/Installation.nsi").exists():
            nsi_script = Path("installer/Installation.nsi")
        else:
            # Check inside the pytron package
            try:
                import pytron

                if pytron.__file__ is not None:
                    pkg_root = Path(pytron.__file__).resolve().parent
                    pkg_nsi = pkg_root / "installer" / "Installation.nsi"
                    if pkg_nsi.exists():
                        nsi_script = pkg_nsi
            except ImportError:
                pass

            if not nsi_script.exists():
                print(
                    "Error: installer.nsi not found. Please create one or place it in the current directory."
                )
                return 1

    build_dir_abs = build_dir.resolve()

    # Get metadata from settings
    version = "1.0"
    author = "Pytron User"
    description = f"{out_name} Application"
    copyright = f"Copyright © 2025 {author}"
    signing_config = {}

    try:
        settings_path = script_dir / "settings.json"
        if settings_path.exists():
            settings = json.loads(settings_path.read_text())
            version = settings.get("version", "1.0")
            author = settings.get("author", author)
            description = settings.get("description", description)
            copyright = settings.get("copyright", copyright)
            signing_config = settings.get("signing", {})
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
        # Wrap in quotes in case of spaces
        cmd_nsis.append(f"/DMUI_ICON={abs_icon}")
        cmd_nsis.append(f"/DMUI_UNICON={abs_icon}")
    # NSIS expects switches (like /V4) before the script filename; place verbosity
    # flag before the script so it's honored.
    cmd_nsis.append(f"/V4")
    cmd_nsis.append(str(nsi_script))
    log(f"Running NSIS: {' '.join(cmd_nsis)}", style="dim")

    ret = run_command_with_output(cmd_nsis, style="dim")
    if ret != 0:
        return ret

    # Installer path (based on NSIS script logic)
    installer_path = script_dir / f"{out_name}_Installer_{version}.exe"

    # Signing Logic
    if signing_config and installer_path.exists():
        if "certificate" in signing_config:
            cert_path = script_dir / signing_config["certificate"]
            password = signing_config.get("password")

            if cert_path.exists():
                log(f"Signing installer: {installer_path.name}")
                # Try to find signtool
                signtool = shutil.which("signtool")

                # Check common paths if not in PATH
                if not signtool:
                    common_sign_paths = [
                        r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\signtool.exe",
                        r"C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe",
                        r"C:\Program Files (x86)\Windows Kits\8.1\bin\x64\signtool.exe",
                    ]
                    for p in common_sign_paths:
                        if os.path.exists(p):
                            signtool = p
                            break

                if signtool:
                    sign_cmd = [
                        signtool,
                        "sign",
                        "/f",
                        str(cert_path),
                        "/fd",
                        "SHA256",
                        "/tr",
                        "http://timestamp.digicert.com",
                        "/td",
                        "SHA256",
                    ]
                    if password:
                        sign_cmd.extend(["/p", password])
                    sign_cmd.append(str(installer_path))

                    try:
                        subprocess.run(sign_cmd, check=True)
                        log("Installer signed successfully!", style="success")
                    except Exception as e:
                        log(f"Signing failed: {e}", style="error")
                else:
                    log(
                        "Warning: 'signtool' not found. Cannot sign the installer.",
                        style="warning",
                    )
            else:
                log(f"Warning: Certificate not found at {cert_path}", style="warning")

    return ret


def build_mac_installer(out_name: str, script_dir: Path, app_icon: str | None) -> int:
    log("Building macOS installer (DMG)...")

    # Check for dmgbuild
    if not shutil.which("dmgbuild"):
        log("'dmgbuild' not found. Attempting to install it...", style="warning")
        try:
            subprocess.check_call(
                [get_python_executable(), "-m", "pip", "install", "dmgbuild"]
            )
            log("'dmgbuild' installed successfully.", style="success")
        except subprocess.CalledProcessError:
            log(
                "Failed to install 'dmgbuild'. Please install it manually: pip install dmgbuild",
                style="error",
            )
            log("Skipping DMG creation. Your .app bundle is in dist/", style="warning")
            return 0

    app_bundle = Path("dist") / f"{out_name}.app"
    if not app_bundle.exists():
        log(f"Error: .app bundle not found at {app_bundle}", style="error")
        return 1

    dmg_name = f"{out_name}.dmg"
    dmg_path = Path("dist") / dmg_name

    # Generate settings file for dmgbuild
    settings_file = Path("build") / "dmg_settings.py"
    settings_file.parent.mkdir(parents=True, exist_ok=True)

    with open(settings_file, "w") as f:
        f.write(f"files = [r'{str(app_bundle)}']\n")
        f.write("symlinks = {'Applications': '/Applications'}\n")
        if app_icon and Path(app_icon).suffix == ".icns":
            f.write(f"icon = r'{app_icon}'\n")
        f.write(f"badge_icon = r'{app_icon}'\n")

    cmd = ["dmgbuild", "-s", str(settings_file), out_name, str(dmg_path)]
    log(f"Running: {' '.join(cmd)}", style="dim")
    return subprocess.call(cmd)


def build_linux_installer(out_name: str, script_dir: Path, app_icon: str | None) -> int:
    log("Building Linux installer (.deb package)...")

    # Check for dpkg-deb
    if not shutil.which("dpkg-deb"):
        log("Error: 'dpkg-deb' not found. Cannot build .deb package.", style="error")
        log(
            "Ensure you are on a Debian-based system (Ubuntu, Kali, Pop!_OS, etc.)",
            style="warning",
        )
        return 1

    # Get metadata
    version = "1.0"
    author = "Pytron User"
    description = f"{out_name} Application"
    try:
        settings_path = script_dir / "settings.json"
        if settings_path.exists():
            settings = json.loads(settings_path.read_text())
            version = settings.get("version", "1.0")
            author = settings.get("author", author)
            description = settings.get("description", description)
    except Exception as e:
        log(f"Debug: Failed to load settings.json for linux build: {e}", style="dim")

    # Clean version for Debian (digits, dots, plus, tilde)
    deb_version = "".join(c for c in version if c.isalnum() or c in ".-+~")
    if not deb_version[0].isdigit():
        deb_version = "0." + deb_version

    # Prepare directories
    package_name = out_name.lower().replace(" ", "-").replace("_", "-")
    build_root = Path("build") / "deb_package"
    if build_root.exists():
        shutil.rmtree(build_root)

    install_dir = build_root / "opt" / package_name
    bin_dir = build_root / "usr" / "bin"
    desktop_dir = build_root / "usr" / "share" / "applications"
    debian_dir = build_root / "DEBIAN"

    for d in [install_dir, bin_dir, desktop_dir, debian_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. Copy Application Files
    # Source is dist/out_name (onedir mode)
    src_dir = Path("dist") / out_name
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
        icon_dest_dir = (
            build_root / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
        )
        icon_dest_dir.mkdir(parents=True, exist_ok=True)
        # Convert if needed? explicit .png is best. Assume user provided decent icon or we just copy.
        ext = icon_path.suffix
        if ext == ".ico":
            # Try simple copy, Linux often handles it, but png preferred.
            pass
        shutil.copy(icon_path, icon_dest_dir / (package_name + ext))
        icon_name = package_name  # without extension works usually if matched name

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
    (debian_dir / "control").write_text(control_content)

    # 5. Build .deb
    deb_filename = f"{package_name}_{deb_version}_amd64.deb"
    output_deb = script_dir / deb_filename

    cmd = ["dpkg-deb", "--build", str(build_root), str(output_deb)]
    log(f"Running: {' '.join(cmd)}", style="dim")
    result = subprocess.call(cmd)

    if result == 0:
        log(f"Linux .deb package created: {output_deb}", style="success")
    else:
        log("Failed to create .deb package.", style="error")

    return result


def build_installer(out_name: str, script_dir: Path, app_icon: str | None) -> int:
    if sys.platform == "win32":
        return build_windows_installer(out_name, script_dir, app_icon)
    elif sys.platform == "darwin":
        return build_mac_installer(out_name, script_dir, app_icon)
    elif sys.platform == "linux":
        return build_linux_installer(out_name, script_dir, app_icon)
    else:
        log(f"Installer creation not supported on {sys.platform} yet.", style="warning")
        return 0
