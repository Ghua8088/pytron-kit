import ctypes
import sys
import json
import time
import threading
import asyncio
import inspect
import pathlib
import platform
import mimetypes
from collections import deque
import logging
import os
from .bindings import lib, dispatch_callback, BindCallback, IS_ANDROID
import base64
from .serializer import pytron_serialize
from .exceptions import ResourceNotFoundError, BridgeError, ConfigError
from .platforms.interface import PlatformInterface


# -------------------------------------------------------------------
# Callback handler for dispatch
# -------------------------------------------------------------------
def _dispatch_handler(window_ptr, arg_ptr):
    js_code = ctypes.cast(arg_ptr, ctypes.c_char_p).value  # read JS code
    # Fix: Explicitly cast to c_void_p to prevent "int too long to convert" on 64-bit systems
    lib.webview_eval(ctypes.c_void_p(window_ptr), js_code)


c_dispatch_handler = dispatch_callback(_dispatch_handler)


# -------------------------------------------------------------------
# Browser wrapper
# -------------------------------------------------------------------
class Webview:
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger("Pytron.Webview")

        # SECURITY/CORS: Fix for "origin 'null'" and CORS issues with file:// and ES Modules in WebView2.
        # This allows Vite builds (type="module") to load correctly over the file:// scheme.
        if not IS_ANDROID and platform.system() == "Windows":
             # --allow-file-access-from-files: Allows file:// to fetch other file:// resources.
             # --disable-web-security: Permissive mode for complex ESM module graphs over custom schemes/file.
             args = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
             if "--allow-file-access-from-files" not in args:
                 os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"{args} --allow-file-access-from-files --disable-web-security"

        # PERFORMANCE: Use shared thread pool from App if available
        self.app = config.get("__app__")
        if self.app:
            self.thread_pool = self.app.thread_pool
        else:
            self.thread_pool = __import__(
                "concurrent.futures"
            ).futures.ThreadPoolExecutor(max_workers=5)

        self._gc_protector = deque(maxlen=50)
        self._bound_functions = {}
        self._served_data = {}

        # ------------------------------------------------
        # NATIVE ENGINE INITIALIZATION
        # ------------------------------------------------
        shield_ptr = os.environ.get("PYTRON_SHIELD_WINDOW_PTR")
        if shield_ptr:
            # Use the window created by the Rust bootloader
            self.w = ctypes.c_void_p(int(shield_ptr))
            self.logger.debug(f"Shielded Mode: Attaching to native window {shield_ptr}")
        else:
            # Fix: Store as c_void_p object to ensure consistent pointer handling on 64-bit systems
            raw_ptr = lib.webview_create(int(config.get("debug", False)), None)
            self.w = ctypes.c_void_p(raw_ptr)
            
        self._cb = c_dispatch_handler

        # ------------------------------------------------
        # PLATFORM INITIALIZATION
        # ------------------------------------------------
        CURRENT_PLATFORM = platform.system()
        self._platform = PlatformInterface()

        if not IS_ANDROID:
            if CURRENT_PLATFORM == "Windows":
                from .platforms.windows import WindowsImplementation
                self._platform = WindowsImplementation()
            elif CURRENT_PLATFORM == "Linux":
                from .platforms.linux import LinuxImplementation
                self._platform = LinuxImplementation()
            elif CURRENT_PLATFORM == "Darwin":
                from .platforms.darwin import DarwinImplementation
                self._platform = DarwinImplementation()

        # Default Bindings
        self.bind("pytron_minimize", lambda: self.minimize(), run_in_thread=False)
        self.bind("pytron_close", self.close, run_in_thread=False)
        self.bind(
            "pytron_toggle_maximize",
            lambda: self.toggle_maximize(),
            run_in_thread=False,
        )
        self.bind("pytron_drag", lambda: self.start_drag(), run_in_thread=False)
        self.bind("pytron_set_title", self.set_title, run_in_thread=False)
        self.bind("pytron_set_size", self.set_size, run_in_thread=False)
        self.bind("pytron_center", self.center, run_in_thread=False)
        self.bind("pytron_set_bounds", self.set_bounds, run_in_thread=False)

        # New Daemon bindings
        self.bind("pytron_hide", lambda: self.hide(), run_in_thread=False)
        self.bind("pytron_show", lambda: self.show(), run_in_thread=False)
        self.bind(
            "pytron_system_notification", self.system_notification, run_in_thread=True
        )
        self.bind(
            "pytron_set_taskbar_progress", self.set_taskbar_progress, run_in_thread=True
        )
        self.bind("pytron_notify", self.notify, run_in_thread=False)
        self.bind("pytron_open_devtools", self.open_devtools, run_in_thread=False)

        # Dialog bindings
        self.bind("pytron_dialog_open_file", self.dialog_open_file, run_in_thread=True)
        self.bind("pytron_dialog_save_file", self.dialog_save_file, run_in_thread=True)
        self.bind(
            "pytron_dialog_open_folder", self.dialog_open_folder, run_in_thread=True
        )
        self.bind("pytron_message_box", self.message_box, run_in_thread=True)
        # Compatibility binding for UI components
        self.bind("get_registered_shortcuts", lambda: [], run_in_thread=False)

        # Asset Provider (Performance Bridge)
        # This provides a port-less, high-performance O(1) binary bridge.
        # It handles pytron:// URLs via window.fetch and the Latin-1 trick.
        self._served_data = {}
        
        def _get_binary_asset(key):
            """Returns (mime, raw_latin1_data) with Path Traversal Protection."""
            data, mime = None, "application/octet-stream"
            
            # 1. Check Memory
            if key in self._served_data:
                data, mime = self._served_data[key]
            
            # 2. Check Disk (Virtual Mapping for the app)
            elif key.startswith("app/"):
                rel_path = key[4:]
                app_dir = getattr(self, "_vap_app_dir", self._app_root)
                
                try:
                    # SECURITY: Sanitize path to prevent directory traversal
                    # This ensures the final path is INSIDE the app_dir
                    safe_path = os.path.normpath(rel_path).lstrip(os.path.sep).lstrip("/")
                    path_obj = (app_dir / safe_path).resolve()
                    
                    if not str(path_obj).startswith(str(app_dir.resolve())):
                         self.logger.warning(f"Security blocked path traversal attempt: {key}")
                         return None

                    if path_obj.exists() and path_obj.is_file():
                        mime, _ = mimetypes.guess_type(str(path_obj))
                        with open(path_obj, "rb") as f:
                            data = f.read()
                except Exception as e:
                    self.logger.error(f"Asset access error: {e}")
                    return None

            if data:
                return {"mime": mime or "application/octet-stream", "raw": data.decode('latin-1')}
            return None

        self.bind("__pytron_vap_get", _get_binary_asset, run_in_thread=True)

        # Legacy compatibility binding
        def _legacy_get_asset(key):
            asset = _get_binary_asset(key)
            if asset:
                # Convert back to Base64 for legacy clients
                data_b64 = base64.b64encode(asset["raw"].encode("latin-1")).decode("utf-8")
                return {"data": f"data:{asset['mime']};base64,{data_b64}"}
            return None
        self.bind("pytron_get_asset", _legacy_get_asset, run_in_thread=True)

        # Inject Virtual Fetch Interceptor
        # This allows the frontend to call fetch('pytron://...') for heavy assets
        # and get binary data with zero base64 overhead.
        init_js = """
        (function() {
            window.__pytron_fetch_interceptor_active = true;
            const originalFetch = window.fetch;
            
            function getPytronKey(url) {
                if (!url || typeof url !== 'string') return null;
                const match = url.match(/pytron:\/\/([^?#]+)/);
                return match ? match[1] : null;
            }

            window.fetch = async (input, init) => {
                const url = typeof input === 'string' ? input : (input ? input.url : '');
                const key = getPytronKey(url);
                
                if (key) {
                    console.log("[Pytron VAP] Intercepting fetch for key:", key);
                    const asset = await window.__pytron_vap_get(key);
                    if (asset) {
                        const bytes = new Uint8Array(asset.raw.length);
                        for (let i = 0; i < asset.raw.length; i++) {
                            bytes[i] = asset.raw.charCodeAt(i);
                        }
                        const blob = new Blob([bytes], {type: asset.mime});
                        return new Response(blob);
                    }
                    console.warn("[Pytron VAP] Asset not found in bridge:", key);
                    return new Response('Not Found', {status: 404});
                }
                return originalFetch(input, init);
            };

            // Global handler for pytron:// URLs in tags (Images, Scripts, Styles)
            async function handlePytronAsset(el) {
                if (!el || !el.tagName) return;
                const isLink = el.tagName === 'LINK';
                const isScript = el.tagName === 'SCRIPT';
                const attr = isLink ? 'href' : 'src';
                
                const rawUrl = el.getAttribute(attr);
                const key = getPytronKey(rawUrl) || getPytronKey(el[attr]);

                if (key && !el.__pytron_loading) {
                    el.__pytron_loading = true;
                    try {
                        console.log("[Pytron VAP] Reconciling asset key:", key, "for", el.tagName);
                        const res = await fetch(`pytron://${key}`);
                        if (res.ok) {
                            const blob = await res.blob();
                            const blobUrl = URL.createObjectURL(blob);
                            
                            if (isScript) {
                                const newScript = document.createElement('script');
                                Array.from(el.attributes).forEach(a => {
                                    if (a.name !== 'src') newScript.setAttribute(a.name, a.value);
                                });
                                newScript.src = blobUrl;
                                newScript.__pytron_loading = true;
                                el.parentNode.replaceChild(newScript, el);
                            } else {
                                if (el.__pytron_blob_url) URL.revokeObjectURL(el.__pytron_blob_url);
                                el.__pytron_blob_url = blobUrl;
                                el[attr] = blobUrl;
                            }
                        }
                    } catch (e) {
                        console.error("[Pytron VAP] Asset load failed:", e);
                    } finally {
                        el.__pytron_loading = false;
                    }
                }
            }

            // Observe the DOM for new assets or src/href changes
            const observer = new MutationObserver((mutations) => {
                for (const mutation of mutations) {
                    if (mutation.type === 'childList') {
                        mutation.addedNodes.forEach(node => {
                            if (['IMG', 'SCRIPT', 'LINK'].includes(node.tagName)) handlePytronAsset(node);
                            else if (node.querySelectorAll) {
                                node.querySelectorAll('img, script, link').forEach(handlePytronAsset);
                            }
                        });
                    } else if (mutation.type === 'attributes') {
                        if (['IMG', 'SCRIPT', 'LINK'].includes(mutation.target.tagName)) {
                            handlePytronAsset(mutation.target);
                        }
                    }
                }
            });

            const startObserver = () => {
                const target = document.documentElement || document.body;
                if (target) {
                    observer.observe(target, { 
                        childList: true, 
                        subtree: true, 
                        attributes: true, 
                        attributeFilter: ['src', 'href'] 
                    });
                } else {
                    setTimeout(startObserver, 5);
                }
            };
            startObserver();

            // Initial scan
            const scan = () => document.querySelectorAll('img, script, link').forEach(handlePytronAsset);
            if (document.readyState === 'loading') {
                window.addEventListener('DOMContentLoaded', scan);
            } else {
                scan();
            }
        })();
        """
        
        init_js += """
        console.log("[Pytron] Core Initialized");
        window.pytron = window.pytron || {};
        window.pytron.is_ready = true;
        """

        # Disable default context menu if requested in config, but allow it in debug mode
        if not config.get("default_context_menu", True) and not config.get("debug", False):
            init_js += (
                "\nwindow.addEventListener('contextmenu', e => e.preventDefault());"
            )

        # Development Shortcuts
        if config.get("debug", False):
            init_js += """
            window.addEventListener('keydown', e => {
                if ((e.ctrlKey && e.shiftKey && (e.key === 'I' || e.key === 'i')) || e.key === 'F12') {
                    if (typeof window.pytron_open_devtools === 'function') {
                        window.pytron_open_devtools();
                    }
                }
            });
            """

        lib.webview_init(self.w, init_js.encode("utf-8"))

        # self._served_data = {} # Removed: initialized earlier
        
        # Resolve App Root for reliable relative pathing
        if getattr(sys, "frozen", False):
            self._app_root = pathlib.Path(sys.executable).parent
            if hasattr(sys, "_MEIPASS"):
                self._app_root = pathlib.Path(sys._MEIPASS)
        else:
            main_script = sys.modules['__main__'].__file__ if '__main__' in sys.modules and hasattr(sys.modules['__main__'], '__file__') else None
            if main_script:
                self._app_root = pathlib.Path(main_script).parent
            else:
                self._app_root = pathlib.Path.cwd()

        self.normalize_path(config)

        self.loop = asyncio.new_event_loop()
        self.frameless = config.get("frameless", False)

        def start_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        t = threading.Thread(target=start_loop, daemon=True)
        t.start()

        # Setters
        self.set_title(config.get("title", "Pytron App"))
        width, height = config.get("dimensions", [800, 600])
        self.set_size(width, height)
        if "icon" in config:
            self.set_icon(config["icon"])

        if self.frameless:
            self.make_frameless()

        if config.get("debug", False):
            self.logger.debug(f"Debug mode active. Native webview_debug available: {hasattr(lib, 'webview_debug')}")
            if hasattr(lib, "webview_debug"):
                try:
                    lib.webview_debug(self.w)
                except Exception as e:
                    self.logger.warning(f"Could not launch debug window: {e}")

        if config.get("navigate_on_init", True):
            self.navigate(config["url"])

    def _return_result(self, seq, status, result_json_str):
        lib.webview_return(self.w, seq, status, result_json_str.encode("utf-8"))

    def minimize(self):
        self._platform.minimize(self.w)

    def set_bounds(self, x, y, width, height):
        self._platform.set_bounds(self.w, x, y, width, height)

    def close(self, force=False):
        # Check for 'close_to_tray' setting
        if not force and self.config.get("close_to_tray", False):
            self.hide()
            return

        self._platform.close(self.w)

    def toggle_maximize(self):
        return self._platform.toggle_maximize(self.w)

    def open_devtools(self):
        """Opens the native developer tools window if supported."""
        if hasattr(lib, "webview_debug"):
            self.logger.debug(f"Opening DevTools for window: {self.w.value}")
            lib.webview_debug(self.w)
        else:
            self.logger.warning("Native DevTools (webview_debug) not supported by the current engine.")

    def make_frameless(self):
        self._platform.make_frameless(self.w)

    def start_drag(self):
        self._platform.start_drag(self.w)

    def set_title(self, title):
        lib.webview_set_title(self.w, title.encode("utf-8"))

    def set_size(self, w, h):
        lib.webview_set_size(self.w, w, h, 0)

    def hide(self):
        self._platform.hide(self.w)

    def show(self):
        self._platform.show(self.w)

    def system_notification(self, title, message, icon=None):
        if not icon and self.config:
            icon = self.config.get("icon")
        self._platform.notification(self.w, title, message, icon)

    def set_taskbar_progress(self, state="normal", value=0, max_value=100):
        if self._platform and hasattr(self._platform, "set_taskbar_progress"):
            self._platform.set_taskbar_progress(self.w, state, value, max_value)

    def set_icon(self, icon_path):
        self._platform.set_window_icon(self.w, icon_path)

    def center(self):
        """Centers the window on the primary screen."""
        if self._platform and hasattr(self._platform, "center"):
            self._platform.center(self.w)

    # --- Native Dialogs ---
    def dialog_open_file(self, title="Open File", default_path=None, file_types=None):
        return self._platform.open_file_dialog(self.w, title, default_path, file_types)

    def dialog_save_file(
        self, title="Save File", default_path=None, default_name=None, file_types=None
    ):
        return self._platform.save_file_dialog(
            self.w, title, default_path, default_name, file_types
        )

    def dialog_open_folder(self, title="Select Folder", default_path=None):
        return self._platform.open_folder_dialog(self.w, title, default_path)

    def message_box(self, title, message, style=0):
        # Styles: 0=OK, 1=OK/Cancel, 2=Abort/Retry/Ignore, 3=Yes/No/Cancel, 4=Yes/No, 5=Retry/Cancel
        # Returns: 1=OK, 2=Cancel, 6=Yes, 7=No
        return self._platform.message_box(self.w, title, message, style)

    def navigate(self, url):
        lib.webview_navigate(self.w, url.encode("utf-8"))

    def start(self):
        lib.webview_run(self.w)
        lib.webview_destroy(self.w)

    # -------------------------------------------------------------------
    # Safe JS -> Python Binding
    # -------------------------------------------------------------------
    def bind(self, name, python_func, run_in_thread=True, secure=False):
        """
        Exposes a Python function (Sync or Async) to JS.
        """

        # Check if the user passed an 'async def'
        is_async = inspect.iscoroutinefunction(python_func)

        def _callback(seq, req, arg):
            # 1. Parse Args
            try:
                args = json.loads(req) if req else []
            except json.JSONDecodeError:
                self.logger.warning(f"Failed to parse arguments for {name}")
                args = []
            except Exception as e:
                self.logger.error(f"Unexpected error parsing arguments for {name}: {e}")
                args = []

            self.logger.debug(f"Bound function : {name} invoked with args {args}")

            # ------------------------------------------------
            # SECURITY CHECK
            # ------------------------------------------------
            if secure:
                # 4=MB_YESNO. 6=IDYES
                confirm = self._platform.message_box(
                    self.w,
                    "Security Alert",
                    f"The application is attempting to execute a restricted function: '{name}'.\n\nAllow execution?",
                    4,
                )
                if confirm != 6:  # User did not click Yes
                    self.logger.warning(f"Security: User denied execution of {name}")
                    lib.webview_return(
                        self.w,
                        seq,
                        1,
                        json.dumps("User denied execution.").encode("utf-8"),
                    )
                    return

            # Helper for binary-optimized serialization
            def _serialize_result(res):
                # Pass serve_data as the VAP provider to avoid Base64
                return pytron_serialize(res, vap_provider=self.serve_data)

            # ------------------------------------------------
            # CASE A: ASYNC FUNCTION (Run in Background Loop)
            # ------------------------------------------------
            if is_async:

                async def _async_runner():
                    try:
                        result = await python_func(*args)
                        # Ensure result is JSON-serializable using Pytron's encoder
                        res_json = json.dumps(_serialize_result(result))
                        self._return_result(seq, 0, res_json)
                    except Exception as e:
                        self.logger.error(f"Async execution error in {name}: {e}")
                        err_json = json.dumps(str(e))
                        self._return_result(seq, 1, err_json)

                asyncio.run_coroutine_threadsafe(_async_runner(), self.loop)
            # ------------------------------------------------
            # CASE B: SYNC FUNCTION
            # ------------------------------------------------
            else:

                def _sync_runner():
                    try:
                        result = python_func(*args)
                        # Ensure result is JSON-serializable using Pytron's encoder
                        result_json = json.dumps(_serialize_result(result))
                        self._return_result(seq, 0, result_json)
                    except Exception as e:
                        self.logger.error(f"Execution error in {name}: {e}")
                        error_msg = json.dumps(str(e))
                        self._return_result(seq, 1, error_msg)

                if run_in_thread:
                    # Run in thread pool
                    self.thread_pool.submit(_sync_runner)
                else:
                    # Run immediately on Main Thread (Required for Window Controls like Drag)
                    _sync_runner()

        c_func = BindCallback(_callback)
        self._bound_functions[name] = c_func
        lib.webview_bind(self.w, name.encode("utf-8"), c_func, None)

    def _report_error(self, error_data):
        """
        Logs an error from the webview to the Python console.
        """
        msg = error_data.get("message", "Unknown error")
        source = error_data.get("source", "unknown")
        line = error_data.get("lineno", "?")
        col = error_data.get("colno", "?")
        stack = error_data.get("stack", "")

        err_msg = f"Webview Error: {msg} at {source}:{line}:{col}"
        self.logger.error(err_msg)
        if stack:
            self.logger.error(f"Stack trace:\n{stack}")

    # -------------------------------------------------------------------
    # Safe event dispatch to JS
    # -------------------------------------------------------------------
    def emit(self, event_name, data):
        # PERFORMANCE: Use optimized serialization with VAP support
        payload = json.dumps(pytron_serialize(data, vap_provider=self.serve_data))
        js_code = (
            f"window.dispatchEvent(new CustomEvent('{event_name}', "
            f"{{ detail: {payload} }}));"
        )
        self.eval(js_code)

    # -------------------------------------------------------------------
    # Notification Helper
    # -------------------------------------------------------------------
    def notify(self, title, message, type="info", duration=5000):
        """
        Sends a notification event to the frontend.
        """
        self.emit(
            "pytron:notification",
            {"title": title, "message": message, "type": type, "duration": duration},
        )

    def eval(self, js_code):
        def _thread_send():
            js_buf = ctypes.create_string_buffer(js_code.encode("utf-8"))
            self._gc_protector.append(js_buf)
            if len(self._gc_protector) > 50:
                self._gc_protector.pop(0)
            lib.webview_dispatch(self.w, self._cb, ctypes.cast(js_buf, ctypes.c_void_p))

        threading.Thread(target=_thread_send, daemon=True).start()

    def serve_data(self, key, data, mime_type="application/octet-stream"):
        """
        Serves binary data via pytron://<key> for high-performance IPC.
        Data is stored in memory and served via the registered custom scheme handler (O(1)).
        """
        if hasattr(self, "_served_data"):
            self._served_data[key] = (data, mime_type)
            self.logger.debug(
                f"Serving data at pytron://{key} ({len(data)} bytes, {mime_type})"
            )
        else:
            self.logger.warning(
                "serve_data is not supported on this platform/engine configuration."
            )

    def expose(self, entity):
        if callable(entity) and not isinstance(entity, type):
            self.bind(entity.__name__, entity)
            self.logger.debug(f"Binding {entity.__name__}")
            return entity
        if isinstance(entity, type):
            instance = entity()
            for name in dir(instance):
                if not name.startswith("_"):
                    attr = getattr(instance, name)
                    if callable(attr):
                        self.logger.debug(f"Binding {name}")
                        self.bind(name, attr)
            return entity

    def normalize_path(self, config):
        if IS_ANDROID:
            if not config.get("url"):
                config["url"] = "android://loaded-by-java"
            config["navigate_on_init"] = False
            return
        raw_url = config.get("url")
        if not raw_url:
            self.logger.error(
                "No URL provided in configuration. Pytron needs a URL or HTML file to load."
            )
            raise ConfigError("No URL or HTML file specified in configuration.")

        if raw_url.startswith(("http://", "https://", "file://", "pytron://")):
            return
        path_obj = pathlib.Path(raw_url)

        if getattr(sys, "frozen", False) and not path_obj.is_absolute():
            # Check _MEIPASS (onefile)
            if hasattr(sys, "_MEIPASS"):
                meipass_path = pathlib.Path(sys._MEIPASS) / path_obj
                if meipass_path.exists():
                    path_obj = meipass_path

            # Check exe dir (onedir)
            if not path_obj.is_absolute() or not path_obj.exists():
                exe_dir = pathlib.Path(sys.executable).parent
                frozen_candidate = exe_dir / path_obj
                if frozen_candidate.exists():
                    path_obj = frozen_candidate

        if not path_obj.is_absolute():
            # Try resolving relative to self._app_root first
            app_rel_path = self._app_root / path_obj
            if app_rel_path.exists():
                path_obj = app_rel_path
            else:
                path_obj = path_obj.resolve()
        
        if not path_obj.exists():
            self.logger.error(f"HTML file not found at: {path_obj}")
            raise ResourceNotFoundError(
                f"Pytron Error: HTML file not found at: {path_obj}"
            )

        # Standard file path for engine-level navigation (Fixes blank page)
        # We still provide the high-performance VAP bridge via current JS hooks.
        uri = path_obj.as_uri()
        config["url"] = uri
        self._vap_app_dir = path_obj.parent
        self.logger.debug(f"Normalized URL: {uri}")
