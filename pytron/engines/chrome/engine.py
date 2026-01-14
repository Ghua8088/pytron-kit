import os
import sys
import json
import logging
import time
import ctypes
import pathlib
import platform
import threading
import subprocess
from ...webview import Webview
from .adapter import ChromeAdapter
from ...serializer import pytron_serialize


def _to_str(b):
    if isinstance(b, bytes):
        return b.decode("utf-8")
    if hasattr(b, "value") and isinstance(b.value, bytes):  # ctypes.c_char_p
        return b.value.decode("utf-8")
    return str(b)


class ChromeBridge:
    """Mocks the native 'lib' DLL interface but redirects to Chrome Shell via IPC."""

    def __init__(self, adapter):
        self.adapter = adapter
        self._callbacks = {}
        self.real_hwnd = 0

    def webview_create(self, debug, window):
        self.adapter.send(
            {
                "action": "init",
                "options": {
                    "debug": bool(debug),
                    "frameless": self.adapter.config.get("frameless", False),
                    "icon": self.adapter.config.get("icon", ""),
                    "width": self.adapter.config.get("width", 1024),
                    "height": self.adapter.config.get("height", 768),
                    "title": self.adapter.config.get("title", "Pytron"),
                    "min_size": self.adapter.config.get("min_size"),
                    "max_size": self.adapter.config.get("max_size"),
                    "resizable": self.adapter.config.get("resizable", True),
                    "fullscreen": self.adapter.config.get("fullscreen", False),
                    "always_on_top": self.adapter.config.get("always_on_top", False),
                    "background_color": self.adapter.config.get(
                        "background_color", "#ffffff"
                    ),
                    "start_hidden": self.adapter.config.get("start_hidden", False),
                    "start_maximized": self.adapter.config.get(
                        "start_maximized", False
                    ),
                },
            }
        )
        return 1

    def webview_show(self, w):
        self.adapter.send({"action": "show"})

    def webview_hide(self, w):
        self.adapter.send({"action": "hide"})

    def webview_set_title(self, w, title):
        self.adapter.send({"action": "set_title", "title": _to_str(title)})

    def webview_set_size(self, w, width, height, hints):
        self.adapter.send({"action": "set_size", "width": width, "height": height})

    def webview_navigate(self, w, url):
        self.adapter.send({"action": "navigate", "url": _to_str(url)})

    def webview_eval(self, w, js):
        self.adapter.send({"action": "eval", "code": _to_str(js)})

    def webview_init(self, w, js):
        self.adapter.send({"action": "init_script", "js": _to_str(js)})

    def webview_run(self, w):
        if self.adapter.process:
            self.adapter.process.wait()

    def webview_destroy(self, w):
        self.adapter.send({"action": "close"})

    def webview_bind(self, w, name, fn, arg):
        n = _to_str(name)
        self._callbacks[n] = fn
        self.adapter.send({"action": "bind", "name": n})

    def webview_return(self, w, seq, status, result):
        try:
            if result is None:
                res_obj = None
            else:
                res_obj = json.loads(_to_str(result))
        except:
            res_obj = _to_str(result)

        self.adapter.send(
            {"action": "reply", "id": _to_str(seq), "status": status, "result": res_obj}
        )

    def webview_get_window(self, w):
        # On Windows, returning the real HWND allows native features (Taskbar, Menus) to work.
        if platform.system() == "Windows":
            return self.real_hwnd
        return 0

    def webview_dispatch(self, w, fn, arg):
        try:
            js_code = _to_str(ctypes.cast(arg, ctypes.c_char_p))
            self.webview_eval(w, js_code)
        except:
            pass


from .forge import ChromeForge


class ChromeWebView(Webview):
    """
    Electronic Mojo Engine for Pytron.
    A professional, Chromium-based alternative to the native webview.
    """

    def __init__(self, config):
        self.logger = logging.getLogger("Pytron.ChromeWebView")

        # 1. Resolve Binary (Production vs Development)
        shell_path = config.get("engine_path")
        if not shell_path:
            # A. Global Engine Path (Forge)
            global_path = os.path.expanduser("~/.pytron/engines/chrome/electron.exe")
            if os.path.exists(global_path):
                shell_path = global_path
            else:
                # B. Local Workspace Path (Dev)
                search_path = os.path.abspath(
                    os.path.join(
                        os.getcwd(),
                        "..",
                        "pytron-electron-engine",
                        "bin",
                        "electron.exe",
                    )
                )
                if os.path.exists(search_path):
                    shell_path = search_path
                else:
                    # C. Package Path (Fallback)
                    # Support for "Renamed Engine" (Grouping fix)
                    renamed_engine = None
                    if getattr(sys, "frozen", False):
                        exe_name = os.path.splitext(os.path.basename(sys.executable))[0]
                        candidate_name = f"{exe_name}-Engine.exe"

                        # 1. Check next to main exe (legacy/flat)
                        flat_path = os.path.join(
                            os.path.dirname(sys.executable), candidate_name
                        )
                        if os.path.exists(flat_path):
                            renamed_engine = flat_path

                        # 2. Check in standard engine dir
                        if not renamed_engine:
                            std_dir_path = os.path.abspath(
                                os.path.join(
                                    os.path.dirname(__file__),
                                    "..",
                                    "..",
                                    "dependancies",
                                    "chrome",
                                    candidate_name,
                                )
                            )
                            if os.path.exists(std_dir_path):
                                renamed_engine = std_dir_path

                    if renamed_engine:
                        shell_path = renamed_engine
                    else:
                        package_path = os.path.abspath(
                            os.path.join(
                                os.path.dirname(__file__),
                                "..",
                                "..",
                                "dependancies",
                                "chrome",
                                "electron.exe",
                            )
                        )
                        if os.path.exists(package_path):
                            shell_path = package_path
                        else:
                            # D. AUTO-PROVISION!
                            self.logger.warning(
                                "Chrome Engine not found. Auto-provisioning..."
                            )
                            forge = ChromeForge()
                            shell_path = forge.provision()

        self.logger.info(f"Using Chrome Shell (v3): {shell_path}")
        self.adapter = ChromeAdapter(shell_path, config)
        self.bridge = ChromeBridge(self.adapter)
        self._bound_functions = {}

        # 2. Context SWAP & Global Patching (Permanent)
        # We replace the native lib with our Bridge PERMANENTLY for this session.
        import pytron.webview as wv

        wv.lib = self.bridge

        if platform.system() == "Windows":
            try:
                from ...platforms.windows_ops import utils as win_utils

                win_utils.lib = self.bridge
            except ImportError:
                pass

        self.adapter.start()
        self.adapter.bind_raw(self._handle_ipc_message)
        super().__init__(config)

    def _handle_ipc_message(self, msg):
        import inspect
        import asyncio

        msg_type = msg.get("type")
        payload = msg.get("payload")

        # HWND Sync
        if (
            msg_type == "lifecycle"
            and isinstance(payload, dict)
            and payload.get("event") == "window_created"
        ):
            hwnd_str = payload.get("hwnd")
            try:
                self.bridge.real_hwnd = int(hwnd_str)
                self.logger.info(f"Acquired Electron HWND: {self.bridge.real_hwnd}")
            except:
                pass
            return

        if msg_type == "ipc":
            event = payload.get("event")
            inner_payload = payload.get("data", {})
            if isinstance(inner_payload, dict) and "data" in inner_payload:
                args = inner_payload.get("data", [])
                seq = inner_payload.get("id")
            else:
                args = inner_payload
                seq = None

            if event in self._bound_functions:
                func = self._bound_functions[event]
                try:
                    result = func(*args) if isinstance(args, list) else func(args)

                    if inspect.iscoroutine(result):
                        try:
                            result = asyncio.run(result)
                        except RuntimeError:
                            pass

                    safe_obj = pytron_serialize(result, None)
                    serialized_json = json.dumps(safe_obj)

                    if seq:
                        self.bridge.webview_return(
                            self.w, seq.encode("utf-8"), 0, serialized_json
                        )
                except Exception as e:
                    self.logger.error(f"Mojo IPC Error in {event}: {e}")
                    if seq:
                        safe_err = pytron_serialize(str(e), None)
                        self.bridge.webview_return(
                            self.w, seq.encode("utf-8"), 1, json.dumps(safe_err)
                        )

    def bind(self, name, func, run_in_thread=True, secure=False):
        self._bound_functions[name] = func
        self.bridge.webview_bind(self.w, name.encode("utf-8"), None, None)

    # --- Feature Overrides (Compatibility Layer) ---

    def center(self):
        self.bridge.adapter.send({"action": "center"})

    def set_icon(self, icon_path):
        pass

    def minimize(self):
        self.bridge.adapter.send({"action": "minimize"})

    def show(self):
        self.bridge.webview_show(self.w)

    def hide(self):
        self.bridge.webview_hide(self.w)

    def close(self, force=False):
        self.bridge.webview_destroy(self.w)

    def set_title(self, title):
        self.bridge.webview_set_title(self.w, title.encode("utf-8"))

    def set_size(self, w, h):
        self.bridge.webview_set_size(self.w, w, h, 0)

    def navigate(self, url):
        self.bridge.webview_navigate(self.w, url.encode("utf-8"))

    def eval(self, js):
        self.bridge.webview_eval(self.w, js)

    def toggle_maximize(self):
        self.bridge.adapter.send({"action": "toggle_maximize"})

    def make_frameless(self):
        self.bridge.adapter.send({"action": "set_frameless", "frameless": True})

    def start_drag(self):
        pass

    def set_menu(self, menu_bar):
        pass

    def start(self):
        try:
            if self.adapter.process:
                # Use a loop with timeout to allow for signal processing (like Ctrl+C)
                while self.adapter.process.poll() is None:
                    try:
                        self.adapter.process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        continue
        except KeyboardInterrupt:
            self.close()
        finally:
            self.logger.info("Chrome Engine stopped.")
