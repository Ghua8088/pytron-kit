import os
import sys
import shutil
import subprocess
import platform
import re
from pathlib import Path
from ..console import log


def get_python_executable():
    """Returns the path to the current python executable."""
    return sys.executable


def ensure_cython(python_exe):
    """Ensures Cython is installed/available."""
    try:
        subprocess.run(
            [python_exe, "-c", "import Cython"], check=True, capture_output=True
        )
    except subprocess.CalledProcessError:
        log("Cython missing in build environment. Installing...", style="info")
        try:
            subprocess.run([python_exe, "-m", "pip", "install", "Cython"], check=True)
        except subprocess.CalledProcessError:
            log(
                "Failed to install Cython automatically. Please install it manually in your venv.",
                style="error",
            )
            return False
    return True


def find_zig():
    """Locates the Zig compiler binary."""
    zig_bin = shutil.which("zig")
    if not zig_bin:
        # Check if ziglang package is installed and use its binary
        try:
            import ziglang

            zig_bin = os.path.join(os.path.dirname(ziglang.__file__), "bin", "zig")
            if sys.platform == "win32":
                zig_bin += ".exe"
            if not os.path.exists(zig_bin):
                # Try sibling bin directory for some installations
                zig_bin = os.path.join(
                    os.path.dirname(os.path.dirname(ziglang.__file__)), "bin", "zig"
                )
                if sys.platform == "win32":
                    zig_bin += ".exe"

            if not os.path.exists(zig_bin):
                zig_bin = None
        except ImportError:
            zig_bin = None

    if not zig_bin:
        log(
            "Zig compiler ('zig') not found. Falling back to default C compiler...",
            style="warning",
        )
    else:
        log(f"Using Zig compiler at: {zig_bin}", style="dim")

    return zig_bin


def cython_gen_c(script_path: Path, build_dir: Path, python_exe: str):
    """Generates a C file from a Python script using Cython."""
    # 0. PRE-PROCESS: Force the 'main' block to execute when imported as a module
    try:
        content = script_path.read_text(encoding="utf-8", errors="ignore")
        pattern = r'if\s+__name__\s*==\s*[\'"]__main__[\'"]\s*:'
        if re.search(pattern, content):
            log("  + Patching entry point for native execution...", style="dim")
            content = re.sub(pattern, "if True: # Shield Redirect", content)

        target_script = build_dir / "app.py"
        target_script.write_text(content, encoding="utf-8")
    except Exception as e:
        log(f"Warning: Failed to pre-process script: {e}", style="warning")
        target_script = script_path

    c_file = build_dir / "app.c"

    try:
        log("  + Generating C source with Cython...", style="dim")
        process = subprocess.run(
            [
                python_exe,
                "-m",
                "cython",
                "-3",
                "--fast-fail",
                str(target_script),
                "-o",
                str(c_file),
            ],
            capture_output=True,
            text=True,
        )

        if process.returncode != 0:
            log(f"Cython generation failed: {process.stderr}", style="error")
            return None
    except Exception as e:
        log(f"Cythonization error: {e}", style="error")
        return None

    if not c_file.exists():
        log("Cython failed to generate C source.", style="error")
        return None

    return c_file


def compile_c_to_binary(c_file: Path, build_dir: Path, zig_bin: str, python_exe: str):
    """Compiles C source to a .pyd/.so using Zig."""
    ext = ".pyd" if sys.platform == "win32" else ".so"
    output_bin = build_dir / f"app{ext}"

    # Get Python build constants
    res_include = subprocess.run(
        [python_exe, "-c", "import sysconfig; print(sysconfig.get_path('include'))"],
        capture_output=True,
        text=True,
    )
    py_include = res_include.stdout.strip()

    res_ver = subprocess.run(
        [
            python_exe,
            "-c",
            "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')",
        ],
        capture_output=True,
        text=True,
    )
    py_ver_str = (
        res_ver.stdout.strip() or f"{sys.version_info.major}{sys.version_info.minor}"
    )

    res_prefix = subprocess.run(
        [python_exe, "-c", "import sys; print(sys.base_prefix)"],
        capture_output=True,
        text=True,
    )
    base_prefix = res_prefix.stdout.strip() or sys.base_prefix

    if sys.platform == "win32":
        py_lib_dir = os.path.join(base_prefix, "libs")
    else:
        res_libdir = subprocess.run(
            [
                python_exe,
                "-c",
                "import sysconfig; print(sysconfig.get_config_var('LIBDIR') or '')",
            ],
            capture_output=True,
            text=True,
        )
        py_lib_dir = res_libdir.stdout.strip() or os.path.join(base_prefix, "lib")

    if zig_bin:
        # Determine target architecture
        machine = platform.machine().lower()
        if machine in ["amd64", "x86_64"]:
            arch = "x86_64"
        elif machine in ["arm64", "aarch64"]:
            arch = "aarch64"
        else:
            arch = "x86"

        target = (
            f"{arch}-windows" if sys.platform == "win32" else f"{arch}-{sys.platform}"
        )
        if sys.platform == "linux":
            target += "-gnu"

        log(
            f"  + Compiling {output_bin.name} with Zig CC (Target: {target})...",
            style="dim",
        )

        compile_cmd = [
            zig_bin,
            "cc",
            "-target",
            target,
            "-O3",
            "-shared",
            "-o",
            str(output_bin),
            str(c_file),
            f"-I{py_include}",
        ]

        if sys.platform == "win32":
            compile_cmd.append(f"-L{py_lib_dir}")
            lib_name = f"python{py_ver_str}"
            compile_cmd.append(f"-l{lib_name}")
        else:
            compile_cmd.append("-fPIC")
            if py_lib_dir:
                compile_cmd.append(f"-L{py_lib_dir}")

        try:
            res = subprocess.run(compile_cmd, capture_output=True, text=True)
            if res.returncode != 0:
                log(f"Zig compilation failed: {res.stderr}", style="error")
                return None
        except Exception as e:
            log(f"Zig encountered an error: {e}", style="error")
            return None

        if output_bin.exists():
            log(
                f"Successfully compiled to {output_bin.name} using Zig", style="success"
            )
            return output_bin

    return None


def fallback_compile(script_path: Path, build_dir: Path, python_exe: str):
    """Fallback using standard setuptools/MSVC."""
    log("Using standard Python build tools...", style="dim")
    setup_path = build_dir / "setup_compile.py"
    setup_content = f"""
from setuptools import setup
from Cython.Build import cythonize
import sys

setup(
    ext_modules = cythonize("{script_path.as_posix()}", 
                            compiler_directives={{'language_level': "3"}},
                            quiet=True),
)
"""
    setup_path.write_text(setup_content)
    cmd = [python_exe, "setup_compile.py", "build_ext", "--inplace"]

    try:
        subprocess.run(
            cmd, cwd=str(build_dir), capture_output=True, text=True, check=True
        )
    except Exception as e:
        log(f"Standard compilation failed: {e}", style="error")
        return None

    ext = ".pyd" if sys.platform == "win32" else ".so"
    compiled_files = list(build_dir.glob(f"*{ext}"))
    if not compiled_files:
        compiled_files = list(build_dir.glob(f"build/lib*/{script_path.stem}*{ext}"))

    if compiled_files:
        pyd_path = compiled_files[0]
        final_pyd = build_dir / f"app{ext}"
        if final_pyd.exists():
            os.remove(final_pyd)
        shutil.move(str(pyd_path), str(final_pyd))
        return final_pyd
    return None


def compile_script(script_path: Path, build_dir: Path):
    """Orchestrates the full compilation pipeline."""
    python_exe = get_python_executable()

    if not ensure_cython(python_exe):
        return None

    zig_bin = find_zig()

    c_file = cython_gen_c(script_path, build_dir, python_exe)
    if not c_file:
        return None

    # Try Zig
    if zig_bin:
        result = compile_c_to_binary(c_file, build_dir, zig_bin, python_exe)
        if result:
            return result

    # Fallback
    log("Zig compliation not possible, falling back...", style="warning")
    return fallback_compile(script_path, build_dir, python_exe)
