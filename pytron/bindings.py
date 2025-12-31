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
os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--allow-file-access-from-files"
os.environ["WebKitWebProcessArguments"] = (
    "--allow-file-access-from-files"  # CORS AVOIDANCE (All platforms)
)

# -------------------------------------------------------------------
# Callback signatures (Must be available for import)
# -------------------------------------------------------------------
dispatch_callback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)
BindCallback = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p)

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
                c_func(str(seq).encode("utf-8"), req_str.encode("utf-8"), None)
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
    lib_name = "webview.dll"
    if CURRENT_PLATFORM == "Linux":
        lib_name = "libwebview.so"
    elif CURRENT_PLATFORM == "Darwin":
        if platform.machine() == "arm64":
            lib_name = "libwebview_arm64.dylib"
        else:
            lib_name = "libwebview_x64.dylib"

    dll_path = os.path.join(os.path.dirname(__file__), "dependancies", lib_name)

    # Frozen app handling
    if hasattr(sys, "frozen"):
        # PyInstaller: Look in the bundled location
        if hasattr(sys, "_MEIPASS"):
            alt_path = os.path.join(sys._MEIPASS, "pytron", "dependancies", lib_name)
        else:
            base = os.path.dirname(sys.executable)
            alt_path = os.path.join(
                base, "_internal", "pytron", "dependancies", lib_name
            )

        if os.path.exists(alt_path):
            dll_path = alt_path

    if not os.path.exists(dll_path):
        # Fallback to local dependancies if everything else failed
        dll_path = os.path.join(os.path.dirname(__file__), "dependancies", lib_name)

    lib = ctypes.CDLL(dll_path)

    # -------------------------------------------------------------------
    # Correct function signatures (Only needed for CTYPES/Desktop)
    # -------------------------------------------------------------------
    lib.webview_create.argtypes = [ctypes.c_int, ctypes.c_void_p]
    lib.webview_create.restype = ctypes.c_void_p

    lib.webview_set_title.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.webview_set_size.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
    ]
    lib.webview_navigate.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.webview_run.argtypes = [ctypes.c_void_p]
    lib.webview_destroy.argtypes = [ctypes.c_void_p]
    lib.webview_eval.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.webview_init.argtypes = [ctypes.c_void_p, ctypes.c_char_p]

    lib.webview_get_window.argtypes = [ctypes.c_void_p]
    lib.webview_get_window.restype = ctypes.c_void_p

    lib.webview_dispatch.argtypes = [
        ctypes.c_void_p,
        dispatch_callback,
        ctypes.c_void_p,
    ]
    lib.webview_bind.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        BindCallback,
        ctypes.c_void_p,
    ]
    lib.webview_return.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
    ]
