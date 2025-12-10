import ctypes
import os
import sys
import platform

CURRENT_PLATFORM = platform.system()

# CORS AVOIDANCE (Windows/WebView2 only)
if CURRENT_PLATFORM == "Windows":
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--allow-file-access-from-files"

# Load the DLL
lib_name = 'webview.dll'
if CURRENT_PLATFORM == "Linux":
    lib_name = 'libwebview.so'
elif CURRENT_PLATFORM == "Darwin":
    # Identify architecture: 'arm64' (Apple Silicon) vs 'x86_64' (Intel)
    if platform.machine() == 'arm64':
        lib_name = 'libwebview_arm64.dylib'
    else:
        lib_name = 'libwebview_x64.dylib'

dll_path = os.path.join(os.path.dirname(__file__), 'dependancies', lib_name)

if hasattr(sys, 'frozen'):
    # PyInstaller: Look in the bundled location
    # If onefile: sys._MEIPASS/pytron/dependancies/lib_name
    # If onedir: sys.executable/../pytron/dependancies/lib_name (or inside _internal)
    # We rely on __file__ if it's consistent, but let's try explicit locations if default fails.
    
    if not os.path.exists(dll_path):
        # Fallback for some bundle structures
        if hasattr(sys, '_MEIPASS'):
            # Onefile
            alt_path = os.path.join(sys._MEIPASS, 'pytron', 'dependancies', lib_name)
        else:
            # Onedir
            # Typically in {sys.executable dir}/_internal/pytron/dependancies
            # or {sys.executable dir}/pytron/dependancies
            base = os.path.dirname(sys.executable)
            alt_path = os.path.join(base, 'pytron', 'dependancies', lib_name)
            if not os.path.exists(alt_path):
                 alt_path = os.path.join(base, '_internal', 'pytron', 'dependancies', lib_name)

        if os.path.exists(alt_path):
            dll_path = alt_path

if not os.path.exists(dll_path):
    raise Exception(f"Library Not Found: {dll_path}")

lib = ctypes.CDLL(dll_path)

# -------------------------------------------------------------------
# Correct function signatures
# -------------------------------------------------------------------
lib.webview_create.argtypes = [ctypes.c_int, ctypes.c_void_p]
lib.webview_create.restype = ctypes.c_void_p

lib.webview_set_title.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
lib.webview_set_size.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
lib.webview_navigate.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
lib.webview_run.argtypes = [ctypes.c_void_p]
lib.webview_destroy.argtypes = [ctypes.c_void_p]
lib.webview_eval.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
#scary sync function
lib.webview_init.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
# Declare get_window in DLL

lib.webview_get_window.argtypes = [ctypes.c_void_p]
lib.webview_get_window.restype = ctypes.c_void_p

# -------------------------------------------------------------------
# Callback signatures
# -------------------------------------------------------------------
dispatch_callback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)
BindCallback = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p)

# Declare dispatch and bind in DLL using the callback types
lib.webview_dispatch.argtypes = [ctypes.c_void_p, dispatch_callback, ctypes.c_void_p]
lib.webview_bind.argtypes = [ctypes.c_void_p, ctypes.c_char_p, BindCallback, ctypes.c_void_p]
lib.webview_return.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p]
