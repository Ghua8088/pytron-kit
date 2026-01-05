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
            self.logger.error(f"Unexpected error loading plugin from {manifest_path}: {e}")

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
        tray = self.setup_tray(title, icon)
        tray.add_item("Show App", self.show)
        tray.add_item("Hide App", self.hide)
        tray.add_separator()
        tray.add_item("Quit", self.quit)
        return tray
