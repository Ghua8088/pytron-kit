import os
import sys
from typing import Any
from .state import ReactiveState
from .router import Router

from .plugin import Plugin

from .shortcuts import ShortcutManager
from .apputils.codegen import CodegenMixin
from .apputils.native import NativeMixin
from .apputils.config import ConfigMixin
from .apputils.windows import WindowMixin
from .apputils.extras import ExtrasMixin
from .apputils.shell import Shell
from .inspector import Inspector


class App(ConfigMixin, WindowMixin, ExtrasMixin, CodegenMixin, NativeMixin, Shell):
    def __init__(self, config_file="settings.json"):
        # PERFORMANCE: Shared thread pool for all internal window operations
        self.thread_pool = __import__("concurrent.futures").futures.ThreadPoolExecutor(
            max_workers=10
        )

        # Init State
        self.windows = []
        self.is_running = False
        self._exposed_functions = {}
        self._exposed_ts_defs = {}
        self._pydantic_models = {}
        self.shortcuts = {}
        self.plugins = []
        self._on_exit_callbacks = []
        self.tray = None
        self.shortcut_manager = ShortcutManager()
        self._on_file_drop_callback = None
        self.plugin_statuses = []  # Track load status for inspector

        # Router Init
        self.router = Router()

        # ConfigMixin setup
        self._setup_logging()
        self.router.logger = self.logger  # Share logger
        self.state = ReactiveState(self)
        self._check_deep_link()
        self._load_config(config_file)
        _, safe_title = self._setup_identity()
        self._setup_storage(safe_title)
        self._resolve_resources()
        self._register_core_apis()

        # Engine Selection (PRO FEATURES)
        self.engine = os.environ.get(
            "PYTRON_ENGINE", self.config.get("engine", "native")
        )

        # Override via CLI flags if present
        if "--web" in sys.argv:
            self.engine = "chrome"

        # Check if --engine X was passed directly to the script
        for i, arg in enumerate(sys.argv):
            if arg == "--engine" and i + 1 < len(sys.argv):
                self.engine = sys.argv[i + 1]

        if self.engine == "chrome":
            self.logger.info("Using Chrome Shell Engine (Mojo IPC)")

        # Initialize Inspector
        self.inspector = Inspector(self)

        if self.config.get("single_instance", False):
            # ConfigMixin already handles this via _setup_identity -> _setup_single_instance
            pass

        self._setup_key_value_store()

        # Register automatic cleanup for thread pool
        # Register automatic cleanup for thread pool
        @self.on_exit
        def _cleanup_pool():
            if self.thread_pool:
                self.logger.debug("Shutting down thread pool...")
                try:
                    self.thread_pool.shutdown(wait=False, cancel_futures=True)
                except Exception as e:
                    self.logger.debug(f"Error shutting down thread pool: {e}")
                self.thread_pool = None

        # AUTO-CODEGEN: Generate TypeScript definitions in debug mode
        if self.config.get("debug", False):
            # We use a small delay via the event loop or just run it before start
            # To ensure all plugins/modules have had a chance to .expose()
            # But usually they do it during __init__ or before app.run()
            # We'll attach it to a pre-run hook or just before the loop starts in WindowMixin.run
            pass

        # Actually, let's trigger it once here for early feedback
        if self.config.get("debug", False):
            try:
                self.generate_types()
            except Exception as e:
                self.logger.debug(f"Initial codegen skipped: {e}")

        # Load Plugins
        # We must use the script/exe directory (sys.path[0]), NOT cwd, because cwd changes to AppData
        if getattr(sys, "frozen", False):
            # Senior Fix: Use sys._MEIPASS for internal assets/plugins in frozen builds.
            # Fallback to sys.executable dir if _MEIPASS is somehow missing.
            base_dir = getattr(
                sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable))
            )
        else:
            # Prefer the directory of the actual main script if possible
            main_script = (
                sys.modules.get("__main__", {}).__file__
                if "__main__" in sys.modules
                else None
            )
            if main_script:
                base_dir = os.path.dirname(os.path.abspath(main_script))
            elif sys.path[0]:
                base_dir = os.path.abspath(sys.path[0])
            else:
                base_dir = os.getcwd()

            self.logger.debug(f"Plugin Base Dir resolved to: {base_dir}")

        self.app_root = base_dir

        # Plugin Discovery: Check both bundled (internal) and drop-in (external) paths
        candidate_dirs = []
        if getattr(sys, "frozen", False):
            # 1. Bundled plugins inside _internal
            if hasattr(sys, "_MEIPASS"):
                candidate_dirs.append(os.path.join(sys._MEIPASS, "plugins"))
            # 2. Drop-in plugins next to the EXE
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            candidate_dirs.append(os.path.join(exe_dir, "plugins"))
        else:
            # Local dev plugins next to the script
            candidate_dirs.append(os.path.join(base_dir, "plugins"))

        custom_plugins_dir = self.config.get("plugins_dir")
        if custom_plugins_dir:
            if not os.path.isabs(custom_plugins_dir):
                custom_plugins_dir = os.path.join(base_dir, custom_plugins_dir)
            candidate_dirs.append(custom_plugins_dir)

        # Remove duplicates and resolve
        seen = set()
        for p_dir in candidate_dirs:
            p_dir = os.path.abspath(p_dir)
            if p_dir not in seen and os.path.exists(p_dir):
                self.logger.info(f"Scanning for plugins in: {p_dir}")
                self.load_plugins(p_dir)
                seen.add(p_dir)

    def on_exit(self, func):
        """
        Register a function to run when the application is exiting.
        Can be used as a decorator: @app.on_exit
        """
        self._on_exit_callbacks.append(func)
        return func

    # Expose function to all windows
    def expose(self, func=None, name=None, secure=False, run_in_thread=True):
        """
        Expose a function to ALL windows created by this App.
        Can be used as a decorator: @app.expose or @app.expose(secure=True)
        """
        # Case 1: Used as @app.expose(secure=True) - func is None
        if func is None:

            def decorator(f):
                self.expose(f, name=name, secure=secure, run_in_thread=run_in_thread)
                return f

            return decorator

        # Case 2: Used as @app.expose or app.expose(func)
        # If the user passed a class or an object (bridge), expose its public callables
        if isinstance(func, type) or (not callable(func) and hasattr(func, "__dict__")):
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
                if attr_name.startswith("_"):
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
                        self._exposed_functions[attr_name] = {
                            "func": attr,
                            "secure": secure,
                            "run_in_thread": run_in_thread,
                        }
                        self._exposed_ts_defs[attr_name] = self._get_ts_definition(
                            attr_name, attr
                        )
                    except Exception:
                        pass
            return func

        if name is None:
            name = func.__name__

        self._exposed_functions[name] = {
            "func": func,
            "secure": secure,
            "run_in_thread": run_in_thread,
        }
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

    def on_deep_link(self, pattern: str):
        """
        Decorator to register a handler for deep links.
        Pattern examples: "project/{id}", "settings", "oauth/callback"

        @app.on_deep_link("project/{id}")
        def open_project(id, link):
            print(f"Opening project {id} from {link.raw_url}")
        """
        return self.router.route(pattern)

    def on_file_drop(self, func):
        """
        Decorator to register a handler for file drop events.

        @app.on_file_drop
        def handle_drop(window, files):
            print(f"Dropped files on window {window.id}: {files}")
        """
        self._on_file_drop_callback = func
        return func

    def _register_core_apis(self):
        """Automatically exposes built-in system APIs to the frontend."""
        # Shell APIs
        self.expose(self.open_external, name="shell_open_external")
        self.expose(self.show_item_in_folder, name="shell_show_item_in_folder")

        # Clipboard APIs
        self.expose(self.copy_to_clipboard, name="clipboard_write_text")
        self.expose(self.get_clipboard_text, name="clipboard_read_text")

        # System Info
        self.expose(self.get_system_info, name="system_get_info")

        # Store APIs
        self.expose(self.store_set, name="store_set")
        self.expose(self.store_get, name="store_get")
        self.expose(self.store_delete, name="store_delete")

        # App Lifecycle
        self.expose(self.quit, name="app_quit", run_in_thread=False)
        self.expose(self.show, name="app_show", run_in_thread=False)
        self.expose(self.hide, name="app_hide", run_in_thread=False)
        self.expose(lambda: self.is_visible, name="app_is_visible", run_in_thread=False)

        # Event Bus
        self.expose(self.publish, name="app_publish")

        # Updater APIs
        self.expose(self.check_updates, name="app_check_updates")
        self.expose(self.install_update, name="app_install_update")

        # Inspector APIs
        self.expose(
            self.toggle_inspector, name="app_toggle_inspector", run_in_thread=False
        )

    def check_updates(self, url: str):
        """
        Checks for application updates.
        Returns update info if available, else None.
        """
        from .updater import Updater

        upd = Updater(current_version=self.config.get("version"))
        return upd.check(url)

    def install_update(self, update_info: dict):
        """
        Downloads and installs an update.
        Emits 'pytron:update-progress' events.
        """
        from .updater import Updater

        upd = Updater(current_version=self.config.get("version"))

        def _on_progress(pct):
            self.broadcast("pytron:update-progress", {"percent": pct})

        # Run install in thread pool to avoid blocking IPC
        self.thread_pool.submit(upd.download_and_install, update_info, _on_progress)
        return True

    def publish(self, event_name: str, data: Any = None):
        """
        Broadcasts an event to all open windows.
        This enables simple cross-window communication.
        """
        self.broadcast(event_name, data)
        return True

    def dispatch(self, event_name: str, payload: Any = None):
        """
        Dispatches an event to the frontend Event Bus in ALL active windows.
        Usage: app.dispatch('navigate', {'route': '/settings'})
        """
        # We iterate over windows and call their individual dispatch method
        # This ensures they use the strictly defined event bus protocol we implemented in Webview
        for window in self.windows:
            if hasattr(window, "dispatch"):
                window.dispatch(event_name, payload)
        return True

    def toggle_inspector(self):
        """
        Toggles the Pytron Inspector window.
        """
        if self.inspector:
            self.inspector.toggle()
        return True

    def load_plugins(self, plugins_dir: str):
        """
        Discovers and loads plugins from the specified directory.
        Each subdirectory with a manifest.json is considered a plugin.
        """
        if not os.path.exists(plugins_dir):
            self.logger.warning(f"Plugins directory not found: {plugins_dir}")
            return

        # Initialize plugin list in state if not present
        if not hasattr(self.state, "plugins"):
            self.state.plugins = []

        # Resolve frontend dir for NPM dependency installation
        frontend_dir = os.path.join(self.app_root, "frontend")
        if not os.path.exists(frontend_dir):
            # Try to find it by looking for package.json
            potential = os.path.join(
                self.app_root, self.config.get("url", "").split("/")[0]
            )
            if os.path.exists(os.path.join(potential, "package.json")):
                frontend_dir = potential

        # Filter and order by 'plugins' config list if present
        allowed_plugins = self.config.get("plugins", [])
        scan_items = []

        if (
            allowed_plugins
            and isinstance(allowed_plugins, list)
            and len(allowed_plugins) > 0
        ):
            scan_items = allowed_plugins
        else:
            # Fallback to scanning directory
            if os.path.exists(plugins_dir):
                scan_items = sorted(os.listdir(plugins_dir))

        for item in scan_items:
            plugin_path = os.path.join(plugins_dir, item)
            manifest_path = os.path.join(plugin_path, "manifest.json")

            if os.path.isdir(plugin_path) and os.path.exists(manifest_path):
                try:
                    self.logger.info(f"Loading plugin from {plugin_path}...")
                    plugin = Plugin(manifest_path)

                    # Dependency Check & Install
                    # For NPM, we usually want to install if there are any listed to be safe,
                    # as check_dependencies currently only verifies Python modules.
                    if not plugin.check_dependencies() or (
                        plugin.npm_dependencies and not plugin.check_js_dependencies()
                    ):
                        self.logger.info(
                            f"Checking/Installing dependencies for {plugin.name}..."
                        )
                        # Pass the configured provider to ensure consistency
                        provider = self.config.get("frontend_provider", "npm")
                        plugin.install_dependencies(
                            frontend_dir=frontend_dir, provider=provider
                        )

                    plugin.load(self)
                    self.plugins.append(plugin)

                    # Update state with plugin metadata for the frontend
                    plugins_list = list(self.state.plugins or [])
                    plugin_meta = {
                        "name": plugin.name,
                        "version": plugin.version,
                        "ui_entry": (
                            f"pytron://app/plugins/{item}/{plugin.ui_entry}"
                            if plugin.ui_entry
                            else None
                        ),
                        "slot": plugin.manifest.get(
                            "slot"
                        ),  # NEW: Support slot mapping
                    }
                    plugins_list.append(plugin_meta)
                    self.state.plugins = plugins_list

                    self.plugin_statuses.append(
                        {
                            "name": plugin.name,
                            "status": "loaded",
                            "version": plugin.version,
                            "path": plugin_path,
                        }
                    )
                    self.logger.info(
                        f"Plugin '{plugin.name}' (v{plugin.version}) loaded successfully."
                    )

                    self.publish("pytron:plugin-loaded", plugin_meta)

                except Exception as e:
                    self.plugin_statuses.append(
                        {
                            "name": item,
                            "status": "error",
                            "error": str(e),
                            "path": plugin_path,
                        }
                    )
                    self.logger.error(f"Failed to load plugin at {plugin_path}: {e}")

    def unload_plugins(self):
        """
        Unloads all loaded plugins.
        """
        for plugin in self.plugins:
            try:
                plugin.unload()
            except Exception as e:
                self.logger.error(f"Error unloading plugin {plugin.name}: {e}")
        self.plugins.clear()

    def audit_dependencies(self):
        """
        Packaging Heuristic:
        Traverses all exposed functions to find hidden dependencies (imports inside functions).
        Triggers sys.audit('import') events for found modules so packaging tools can capture them.
        """
        import inspect
        import dis
        import sys

        visited = set()

        def _report(name, file=None):
            if name:
                sys.audit("import", name, file, None, None, None)

        def _inspect(func, depth=0):
            if depth > 5:
                return
            try:
                if func in visited:
                    return
                visited.add(func)
            except:
                return

            try:
                # 1. Handle Classes/Instances (if stored directly)
                if inspect.isclass(func) or (
                    not callable(func) and hasattr(func, "__dict__")
                ):
                    if hasattr(func, "__module__") and func.__module__:
                        _report(func.__module__)
                    for attr_name in dir(func):
                        if attr_name.startswith("_"):
                            continue
                        try:
                            val = getattr(func, attr_name)
                            if inspect.isfunction(val) or inspect.ismethod(val):
                                _inspect(val, depth + 1)
                        except:
                            pass
                    return

                # Report the module of the function itself
                if hasattr(func, "__module__") and func.__module__:
                    _report(func.__module__)

                # Check method self if applicable
                if inspect.ismethod(func) and hasattr(func, "__self__"):
                    if hasattr(func.__self__, "__module__"):
                        _report(func.__self__.__module__)

                # 2. Inspect closures and globals
                closures = inspect.getclosurevars(func)

                for name, value in closures.globals.items():
                    if inspect.ismodule(value):
                        _report(value.__name__, getattr(value, "__file__", None))
                    elif hasattr(value, "__module__") and value.__module__:
                        _report(value.__module__)
                        if inspect.isfunction(value) or inspect.isclass(value):
                            _inspect(value, depth + 1)

                for name, value in closures.nonlocals.items():
                    if hasattr(value, "__module__") and value.__module__:
                        _report(value.__module__)
                        if inspect.isfunction(value):
                            _inspect(value, depth + 1)

                # 3. Bytecode Analysis
                if hasattr(func, "__code__"):
                    for instr in dis.get_instructions(func):
                        if instr.opname == "IMPORT_NAME":
                            _report(instr.argval)

            except Exception:
                pass

        # Trigger inspection for all registered entry points
        self.logger.info("Running Packaging Heuristic on exposed functions...")
        for info in self._exposed_functions.values():
            func = info.get("func")
            if func:
                _inspect(func)
