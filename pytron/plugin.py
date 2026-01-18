import os
import json
import sys
import importlib
import importlib.util
import logging
import subprocess
import threading
import traceback
import shutil
from typing import Dict, Any, List


class PluginError(Exception):
    pass


class PluginStorage:
    """Provides a plugin with its own private JSON storage and data folder."""

    def __init__(self, app_instance, plugin_name):
        self._app = app_instance
        self._name = plugin_name
        self._dir = os.path.join(self._app.storage_path, "plugins", self._name)
        os.makedirs(self._dir, exist_ok=True)
        self._file = os.path.join(self._dir, "data.json")

    def set(self, key, value):
        data = self._read()
        data[key] = value
        self._write(data)

    def get(self, key, default=None):
        data = self._read()
        return data.get(key, default)

    def delete(self, key):
        data = self._read()
        if key in data:
            del data[key]
            self._write(data)

    def path(self, *suffixes):
        """Returns an absolute path to a file in the plugin's private folder."""
        path = os.path.join(self._dir, *suffixes)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def _read(self):
        if not os.path.exists(self._file):
            return {}
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def _write(self, data):
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)


class SupervisedApp:
    """
    A proxy for the App instance that protects the main app from plugin crashes.
    """

    def __init__(self, app, plugin_name):
        self._app = app
        self._plugin_name = plugin_name
        self.logger = logging.getLogger(f"Pytron.Plugin.{plugin_name}.Supervisor")
        self.storage = PluginStorage(app, plugin_name)

    def expose(self, func, name=None, secure=False):
        """Wraps the exposed function in an error handler."""
        func_name = name or func.__name__

        def safe_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self.logger.error(
                    f"Plugin '{self._plugin_name}' crashed in '{func_name}': {e}"
                )
                self.logger.debug(traceback.format_exc())
                return {"error": "Plugin Execution Failed", "message": str(e)}

        return self._app.expose(safe_wrapper, name=name, secure=secure)

    def __getattr__(self, name):
        # Delegate everything else (state, broadcast, etc.) to the real app
        return getattr(self._app, name)


class Plugin:
    """
    Represents a loaded Pytron Plugin.
    """

    def __init__(self, manifest_path: str):
        self.manifest_path = os.path.abspath(manifest_path)
        self.directory = os.path.dirname(self.manifest_path)
        self.manifest = self._load_manifest()
        self.logger = logging.getLogger(f"Pytron.Plugin.{self.name}")

    def _load_manifest(self) -> Dict[str, Any]:
        if not os.path.exists(self.manifest_path):
            raise PluginError(f"Manifest not found at {self.manifest_path}")

        try:
            with open(self.manifest_path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise PluginError(f"Invalid JSON in manifest: {e}")

        required_fields = ["name", "version", "entry_point"]
        for field in required_fields:
            if field not in data:
                raise PluginError(f"Manifest missing required field: {field}")

        return data

    @property
    def name(self) -> str:
        return self.manifest.get("name", "unknown")

    @property
    def version(self) -> str:
        return self.manifest.get("version", "0.0.0")

    @property
    def python_dependencies(self) -> List[str]:
        return self.manifest.get("python_dependencies", [])

    @property
    def npm_dependencies(self) -> Dict[str, str]:
        return self.manifest.get("npm_dependencies", {})

    @property
    def entry_point(self) -> str:
        return self.manifest.get("entry_point")

    @property
    def ui_entry(self) -> str:
        """Relative path to the JS/WebComponent entry point for this plugin."""
        return self.manifest.get("ui_entry")

    @property
    def config(self) -> Dict[str, Any]:
        """Plugin-specific configuration from manifest."""
        return self.manifest.get("config", {})

    @property
    def isolated(self) -> bool:
        """Whether this plugin should run in its own process/venv."""
        return self.manifest.get("isolated", False)

    def check_js_dependencies(self) -> bool:
        """
        Checks if JS dependencies are installed (rudimentary check for node_modules).
        """
        if not self.npm_dependencies:
            return True
        node_modules = os.path.join(self.directory, "node_modules")
        return os.path.exists(node_modules) and os.path.isdir(node_modules)

    def check_dependencies(self) -> bool:
        """
        Checks if Python dependencies are installed.
        Returns True if all dependencies are present.
        """
        missing = []
        for dep in self.python_dependencies:
            try:
                importlib.import_module(dep)  # nosemgrep
            except ImportError:
                missing.append(dep)

        if missing:
            self.logger.warning(f"Missing Python dependencies: {', '.join(missing)}")
            return False

        return True

    def install_dependencies(self, frontend_dir: str = None, provider: str = "npm"):
        """
        Attempts to install missing Python and JS dependencies.
        """
        # GUARD: Do not install dependencies in packaged/frozen apps.
        if getattr(sys, "frozen", False):
            self.logger.info(
                f"Skipping dependency install for '{self.name}' (Frozen Environment)"
            )
            return

        # 1. Python Dependencies
        py_deps = self.python_dependencies
        if py_deps:
            # Check if they are already installed to avoid redundant operations
            if self.check_dependencies():
                self.logger.debug(f"Python dependencies for {self.name} are satisfied.")
            else:
                self.logger.info(
                    f"Installing Python dependencies for {self.name}: {py_deps}"
                )
            try:
                # Resolve the project's virtual environment if it exists
                python_exe = sys.executable
                venv_scripts = os.path.join(os.getcwd(), "env", "Scripts", "python.exe")
                venv_bin = os.path.join(os.getcwd(), "env", "bin", "python")

                if os.path.exists(venv_scripts):
                    python_exe = venv_scripts
                elif os.path.exists(venv_bin):
                    python_exe = venv_bin

                subprocess.check_call([python_exe, "-m", "pip", "install"] + py_deps)
                self.logger.info(f"Python dependencies installed into {python_exe}")
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to install Python dependencies: {e}")
                raise PluginError(f"Python dependency installation failed: {e}")

        # 2. JS Dependencies
        js_deps = self.npm_dependencies
        if js_deps:
            if self.check_js_dependencies():
                self.logger.debug(f"JS dependencies for {self.name} are satisfied.")
                return

            # ISOLATION: Install inside the plugin directory
            target_dir = self.directory

            self.logger.info(
                f"Installing JS dependencies for {self.name} using '{provider}' in {target_dir} for isolation..."
            )

            # Ensure a package.json exists in the plugin directory
            pkg_json_path = os.path.join(target_dir, "package.json")
            if not os.path.exists(pkg_json_path):
                pkg_data = {
                    "name": f"pytron-plugin-{self.name}",
                    "version": self.version,
                    "dependencies": js_deps,
                }
                with open(pkg_json_path, "w") as f:
                    json.dump(pkg_data, f, indent=2)

            try:
                # Find JS provider binary
                provider_bin = shutil.which(provider)
                if not provider_bin:
                    self.logger.warning(
                        f"JS Provider '{provider}' not found in PATH. Skipping JS dependencies."
                    )
                    return

                subprocess.check_call(
                    [provider_bin, "install"],
                    cwd=target_dir,
                    shell=False,
                )  # nosec B603
                self.logger.info(
                    f"JS dependencies installed successfully using {provider}."
                )
            except Exception as e:
                self.logger.error(f"Failed to install JS dependencies: {e}")
                raise PluginError(f"JS dependency installation failed: {e}")
                # We don't necessarily want to crash the whole app if NPM is missing,
                # but we should log it.

    def load(self, app_instance):
        """
        Loads the entry point and runs initialization. (Senior Fix: Isolated Namespace)
        """
        # Ensure we use an absolute path
        plugin_dir = os.path.abspath(self.directory)
        entry_str = self.entry_point

        if ":" not in entry_str:
            raise PluginError(
                f"Invalid entry_point format '{entry_str}'. Expected 'module:function' or 'module:Class'"
            )

        module_name, object_name = entry_str.split(":")

        # Senior Fix: Define a unique name for the module (e.g., "pytron_plugins.myplugin")
        # This prevents collisions if multiple plugins have a 'main.py' or 'app.py'
        safe_name = self.name.replace("-", "_").replace(".", "_")
        unique_module_name = f"pytron_plugins.{safe_name}"

        # Resolve the file path (handles packages and submodules)
        module_path_parts = module_name.split(".")
        file_path = os.path.join(plugin_dir, *module_path_parts) + ".py"
        if not os.path.exists(file_path):
            init_path = os.path.join(plugin_dir, *module_path_parts, "__init__.py")
            if os.path.exists(init_path):
                file_path = init_path

        if not os.path.exists(file_path):
            raise PluginError(
                f"Could not find entry point file for plugin '{self.name}': {file_path}"
            )

        # Create the Supervised proxy
        supervised_app = SupervisedApp(app_instance, self.name)

        try:
            # Senior Fix: Load the module directly via spec without polluting global sys.path
            spec = importlib.util.spec_from_file_location(unique_module_name, file_path)
            if spec and spec.loader:
                self.module = importlib.util.module_from_spec(spec)
                sys.modules[unique_module_name] = self.module  # Register it safely

                # To support local imports inside the plugin folder, we briefly add to path
                # only during the execution of the module.
                path_added = False
                if plugin_dir not in sys.path:
                    sys.path.insert(0, plugin_dir)
                    path_added = True

                try:
                    spec.loader.exec_module(self.module)
                except ImportError as e:
                    raise PluginError(f"Import Error in {self.name}: {e}")
                finally:
                    if path_added and plugin_dir in sys.path:
                        sys.path.remove(plugin_dir)
            else:
                raise PluginError(f"Could not load module spec for {self.name}")

            # Get the object
            if not hasattr(self.module, object_name):
                raise PluginError(
                    f"Entry point '{object_name}' not found in module '{module_name}'"
                )

            entry_obj = getattr(self.module, object_name)

            def init_plugin():
                try:
                    self.logger.debug(
                        f"Initializing entry point: {entry_obj} (Type: {type(entry_obj).__name__})"
                    )

                    # 1. If it's a function, call it with `supervised_app`
                    if callable(entry_obj) and not isinstance(entry_obj, type):
                        self.logger.info(
                            f"Initializing plugin '{self.name}' via function '{object_name}'"
                        )
                        # Check for manual configuration from the 'plugins' pseudo-module if it exists
                        manual_config = {}
                        if "plugins" in sys.modules:
                            p_mod = sys.modules["plugins"]
                            if hasattr(p_mod, "get_registered_config"):
                                manual_config = p_mod.get_registered_config(self.name)

                        if manual_config:
                            self.logger.info(
                                f"Applying manual configuration to '{self.name}': {list(manual_config.keys())}"
                            )

                        self.instance = entry_obj(supervised_app, **manual_config)

                    # 2. If it's a class, instantiate it with `supervised_app`
                    elif isinstance(entry_obj, type):
                        self.logger.info(
                            f"Initializing plugin '{self.name}' via class '{object_name}'"
                        )
                        # Check for manual configuration from the 'plugins' pseudo-module if it exists
                        manual_config = {}
                        if "plugins" in sys.modules:
                            p_mod = sys.modules["plugins"]
                            if hasattr(p_mod, "get_registered_config"):
                                manual_config = p_mod.get_registered_config(self.name)

                        if manual_config:
                            self.logger.info(
                                f"Applying manual configuration to '{self.name}': {list(manual_config.keys())}"
                            )

                        self.instance = entry_obj(supervised_app, **manual_config)

                        # If the class has a 'setup' method, call it
                        if hasattr(self.instance, "setup"):
                            self.instance.setup()

                    else:
                        self.logger.error(
                            f"Entry point '{object_name}' is not callable. Got type: {type(entry_obj)}"
                        )

                except TypeError as e:
                    if "NoneType" in str(e) and "callable" in str(e):
                        self.logger.error(
                            f"CRITICAL: 'NoneType' object is not callable in {self.name}. Check if entry point is valid or if dependencies are missing."
                        )
                    self.logger.error(
                        f"Plugin '{self.name}' initialization crash (TypeError): {e}"
                    )
                    self.logger.debug(traceback.format_exc())
                except Exception as e:
                    self.logger.error(f"Plugin '{self.name}' initialization crash: {e}")
                    self.logger.debug(traceback.format_exc())

            if self.isolated:
                self.logger.info(
                    f"Plugin '{self.name}' is isolated. Starting in worker thread..."
                )
                thread = threading.Thread(
                    target=init_plugin, name=f"Plugin-{self.name}", daemon=True
                )
                thread.start()
            else:
                init_plugin()

        except Exception as e:
            raise PluginError(f"Failed to load plugin '{self.name}': {e}")

    def unload(self):
        """
        Unloads the plugin by calling its teardown method if available.
        """
        if hasattr(self, "instance") and self.instance:
            if hasattr(self.instance, "teardown"):
                try:
                    self.instance.teardown()
                    self.logger.info(f"Plugin '{self.name}' torn down successfully.")
                except Exception as e:
                    self.logger.error(f"Error tearing down plugin '{self.name}': {e}")
            self.instance = None

        if hasattr(self, "module") and self.module:
            # Note: We don't remove from sys.modules to avoid breaking background threads
            # that might still be using the code, but we clear the local reference.
            del self.module

    def invoke_package_hook(self, context: Dict[str, Any]):
        """
        Invoked during 'pytron package'. Allows plugins to add extra data,
        hidden imports, or run custom build scripts.
        """
        if hasattr(self, "instance") and hasattr(self.instance, "on_package"):
            try:
                self.logger.info(f"Invoking on_package hook for '{self.name}'...")
                self.instance.on_package(context)
            except Exception as e:
                self.logger.error(f"Error in on_package hook for '{self.name}': {e}")
                self.logger.debug(traceback.format_exc())


def discover_plugins(plugins_dir: str) -> List[Plugin]:
    """
    Utility to find all plugins in a directory without loading them.
    """
    plugins = []
    if not os.path.exists(plugins_dir):
        return plugins

    for item in os.listdir(plugins_dir):
        plugin_path = os.path.join(plugins_dir, item)
        manifest_path = os.path.join(plugin_path, "manifest.json")
        if os.path.isdir(plugin_path) and os.path.exists(manifest_path):
            try:
                plugins.append(Plugin(manifest_path))
            except Exception:
                pass
    return plugins
