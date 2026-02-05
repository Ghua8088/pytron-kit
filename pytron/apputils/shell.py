import os
import subprocess
import platform

import shutil


class Shell:
    """
    Native OS Shell utilities for Pytron.
    """

    @staticmethod
    def _resolve_bin(bin_name):
        return shutil.which(bin_name) or bin_name

    @staticmethod
    def open_external(url: str):
        """
        Opens a URL or file path in the default system browser/handler.
        """
        if platform.system() == "Windows":
            os.startfile(url)
        elif platform.system() == "Darwin":
            bin_path = Shell._resolve_bin("open")
            subprocess.run([bin_path, url])
        else:
            bin_path = Shell._resolve_bin("xdg-open")
            subprocess.run([bin_path, url])

    @staticmethod
    def show_item_in_folder(path: str):
        """
        Opens the folder containing the file and selects it.
        """
        path = os.path.abspath(path)
        if platform.system() == "Windows":
            bin_path = Shell._resolve_bin("explorer")
            subprocess.run([bin_path, "/select,", path])
        elif platform.system() == "Darwin":
            bin_path = Shell._resolve_bin("open")
            subprocess.run([bin_path, "-R", path])
        else:
            # Linux doesn't have a universal 'select' but we can open the dir
            bin_path = Shell._resolve_bin("xdg-open")
            subprocess.run([bin_path, os.path.dirname(path)])

    @staticmethod
    def trash_item(path: str):
        """
        Moves a file to the system trash/recycle bin.
        Requires 'send2trash' library if available, else fails.
        """
        try:
            import logging

            logger = logging.getLogger("Pytron.Shell")
            from send2trash import send2trash

            send2trash(path)
            return True
        except ImportError:
            import logging

            logging.getLogger("Pytron.Shell").warning(
                "send2trash is not installed. File cannot be moved to trash."
            )
            return False
        except Exception as e:
            import logging

            logging.getLogger("Pytron.Shell").error(f"Failed to trash item: {e}")
            return False
