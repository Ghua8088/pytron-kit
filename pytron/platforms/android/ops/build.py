import os
from ....console import log
from .utils import run_command
import stat


def build_android_project(project_root: str, is_aab: bool = False) -> None:
    """
    Build the Android project (APK or AAB).
    """
    target_android_dir = os.path.join(project_root, "android")

    if not os.path.exists(target_android_dir):
        log("Run init first.", style="error")
        return

    # Ensure gradlew is executable
    gradlew = os.path.join(target_android_dir, "gradlew")
    if os.name != "nt" and os.path.exists(gradlew):
        os.chmod(gradlew, stat.S_IRWXU)

    if is_aab:
        log("Building Android App Bundle (.aab) for Release...", style="info")
        task = "bundleRelease"
    else:
        log("Building APK (Debug)...", style="info")
        task = "assembleDebug"

    cmd = [gradlew, task]
    if os.name == "nt":
        cmd = [gradlew + ".bat", task]

    run_command(cmd, cwd=target_android_dir)

    if is_aab:
        aab_path = os.path.join(
            target_android_dir,
            "app",
            "build",
            "outputs",
            "bundle",
            "release",
            "app-release.aab",
        )
        # Note: If not signed, it might be in a different place or named differently, but bundleRelease usually goes here
        if os.path.exists(aab_path):
            log(f"Build Success! AAB: {aab_path}", style="success")
        else:
            # Fallback check for unsigned
            unsigned_aab = os.path.join(
                target_android_dir,
                "app",
                "build",
                "outputs",
                "bundle",
                "release",
                "app-release-unsigned.aab",
            )
            if os.path.exists(unsigned_aab):
                log(
                    f"Build Success! AAB (Unsigned): {unsigned_aab}",
                    style="success",
                )
            else:
                log("Build seemed to succeed but AAB not found?", style="warning")
    else:
        apk_path = os.path.join(
            target_android_dir,
            "app",
            "build",
            "outputs",
            "apk",
            "debug",
            "app-debug.apk",
        )
        if os.path.exists(apk_path):
            log(f"Build Success! APK: {apk_path}", style="success")
        else:
            log("Build seemed to succeed but APK not found?", style="warning")
