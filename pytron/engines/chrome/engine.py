import os
import sys
import json
import logging
import ctypes
import platform
import subprocess
import urllib.parse
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

    def webview_create(self, debug, window, root_path=None):
        self.adapter.send(
            {
                "action": "init",
                "options": {
                    "debug": bool(debug),
                    "root": root_path,  # Pass the root path!
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
                    "start_minimized": self.adapter.config.get(
                        "start_minimized", False
                    ),
                    "transparent": self.adapter.config.get("transparent", False),
                    "center": self.adapter.config.get("center", True),
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

    def create_tray(self, icon_path, tooltip="Pytron App"):
        self.adapter.send(
            {"action": "create_tray", "icon": str(icon_path), "tooltip": tooltip}
        )

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

        # --- Replicate Webview Basic Init ---
        self.config = config
        self.id = config.get("id") or str(int(__import__("time").time() * 1000))

        # 1. Resolve Root
        if getattr(sys, "frozen", False):
            self._app_root = __import__("pathlib").Path(sys.executable).parent
            if hasattr(sys, "_MEIPASS"):
                self._app_root = __import__("pathlib").Path(sys._MEIPASS)
        else:
            self._app_root = __import__("pathlib").Path.cwd()

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

        # 3. Resolve Chrome Binary
        shell_path = config.get("engine_path")
        if not shell_path:
            renamed_engine = None
            if getattr(sys, "frozen", False):
                exe_name = os.path.splitext(os.path.basename(sys.executable))[0]
                candidates = [
                    f"{exe_name}.exe",
                    f"{exe_name}-Renderer.exe",
                    f"{exe_name}-Engine.exe",
                    "electron.exe",
                ]
                base_dir = os.path.dirname(sys.executable)
                std_dir = os.path.join(base_dir, "pytron", "dependencies", "chrome")
                mei_dir = getattr(sys, "_MEIPASS", None)
                search_roots = [base_dir]
                if std_dir:
                    search_roots.append(std_dir)
                if mei_dir:
                    search_roots.append(
                        os.path.join(mei_dir, "pytron", "dependencies", "chrome")
                    )
                for root in search_roots:
                    if not os.path.exists(root):
                        continue
                    for candidate in candidates:
                        candidate_path = os.path.join(root, candidate)
                        if os.path.exists(candidate_path):
                            if os.path.abspath(candidate_path) == os.path.abspath(
                                sys.executable
                            ):
                                continue
                            renamed_engine = candidate_path
                            break
                    if renamed_engine:
                        break

            if renamed_engine:
                shell_path = renamed_engine
            else:
                global_path = os.path.expanduser(
                    "~/.pytron/engines/chrome/electron.exe"
                )
                if os.path.exists(global_path):
                    shell_path = global_path
                else:
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
                        self.logger.warning(
                            "Chrome Engine not found. Auto-provisioning..."
                        )
                        forge = ChromeForge()
                        shell_path = forge.provision()

        # 4. Resolve Root Path (Robust Common Ancestor Logic)
        # We need a root that covers both 'frontend/dist' and 'plugins'
        raw_url = config.get("url", "")
        root_path = str(self._app_root)  # Default fallback
        navigate_url = raw_url

        if not raw_url.startswith(("http:", "https:", "pytron:")):
            p = __import__("pathlib").Path(raw_url).resolve()
            # Assume standard structure: <root>/frontend/dist/index.html
            # We want <root> to be the base.
            # Heuristic: Go up until we find 'plugins' folder or hit root
            candidate = p.parent
            found_root = None
            for _ in range(4):  # Check up to 4 levels up
                if (candidate / "plugins").exists():
                    found_root = candidate
                    break
                candidate = candidate.parent

            if found_root:
                root_path = str(found_root)
                try:
                    rel = os.path.relpath(str(p), str(found_root))
                    navigate_url = (
                        f"pytron://app/{urllib.parse.quote(rel.replace(os.sep, '/'))}"
                    )
                except ValueError:
                    pass
            else:
                root_path = str(p.parent)
                navigate_url = f"pytron://app/{urllib.parse.quote(p.name)}"

        self.logger.info(f"Target Root: {root_path}")
        self.logger.info(f"Navigating to: {navigate_url}")

        if "cwd" not in config:
            config["cwd"] = root_path

        # 5. Initialize Bridge & Start Adapter
        self.logger.info(f"Using Chrome Shell (v3): {shell_path}")
        self.adapter = ChromeAdapter(shell_path, config)
        self.bridge = ChromeBridge(self.adapter)

        self.adapter.start()
        self.adapter.bind_raw(self._handle_ipc_message)

        # Mock Window Object
        if "resizable" not in config:
            config["resizable"] = True

        self.w = self.bridge.webview_create(
            config.get("debug", False), None, root_path=root_path
        )

        # Safety Net
        self.native = None

        # 5. Bindings & Init
        self._init_bindings()

        # 6. Window Settings
        self.set_title(config.get("title", "Pytron App"))
        w, h = config.get("dimensions", [800, 600])
        self.set_size(w, h)
        if not config.get("start_hidden", False):
            self.show()

        # Navigate
        self.navigate(navigate_url)

        # --- Platform Helpers (All Platforms) ---
        self._platform = None
        current_sys = platform.system()
        try:
            if current_sys == "Windows":
                from ...platforms.windows import WindowsImplementation

                self._platform = WindowsImplementation()
            elif current_sys == "Darwin":
                from ...platforms.darwin import DarwinImplementation

                self._platform = DarwinImplementation()
            elif current_sys == "Linux":
                from ...platforms.linux import LinuxImplementation

                self._platform = LinuxImplementation()
        except Exception as e:
            self.logger.warning(f"Failed to load {current_sys} Platform helpers: {e}")

        # 7. JS Init Shim (With Proxy for Dynamic Methods)
        init_js = f"""
        (function() {{
            try {{
                if (!window.pytron) {{
                    window.pytron = {{ is_ready: true, id: "{self.id}" }};
                }} else {{
                    window.pytron.is_ready = true;
                    window.pytron.id = "{self.id}";
                }}
            }} catch (e) {{
                // Already read-only or handled by bridge
            }}
            
            window.pytron_is_native = true;

            // --- DE-BROWSERIFY CORE ---
            (function() {{
                const isDebug = {str(self.config.get("debug", False)).lower()};
                
                // 1. Kill Context Menu (Unless debugging)
                if (!isDebug) {{
                    document.addEventListener('contextmenu', e => e.preventDefault());
                }}

                // 2. Kill "Ghost" Drags (images/links flying around)
                document.addEventListener('dragstart', e => {{
                    if (e.target.tagName === 'IMG' || e.target.tagName === 'A') e.preventDefault();
                }});

                // 3. Kill Browser Shortcuts
                window.addEventListener('keydown', e => {{
                    const forbidden = ['r', 'p', 's', 'j', 'u', 'f'];
                    if (e.ctrlKey && forbidden.includes(e.key.toLowerCase())) e.preventDefault();
                    if (e.key === 'F5' || e.key === 'F3' || (e.ctrlKey && e.key === 'f')) e.preventDefault();
                    // Block Zoom
                    if (e.ctrlKey && (e.key === '=' || e.key === '-' || e.key === '0')) e.preventDefault();
                }}, true);

                // 4. Kill System UI Styles (Selection, Outlines, Rubber-banding)
                const style = document.createElement('style');
                style.textContent = `
                    * {{ 
                        -webkit-user-select: none; 
                        user-select: none;
                        -webkit-user-drag: none; 
                        -webkit-tap-highlight-color: transparent;
                        outline: none !important;
                    }}
                    input, textarea, [contenteditable], [contenteditable] * {{ 
                        -webkit-user-select: text !important; 
                        user-select: text !important;
                    }}
                    html, body {{
                        overscroll-behavior: none !important;
                        cursor: default;
                    }}
                    a, button, input[type="button"], input[type="submit"] {{
                        cursor: pointer;
                    }}
                `;
                document.head ? document.head.appendChild(style) : document.addEventListener('DOMContentLoaded', () => document.head.appendChild(style));
            }})();

            // Universal IPC Bridge
            if (!window.__pytron_native_bridge) {{
                window.__pytron_native_bridge = (method, args) => {{
                    const seq = Math.random().toString(36).substring(2, 10);
                    if (window.ipc) {{
                         window.ipc.postMessage(JSON.stringify({{id: seq, method: method, params: args}}));
                    }}
                    return new Promise((resolve, reject) => {{
                        window._rpc = window._rpc || {{}};
                        window._rpc[seq] = {{resolve, reject}};
                    }});
                }};
            }}

            // Dynamic Proxy to handle ANY method call from frontend (hide, center, etc.)
            try {{
                const existing = window.pytron;
                window.pytron = new Proxy(existing || {{}}, {{
                    get: function(target, prop) {{
                        if (prop in target) return target[prop];
                        // If not found, assume it's a bridge call
                        return (...args) => window.__pytron_native_bridge(prop, args);
                    }}
                }});
            }} catch (e) {{
                // Skip proxy if window.pytron is read-only
            }}
            
            // Standard Pollys & Asset Bridge
            window.pytron_drag = () => window.__pytron_native_bridge('pytron_drag', []);
            window.pytron_minimize = () => window.__pytron_native_bridge('pytron_minimize', []);
            window.pytron_get_asset = (key) => window.__pytron_native_bridge('pytron_get_asset', [key]);
            
            window['pytron_drag'] = window.pytron_drag;
            window['pytron_minimize'] = window.pytron_minimize;
            window['pytron_get_asset'] = window.pytron_get_asset;
            window['__pytron_vap_get'] = window.pytron_get_asset; 

        }})();
        """
        self.eval(init_js)

        # Force Resizable Update (Fix gray maximize button)
        # Sometimes init flag is overridden by window style defaults in Electron
        self.bridge.adapter.send({"action": "set_resizable", "resizable": True})

    @property
    def hwnd(self):
        """Override to return Electron HWND instead of native engine HWND."""
        if hasattr(self.bridge, "real_hwnd"):
            return self.bridge.real_hwnd
        return 0

    def _handle_ipc_message(self, msg):
        import inspect
        import asyncio

        msg_type = msg.get("type")
        payload = msg.get("payload")

        # DEBUG: Log all lifecycle events to trace HWND
        if msg_type == "lifecycle":
            self.logger.info(f"Chrome Lifecycle Event: {payload}")

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

    def serve_data(self, key, data, mime="application/octet-stream"):
        """Sends binary data to the Node process for pytron:// serving."""
        import base64

        try:
            b64_data = base64.b64encode(data).decode("utf-8")
            self.bridge.adapter.send(
                {
                    "action": "serve_data",
                    "key": key,
                    "data": b64_data,
                    "mime": mime,
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to serve data for key {key}: {e}")

    def unserve_data(self, key):
        self.bridge.adapter.send({"action": "unserve_data", "key": key})

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
