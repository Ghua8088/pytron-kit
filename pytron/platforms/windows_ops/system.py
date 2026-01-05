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
        h_small = ctypes.windll.user32.LoadImageW(
            0, str(icon_path), 1, 16, 16, 0x10
        )
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
    ofn.Flags = (
        OFN_EXPLORER
        | OFN_FILEMUSTEXIST
        | OFN_PATHMUSTEXIST
        | OFN_NOCHANGEDIR
    )

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
    ofn.Flags = (
        OFN_EXPLORER
        | OFN_OVERWRITEPROMPT
        | OFN_PATHMUSTEXIST
        | OFN_NOCHANGEDIR
    )

    if ctypes.windll.comdlg32.GetSaveFileNameW(ctypes.byref(ofn)):
        return buff.value
    return None

def open_folder_dialog(w, title, default_path=None):
    bif = BROWSEINFOW()
    bif.hwndOwner = get_hwnd(w)
    bif.lpszTitle = title
    bif.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE

    pidl = ctypes.windll.shell32.SHBrowseForFolderW(ctypes.byref(bif))
    if pidl:
        path = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetPathFromIDListW(pidl, path):
            ctypes.windll.shell32.ILFree(ctypes.c_void_p(pidl))
            return path.value
        ctypes.windll.shell32.ILFree(ctypes.c_void_p(pidl))
    return None

def register_protocol(scheme):
    if not winreg:
        return False
    try:
        exe = sys.executable
        command = f'"{exe}" "%1"'
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
                COMMETHOD([], HRESULT, "AddTab", (["in"], ctypes.wintypes.HWND, "hwnd")),
                COMMETHOD([], HRESULT, "DeleteTab", (["in"], ctypes.wintypes.HWND, "hwnd")),
                COMMETHOD([], HRESULT, "ActivateTab", (["in"], ctypes.wintypes.HWND, "hwnd")),
                COMMETHOD([], HRESULT, "SetActiveAlt", (["in"], ctypes.wintypes.HWND, "hwnd")),
                # ITaskbarList2
                COMMETHOD([], HRESULT, "MarkFullscreenWindow", (["in"], ctypes.wintypes.HWND, "hwnd"), (["in"], ctypes.c_int, "fFullscreen")),
                # ITaskbarList3
                COMMETHOD([], HRESULT, "SetProgressValue", (["in"], ctypes.wintypes.HWND, "hwnd"), (["in"], ctypes.c_ulonglong, "ullCompleted"), (["in"], ctypes.c_ulonglong, "ullTotal")),
                COMMETHOD([], HRESULT, "SetProgressState", (["in"], ctypes.wintypes.HWND, "hwnd"), (["in"], ctypes.c_int, "tbpFlags")),
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
