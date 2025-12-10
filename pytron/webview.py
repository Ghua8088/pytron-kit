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

from .bindings import lib, dispatch_callback, BindCallback
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
        self.w = lib.webview_create(int(config.get("debug", False)), None)
        self._gc_protector = deque(maxlen=50)      
        self._cb = c_dispatch_handler
        self._bound_functions = {} 
        # Default Bindings
        self.bind("pytron_drag", lambda: self.start_drag())
        self.bind("pytron_minimize", lambda: self.minimize())
        self.bind("pytron_close", lambda: self.close())
        self.bind("pytron_toggle_maximize", lambda: self.toggle_maximize())
        self.bind("pytron_set_bounds", self.set_bounds)
        
        init_js = """
        
        console.log("[Pytron] Core Initialized");
        window.pytron = window.pytron || {};
        window.pytron.is_ready = true;
        
        """
        lib.webview_init(self.w, init_js.encode('utf-8'))
        
        
        CURRENT_PLATFORM = platform.system()
        
        # Initialize Platform Specifics
        if CURRENT_PLATFORM == "Windows":
            self._platform = WindowsImplementation()
        elif CURRENT_PLATFORM == "Linux":
            self._platform = LinuxImplementation()
        elif CURRENT_PLATFORM == "Darwin":
            self._platform = DarwinImplementation()
        else:
            print(f"[Pytron] Warning: Minimal support for {CURRENT_PLATFORM}. Window controls may not work.")
            self._platform = PlatformInterface()
        self.normalize_path(config)    

        self.loop = asyncio.new_event_loop()
        self.frameless=config.get("frameless", False)
        if self.frameless:
            self.make_frameless()
        def start_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
        t = threading.Thread(target=start_loop, daemon=True)
        t.start()
        
        # Bindings
        
        
        self.set_title(config.get("title", "Pytron App"))
        width, height = config.get("dimensions", [800, 600])
        self.set_size(width, height)
        self.navigate(config["url"])
    
    def minimize(self):
        self._platform.minimize(self.w)

    def set_bounds(self, x, y, width, height):
        self._platform.set_bounds(self.w, x, y, width, height)

    def close(self):
        self._platform.close(self.w)

    def toggle_maximize(self):
        return self._platform.toggle_maximize(self.w)

    def make_frameless(self):
        self._platform.make_frameless(self.w)

    def start_drag(self):
        self._platform.start_drag(self.w)

    def set_title(self, title):
        lib.webview_set_title(self.w, title.encode("utf-8"))

    def set_size(self, w, h):
        lib.webview_set_size(self.w, w, h, 0)

    def navigate(self, url):
        lib.webview_navigate(self.w, url.encode("utf-8"))

    def start(self):
        lib.webview_run(self.w)
        lib.webview_destroy(self.w)
    #-------------------------------------------------------------------
    # Safe JS -> Python Binding
    #-------------------------------------------------------------------
    def bind(self, name, python_func):
        """
        Exposes a Python function (Sync or Async) to JS.
        """
        
        # Check if the user passed an 'async def'
        is_async = inspect.iscoroutinefunction(python_func)

        def _callback(seq, req, arg):
            # 1. Parse Args
            try:
                args = json.loads(req) if req else []
            except:
                args = []
            print(f"Binding {name} with args {args}")
            # ------------------------------------------------
            # CASE A: ASYNC FUNCTION (Run in Background Loop)
            # ------------------------------------------------
            if is_async:
                async def _async_runner():
                    try:
                        result = await python_func(*args)
                        # Ensure result is JSON-serializable using Pytron's encoder
                        res_json = json.dumps(pytron_serialize(result))
                        lib.webview_return(self.w, seq, 0, res_json.encode('utf-8'))
                    except Exception as e:
                        err_json = json.dumps(str(e))
                        lib.webview_return(self.w, seq, 1, err_json.encode('utf-8'))
                asyncio.run_coroutine_threadsafe(_async_runner(), self.loop)
            # ------------------------------------------------
            # CASE B: SYNC FUNCTION (Run Immediately)
            # ------------------------------------------------
            else:
                try:
                    result = python_func(*args)
                    # Ensure result is JSON-serializable using Pytron's encoder
                    result_json = json.dumps(pytron_serialize(result))
                    lib.webview_return(self.w, seq, 0, result_json.encode('utf-8'))
                except Exception as e:
                    error_msg = json.dumps(str(e))
                    lib.webview_return(self.w, seq, 1, error_msg.encode('utf-8'))

        c_func = BindCallback(_callback)
        self._bound_functions[name] = c_func
        lib.webview_bind(self.w, name.encode('utf-8'), c_func, None)
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
            print(f"Binding {entity.__name__}")
            return entity
        if isinstance(entity, type):
            instance = entity()
            for name in dir(instance):
                if not name.startswith("_"):
                    attr = getattr(instance, name)
                    if callable(attr):
                        print(f"Binding {name}")
                        self.bind(name, attr)
            return entity
    def normalize_path(self, config):
        raw_url = config.get("url")
        if raw_url.startswith("http://") or raw_url.startswith("https://"):
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
            raise FileNotFoundError(f"Pytron Error: HTML file not found at: {path_obj}")
        config["url"] = path_obj.as_uri()
