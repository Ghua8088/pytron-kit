import ctypes
import os
import sys
from .constants import *
from .utils import get_hwnd

try:
    import winreg
except ImportError:
    winreg = None


def notification(w, title, message, icon=None):
    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32

    try:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = get_hwnd(w)
        nid.uID = 2000

        nid.uFlags = NIF_INFO | NIF_ICON | NIF_TIP

        nid.szInfo = message[:255]
        nid.szInfoTitle = title[:63]
        nid.szTip = title[:127] if title else "Notification"
        nid.dwInfoFlags = NIIF_INFO

        h_icon = 0
        if icon and os.path.exists(icon):
            h_icon = user32.LoadImageW(
                0,
                str(icon),
                1,
                16,
                16,
                0x00000010,
            )

        if not h_icon:
            h_icon = user32.LoadIconW(0, 32512)

        nid.hIcon = h_icon

        success = shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        if not success:
            success = shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

        if not success:
            err = ctypes.GetLastError()
            print(f"[Pytron] Notification Failed. Error Code: {err}")
            return

        nid.uVersion = NOTIFYICON_VERSION_4
        shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(nid))

    except Exception as e:
        print(f"[Pytron] Notification Exception: {e}")


def message_box(w, title, message, style=0):
    hwnd = get_hwnd(w)
    return ctypes.windll.user32.MessageBoxW(hwnd, message, title, style)


def set_window_icon(w, icon_path):
    if not icon_path or not os.path.exists(icon_path):
        return
    hwnd = get_hwnd(w)
    try:
        h_small = ctypes.windll.user32.LoadImageW(0, str(icon_path), 1, 16, 16, 0x10)
        if h_small:
            ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, h_small)

        h_big = ctypes.windll.user32.LoadImageW(0, str(icon_path), 1, 32, 32, 0x10)
        if h_big:
            ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, h_big)
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

    filter_str = file_types.replace("|", "\0") + "\0"
    ofn.lpstrFilter = filter_str

    return ofn, buff


def open_file_dialog(w, title, default_path=None, file_types=None):
    ofn, buff = _prepare_ofn(w, title, default_path, file_types)
    ofn.Flags = OFN_EXPLORER | OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR

    if ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
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

    if ctypes.windll.comdlg32.GetSaveFileNameW(ctypes.byref(ofn)):
        return buff.value
    return None


def open_folder_dialog(w, title, default_path=None):
    shell32 = ctypes.windll.shell32

    # We MUST define argtypes and restype for x64 pointer safety
    shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFOW)]
    shell32.SHBrowseForFolderW.restype = ctypes.c_void_p

    shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    shell32.SHGetPathFromIDListW.restype = ctypes.wintypes.BOOL

    shell32.ILFree.argtypes = [ctypes.c_void_p]
    shell32.ILFree.restype = None

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
            # Dev mode: python.exe app.py "%1"
            # Use __main__.__file__ to get the absolute path to the running script
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
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def set_window_icon(w, icon_path):
    """Sets the icon for the specified window."""
    try:
        hwnd = get_hwnd(w)
        if not hwnd or not icon_path or not os.path.exists(icon_path):
            return

        user32 = ctypes.windll.user32

        # Determine if it's an .ico or something else
        # Windows requires HICON, so we use LoadImage
        icon_path = str(os.path.abspath(icon_path))

        # Load small icon (16x16)
        h_icon_small = user32.LoadImageW(
            0,
            icon_path,
            1,
            16,
            16,
            0x00000010 | 0x00000040,  # LR_LOADFROMFILE | LR_DEFAULTSIZE
        )
        # Load large icon (32x32)
        h_icon_large = user32.LoadImageW(
            0, icon_path, 1, 32, 32, 0x00000010 | 0x00000040
        )

        if h_icon_small:
            user32.SendMessageW(hwnd, 0x0080, 0, h_icon_small)  # WM_SETICON, ICON_SMALL
        if h_icon_large:
            user32.SendMessageW(hwnd, 0x0080, 1, h_icon_large)  # WM_SETICON, ICON_BIG

    except Exception as e:
        print(f"[Pytron] Failed to set window icon: {e}")


# Taskbar Progress
_taskbar_list = None


def _init_taskbar():
    global _taskbar_list
    if _taskbar_list:
        return _taskbar_list
    try:
        try:
            ctypes.windll.ole32.CoInitialize(0)
        except:
            pass

        CLSID_TaskbarList = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
        import comtypes.client
        from comtypes import GUID, IUnknown, COMMETHOD, HRESULT

        class ITaskbarList3(IUnknown):
            _iid_ = GUID("{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}")
            _methods_ = [
                # ITaskbarList
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
                # ITaskbarList2
                COMMETHOD(
                    [],
                    HRESULT,
                    "MarkFullscreenWindow",
                    (["in"], ctypes.wintypes.HWND, "hwnd"),
                    (["in"], ctypes.c_int, "fFullscreen"),
                ),
                # ITaskbarList3
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
    except Exception:
        pass


# Clipboard Support (Native Win32 implementation)
def set_clipboard_text(text: str):
    """Copies text to the system clipboard."""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # 1. Open Clipboard
        if not user32.OpenClipboard(0):
            return False

        # 2. Empty Clipboard
        user32.EmptyClipboard()

        # 3. Alloc Memory for UTF-16 text
        # (len + 1 for null terminator) * 2 bytes per char
        text_unicode = text
        size = (len(text_unicode) + 1) * 2
        h_mem = kernel32.GlobalAlloc(0x0042, size)  # GMEM_MOVEABLE | GMEM_ZEROINIT

        # 4. Lock Memory and copy
        p_mem = kernel32.GlobalLock(h_mem)
        ctypes.memmove(p_mem, text_unicode, size)
        kernel32.GlobalUnlock(h_mem)

        # 5. Set Data to Clipboard (CF_UNICODETEXT = 13)
        user32.SetClipboardData(13, h_mem)

        # 6. Close Clipboard
        user32.CloseClipboard()
        return True
    except Exception as e:
        print(f"[Pytron] Clipboard Set Error: {e}")
        return False


def get_clipboard_text():
    """Returns text from the system clipboard."""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        if not user32.OpenClipboard(0):
            return None

        # CF_UNICODETEXT = 13
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
    import psutil  # Note: Added as dynamic check to avoid dependency blowup if not installed

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


# -------------------------------------------------------------------------
# Native Drag & Drop Support - REMOVED AS PER USER REQUEST
# -------------------------------------------------------------------------


def enable_drag_drop_safe(w, callback):
    # Legacy Native Hook - Disabled in favor of JS Bridge
    pass
