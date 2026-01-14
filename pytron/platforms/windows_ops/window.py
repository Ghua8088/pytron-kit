import ctypes
import ctypes
try:
    import ctypes.wintypes
except ImportError:
    ctypes.wintypes = None
from .constants import *
from .utils import get_hwnd

# -------------------------------------------------------------------
# Hardened User32
# -------------------------------------------------------------------
# -------------------------------------------------------------------
# Hardened User32
# -------------------------------------------------------------------
try:
    user32 = ctypes.windll.user32
except AttributeError:
    # Non-Windows platform (Linux/macOS) during generic import or tests
    user32 = None


if user32:
    # Function Prototyping (Safe)

    # ShowWindow
    user32.ShowWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = ctypes.wintypes.BOOL

    # SetWindowPos
    user32.SetWindowPos.argtypes = [
        ctypes.wintypes.HWND,
        ctypes.wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.SetWindowPos.restype = ctypes.wintypes.BOOL

    # PostMessageW
    user32.PostMessageW.argtypes = [
        ctypes.wintypes.HWND,
        ctypes.c_uint,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    ]
    user32.PostMessageW.restype = ctypes.wintypes.BOOL

    # IsZoomed
    user32.IsZoomed.argtypes = [ctypes.wintypes.HWND]
    user32.IsZoomed.restype = ctypes.wintypes.BOOL

    # GetWindowLongW
    user32.GetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long

    # SetWindowLongW
    user32.SetWindowLongW.argtypes = [
        ctypes.wintypes.HWND,
        ctypes.c_int,
        ctypes.c_long,
    ]
    user32.SetWindowLongW.restype = ctypes.c_long

    # ReleaseCapture
    user32.ReleaseCapture.argtypes = []
    user32.ReleaseCapture.restype = ctypes.wintypes.BOOL

    # SendMessageW
    user32.SendMessageW.argtypes = [
        ctypes.wintypes.HWND,
        ctypes.c_uint,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    ]
    user32.SendMessageW.restype = ctypes.wintypes.LPARAM

    # IsWindowVisible
    user32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]
    user32.IsWindowVisible.restype = ctypes.wintypes.BOOL

    # SetForegroundWindow
    user32.SetForegroundWindow.argtypes = [ctypes.wintypes.HWND]
    user32.SetForegroundWindow.restype = ctypes.wintypes.BOOL

    # GetWindowRect
    user32.GetWindowRect.argtypes = [
        ctypes.wintypes.HWND,
        ctypes.POINTER(ctypes.wintypes.RECT),
    ]
    user32.GetWindowRect.restype = ctypes.wintypes.BOOL

    # GetSystemMetrics
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int

    # GetWindowLongPtrW - Check if available
    if hasattr(user32, "GetWindowLongPtrW"):
        user32.GetWindowLongPtrW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            user32.GetWindowLongPtrW.restype = ctypes.c_longlong
        else:
            user32.GetWindowLongPtrW.restype = ctypes.c_long

    # SetWindowLongPtrW - Check if available
    if hasattr(user32, "SetWindowLongPtrW"):
        user32.SetWindowLongPtrW.argtypes = [
            ctypes.wintypes.HWND,
            ctypes.c_int,
            ctypes.c_void_p,
        ]
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            user32.SetWindowLongPtrW.restype = ctypes.c_longlong
        else:
            user32.SetWindowLongPtrW.restype = ctypes.c_long

    # CallWindowProcW
    user32.CallWindowProcW.argtypes = [
        ctypes.c_void_p,
        ctypes.wintypes.HWND,
        ctypes.c_uint,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    ]
    user32.CallWindowProcW.restype = ctypes.wintypes.LPARAM

    # DrawMenuBar
    user32.DrawMenuBar.argtypes = [ctypes.wintypes.HWND]
    user32.DrawMenuBar.restype = ctypes.wintypes.BOOL

# -------------------------------------------------------------------
# Operations
# -------------------------------------------------------------------


def minimize(w):
    hwnd = get_hwnd(w)
    if not hwnd:
        return
    user32.ShowWindow(hwnd, SW_MINIMIZE)


def set_bounds(w, x, y, width, height):
    hwnd = get_hwnd(w)
    if not hwnd:
        return
    user32.SetWindowPos(
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
    if not hwnd:
        return
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def toggle_maximize(w):
    hwnd = get_hwnd(w)
    if not hwnd:
        return False
    is_zoomed = user32.IsZoomed(hwnd)
    if is_zoomed:
        user32.ShowWindow(hwnd, SW_RESTORE)
        return False
    else:
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        return True


def make_frameless(w):
    hwnd = get_hwnd(w)
    if not hwnd:
        return
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    style = style & ~WS_CAPTION
    user32.SetWindowLongW(hwnd, GWL_STYLE, style)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x0001 | 0x0002 | 0x0004 | 0x0010)


def start_drag(w):
    hwnd = get_hwnd(w)
    if not hwnd:
        return
    user32.ReleaseCapture()
    user32.SendMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)


def hide(w):
    hwnd = get_hwnd(w)
    if not hwnd:
        return
    user32.ShowWindow(hwnd, SW_HIDE)


def is_visible(w):
    hwnd = get_hwnd(w)
    if not hwnd:
        return False
    return bool(user32.IsWindowVisible(hwnd))


def show(w):
    hwnd = get_hwnd(w)
    if not hwnd:
        return
    user32.ShowWindow(hwnd, SW_SHOW)
    user32.SetForegroundWindow(hwnd)


def center(w):
    hwnd = get_hwnd(w)
    if not hwnd:
        return
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    SM_CXSCREEN, SM_CYSCREEN = 0, 1
    screen_width = user32.GetSystemMetrics(SM_CXSCREEN)
    screen_height = user32.GetSystemMetrics(SM_CYSCREEN)
    x = (screen_width - width) // 2
    y = (screen_height - height) // 2
    user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 0x0001)


# Window Procedure Hooking for Menus
_wnd_procs = {}


def set_menu(w, menu_bar):
    """Attaches a MenuBar to the window and hooks its messages."""
    hwnd = get_hwnd(w)
    if not hwnd:
        return

    h_menu = menu_bar.build_for_windows(hwnd)

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

    # Cast to void ptr for SetWindowLongPtrW
    new_proc_ptr = ctypes.cast(new_proc_inst, ctypes.c_void_p)
    user32.SetWindowLongPtrW(hwnd, GWL_WNDPROC, new_proc_ptr)
    user32.DrawMenuBar(hwnd)
