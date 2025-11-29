import webview
import json
from .system import SystemAPI
from .serializer import pytron_serialize, PytronJSONEncoder

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
        # Reference to parent App (set by App when window is registered)
        self._app_ref = None

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
            try:
                self._window.destroy()
            except Exception:
                pass
            # Clear the underlying webview window reference
            self._window = None
        # Remove from parent App window list if present
        if getattr(self, '_app_ref', None):
            try:
                if hasattr(self._app_ref, 'remove_window'):
                    try:
                        self._app_ref.remove_window(self)
                    except Exception:
                        # Fallback to direct list removal
                        try:
                            self._app_ref.windows.remove(self)
                        except Exception:
                            pass
                else:
                    try:
                        self._app_ref.windows.remove(self)
                    except Exception:
                        pass
            except Exception:
                pass
            
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
            # We use a safe serialization
            try:
                # Serialize the payload using our encoder
                payload = json.dumps(data, cls=PytronJSONEncoder)

                # Serialize the call arguments (event name and payload string)
                call_args = json.dumps([event, payload])

                # Use spread operator to safely pass arguments into JS
                self._window.evaluate_js(f"window.__pytron_dispatch(...{call_args})")
            except Exception as e:
                print(f"[Pytron] Failed to emit event '{event}': {e}")

    def _build_api(self):
        # Create a dictionary of methods to expose
        methods = {}
        
        # Helper wrapper to ensure serialization
        def create_wrapper(func):
            # The wrapper will be attached as a method on the dynamic API class.
            # pywebview will call it as a bound method, so the first argument
            # will be the api instance. We must accept that parameter but not
            # forward it to the underlying function `func`.
            def wrapper(api_self, *args, _func=func, **kwargs):
                result = _func(*args, **kwargs)
                # Serialize complex types to simple JSON-able structures
                return pytron_serialize(result)
            return wrapper

        # 1. Add existing js_api methods
        if self.js_api:
            for attr_name in dir(self.js_api):
                if not attr_name.startswith('_'):
                    attr = getattr(self.js_api, attr_name)
                    if callable(attr):
                        methods[attr_name] = create_wrapper(attr)

        # 2. Add explicitly exposed functions (Window level)
        for name, func in self._exposed_functions.items():
            methods[name] = create_wrapper(func)

        # 2.5 Add Global App exposed functions (App level)
        if hasattr(self, '_app_ref') and self._app_ref:
             for name, func in self._app_ref._exposed_functions.items():
                if name not in methods: # Window specific overrides global
                    methods[name] = create_wrapper(func)

        # 3. Add window management methods automatically
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
            if name not in methods:
                methods[name] = create_wrapper(func)
        
        # 4. Add System API methods automatically
        system_api = SystemAPI(self)
        for attr_name in dir(system_api):
            if not attr_name.startswith('_'):
                attr = getattr(system_api, attr_name)
                if callable(attr):
                    if attr_name not in methods:
                        methods[attr_name] = create_wrapper(attr)
        
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
