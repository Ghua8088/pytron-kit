import subprocess
import shutil
import os
import sys

# Paths
# This script is in pytron/pytron/engines/native/
ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
# ROOT is d:\playground\pytron (3 levels up)
ROOT = os.path.abspath(os.path.join(ENGINE_DIR, "..", "..", ".."))

# Destination Directory (Python runtime dependencies)
DEPENDENCIES_DIR = os.path.join(ROOT, "pytron", "dependencies")

# Determine Extension (Python Extension Module)
if sys.platform == "win32":
    LIB_NAME = "pytron_native.dll"  # Cargo outputs .dll on Windows
    EXT_NAME = "pytron_native.pyd"  # Python expects .pyd
elif sys.platform == "darwin":
    LIB_NAME = "libpytron_native.dylib"
    EXT_NAME = "pytron_native.so"  # Python on Mac expects .so
else:
    LIB_NAME = "libpytron_native.so"
    EXT_NAME = "pytron_native.so"

TARGET_PATH = os.path.join(ENGINE_DIR, "target", "release", LIB_NAME)
DEST_PATH = os.path.join(DEPENDENCIES_DIR, EXT_NAME)


def build():
    print(f"\n[BUILD] Starting Iron Engine Build...")
    print(f"   Source: {ENGINE_DIR}")
    print(f"   Target: {DEST_PATH}\n")

    # 1. Check Rust
    try:
        subprocess.check_output(["cargo", "--version"])
    except FileNotFoundError:
        print("[ERROR] Rust (cargo) is not installed or not in PATH.")
        sys.exit(1)

    # 2. Build Release
    print(f"[INFO] Compiling (Release Mode)... This may take a minute.")
    env = os.environ.copy()
    env["PYO3_USE_ABI3_FORWARD_COMPATIBILITY"] = "1"
    try:
        subprocess.check_call(["cargo", "build", "--release"], cwd=ENGINE_DIR, env=env)
    except subprocess.CalledProcessError:
        print("\n[ERROR] Cargo Build Failed! Check the error messages above.")
        sys.exit(1)

    # 3. Verify Artifact
    if not os.path.exists(TARGET_PATH):
        print(f"\n[ERROR] Build finished but artifact not found at:\n   {TARGET_PATH}")
        sys.exit(1)

    # 4. Deploy
    print(f"\n[SUCCESS] Build Successful!")
    print(f"[INFO] Copying artifact to dependencies...")

    os.makedirs(DEPENDENCIES_DIR, exist_ok=True)

    try:
        shutil.copy2(TARGET_PATH, DEST_PATH)
        print(f"[SUCCESS] Deployed to: {DEST_PATH}")
        print("[INFO] You are ready to run Pytron with Native Power.")
    except Exception as e:
        print(f"[ERROR] Failed to copy file: {e}")
        try:
            if os.path.exists(DEST_PATH):
                os.remove(DEST_PATH)  # Force delete
            shutil.copy2(TARGET_PATH, DEST_PATH)
            print(f"[SUCCESS] Deployed to: {DEST_PATH} (Force Overwrite)")
        except Exception as e2:
            print(f"[ERROR] Force copy failed: {e2}. Is the app running?")
            sys.exit(1)


if __name__ == "__main__":
    build()
