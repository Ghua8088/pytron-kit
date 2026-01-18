import shutil
import subprocess
import sys
from pathlib import Path


def build_and_deploy():
    """
    Compiles the Rust bootloader and deploys the binary to the bin/ folder.
    This ensures the 'secure' packager always has the latest hardened version.
    """
    # 1. Setup paths
    base_dir = Path(__file__).parent.resolve()
    bin_dir = base_dir / "bin"
    target_dir = base_dir / "target" / "release"

    # 2. Determine binary name
    ext = ".exe" if sys.platform == "win32" else ""
    loader_name = f"pytron_rust_bootloader{ext}"

    print(f"[*] Starting build of {loader_name}...")

    # 3. Compile Rust (Release mode)
    try:
        cargo_bin = shutil.which("cargo") or "cargo"
        subprocess.run(
            [cargo_bin, "build", "--release"], cwd=str(base_dir), check=True
        )  # nosec B603
    except FileNotFoundError:
        print("[!] Error: 'cargo' not found. Please install Rust (https://rustup.rs).")
        sys.exit(1)
    except subprocess.CalledProcessError:
        print("[!] Error: Cargo build failed.")
        sys.exit(1)

    # 4. Ensure bin directory exists
    bin_dir.mkdir(exist_ok=True)

    # 5. Move binary to bin/
    src_bin = target_dir / loader_name
    dest_bin = bin_dir / loader_name

    if src_bin.exists():
        shutil.copy2(src_bin, dest_bin)
        print(
            f"[+] Success: Deployed {loader_name} to {bin_dir.relative_to(base_dir.parent.parent)}"
        )
    else:
        print(f"[!] Error: Could not find compiled binary at {src_bin}")
        sys.exit(1)


if __name__ == "__main__":
    build_and_deploy()
