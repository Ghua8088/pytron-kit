import os
from ..tray import SystemTray


class ExtrasMixin:
    def load_plugin(self, manifest_path):
        from ..plugin import Plugin, PluginError

        try:
            plugin = Plugin(manifest_path)
            plugin.check_dependencies()
            plugin.load(self)
            self.plugins.append(plugin)
            self.logger.info(f"Loaded plugin: {plugin.name} v{plugin.version}")
        except PluginError as e:
            self.logger.error(f"Failed to load plugin from {manifest_path}: {e}")
        except Exception as e:
            self.logger.error(
                f"Unexpected error loading plugin from {manifest_path}: {e}"
            )

    def setup_tray(self, title=None, icon=None):
        if not title:
            title = self.config.get("title", "Pytron")
        if not icon and "icon" in self.config:
            icon = self.config["icon"]
        if icon and not os.path.isabs(icon):
            icon = os.path.join(self.app_root, icon)
        self.tray = SystemTray(title, icon)
        return self.tray

    def setup_tray_standard(self, title=None, icon=None):
        # Native Engine Check
        if hasattr(self, "engine") and self.engine == "native":
            # We assume window 0 is main.
            # If windows aren't created yet, we can't create tray on native easily unless we cache it.
            # But setup_tray is usually called before run().
            # The native tray requires the event loop (which starts in run()).
            # So we should queue this creation?
            # Or we leverage the fact that user calls `app.setup_tray` then `app.run`.
            # `app.run` calls `self.windows[0].start()`.
            # `webview.py` start connects bindings.

            # The best way is to let `webview.create_tray` happen AFTER run starts?
            # No, `create_tray` sends an event. If loop not started, event is lost or queued?
            # `EventLoopProxy` can send events before run? Yes, usually.

            if not title:
                title = self.config.get("title", "Pytron")
            if not icon:
                icon = self.config.get("icon")
            if icon and not os.path.isabs(icon):
                icon = os.path.join(self.app_root, icon)

            # We defer this to the first window's initialization if possible, or sets a config?
            # Actually, if we just call it on the window instance, and the window exists...
            # app.windows is empty at setup time usually?
            # In `app.py`: `app = App(...)`, `app.create_window(...)`, `app.setup_tray...`
            # If create_window already added to self.windows, then yes.

            if self.windows:
                try:
                    self.windows[0].create_tray(icon, title)
                    self.logger.info("Used Native Tray integration.")
                    # Enable Close-to-Tray for standard tray setup
                    self.windows[0].config["close_to_tray"] = True
                    return None
                except Exception as e:
                    self.logger.warning(f"Native Tray failed, falling back: {e}")

        tray = self.setup_tray(title, icon)
        tray.add_item("Show App", self.show)
        tray.add_item("Hide App", self.hide)
        tray.add_separator()
        tray.add_item("Quit", self.quit)
        return tray
