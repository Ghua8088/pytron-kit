import os
from ....console import log
from .utils import run_command

def run_android_project(project_root: str) -> None:
    """
    Install and run the Android app on a connected device.
    """
    target_android_dir = os.path.join(project_root, "android")
    
    # Install and Launch
    log("Installing...", style="info")
    # Find the APK - it might have a different name if we customized the build
    apk_path = os.path.join(
        target_android_dir,
        "app",
        "build",
        "outputs",
        "apk",
        "debug",
        "app-debug.apk",
    )
    
    if not os.path.exists(apk_path):
        log(f"APK not found at {apk_path}. Run 'pytron android build' first.", style="error")
        return

    run_command(["adb", "install", "-r", apk_path], cwd=project_root)

    log("Launching...", style="info")
    # Dynamically determine Package Name from build.gradle
    pkg_name = "com.pytron.android"  # Fallback
    gradle_path = os.path.join(target_android_dir, "app", "build.gradle")
    if os.path.exists(gradle_path):
        with open(gradle_path, "r") as f:
            for line in f:
                if "applicationId" in line:
                    parts = line.split('"')
                    if len(parts) > 1:
                        pkg_name = parts[1]
                    break

    run_command(
        [
            "adb",
            "shell",
            "am",
            "start",
            "-n",
            f"{pkg_name}/com.pytron.android.MainActivity",
        ]
    )

    log("Starting Logcat...", style="info")
    run_logcat()

def run_logcat() -> None:
    """
    Run adb logcat with filters.
    """
    run_command(
        [
            "adb",
            "logcat",
            "-v",
            "time",
            "*:S",
            "Pytron:V",
            "PytronNative:V",
            "PytronPython:V",
            "AndroidRuntime:E",
            "chromium:I",
        ]
    )
