import os
import json
import sys
import importlib
import logging
import subprocess
from typing import List, Dict, Any, Union


class PluginError(Exception):
    pass


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

    def check_dependencies(self):
        """
        Checks if Python dependencies are installed.
        """
        missing = []
        for dep in self.python_dependencies:
            try:
                importlib.import_module(dep)
            except ImportError:
                missing.append(dep)

        if missing:
            self.logger.warning(f"Missing Python dependencies: {', '.join(missing)}")
            # Optional: auto-install? For now, just warn.

    def load(self, app_instance):
        """
        Loads the entry point and runs initialization.
        """
        # Add plugin directory to path so imports work
        if self.directory not in sys.path:
            sys.path.insert(0, self.directory)

        entry_str = self.entry_point
        if ":" not in entry_str:
            raise PluginError(
                f"Invalid entry_point format '{entry_str}'. Expected 'module:function' or 'module:Class'"
            )

        module_name, object_name = entry_str.split(":")

        try:
            # Import the module
            module = importlib.import_module(module_name)

            # Get the object
            if not hasattr(module, object_name):
                raise PluginError(
                    f"Entry point '{object_name}' not found in module '{module_name}'"
                )

            entry_obj = getattr(module, object_name)

            # 1. If it's a function, call it with `app`
            if callable(entry_obj) and not isinstance(entry_obj, type):
                self.logger.info(
                    f"Initializing plugin '{self.name}' via function '{object_name}'"
                )
                entry_obj(app_instance)

            # 2. If it's a class, instantiate it with `app`
            elif isinstance(entry_obj, type):
                self.logger.info(
                    f"Initializing plugin '{self.name}' via class '{object_name}'"
                )
                instance = entry_obj(app_instance)
                # If the class has a 'setup' method, call it
                if hasattr(instance, "setup"):
                    instance.setup()

                # Automatically expose public methods of the class instance if desired
                # But typically the plugin logic inside __init__ or setup should handle app.expose() manually or via decorator

        except Exception as e:
            raise PluginError(f"Failed to load plugin '{self.name}': {e}")
