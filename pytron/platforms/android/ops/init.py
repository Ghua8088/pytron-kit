import os
import shutil
from pathlib import Path
from ....console import log

def init_android_project(project_root: str, force: bool = False) -> None:
    """
    Initialize the Android project structure.
    """
    target_android_dir = os.path.join(project_root, "android")
    
    # Template directory is ../shell relative to this file
    # pytron/platforms/android/ops/init.py -> pytron/platforms/android/shell
    current_dir = Path(__file__).resolve().parent
    template_dir = current_dir.parent / "shell"

    if os.path.exists(target_android_dir):
        if not force:
            log(
                "Android folder already exists. Use --force to overwrite.",
                style="warning",
            )
            return
        shutil.rmtree(target_android_dir)

    log(f"Copying Android template to {target_android_dir}...")

    # Helper to ignore some build files
    def ignore_patterns(path, names):
        return [
            n
            for n in names
            if n in ["build", ".gradle", ".idea", "local.properties"]
        ]

    shutil.copytree(template_dir, target_android_dir, ignore=ignore_patterns)

    # Create local.properties with SDK location if ANDROID_HOME is set
    sdk_dir = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if sdk_dir:
        with open(os.path.join(target_android_dir, "local.properties"), "w") as f:
            # Escape backslashes for Windows
            sdk_dir_safe = sdk_dir.replace("\\", "\\\\")
            f.write(f"sdk.dir={sdk_dir_safe}")

    log("Android project initialized!", style="success")

def reset_android_project(project_root: str) -> None:
    """
    Reset the Android project structure (delete and re-init).
    """
    target_android_dir = os.path.join(project_root, "android")
    
    if os.path.exists(target_android_dir):
        log(
            f"Removing existing Android folder: {target_android_dir}",
            style="warning",
        )
        shutil.rmtree(target_android_dir)
    
    # Reuse init logic, forcing creation
    init_android_project(project_root, force=True)
    log("Android project reset complete!", style="success")
