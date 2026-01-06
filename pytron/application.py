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
from .apputils.codegen import CodegenMixin
from .apputils.native import NativeMixin
from .apputils.config import ConfigMixin
from .apputils.windows import WindowMixin
from .apputils.extras import ExtrasMixin


class App(ConfigMixin, WindowMixin, ExtrasMixin, CodegenMixin, NativeMixin):
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
        
        # ConfigMixin setup
        self._setup_logging()
        self.state = ReactiveState(self)
        self._check_deep_link()
        self._load_config(config_file)
        _, safe_title = self._setup_identity()
        self._setup_storage(safe_title)
        self._resolve_resources()

    def on_exit(self, func):
        """
        Register a function to run when the application is exiting.
        Can be used as a decorator: @app.on_exit
        """
        self._on_exit_callbacks.append(func)
        return func

    # Expose function to all windows
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
                        }
                        self._exposed_ts_defs[attr_name] = self._get_ts_definition(
                            attr_name, attr
                        )
                    except Exception:
                        pass
            return func

        if name is None:
            name = func.__name__

        self._exposed_functions[name] = {"func": func, "secure": secure}
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

