import sys
import json
import logging
import threading
import asyncio
import ctypes
from concurrent.futures import ThreadPoolExecutor

try:
    from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import QWebEngineScript, QWebEngineSettings
    from PySide6.QtCore import QUrl, QObject, Slot, Signal, Qt, QFile, QIODevice, QTimer
    from PySide6.QtGui import QIcon
    import ctypes.wintypes
except ImportError as e:
    raise ImportError(
        "PySide6 or its components (QtWebEngineWidgets) not found. "
        "Please install it with: pip install PySide6"
    ) from e

class PytronWebEngineView(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._frameless_active = False

    def nativeEvent(self, eventType, message):
        try:
            # Handle Windows Native Events for Frameless
            if self._frameless_active and eventType == "windows_generic_MSG":
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == 0x0083: # WM_NCCALCSIZE
                     # If wParam is True, we return 0 (valid rectangle) to indicate client area is entire window.
                     # We leave 1 pixel at the top to allow for system drag/snap gestures (almost 0).
                     if msg.wParam:
                         ptr = ctypes.cast(msg.lParam, ctypes.POINTER(ctypes.wintypes.RECT))
                         ptr[0].top += 1
                         return True, 0
        except Exception:
             pass
        return super().nativeEvent(eventType, message)

    def set_frameless(self, enabled):
        self._frameless_active = enabled
        if enabled and sys.platform == 'win32':
             # Logic: Set Qt Frameless (to signal Qt internal logic), 
             # but FORCE Windows Styles back to allow Snap/Shadow.
             # Then rely on WM_NCCALCSIZE to accept clicks/paint over titlebar area.
             
             # 1. Set Flags
             self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.Window)
             # Translucent helps with some resize glitches but user might want opaque?
             # User said: "dont just make it translucent". Try Opaque (attribute not set) 
             # or keep transparency support? 
             # Let's KEEP Translucent for rounded corners support, users can set background: black in CSS.
             self.setAttribute(Qt.WA_TranslucentBackground)
             
             # 2. Re-Apply Windows Styles (Snap/Shadow/Resize) that Qt removed
             hwnd = int(self.winId())
             GWL_STYLE = -16
             WS_CAPTION = 0x00C00000
             WS_THICKFRAME = 0x00040000
             WS_MINIMIZEBOX = 0x00020000
             WS_MAXIMIZEBOX = 0x00010000
             WS_SYSMENU = 0x00080000
             
             style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
             style |= WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU
             ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)
             
             # 3. Trigger Re-Layout (SWP_FRAMECHANGED)
             SWP_FRAMECHANGED = 0x0020
             SWP_NOZORDER = 0x0004
             SWP_NOMOVE = 0x0002
             SWP_NOSIZE = 0x0001
             ctypes.windll.user32.SetWindowPos(hwnd, 0, 0,0,0,0, SWP_FRAMECHANGED | SWP_NOZORDER | SWP_NOMOVE | SWP_NOSIZE)

class PySideEngine:
    def __init__(self, config, bound_functions=None):
        self.logger = logging.getLogger("Pytron.PySideEngine")
        # Fix: explicitly check is not None so we keep the reference to the empty dict passed in
        self._bound_functions = bound_functions if bound_functions is not None else {}
        self.config = config
        
        self.app = QApplication.instance() or QApplication(sys.argv)
        # Use our custom View
        self.view = PytronWebEngineView()
        self.channel = QWebChannel()
        self.view.page().setWebChannel(self.channel)

        
        # Bridge object to handle calls from JS
        class Bridge(QObject):
            # We use a signal to dispatch back to Python properly if needed, 
            # but slots are enough for direct calls.
            # However, QWebChannel requires predefined Slots. 
            # Since we have dynamic bindings, we can't define slots at runtime easily for the class.
            # A common workaround is a single `call` slot that takes the function name and args.
            
            @Slot(str, str, str)
            def call(self, name, seq, args_json):
                # Dispatch to the bound function
                if name in self._engine._bound_functions:
                    # Invoke the callback (which is the _callback wrapper in Webview class)
                    # The Webview._callback expects (seq, req, arg) ? 
                    # Wait, Webview.bind creates a C-callback. 
                    # We need to adapt it. 
                    
                    # For PySide, we can just call the python function directly.
                    # But we want to reuse the logic in Webview class (serialization etc).
                    # So we should call the wrapper.
                    
                    # Actually, the wrapper in Webview class is designed for the C-API.
                    # We might need to adjust the binding mechanism in Webview.py to separate logic from C-ctypes.
                    pass

        # To handle dynamic bindings in PySide6/QWebChannel, 
        # we usually expose a single object "pytron_bridge" with a generic method, Or
        # we dynamically extend the QObject.
        # Simplify: We will expose one object "pytron_internal" with `invoke(name, seq, args)`
        
        class PytronBridge(QObject):
            def __init__(self, engine):
                super().__init__()
                self.engine = engine

            @Slot(str, str, str)
            def invoke(self, name, seq, args_json):
                print(f"DEBUG: PySide Bridge Invoke: {name}")
                self.engine.dispatch_binding(name, seq, args_json)

        self.bridge = PytronBridge(self)
        self.channel.registerObject("pytron_internal", self.bridge)
        
        # Initialize Script to setup the JS side
        default_cm = "true" if config.get("default_context_menu", True) else "false"
        init_script = f"""
        window.pytron = window.pytron || {{}};
        window.pytron._callbacks = {{}};
        const config_default_context_menu = {default_cm};

        // Connect to QWebChannel
        new QWebChannel(qt.webChannelTransport, function(channel) {
            window.pytron_internal = channel.objects.pytron_internal;
            window.pytron.is_ready = true;
            console.log("Pytron PySide6 Bridge Connected");
            window.dispatchEvent(new Event('pytron-ready'));
            
            // Re-emit generic ready event for convenience
            if (window.pytron.onReady) window.pytron.onReady();
        });

        // Disable default context menu if requested in config
        if (!config_default_context_menu) {
            window.addEventListener('contextmenu', e => e.preventDefault());
        }

        // Generic Caller
        window.pytron.invoke = function(name, args) {
            return new Promise((resolve, reject) => {
                const seq = (Date.now() + Math.random()).toString();
                window.pytron._callbacks[seq] = { resolve, reject };
                
                // If bridge not ready, wait (simple retry or queue could be added here)
                if (window.pytron_internal) {
                    window.pytron_internal.invoke(name, seq, JSON.stringify(args));
                } else {
                    console.error("Pytron Bridge not connected yet");
                    reject("Bridge not connected");
                }
            });
        };
        
        // Resolver called by Python
        window.pytron._resolve = function(seq, status, result) {
            const cb = window.pytron._callbacks[seq];
            if (cb) {
                if (status === 0) {
                    cb.resolve(JSON.parse(result));
                } else {
                    cb.reject(JSON.parse(result));
                }
                delete window.pytron._callbacks[seq];
            }
        };
        """
        
        # Configure Settings to allow file:// access and mixed content if needed
        settings = self.view.page().settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        
        # Load QWebChannel.js content directly from resource
        qwebchannel_js = ""
        f = QFile(":/qtwebchannel/qwebchannel.js")
        if f.open(QIODevice.ReadOnly):
            print("DEBUG: Loaded qwebchannel.js from resources")
            qwebchannel_js = str(f.readAll(), 'utf-8')
            f.close()
        else:
            print("ERROR: Failed to load qwebchannel.js from resources!")

        # Combine library and init code
        full_script = qwebchannel_js + "\n" + init_script

        script = QWebEngineScript()
        script.setSourceCode(full_script) 
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setWorldId(QWebEngineScript.MainWorld)
        self.view.page().scripts().insert(script)
        
        # Configure Window
        self.view.setWindowTitle(config.get("title", "Pytron App"))
        w, h = config.get("dimensions", (800, 600))
        self.view.resize(w, h)
        
        if "icon" in config:
             self.view.setWindowIcon(QIcon(config["icon"]))
             
        if config.get("frameless", False):
            self.make_frameless()

    def resolve(self, seq, status, result_json):
        # Escape JSON for JS string
        safe_result = json.dumps(result_json) 
        code = f"window.pytron._resolve('{seq}', {status}, {safe_result});"
        
        QTimer.singleShot(0, self.bridge, lambda: self.view.page().runJavaScript(code))

    def dispatch_binding(self, name, seq, args_json):
        if name in self._bound_functions:
            self._bound_functions[name](seq, args_json, None)

    def register_binding(self, name):
        js = f"""
        window['{name}'] = function(...args) {{
            return window.pytron.invoke('{name}', args);
        }};
        """
        script = QWebEngineScript()
        script.setName(f"binding_{name}")
        script.setSourceCode(js)
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setWorldId(QWebEngineScript.MainWorld)
        self.view.page().scripts().insert(script)
        self.eval_js(js)

    def load_url(self, url):
        self.view.load(QUrl.fromUserInput(url))

    def run(self):
        self.view.show()
        sys.exit(self.app.exec())
    
    def eval_js(self, code):
        self.view.page().runJavaScript(code)

    def set_title(self, title):
        self.view.setWindowTitle(title)
        
    def set_size(self, w, h):
        self.view.resize(w, h)

    def make_frameless(self):
        print("DEBUG: Setting Native Frameless (NCCALCSIZE)")
        self.view.set_frameless(True)
        
    def start_drag(self):
        print("DEBUG: Starting System Move")
        window = self.view.window()
        
        # Try Qt Native Move
        if window and window.windowHandle():
            started = window.windowHandle().startSystemMove()
            if started:
                return

        # Fallback to Windows API if on Windows
        import platform
        if platform.system() == "Windows":
             try:
                 print("DEBUG: Using Windows API Drag Fallback")
                 import ctypes
                 hwnd = int(self.view.winId())
                 ctypes.windll.user32.ReleaseCapture()
                 ctypes.windll.user32.SendMessageW(hwnd, 0xA1, 2, 0)
             except Exception as e:
                 print(f"DEBUG: Windows Drag Failed: {e}")
