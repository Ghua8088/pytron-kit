import os
import sys
import shutil
import secrets
import traceback
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from ..console import log, run_command_with_output, console, Rule
from .installers import build_installer
from ..commands.helpers import get_python_executable, get_venv_site_packages
from ..commands.harvest import generate_nuclear_hooks

from .metadata import MetadataEditor


# The placeholder that exists in the precompiled binary
KEY_PLACEHOLDER = b"__PYTRON_SECURE_SHIELD_KEY_32B__"


def get_webview_lib():
    if sys.platform == "win32":
        return "webview.dll"
    elif sys.platform == "darwin":
        return "libwebview.dylib"
    else:
        return "libwebview.so"


from .utils import cleanup_dist as prune_junk_folders

import plistlib



def apply_metadata_to_binary(binary_path, icon_path, settings, dist_dir, package_dir=None):
    editor = MetadataEditor(package_dir=package_dir)
    return editor.update(binary_path, icon_path, settings, dist_dir)


def append_key_footer(binary_path, key_bytes, settings):
    """
    Appends the Shield Key and Settings to the end of the binary using a structural footer.
    Format (Disk Order): [SETTINGS JSON] [LEN: 4 bytes LE] [KEY: 32 bytes] [MAGIC: 8 bytes]
    Magic: "PYTRON_K"
    """
    MAGIC = b"PYTRON_K"

    if len(key_bytes) != 32:
        log("Error: Key must be 32 bytes.", style="error")
        return False

    try:
        with open(binary_path, "ab") as f:
            f.write(key_bytes)  # Write Key (32B)
            f.write(MAGIC)  # Write Magic (8B)

        log(
            f"Sealed {binary_path.name}: Embedded Shield Key (40 bytes).",
            style="success",
        )
        return True
    except Exception as e:
        log(f"Error appending key footer: {e}", style="error")
        return False


def run_secure_build(
    args,
    script,
    out_name,
    settings,
    app_icon,
    package_dir,
    add_data,
    progress,
    task,
    package_context=None,
):
    """
    Implements the 'Agentic Shield' secure packaging workflow.
    """
    try:
        log("Rust Bootloader: Initializing Secure Packaging...[/]", style="info")
        progress.update(
            task, description="Bootloader: Preparing Environment...", completed=10
        )

        script_path = Path(script).resolve()
        script_dir = script_path.parent
        script_stem = script_path.stem

        # 1. GENERATE OR LOAD KEY
        env_path = script_dir / ".env"
        boot_key_hex = None

        if env_path.exists():
            with open(env_path, "r") as f:
                for line in f:
                    if line.startswith("PYTRON_SHIELD_KEY="):
                        boot_key_hex = line.strip().split("=")[1]
                        break

        if not boot_key_hex:
            # Generate a new 32-byte key
            key_bytes = secrets.token_bytes(32)
            boot_key_hex = key_bytes.hex()
            with open(env_path, "a" if env_path.exists() else "w") as f:
                f.write(
                    f"\n# Pytron Secure Shield Key - DO NOT SHARE\nPYTRON_SHIELD_KEY={boot_key_hex}\n"
                )
            log(f"Generated new unique shield key and saved to .env", style="success")
        else:
            log(f"Using existing shield key from .env", style="dim")
            key_bytes = bytes.fromhex(boot_key_hex)
        build_dir = Path("build") / "secure_build"
        if build_dir.exists():
            shutil.rmtree(build_dir)
        build_dir.mkdir(parents=True, exist_ok=True)

        # 2. GENERATE BOOTSTRAP SCRIPT
        bootstrap_path = build_dir / "bootstrap_env.py"
        bootstrap_content = f"""
import sys, os, json, logging, threading, asyncio, textwrap, re, socket, ssl, ctypes, hashlib, time, base64, mimetypes
from collections import deque
import pytron

try:
    import {script_stem}
except Exception:
    pass

print("Secure Environment Ready")
"""
        bootstrap_path.write_text(bootstrap_content)

        # 3. PREPARE DATA FILES
        spec_datas = []
        for item in add_data:
            if os.pathsep in item:
                src, dest = item.split(os.pathsep)
                spec_datas.append(
                    (
                        str(Path(src).resolve()).replace("\\", "/"),
                        dest.replace("\\", "/"),
                    )
                )

        # 3.5. GENERATE NUCLEAR HOOKS (Parity with package.py)
        temp_hooks_dir = None
        hookspath_str = "[]"

        # Calculate site-packages to ensure we harvest from the correct ENV
        python_exe = get_python_executable()
        site_packages = get_venv_site_packages(python_exe)

        # Add site_packages to pathex to ensure "from env not pythonhome"
        pathex_list = [script_dir.as_posix(), str(site_packages).replace("\\", "/")]

        try:
            if getattr(args, "collect_all", False) or getattr(
                args, "force_hooks", False
            ):
                temp_hooks_dir = build_dir / "nuclear_hooks"
                collect_mode = getattr(args, "collect_all", False)

                generate_nuclear_hooks(
                    temp_hooks_dir,
                    collect_all_mode=collect_mode,
                    search_path=site_packages,
                )
                hookspath_str = f"[r'{temp_hooks_dir.as_posix()}']"
                log("Generated nuclear hooks for secure build.", style="dim")
        except Exception as e:
            log(f"Warning: failed to generate nuclear hooks: {e}", style="warning")

        # 4. GENERATE SPEC FILE
        spec_path = build_dir / "secure.spec"
        lib_name = get_webview_lib()
        dll_src = Path(package_dir) / "pytron" / "dependancies" / lib_name
        dll_dest = os.path.join("pytron", "dependancies")

        # Parity: Add Windows UTF-8 Hook
        runtime_hooks = []
        if sys.platform == "win32":
            utf8_hook_path = Path(package_dir) / "pytron" / "utf8_hook.py"
            if utf8_hook_path.exists():
                runtime_hooks.append(str(utf8_hook_path).replace("\\", "/"))

        # Parity: Handle 'force-package' from settings using collect_all
        force_pkgs = settings.get("force-package", [])
        if isinstance(force_pkgs, str):
            force_pkgs = [p.strip() for p in force_pkgs.split(",")]

        collect_code = ""
        for pkg in force_pkgs:
            if pkg and "-" not in pkg:  # Simple validation
                collect_code += f"""
tmp_ret = collect_all('{pkg}')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]
"""
                log(f"Secure Bundle: Forcing full collection of {pkg}", style="dim")

        # Note: We rely on Analysis of bootstrap_env.py (which imports user script)
        # to find dependencies. We explicitly add site_packages to pathex.
        dll_dest_posix = dll_dest.replace("\\", "/")
        spec_content = f"""
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = {repr(spec_datas)}
binaries = [('{dll_src.as_posix()}', '{dll_dest_posix}')]
hiddenimports = ['pytron', 'textwrap', 're', 'json', 'ctypes', 'cryptography']

# Force-Package Collections
{collect_code}

a = Analysis(
    ['{bootstrap_path.name}'],
    pathex={repr(pathex_list)},
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath={hookspath_str},
    hooksconfig={{}},
    runtime_hooks={repr(runtime_hooks)},
    excludes=[],
    noarchive=True,
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='{out_name}_base',
    debug=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='{out_name}',
)
"""
        spec_path.write_text(spec_content)

        # 5. RUN PYINSTALLER
        log("Bundling Python runtime and project dependencies...", style="dim")
        progress.update(
            task, description="Bootloader: Bundling Runtime...", completed=30
        )

        build_cmd = [
            get_python_executable(),
            "-m",
            "PyInstaller",
            "--noconfirm",
            spec_path.name,
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = (
            str(script_dir.resolve()) + os.pathsep + env.get("PYTHONPATH", "")
        )

        ret = run_command_with_output(
            build_cmd, cwd=str(build_dir), env=env, style="dim"
        )
        if ret != 0:
            log("Error: PyInstaller bundling failed.", style="error")
            return 1

        # 6. ENCRYPT APP SCRIPT
        log("Forging AES-256-GCM Shield...", style="cyan")
        progress.update(
            task, description="Bootloader: Encrypting Payload...", completed=60
        )

        payload_dest = build_dir / "dist" / out_name / "app.pytron"
        with open(script, "r", encoding="utf-8") as f:
            code = f.read()

        aesgcm = AESGCM(key_bytes)
        nonce = os.urandom(12)
        encrypted_code = aesgcm.encrypt(nonce, code.encode("utf-8"), None)

        new_payload_data = nonce + encrypted_code
        with open(payload_dest, "wb") as f:
            f.write(new_payload_data)

        # 6.6. GENERATE EVOLUTION PATCH (If requested)
        patch_from = getattr(args, "patch_from", None)
        if patch_from:
            old_payload_path = Path(patch_from)
            if old_payload_path.exists():
                try:
                    import bsdiff4

                    log(
                        f"Generating Binary Evolution patch from {old_payload_path.name}...",
                        style="cyan",
                    )
                    old_payload_data = old_payload_path.read_bytes()
                    patch_data = bsdiff4.diff(old_payload_data, new_payload_data)

                    patch_dest = build_dir / "dist" / out_name / "app.pytron_patch"
                    patch_dest.write_bytes(patch_data)

                    reduction = 100 - (len(patch_data) / len(new_payload_data) * 100)
                    log(
                        f"Success: Evolution patch generated ({len(patch_data)} bytes, -{reduction:.1f}% size)",
                        style="success",
                    )
                except ImportError:
                    log(
                        "Warning: 'bsdiff4' not installed. Skipping patch generation.",
                        style="warning",
                    )
                except Exception as e:
                    log(f"Warning: Failed to generate patch: {e}", style="warning")
            else:
                log(
                    f"Warning: Patch source file not found: {patch_from}",
                    style="warning",
                )

        # Cleanup leaked files
        internal_folder = build_dir / "dist" / out_name / "_internal"
        for leak in [f"{script_stem}.py", "bootstrap_env.py"]:
            leak_path = internal_folder / leak
            if leak_path.exists():
                os.remove(leak_path)

        # 7. DEPLOY & PATCH PRECOMPILED LOADER
        log("Deploying and Hardening Loader...", style="info")
        progress.update(
            task, description="Bootloader: Deploying Loader...", completed=80
        )

        ext = ".exe" if sys.platform == "win32" else ""
        loader_name = f"pytron_rust_bootloader{ext}"
        precompiled_bin = (
            Path(package_dir)
            / "pytron"
            / "pack"
            / "secure_loader"
            / "bin"
            / loader_name
        )

        if not precompiled_bin.exists():
            log(
                "Error: Native loader binary not found in pytron/pack/secure_loader/bin/",
                style="error",
            )
            return 1

        # 8. ASSEMBLE FINAL DIST
        final_dist = Path("dist") / out_name
        if final_dist.exists():
            shutil.rmtree(final_dist)

        shutil.copytree(build_dir / "dist" / out_name, final_dist)

        # Deploy and patch the loader
        final_loader = final_dist / f"{out_name}{ext}"
        shutil.copy(precompiled_bin, final_loader)

        # Apply Icon and Metadata (Windows / macOS / Linux)
        # MUST happen before sealing the binary, as resource editing shifts offsets!
        final_loader = apply_metadata_to_binary(
            final_loader, app_icon, settings, final_dist, package_dir=package_dir
        )

        # Seal the binary with the footer (Must be the last operation)
        if not append_key_footer(final_loader, key_bytes, settings):
            return 1

        # Nuclear Pruning & Distribution Hardening
        has_splash = bool(settings.get("splash_image"))
        prune_junk_folders(final_dist, preserve_tk=has_splash)

        # Cleanup dummy base
        base_bin = final_dist / f"{out_name}_base{ext}"
        if base_bin.exists():
            os.remove(base_bin)

        # 9. INSTALLER
        if getattr(args, "installer", False):
            progress.update(
                task, description="Shield: Building Installer...", completed=95
            )
            ret = build_installer(out_name, script_dir, app_icon)
            if ret != 0:
                return ret

        try:
            shutil.rmtree(build_dir)
        except Exception as e:
            log(f"Debug: Failed to cleanup build dir: {e}", style="dim")

        progress.update(task, description="Shield: Complete!", completed=100)
        progress.stop()
        console.print(Rule("[bold green]Success: Agentic Shield Active"))
        log(f"Secure app packaged: {final_dist}", style="bold green")
        return 0

    except Exception as e:
        import traceback

        traceback.print_exc()
        log(f"Shield Error: {e}", style="error")
        progress.stop()
        return 1
