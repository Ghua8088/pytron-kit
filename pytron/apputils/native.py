import sys
import os
from typing import Optional

class NativeMixin:
    """
    Mixin class to handle native system interactions.
    """
    def set_start_on_boot(self, enable=True):
        """
        Enables or disables automatic application startup on system boot.
        """
        app_name = self.config.get("title", "PytronApp")
        # Sanitize for registry key
        safe_name = "".join(c if c.isalnum() else "_" for c in app_name)

        exe_path = sys.executable
        if not getattr(sys, "frozen", False):
            # Development mode: python.exe "path/to/script.py"
            # This is tricky because we need arguments.
            # Windows registry Run key handles arguments fine.
            main_script = os.path.abspath(sys.argv[0])
            exe_path = f'"{sys.executable}" "{main_script}"'
        else:
            exe_path = f'"{exe_path}"'  # Quote for safety

        # We need a platform instance.
        # Since App doesn't hold it, we instantiate temporarily or grab from first window
        if self.windows:
            # Best effort
            try:
                return self.windows[0]._platform.set_launch_on_boot(
                    safe_name, exe_path, enable
                )
            except Exception:
                pass

        # Fallback if no window yet or needed
        try:
            import platform

            if platform.system() == "Windows":
                from ..platforms.windows import WindowsImplementation

                return WindowsImplementation().set_launch_on_boot(
                    safe_name, exe_path, enable
                )
        except Exception as e:
            self.logger.warning(f"Could not set start on boot: {e}")

    def message_box(self, title, message, style=0):
        """
        Shows a native message box.
        Styles: 0=OK, 1=OK/Cancel, 2=Abort/Retry/Ignore, 3=Yes/No/Cancel, 4=Yes/No, 5=Retry/Cancel
        Returns: 1=OK, 2=Cancel, 6=Yes, 7=No
        """
        if self.windows:
            return self.windows[0].message_box(title, message, style)
        return 0

    def dialog_save_file(
        self, title="Save File", default_path=None, default_name=None, file_types=None
    ):
        """Opens a native save file dialog. Returns the selected path or None."""
        if self.windows:
            return self.windows[0].dialog_save_file(
                title, default_path, default_name, file_types
            )
        return None

    def dialog_open_file(self, title="Open File", default_path=None, file_types=None):
        """Opens a native file selection dialog. Returns the selected path or None."""
        if self.windows:
            return self.windows[0].dialog_open_file(title, default_path, file_types)
        return None

    def dialog_open_folder(self, title="Select Folder", default_path=None):
        """Opens a native folder selection dialog. Returns the selected path or None."""
        if self.windows:
            return self.windows[0].dialog_open_folder(title, default_path)
        return None

    def system_notification(self, title: Optional[str] = None, message: str = ""):
        """Sends a system-level (tray/toast) notification via the OS."""
        if not title:
            title = self.config.get("author", self.config.get("title", "Pytron"))

        icon = self.config.get("icon")

        if self.windows:
            for window in self.windows:
                try:
                    window.system_notification(title, message, icon=icon)
                    break
                except Exception:
                    pass
