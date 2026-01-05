import os
import sys
import shutil
import inspect
from ..webview import Webview

class WindowMixin:
    def create_window(self, **kwargs):
        if "url" in kwargs and not getattr(sys, "frozen", False):
            if not kwargs["url"].startswith(("http:", "https:", "file:")):
                if not os.path.isabs(kwargs["url"]):
                    kwargs["url"] = os.path.join(self.app_root, kwargs["url"])
        window_config = self.config.copy()
        window_config.update(kwargs)
        original_url = window_config.get("url")
        window_config["navigate_on_init"] = False
        window = Webview(config=window_config)
        self.windows.append(window)
        for name, data in self._exposed_functions.items():
            func = data["func"]
            secure = data["secure"]
            if isinstance(func, type):
                try:
                    window.expose(func)
                except Exception as e:
                    self.logger.debug(f"Failed to expose class {name}: {e}")
                    window.bind(name, func, secure=secure)
            else:
                window.bind(name, func, secure=secure)
        if original_url:
            window.navigate(window_config.get("url", original_url))
        if window_config.get("center", True):
            window.center()
        icon = window_config.get("icon")
        if icon:
            window.set_icon(icon)
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
            try:
                import pyi_splash
                if pyi_splash.is_alive():
                    pyi_splash.close()
                    self.logger.info("Closed splash screen.")
            except ImportError:
                pass
            except Exception as e:
                self.logger.debug(f"Error closing splash screen: {e}")

            for combo, func in self.shortcuts.items():
                self.shortcut_manager.register(combo, func)

            if self.tray:
                self.tray.start(self)

            self.windows[0].start()

        self.is_running = False

        for callback in self._on_exit_callbacks:
            try:
                if inspect.iscoroutinefunction(callback):
                    pass
                else:
                    callback()
            except Exception as e:
                self.logger.error(f"Error in on_exit callback: {e}")

        if self.tray:
            self.tray.stop()
        self.shortcut_manager.stop()

        if self.config.get("debug", False) and "storage_path" in kwargs:
            path = kwargs["storage_path"]
            if os.path.isdir(path) and f"_Dev_{os.getpid()}" in path:
                try:
                    shutil.rmtree(path, ignore_errors=True)
                except Exception:
                    pass

    def register_protocol(self, scheme="pytron"):
        try:
            import platform
            if platform.system() == "Windows":
                from ..platforms.windows import WindowsImplementation
                impl = WindowsImplementation()
                if impl.register_protocol(scheme):
                    self.logger.info(f"Successfully registered protocol: {scheme}://")
                else:
                    self.logger.warning(f"Failed to register protocol: {scheme}://")
            else:
                self.logger.warning(f"Protocol registration not implemented for {platform.system()}")
        except Exception as e:
            self.logger.error(f"Error registering protocol: {e}")

    def broadcast(self, event_name, data):
        if self.windows:
            for window in self.windows:
                try:
                    window.emit(event_name, data)
                except Exception as e:
                    self.logger.warning(f"Failed to broadcast to window: {e}")

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
