import ctypes

try:
    import ctypes.wintypes
except ImportError:

    class MockWintypes:
        HWND = ctypes.c_void_p
        BOOL = ctypes.c_int

    ctypes.wintypes = MockWintypes
from .interface import PlatformInterface
from .windows_ops import window, system, webview


class WindowsImplementation(PlatformInterface):
    def __init__(self):
        # Harden High-DPI loading
        try:
            shcore = ctypes.windll.shcore
            shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
            shcore.SetProcessDpiAwareness.restype = ctypes.c_long
            shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                user32 = ctypes.windll.user32
                user32.SetProcessDPIAware.argtypes = []
                user32.SetProcessDPIAware.restype = ctypes.wintypes.BOOL
                user32.SetProcessDPIAware()
            except Exception:
                pass

        self._protocol_handler = None
        self._webview_env = None

    def notification(self, w, title, message, icon=None):
        system.notification(w, title, message, icon)

    def minimize(self, w):
        window.minimize(w)

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

    def set_fullscreen(self, w, fullscreen):
        window.set_fullscreen(w, fullscreen)

    def set_always_on_top(self, w, enable):
        window.set_always_on_top(w, enable)

    def hide(self, w):
        window.hide(w)

    def is_visible(self, w):
        return window.is_visible(w)

    def is_alive(self, w):
        hwnd = self.get_hwnd(w)
        # Harden IsWindow check
        if not hwnd:
            return False

        try:
            # IsWindow takes HWND, returns BOOL (int)
            user32 = ctypes.windll.user32
            user32.IsWindow.argtypes = [ctypes.wintypes.HWND]
            user32.IsWindow.restype = ctypes.wintypes.BOOL
            return bool(user32.IsWindow(hwnd))
        except (AttributeError, ValueError):
            return False

    def show(self, w):
        window.show(w)

    def set_window_icon(self, w, icon_path):
        system.set_window_icon(w, icon_path)

    def open_file_dialog(self, w, title, default_path=None, file_types=None):
        return system.open_file_dialog(w, title, default_path, file_types)

    def save_file_dialog(
        self, w, title, default_path=None, default_name=None, file_types=None
    ):
        return system.save_file_dialog(w, title, default_path, default_name, file_types)

    def open_folder_dialog(self, w, title, default_path=None):
        return system.open_folder_dialog(w, title, default_path)

    def register_protocol(self, scheme):
        return system.register_protocol(scheme)

    def register_pytron_scheme(self, w, callback):
        return webview.register_pytron_scheme(w, callback)

    def set_taskbar_progress(self, w, state="normal", value=0, max_value=100):
        try:
            system.set_taskbar_progress(w, state, value, max_value)
        except Exception:
            # Taskbar progress is non-critical, fail silently if COM/HWND issues occur
            pass

    def set_app_id(self, app_id):
        system.set_app_id(app_id)

    def center(self, w):
        window.center(w)

    def set_launch_on_boot(self, app_name, exe_path, enable=True):
        return system.set_launch_on_boot(app_name, exe_path, enable)

    def set_clipboard_text(self, text):
        return system.set_clipboard_text(text)

    def get_clipboard_text(self):
        return system.get_clipboard_text()

    def get_system_info(self):
        return system.get_system_info()

    def set_menu(self, w, menu_bar):
        window.set_menu(w, menu_bar)
