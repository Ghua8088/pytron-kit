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
    ctypes.windll.user32.SendMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)


def hide(w):
    hwnd = get_hwnd(w)
    ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)


def is_visible(w):
    hwnd = get_hwnd(w)
    return bool(ctypes.windll.user32.IsWindowVisible(hwnd))


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


# Window Procedure Hooking for Menus
_wnd_procs = {}


def set_menu(w, menu_bar):
    """Attaches a MenuBar to the window and hooks its messages."""
    hwnd = get_hwnd(w)
    if not hwnd:
        return

    h_menu = menu_bar.build_for_windows(hwnd)

    # Subclass window to catch WM_COMMAND
    user32 = ctypes.windll.user32
    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_longlong,
        ctypes.wintypes.HWND,
        ctypes.wintypes.UINT,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    )

    # Get original proc
    from .constants import GWL_WNDPROC, WM_COMMAND

    old_proc = user32.GetWindowLongPtrW(hwnd, GWL_WNDPROC)

    def new_wnd_proc(hwnd_in, msg, wparam, lparam):
        if msg == WM_COMMAND:
            # Low word of wparam is the menu ID
            cmd_id = wparam & 0xFFFF
            if menu_bar.handle_command(cmd_id):
                return 0

        return user32.CallWindowProcW(old_proc, hwnd_in, msg, wparam, lparam)

    # Keep reference to prevent GC
    new_proc_inst = WNDPROC(new_wnd_proc)
    _wnd_procs[hwnd] = (new_proc_inst, old_proc)

    user32.SetWindowLongPtrW(hwnd, GWL_WNDPROC, new_proc_inst)
    user32.DrawMenuBar(hwnd)
