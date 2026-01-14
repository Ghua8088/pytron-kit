import os
import sys
import json
import logging
import threading
import subprocess
import time
import uuid
import platform
import ctypes
import pathlib
from .webview import Webview
from .serializer import pytron_serialize

logger = logging.getLogger("Pytron.ChromeWebView")


class ChromeBridge:
    """Mocks the native 'lib' DLL interface but redirects to Chrome Shell via IPC."""

    def __init__(self, adapter):
        self.adapter = adapter
        self._callbacks = {}

    def webview_create(self, debug, window):
        return 1  # Dummy handle

    def webview_set_title(self, w, title):
        self.adapter.send({"action": "set_title", "title": title.decode("utf-8")})

    def webview_set_size(self, w, width, height, hints):
        self.adapter.send({"action": "set_size", "width": width, "height": height})

    def webview_navigate(self, w, url):
        self.adapter.send({"action": "navigate", "url": url.decode("utf-8")})

    def webview_eval(self, w, js):
        self.adapter.send({"action": "eval", "code": js.decode("utf-8")})

    def webview_init(self, w, js):
        self.adapter.send({"action": "init_script", "js": js.decode("utf-8")})

    def webview_run(self, w):
        # The main process loop is managed by the shell process.
        # We just wait for it to exit if needed.
        if self.adapter.process:
            self.adapter.process.wait()

    def webview_destroy(self, w):
        self.adapter.send({"action": "close"})

    def webview_bind(self, w, name, fn, arg):
        n = name.decode("utf-8")
        self._callbacks[n] = fn
        self.adapter.send({"action": "bind", "name": n})

    def webview_return(self, w, seq, status, result):
        # Respond to an async call
        seq_str = seq.decode("utf-8") if isinstance(seq, bytes) else str(seq)
        res_str = result.decode("utf-8") if isinstance(result, bytes) else str(result)
        self.adapter.send(
            {
                "action": "reply",
                "id": seq_str,
                "status": status,
                "result": json.loads(res_str),  # Re-parse to send as structured JSON
            }
        )

    def webview_dispatch(self, w, fn, arg):
        # Standard lib uses this for main-thread execution.
        # Our Chrome shell is already async, so we'll just execute.
        # Note: arg in current Pytron is often a JS string for eval.
        import ctypes

        js_code = ctypes.cast(arg, ctypes.c_char_p).value
        self.webview_eval(w, js_code)


class ChromeWebView(Webview):
    """
    Experimental Chrome-based WebView engine for Pytron.
    Uses a custom 'Chrome Shell' (stripped Electron/Chromium) with Mojo-style IPC.
    """

    def __init__(self, config):
        # 1. SETUP THE ADAPTER
        from .apputils.chrome_ipc import ChromeAdapter

        shell_path = config.get("engine_path")
        if not shell_path:
            shell_path = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "..",
                    "pytron-electron-engine",
                    "bin",
                    "electron.exe",
                )
            )

        self.adapter = ChromeAdapter(shell_path, config)
        self.bridge = ChromeBridge(self.adapter)

        # 2. THE CONTEXT SWAP (Professional Engine Injection)
        # We temporarily replace the module-level 'lib' with our bridge.
        # This allows super().__init__ to set up everything (VAP, bindings, state sync)
        # without touching the actual webview.dll.
        self.logger = logging.getLogger("Pytron.ChromeWebView")
        self._bound_functions = {}

        import pytron.webview as wv

        original_lib = wv.lib
        wv.lib = self.bridge

        try:
            # Spawning the shell first ensures the bridge is ready when init_script calls come
            self.adapter.start()
            self.adapter.bind_raw(self._handle_ipc_message)

            # This will call webview_create (returning 1) and webview_init
            super().__init__(config)
        finally:
            wv.lib = original_lib

    def _handle_ipc_message(self, msg):
        """Dispatches messages from the Mojo pipe."""
        if msg.get("type") == "ipc":
            event = msg.get("payload", {}).get("event")
            inner_payload = msg.get("payload", {}).get("data", {})
            if isinstance(inner_payload, dict) and "data" in inner_payload:
                args = inner_payload.get("data", [])
                seq = inner_payload.get("id")
            else:
                args = inner_payload
                seq = None

            if event in self._bound_functions:
                func = self._bound_functions[event]
                try:
                    import inspect
                    import asyncio

                    # Execute
                    if isinstance(args, list):
                        result = func(*args)
                    else:
                        result = func(args)

                    # Handle Async
                    if inspect.iscoroutine(result):
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                        result = loop.run_until_complete(result)

                    # Serialize (Handle Images, etc.)
                    serialized_result = self._serialize_result(result)

                    if seq:
                        self.bridge.webview_return(
                            self.w, seq.encode("utf-8"), 0, serialized_result
                        )
                except Exception as e:
                    self.logger.error(f"Mojo IPC Error in {event}: {e}")
                    if seq:
                        self.bridge.webview_return(
                            self.w, seq.encode("utf-8"), 1, json.dumps(str(e))
                        )

    def _serialize_result(self, obj):
        try:
            return json.dumps(obj)
        except TypeError:
            # Handle PIL Images
            if hasattr(obj, "save") and hasattr(obj, "format"):
                import io
                import base64

                buffered = io.BytesIO()
                obj.save(buffered, format="PNG")
                return json.dumps(
                    f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"
                )
            return json.dumps(str(obj))

    def bind(self, name, func, run_in_thread=True, secure=False):
        # Re-implement bind for the Chrome shell
        self._bound_functions[name] = func
        self.bridge.webview_bind(self.w, name.encode("utf-8"), None, None)

    # --- Window Methods (Override to avoid invalid handle errors) ---
    def center(self):
        # We can implement this in the bridge later
        pass

    def set_icon(self, icon_path):
        # We can handle this in the bridge later
        pass

    def minimize(self):
        self.bridge.webview_set_size(self.w, 0, 0, 0)  # Dummy or use proper action

    def show(self):
        pass

    def hide(self):
        pass

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

    def start(self):
        if self.adapter.process:
            self.adapter.process.wait()
