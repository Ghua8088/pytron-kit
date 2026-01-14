import os
import sys
import ctypes
import threading
import logging
from typing import Callable, List, Dict, Optional
from .utils import get_resource_path

# Platform-specific imports
if sys.platform == "win32":
    import ctypes.wintypes
    from .platforms.windows_ops.constants import NOTIFYICONDATAW

# Windows Constants
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 1
NIM_ADD = 0x00
NIM_MODIFY = 0x01
NIM_DELETE = 0x02
NIF_ICON = 0x01
NIF_MESSAGE = 0x02
NIF_TIP = 0x04
NIF_INFO = 0x10
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
TPM_LEFTALIGN = 0x0000
TPM_RIGHTBUTTON = 0x0002
MIIM_ID = 0x0002
MIIM_TYPE = 0x0010
MIIM_DATA = 0x0020
MFT_STRING = 0x0000
MFT_SEPARATOR = 0x0800


class MenuItem:
    def __init__(
        self,
        label: str,
        callback: Optional[Callable] = None,
        is_separator: bool = False,
    ):
        self.label = label
        self.callback = callback
        self.is_separator = is_separator
        self.id = 0


class SystemTray:
    def __init__(self, title: str, icon_path: Optional[str] = None):
        self.title = title
        self.icon_path = icon_path
        self.menu_items: List[MenuItem] = []
        self.logger = logging.getLogger("Pytron.Tray")
        self._hwnd = None
        self._hicon = None
        self._running = False
        self._next_id = 1000
        self._thread = None
        self._app = None

    def add_item(self, label: str, callback: Optional[Callable] = None):
        item = MenuItem(label, callback)
        item.id = self._next_id
        self._next_id += 1
        self.menu_items.append(item)
        return self

    def add_separator(self):
        item = MenuItem("", is_separator=True)
        self.menu_items.append(item)
        return self

    def add_quit_item(self, label: str = "Quit"):
        """Adds a standard Quit item to the tray menu."""

        def _quit():
            if self._app:
                # Use app.quit() for graceful exit (triggers cleanup/atexit)
                self._app.quit()
            else:
                os._exit(0)

        return self.add_item(label, _quit)

    def start(self, app):
        """Starts the tray icon."""
        self._app = app
        platform = sys.platform
        if platform == "win32":
            self._start_windows(app)
        elif platform == "darwin":
            self._start_darwin(app)
        elif platform == "linux":
            self._start_linux(app)
        else:
            self.logger.warning(f"System tray not implemented for {platform}")

    def stop(self):
        platform = sys.platform
        if platform == "win32":
            self._stop_windows()
            # Cleanup Icon handle to prevent leaks
            if self._hicon:
                ctypes.windll.user32.DestroyIcon(self._hicon)
                self._hicon = None

    def _start_darwin(self, app):
        try:
            from AppKit import (
                NSStatusBar,
                NSVariableStatusItemLength,
                NSMenu,
                NSMenuItem,
                NSImage,
            )
            from PyObjCTools import AppHelper

            self._status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
                NSVariableStatusItemLength
            )
            self._status_item.setToolTip_(self.title)

            if self.icon_path:
                image = NSImage.alloc().initWithContentsOfFile_(self.icon_path)
                if image:
                    image.setTemplate_(True)
                    self._status_item.button().setImage_(image)

            if not self._status_item.button().image():
                self._status_item.setTitle_(self.title[:3])

            # Create Menu
            menu = NSMenu.alloc().init()

            class MenuDelegate:
                def __init__(self, callback):
                    self.callback = callback

                def call_(self, sender):
                    if self.callback:
                        self.callback()

            self._delegates = []

            for item in self.menu_items:
                if item.is_separator:
                    menu.addItem_(NSMenuItem.separatorItem())
                else:
                    d = MenuDelegate(item.callback)
                    self._delegates.append(d)
                    mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        item.label, "call:", ""
                    )
                    mi.setTarget_(d)
                    menu.addItem_(mi)

            self._status_item.setMenu_(menu)
        except ImportError:
            self.logger.error("macOS Tray requires 'pyobjc-framework-Cocoa'.")

    def _start_linux(self, app):
        try:
            import gi

            gi.require_version("Gtk", "3.0")
            gi.require_version("AppIndicator3", "0.1")
            from gi.repository import Gtk, AppIndicator3

            ind_id = f"pytron.tray.{id(self)}"
            icon = self.icon_path if self.icon_path else "help-about"

            indicator = AppIndicator3.Indicator.new(
                ind_id, icon, AppIndicator3.IndicatorCategory.APPLICATION_STATUS
            )
            indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

            menu = Gtk.Menu()

            for item in self.menu_items:
                if item.is_separator:
                    menu.append(Gtk.SeparatorMenuItem())
                else:
                    mi = Gtk.MenuItem(label=item.label)
                    if item.callback:
                        mi.connect("activate", lambda _: item.callback())
                    menu.append(mi)

            menu.show_all()
            indicator.set_menu(menu)
            self._indicator = indicator

        except (ImportError, ValueError):
            self.logger.error("Linux Tray requires 'PyGObject' and 'libappindicator3'.")

    def _start_windows(self, app):
        # Event to sync creation
        ready_event = threading.Event()

        def run_tray_thread():
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            shell32 = ctypes.windll.shell32

            # --- Definitions ---
            user32.DefWindowProcW.argtypes = [
                ctypes.wintypes.HWND,
                ctypes.wintypes.UINT,
                ctypes.wintypes.WPARAM,
                ctypes.wintypes.LPARAM,
            ]
            user32.DefWindowProcW.restype = ctypes.wintypes.LPARAM
            user32.CreateWindowExW.argtypes = [
                ctypes.c_uint,
                ctypes.c_wchar_p,
                ctypes.c_wchar_p,
                ctypes.c_uint,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            user32.CreateWindowExW.restype = ctypes.c_void_p
            kernel32.GetModuleHandleW.restype = ctypes.c_void_p

            # Ensure we use the shared NOTIFYICONDATAW definition
            shell32.Shell_NotifyIconW.argtypes = [
                ctypes.c_ulong,
                ctypes.POINTER(NOTIFYICONDATAW),
            ]
            shell32.Shell_NotifyIconW.restype = ctypes.wintypes.BOOL

            def window_proc(hwnd, msg, wparam, lparam):
                if msg == WM_TRAYICON:
                    if lparam == WM_LBUTTONUP:
                        app.show()
                    elif lparam == WM_RBUTTONUP:
                        self._show_menu(hwnd)
                elif msg == 0x0111:  # WM_COMMAND
                    item_id = wparam & 0xFFFF
                    for item in self.menu_items:
                        if item.id == item_id and item.callback:
                            try:
                                item.callback()
                            except Exception as e:
                                self.logger.error(f"Menu callback failed: {e}")
                            break
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

            WNDPROC = ctypes.WINFUNCTYPE(
                ctypes.wintypes.LPARAM,
                ctypes.wintypes.HWND,
                ctypes.wintypes.UINT,
                ctypes.wintypes.WPARAM,
                ctypes.wintypes.LPARAM,
            )
            self._wndproc = WNDPROC(window_proc)  # Keep ref to prevent GC

            class WNDCLASSW(ctypes.Structure):
                _fields_ = [
                    ("style", ctypes.c_uint),
                    ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int),
                    ("hInstance", ctypes.c_void_p),
                    ("hIcon", ctypes.c_void_p),
                    ("hCursor", ctypes.c_void_p),
                    ("hbrBackground", ctypes.c_void_p),
                    ("lpszMenuName", ctypes.c_wchar_p),
                    ("lpszClassName", ctypes.c_wchar_p),
                ]

            wc = WNDCLASSW()
            wc.lpfnWndProc = self._wndproc
            wc.lpszClassName = f"PytronTray_{id(self)}"
            wc.hInstance = kernel32.GetModuleHandleW(None)
            user32.RegisterClassW(ctypes.byref(wc))

            # 2. Create Window INSIDE this thread
            self._hwnd = user32.CreateWindowExW(
                0, wc.lpszClassName, self.title, 0, 0, 0, 0, 0, 0, 0, wc.hInstance, 0
            )

            # 3. Create Icon
            if self.icon_path:
                IMAGE_ICON = 1
                LR_LOADFROMFILE = 0x00000010
                r_path = get_resource_path(self.icon_path)
                self.logger.debug(f"Attempting to load icon from: {r_path}")

                # Load 16x16 for logic
                self._hicon = user32.LoadImageW(
                    None, str(r_path), IMAGE_ICON, 16, 16, LR_LOADFROMFILE
                )

                if not self._hicon:
                    err = ctypes.GetLastError()
                    self.logger.warning(
                        f"Failed to load 16x16 icon. Error: {err}. Retrying with default size."
                    )
                    # Retry with default size
                    self._hicon = user32.LoadImageW(
                        None, str(r_path), IMAGE_ICON, 0, 0, LR_LOADFROMFILE
                    )
                    if not self._hicon:
                        self.logger.error(
                            f"Failed to load default size icon. Error: {ctypes.GetLastError()}"
                        )

            if not self._hicon:
                self.logger.warning("Fallback to system application icon")
                self._hicon = user32.LoadIconW(0, ctypes.c_void_p(32512))

            # 4. Add to Tray
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = self._hwnd
            nid.uID = 1
            nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP
            nid.uCallbackMessage = WM_TRAYICON
            nid.hIcon = self._hicon
            nid.szTip = self.title[:127]

            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

            # Signal that we are ready!
            ready_event.set()

            # 5. Pump Messages (Blocking)
            msg = ctypes.wintypes.MSG()
            while self._running:
                # GetMessage blocks until a message arrives
                res = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
                if res <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            # Cleanup when loop exits
            if self._hwnd:
                user32.DestroyWindow(self._hwnd)

        self._running = True
        self._thread = threading.Thread(target=run_tray_thread, daemon=True)
        self._thread.start()

        # Wait for tray to appear before returning (prevents race conditions)
        ready_event.wait(timeout=2.0)

    def _show_menu(self, hwnd):
        hmenu = ctypes.windll.user32.CreatePopupMenu()

        for item in self.menu_items:
            if item.is_separator:
                ctypes.windll.user32.AppendMenuW(hmenu, MFT_SEPARATOR, 0, None)
            else:
                ctypes.windll.user32.AppendMenuW(hmenu, MFT_STRING, item.id, item.label)

        pos = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pos))

        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.TrackPopupMenu(
            hmenu, TPM_LEFTALIGN | TPM_RIGHTBUTTON, pos.x, pos.y, 0, hwnd, None
        )
        ctypes.windll.user32.PostMessageW(hwnd, 0, 0, 0)

    def _stop_windows(self):
        self._running = False
        if self._hwnd:
            # Force wake up the message loop to exit?
            # GetMessage is blocking. We need to post a dummy message or WM_NULL/WM_CLOSE
            ctypes.windll.user32.PostMessageW(self._hwnd, 0x0010, 0, 0)  # WM_CLOSE

        # Wait for thread to finish to prevent zombies
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                self.logger.warning("Tray thread did not exit cleanly.")

        # Also delete icon
        if self._hwnd:
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = self._hwnd
            nid.uID = 1

            shell32 = ctypes.windll.shell32
            # Use strict argtypes with shared structure
            shell32.Shell_NotifyIconW.argtypes = [
                ctypes.c_ulong,
                ctypes.POINTER(NOTIFYICONDATAW),
            ]

            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            self._hwnd = None
