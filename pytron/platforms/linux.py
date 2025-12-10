import ctypes
from ..bindings import lib
from .interface import PlatformInterface

class LinuxImplementation(PlatformInterface):
    def __init__(self):
        try:
            self.gtk = ctypes.CDLL("libgtk-3.so.0")
        except OSError:
            try:
                self.gtk = ctypes.CDLL("libgtk-3.so")
            except OSError:
                 # Fallback or silent failure if GTK not present
                 print("Pytron Warning: GTK3 not found. Window controls may fail.")
                 self.gtk = None

    def _get_window(self, w):
        return lib.webview_get_window(w)

    def minimize(self, w):
        if not self.gtk: return
        win = self._get_window(w)
        self.gtk.gtk_window_iconify(win)

    def set_bounds(self, w, x, y, width, height):
        if not self.gtk: return
        win = self._get_window(w)
        self.gtk.gtk_window_move(win, int(x), int(y))
        self.gtk.gtk_window_resize(win, int(width), int(height))

    def close(self, w):
        if not self.gtk: return
        win = self._get_window(w)
        self.gtk.gtk_window_close(win)

    def toggle_maximize(self, w):
        if not self.gtk: return False
        win = self._get_window(w)
        is_maximized = self.gtk.gtk_window_is_maximized(win)
        if is_maximized:
            self.gtk.gtk_window_unmaximize(win)
            return False
        else:
            self.gtk.gtk_window_maximize(win)
            return True

    def make_frameless(self, w):
        if not self.gtk: return
        win = self._get_window(w)
        self.gtk.gtk_window_set_decorated(win, 0) # FALSE

    def start_drag(self, w):
        if not self.gtk: return
        win = self._get_window(w)
        # 1 = GDK_BUTTON_PRIMARY_MASK (approx), sometimes 0 works for timestamps
        self.gtk.gtk_window_begin_move_drag(win, 1, 0, 0)
