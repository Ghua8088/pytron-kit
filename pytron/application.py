import os
import sys
import json
import webview
import inspect
import typing
from .utils import get_resource_path
from .state import ReactiveState
from .window import Window
from .system import SystemAPI
from .serializer import pydantic

class App:
    def __init__(self, config_file='settings.json'):
        self.windows = []
        self.is_running = False
        self.config = {}
        self._exposed_functions = {} # Global functions for all windows
        self._exposed_ts_defs = {} # Store generated TS definitions
        self._pydantic_models = {} # Store pydantic models to generate interfaces for
        self.shortcuts = {} # Global shortcuts
        self.state = ReactiveState(self) # Magic state object
        
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
                # print(f"[Pytron] Loaded settings from {path}")

                # Check version compatibility
                config_version = self.config.get('pytron_version')
                if config_version:
                    try:
                        from . import __version__
                        if config_version != __version__:
                            print(f"[Pytron] Warning: Project settings version ({config_version}) does not match installed Pytron version ({__version__}).")
                    except ImportError:
                        pass
            except Exception as e:
                print(f"[Pytron] Failed to load settings: {e}")

    def create_window(self, title=None, url=None, html=None, js_api=None, width=None, height=None, **kwargs):
        # Merge config with arguments. Arguments take precedence.
        
        # Helper to get value from arg, then config, then default
        def get_val(arg, key, default):
            if arg is not None:
                return arg
            return self.config.get(key, default)

        # Resolve URL
        final_url = url
        if final_url is None:
            final_url = self.config.get('url')
            # If we got a URL from config, check if it needs path resolution
            if final_url and not final_url.startswith('http') and not final_url.startswith('file://'):
                final_url = get_resource_path(final_url)
                if not os.path.exists(final_url):
                    # Fallback check relative to cwd
                    cwd_path = os.path.abspath(self.config.get('url'))
                    if os.path.exists(cwd_path):
                        final_url = cwd_path

        # Construct window with resolved values
        # Note: We pass defaults here that match the original Window.__init__ defaults if not in config
        window = Window(
            title=get_val(title, 'title', 'Pytron App'),
            url=final_url,
            html=get_val(html, 'html', None),
            js_api=js_api,
            width=get_val(width, 'width', 800),
            height=get_val(height, 'height', 600),
            resizable=get_val(kwargs.get('resizable'), 'resizable', True),
            fullscreen=get_val(kwargs.get('fullscreen'), 'fullscreen', False),
            min_size=get_val(kwargs.get('min_size'), 'min_size', (200, 100)),
            hidden=get_val(kwargs.get('hidden'), 'hidden', False),
            frameless=get_val(kwargs.get('frameless'), 'frameless', False),
            easy_drag=get_val(kwargs.get('easy_drag'), 'easy_drag', True),
            **{k: v for k, v in kwargs.items() if k not in ['resizable', 'fullscreen', 'min_size', 'hidden', 'frameless', 'easy_drag']}
        )
        # Link app reference to window so it can access global exposed functions
        window._app_ref = self
        
        self.windows.append(window)
        
        # If the app is already running, create the window immediately.
        # Otherwise, wait until run() is called to allow for configuration (e.g. expose).
        if self.is_running:
            window.create()
            
        return window

    def run(self, debug=False, menu=None, **kwargs):
        self.is_running = True
        # Create any pending windows
        for window in self.windows:
            if window._window is None:
                window.create()
        
        # Ensure we have a writable storage_path for WebView2 cache
        # Default behavior tries to write to executable dir, which fails in Program Files
        if 'storage_path' not in kwargs:
            title = self.config.get('title', 'Pytron App')
            # Sanitize title for folder name
            safe_title = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in title).strip('_')
            
            if sys.platform == 'win32':
                base_path = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
            else:
                base_path = os.path.expanduser('~/.config')
                
            storage_path = os.path.join(base_path, safe_title)
            kwargs['storage_path'] = storage_path
            
            # Ensure directory exists (pywebview might do this, but good to be safe)
            try:
                os.makedirs(storage_path, exist_ok=True)
            except Exception:
                pass # Let pywebview handle or fail if it can't write

        # pywebview.start() is a blocking call that runs the GUI loop
        # Menu is passed to start() in pywebview
        webview.start(debug=debug, menu=menu,http_server=False, **kwargs)
        self.is_running = False

    def quit(self):
        for window in self.windows:
            window.destroy()

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
            print(f"[Pytron] Warning: Could not generate types for {name}: {e}")
            return f"    {name}(...args: any[]): Promise<any>;"

    def expose(self, func=None, name=None):
        """
        Expose a function to ALL windows created by this App.
        Can be used as a decorator: @app.expose
        """
        if func is None:
            def decorator(f):
                self.expose(f, name=name)
                return f
            return decorator
            
        if name is None:
            name = func.__name__
        self._exposed_functions[name] = func
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

        # 2. Add SystemAPI methods
        system_api = SystemAPI(None)
        for attr_name in dir(system_api):
            if not attr_name.startswith('_'):
                attr = getattr(system_api, attr_name)
                if callable(attr):
                    ts_lines.append(self._get_ts_definition(attr_name, attr))

        # 3. Add Window methods
        # Map exposed name to Window class method name
        win_map = {
            'minimize': 'minimize',
            'maximize': 'maximize',
            'restore': 'restore',
            'close': 'destroy',
            'toggle_fullscreen': 'toggle_fullscreen',
            'resize': 'resize',
            'get_size': 'get_size',
        }
        
        for exposed_name, method_name in win_map.items():
            if hasattr(Window, method_name):
                method = getattr(Window, method_name)
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
            except Exception:
                pass

        try:
            with open(output_path, "w") as f:
                f.write("\n".join(ts_lines))
            print(f"[Pytron] ✅ Generated TypeScript definitions at {output_path}")
        except Exception as e:
            print(f"[Pytron] Failed to write TypeScript definitions: {e}")
