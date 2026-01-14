from .interface import PlatformInterface
from .linux_ops import window, system, webview, libs


class LinuxImplementation(PlatformInterface):
    def __init__(self):
        # Libraries are loaded by linux_ops.libs on import
        if not libs.gtk:
            print("Pytron Warning: GTK3 not found. Window controls may fail.")

    def minimize(self, w):
        window.minimize(w)

    def center(self, w):
        window.center(w)

    def set_bounds(self, w, x, y, width, height):
        window.set_bounds(w, x, y, width, height)

    def close(self, w):
        window.close(w)

    def toggle_maximize(self, w):
        return window.toggle_maximize(w)

    def make_frameless(self, w):
        window.make_frameless(w)

    def start_drag(self, w):
        window.start_drag(w)

    def message_box(self, w, title, message, style=0):
        return system.message_box(w, title, message, style)

    def hide(self, w):
        window.hide(w)

    def is_visible(self, w):
        return window.is_visible(w)

    def is_alive(self, w):
        # A simple check for Linux/GTK is to see if the widget still has a window
        win = window.get_window(w)
        return bool(win and win != 0)

    def show(self, w):
        window.show(w)

    def notification(self, w, title, message, icon=None):
        system.notification(w, title, message, icon)

    def open_file_dialog(self, w, title, default_path=None, file_types=None):
        return system.open_file_dialog(w, title, default_path, file_types)

    def save_file_dialog(
        self, w, title, default_path=None, default_name=None, file_types=None
    ):
        return system.save_file_dialog(w, title, default_path, default_name, file_types)

    def open_folder_dialog(self, w, title, default_path=None):
        return system.open_folder_dialog(w, title, default_path)

    def set_taskbar_progress(self, w, state="normal", value=0, max_value=100):
        system.set_taskbar_progress(w, state, value, max_value)

    def set_window_icon(self, w, icon_path):
        window.set_window_icon(w, icon_path)

    def set_app_id(self, app_id):
        system.set_app_id(app_id)

    def set_launch_on_boot(self, app_name, exe_path, enable=True):
        return system.set_launch_on_boot(app_name, exe_path, enable)

    def register_protocol(self, scheme):
        return system.register_protocol(scheme)
