import ctypes
import ctypes.util
from ..bindings import lib
from .interface import PlatformInterface
import os


class DarwinImplementation(PlatformInterface):
    def __init__(self):
        try:
            # Load Cocoa
            self.cocoa = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Cocoa"))

            # Setup objc_msgSend
            self.objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))

            self.objc.objc_getClass.restype = ctypes.c_void_p
            self.objc.objc_getClass.argtypes = [ctypes.c_char_p]

            self.objc.sel_registerName.restype = ctypes.c_void_p
            self.objc.sel_registerName.argtypes = [ctypes.c_char_p]

            self.objc.objc_msgSend.restype = ctypes.c_void_p
            # Do NOT set argtypes for objc_msgSend as it is variadic

        except Exception as e:
            print(f"Pytron Warning: Cocoa/ObjC not found: {e}")
            self.objc = None

    def _get_window(self, w):
        return lib.webview_get_window(w)

    def _call(self, obj, selector, *args):
        if not self.objc:
            return None
        sel = self.objc.sel_registerName(selector.encode("utf-8"))
        return self.objc.objc_msgSend(obj, sel, *args)

    def minimize(self, w):
        win = self._get_window(w)
        self._call(win, "miniaturize:", None)

    def set_bounds(self, w, x, y, width, height):
        pass

    def close(self, w):
        win = self._get_window(w)
        self._call(win, "close")

    def toggle_maximize(self, w):
        win = self._get_window(w)
        self._call(win, "zoom:", None)
        return True

    def make_frameless(self, w):
        win = self._get_window(w)
        # setStyleMask: 8 (Resizable) | 0 (Borderless) -> But we usually want Titled | FullSizeContentView
        # To mimic standardized frameless:
        # NSWindowStyleMaskTitled = 1 << 0
        # NSWindowStyleMaskClosable = 1 << 1
        # NSWindowStyleMaskMiniaturizable = 1 << 2
        # NSWindowStyleMaskResizable = 1 << 3
        # NSWindowStyleMaskFullSizeContentView = 1 << 15

        # We want bits: 1|2|4|8|32768 = 32783
        self._call(
            win, "setStyleMask:", 32783
        )  # Standard macos "frameless but native controls"
        self._call(win, "setTitlebarAppearsTransparent:", 1)
        self._call(win, "setTitleVisibility:", 1)  # NSWindowTitleHidden

    def start_drag(self, w):
        win = self._get_window(w)
        self._call(win, "setMovableByWindowBackground:", 1)

    def message_box(self, w, title, message, style=0):
        # Use osascript for native-look dialogs
        import subprocess

        script = ""
        if style == 4:
            script = f'display alert "{title}" message "{message}" buttons {{"No", "Yes"}} default button "Yes"'
        elif style == 1:
            script = f'display alert "{title}" message "{message}" buttons {{"Cancel", "OK"}} default button "OK"'
        else:
            script = f'display alert "{title}" message "{message}" buttons {{"OK"}} default button "OK"'

        try:
            output = subprocess.check_output(["osascript", "-e", script], text=True)
            if "Yes" in output or "OK" in output:
                return 6 if style == 4 else 1
            return 7 if style == 4 else 2
        except subprocess.CalledProcessError:
            return 7 if style == 4 else 2
        except Exception:
            return 6

    def register_pytron_scheme(self, w, callback):
        """
        Setup handler for macOS.
        Note: Registering custom URL schemes on WKWebView requires configuration injection
        BEFORE instantiation, which the current C-bindings don't support.

        We fallback to enabling File Access so file:// works, and logging the limitation.
        """
        if not self.objc:
            return

        try:
            # 1. Helpers for ObjC interactions
            def get_class(name):
                return self.objc.objc_getClass(name.encode("utf-8"))

            def str_to_nsstring(s):
                cls = get_class("NSString")
                sel = self.objc.sel_registerName(
                    "stringWithUTF8String:".encode("utf-8")
                )
                f = ctypes.CFUNCTYPE(
                    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p
                )(self.objc.objc_msgSend)
                return f(cls, sel, s.encode("utf-8"))

            def bool_to_nsnumber(b):
                cls = get_class("NSNumber")
                sel = self.objc.sel_registerName("numberWithBool:".encode("utf-8"))
                f = ctypes.CFUNCTYPE(
                    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool
                )(self.objc.objc_msgSend)
                return f(cls, sel, b)

            # 2. Get the WebView
            win = self._get_window(w)
            f_id = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
                self.objc.objc_msgSend
            )
            sel_contentView = self.objc.sel_registerName("contentView".encode("utf-8"))
            webView = f_id(win, sel_contentView)

            if not webView:
                print("[Pytron] Could not find WebView (contentView is null).")
                return

            # 3. Get Configuration
            sel_config = self.objc.sel_registerName("configuration".encode("utf-8"))
            config = f_id(webView, sel_config)

            # 4. Get Preferences
            sel_prefs = self.objc.sel_registerName("preferences".encode("utf-8"))
            prefs = f_id(config, sel_prefs)

            # 5. Set Values using KVC
            f_kv = ctypes.CFUNCTYPE(
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
            )(self.objc.objc_msgSend)
            sel_setValue = self.objc.sel_registerName(
                "setValue:forKey:".encode("utf-8")
            )

            val_true = bool_to_nsnumber(True)

            # Allow File Access
            key_file = str_to_nsstring("allowFileAccessFromFileURLs")
            f_kv(prefs, sel_setValue, val_true, key_file)
            print(
                "[Pytron] macOS: Enabled allowFileAccessFromFileURLs (Scheme interception not available post-init)"
            )

            # Developer Extras
            key_dev = str_to_nsstring("developerExtrasEnabled")
            f_kv(prefs, sel_setValue, val_true, key_dev)

        except Exception as e:
            print(f"[Pytron] Error enabling file access on macOS: {e}")

    # --- Daemon Capabilities ---
    def hide(self, w):
        win = self._get_window(w)
        self._call(win, "orderOut:", None)

    def show(self, w):
        win = self._get_window(w)
        self._call(win, "makeKeyAndOrderFront:", None)
        try:
            cls_app = self.objc.objc_getClass("NSApplication".encode("utf-8"))
            sel_shared = self.objc.sel_registerName("sharedApplication".encode("utf-8"))
            ns_app = self.objc.objc_msgSend(cls_app, sel_shared)

            sel_activate = self.objc.sel_registerName(
                "activateIgnoringOtherApps:".encode("utf-8")
            )
            f_act = ctypes.CFUNCTYPE(
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool
            )(self.objc.objc_msgSend)
            f_act(ns_app, sel_activate, True)
        except Exception:
            pass

    def notification(self, w, title, message, icon=None):
        import subprocess

        script = f'display notification "{message}" with title "{title}"'
        try:
            subprocess.Popen(["osascript", "-e", script])
        except Exception:
            pass

    # --- File Dialogs Support via AppleScript ---
    def _run_osascript_dialog(self, script):
        import subprocess

        try:
            proc = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True
            )
            if proc.returncode == 0:
                return proc.stdout.strip()
            return None
        except Exception:
            return None

    def open_file_dialog(self, w, title, default_path=None, file_types=None):
        script = f'POSIX path of (choose file with prompt "{title}"'
        if default_path:
            script += f' default location "{default_path}"'
        script += ")"
        return self._run_osascript_dialog(script)

    def save_file_dialog(
        self, w, title, default_path=None, default_name=None, file_types=None
    ):
        script = f'POSIX path of (choose file name with prompt "{title}"'
        if default_path:
            script += f' default location "{default_path}"'
        if default_name:
            script += f' default name "{default_name}"'
        script += ")"
        return self._run_osascript_dialog(script)

    def open_folder_dialog(self, w, title, default_path=None):
        script = f'POSIX path of (choose folder with prompt "{title}"'
        if default_path:
            script += f' default location "{default_path}"'
        script += ")"
        return self._run_osascript_dialog(script)

    # --- Taskbar/Dock Progress ---
    def set_taskbar_progress(self, w, state="normal", value=0, max_value=100):
        if not self.objc:
            return
        try:
            cls_app = self.objc.objc_getClass("NSApplication".encode("utf-8"))
            sel_shared = self.objc.sel_registerName("sharedApplication".encode("utf-8"))
            ns_app = self.objc.objc_msgSend(cls_app, sel_shared)

            sel_dock = self.objc.sel_registerName("dockTile".encode("utf-8"))
            f_dock = ctypes.CFUNCTYPE(
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
            )(self.objc.objc_msgSend)
            dock_tile = f_dock(ns_app, sel_dock)

            sel_set_badge = self.objc.sel_registerName("setBadgeLabel:".encode("utf-8"))
            f_set = ctypes.CFUNCTYPE(
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
            )(self.objc.objc_msgSend)

            def get_class(name):
                return self.objc.objc_getClass(name.encode("utf-8"))

            def str_to_nsstring(s):
                cls = get_class("NSString")
                sel = self.objc.sel_registerName(
                    "stringWithUTF8String:".encode("utf-8")
                )
                f = ctypes.CFUNCTYPE(
                    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p
                )(self.objc.objc_msgSend)
                return f(cls, sel, s.encode("utf-8"))

            badge_text = None
            if state in ("normal", "error", "paused") and max_value > 0:
                pct = int((value / max_value) * 100)
                badge_text = str_to_nsstring(f"{pct}%")
            elif state == "indeterminate":
                badge_text = str_to_nsstring("...")

            f_set(dock_tile, sel_set_badge, badge_text)

            sel_display = self.objc.sel_registerName("display".encode("utf-8"))
            self.objc.objc_msgSend(dock_tile, sel_display)

        except Exception:
            pass

    def set_window_icon(self, w, icon_path):
        if not self.objc or not icon_path:
            return
        try:
            cls_image = self.objc.objc_getClass("NSImage".encode("utf-8"))
            sel_alloc = self.objc.sel_registerName("alloc".encode("utf-8"))
            sel_init_file = self.objc.sel_registerName(
                "initWithContentsOfFile:".encode("utf-8")
            )

            def str_to_nsstring(s):
                cls = self.objc.objc_getClass("NSString".encode("utf-8"))
                sel = self.objc.sel_registerName(
                    "stringWithUTF8String:".encode("utf-8")
                )
                f = ctypes.CFUNCTYPE(
                    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p
                )(self.objc.objc_msgSend)
                return f(cls, sel, s.encode("utf-8"))

            img_alloc = self.objc.objc_msgSend(cls_image, sel_alloc)
            ns_path = str_to_nsstring(icon_path)
            f_init = ctypes.CFUNCTYPE(
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
            )(self.objc.objc_msgSend)
            ns_image = f_init(img_alloc, sel_init_file, ns_path)

            if ns_image:
                cls_app = self.objc.objc_getClass("NSApplication".encode("utf-8"))
                sel_shared = self.objc.sel_registerName(
                    "sharedApplication".encode("utf-8")
                )
                ns_app = self.objc.objc_msgSend(cls_app, sel_shared)

                sel_set_icon = self.objc.sel_registerName(
                    "setApplicationIconImage:".encode("utf-8")
                )
                f_set = ctypes.CFUNCTYPE(
                    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
                )(self.objc.objc_msgSend)
                f_set(ns_app, sel_set_icon, ns_image)
        except Exception:
            pass

    def set_app_id(self, app_id):
        if not self.objc:
            return
        try:
            cls_proc = self.objc.objc_getClass("NSProcessInfo".encode("utf-8"))
            sel_info = self.objc.sel_registerName("processInfo".encode("utf-8"))
            proc_info = self.objc.objc_msgSend(cls_proc, sel_info)
            sel_set_name = self.objc.sel_registerName("setProcessName:".encode("utf-8"))

            def str_to_nsstring(s):
                cls = self.objc.objc_getClass("NSString".encode("utf-8"))
                sel = self.objc.sel_registerName(
                    "stringWithUTF8String:".encode("utf-8")
                )
                f = ctypes.CFUNCTYPE(
                    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p
                )(self.objc.objc_msgSend)
                return f(cls, sel, s.encode("utf-8"))

            name_str = str_to_nsstring(app_id)
            f_set = ctypes.CFUNCTYPE(
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
            )(self.objc.objc_msgSend)
            f_set(proc_info, sel_set_name, name_str)
        except Exception:
            pass

    def set_launch_on_boot(self, app_name, exe_path, enable=True):
        import os
        import shlex

        home = os.path.expanduser("~")
        launch_agents = os.path.join(home, "Library/LaunchAgents")
        plist_file = os.path.join(
            launch_agents, f"com.{app_name.lower()}.startup.plist"
        )

        if enable:
            try:
                os.makedirs(launch_agents, exist_ok=True)
                args = shlex.split(exe_path)
                array_str = "\n".join([f"    <string>{a}</string>" for a in args])
                content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.{app_name.lower()}.startup</string>
    <key>ProgramArguments</key>
    <array>
{array_str}
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
                with open(plist_file, "w") as f:
                    f.write(content)
                return True
            except Exception as e:
                print(f"[Pytron] Failed to enable launch agent on macOS: {e}")
                return False
        else:
            try:
                if os.path.exists(plist_file):
                    os.remove(plist_file)
                return True
            except Exception as e:
                print(f"[Pytron] Failed to disable launch agent on macOS: {e}")
                return False
