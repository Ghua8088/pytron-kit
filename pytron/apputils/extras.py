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

    def _resolve_icon_path(self, icon_path):
        """
        Robustly resolves the icon path, checking absolute paths,
        config-relative paths, and the bundled 'resources/app_icon' fallback.
        """
        if not icon_path:
            return None
            
        resolved = icon_path
        if not os.path.isabs(icon_path):
            resolved = os.path.join(self.app_root, icon_path)
        
        # Check if strictly exists
        if os.path.exists(resolved):
            return resolved
            
        # Fallback to bundled resource
        for ext in [".ico", ".png", ".icns"]:
            fallback = os.path.join(self.app_root, "resources", f"app_icon{ext}")
            if os.path.exists(fallback):
                return fallback
                
        return resolved # Return best guess if fallback fails

    def setup_tray(self, title=None, icon=None):
        if not title:
            title = self.config.get("title", "Pytron")
        if not icon and "icon" in self.config:
            icon = self.config["icon"]
            
        icon = self._resolve_icon_path(icon)
        self.tray = SystemTray(title, icon)
        return self.tray

    def setup_tray_standard(self, title=None, icon=None):
        # Native Engine Check & Deferral
        if hasattr(self, "engine") and self.engine == "native":
            if not title:
                title = self.config.get("title", "Pytron")
            if not icon:
                icon = self.config.get("icon")
            
            icon = self._resolve_icon_path(icon)

            if not self.windows:
                # QUEUE IT: Windows aren't ready, but we WANT native tray.
                # Store it in config so the window picks it up on __init__ or start()
                self.config["_pending_native_tray"] = {
                    "title": title,
                    "icon": icon,
                    "close_to_tray": True
                }
                self.logger.info("Queued Native Tray creation for upcoming window.")
                return None

            if self.windows:
                try:
                    self.windows[0].create_tray(icon, title)
                    self.logger.info("Used Native Tray integration.")
                    self.windows[0].config["close_to_tray"] = True
                    return None
                except Exception as e:
                    self.logger.warning(f"Native Tray failed, falling back: {e}")

        # Fallback to Python-ctypes Tray (Chrome engine or Native failure)
        tray = self.setup_tray(title, icon)
        tray.add_item("Show App", self.show)
        tray.add_item("Hide App", self.hide)
        tray.add_separator()
        tray.add_item("Quit", self.quit)
        return tray
