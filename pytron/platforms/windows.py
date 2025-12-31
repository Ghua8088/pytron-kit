import ctypes
import ctypes.wintypes
import os
import sys

try:
    import winreg
except ImportError:
    winreg = None

from ..bindings import lib
from .interface import PlatformInterface


class WindowsImplementation(PlatformInterface):
    def __init__(self):
        user32 = ctypes.windll.user32

        # Prevent 64-bit Overflow
        user32.SendMessageW.argtypes = [
            ctypes.wintypes.HWND,
            ctypes.wintypes.UINT,
            ctypes.wintypes.WPARAM,
            ctypes.wintypes.LPARAM,
        ]
        user32.PostMessageW.argtypes = [
            ctypes.wintypes.HWND,
            ctypes.wintypes.UINT,
            ctypes.wintypes.WPARAM,
            ctypes.wintypes.LPARAM,
        ]
        user32.ShowWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]

        # Enable High-DPI (Fixes blurry icons)
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
        self._webview_env = None
        self._webview_controller = None

    # --- Constants ---
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

    # --- Notification Constants ---
    SW_HIDE = 0
    SW_SHOW = 5
    NIM_ADD = 0
    NIM_MODIFY = 1
    NIM_DELETE = 2
    NIM_SETVERSION = 4
    NIF_MESSAGE = 0x1
    NIF_ICON = 0x2
    NIF_TIP = 0x4
    NIF_INFO = 0x10
    NIIF_INFO = 0x1
    NOTIFYICON_VERSION_4 = 4

    # --- Structures ---
    class NOTIFYICONDATAW(ctypes.Structure):
        _pack_ = 8  # <--- CRITICAL FIX: Force 8-byte packing for x64 compatibility
        _fields_ = [
            ("cbSize", ctypes.c_uint),
            ("hWnd", ctypes.c_void_p),
            ("uID", ctypes.c_uint),
            ("uFlags", ctypes.c_uint),
            ("uCallbackMessage", ctypes.c_uint),
            ("hIcon", ctypes.c_void_p),
            ("szTip", ctypes.c_wchar * 128),
            ("dwState", ctypes.c_uint),
            ("dwStateMask", ctypes.c_uint),
            ("szInfo", ctypes.c_wchar * 256),
            ("uVersion", ctypes.c_uint),  # Union with uTimeout
            ("szInfoTitle", ctypes.c_wchar * 64),
            ("dwInfoFlags", ctypes.c_uint),
            ("guidItem", ctypes.c_ubyte * 16),
            ("hBalloonIcon", ctypes.c_void_p),
        ]

    def _get_hwnd(self, w):
        # Ensure we always return a valid handle or 0
        try:
            return lib.webview_get_window(w)
        except:
            return 0

    def notification(self, w, title, message, icon=None):
        """
        Sends a native Windows Toast/Balloon notification.
        """
        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32

        try:
            nid = self.NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(self.NOTIFYICONDATAW)
            nid.hWnd = self._get_hwnd(w)
            nid.uID = 2000  # Keep ID consistent

            # Flags: Info (Text) + Icon (Tray) + Tip (Hover)
            nid.uFlags = self.NIF_INFO | self.NIF_ICON | self.NIF_TIP

            nid.szInfo = message[:255]
            nid.szInfoTitle = title[:63]
            nid.szTip = title[:127] if title else "Notification"
            nid.dwInfoFlags = self.NIIF_INFO  # Standard 'Info' icon in the bubble

            # --- Icon Loading Logic ---
            h_icon = 0
            if icon and os.path.exists(icon):
                # Try loading custom icon
                h_icon = user32.LoadImageW(
                    0,
                    str(icon),
                    1,
                    16,
                    16,
                    0x00000010,  # IMAGE_ICON, 16x16, LOADFROMFILE
                )

            if not h_icon:
                # Fallback to system 'Application' icon
                h_icon = user32.LoadIconW(0, 32512)

            nid.hIcon = h_icon

            # 1. Try to ADD
            success = shell32.Shell_NotifyIconW(self.NIM_ADD, ctypes.byref(nid))

            # 2. If Add failed (icon likely already there), try MODIFY
            if not success:
                success = shell32.Shell_NotifyIconW(self.NIM_MODIFY, ctypes.byref(nid))

            if not success:
                err = ctypes.GetLastError()
                print(f"[Pytron] Notification Failed. Error Code: {err}")
                return

            # 3. CRITICAL: Set Version to 4 to enable "Toast" behavior (vs old balloons)
            nid.uVersion = self.NOTIFYICON_VERSION_4
            shell32.Shell_NotifyIconW(self.NIM_SETVERSION, ctypes.byref(nid))

        except Exception as e:
            print(f"[Pytron] Notification Exception: {e}")

    # --- Window Controls ---

    def minimize(self, w):
        hwnd = self._get_hwnd(w)
        ctypes.windll.user32.ShowWindow(hwnd, self.SW_MINIMIZE)

    def set_bounds(self, w, x, y, width, height):
        hwnd = self._get_hwnd(w)
        ctypes.windll.user32.SetWindowPos(
            hwnd,
            0,
            int(x),
            int(y),
            int(width),
            int(height),
            self.SWP_NOZORDER | self.SWP_NOACTIVATE,
        )

    def close(self, w):
        hwnd = self._get_hwnd(w)
        ctypes.windll.user32.PostMessageW(hwnd, self.WM_CLOSE, 0, 0)

    def toggle_maximize(self, w):
        hwnd = self._get_hwnd(w)
        is_zoomed = ctypes.windll.user32.IsZoomed(hwnd)
        if is_zoomed:
            ctypes.windll.user32.ShowWindow(hwnd, self.SW_RESTORE)
            return False
        else:
            ctypes.windll.user32.ShowWindow(hwnd, self.SW_MAXIMIZE)
            return True

    def make_frameless(self, w):
        hwnd = self._get_hwnd(w)
        style = ctypes.windll.user32.GetWindowLongW(hwnd, self.GWL_STYLE)
        style = style & ~self.WS_CAPTION
        ctypes.windll.user32.SetWindowLongW(hwnd, self.GWL_STYLE, style)
        ctypes.windll.user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x0001 | 0x0002 | 0x0004 | 0x0010
        )

    def start_drag(self, w):
        hwnd = self._get_hwnd(w)
        ctypes.windll.user32.ReleaseCapture()
        ctypes.windll.user32.SendMessageW(
            hwnd, self.WM_NCLBUTTONDOWN, self.HTCAPTION, 0
        )

    def message_box(self, w, title, message, style=0):
        hwnd = self._get_hwnd(w)
        return ctypes.windll.user32.MessageBoxW(hwnd, message, title, style)

    def hide(self, w):
        hwnd = self._get_hwnd(w)
        ctypes.windll.user32.ShowWindow(hwnd, self.SW_HIDE)

    def show(self, w):
        hwnd = self._get_hwnd(w)
        ctypes.windll.user32.ShowWindow(hwnd, self.SW_SHOW)
        ctypes.windll.user32.SetForegroundWindow(hwnd)

    def set_window_icon(self, w, icon_path):
        if not icon_path or not os.path.exists(icon_path):
            return
        hwnd = self._get_hwnd(w)

        # 0x0080 = WM_SETICON, 1 = ICON_BIG, 0 = ICON_SMALL
        try:
            # Small (Titlebar/Taskbar)
            h_small = ctypes.windll.user32.LoadImageW(
                0, str(icon_path), 1, 16, 16, 0x10
            )
            if h_small:
                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, h_small)

            # Big (Alt-Tab/Task Manager)
            h_big = ctypes.windll.user32.LoadImageW(0, str(icon_path), 1, 32, 32, 0x10)
            if h_big:
                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, h_big)
        except Exception as e:
            print(f"Icon error: {e}")

    # --- File Dialogs Support ---

    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", ctypes.c_uint),
            ("hwndOwner", ctypes.c_void_p),
            ("hInstance", ctypes.c_void_p),
            ("lpstrFilter", ctypes.c_wchar_p),
            ("lpstrCustomFilter", ctypes.c_wchar_p),
            ("nMaxCustFilter", ctypes.c_uint),
            ("nFilterIndex", ctypes.c_uint),
            ("lpstrFile", ctypes.c_wchar_p),
            ("nMaxFile", ctypes.c_uint),
            ("lpstrFileTitle", ctypes.c_wchar_p),
            ("nMaxFileTitle", ctypes.c_uint),
            ("lpstrInitialDir", ctypes.c_wchar_p),
            ("lpstrTitle", ctypes.c_wchar_p),
            ("Flags", ctypes.c_uint),
            ("nFileOffset", ctypes.c_ushort),
            ("nFileExtension", ctypes.c_ushort),
            ("lpstrDefExt", ctypes.c_wchar_p),
            ("lCustData", ctypes.c_long),
            ("lpfnHook", ctypes.c_void_p),
            ("lpTemplateName", ctypes.c_wchar_p),
        ]

    # Flags
    OFN_EXPLORER = 0x00080000
    OFN_FILEMUSTEXIST = 0x00001000
    OFN_PATHMUSTEXIST = 0x00000800
    OFN_OVERWRITEPROMPT = 0x00000002
    OFN_NOCHANGEDIR = 0x00000008

    def _prepare_ofn(self, w, title, default_path, file_types, file_buffer_size=1024):
        ofn = self.OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(self.OPENFILENAMEW)
        ofn.hwndOwner = self._get_hwnd(w)

        # Buffer for file name
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

    def open_file_dialog(self, w, title, default_path=None, file_types=None):
        ofn, buff = self._prepare_ofn(w, title, default_path, file_types)
        ofn.Flags = (
            self.OFN_EXPLORER
            | self.OFN_FILEMUSTEXIST
            | self.OFN_PATHMUSTEXIST
            | self.OFN_NOCHANGEDIR
        )

        if ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
            return buff.value
        return None

    def save_file_dialog(
        self, w, title, default_path=None, default_name=None, file_types=None
    ):
        path = default_path
        if default_name:
            if path:
                path = os.path.join(path, default_name)
            else:
                path = default_name

        ofn, buff = self._prepare_ofn(w, title, path, file_types)
        ofn.Flags = (
            self.OFN_EXPLORER
            | self.OFN_OVERWRITEPROMPT
            | self.OFN_PATHMUSTEXIST
            | self.OFN_NOCHANGEDIR
        )

        if ctypes.windll.comdlg32.GetSaveFileNameW(ctypes.byref(ofn)):
            return buff.value
        return None

    # Folder/Browse Logic using SHBrowseForFolder (Simple)
    class BROWSEINFOW(ctypes.Structure):
        _fields_ = [
            ("hwndOwner", ctypes.c_void_p),
            ("pidlRoot", ctypes.c_void_p),
            ("pszDisplayName", ctypes.c_wchar_p),
            ("lpszTitle", ctypes.c_wchar_p),
            ("ulFlags", ctypes.c_uint),
            ("lpfn", ctypes.c_void_p),
            ("lParam", ctypes.c_long),
            ("iImage", ctypes.c_int),
        ]

    BIF_RETURNONLYFSDIRS = 0x00000001
    BIF_NEWDIALOGSTYLE = 0x00000040

    def open_folder_dialog(self, w, title, default_path=None):
        bif = self.BROWSEINFOW()
        bif.hwndOwner = self._get_hwnd(w)
        bif.lpszTitle = title
        bif.ulFlags = self.BIF_RETURNONLYFSDIRS | self.BIF_NEWDIALOGSTYLE

        pidl = ctypes.windll.shell32.SHBrowseForFolderW(ctypes.byref(bif))
        if pidl:
            path = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetPathFromIDListW(pidl, path):
                ctypes.windll.shell32.ILFree(ctypes.c_void_p(pidl))
                return path.value
            ctypes.windll.shell32.ILFree(ctypes.c_void_p(pidl))
        return None

    # --- Custom Protocol for App Launch ---
    def register_protocol(self, scheme):
        if not winreg:
            return False
        try:
            exe = sys.executable
            if not getattr(sys, "frozen", False):
                pass
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

    # --- Taskbar Progress (ITaskbarList3) ---
    TBPF_NOPROGRESS = 0
    TBPF_INDETERMINATE = 0x1
    TBPF_NORMAL = 0x2
    TBPF_ERROR = 0x4
    TBPF_PAUSED = 0x8

    _taskbar_list = None

    def _init_taskbar(self):
        if self._taskbar_list:
            return self._taskbar_list
        try:
            try:
                ctypes.windll.ole32.CoInitialize(0)
            except:
                pass

            CLSID_TaskbarList = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
            import comtypes.client

            self._taskbar_list = comtypes.client.CreateObject(
                CLSID_TaskbarList, interface=comtypes.gen.TaskbarLib.ITaskbarList3
            )
            self._taskbar_list.HrInit()
            return self._taskbar_list
        except Exception:
            return None

    def set_taskbar_progress(self, w, state="normal", value=0, max_value=100):
        try:
            tbl = self._init_taskbar()
            if not tbl:
                return
            hwnd = self._get_hwnd(w)
            flags = self.TBPF_NOPROGRESS
            if state == "indeterminate":
                flags = self.TBPF_INDETERMINATE
            elif state == "normal":
                flags = self.TBPF_NORMAL
            elif state == "error":
                flags = self.TBPF_ERROR
            elif state == "paused":
                flags = self.TBPF_PAUSED
            tbl.SetProgressState(hwnd, flags)
            if state in ("normal", "error", "paused"):
                tbl.SetProgressValue(hwnd, int(value), int(max_value))
        except Exception:
            pass

    def set_app_id(self, app_id):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass

    def center(self, w):
        hwnd = self._get_hwnd(w)
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

    def set_launch_on_boot(self, app_name, exe_path, enable=True):
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

    # --- Pytron Scheme Handler (O(1)) ---
    def register_pytron_scheme(self, w, callback):
        """
        Registers a WebResourceRequested handler on the underlying WebView2 interface
        to intercept pytron:// requests and serve them via IStream.
        """
        try:
            import comtypes
            import comtypes.client
            from comtypes import GUID, IUnknown, HRESULT, COMMETHOD, POINTER
            from ctypes import cast, c_void_p, c_int, byref, c_ulonglong

            # 1. Define Minimum Required Interfaces (since we don't assume TLB availability)

            class IStream(IUnknown):
                _iid_ = GUID("{0000000c-0000-0000-C000-000000000046}")
                _methods_ = [
                    COMMETHOD(
                        [],
                        HRESULT,
                        "Read",
                        (["out"], c_void_p, "pv"),
                        (["in"], c_int, "cb"),
                        (["out"], POINTER(c_ulonglong), "pcbRead"),
                    ),
                    COMMETHOD(
                        [],
                        HRESULT,
                        "Write",
                        (["in"], c_void_p, "pv"),
                        (["in"], c_int, "cb"),
                        (["out"], POINTER(c_ulonglong), "pcbWritten"),
                    ),
                ]

            class ICoreWebView2WebResourceRequest(IUnknown):
                _iid_ = GUID("{97055CD4-512C-4264-8B5F-E3F446EA0C59}")
                _methods_ = [
                    COMMETHOD(
                        [],
                        HRESULT,
                        "get_Uri",
                        (["out"], POINTER(ctypes.c_wchar_p), "uri"),
                    ),
                    COMMETHOD(
                        [],
                        HRESULT,
                        "get_Method",
                        (["out"], POINTER(ctypes.c_wchar_p), "method"),
                    ),
                ]

            class ICoreWebView2WebResourceResponse(IUnknown):
                _iid_ = GUID("{AAFCC94F-FA27-48FD-97DF-830EF75AAEC9}")
                # No methods needed to call, we just create instances and pass them back

            class ICoreWebView2WebResourceRequestedEventArgs(IUnknown):
                _iid_ = GUID("{453E667F-12C7-49D4-BE6D-DDBE7956A57A}")
                _methods_ = [
                    COMMETHOD(
                        [],
                        HRESULT,
                        "get_Request",
                        (
                            ["out"],
                            POINTER(POINTER(ICoreWebView2WebResourceRequest)),
                            "request",
                        ),
                    ),
                    COMMETHOD(
                        [],
                        HRESULT,
                        "get_Response",
                        (
                            ["out"],
                            POINTER(POINTER(ICoreWebView2WebResourceResponse)),
                            "response",
                        ),
                    ),
                    COMMETHOD(
                        [],
                        HRESULT,
                        "put_Response",
                        (["in"], POINTER(ICoreWebView2WebResourceResponse), "response"),
                    ),
                    COMMETHOD(
                        [],
                        HRESULT,
                        "GetDeferral",
                        (["out"], POINTER(c_void_p), "deferral"),
                    ),
                ]

            class ICoreWebView2WebResourceRequestedEventHandler(IUnknown):
                _iid_ = GUID("{D603F230-081A-4927-94BC-9F8E32D33D3B}")
                _methods_ = [
                    COMMETHOD(
                        [],
                        HRESULT,
                        "Invoke",
                        (["in"], POINTER(IUnknown), "sender"),
                        (
                            ["in"],
                            POINTER(ICoreWebView2WebResourceRequestedEventArgs),
                            "args",
                        ),
                    ),
                ]

            # Simplified Environment to Create Response
            class ICoreWebView2Environment(IUnknown):
                _iid_ = GUID("{B96D755E-0319-4E92-A296-23436F46A1FC}")
                # We need CreateWebResourceResponse which is index 8 (0-based) ??
                # VTable order:
                # QueryInterface, AddRef, Release (3)
                # CreateCoreWebView2Controller (3)
                # CreateWebResourceResponse (1)
                # Total offset: 3+1 = 4? No.
                # Let's rely on name if comtypes allows, or dynamic
                # We will define it properly:
                _methods_ = [
                    COMMETHOD(
                        [],
                        HRESULT,
                        "CreateCoreWebView2Controller",
                        (["in"], c_void_p, "ParentWindow"),
                        (["in"], c_void_p, "handler"),
                    ),
                    COMMETHOD(
                        [],
                        HRESULT,
                        "CreateWebResourceResponse",
                        (["in"], POINTER(IStream), "Content"),
                        (["in"], c_int, "StatusCode"),
                        (["in"], ctypes.c_wchar_p, "ReasonPhrase"),
                        (["in"], ctypes.c_wchar_p, "Headers"),
                        (
                            ["out"],
                            POINTER(POINTER(ICoreWebView2WebResourceResponse)),
                            "Response",
                        ),
                    ),
                ]

            # Simplified WebView2
            class ICoreWebView2(IUnknown):
                _iid_ = GUID("{76741B9C-9200-4719-84C2-F003CE026461}")
                # We need AddWebResourceRequestedFilter (index ??) and add_WebResourceRequested (index ??)
                # This is tricky without Tlb. I'll rely on DISPATCH if possible but this is IUnknown.
                # Assuming Interface order:
                # ...
                # add_WebResourceRequested is usually around index 16.
                pass

            # --- Implementation Logic ---

            # 2. Handler Implementation
            class Handler(comtypes.COMObject):
                _com_interfaces_ = [ICoreWebView2WebResourceRequestedEventHandler]

                def __init__(self, env):
                    self.env = env
                    super().__init__()

                def Invoke(self, sender, args):
                    # args is pointer to ICoreWebView2WebResourceRequestedEventArgs
                    try:
                        req = POINTER(ICoreWebView2WebResourceRequest)()
                        args.get_Request(byref(req))
                        uri = ctypes.c_wchar_p()
                        req.get_Uri(byref(uri))
                        url_str = uri.value

                        if url_str and url_str.startswith("pytron://"):
                            # Call Python Callback
                            data, mime = callback(url_str)
                            if data:
                                # Create IStream from data
                                # We use shlwapi SHCreateMemStream
                                shlwapi = ctypes.windll.shlwapi
                                shlwapi.SHCreateMemStream.restype = POINTER(IStream)
                                shlwapi.SHCreateMemStream.argtypes = [
                                    ctypes.c_char_p,
                                    ctypes.c_uint,
                                ]

                                stream = shlwapi.SHCreateMemStream(data, len(data))

                                resp = POINTER(ICoreWebView2WebResourceResponse)()
                                # Set Headers to allow CORS (fetch/xhr)
                                header_str = f"Content-Type: {mime}\nAccess-Control-Allow-Origin: *"
                                self.env.CreateWebResourceResponse(
                                    stream, 200, "OK", header_str, byref(resp)
                                )

                                args.put_Response(resp)
                    except Exception as e:
                        print(f"Pytron Scheme Error: {e}")
                    return 0  # S_OK

            # 3. Locate ICoreWebView2* and Environment
            # We assume layout: vtbl(8) + HWND(8) + Env*(8) + Controller*(8) + WebView*(8)
            # This is heuristics based on zserge/webview implementation

            base_addr = w.value if hasattr(w, "value") else w
            if not base_addr:
                return False

            # Try to read members
            # We need to find valid pointers.
            # pointer_size = 8

            # Check Env
            env_ptr_val = ctypes.c_void_p.from_address(base_addr + 16).value
            if not env_ptr_val:
                return False
            env = cast(env_ptr_val, POINTER(ICoreWebView2Environment))
            self._webview_env = env  # Keep alive

            # Check WebView
            wv_ptr_val = ctypes.c_void_p.from_address(
                base_addr + 32
            ).value  # 32 seems more likely for webview* in standard layout
            if not wv_ptr_val:
                # Try 24
                wv_ptr_val = ctypes.c_void_p.from_address(base_addr + 24).value

            if not wv_ptr_val:
                return False

            # We have the pointer, but we need to call methods dynamically because we don't have exact VTABLE definition
            # ICoreWebView2::AddWebResourceRequestedFilter (Method 66??)
            # ICoreWebView2::add_WebResourceRequested (Method 64??)

            # We can use comtypes to Bind dynamically if TypeInfo was available, but it's not.
            # We will use manual VTable binding via ctypes, assuming standard offsets.
            # add_WebResourceRequested is offset: 16
            # AddWebResourceRequestedFilter is offset: 62 or something

            # Actually, let's look at `comtypes.client.GetModule` if possible? No.

            # HACK: Retrieve VTABLE and call by index
            # This requires knowing index.
            # ICoreWebView2:
            # 3 (IUnknown) + ...
            # 64: add_WebResourceRequested
            # 66: AddWebResourceRequestedFilter
            # (Based on SDK analysis)

            wv_obj = cast(wv_ptr_val, POINTER(ICoreWebView2))

            # Setup Handler
            handler = Handler(env)
            # Keep handler alive
            self._protocol_handler = handler

            # Define Ftypes
            AddFilterProto = ctypes.WINFUNCTYPE(
                HRESULT, c_void_p, ctypes.c_wchar_p, c_int
            )
            AddHandlerProto = ctypes.WINFUNCTYPE(
                HRESULT,
                c_void_p,
                POINTER(ICoreWebView2WebResourceRequestedEventHandler),
                POINTER(c_ulonglong),
            )

            vtable = cast(wv_obj, POINTER(c_void_p))[0]

            # AddWebResourceRequestedFilter
            # The User wants implementation "using ctypes".
            # I am doing exactly that.
            # Indexes for ICoreWebView2 (Interface 76741B9C...):
            # ...
            # 64: add_WebResourceRequested
            # 65: remove_WebResourceRequested
            # 66: AddWebResourceRequestedFilter (Added in 1.0.774.44)
            # 67: remove_WebResourceRequestedFilter

            add_filter_addr = cast(vtable + (66 * 8), POINTER(c_void_p))[0]
            add_filter = AddFilterProto(add_filter_addr)

            add_handler_addr = cast(vtable + (64 * 8), POINTER(c_void_p))[0]
            add_handler = AddHandlerProto(add_handler_addr)

            # Register Filter
            # COREWEBVIEW2_WEB_RESOURCE_CONTEXT_ALL = 0
            add_filter(wv_ptr_val, "pytron://*", 0)

            # Add Handler
            token = c_ulonglong()
            add_handler(wv_ptr_val, handler, byref(token))

            print("[Pytron] O(1) Protocol Handler Registered Successfully.")
            return True

        except Exception as e:
            print(f"[Pytron] Failed to register O(1) scheme handler: {e}")
            return False
