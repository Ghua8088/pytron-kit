import webview
import sys
import os
import threading

def get_resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller
    """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), relative_path)


class SystemAPI:
    """
    Built-in system capabilities exposed to every Pytron window.
    """
    def __init__(self, window_instance):
        self.window = window_instance

    def system_notification(self, title, message):
        # Pywebview doesn't have a direct notification API, so we might need a library
        # or just print for now / use OS specific command.
        # For now, let's just print to console to show it works, 
        # or use a simple ctypes message box on Windows if possible.
        print(f"[System Notification] {title}: {message}")
        # TODO: Implement native notifications
        
    def system_open_file(self, file_types=()):
        """
        Open a file dialog.
        """
        if self.window._window:
            return self.window._window.create_file_dialog(webview.OPEN_DIALOG, file_types=file_types)
            
    def system_save_file(self, save_filename='', file_types=()):
        """
        Open a save file dialog.
        """
        if self.window._window:
            return self.window._window.create_file_dialog(webview.SAVE_DIALOG, save_filename=save_filename, file_types=file_types)

    def system_message_box(self, title, message):
        """
        Open a message box (confirmation dialog).
        """
        if self.window._window:
            return self.window._window.create_confirmation_dialog(title, message)


class ReactiveState:
    """
    A magic object that syncs its attributes to the frontend automatically.
    """
    def __init__(self, app):
        # Use super().__setattr__ to avoid triggering our own hook for internal vars
        super().__setattr__('_app', app)
        super().__setattr__('_data', {})
        # Re-entrant lock to allow nested access from same thread
        super().__setattr__('_lock', threading.RLock())

    def __setattr__(self, key, value):
        # Store the value in a thread-safe manner
        lock = getattr(self, '_lock', None)
        if lock is not None:
            with lock:
                self._data[key] = value
        else:
            self._data[key] = value

        # Broadcast to all windows outside of the lock to avoid potential deadlocks
        app_ref = getattr(self, '_app', None)
        if app_ref:
            # Iterate over a snapshot of windows to avoid issues if list is mutated
            for window in list(app_ref.windows):
                try:
                    window.emit('pytron:state-update', {'key': key, 'value': value})
                except Exception as e:
                    print(f"[Pytron] Error emitting state update for key '{key}': {e}")

    def __getattr__(self, key):
        lock = getattr(self, '_lock', None)
        if lock is not None:
            with lock:
                return self._data.get(key)
        return self._data.get(key)
        
    def to_dict(self):
        lock = getattr(self, '_lock', None)
        if lock is not None:
            with lock:
                return dict(self._data)
        return dict(self._data)

    def update(self, mapping: dict):
        """
        Atomically update multiple keys and emit updates for each key.
        Use this when you want to set multiple state values from another thread
        without causing intermediate inconsistent states.
        """
        if not isinstance(mapping, dict):
            raise TypeError('mapping must be a dict')

        lock = getattr(self, '_lock', None)
        if lock is not None:
            with lock:
                self._data.update(mapping)
        else:
            self._data.update(mapping)

        app_ref = getattr(self, '_app', None)
        if app_ref:
            for key, value in mapping.items():
                for window in list(app_ref.windows):
                    try:
                        window.emit('pytron:state-update', {'key': key, 'value': value})
                    except Exception as e:
                        print(f"[Pytron] Error emitting state update for key '{key}': {e}")


class Window:
    def __init__(self, title, url=None, html=None, js_api=None, width=800, height=600, 
                 resizable=True, fullscreen=False, min_size=(200, 100), hidden=False, 
                 frameless=False, easy_drag=True, on_loaded=None, on_closing=None, 
                 on_closed=None, on_shown=None, on_minimized=None, on_maximized=None, 
                 on_restored=None, on_resized=None, on_moved=None, **kwargs):
        self.title = title
        self.url = url
        self.html = html
        self.js_api = js_api
        self.width = width
        self.height = height
        self.resizable = resizable
        self.fullscreen = fullscreen
        self.min_size = min_size
        self.hidden = hidden
        self.frameless = frameless
        self.easy_drag = easy_drag
        
        # Events
        self.on_loaded = on_loaded
        self.on_closing = on_closing
        self.on_closed = on_closed
        self.on_shown = on_shown
        self.on_minimized = on_minimized
        self.on_maximized = on_maximized
        self.on_restored = on_restored
        self.on_resized = on_resized
        self.on_moved = on_moved
        
        self._window = None
        self._exposed_functions = {}
        self.shortcuts = {}

    def shortcut(self, key_combo, func=None):
        """
        Register a keyboard shortcut for this window.
        Example: @window.shortcut('Ctrl+S')
        """
        if func is None:
            def decorator(f):
                self.shortcut(key_combo, f)
                return f
            return decorator
        self.shortcuts[key_combo] = func
        return func

    def expose(self, func=None, name=None):
        """
        Expose a Python function to JavaScript. Can be used as a decorator.
        @window.expose
        def my_func(): ...
        """
        if self._window:
             raise RuntimeError("Cannot expose functions after window creation. Call expose() before app.run() or window.create().")
        
        # Handle decorator usage: @window.expose or @window.expose(name="foo")
        if func is None:
            def decorator(f):
                self.expose(f, name=name)
                return f
            return decorator
             
        if name is None:
            name = func.__name__
        self._exposed_functions[name] = func
        return func

    def minimize(self):
        if self._window:
            self._window.minimize()

    def maximize(self):
        if self._window:
            self._window.maximize()

    def restore(self):
        if self._window:
            self._window.restore()

    def toggle_fullscreen(self):
        if self._window:
            self._window.toggle_fullscreen()
            
    def resize(self, width, height):
        if self._window:
            self._window.resize(width, height)
            
    def get_size(self):
        if self._window:
            return {"width": self._window.width, "height": self._window.height}
        return {"width": self.width, "height": self.height}
            
    def move(self, x, y):
        if self._window:
            self._window.move(x, y)
            
    def destroy(self):
        if self._window:
            self._window.destroy()
            
    @property
    def on_top(self):
        if self._window:
            return self._window.on_top
    
    @on_top.setter
    def on_top(self, on_top):
        if self._window:
            self._window.on_top = on_top

    def load_url(self, url):
        if self._window:
            self._window.load_url(url)
            
    def load_html(self, content, base_uri=None):
        if self._window:
            self._window.load_html(content, base_uri)

    def emit(self, event, data=None):
        """
        Emit an event to the JavaScript frontend.
        """
        if self._window:
            import json
            # We use a safe serialization
            try:
                payload = json.dumps(data)
                self._window.evaluate_js(f"window.__pytron_dispatch('{event}', {payload})")
            except Exception as e:
                print(f"[Pytron] Failed to emit event '{event}': {e}")

    def _build_api(self):
        # Create a dictionary of methods to expose
        methods = {}
        
        # 1. Add existing js_api methods
        if self.js_api:
            for attr_name in dir(self.js_api):
                if not attr_name.startswith('_'):
                    attr = getattr(self.js_api, attr_name)
                    if callable(attr):
                        methods[attr_name] = attr

        # 2. Add explicitly exposed functions (Window level)
        for name, func in self._exposed_functions.items():
            def wrapper(self, *args, _func=func, **kwargs):
                return _func(*args, **kwargs)
            methods[name] = wrapper

        # 2.5 Add Global App exposed functions (App level)
        # We assume self.app_ref might exist if we link them, or we can pass it in.
        # For now, let's assume the user might have passed it or we can't access it easily 
        # without changing __init__. 
        # Actually, let's check if we can access the parent app. 
        # Since Window is usually created by App, we can inject the app reference in App.create_window.
        if hasattr(self, '_app_ref') and self._app_ref:
             for name, func in self._app_ref._exposed_functions.items():
                if name not in methods: # Window specific overrides global
                    def wrapper(self, *args, _func=func, **kwargs):
                        return _func(*args, **kwargs)
                    methods[name] = wrapper

        # 3. Add window management methods automatically
        # We expose them with a prefix or just as is? 
        # Let's expose them as 'window_minimize', 'window_close', etc. to avoid conflicts
        # or just expose them directly if we want a clean API.
        # Let's go with direct names but be careful.
        
        window_methods = {
            'minimize': self.minimize,
            'maximize': self.maximize,
            'restore': self.restore,
            'close': self.destroy,
            'toggle_fullscreen': self.toggle_fullscreen,
            'resize': self.resize,
            'get_size': self.get_size,
        }


        for name, func in window_methods.items():
            # Only add if not already defined by user
            if name not in methods:
                def wrapper(self, *args, _func=func, **kwargs):
                    return _func(*args, **kwargs)
                methods[name] = wrapper
        
        # 4. Add System API methods automatically
        # These provide "batteries included" features like dialogs, notifications, etc.
        system_api = SystemAPI(self)
        for attr_name in dir(system_api):
            if not attr_name.startswith('_'):
                attr = getattr(system_api, attr_name)
                if callable(attr):
                    # We prefix them with 'system_' if they aren't already, 
                    # but SystemAPI methods should probably be named 'system_...' to avoid collisions
                    # Let's assume SystemAPI methods are named correctly.
                    if attr_name not in methods:
                        methods[attr_name] = attr
        
        # 5. Add Shortcut Handling
        def trigger_shortcut(api_self, combo):
            # Check window shortcuts first
            if combo in self.shortcuts:
                self.shortcuts[combo]()
                return True
            # Check app shortcuts
            if hasattr(self, '_app_ref') and self._app_ref and combo in self._app_ref.shortcuts:
                self._app_ref.shortcuts[combo]()
                return True
            return False
        methods['trigger_shortcut'] = trigger_shortcut

        def get_registered_shortcuts(api_self):
            keys = list(self.shortcuts.keys())
            if hasattr(self, '_app_ref') and self._app_ref:
                keys.extend(self._app_ref.shortcuts.keys())
            return list(set(keys))
        methods['get_registered_shortcuts'] = get_registered_shortcuts
            
        # Create the dynamic class
        DynamicApi = type('DynamicApi', (object,), methods)
        
        # Return an instance of this class
        api_instance = DynamicApi()
        print(f"[Pytron] Built API with methods: {list(methods.keys())}")
        return api_instance

    def create(self):
        # Build the final API object
        final_api = self._build_api()
        
        self._window = webview.create_window(
            self.title,
            url=self.url,
            html=self.html,
            js_api=final_api,
            width=self.width,
            height=self.height,
            resizable=self.resizable,
            fullscreen=self.fullscreen,
            min_size=self.min_size,
            hidden=self.hidden,
            frameless=self.frameless,
            easy_drag=self.easy_drag
        )
        
        # Bind events
        if self.on_loaded: self._window.events.loaded += self.on_loaded
        if self.on_closing: self._window.events.closing += self.on_closing
        if self.on_closed: self._window.events.closed += self.on_closed
        if self.on_shown: self._window.events.shown += self.on_shown
        if self.on_minimized: self._window.events.minimized += self.on_minimized
        if self.on_maximized: self._window.events.maximized += self.on_maximized
        if self.on_restored: self._window.events.restored += self.on_restored
        if self.on_resized: self._window.events.resized += self.on_resized
        if self.on_moved: self._window.events.moved += self.on_moved
        
        # Inject initial state if available
        if hasattr(self, '_app_ref') and self._app_ref and hasattr(self._app_ref, 'state'):
            # We need to wait for the window to be ready to receive events, 
            # but pywebview doesn't have a perfect "ready for JS" event that guarantees listeners are set.
            # We can expose a method 'pytron_init' that the client calls?
            # Or just try to emit after a short delay?
            # For now, let's rely on the client asking for state or just pushing updates.
            pass

class App:
    def __init__(self, config_file='settings.json'):
        self.windows = []
        self.is_running = False
        self.config = {}
        self._exposed_functions = {} # Global functions for all windows
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
        webview.start(debug=debug, menu=menu, **kwargs)
        self.is_running = False

    def quit(self):
        for window in self.windows:
            window.destroy()

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
