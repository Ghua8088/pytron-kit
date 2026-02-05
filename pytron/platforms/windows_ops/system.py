import ctypes
import os
import sys
from .constants import *
from .utils import get_hwnd

try:
    import winreg
except ImportError:
    winreg = None

try:
    import ctypes.wintypes
except ImportError:
    # Safe fallback for non-Windows imports
    class MockWintypes:
        HWND = ctypes.c_void_p
        BOOL = ctypes.c_int
        WPARAM = ctypes.c_void_p
        LPARAM = ctypes.c_void_p
        RECT = ctypes.c_void_p

    ctypes.wintypes = MockWintypes

# -------------------------------------------------------------------
# Hardened Library Wrappers
# -------------------------------------------------------------------
try:
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32
    comdlg32 = ctypes.windll.comdlg32
except AttributeError:
    # Non-Windows Platform
    user32 = None
    shell32 = None
    kernel32 = None
    comdlg32 = None


if user32 and shell32 and kernel32 and comdlg32:
    # --- USER32 ---
    user32.LoadImageW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.LoadImageW.restype = ctypes.c_void_p  # HANDLE

    user32.LoadIconW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]  # Used with ID
    user32.LoadIconW.restype = ctypes.c_void_p

    user32.MessageBoxW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint,
    ]
    user32.MessageBoxW.restype = ctypes.c_int

    user32.SendMessageW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    ]
    user32.SendMessageW.restype = ctypes.c_longlong  # LRESULT can be 64-bit

    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.wintypes.BOOL

    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = ctypes.wintypes.BOOL

    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p

    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = ctypes.wintypes.BOOL

    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = ctypes.c_void_p

    # --- SHELL32 ---
    shell32.Shell_NotifyIconW.argtypes = [
        ctypes.c_ulong,
        ctypes.POINTER(NOTIFYICONDATAW),
    ]
    shell32.Shell_NotifyIconW.restype = ctypes.wintypes.BOOL

    shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
    shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long  # HRESULT

    shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFOW)]
    shell32.SHBrowseForFolderW.restype = ctypes.c_void_p  # PIDLIST_ABSOLUTE

    shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    shell32.SHGetPathFromIDListW.restype = ctypes.wintypes.BOOL

    shell32.ILFree.argtypes = [ctypes.c_void_p]
    shell32.ILFree.restype = None

    # --- KERNEL32 ---
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p

    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p

    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.wintypes.BOOL

    # --- COMDLG32 ---
    comdlg32.GetOpenFileNameW.argtypes = [ctypes.POINTER(OPENFILENAMEW)]
    comdlg32.GetOpenFileNameW.restype = ctypes.wintypes.BOOL

    comdlg32.GetSaveFileNameW.argtypes = [ctypes.POINTER(OPENFILENAMEW)]
    comdlg32.GetSaveFileNameW.restype = ctypes.wintypes.BOOL

# -------------------------------------------------------------------
# Operations
# -------------------------------------------------------------------


def notification(w, title, message, icon=None):
    try:
        hwnd = get_hwnd(w)
        # Even if hwnd is None (e.g. hidden mode), we might need a dummy HWND for the tray api.
        # However, linking it to the main webview HWND is standard.
        if not hwnd:
            print(f"[Pytron] Notification skipped: No valid HWND for window {w}")
            return

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 2000  # Unique ID for "Toast" source

        # 1. Ensure Icon is Valid
        h_icon = 0
        if icon and os.path.exists(icon):
            h_icon = user32.LoadImageW(None, str(icon), 1, 16, 16, 0x00000010)
        if not h_icon:
            h_icon = user32.LoadIconW(None, ctypes.c_void_p(32512))  # IDI_APPLICATION

        nid.hIcon = h_icon

        # 2. Strict ctypes definition (Local Override similar to tray.py)
        shell32.Shell_NotifyIconW.argtypes = [
            ctypes.c_ulong,
            ctypes.POINTER(NOTIFYICONDATAW),
        ]
        shell32.Shell_NotifyIconW.restype = ctypes.wintypes.BOOL

        # 3. ADD the Icon first (if not exists)
        # We need NIF_ICON so it exists. We assume it might already exist.
        nid.uFlags = NIF_ICON | NIF_TIP
        nid.szTip = title[:127] if title else "Notification"

        # Try ADD. If it fails, it might already exist, so we treat it as success-ish
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

        # 4. Set Version to 4 (Vista+) to enable modern "Balloon/Toast" behavior
        nid.uVersion = NOTIFYICON_VERSION_4
        shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(nid))

        # 5. Show The Toast (MODIFY)
        nid.uFlags = NIF_INFO | NIF_ICON | NIF_TIP
        nid.szInfo = message[:255]
        nid.szInfoTitle = title[:63]
        nid.dwInfoFlags = NIIF_INFO  # | NIIF_LARGE_ICON if we had a large icon

        success = shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

        if not success:
            err = ctypes.get_last_error()
            print(f"[Pytron] Notification Failed. Error Code: {err}")

    except Exception as e:
        print(f"[Pytron] Notification Exception: {e}")


def message_box(w, title, message, style=0):
    hwnd = get_hwnd(w)
    return user32.MessageBoxW(hwnd, message, title, style)


def set_window_icon(w, icon_path):
    if not icon_path or not os.path.exists(icon_path):
        return
    hwnd = get_hwnd(w)
    try:
        # LR_LOADFROMFILE | LR_DEFAULTSIZE
        flags = 0x00000010 | 0x00000040

        h_small = user32.LoadImageW(None, str(icon_path), 1, 16, 16, flags)
        if h_small:
            user32.SendMessageW(hwnd, 0x0080, 0, h_small)  # WM_SETICON, ICON_SMALL

        h_big = user32.LoadImageW(None, str(icon_path), 1, 32, 32, flags)
        if h_big:
            user32.SendMessageW(hwnd, 0x0080, 1, h_big)  # WM_SETICON, ICON_BIG
    except Exception as e:
        print(f"Icon error: {e}")


def _prepare_ofn(w, title, default_path, file_types, file_buffer_size=1024):
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = get_hwnd(w)

    buff = ctypes.create_unicode_buffer(file_buffer_size)
    ofn.lpstrFile = ctypes.addressof(buff)
    ofn.nMaxFile = file_buffer_size

    if title:
        ofn.lpstrTitle = title

    if default_path:
        if os.path.isfile(default_path):
            d = os.path.dirname(default_path)
            n = os.path.basename(default_path)
            ofn.lpstrInitialDir = d
            buff.value = n
        else:
            ofn.lpstrInitialDir = default_path

    if not file_types:
        file_types = "All Files (*.*)|*.*"

    if isinstance(file_types, (list, tuple)):
        # Convert list of tuples [("Name", "*.ext"), ...] to "Name|*.ext|..."
        # Or if it's a list of strings ["Name|*.ext", ...], just join them.
        ft_parts = []
        for ft in file_types:
            if isinstance(ft, (list, tuple)) and len(ft) >= 2:
                # Ensure the description doesn't contain pipes, though patterns might
                ft_parts.append(f"{ft[0]}|{ft[1]}")
            else:
                ft_parts.append(str(ft))
        file_types = "|".join(ft_parts)

    filter_str = file_types.replace("|", "\0") + "\0"
    ofn.lpstrFilter = filter_str

    return ofn, buff


def open_file_dialog(w, title, default_path=None, file_types=None):
    ofn, buff = _prepare_ofn(w, title, default_path, file_types)
    ofn.Flags = OFN_EXPLORER | OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR

    if comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
        return buff.value
    return None


def save_file_dialog(w, title, default_path=None, default_name=None, file_types=None):
    path = default_path
    if default_name:
        if path:
            path = os.path.join(path, default_name)
        else:
            path = default_name

    ofn, buff = _prepare_ofn(w, title, path, file_types)
    ofn.Flags = OFN_EXPLORER | OFN_OVERWRITEPROMPT | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR

    if comdlg32.GetSaveFileNameW(ctypes.byref(ofn)):
        return buff.value
    return None


def open_folder_dialog(w, title, default_path=None):
    bif = BROWSEINFOW()
    bif.hwndOwner = get_hwnd(w)
    bif.lpszTitle = title
    bif.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE

    pidl = shell32.SHBrowseForFolderW(ctypes.byref(bif))
    if pidl:
        path = ctypes.create_unicode_buffer(260)
        if shell32.SHGetPathFromIDListW(pidl, path):
            shell32.ILFree(pidl)
            return path.value
        shell32.ILFree(pidl)
    return None


def register_protocol(scheme):
    if not winreg:
        return False
    try:
        exe = sys.executable
        if getattr(sys, "frozen", False):
            command = f'"{exe}" "%1"'
        else:
            main_file = os.path.abspath(sys.modules["__main__"].__file__)
            command = f'"{exe}" "{main_file}" "%1"'

        key_path = f"Software\\Classes\\{scheme}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f"URL:{scheme} Protocol")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, f"{key_path}\\shell\\open\\command"
        ) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
        return True
    except Exception:
        return False


def set_launch_on_boot(app_name, exe_path, enable=True):
    if not winreg:
        return False
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            key_path,
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
        ) as key:
            if enable:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


def set_app_id(app_id):
    try:
        shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception as e:
        print(f"[Pytron] Debug: Failed to set app model ID: {e}")


# Taskbar Progress (Using COM - Requires valid ITaskbarList3 definition)
# For robustness, we catch exceptions but don't strictly type COM interfaces here
# as that requires a larger struct definition block which is already present but complex.
_taskbar_list = None


def _init_taskbar():
    global _taskbar_list
    if _taskbar_list:
        return _taskbar_list
    try:
        try:
            if hasattr(ctypes, "windll"):
                ctypes.windll.ole32.CoInitialize(0)
        except Exception as e:
            print(f"[Pytron] Debug: Failed to initialize COM: {e}")
            return None

        CLSID_TaskbarList = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
        import comtypes.client
        from comtypes import GUID, IUnknown, COMMETHOD, HRESULT

        class ITaskbarList3(IUnknown):
            _iid_ = GUID("{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}")
            _methods_ = [
                COMMETHOD([], HRESULT, "HrInit"),
                COMMETHOD(
                    [], HRESULT, "AddTab", (["in"], ctypes.wintypes.HWND, "hwnd")
                ),
                COMMETHOD(
                    [], HRESULT, "DeleteTab", (["in"], ctypes.wintypes.HWND, "hwnd")
                ),
                COMMETHOD(
                    [], HRESULT, "ActivateTab", (["in"], ctypes.wintypes.HWND, "hwnd")
                ),
                COMMETHOD(
                    [], HRESULT, "SetActiveAlt", (["in"], ctypes.wintypes.HWND, "hwnd")
                ),
                COMMETHOD(
                    [],
                    HRESULT,
                    "MarkFullscreenWindow",
                    (["in"], ctypes.wintypes.HWND, "hwnd"),
                    (["in"], ctypes.c_int, "fFullscreen"),
                ),
                COMMETHOD(
                    [],
                    HRESULT,
                    "SetProgressValue",
                    (["in"], ctypes.wintypes.HWND, "hwnd"),
                    (["in"], ctypes.c_ulonglong, "ullCompleted"),
                    (["in"], ctypes.c_ulonglong, "ullTotal"),
                ),
                COMMETHOD(
                    [],
                    HRESULT,
                    "SetProgressState",
                    (["in"], ctypes.wintypes.HWND, "hwnd"),
                    (["in"], ctypes.c_int, "tbpFlags"),
                ),
            ]

        _taskbar_list = comtypes.client.CreateObject(
            CLSID_TaskbarList, interface=ITaskbarList3
        )
        _taskbar_list.HrInit()
        return _taskbar_list
    except Exception as e:
        print(f"[Pytron] Taskbar Init Failed: {e}")
        return None


def set_taskbar_progress(w, state="normal", value=0, max_value=100):
    try:
        tbl = _init_taskbar()
        if not tbl:
            return
        hwnd = get_hwnd(w)
        flags = TBPF_NOPROGRESS
        if state == "indeterminate":
            flags = TBPF_INDETERMINATE
        elif state == "normal":
            flags = TBPF_NORMAL
        elif state == "error":
            flags = TBPF_ERROR
        elif state == "paused":
            flags = TBPF_PAUSED
        tbl.SetProgressState(hwnd, flags)
        if state in ("normal", "error", "paused"):
            tbl.SetProgressValue(hwnd, int(value), int(max_value))
    except Exception as e:
        print(f"[Pytron] Taskbar progress error: {e}")


def set_clipboard_text(text: str):
    """Copies text to the system clipboard."""
    if not user32:
        return False
    try:
        if not user32.OpenClipboard(0):
            return False

        user32.EmptyClipboard()

        text_unicode = text
        size = (len(text_unicode) + 1) * 2
        h_mem = kernel32.GlobalAlloc(0x0042, size)  # GMEM_MOVEABLE | GMEM_ZEROINIT

        p_mem = kernel32.GlobalLock(h_mem)
        ctypes.memmove(p_mem, text_unicode, size)
        kernel32.GlobalUnlock(h_mem)

        user32.SetClipboardData(13, h_mem)  # CF_UNICODETEXT
        user32.CloseClipboard()
        return True
    except Exception as e:
        print(f"[Pytron] Clipboard Set Error: {e}")
        return False


def get_clipboard_text():
    """Returns text from the system clipboard."""
    if not user32:
        return None
    try:
        if not user32.OpenClipboard(0):
            return None

        h_mem = user32.GetClipboardData(13)
        if not h_mem:
            user32.CloseClipboard()
            return None

        p_mem = kernel32.GlobalLock(h_mem)
        text = ctypes.c_wchar_p(p_mem).value
        kernel32.GlobalUnlock(p_mem)

        user32.CloseClipboard()
        return text
    except Exception as e:
        print(f"[Pytron] Clipboard Get Error: {e}")
        return None


def get_system_info():
    """Returns platform core information."""
    import platform

    info = {
        "os": platform.system(),
        "arch": platform.machine(),
        "release": platform.release(),
        "version": platform.version(),
        "cpu_count": os.cpu_count(),
    }

    try:
        import psutil

        mem = psutil.virtual_memory()
        info["ram_total"] = mem.total
        info["ram_available"] = mem.available
        info["cpu_usage"] = psutil.cpu_percent(interval=None)
    except ImportError:
        pass

    return info


def enable_drag_drop_safe(w, callback):
    # Legacy Native Hook - Disabled in favor of JS Bridge
    pass
