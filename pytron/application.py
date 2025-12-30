import os
import sys
import json
import inspect
import typing
from typing import Optional, List, Dict, Union, Any, Callable
import shutil
from .utils import get_resource_path
from .state import ReactiveState
from .webview import Webview

from .serializer import pydantic
import logging
from .exceptions import ConfigError, BridgeError
from .tray import SystemTray
from .shortcuts import ShortcutManager

class App:
    def __init__(self, config_file='settings.json'):
        self.windows = []
        self.is_running = False
        self.config = {}
        self._exposed_functions = {} # Global functions for all windows
        self._exposed_ts_defs = {} # Store generated TS definitions
        self._pydantic_models = {} # Store pydantic models to generate interfaces for
        self.shortcuts = {} # Decorator storage
        self.storage_path = None # Initialize storage_path
        self.plugins = [] # Store loaded plugins
        self._on_exit_callbacks = [] # Callbacks to run on exit
        
        self.tray: Optional[SystemTray] = None
        self.shortcut_manager = ShortcutManager()
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='[Pytron] %(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        self.logger = logging.getLogger("Pytron")

        self.state = ReactiveState(self) # Magic state object
        
        # Check for Deep Link Startup
        self.state.launch_url = None
        if len(sys.argv) > 1:
            possible_url = sys.argv[1]
            if possible_url.startswith("pytron:") or "://" in possible_url: # Heuristic
                self.logger.info(f"App launched via Deep Link: {possible_url}")
                self.state.launch_url = possible_url

        # Load config
        # Try to find settings.json
        # 1. Using get_resource_path (handles PyInstaller)
        path = get_resource_path(config_file)
        if not os.path.exists(path):
            # 2. Try relative to the current working directory (useful during dev if running from root)
            path = os.path.abspath(config_file)
            
        if os.path.exists(path):
            try:
                import json
                with open(path, 'r') as f:
                    self.config = json.load(f)
                # Update logging level if debug is enabled
                if self.config.get('debug', False):
                    self.logger.setLevel(logging.DEBUG)
                    # Ensure root handlers capture debug logs
                    for handler in logging.root.handlers:
                        handler.setLevel(logging.DEBUG)
                    self.logger.debug("Debug mode enabled in settings.json. Verbose logging active.")
                    
                    # Check for Dev Server Override
                    dev_url = os.environ.get('PYTRON_DEV_URL')
                    if dev_url:
                        self.config['url'] = dev_url
                        self.logger.info(f"Dev mode: Overriding URL to {dev_url}")

                # Check version compatibility
                config_version = self.config.get('pytron_version')
                if config_version:
                    try:
                        from . import __version__
                        if config_version != __version__:
                            self.logger.warning(f"Project settings version ({config_version}) does not match installed Pytron version ({__version__}).")
                    except ImportError:
                        self.logger.debug("Could not verify Pytron version compatibility.")
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse settings.json: {e}")
                raise ConfigError(f"Invalid JSON in settings file: {path}") from e
            except Exception as e:
                self.logger.error(f"Failed to load settings: {e}")
                raise ConfigError(f"Could not load settings from {path}") from e
        else:
            self.logger.warning(f"Settings file not found at {path}. Using default configuration.")

        # --- Initialize Environment & Storage Path ---
        # Calculate this immediately so the environment is sanitized before the user runs logic
        title = self.config.get('title', 'Pytron App')
        # Sanitize title for folder name
        safe_title = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in title).strip('_')
        
        # Set Identity for Taskbar/System
        self._register_app_id(title, safe_title)
        
        if sys.platform == 'win32':
            base_path = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        elif os.environ.get('PYTHON_PLATFORM') == 'android':
            # On Android, we must use the app's private files directory.
            # The JNI bridge sets PYTHONHOME to filesDir/python
            python_home = os.environ.get('PYTHONHOME')
            if python_home:
                base_path = os.path.dirname(python_home)
            else:
                base_path = os.path.expanduser('~')
        else:
            base_path = os.path.expanduser('~/.config')
        
        # If in debug mode, use a unique path to allow multiple instances
        if self.config.get('debug', False):
            self.storage_path = os.path.join(base_path, f"{safe_title}_Dev_{os.getpid()}")
        else:
            self.storage_path = os.path.join(base_path, safe_title)

        # Save original root for resource resolution
        if getattr(sys, 'frozen', False):
            self.app_root = os.path.dirname(sys.executable)
        else:
            self.app_root = os.getcwd()

        # FIX: Resolve URL and icon to absolute paths before changing CWD
        def resolve_resource(path):
            if not path or path.startswith(('http:', 'https:', 'file:')) or os.path.isabs(path):
                return path
            
            # 1. Try inside _internal (PyInstaller 6+ onedir) - BEST for assets
            internal = os.path.join(self.app_root, "_internal", path)
            if os.path.exists(internal): return internal
            
            # 2. Try relative to app_root (root of installation)
            candidate = os.path.join(self.app_root, path)
            if os.path.exists(candidate): return candidate
            
            # 3. Fallback to resource path (handles _MEIPASS)
            return get_resource_path(path)

        if 'url' in self.config:
            self.config['url'] = resolve_resource(self.config['url'])
        
        if 'icon' in self.config:
            orig_icon = self.config['icon']
            resolved_icon = resolve_resource(orig_icon)
            if os.path.exists(resolved_icon):
                self.config['icon'] = resolved_icon
                self.logger.info(f"Resolved icon to: {resolved_icon}")
            else:
                self.logger.warning(f"Could not find icon at: {orig_icon} (searched in {self.app_root})")
            
        try:
            os.makedirs(self.storage_path, exist_ok=True)
            
            # Change CWD to storage_path to allow writing logs/dbs
            # consistently in both Dev and Frozen/Packaged modes.
            # This redirects relative file actions to the AppData/Config directory.
            os.chdir(self.storage_path)
            self.logger.info(f"Changed Working Directory to: {self.storage_path}")
        except Exception as e:
            self.logger.warning(f"Could not create storage directory at {self.storage_path}: {e}")
            pass

    def load_plugin(self, manifest_path):
        """
        Loads a plugin from a manifest.json file.
        """
        from .plugin import Plugin, PluginError
        try:
            plugin = Plugin(manifest_path)
            plugin.check_dependencies()
            plugin.load(self)
            self.plugins.append(plugin)
            self.logger.info(f"Loaded plugin: {plugin.name} v{plugin.version}")
        except PluginError as e:
            self.logger.error(f"Failed to load plugin from {manifest_path}: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error loading plugin from {manifest_path}: {e}")

    def _register_app_id(self, title, safe_title):
        # Register App ID for process identity (Taskbar grouping/Notifications/Task Manager)
        # Windows uses this ID to group child processes (like WebView2) under the same header.
        author = self.config.get('author', 'PytronUser')
        
        # Ensure we have a valid safe_title
        if not safe_title:
             safe_title = "".join([c for c in (title or "Pytron") if c.isalnum()]) or "PytronApp"
             
        # AUMID format: Company.Product.SubComponent.Version
        app_id = f"{author}.{safe_title}.App"
        
        # Also try to set the process name if possible (purely for identification)
        if sys.platform == 'win32':
             try:
                 from .platforms.windows import WindowsImplementation
                 WindowsImplementation().set_app_id(app_id)
                 self.logger.debug(f"Set Windows AppUserModelID: {app_id}")
             except Exception as e:
                 self.logger.debug(f"Failed to set App ID: {e}")
        elif sys.platform == 'linux':
             try:
                 from .platforms.linux import LinuxImplementation
                 LinuxImplementation().set_app_id(safe_title)
             except Exception: pass
        elif sys.platform == 'darwin':
             try:
                 from .platforms.darwin import DarwinImplementation
                 DarwinImplementation().set_app_id(title)
             except Exception: pass

    def register_protocol(self, scheme="pytron"):
        """
        Registers a custom URI scheme (e.g. 'pytron://') for the application.
        On Windows, this modifies the Registry.
        """
        # We need an instance of platform specific impl.
        # But Webview holds it. App doesn't directly hold platform unless we refactor.
        # Temp workaround: Instantiate platform impl directly since it's just registry logic
        try:
             import platform
             if platform.system() == "Windows":
                 from .platforms.windows import WindowsImplementation
                 impl = WindowsImplementation()
                 if impl.register_protocol(scheme):
                     self.logger.info(f"Successfully registered protocol: {scheme}://")
                 else:
                     self.logger.warning(f"Failed to register protocol: {scheme}://")
             else:
                 self.logger.warning(f"Protocol registration not implemented for {platform.system()}")
        except Exception as e:
             self.logger.error(f"Error registering protocol: {e}")

    def create_window(self, **kwargs):
        """
        Creates a new window with the App's configuration, optionally overridden by kwargs.
        Automatically binds any exposed functions to the new window.
        """
        # Resolve 'url' in kwargs if present (assuming relative to app_root)
        if 'url' in kwargs and not getattr(sys, 'frozen', False):
             if not kwargs['url'].startswith(('http:', 'https:', 'file:')):
                  if not os.path.isabs(kwargs['url']):
                        kwargs['url'] = os.path.join(self.app_root, kwargs['url'])

        # Merge config
        window_config = self.config.copy()
        window_config.update(kwargs)
        
        # Defer navigation until after bindings are applied
        original_url = window_config.get("url")
        window_config["navigate_on_init"] = False
        
        window = Webview(config=window_config)
        self.windows.append(window)
        
        # Bind exposed functions to the new window
        for name, data in self._exposed_functions.items():
            func = data['func']
            secure = data['secure']
            
            # Legacy check: if for some reason a raw class ended up here (unlikely with current expose logic)
            if isinstance(func, type):
                try:
                    window.expose(func)
                except Exception as e:
                    self.logger.debug(f"Failed to expose class {name} directly: {e}. Falling back to binding as callable.")
                    window.bind(name, func, secure=secure)
            else:
                window.bind(name, func, secure=secure)
        
        # Now navigate, sending all bindings (scripts) in the payload
        if original_url:
            window.navigate(window_config.get("url", original_url))
            
        # Automatic centering if requested
        if window_config.get("center", True): # Default to true for Raycast-like experience
             window.center()

        # Set window icon if specified
        icon = window_config.get("icon")
        if icon:
            window.set_icon(icon)
        return window

    def run(self, **kwargs):
        self.is_running = True
        
        # Respect override if provided
        if 'storage_path' in kwargs:
            pass 
        else:
            kwargs['storage_path'] = self.storage_path
            
        # Set WebView2 User Data Folder to avoid writing to exe dir
        if sys.platform == 'win32' and 'storage_path' in kwargs:
             os.environ["WEBVIEW2_USER_DATA_FOLDER"] = kwargs['storage_path']

        # Ensure at least one window exists
        if not self.windows:
            self.create_window()

        # Start the main window loop (usually blocks)
        if len(self.windows) > 0:
            # Check for PyInstaller Splash Screen and close it before showing UI
            try:
                import pyi_splash
                if pyi_splash.is_alive():
                    pyi_splash.close()
                    self.logger.info("Closed splash screen.")
            except ImportError:
                pass
            except Exception as e:
                self.logger.debug(f"Error closing splash screen: {e}")
            
            # Start global shortcuts
            for combo, func in self.shortcuts.items():
                self.shortcut_manager.register(combo, func)
                
            # Start tray if configured
            if self.tray:
                self.tray.start(self)

            self.windows[0].start()
            
        self.is_running = False
        
        # Execute on_exit callbacks
        for callback in self._on_exit_callbacks:
            try:
                if inspect.iscoroutinefunction(callback):
                    # We can't easily await here since we might be off the main loop, 
                    # but typically cleanup is sync. If async is needed, we'd need a runner.
                    # For now, warn or try to run.
                    pass 
                else:
                    callback()
            except Exception as e:
                self.logger.error(f"Error in on_exit callback: {e}")

        # Cleanup Tray
        if self.tray:
            self.tray.stop()
        self.shortcut_manager.stop()
        
        # Cleanup dev storage if needed
        if self.config.get('debug', False) and 'storage_path' in kwargs:
             path = kwargs['storage_path']
             if os.path.isdir(path) and f"_Dev_{os.getpid()}" in path:
                  try:
                      shutil.rmtree(path, ignore_errors=True)
                  except Exception as e:
                      self.logger.debug(f"Failed to cleanup dev storage: {e}")
                      pass

    def on_exit(self, func):
        """
        Register a function to run when the application is exiting.
        Can be used as a decorator: @app.on_exit
        """
        self._on_exit_callbacks.append(func)
        return func

    def broadcast(self, event_name, data):
        """
        Emits an event to ALL active windows.
        Useful for app-wide notifications or state updates.
        Safe to call even if no windows are open (no-op).
        """
        if self.windows:
            for window in self.windows:
                try:
                    window.emit(event_name, data)
                except Exception as e:
                    self.logger.warning(f"Failed to broadcast to window: {e}")

    def emit(self, event_name, data):
        """
        Alias for broadcast. Emits to all windows.
        """
        self.broadcast(event_name, data)

    def setup_tray(self, title: Optional[str] = None, icon: Optional[str] = None):
        """
        Initializes the system tray icon for the application.
        """
        if not title:
            title = self.config.get('title', 'Pytron')
        
        if not icon and 'icon' in self.config:
            icon = self.config['icon']
            
        if icon and not os.path.isabs(icon):
            icon = os.path.join(self.app_root, icon)
        
        self.tray = SystemTray(title, icon)
        return self.tray

    def setup_tray_standard(self, title: Optional[str] = None, icon: Optional[str] = None):
        """
        Sets up a standard tray with 'Show App' and 'Quit' items.
        """
        tray = self.setup_tray(title, icon)
        tray.add_item("Show App", self.show)
        tray.add_item("Hide App", self.hide)
        tray.add_separator()
        tray.add_item("Quit", self.quit)
        return tray

    def hide(self):
        """Hides all application windows (Daemon mode)."""
        if self.windows:
            for window in self.windows:
                try:
                    window.hide()
                except Exception:
                    pass

    def show(self):
        """Shows all application windows."""
        if self.windows:
            for window in self.windows:
                try:
                    window.show()
                except Exception:
                    pass

    def notify(self, title, message, type="info", duration=5000):
        """Sends a notification command to the frontend UI of all windows."""
        if self.windows:
            for window in self.windows:
                try:
                    window.notify(title, message, type, duration)
                except Exception:
                    pass

    def system_notification(self, title: Optional[str] = None, message: str = ""):
        """Sends a system-level (tray/toast) notification via the OS."""
        if not title:
            title = self.config.get('author', self.config.get('title', 'Pytron'))
            
        icon = self.config.get('icon')
        
        if self.windows:
            for window in self.windows:
                try:
                    window.system_notification(title, message, icon=icon)
                    break 
                except Exception:
                    pass

    def dialog_open_file(self, title="Open File", default_path=None, file_types=None):
        """Opens a native file selection dialog. Returns the selected path or None."""
        if self.windows:
            return self.windows[0].dialog_open_file(title, default_path, file_types)
        return None

    def dialog_save_file(self, title="Save File", default_path=None, default_name=None, file_types=None):
        """Opens a native save file dialog. Returns the selected path or None."""
        if self.windows:
            return self.windows[0].dialog_save_file(title, default_path, default_name, file_types)
        return None

    def dialog_open_folder(self, title="Select Folder", default_path=None):
        """Opens a native folder selection dialog. Returns the selected path or None."""
        if self.windows:
            return self.windows[0].dialog_open_folder(title, default_path)
        return None

    def message_box(self, title, message, style=0):
        """
        Shows a native message box.
        Styles: 0=OK, 1=OK/Cancel, 2=Abort/Retry/Ignore, 3=Yes/No/Cancel, 4=Yes/No, 5=Retry/Cancel
        Returns: 1=OK, 2=Cancel, 6=Yes, 7=No
        """
        if self.windows:
            return self.windows[0].message_box(title, message, style)
        return 0

    def set_start_on_boot(self, enable=True):
        """
        Enables or disables automatic application startup on system boot.
        """
        app_name = self.config.get('title', 'PytronApp')
        # Sanitize for registry key
        safe_name = "".join(c if c.isalnum() else "_" for c in app_name)
        
        exe_path = sys.executable
        if not getattr(sys, 'frozen', False):
            # Development mode: python.exe "path/to/script.py"
            # This is tricky because we need arguments.
            # Windows registry Run key handles arguments fine.
            main_script = os.path.abspath(sys.argv[0])
            exe_path = f'"{sys.executable}" "{main_script}"'
        else:
            exe_path = f'"{exe_path}"' # Quote for safety
            
        # We need a platform instance.
        # Since App doesn't hold it, we instantiate temporarily or grab from first window
        if self.windows:
             # Best effort
             try:
                 return self.windows[0]._platform.set_launch_on_boot(safe_name, exe_path, enable)
             except Exception: pass
        
        # Fallback if no window yet or needed
        try:
            import platform
            if platform.system() == "Windows":
                 from .platforms.windows import WindowsImplementation
                 return WindowsImplementation().set_launch_on_boot(safe_name, exe_path, enable)
        except Exception as e:
            self.logger.warning(f"Could not set start on boot: {e}")
            
    def quit(self):
        """Gracefully quits the application by closing all windows."""
        for window in self.windows:
            window.close(force=True)
    def _python_type_to_ts(self, py_type):
        if py_type == str: return "string"
        if py_type == int: return "number"
        if py_type == float: return "number"
        if py_type == bool: return "boolean"
        if py_type == type(None): return "void"
        if py_type == list: return "any[]"
        if py_type == dict: return "Record<string, any>"
        
        # Handle Pydantic Models
        if pydantic and isinstance(py_type, type) and issubclass(py_type, pydantic.BaseModel):
            model_name = py_type.__name__
            self._pydantic_models[model_name] = py_type
            return model_name

        # Handle typing module
        origin = getattr(py_type, '__origin__', None)
        args = getattr(py_type, '__args__', ())
        
        if origin is list or origin is typing.List:
            if args:
                return f"{self._python_type_to_ts(args[0])}[]"
            return "any[]"
        
        if origin is dict or origin is typing.Dict:
            if args and len(args) == 2:
                k = self._python_type_to_ts(args[0])
                v = self._python_type_to_ts(args[1])
                if k == "number":
                    return f"Record<number, {v}>"
                return f"Record<string, {v}>"
            return "Record<string, any>"
            
        if origin is typing.Union:
            non_none = [t for t in args if t != type(None)]
            # Check for pydantic models inside Union
            if pydantic:
                for t in non_none:
                     if isinstance(t, type) and issubclass(t, pydantic.BaseModel):
                          self._pydantic_models[t.__name__] = t

            if len(non_none) == len(args):
                return " | ".join([self._python_type_to_ts(t) for t in args])
            else:
                if len(non_none) == 1:
                    return f"{self._python_type_to_ts(non_none[0])} | null"
                return " | ".join([self._python_type_to_ts(t) for t in non_none]) + " | null"

        return "any"

    def _generate_pydantic_interface(self, model_name, model_cls):
        lines = [f"  export interface {model_name} {{"]
        
        # Pydantic v1 vs v2
        fields = {}
        if hasattr(model_cls, 'model_fields'): # v2
            fields = model_cls.model_fields
        elif hasattr(model_cls, '__fields__'): # v1
            fields = model_cls.__fields__
            
        for field_name, field in fields.items():
            # Get type annotation
            if hasattr(field, 'annotation'): # v2
                py_type = field.annotation
            elif hasattr(field, 'type_'): # v1
                py_type = field.type_
            else:
                py_type = typing.Any
                
            ts_type = self._python_type_to_ts(py_type)
            
            # Check if optional
            is_optional = False
            if hasattr(field, 'is_required'): # v2
                 is_optional = not field.is_required()
            elif hasattr(field, 'required'): # v1
                 is_optional = not field.required
            
            suffix = "?" if is_optional else ""
            lines.append(f"    {field_name}{suffix}: {ts_type};")
            
        lines.append("  }")
        return "\n".join(lines)

    def _get_ts_definition(self, name, func):
        try:
            sig = inspect.signature(func)
            params = []
            
            for param_name, param in sig.parameters.items():
                if param_name == "self": continue
                
                py_type = param.annotation
                ts_type = self._python_type_to_ts(py_type)
                if py_type == inspect.Parameter.empty:
                    ts_type = "any"
                    
                params.append(f"{param_name}: {ts_type}")
            
            param_str = ", ".join(params)
            
            return_annotation = sig.return_annotation
            ts_return = self._python_type_to_ts(return_annotation)
            if return_annotation == inspect.Parameter.empty:
                ts_return = "any"
            
            lines = []
            doc = inspect.getdoc(func)
            if doc:
                lines.append("    /**")
                for line in doc.split('\n'):
                    lines.append(f"     * {line}")
                lines.append("     */")
            
            lines.append(f"    {name}({param_str}): Promise<{ts_return}>;")
            return "\n".join(lines)
            
        except Exception as e:
            self.logger.warning(f"Could not generate types for {name}: {e}")
            return f"    {name}(...args: any[]): Promise<any>;"

    def expose(self, func=None, name=None, secure=False):
        """
        Expose a function to ALL windows created by this App.
        Can be used as a decorator: @app.expose or @app.expose(secure=True)
        """
        # Case 1: Used as @app.expose(secure=True) - func is None
        if func is None:
            def decorator(f):
                self.expose(f, name=name, secure=secure)
                return f
            return decorator
        
        # Case 2: Used as @app.expose or app.expose(func)
        # If the user passed a class or an object (bridge), expose its public callables
        if isinstance(func, type) or (not callable(func) and hasattr(func, '__dict__')):
            # Try to instantiate the class if a class was provided, otherwise use the instance
            bridge = None
            if isinstance(func, type):
                try:
                    bridge = func()
                except Exception:
                    # Could not instantiate; fall back to using the class object itself
                    bridge = func
            else:
                bridge = func

            for attr_name in dir(bridge):
                if attr_name.startswith('_'):
                    continue
                try:
                    attr = getattr(bridge, attr_name)
                except Exception:
                    continue
                if callable(attr):
                    try:
                        # For classes, we assume default security unless specified? 
                        # Or maybe we shouldn't support granular security on class-based expose yet for simplicity
                        # just pass 'secure' to all methods.
                        self._exposed_functions[attr_name] = {'func': attr, 'secure': secure}
                        self._exposed_ts_defs[attr_name] = self._get_ts_definition(attr_name, attr)
                    except Exception:
                        pass
            return func

        if name is None:
            name = func.__name__
        
        self._exposed_functions[name] = {'func': func, 'secure': secure}
        self._exposed_ts_defs[name] = self._get_ts_definition(name, func)
        return func

    def shortcut(self, key_combo, func=None):
        """
        Register a global keyboard shortcut for all windows.
        Example: @app.shortcut('Ctrl+Q')
        """
        if func is None:
            def decorator(f):
                self.shortcut(key_combo, f)
                return f
            return decorator
        self.shortcuts[key_combo] = func
        return func

    def generate_types(self, output_path="frontend/src/pytron.d.ts"):
        """
        Generates TypeScript definitions for all exposed functions.
        """
        ts_lines = [
            "// Auto-generated by Pytron. Do not edit manually.",
            "// This file provides type definitions for the Pytron client.",
            "",
            "declare module 'pytron-client' {",
        ]

        # 0. Add Pydantic Interfaces
        # We need to process exposed functions first to populate _pydantic_models
        # But wait, _exposed_ts_defs are already generated during @expose.
        # So _pydantic_models should be populated if they were used in signatures.
        # However, nested models might be missed if we don't recurse properly in _python_type_to_ts.
        # My current _python_type_to_ts does recurse for List/Dict/Union, so it should find them.
        
        # We iterate a copy because generating one interface might discover more models (nested)
        processed_models = set()
        while True:
            current_models = set(self._pydantic_models.keys())
            new_models = current_models - processed_models
            if not new_models:
                break
            
            for model_name in new_models:
                model_cls = self._pydantic_models[model_name]
                ts_lines.append(self._generate_pydantic_interface(model_name, model_cls))
                processed_models.add(model_name)

        ts_lines.append("")
        ts_lines.append("  export interface PytronClient {")
        ts_lines.append("    /**")
        ts_lines.append("     * Local state cache synchronized with the backend.")
        ts_lines.append("     */")
        ts_lines.append("    state: Record<string, any>;")
        ts_lines.append("")
        ts_lines.append("    /**")
        ts_lines.append("     * Listen for an event sent from the Python backend.")
        ts_lines.append("     */")
        ts_lines.append("    on(event: string, callback: (data: any) => void): void;")
        ts_lines.append("")
        ts_lines.append("    /**")
        ts_lines.append("     * Remove an event listener.")
        ts_lines.append("     */")
        ts_lines.append("    off(event: string, callback: (data: any) => void): void;")
        ts_lines.append("")
        ts_lines.append("    /**")
        ts_lines.append("     * Wait for the backend to be connected.")
        ts_lines.append("     */")
        ts_lines.append("    waitForBackend(timeout?: number): Promise<void>;")
        ts_lines.append("")
        ts_lines.append("    /**")
        ts_lines.append("     * Log a message to the Python console.")
        ts_lines.append("     */")
        ts_lines.append("    log(message: string): Promise<void>;")
        ts_lines.append("")

        # 1. Add User Exposed Functions (pre-calculated in expose)
        for def_str in self._exposed_ts_defs.values():
            ts_lines.append(def_str)


        # 3. Add Window methods
        # Map exposed name to Window class method name
        win_map = {
            'minimize': 'minimize',
            'toggle_maximize': 'toggle_maximize',
            'close': 'close',
            'hide': 'hide',
            'show': 'show',
            'notify': 'notify',
            'start_drag': 'start_drag',
            'set_title': 'set_title',
            'set_size': 'set_size',
            'center': 'center',
            'system_notification': 'system_notification',
            'set_bounds': 'set_bounds',
        }
        for exposed_name, method_name in win_map.items():
            method = getattr(Webview, method_name, None)
            if method:
                ts_lines.append(self._get_ts_definition(exposed_name, method))
        # 4. Add dynamic methods that are not on Window class
        ts_lines.append("    trigger_shortcut(combo: string): Promise<boolean>;")
        ts_lines.append("    get_registered_shortcuts(): Promise<string[]>;")

        ts_lines.append("  }")
        ts_lines.append("")
        ts_lines.append("  const pytron: PytronClient;")
        ts_lines.append("  export default pytron;")
        ts_lines.append("}")

        # Ensure directory exists
        dirname = os.path.dirname(output_path)
        if dirname and not os.path.exists(dirname):
            try:
                os.makedirs(dirname)
            except Exception as e:
                self.logger.error(f"Failed to create directory for typescript definitions: {e}")

        try:
            with open(output_path, "w") as f:
                f.write("\n".join(ts_lines))
            self.logger.info(f"Generated TypeScript definitions at {output_path}")
        except Exception as e:
            self.logger.error(f"Failed to write TypeScript definitions: {e}")
