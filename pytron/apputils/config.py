import os
import sys
import json
import logging
from ..utils import get_resource_path
from ..exceptions import ConfigError

class ConfigMixin:
    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format="[Pytron] %(asctime)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S",
        )
        self.logger = logging.getLogger("Pytron")

    def _check_deep_link(self):
        self.state.launch_url = None
        if len(sys.argv) > 1:
            possible_url = sys.argv[1]
            if possible_url.startswith("pytron:") or "://" in possible_url:
                self.logger.info(f"App launched via Deep Link: {possible_url}")
                self.state.launch_url = possible_url

    def _load_config(self, config_file):
        self.config = {}
        path = get_resource_path(config_file)
        self.logger.debug(f"Resolved settings path: {path}")

        if not os.path.exists(path):
            path = os.path.abspath(config_file)

        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    self.config = json.load(f)
                
                if self.config.get("debug", False):
                    self.logger.setLevel(logging.DEBUG)
                    for handler in logging.root.handlers:
                        handler.setLevel(logging.DEBUG)
                    self.logger.debug("Debug mode enabled.")
                    
                    dev_url = os.environ.get("PYTRON_DEV_URL")
                    if dev_url:
                        self.config["url"] = dev_url
                        self.logger.info(f"Dev mode: Overriding URL to {dev_url}")

                config_version = self.config.get("pytron_version")
                if config_version:
                    try:
                        from .. import __version__
                        if config_version != __version__:
                            self.logger.warning(f"Version mismatch: Settings({config_version}) vs Installed({__version__})")
                    except ImportError:
                        pass
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse settings.json: {e}")
                raise ConfigError(f"Invalid JSON in settings file: {path}") from e
            except Exception as e:
                self.logger.error(f"Failed to load settings: {e}")
                raise ConfigError(f"Could not load settings from {path}") from e
        else:
            self.logger.warning(f"Settings file not found at {path}. Using default configuration.")

    def _setup_identity(self):
        title = self.config.get("title", "Pytron App")
        safe_title = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in title).strip("_")
        self._register_app_id(title, safe_title)
        return title, safe_title

    def _register_app_id(self, title, safe_title):
        author = self.config.get("author", "PytronUser")
        if not safe_title:
            safe_title = "".join([c for c in (title or "Pytron") if c.isalnum()]) or "PytronApp"
        app_id = f"{author}.{safe_title}.App"

        if sys.platform == "win32":
            try:
                from ..platforms.windows import WindowsImplementation
                WindowsImplementation().set_app_id(app_id)
                self.logger.debug(f"Set Windows AppUserModelID: {app_id}")
            except Exception as e:
                self.logger.debug(f"Failed to set App ID: {e}")
        elif sys.platform == "linux":
            try:
                from ..platforms.linux import LinuxImplementation
                LinuxImplementation().set_app_id(safe_title)
            except Exception:
                pass
        elif sys.platform == "darwin":
            try:
                from ..platforms.darwin import DarwinImplementation
                DarwinImplementation().set_app_id(title)
            except Exception:
                pass

    def _setup_storage(self, safe_title):
        if sys.platform == "win32":
            base_path = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        elif os.environ.get("PYTHON_PLATFORM") == "android":
            python_home = os.environ.get("PYTHONHOME")
            if python_home:
                base_path = os.path.dirname(python_home)
            else:
                base_path = os.path.expanduser("~")
        else:
            base_path = os.path.expanduser("~/.config")

        if self.config.get("debug", False):
            self.storage_path = os.path.join(base_path, f"{safe_title}_Dev")
        else:
            self.storage_path = os.path.join(base_path, safe_title)

        if getattr(sys, "frozen", False):
            self.app_root = os.path.dirname(sys.executable)
        else:
            self.app_root = os.getcwd()

        try:
            os.makedirs(self.storage_path, exist_ok=True)
            os.chdir(self.storage_path)
            self.logger.info(f"Changed Working Directory to: {self.storage_path}")
        except Exception as e:
            self.logger.warning(f"Could not create storage directory at {self.storage_path}: {e}")

    def _resolve_resources(self):
        def resolve_resource(path):
            if not path or path.startswith(("http:", "https:", "file:")) or os.path.isabs(path):
                return path
            
            internal = os.path.join(self.app_root, "_internal", path)
            if os.path.exists(internal):
                return internal

            candidate = os.path.join(self.app_root, path)
            if os.path.exists(candidate):
                return candidate

            return get_resource_path(path)

        if "url" in self.config:
            self.config["url"] = resolve_resource(self.config["url"])

        if "icon" in self.config:
            orig_icon = self.config["icon"]
            resolved_icon = resolve_resource(orig_icon)
            if os.path.exists(resolved_icon):
                self.config["icon"] = resolved_icon
                self.logger.info(f"Resolved icon to: {resolved_icon}")
            else:
                self.logger.warning(f"Could not find icon at: {orig_icon}")
