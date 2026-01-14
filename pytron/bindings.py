import ctypes
import os
import sys
import platform

# Check if we are on Android
try:
    # We try to import the native bridge you built in C++
    import _pytron_android

    IS_ANDROID = True
except ImportError:
    IS_ANDROID = False
CURRENT_PLATFORM = platform.system()

# -------------------------------------------------------------------
# Callback signatures (Must be available for import)
# -------------------------------------------------------------------
dispatch_callback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)

if IS_ANDROID:
    # OPTIMIZATION: On Android, we don't need ctypes trampolines.
    # We pass Python objects directly to save encoding/decoding overhead.
    def BindCallback(f):
        return f

else:
    BindCallback = ctypes.CFUNCTYPE(
        None, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p
    )

# -------------------------------------------------------------------
# Android Dispatcher
# -------------------------------------------------------------------
if IS_ANDROID:

    def dispatch_android_message(msg):
        # Called from C++ JNI
        try:
            import json

            data = json.loads(msg)
            # data: {id: seq, name: funcName, args: [..]}
            # OR {id: seq, method: 'eval', result: ...} (Not fully integrated yet)

            # For now, we only support Callbacks via "window.external.invoke" emulation
            # The structure Pytron expects depends on how webview.js sends it.
            # Standard webview.js does: window.external.invoke(JSON.stringify({id, method, params}))

            # If msg is already the JSON string from JS invoke(s)

            # print(f"DEBUG: dispatch_android_message raw: {msg}")

            payload = data

            seq = data.get("id")
            name = data.get("method")
            params = data.get("params")

            if name in lib._callbacks:
                print(f"DEBUG: Invoking callback for {name} with seq {seq}")
                req_str = json.dumps(params)
                c_func = lib._callbacks[name]
                # Optimization: Pass strings directly to avoid redundant encoding/decoding cycles on Android
                c_func(str(seq), req_str, None)
            else:
                print(f"DEBUG: Callback {name} not found in lib._callbacks")

        except Exception as e:
            print(f"Android Dispatch Error: {e}")

    class AndroidBridge:
        def __init__(self):
            self._callbacks = {}

        def _send(self, method, args=None):
            # Helper to send data to Java -> WebView
            try:
                import _pytron_android
                import json

                payload = {"method": method, "args": args or {}}
                _pytron_android.send_to_android(json.dumps(payload))
            except Exception as e:
                print(f"AndroidBridge Error: {e}")

        def webview_init(self, w, js):
            # 1. SETUP THE JS-SIDE BRIDGE
            # We map window.external.invoke -> window._pytron_bridge.postMessage
            # We also create a registry for Promises so we can reply later.
            adapter = """
            window.external = {
                invoke: function(s) { window._pytron_bridge.postMessage(s); }
            };
            window._rpc = { promises: {} };
            """
            # Inject adapter + user script
            self._send("eval", {"code": adapter + js.decode("utf-8")})

        def webview_bind(self, w, name, fn, arg):
            try:
                n = name.decode("utf-8")
                print(f"DEBUG: AndroidBridge binding function '{n}'")
                self._callbacks[n] = fn

                # 2. CREATE THE JS STUB
                # When JS calls 'test()', we create a Promise, save it, and call Python.
                js = f"""
                window.{n} = function(...args) {{
                    var id = (Math.random() * 1000000).toFixed(0);
                    return new Promise(function(resolve, reject) {{
                        window._rpc.promises[id] = {{resolve: resolve, reject: reject}};
                        window.external.invoke(JSON.stringify({{id: id, method: '{n}', params: args}}));
                    }});
                }};
                """
                self._send("eval", {"code": js})
            except Exception as e:
                print(f"DEBUG: CRITICAL ERROR in webview_bind: {e}")

        def webview_return(self, w, seq, status, result):
            # 3. HANDLE THE REPLY
            # Python is done. We find the matching JS Promise and resolve it.
            # seq is the 'id' we generated in JS above.

            # Ensure seq is a string for JS lookup
            seq_str = seq.decode("utf-8") if isinstance(seq, bytes) else str(seq)
            res_str = (
                result.decode("utf-8") if isinstance(result, bytes) else str(result)
            )

            js = f"""
            (function() {{
                var p = window._rpc.promises['{seq_str}'];
                if (p) {{
                    if ({status} === 0) p.resolve({res_str});
                    else p.reject({res_str});
                    delete window._rpc.promises['{seq_str}'];
                }}
            }})();
            """
            self._send("eval", {"code": js})

        # ... (keep webview_create/navigate/eval/destroy as before) ...
        def webview_create(self, debug, window):
            return 1

        def webview_navigate(self, w, url):
            self._send("navigate", {"url": url.decode("utf-8")})

        def webview_eval(self, w, js):
            self._send("eval", {"code": js.decode("utf-8")})

        def webview_destroy(self, w):
            pass

        def webview_run(self, w):
            pass

        def webview_set_title(self, w, t):
            pass

        def webview_set_size(self, w, width, height, hints):
            pass

        def __getattr__(self, name):
            return lambda *args: None

    lib = AndroidBridge()

else:
    # -------------------------------------------------------------------
    # Desktop Library Loading (Native Engine)
    # -------------------------------------------------------------------
    class WebviewError(Exception):
        """Base exception for Webview errors."""

        pass

    class LibraryLoadError(WebviewError):
        """Raised when the native library cannot be loaded."""

        pass

    class NativeCallError(WebviewError):
        """Raised when a native function call fails."""

        pass

    class SegmentationFault(NativeCallError):
        """Raised when the native library crashes (e.g. Access Violation)."""

        pass

    lib_name = "webview.dll"
    if CURRENT_PLATFORM == "Linux":
        lib_name = "libwebview.so"
    elif CURRENT_PLATFORM == "Darwin":
        if platform.machine() == "arm64":
            lib_name = "libwebview_arm64.dylib"
        else:
            lib_name = "libwebview_x64.dylib"

    # --- CROSS-PLATFORM FIXED RUNTIME DETECTION ---
    if getattr(sys, "frozen", False):
        app_root = os.path.dirname(os.path.abspath(sys.executable))
        if hasattr(sys, "_MEIPASS"):
            pass
    else:
        main_mod = sys.modules.get("__main__")
        if main_mod and hasattr(main_mod, "__file__"):
            app_root = os.path.dirname(os.path.abspath(main_mod.__file__))
        else:
            app_root = os.path.abspath(sys.path[0] or os.getcwd())

    # Search candidates
    candidates = [
        os.path.join(app_root, "runtime", lib_name),
        os.path.join(app_root, "bin", lib_name),
        os.path.join(os.path.dirname(__file__), "dependancies", lib_name),
    ]

    dll_path = candidates[-1]  # Default to internal
    for lib_path in candidates:
        if os.path.exists(lib_path):
            dll_path = lib_path
            break

    # Frozen app handling
    if hasattr(sys, "frozen") and hasattr(sys, "_MEIPASS"):
        alt_path = os.path.join(sys._MEIPASS, "pytron", "dependancies", lib_name)
        if os.path.exists(alt_path):
            dll_path = alt_path

    # Force Load dependancies for Windows
    if CURRENT_PLATFORM == "Windows" and os.path.dirname(dll_path) != os.path.dirname(
        __file__
    ):
        try:
            # Harden: Use strict kernel32 definition
            k32 = ctypes.windll.kernel32
            k32.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
            k32.SetDllDirectoryW.restype = ctypes.c_int

            if k32.SetDllDirectoryW(os.path.dirname(dll_path)) == 0:
                print(
                    f"[Pytron] Warning: SetDllDirectoryW failed: {ctypes.FormatError(ctypes.get_last_error())}"
                )
        except Exception as e:
            print(f"[Pytron] Warning: Failed to set DLL directory: {e}")

    if not os.path.exists(dll_path):
        dll_path = os.path.join(os.path.dirname(__file__), "dependancies", lib_name)

    _raw_lib = None
    try:
        if CURRENT_PLATFORM == "Windows":
            _raw_lib = ctypes.CDLL(dll_path, use_last_error=True)
        else:
            _raw_lib = ctypes.CDLL(dll_path)
    except OSError as e:
        print(f"[Pytron] CRITICAL: Failed to load webview library from {dll_path}")
        print(f"[Pytron] Error: {e}")
        try:
            _raw_lib = ctypes.CDLL(lib_name)
        except Exception:
            raise LibraryLoadError(
                f"Could not load native webview engine from {dll_path} or system path. Error: {e}"
            )

    # -------------------------------------------------------------------
    # Hardened Safe Wrapper
    # -------------------------------------------------------------------

    class SafeWebviewLib:
        """
        Wraps the raw ctypes library calls to provide robustness,
        segfault handling, and strict error checking.
        """

        def __init__(self, raw_lib):
            self._lib = raw_lib
            self._setup_signatures()

        def _setup_signatures(self):
            # Define signatures on the raw lib so ctypes knows how to marshal data
            self._lib.webview_create.argtypes = [ctypes.c_int, ctypes.c_void_p]
            self._lib.webview_create.restype = ctypes.c_void_p

            self._lib.webview_set_title.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            self._lib.webview_set_title.restype = None

            self._lib.webview_set_size.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
            ]
            self._lib.webview_set_size.restype = None

            self._lib.webview_navigate.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            self._lib.webview_navigate.restype = None

            self._lib.webview_run.argtypes = [ctypes.c_void_p]
            self._lib.webview_run.restype = None

            self._lib.webview_destroy.argtypes = [ctypes.c_void_p]
            self._lib.webview_destroy.restype = None

            self._lib.webview_init.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            self._lib.webview_init.restype = None

            if hasattr(self._lib, "webview_debug"):
                self._lib.webview_debug.argtypes = [ctypes.c_void_p]
                self._lib.webview_debug.restype = None

            self._lib.webview_get_window.argtypes = [ctypes.c_void_p]
            self._lib.webview_get_window.restype = ctypes.c_void_p

            self._lib.webview_dispatch.argtypes = [
                ctypes.c_void_p,
                dispatch_callback,
                ctypes.c_void_p,
            ]
            self._lib.webview_dispatch.restype = None

            self._lib.webview_bind.argtypes = [
                ctypes.c_void_p,
                ctypes.c_char_p,
                BindCallback,
                ctypes.c_void_p,
            ]
            self._lib.webview_bind.restype = None

            self._lib.webview_return.argtypes = [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
            ]
            self._lib.webview_return.restype = None

            self._lib.webview_eval.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            self._lib.webview_eval.restype = None

        def _safe_call(self, func_name, *args, check_result=False):
            func = getattr(self._lib, func_name, None)
            if not func:
                if func_name == "webview_debug":
                    return  # Optional
                raise NativeCallError(f"Function {func_name} not found in library.")

            try:
                # Reset error just in case
                if CURRENT_PLATFORM == "Windows":
                    ctypes.set_last_error(0)

                res = func(*args)

                if check_result and not res:
                    # Check for errors if checking enabled and result is NULL/False
                    error_msg = "Unknown Error"
                    if CURRENT_PLATFORM == "Windows":
                        code = ctypes.get_last_error()
                        if code != 0:
                            error_msg = f"{ctypes.FormatError(code)} (Code: {code})"

                    # Special check: webview_create returning NULL is always fatal
                    raise NativeCallError(
                        f"Native call '{func_name}' returned NULL. Error: {error_msg}"
                    )

                return res

            except OSError as e:
                # Catch Access Violations on Windows (SEH)
                if getattr(e, "winerror", 0) == -1073741819:  # 0xC0000005
                    raise SegmentationFault(
                        f"CRITICAL: Access Violation (Segfault) in '{func_name}'. Bad pointer?"
                    )
                raise NativeCallError(f"OS Error in '{func_name}': {e}")
            except Exception as e:
                raise NativeCallError(f"Unexpected Error in '{func_name}': {e}")

        # --- Exposed Wrappers ---

        def webview_create(self, debug, window):
            return self._safe_call("webview_create", debug, window, check_result=True)

        def webview_set_title(self, w, title):
            self._safe_call("webview_set_title", w, title)

        def webview_set_size(self, w, width, height, hints):
            self._safe_call("webview_set_size", w, width, height, hints)

        def webview_navigate(self, w, url):
            self._safe_call("webview_navigate", w, url)

        def webview_run(self, w):
            self._safe_call("webview_run", w)

        def webview_destroy(self, w):
            self._safe_call("webview_destroy", w)

        def webview_init(self, w, js):
            self._safe_call("webview_init", w, js)

        def webview_debug(self, w):
            self._safe_call("webview_debug", w)

        def webview_get_window(self, w):
            # This can legitimately return NULL (e.g. on GTK before realization), so we default check_result to False
            return self._safe_call("webview_get_window", w, check_result=False)

        def webview_dispatch(self, w, fn, arg):
            self._safe_call("webview_dispatch", w, fn, arg)

        def webview_bind(self, w, name, fn, arg):
            self._safe_call("webview_bind", w, name, fn, arg)

        def webview_return(self, w, seq, status, result):
            self._safe_call("webview_return", w, seq, status, result)

        def webview_eval(self, w, js):
            self._safe_call("webview_eval", w, js)

    # Instantiate the safe bridge
    lib = SafeWebviewLib(_raw_lib)
