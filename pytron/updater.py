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
import stat


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
            if not url.startswith("https://"):
                raise ValueError("Updater only supports HTTPS")

            with urllib.request.urlopen(
                url, timeout=5
            ) as response:  # nosec B310 # nosemgrep
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
        Downloads the update.
        In Secure Builds, it prefers the 'patch_url' to download a tiny evolution patch.
        Otherwise, it downloads the full installer.
        """
        patch_url = update_info.get("patch_url")
        full_url = update_info.get("url")

        # Detect if we are in a Secure Build (app.pytron exists next to EXE)
        is_secure = False
        app_root = Path(
            getattr(sys, "_MEIPASS", os.getcwd())
        )  # Usually _internal if frozen
        if getattr(sys, "frozen", False):
            # Real app root is parent of _internal or where exe is
            exe_dir = Path(sys.executable).parent
            payload_path = exe_dir / "app.pytron"
            if payload_path.exists():
                is_secure = True
                self.logger.info("Secure Build detected. Ready for binary evolution.")

        # If secure and patch exists, use patch
        if is_secure and patch_url:
            self.logger.info(f"Preferring evolution patch: {patch_url}")
            return self._handle_patch_download(patch_url, on_progress)

        if not full_url:
            self.logger.error("No download URL provided in update info.")
            return False

        return self._handle_full_download(full_url, on_progress)

    def _handle_patch_download(self, url, on_progress):
        try:
            exe_dir = Path(sys.executable).parent
            patch_dest = exe_dir / "app.pytron_patch"

            self.logger.info(f"Downloading patch to {patch_dest}...")

            def progress(block_num, block_size, total_size):
                if on_progress:
                    downloaded = block_num * block_size
                    percent = min(100, int((downloaded / total_size) * 100))
                    on_progress(percent)

            urllib.request.urlretrieve(
                url, patch_dest, reporthook=progress
            )  # nosec B310 # nosemgrep
            self.logger.info("Evolution patch downloaded successfully.")

            # Since the Rust loader handles patching on launch, we just need to restart
            self.logger.info("Restarting to apply evolution...")

            if sys.platform == "win32":
                subprocess.Popen(
                    [sys.executable], shell=False, creationflags=0x00000008
                )  # DETACHED_PROCESS # nosec B603
            else:
                subprocess.Popen([sys.executable])  # nosec B603

            sys.exit(0)
            return True
        except Exception as e:
            self.logger.error(f"Failed to download patch: {e}")
            return False

    def _handle_full_download(self, url, on_progress):
        filename = url.split("/")[-1]
        if not filename.endswith(
            (".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".AppImage")
        ):
            filename = (
                "update_installer.exe"
                if sys.platform == "win32"
                else "update_installer"
            )

        download_path = Path(tempfile.gettempdir()) / filename
        try:

            def progress(block_num, block_size, total_size):
                if on_progress:
                    percent = min(100, int((block_num * block_size / total_size) * 100))
                    on_progress(percent)

            urllib.request.urlretrieve(
                url, download_path, reporthook=progress
            )  # nosec B310 # nosemgrep
            self.logger.info(f"Download complete: {download_path}")

            if sys.platform == "win32":
                subprocess.Popen(
                    [str(download_path)], shell=False, creationflags=0x00000008
                )
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(download_path)])
            else:
                os.chmod(download_path, stat.S_IRWXU)
                subprocess.Popen([str(download_path)])

            sys.exit(0)
            return True
        except Exception as e:
            self.logger.error(f"Failed to install full update: {e}")
            return False
