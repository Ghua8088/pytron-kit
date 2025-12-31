import json
import logging
import sys
from ..interface import PlatformInterface

# _pytron_android is expected to be a built-in module provided by the C++ JNI layer.
try:
    import _pytron_android
except ImportError:
    _pytron_android = None


class AndroidImplementation(PlatformInterface):
    def __init__(self):
        self.logger = logging.getLogger("Pytron.Android")
        if not _pytron_android:
            self.logger.warning(
                "_pytron_android module not found. This platform implementation requires running inside the Android shell."
            )

    def _send(self, method, **kwargs):
        """
        Send a message to the Java/Kotlin layer via the JNI bridge.
        """
        if _pytron_android:
            payload = json.dumps({"method": method, "args": kwargs})
            # This function is defined in the C++ JNI Bridge
            return _pytron_android.send_to_android(payload)
        else:
            self.logger.debug(f"[Android Mock] Call: {method} Args: {kwargs}")
            return None

    def minimize(self, w):
        self._send("minimize")

    def set_bounds(self, w, x, y, width, height):
        # On Android, windows are usually full screen activities, but we can support resizing if in multi-window mode or PiP
        self._send("set_bounds", x=x, y=y, width=width, height=height)

    def close(self, w):
        self._send("close")

    def toggle_maximize(self, w):
        self._send("toggle_maximize")
        return True

    def make_frameless(self, w):
        self._send("make_frameless")

    def start_drag(self, w):
        self._send("start_drag")

    def message_box(self, w, title, message, style=0):
        # Assuming the JNI call 'send_to_android' can return values if we implement it to wait.
        # We will assume it returns a serialized JSON string or primitive for blocking calls.
        ret = self._send("message_box", title=title, message=message, style=style)
        return int(ret) if ret is not None else 6

    def notification(self, w, title, message, icon=None):
        self._send("notification", title=title, message=message, icon=icon)

    def hide(self, w):
        self._send("hide")

    def show(self, w):
        self._send("show")

    def set_window_icon(self, w, icon_path):
        self._send("set_window_icon", path=icon_path)

    def set_app_id(self, app_id):
        self._send("set_app_id", app_id=app_id)

    # Dialogs
    def open_file_dialog(self, w, title, default_path=None, file_types=None):
        res = self._send(
            "open_file_dialog",
            title=title,
            default_path=default_path,
            file_types=file_types,
        )
        if res:
            return json.loads(res)
        return None

    def save_file_dialog(
        self, w, title, default_path=None, default_name=None, file_types=None
    ):
        res = self._send(
            "save_file_dialog",
            title=title,
            default_path=default_path,
            default_name=default_name,
            file_types=file_types,
        )
        if res:
            return json.loads(res)
        return None

    def open_folder_dialog(self, w, title, default_path=None):
        res = self._send("open_folder_dialog", title=title, default_path=default_path)
        if res:
            return json.loads(res)
        return None
