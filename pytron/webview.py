import ctypes
import sys
import json
import time
import threading
import asyncio
import inspect
import pathlib
import platform
from collections import deque
import logging
from .exceptions import ResourceNotFoundError, BridgeError
import os
from .bindings import lib, dispatch_callback, BindCallback, IS_ANDROID
from .serializer import pytron_serialize
from .platforms.interface import PlatformInterface
from .platforms.windows import WindowsImplementation
from .platforms.linux import LinuxImplementation
from .platforms.darwin import DarwinImplementation

# -------------------------------------------------------------------
# Callback handler for dispatch
# -------------------------------------------------------------------
def _dispatch_handler(window_ptr, arg_ptr):
    js_code = ctypes.cast(arg_ptr, ctypes.c_char_p).value  # read JS code
    lib.webview_eval(window_ptr, js_code)
c_dispatch_handler = dispatch_callback(_dispatch_handler)

# -------------------------------------------------------------------
# Browser wrapper
# -------------------------------------------------------------------
class Webview:
    def __init__(self, config):
        self.logger = logging.getLogger("Pytron.Webview")
        
        # ------------------------------------------------
        # ENGINE SELECTION (Native or PySide6)
        # ------------------------------------------------
        engine_name = os.environ.get("PYTRON_ENGINE", "webview2")
        
        self.thread_pool = __import__('concurrent.futures').futures.ThreadPoolExecutor(max_workers=5)
        self._gc_protector = deque(maxlen=50)      
        self._bound_functions = {} 
        
        # ------------------------------------------------
        # ENGINE SELECTION
        # ------------------------------------------------
        self.is_pyside = False
        if engine_name == "pyside6":
            from .pyside_engine import PySideEngine
            self.logger.info("Using PySide6 Engine")
            self.is_pyside = True
            # Pass bound functions dict reference so it can be updated
            self.pyside = PySideEngine(config, self._bound_functions)
            self.w = None
        else:
            self.w = lib.webview_create(int(config.get("debug", False)), None)
            self._cb = c_dispatch_handler
            
        # Default Bindings
        self.bind("pytron_drag", lambda: self.start_drag(), run_in_thread=False)
        self.bind("pytron_minimize", lambda: self.minimize(), run_in_thread=False)
        self.bind("pytron_close", lambda: self.close(), run_in_thread=False)
        self.bind("pytron_toggle_maximize", lambda: self.toggle_maximize(), run_in_thread=False)
        self.bind("pytron_set_bounds", self.set_bounds, run_in_thread=False)
        
        # New Daemon bindings
        self.bind("pytron_hide", lambda: self.hide(), run_in_thread=False)
        self.bind("pytron_show", lambda: self.show(), run_in_thread=False)
        self.bind("pytron_system_notification", self.system_notification, run_in_thread=True)
        self.bind("pytron_set_taskbar_progress", self.set_taskbar_progress, run_in_thread=True)
         
        # Dialog bindings
        self.bind("pytron_dialog_open_file", self.dialog_open_file, run_in_thread=True)
        self.bind("pytron_dialog_save_file", self.dialog_save_file, run_in_thread=True)
        self.bind("pytron_dialog_open_folder", self.dialog_open_folder, run_in_thread=True)
        self.bind("pytron_message_box", self.message_box, run_in_thread=True)
        # Compatibility binding for UI components
        self.bind("get_registered_shortcuts", lambda: [], run_in_thread=False)

        # Webview Error Reporting
        self.bind("pytron_report_error", self._report_error, run_in_thread=False)
        self.bind("pytron_log", lambda msg: self.logger.info(f"Webview Log: {msg}"), run_in_thread=False)

        init_js = """
        console.log("[Pytron] Core Initialized");
        window.pytron = window.pytron || {};
        window.pytron.is_ready = true;
        """
        
        # Disable default context menu if requested in config
        if not config.get("default_context_menu", True):
            init_js += "\nwindow.addEventListener('contextmenu', e => e.preventDefault());"
        
        # Init Only for Native
        if not self.is_pyside:
             lib.webview_init(self.w, init_js.encode('utf-8'))
        else:
             # PySide engine handles its own init in constructor/later
             pass
        
        
        CURRENT_PLATFORM = platform.system()
        
        # Initialize Platform Specifics (Only if not PySide, or if PySide needs them?)
        # PySide handles most windowing things, but we might keep platform for specific utils
        if not self.is_pyside:
            if IS_ANDROID:
                self._platform = PlatformInterface()
            elif CURRENT_PLATFORM == "Windows":
                self._platform = WindowsImplementation()
            elif CURRENT_PLATFORM == "Linux":
                self._platform = LinuxImplementation()
                # Attempt to fix file:// access via native settings hack
                self._platform.register_pytron_scheme(self.w, None) 
            elif CURRENT_PLATFORM == "Darwin":
                self._platform = DarwinImplementation()
                self._platform.register_pytron_scheme(self.w, None)
            else:
                self.logger.warning(f"Minimal support for {CURRENT_PLATFORM}. Window controls may not work.")
                self._platform = PlatformInterface()
        else:
             # Placeholder for pyside platform if needed
             self._platform = PlatformInterface()
             
        self.normalize_path(config)    
        
        self.loop = asyncio.new_event_loop()
        self.frameless=config.get("frameless", False)
        # Frameless logic for PySide is different (setWindowFlags)
        # We will delegate later
        
        def start_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
        t = threading.Thread(target=start_loop, daemon=True)
        t.start()
        
        # Setters
        if not self.is_pyside:
             self.set_title(config.get("title", "Pytron App"))
             width, height = config.get("dimensions", [800, 600])
             self.set_size(width, height)
             if "icon" in config:
                self.set_icon(config["icon"])
        
        # Apply frameless independent of engine (both support it now)
        if self.frameless:
             self.make_frameless()
        
        if config.get("navigate_on_init", True):
            self.navigate(config["url"])
            
    def _return_result(self, seq, status, result_json_str):
        if self.is_pyside:
             self.pyside.resolve(seq, status, result_json_str) 
        else:
             lib.webview_return(self.w, seq, status, result_json_str.encode('utf-8'))
    
    def minimize(self):
        if self.is_pyside:
            self.pyside.view.showMinimized()
        else:
            self._platform.minimize(self.w)

    def set_bounds(self, x, y, width, height):
        if self.is_pyside:
            self.pyside.view.move(int(x), int(y))
            self.pyside.view.resize(int(width), int(height))
        else:
            self._platform.set_bounds(self.w, x, y, width, height)

    def close(self):
        if self.is_pyside:
            self.pyside.view.close()
        else:
            self._platform.close(self.w)

    def toggle_maximize(self):
        if self.is_pyside:
            if self.pyside.view.isMaximized():
                self.pyside.view.showNormal()
                return False
            else:
                self.pyside.view.showMaximized()
                return True
        else:
            return self._platform.toggle_maximize(self.w)

    def make_frameless(self):
        if self.is_pyside:
             self.pyside.make_frameless()
        else:
             self._platform.make_frameless(self.w)

    def start_drag(self):
        if self.is_pyside:
             self.pyside.start_drag()
        else:
             self._platform.start_drag(self.w)

    def set_title(self, title):
        if self.is_pyside:
            self.pyside.set_title(title)
        else:
            lib.webview_set_title(self.w, title.encode("utf-8"))

    def set_size(self, w, h):
        if self.is_pyside:
            self.pyside.set_size(w, h)
        else:
            lib.webview_set_size(self.w, w, h, 0)
    
    def hide(self):
        if self.is_pyside:
             self.pyside.view.hide()
        else:
             self._platform.hide(self.w)

    def show(self):
        if self.is_pyside:
             self.pyside.view.show()
        else:
             self._platform.show(self.w)

    def system_notification(self, title, message):
        self._platform.notification(self.w, title, message)

    def set_taskbar_progress(self, state="normal", value=0, max_value=100):
        if self._platform and hasattr(self._platform, 'set_taskbar_progress'):
             self._platform.set_taskbar_progress(self.w, state, value, max_value)

    def set_icon(self, icon_path):
        self._platform.set_window_icon(self.w, icon_path)

    # --- Native Dialogs ---
    def dialog_open_file(self, title="Open File", default_path=None, file_types=None):
        return self._platform.open_file_dialog(self.w, title, default_path, file_types)

    def dialog_save_file(self, title="Save File", default_path=None, default_name=None, file_types=None):
        return self._platform.save_file_dialog(self.w, title, default_path, default_name, file_types)

    def dialog_open_folder(self, title="Select Folder", default_path=None):
        return self._platform.open_folder_dialog(self.w, title, default_path)

    def message_box(self, title, message, style=0):
        # Styles: 0=OK, 1=OK/Cancel, 2=Abort/Retry/Ignore, 3=Yes/No/Cancel, 4=Yes/No, 5=Retry/Cancel
        # Returns: 1=OK, 2=Cancel, 6=Yes, 7=No
        return self._platform.message_box(self.w, title, message, style)

    def navigate(self, url):
        if self.is_pyside:
            self.pyside.load_url(url)
        else:
            lib.webview_navigate(self.w, url.encode("utf-8"))

    def start(self):
        if self.is_pyside:
            self.pyside.run()
        else:
            lib.webview_run(self.w)
            lib.webview_destroy(self.w)
    #-------------------------------------------------------------------
    # Safe JS -> Python Binding
    #-------------------------------------------------------------------
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
                    4 
                )
                if confirm != 6: # User did not click Yes
                     self.logger.warning(f"Security: User denied execution of {name}")
                     lib.webview_return(self.w, seq, 1, json.dumps("User denied execution.").encode('utf-8'))
                     return

            # ------------------------------------------------
            # CASE A: ASYNC FUNCTION (Run in Background Loop)
            # ------------------------------------------------
            if is_async:
                async def _async_runner():
                    try:
                        result = await python_func(*args)
                        # Ensure result is JSON-serializable using Pytron's encoder
                        res_json = json.dumps(pytron_serialize(result))
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
                        result_json = json.dumps(pytron_serialize(result))
                        self._return_result(seq, 0, result_json)
                    except Exception as e:
                        self.logger.error(f"Execution error in {name}: {e}")
                        error_msg = json.dumps(str(e))
                        self._return_result(seq, 1, error_msg)
                
                if run_in_thread and not self.is_pyside: # PySide requires thread safety logic? 
                     # Actually pyside signal dispatching handles some, but running long tasks 
                     # in main thread blocks UI. Using thread_pool is good.
                     self.thread_pool.submit(_sync_runner)
                elif self.is_pyside:
                     # For PySide, if run_in_thread is True, use pool.
                     if run_in_thread:
                         self.thread_pool.submit(_sync_runner)
                     else:
                         _sync_runner()
                else:
                     # Run immediately on Main Thread (Required for Window Controls like Drag)
                     _sync_runner()

        if self.is_pyside:
             # We just store the callback wrapper. PySideEngine will call it.
             self._bound_functions[name] = _callback
             # Register the JS wrapper
             self.pyside.register_binding(name)
        else:
             c_func = BindCallback(_callback)
             self._bound_functions[name] = c_func
             lib.webview_bind(self.w, name.encode('utf-8'), c_func, None)

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
        # Serialize event payloads using Pytron's serializer so complex objects work
        payload = json.dumps(pytron_serialize(data))
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
        self.emit("pytron:notification", {
            "title": title,
            "message": message,
            "type": type,
            "duration": duration
        })

    def eval(self, js_code):
        if self.is_pyside:
             self.pyside.eval_js(js_code)
             return

        def _thread_send():
            js_buf = ctypes.create_string_buffer(js_code.encode("utf-8"))
            self._gc_protector.append(js_buf)
            if len(self._gc_protector) > 50:
                self._gc_protector.pop(0)
            lib.webview_dispatch(
                self.w,
                self._cb,
                ctypes.cast(js_buf, ctypes.c_void_p)
            )
        threading.Thread(target=_thread_send, daemon=True).start()
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
        if raw_url.startswith(("http://", "https://", "file://")):
            return 
        path_obj = pathlib.Path(raw_url)
        
        if getattr(sys, 'frozen', False) and not path_obj.is_absolute():
            # Check _MEIPASS (onefile)
            if hasattr(sys, '_MEIPASS'):
                 meipass_path = pathlib.Path(sys._MEIPASS) / path_obj
                 if meipass_path.exists():
                     path_obj = meipass_path

            # Check exe dir (onedir) - only if we haven't found it in MEIPASS
            if not path_obj.exists() or path_obj == pathlib.Path(raw_url):
                 exe_dir = pathlib.Path(sys.executable).parent
                 frozen_path = exe_dir / pathlib.Path(raw_url)
                 if frozen_path.exists():
                     path_obj = frozen_path
        
        if not path_obj.is_absolute():
            path_obj = path_obj.resolve()
        if not path_obj.exists():
            self.logger.error(f"HTML file not found at: {path_obj}")
            raise ResourceNotFoundError(f"Pytron Error: HTML file not found at: {path_obj}")

        # Default fallback
        uri = path_obj.as_uri()
        config["url"] = uri
        self.logger.debug(f"Normalized URL: {uri}")
