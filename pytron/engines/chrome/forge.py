import os
import sys
import zipfile
import shutil
import requests
import platform
import logging

logger = logging.getLogger("Pytron.ChromeForge")

# Configuration
ELECTRON_VERSION = "30.0.6"  # Stable version used for the Mojo Bridge


def get_electron_url():
    system = platform.system().lower()
    arch = "x64"  # Default to x64 for now

    if system == "windows":
        return f"https://github.com/electron/electron/releases/download/v{ELECTRON_VERSION}/electron-v{ELECTRON_VERSION}-win32-{arch}.zip"
    elif system == "darwin":
        return f"https://github.com/electron/electron/releases/download/v{ELECTRON_VERSION}/electron-v{ELECTRON_VERSION}-darwin-{arch}.zip"
    else:
        return f"https://github.com/electron/electron/releases/download/v{ELECTRON_VERSION}/electron-v{ELECTRON_VERSION}-linux-{arch}.zip"


def download_electron(dest_path):
    url = get_electron_url()
    logger.info(
        f"Connecting to Chrome Shell Depository (Electron v{ELECTRON_VERSION})..."
    )

    response = requests.get(url, stream=True)
    total_size = int(response.headers.get("content-length", 0))
    temp_zip = os.path.join(dest_path, "electron.zip")

    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        DownloadColumn,
        TransferSpeedColumn,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("[cyan]Injecting Chromium Core...", total=total_size)

        with open(temp_zip, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    progress.update(task, advance=len(chunk))

    logger.info("Extraction phase: Unpacking Mojo shells...")
    with zipfile.ZipFile(temp_zip, "r") as zip_ref:
        zip_ref.extractall(dest_path)

    os.remove(temp_zip)


def perform_surgery(path):
    """Strips the Electron binary down to a minimal Chrome Shell."""
    logger.info("Performing binary surgery (removing bloat)...")

    # Files to keep
    to_keep = [
        "electron.exe",
        "electron",
        "resources.pak",
        "chrome_100_percent.pak",
        "chrome_200_percent.pak",
        "icudtl.dat",
        "v8_context_snapshot.bin",
        "snapshot_blob.bin",
        "ffmpeg.dll",
        "libEGL.dll",
        "libGLESv2.dll",
        "vk_swiftshader_icd.json",
        "vk_swiftshader.dll",
        "vulkan-1.dll",
        "d3dcompiler_47.dll",
    ]

    # 1. Clean root
    for item in os.listdir(path):
        if item not in to_keep and item not in ["locales", "resources"]:
            p = os.path.join(path, item)
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)

    # 2. Clean locales (Keep only en-US)
    locales_path = os.path.join(path, "locales")
    if os.path.exists(locales_path):
        for locale in os.listdir(locales_path):
            if locale != "en-US.pak":
                os.remove(os.path.join(locales_path, locale))

    # 3. Inject Shell Logic
    logger.info("Injecting Mojo Bridge logic...")
    app_path = os.path.join(path, "resources", "app")
    if not os.path.exists(app_path):
        os.makedirs(app_path)

    # Source the shell files from our core
    core_shell_src = os.path.abspath(os.path.join(os.path.dirname(__file__), "shell"))
    for file in os.listdir(core_shell_src):
        shutil.copy(os.path.join(core_shell_src, file), os.path.join(app_path, file))


class ChromeForge:
    def __init__(self, target_dir=None):
        self.target_dir = target_dir or os.path.expanduser("~/.pytron/engines/chrome")

    def provision(self):
        """Ensures the Chrome engine is installed and ready."""
        exe_name = "electron.exe" if platform.system() == "Windows" else "electron"
        exe_path = os.path.join(self.target_dir, exe_name)

        if not os.path.exists(exe_path):
            if not os.path.exists(self.target_dir):
                os.makedirs(self.target_dir, exist_ok=True)

            download_electron(self.target_dir)
            perform_surgery(self.target_dir)

        return exe_path


def setup_engine(target_dir=None):
    forge = ChromeForge(target_dir)
    return forge.provision()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    setup_engine()
