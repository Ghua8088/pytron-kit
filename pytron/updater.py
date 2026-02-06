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
from .exceptions import UpdateError


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
        """
        if not getattr(sys, "frozen", False):
            self.logger.debug("Skipping update check in development mode.")
            return None
        self.logger.info(f"Checking for updates at {url}...")
        try:
            if not url.startswith("https://"):
                raise ValueError("Updater only supports HTTPS")

            # nosemgrep
            with urllib.request.urlopen(url, timeout=5) as response:  # nosec B310
                data = json.loads(response.read().decode())
                remote_version = data.get("version")

                if not remote_version:
                    raise UpdateError(f"Invalid update manifest at {url}: missing 'version' field.")

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
            raise UpdateError(f"Network error while checking for updates: {e}") from e
        except Exception as e:
            if isinstance(e, UpdateError):
                raise
            raise UpdateError(f"Unexpected error during update check: {e}") from e

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

            # nosemgrep
            urllib.request.urlretrieve(
                url, patch_dest, reporthook=progress
            )  # nosec B310
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

            # nosemgrep
            urllib.request.urlretrieve(
                url, download_path, reporthook=progress
            )  # nosec B310
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
