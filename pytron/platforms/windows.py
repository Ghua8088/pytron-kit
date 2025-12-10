import ctypes
from ..bindings import lib
from .interface import PlatformInterface

class WindowsImplementation(PlatformInterface):
    # MAGICAL CONSTANTS
    GWL_STYLE = -16
    WS_CAPTION = 0x00C00000
    WS_THICKFRAME = 0x00040000
    WS_SYSMENU = 0x00080000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000
    WM_NCLBUTTONDOWN = 0xA1
    HTCAPTION = 2
    SW_MINIMIZE = 6
    SW_MAXIMIZE = 3
    SW_RESTORE = 9
    WM_CLOSE = 0x0010
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010

    def _get_hwnd(self, w):
        return lib.webview_get_window(w)

    def minimize(self, w):
        hwnd = self._get_hwnd(w)
        ctypes.windll.user32.ShowWindow(hwnd, self.SW_MINIMIZE)

    def set_bounds(self, w, x, y, width, height):
        hwnd = self._get_hwnd(w)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, int(x), int(y), int(width), int(height), self.SWP_NOZORDER | self.SWP_NOACTIVATE)

    def close(self, w):
        hwnd = self._get_hwnd(w)
        ctypes.windll.user32.PostMessageW(hwnd, self.WM_CLOSE, 0, 0)

    def toggle_maximize(self, w):
        hwnd = self._get_hwnd(w)
        # Check if zoomed
        is_zoomed = ctypes.windll.user32.IsZoomed(hwnd)
        if is_zoomed:
            ctypes.windll.user32.ShowWindow(hwnd, self.SW_RESTORE)
            return False 
        else:
            ctypes.windll.user32.ShowWindow(hwnd, self.SW_MAXIMIZE)
            return True

    def make_frameless(self, w):
        """
        Surgically removes the Windows Titlebar.
        """
        hwnd = self._get_hwnd(w)
        style = ctypes.windll.user32.GetWindowLongW(hwnd, self.GWL_STYLE)
        style = style & ~self.WS_CAPTION
        ctypes.windll.user32.SetWindowLongW(hwnd, self.GWL_STYLE, style)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x0001 | 0x0002 | 0x0004 | 0x0010)

    def start_drag(self, w):
        hwnd = self._get_hwnd(w)
        ctypes.windll.user32.ReleaseCapture()
        ctypes.windll.user32.SendMessageW(hwnd, self.WM_NCLBUTTONDOWN, self.HTCAPTION, 0)
