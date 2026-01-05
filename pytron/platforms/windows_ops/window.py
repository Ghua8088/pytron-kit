import ctypes
import ctypes.wintypes
from .constants import *
from .utils import get_hwnd

def minimize(w):
    hwnd = get_hwnd(w)
    ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)

def set_bounds(w, x, y, width, height):
    hwnd = get_hwnd(w)
    ctypes.windll.user32.SetWindowPos(
        hwnd,
        0,
        int(x),
        int(y),
        int(width),
        int(height),
        SWP_NOZORDER | SWP_NOACTIVATE,
    )

def close(w):
    hwnd = get_hwnd(w)
    ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

def toggle_maximize(w):
    hwnd = get_hwnd(w)
    is_zoomed = ctypes.windll.user32.IsZoomed(hwnd)
    if is_zoomed:
        ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
        return False
    else:
        ctypes.windll.user32.ShowWindow(hwnd, SW_MAXIMIZE)
        return True

def make_frameless(w):
    hwnd = get_hwnd(w)
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
    style = style & ~WS_CAPTION
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)
    ctypes.windll.user32.SetWindowPos(
        hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x0001 | 0x0002 | 0x0004 | 0x0010
    )

def start_drag(w):
    hwnd = get_hwnd(w)
    ctypes.windll.user32.ReleaseCapture()
    ctypes.windll.user32.SendMessageW(
        hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0
    )

def hide(w):
    hwnd = get_hwnd(w)
    ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)

def show(w):
    hwnd = get_hwnd(w)
    ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW)
    ctypes.windll.user32.SetForegroundWindow(hwnd)

def center(w):
    hwnd = get_hwnd(w)
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    SM_CXSCREEN, SM_CYSCREEN = 0, 1
    screen_width = ctypes.windll.user32.GetSystemMetrics(SM_CXSCREEN)
    screen_height = ctypes.windll.user32.GetSystemMetrics(SM_CYSCREEN)
    x = (screen_width - width) // 2
    y = (screen_height - height) // 2
    ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 0x0001)
