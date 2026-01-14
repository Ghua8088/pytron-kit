import os
import sys
import shutil
import inspect
import asyncio
from ..webview import Webview


class WindowMixin:
    def create_window(self, **kwargs):
        if "url" in kwargs and not getattr(sys, "frozen", False):
            if not kwargs["url"].startswith(("http:", "https:", "file:")):
                if not os.path.isabs(kwargs["url"]):
                    kwargs["url"] = os.path.join(self.app_root, kwargs["url"])
        window_config = self.config.copy()
        window_config.update(kwargs)
        window_config["__app__"] = self
        # Only navigate if a URL was explicitly provided, or if this is the first (main) window
        target_url = kwargs.get("url")
        if target_url is None and not self.windows:
            target_url = self.config.get("url")

        window_config["navigate_on_init"] = False

        # Engine Selection
        if getattr(self, "engine", "native") == "chrome":
            from ..engines.chrome.engine import ChromeWebView

            window = ChromeWebView(config=window_config)
        else:
            window = Webview(config=window_config)

        self.windows.append(window)
        for name, data in self._exposed_functions.items():
            func = data["func"]
            secure = data["secure"]
            run_in_thread = data.get("run_in_thread", True)
            if isinstance(func, type):
                try:
                    window.expose(func)
                except Exception as e:
                    self.logger.debug(f"Failed to expose class {name}: {e}")
                    window.bind(name, func, secure=secure, run_in_thread=run_in_thread)
            else:
                window.bind(name, func, secure=secure, run_in_thread=run_in_thread)

        if target_url:
            window.navigate(target_url)
        if window_config.get("center", True):
            window.center()

        icon = window_config.get("icon")
        if icon:
            # Resolve icon path relative to app root or via resource_path
            from ..core import get_resource_path

            resolved_icon = get_resource_path(icon)

            # If not found in resource path, check script dir fallback
            if not os.path.exists(resolved_icon):
                resolved_icon = os.path.join(self.app_root, icon)

            # If it's a PNG, check if a converted .ico exists (from packaging)
            if resolved_icon.lower().endswith(".png"):
                ico_path = resolved_icon.rsplit(".", 1)[0] + ".ico"
                if os.path.exists(ico_path):
                    resolved_icon = ico_path

            if os.path.exists(resolved_icon):
                self.logger.debug(f"Runtime: Applying window icon from {resolved_icon}")
                window.set_icon(resolved_icon)
            else:
                self.logger.warning(f"Runtime: Icon file not found: {icon}")

        # --- Native Drag & Drop Hook ---
        if hasattr(self, "_on_file_drop_callback") and self._on_file_drop_callback:
            try:
                if sys.platform == "win32":
                    from ..platforms.windows_ops.system import enable_drag_drop_safe

                    # We wrap the callback to pass the window object as first arg
                    def _drop_wrapper(files):
                        self.thread_pool.submit(
                            self._on_file_drop_callback, window, files
                        )

                    # Native Drag & Drop Hook
                    # Switched to JS-based approach for simplicity and stability
                    # if self._on_file_drop_callback:
                    #     enable_drag_drop_safe(window.w, _drop_wrapper)
                elif sys.platform == "linux":
                    from ..platforms.linux_ops.system import enable_drag_drop

                    def _drop_wrapper(files):
                        self.thread_pool.submit(
                            self._on_file_drop_callback, window, files
                        )

                    # Native Drag & Drop Hook
                    # Switched to JS-based approach for simplicity and stability
                    # if self._on_file_drop_callback:
                    #     enable_drag_drop(window.w, _drop_wrapper)
                elif sys.platform == "darwin":
                    # TODO: Implement Cocoa/NSDraggingInfo handling
                    self.logger.warning(
                        "Native Drag & Drop not yet implemented for macOS."
                    )
            except Exception as e:
                self.logger.warning(f"Failed to enable Native Drag & Drop: {e}")

        return window

    def run(self, **kwargs):
        self.is_running = True
        if "storage_path" not in kwargs:
            kwargs["storage_path"] = self.storage_path

        if sys.platform == "win32" and "storage_path" in kwargs:
            os.environ["WEBVIEW2_USER_DATA_FOLDER"] = kwargs["storage_path"]

        if not self.windows:
            self.create_window()

        if len(self.windows) > 0:
            # Only attempt to close PyInstaller splash if we are in a PyInstaller-managed environment
            if sys.platform == "win32":
                try:
                    import pyi_splash

                    if pyi_splash.is_alive():
                        pyi_splash.close()
                        self.logger.info("Closed PyInstaller splash screen.")
                except (ImportError, Exception):
                    # Not in a PyInstaller frozen environment with splash
                    pass

            for combo, func in self.shortcuts.items():
                self.shortcut_manager.register(combo, func)

            if self.tray:
                self.tray.start(self)

            # Dispatch pending deep link (Cold Start)
            if hasattr(self, "state") and self.state.launch_url:
                if hasattr(self, "router"):
                    # We run this slightly deferred or directly?
                    # Since window is created but loop not started, methods should work via queue or direct handle.
                    self.router.dispatch(self.state.launch_url)

            self.windows[0].start()

        self.is_running = False

        for callback in self._on_exit_callbacks:
            try:
                if inspect.iscoroutinefunction(callback):
                    # For async callbacks, run them in the background loop
                    # and wait for them to finish before proceeding
                    future = asyncio.run_coroutine_threadsafe(callback(), self.loop)
                    try:
                        future.result(timeout=5)  # 5-second timeout for cleanup
                    except Exception as e:
                        self.logger.error(
                            f"Async on_exit callback timed out or failed: {e}"
                        )
                else:
                    callback()
            except Exception as e:
                self.logger.error(f"Error in on_exit callback: {e}")

        if self.tray:
            self.tray.stop()
        self.shortcut_manager.stop()

        if self.config.get("debug", False) and "storage_path" in kwargs:
            path = kwargs["storage_path"]
            if os.path.isdir(path):
                try:
                    shutil.rmtree(path, ignore_errors=True)
                except Exception:
                    pass

    def register_protocol(self, scheme="pytron"):
        try:
            # Use the platform implementation from the webview instance if it exists
            # otherwise fall back to detection (Webview creates the correct impl on init)
            impl = self._platform if hasattr(self, "_platform") else None

            if not impl:
                # Fallback detection for App level calls before windows are created
                import platform

                sys_plat = platform.system()
                if sys_plat == "Windows":
                    from ..platforms.windows import WindowsImplementation

                    impl = WindowsImplementation()
                elif sys_plat == "Linux":
                    from ..platforms.linux import LinuxImplementation

                    impl = LinuxImplementation()
                elif sys_plat == "Darwin":
                    from ..platforms.darwin import DarwinImplementation

                    impl = DarwinImplementation()

            if impl and impl.register_protocol(scheme):
                self.logger.info(f"Successfully registered protocol: {scheme}://")
            else:
                self.logger.warning(
                    f"Failed to register protocol: {scheme}:// (Not supported or failed on this OS)"
                )
        except Exception as e:
            self.logger.error(f"Error registering protocol: {e}")

    def broadcast(self, event_name, data):
        if self.windows:
            for window in self.windows:
                try:
                    window.emit(event_name, data)
                except Exception as e:
                    self.logger.warning(f"Failed to broadcast to window: {e}")

    def emit_to(self, window_id, event_name, data):
        """Send an event to a specific window by its ID."""
        for window in self.windows:
            if window.id == window_id:
                window.emit(event_name, data)
                return True
        return False

    def get_window(self, window_id):
        """Find a window by its ID."""
        for window in self.windows:
            if window.id == window_id:
                return window
        return None

    def emit(self, event_name, data):
        self.broadcast(event_name, data)

    def hide(self):
        if self.windows:
            for window in self.windows:
                try:
                    window.hide()
                except Exception:
                    pass

    def show(self):
        if self.windows:
            for window in self.windows:
                try:
                    window.show()
                except Exception:
                    pass

    @property
    def is_visible(self):
        """Returns True if the primary window is visible."""
        if self.windows:
            return self.windows[0].is_visible()
        return False

    def notify(self, title, message, type="info", duration=5000):
        if self.windows:
            for window in self.windows:
                try:
                    window.notify(title, message, type, duration)
                except Exception:
                    pass

    def quit(self):
        for window in self.windows:
            window.close(force=True)

    def set_menubar(self, menu_bar):
        """Attaches a MenuBar to the primary window."""
        if self.windows:
            self.windows[0].set_menu(menu_bar)
