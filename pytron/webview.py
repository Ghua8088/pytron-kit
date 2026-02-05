import sys
import json
import time
import threading
import asyncio
import inspect
import pathlib
import platform
import mimetypes
import logging
import os
import base64
from collections import deque

# Import Native Engine
try:
    from .dependencies import pytron_native
except ImportError:
    # Fallback to check if it's in path
    sys.path.append(os.path.join(os.path.dirname(__file__), "dependencies"))
    try:
        import pytron_native
    except ImportError:
        print("[CRITICAL] Could not load pytron_native engine.")
        pytron_native = None

import urllib.parse
from .serializer import pytron_serialize
from .exceptions import ConfigError

IS_ANDROID = False


# -------------------------------------------------------------------
# Browser wrapper (Native PyO3 Version)
# -------------------------------------------------------------------
class Webview:
    def __init__(self, config):
        if not pytron_native:
            raise ImportError(
                "Pytron Native Engine (pyd) is missing. Run build_engine.py."
            )

        self.config = config
        self.logger = logging.getLogger("Pytron.Webview")
        self.id = config.get("id") or str(int(time.time() * 1000))

        # 1. Resolve Root
        if getattr(sys, "frozen", False):
            self._app_root = pathlib.Path(sys.executable).parent
            if hasattr(sys, "_MEIPASS"):
                self._app_root = pathlib.Path(sys._MEIPASS)
        else:
            self._app_root = pathlib.Path.cwd()

        # 2. Performance Init
        self.app = config.get("__app__")
        if self.app:
            self.thread_pool = self.app.thread_pool
        else:
            self.thread_pool = __import__(
                "concurrent.futures"
            ).futures.ThreadPoolExecutor(max_workers=5)

        self._bound_functions = {}
        self._served_data = {}

        # 3. Native Engine Initialization
        # 3. Native Engine Initialization
        # Logic to determine Root Path for Virtual Host (pytron://app/)
        raw_url = config.get("url", "")
        debug = config.get("debug", False)

        root_path = str(self._app_root)
        final_url = raw_url

        # Check if URL looks like a local file path
        if not raw_url.startswith(("http:", "https:", "pytron:")):
            path_obj = pathlib.Path(raw_url)
            if not path_obj.is_absolute():
                path_obj = (self._app_root / path_obj).resolve()

            if path_obj.exists():
                # Valid local file found.
                # Map its parent dir as the App Root.
                root_path = str(path_obj.parent)
                # URL becomes https://pytron.localhost/app/<filename>
                final_url = (
                    f"https://pytron.localhost/app/{urllib.parse.quote(path_obj.name)}"
                )
            else:
                # Fallback
                root_path = str(path_obj.parent)
                final_url = (
                    f"https://pytron.localhost/app/{urllib.parse.quote(path_obj.name)}"
                )

        self.root_path = root_path  # Store for later navigations
        self.logger.info(
            f"Native Engine Init: URL={final_url}, VirtualRoot={root_path}"
        )

        resizable = config.get("resizable", True)
        frameless = config.get("frameless", False)

        try:
            # DELAYED NAVIGATION:
            # We initialize with about:blank to ensure the window is created and
            # bindings can be registered (via UserEvent::Bind) BEFORE the real app loads.
            # This prevents race conditions where IPC calls happen before callbacks are ready.
            self._start_url = final_url
            self.native = pytron_native.NativeWebview(
                debug,
                "about:blank",  # Start empty
                root_path,
                bool(resizable),
                bool(frameless),
            )
        except TypeError:
            # Fallback if pyd wasn't updated yet? No, we will rebuild.
            raise ImportError("Native Engine signature mismatch. Please rebuild.")

        # 4. Bindings
        self._init_bindings()

        # 5. Window Settings
        self.set_title(config.get("title", "Pytron App"))
        w, h = config.get("dimensions", [800, 600])
        self.set_size(w, h)

        # Apply strict window settings via Hacks/Bindings for properties not covered in Init
        if config.get("always_on_top", False):
            self.set_always_on_top(True)

        if config.get("fullscreen", False):
            self.set_fullscreen(True)

        if config.get("start_maximized", False):
            self.native.maximize()

        if config.get("min_size") or config.get("max_size"):
            self.logger.warning(
                "Native Engine: min_size/max_size are not currently supported without rebuild. Ignoring."
            )

        # 6. Platform Helpers (Windows)
        self._platform = None
        if platform.system() == "Windows":
            try:
                from .platforms.windows import WindowsImplementation

                self._platform = WindowsImplementation()
            except Exception as e:
                self.logger.warning(f"Failed to load Windows Platform helpers: {e}")

        if not config.get("start_hidden", False):
            self.show()

        # 7. Event Loop (Asyncio)
        self.loop = asyncio.new_event_loop()

        def start_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        t = threading.Thread(target=start_loop, daemon=True)
        t.start()

        # 8. JS Init (Legacy shim)
        init_js = f"""
        (function() {{
            window.pytron = window.pytron || {{}};
            window.pytron.is_ready = true;
            window.pytron.id = "{self.id}";
        }})();
        """
        self.eval(init_js)

        # Apply UI settings (Context Menu, BG) for initial load
        self._apply_ui_settings()

    def start(self):
        self.logger.info("Starting Native Event Loop...")

        # Register Native Event Handlers (Direct Binding)
        self.native.bind("pytron_on_close", self._on_close_requested)
        self.native.bind("pytron_tray_click", self._on_tray_click)

        # Configure Close Behavior
        if self.config.get("close_to_tray", False):
            self.logger.info("Enabling Close-to-Tray behavior.")
            self.set_prevent_close(True)

        # Trigger initial navigation now that bindings are (presumably) queued
        if hasattr(self, "_start_url"):
            self.logger.info(f"Navigating to start URL: {self._start_url}")
            self.navigate(self._start_url)

        self.native.run()

    def _init_bindings(self):
        # 1. CORE SYSTEM BINDINGS (Prefixed with pytron_ to avoid user collisions)
        self.bind("pytron_set_title", self.set_title, run_in_thread=False)
        self.bind("pytron_set_size", self.set_size, run_in_thread=False)
        self.bind("pytron_close", self.close, run_in_thread=False)
        self.bind("pytron_reload", self.reload, run_in_thread=False)
        self.bind("pytron_toggle_maximize", self.toggle_maximize, run_in_thread=False)
        self.bind("pytron_hide", self.hide, run_in_thread=False)
        self.bind("pytron_show", self.show, run_in_thread=False)
        self.bind("pytron_minimize", self.minimize, run_in_thread=False)
        self.bind("pytron_maximize", self.maximize, run_in_thread=False)
        self.bind("pytron_center", self.center, run_in_thread=False)
        self.bind("pytron_sync_state", self._sync_state, run_in_thread=False)
        self.bind("__pytron_vap_get", self._get_binary_asset, run_in_thread=True)
        self.bind("pytron_serve_asset", self._serve_asset_callback, run_in_thread=False)
        self.bind(
            "pytron_set_slim_titlebar", self.set_slim_titlebar, run_in_thread=False
        )

        # 2. SYSTEM TOOLING / DIALOGS (Prefixed)
        self.bind("pytron_dialog_open_file", self.dialog_open_file, run_in_thread=True)
        self.bind("pytron_dialog_save_file", self.dialog_save_file, run_in_thread=True)
        self.bind(
            "pytron_dialog_open_folder", self.dialog_open_folder, run_in_thread=True
        )
        self.bind("pytron_message_box", self.message_box, run_in_thread=True)
        self.bind(
            "pytron_system_notification", self.system_notification, run_in_thread=True
        )
        self.bind(
            "pytron_set_taskbar_progress", self.set_taskbar_progress, run_in_thread=True
        )

        # 3. CLEAN ALIASES (Convenience for JS users, but can be overwritten)
        # Avoid logging for frequent state/asset syncs
        self._spammy_methods = {
            "pytron_sync_state",
            "pytron_serve_asset",
            "__pytron_vap_get",
        }
        self.bind("close", self.close, run_in_thread=False)
        self.bind("hide", self.hide, run_in_thread=False)
        self.bind("show", self.show, run_in_thread=False)
        self.bind("minimize", self.minimize, run_in_thread=False)
        self.bind("maximize", self.maximize, run_in_thread=False)
        self.bind("center", self.center, run_in_thread=False)
        self.bind("reload", self.reload, run_in_thread=False)
        self.bind("toggle_maximize", self.toggle_maximize, run_in_thread=False)
        self.bind("set_title", self.set_title, run_in_thread=False)
        self.bind("set_size", self.set_size, run_in_thread=False)
        self.bind("set_slim_titlebar", self.set_slim_titlebar, run_in_thread=False)
        self.bind("dialog_open_file", self.dialog_open_file, run_in_thread=True)
        self.bind("dialog_save_file", self.dialog_save_file, run_in_thread=True)
        self.bind("dialog_open_folder", self.dialog_open_folder, run_in_thread=True)
        self.bind("message_box", self.message_box, run_in_thread=True)
        self.bind("system_notification", self.system_notification, run_in_thread=True)
        self.bind("set_taskbar_progress", self.set_taskbar_progress, run_in_thread=True)

    def _serve_asset_callback(self, key):
        """Called by Native Engine Protocol Handler to fetch VAP assets."""
        if key in self._served_data:
            data, mime = self._served_data[key]
            return (data, mime)
        return None

    def set_slim_titlebar(self, enable=True):
        if hasattr(self.native, "set_decorations"):
            # enable slim -> disable decorations
            self.native.set_decorations(not enable)

    @property
    def hwnd(self):
        if hasattr(self.native, "get_hwnd"):
            return self.native.get_hwnd()
        return getattr(self, "_hwnd_cache", 0)

    # ... Bindings Logic ... (omitted for brevity, assume existing)
    def bind(self, name, python_func, run_in_thread=True, secure=False):
        is_async = inspect.iscoroutinefunction(python_func)

        # The Wrapper that Rust calls: (seq, args_json, ptr)
        def _native_callback(seq, req, arg_ptr):
            try:
                args = json.loads(req) if req else []
            except Exception:
                args = []

            # Internal logging
            if not name.startswith("inspector_") and name not in self._spammy_methods:
                self.logger.debug(f"IPC Call: {name}({args})")

            # Result serializer
            def _serialize_result(res):
                return pytron_serialize(res, vap_provider=self.serve_data)

            # Response Helper
            def _respond(status, result):
                res_str = json.dumps(result)
                self.native.return_result(seq, status, res_str)

            # Runner Logic
            def _runner():
                try:
                    res = python_func(*args)
                    _respond(0, _serialize_result(res))
                except Exception as e:
                    self.logger.error(f"Error in {name}: {e}")
                    _respond(1, str(e))

            async def _async_runner():
                try:
                    res = await python_func(*args)
                    _respond(0, _serialize_result(res))
                except Exception as e:
                    self.logger.error(f"Error in {name}: {e}")
                    _respond(1, str(e))

            if is_async:
                asyncio.run_coroutine_threadsafe(_async_runner(), self.loop)
            else:
                if run_in_thread:
                    self.thread_pool.submit(_runner)
                else:
                    _runner()

        # Register with Rust
        self.native.bind(name, _native_callback)

    # --- Core API ---

    def navigate(self, url):
        target = self._normalize_to_pytron(url)
        self.config["url"] = target
        self.native.navigate(target)
        # Attempt to apply UI settings (Context Menu, BG) via JS for Native Engine
        # Note: This might race with page load clearing scripts, but it's best effort.
        self._apply_ui_settings()

    def _normalize_to_pytron(self, url):
        """Ensures local file paths are converted to pytron://app/ URLs relative to root_path."""
        if url.startswith(("http:", "https:", "pytron:")):
            return url

        path_obj = pathlib.Path(url)
        if not path_obj.is_absolute():
            # If relative, assuming relative to root_path or app_root?
            # Usually relative to cwd.
            path_obj = pathlib.Path.cwd() / path_obj

        # Check if it resides within self.root_path
        try:
            root = pathlib.Path(self.root_path)
            # relative_to throws ValueError if not relative
            rel = path_obj.resolve().relative_to(root.resolve())
            # Use forward slashes for URL
            return f"https://pytron.localhost/app/{urllib.parse.quote(rel.as_posix())}"
        except (ValueError, Exception):
            # If outside root, we can't serve it via current pytron instance easily.
            # But maybe the current logic allows it if we didn't lock protocol_root?
            # (Native engine locks protocol_root).
            self.logger.warning(
                f"Navigate path {url} is outside protocol root {self.root_path}. Falling back to raw path (likely file://)."
            )
            return str(path_obj)

    def serve_data(self, key, data, mime_type):
        """
        Callback for serializing binary data used by plugins/VAP.
        Stores the data in memory to be served via __pytron_vap_get.
        """
        self._served_data[key] = (data, mime_type)
        # Use HTTPS scheme for Windows/Native compatibility
        return f"https://pytron.localhost/{key}"

    def _apply_ui_settings(self):
        """Applies UI configuration via JavaScript injection."""
        js = []

        # 1. Background Color (Fallback for Native)
        # bg = self.config.get("background_color")
        # if bg:
        #     js.append(f"try {{ document.documentElement.style.backgroundColor = '{bg}'; document.body.style.backgroundColor = '{bg}'; }} catch(e) {{}}")

        # 2. Context Menu
        if self.config.get("default_context_menu") is False:
            js.append(
                "try { document.addEventListener('contextmenu', e => e.preventDefault()); } catch(e) {}"
            )

        if js:
            # We use setTimeout to allow parsing to complete if called early
            full_script = (
                "(function(){ setTimeout(() => { " + " ".join(js) + " }, 100); })();"
            )
            self.eval(full_script)

    def set_title(self, title):
        self.native.set_title(title)

    def set_size(self, w, h):
        self.native.set_size(w, h, 0)

    def eval(self, js):
        self.native.eval(js)

    def reload(self):
        self.native.eval("location.reload()")

    def close(self, force=False):
        """
        Closes the window.
        If 'close_to_tray' config is True and force is False, it just hides the window.
        """
        if not force and self.config.get("close_to_tray", False):
            self.hide()
            # If we hide, we might want to notify or ensure tray exists?
            # Assuming App deals with that.
            return

        self.native.terminate()

    def emit(self, event, data=None):
        """
        Emits a custom event to the frontend.
        Frontend can listen via window.addEventListener(event, ...)
        """
        import json

        payload = json.dumps(data)
        js = f"window.dispatchEvent(new CustomEvent('{event}', {{ detail: {payload} }}));"
        self.eval(js)

    # --- Asset Serving (VAP) ---
    # serve_data is defined above to return the URL.

    def _sync_state(self):
        if self.app:
            return self.app.state.to_dict()
        return {}

    # --- Path Normalizer ---
    def normalize_path(self, config):
        raw_url = config.get("url")
        if not raw_url:
            raise ConfigError("No URL Configured")

        if raw_url.startswith(("http:", "https:", "pytron:")):
            return

        path_obj = pathlib.Path(raw_url)
        if not path_obj.is_absolute():
            path_obj = (self._app_root / path_obj).resolve()

        # Convert to pytron://
        # Use localhost as authority to prevent "Origin null" issues
        config["url"] = path_obj.as_uri().replace("file:///", "pytron://localhost/")

    # --- Native Mappings ---
    def set_icon(self, icon_path):
        if self._platform and self.hwnd:
            self._platform.set_window_icon(self.hwnd, icon_path)

    def minimize(self):
        self.native.minimize()

    def toggle_maximize(self):
        # Native Toggle using HWND check because Native Engine is async state
        if sys.platform == "win32" and self.hwnd:
            import ctypes

            is_maximized = ctypes.windll.user32.IsZoomed(self.hwnd)
            if is_maximized:
                self.restore()
            else:
                self.maximize()
        else:
            self.native.maximize()

    def is_visible(self):
        """Checks if the window is currently visible."""
        # Use simple platform check if possible
        if sys.platform == "win32" and self.hwnd:
            import ctypes

            return bool(ctypes.windll.user32.IsWindowVisible(self.hwnd))
        return True  # Default fallback

    def hide(self):
        self.native.hide()

    def start_drag(self):
        self.native.start_drag()

    def set_always_on_top(self, enable):
        call_native = getattr(self.native, "set_always_on_top", None)
        if call_native:
            call_native(enable)
        elif sys.platform == "win32" and self.hwnd:
            import ctypes

            HWND_TOPMOST = -1
            HWND_NOTOPMOST = -2
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            z_order = HWND_TOPMOST if enable else HWND_NOTOPMOST
            ctypes.windll.user32.SetWindowPos(
                self.hwnd, z_order, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE
            )

    def set_resizable(self, enable):
        call_native = getattr(self.native, "set_resizable", None)
        if call_native:
            call_native(enable)

    def maximize(self):
        self.native.maximize()

    def unmaximize(self):
        if hasattr(self.native, "unmaximize"):
            self.native.unmaximize()

    def restore(self):
        self.unmaximize()

    def show(self):
        self.native.show()

    def set_fullscreen(self, enable):
        self.native.set_fullscreen(enable)

    def center(self):
        call_native = getattr(self.native, "center", None)
        if call_native:
            call_native()
        elif self._platform and self.hwnd:
            self._platform.center(self.hwnd)

    # --- Dialogs ---
    def dialog_open_file(self, *args, **kwargs):
        # Native Engine Impl (preferred)
        if hasattr(self.native, "dialog_open_file"):
            # args mapping: title, default_path, file_types
            # file_types in python: [("Images", "*.png;*.jpg"), ...]
            # file_types in native: "Images:png,jpg;Text:txt"

            title = kwargs.get("title") or (args[0] if args else "Open File")
            default_path = kwargs.get("default_path") or (
                args[1] if len(args) > 1 else None
            )
            file_types = kwargs.get("file_types") or (
                args[2] if len(args) > 2 else None
            )

            filters_str = None
            if file_types:
                parts = []
                for name_ft, pat in file_types:
                    # pat is like "*.png;*.jpg" -> "png,jpg"
                    exts = pat.replace("*.", "").replace(";", ",")
                    parts.append(f"{name_ft}:{exts}")
                filters_str = ";".join(parts)

            return self.native.dialog_open_file(title, default_path, filters_str)

        if self._platform and self.hwnd:
            return self._platform.open_file_dialog(self.hwnd, *args, **kwargs)
        return []

    def dialog_save_file(self, *args, **kwargs):
        if hasattr(self.native, "dialog_save_file"):
            title = kwargs.get("title", "Save File")
            default_path = kwargs.get("default_path")
            default_name = kwargs.get("default_name")
            file_types = kwargs.get("file_types")
            filters_str = None
            if file_types:
                parts = []
                for name, pat in file_types:
                    exts = pat.replace("*.", "").replace(";", ",")
                    parts.append(f"{name}:{exts}")
                filters_str = ";".join(parts)

            return self.native.dialog_save_file(
                title, default_path, default_name, filters_str
            )

        if self._platform and self.hwnd:
            return self._platform.save_file_dialog(self.hwnd, *args, **kwargs)
        return None

    def dialog_open_folder(self, *args, **kwargs):
        if hasattr(self.native, "dialog_open_folder"):
            title = kwargs.get("title", "Select Folder")
            default_path = kwargs.get("default_path")
            return self.native.dialog_open_folder(title, default_path)

        if self._platform and self.hwnd:
            return self._platform.open_folder_dialog(self.hwnd, *args, **kwargs)
        return None

    def message_box(self, *args, **kwargs):
        if hasattr(self.native, "message_box"):
            title = kwargs.get("title") or (args[0] if args else "Message")
            message = kwargs.get("message") or (args[1] if len(args) > 1 else "")
            style = kwargs.get("style") or (args[2] if len(args) > 2 else 0)

            # Map Windows MessageBox styles to Native levels
            # 0x10 = MB_ICONERROR, 0x30 = MB_ICONWARNING, 0x40 = MB_ICONINFORMATION
            level = "info"
            if isinstance(style, int):
                if style & 0x10:
                    level = "error"
                elif style & 0x30:
                    level = "warning"

            return self.native.message_box(title, message, level)

        if self._platform and self.hwnd:
            return self._platform.message_box(self.hwnd, *args, **kwargs)
        return 0

    def set_taskbar_progress(self, state="normal", value=0, max_value=100):
        # State mapping: normal, error, paused, indeterminate, none
        # Native Lib expects: 2=Normal, 4=Error, 8=Paused

        # 1. Try Native Engine Implementation (if reliable) (Disabled until user confirms lib.rs update)
        if hasattr(self.native, "set_taskbar_progress"):
            s_map = {
                "normal": 2,
                "error": 4,
                "paused": 8,
                "indeterminate": 1,
                "none": 0,
            }
            s_code = s_map.get(state, 0)
            self.native.set_taskbar_progress(s_code, int(value), int(max_value))
            return

        # 2. Fallback to Platform Helper (needs valid HWND)
        if self._platform and self.hwnd:
            self._platform.set_taskbar_progress(self.hwnd, state, value, max_value)

    def system_notification(self, title, message, icon=None):
        if self._platform and self.hwnd:
            if not icon:
                icon = self.config.get("icon")
            self._platform.notification(self.hwnd, title, message, icon)

    # --- Native Tray & Close Handling ---
    def create_tray(self, icon_path, tooltip="Pytron App"):
        if hasattr(self.native, "create_tray"):
            self.native.create_tray(icon_path, tooltip)

    def set_prevent_close(self, prevent):
        if hasattr(self.native, "set_prevent_close"):
            self.native.set_prevent_close(prevent)

    def _on_close_requested(self):
        """Called by Native Engine when X is clicked and prevent_close is True."""
        if self.config.get("close_to_tray", False):
            self.hide()
        else:
            # Should not happen if prevent_close logic is consistent, but fallback
            self.native.terminate()

    def _get_binary_asset(self, key):
        """
        Retrieves an asset for the VAP bridge.
        Returns {'raw': <binary_string>, 'mime': <mime_type>} or None.
        """
        # 1. Check Memory Cache (_served_data)
        if key in self._served_data:
            data, mime = self._served_data[key]
            # Convert bytes to "latin-1" string for JS binary interop
            raw = data.decode("latin-1")
            return {"raw": raw, "mime": mime}

        # 2. Check File System (if key is a relative path)
        try:
            # Security: Prevent escaping root
            possible_path = (self._app_root / key).resolve()
            if (
                str(possible_path).startswith(str(self._app_root))
                and possible_path.exists()
                and possible_path.is_file()
            ):
                import mimetypes

                mime, _ = mimetypes.guess_type(str(possible_path))
                with open(possible_path, "rb") as f:
                    data = f.read()
                    raw = data.decode("latin-1")
                    return {"raw": raw, "mime": mime or "application/octet-stream"}
        except Exception:
            pass

        return None

    def _on_tray_click(self, menu_id):
        """Called by Native Engine when tray menu is clicked."""
        self.logger.info(f"Tray Click: {menu_id}")
        if str(menu_id) == "1001" or str(menu_id) == "Quit":  # Approx
            self.native.terminate()
        elif str(menu_id) == "1000" or str(menu_id) == "Show":  # Approx
            self.show()
            self.native.set_visible(True)
            if sys.platform == "win32":
                self.minimize()  # Hack to restore? No, show() involves restore.
                self.native.minimize()
                self.native.show()  # Force restore from minimize

    # Redundant _init_bindings removed.
    def expose(self, entity):
        if callable(entity) and not isinstance(entity, type):
            self.bind(entity.__name__, entity)
            return entity
        if isinstance(entity, type):
            instance = entity()
            for name in dir(instance):
                if not name.startswith("_") and callable(getattr(instance, name)):
                    self.bind(name, getattr(instance, name))
            return entity
