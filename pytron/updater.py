import os
import sys
import json
import urllib.request
import urllib.error
import subprocess
import tempfile
import logging
from pathlib import Path
from packaging.version import parse as parse_version


class Updater:
    def __init__(self, current_version=None):
        self.logger = logging.getLogger("Pytron.Updater")
        # Try to infer version if not provided
        self.current_version = current_version
        if not self.current_version:
            try:
                # If running from source/pytron structure
                from . import __version__

                self.current_version = __version__
            except ImportError:
                self.current_version = "0.0.0"

        # In a real app, the developer sets the version in settings.json or passes it.
        # We will try to find the app's version from settings.json if it exists nearby
        try:
            settings_path = Path("settings.json")
            if settings_path.exists():
                data = json.loads(settings_path.read_text())
                if "version" in data:
                    self.current_version = data["version"]
        except:
            pass

    def check(self, url: str) -> dict | None:
        """
        Checks for updates at the given URL.
        Expected JSON format at URL:
        {
            "version": "1.0.1",
            "url": "https://example.com/downloads/MyApp-1.0.1.exe",
            "notes": "Bug fixes..."
        }
        """
        self.logger.info(f"Checking for updates at {url}...")
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
                remote_version = data.get("version")

                if not remote_version:
                    self.logger.error("Invalid update manifest: missing 'version'")
                    return None

                # Compare versions
                if parse_version(remote_version) > parse_version(self.current_version):
                    self.logger.info(
                        f"Update available: {remote_version} (Current: {self.current_version})"
                    )
                    return data
                else:
                    self.logger.info("App is up to date.")
                    return None

        except urllib.error.URLError as e:
            self.logger.error(f"Failed to check for updates: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error checking updates: {e}")
            return None

    def download_and_install(self, update_info: dict, on_progress=None):
        """
        Downloads the installer/executable from update_info['url'] and runs it.
        """
        url = update_info.get("url")
        if not url:
            self.logger.error("No download URL provided in update info.")
            return False

        filename = url.split("/")[-1]
        if not filename.endswith(
            (".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".AppImage")
        ):
            # Fallback name
            filename = (
                "update_installer.exe"
                if sys.platform == "win32"
                else "update_installer"
            )

        download_path = Path(tempfile.gettempdir()) / filename
        self.logger.info(f"Downloading update from {url} to {download_path}...")

        try:

            def progress(block_num, block_size, total_size):
                if on_progress:
                    downloaded = block_num * block_size
                    percent = min(100, int((downloaded / total_size) * 100))
                    on_progress(percent)

            urllib.request.urlretrieve(url, download_path, reporthook=progress)
            self.logger.info("Download complete.")

            # Run the installer
            self.logger.info("Launching installer...")

            if sys.platform == "win32":
                # Run executable detached
                subprocess.Popen(
                    [str(download_path)],
                    shell=True,
                    creationflags=(
                        subprocess.DETACHED_PROCESS
                        if hasattr(subprocess, "DETACHED_PROCESS")
                        else 0
                    ),
                )
            elif sys.platform == "darwin":
                # Open DMG or pkg
                subprocess.Popen(["open", str(download_path)])
            else:
                # Linux, make executable and run? Or open?
                # Usually user needs to confirm.
                os.chmod(download_path, 0o755)
                subprocess.Popen([str(download_path)])

            self.logger.info("Update launched. Exiting app.")
            sys.exit(0)

        except Exception as e:
            self.logger.error(f"Failed to install update: {e}")
            return False
