import os
import sys
import json
import logging
import shutil
from ..utils import get_resource_path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from ..exceptions import ConfigError
import binascii
import ctypes


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
                # Defer dispatch to run-time if needed, but since plugins/handlers
                # might be registered AFTER init, we might need to handle this carefully.
                # However, for now, we'll store it. The handlers usually aren't registered
                # until the user script runs.
                # So we should probably dispatch in app.run().

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
                            self.logger.warning(
                                f"Version mismatch: Settings({config_version}) vs Installed({__version__})"
                            )
                    except ImportError:
                        pass
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse settings.json: {e}")
                raise ConfigError(f"Invalid JSON in settings file: {path}") from e
            except Exception as e:
                self.logger.error(f"Failed to load settings: {e}")
                raise ConfigError(f"Could not load settings from {path}") from e
        else:
            self.logger.warning(
                f"Settings file not found at {path}. Using default configuration."
            )

    def _setup_identity(self):
        title = self.config.get("title", "Pytron App")
        safe_title = "".join(
            c if c.isalnum() or c in ("-", "_") else "_" for c in title
        ).strip("_")
        app_id = self._register_app_id(title, safe_title)

        # Single Instance Guard
        if self.config.get("single_instance", True):
            self._setup_single_instance(app_id)

        return title, safe_title

    def _register_app_id(self, title, safe_title):
        author = self.config.get("author", "PytronUser")
        if not safe_title:
            safe_title = (
                "".join([c for c in (title or "Pytron") if c.isalnum()]) or "PytronApp"
            )
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
            except Exception as e:
                self.logger.debug(f"Failed to set Linux App ID: {e}")
        elif sys.platform == "darwin":
            try:
                from ..platforms.darwin import DarwinImplementation

                DarwinImplementation().set_app_id(title)
            except Exception as e:
                self.logger.debug(f"Failed to set Darwin App ID: {e}")
        return app_id

    def _setup_single_instance(self, app_id):
        import socket
        import hashlib
        import threading
        import os

        # Skip during tests as they often create multiple app instances rapidly
        if "PYTEST_CURRENT_TEST" in os.environ:
            return

        # Generate a stable port between 10000-60000 based on app_id
        # B324: Use SHA256 instead of MD5 for port generation stability
        port = 10000 + (int(hashlib.sha256(app_id.encode()).hexdigest(), 16) % 50000)
        self._instance_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self._instance_socket.bind(("127.0.0.1", port))
            self._instance_socket.listen(1)

            def _listen_for_other_instances():
                while True:
                    try:
                        conn, _ = self._instance_socket.accept()
                        data = conn.recv(1024).decode("utf-8")
                        if data:
                            msg = json.loads(data)
                            url = msg.get("url")
                            if url:
                                self.logger.info(
                                    f"Received deep link from another instance: {url}"
                                )
                                # Update launch URL and show windows
                                self.state.launch_url = url
                                self.router.dispatch(url)
                                for window in self.windows:
                                    window.show()
                                    window.emit("pytron:deep-link", {"url": url})
                        conn.close()
                    except Exception:
                        break

            t = threading.Thread(target=_listen_for_other_instances, daemon=True)
            t.start()

            @self.on_exit
            def _close_instance_socket():
                try:
                    self._instance_socket.close()
                except Exception as e:
                    self.logger.debug(f"Error closing instance socket: {e}")

        except socket.error:
            # Instance already running!
            self.logger.info(
                "Another instance is already running. Forwarding launch URL and exiting."
            )
            try:
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.connect(("127.0.0.1", port))
                client.send(json.dumps({"url": self.state.launch_url}).encode("utf-8"))
                client.close()
            except Exception:
                pass
            sys.exit(0)

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

        self.storage_path = os.path.join(base_path, safe_title)

        if getattr(sys, "frozen", False):
            self.app_root = os.path.dirname(os.path.abspath(sys.executable))
        else:
            # Better way to find app root than os.getcwd() which depends on where user ran Python
            main_module = sys.modules.get("__main__")
            if main_module and hasattr(main_module, "__file__"):
                self.app_root = os.path.dirname(os.path.abspath(main_module.__file__))
            else:
                self.app_root = os.path.abspath(
                    sys.path[0] if sys.path and sys.path[0] else os.getcwd()
                )

        try:
            os.makedirs(self.storage_path, exist_ok=True)
            os.chdir(self.storage_path)
            self.logger.info(f"Changed Working Directory to: {self.storage_path}")
        except Exception as e:
            self.logger.warning(
                f"Could not create storage directory at {self.storage_path}: {e}"
            )

    def _resolve_resources(self):
        def resolve_resource(path):
            if (
                not path
                or path.startswith(("http:", "https:", "file:"))
                or os.path.isabs(path)
            ):
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

    def _setup_key_value_store(self):
        self._store_file = os.path.join(self.storage_path, "store.json")
        self._kv_store = {}
        if os.path.exists(self._store_file):
            try:
                with open(self._store_file, "r") as f:
                    self._kv_store = json.load(f)
            except Exception as e:
                self.logger.warning(f"Failed to load persistent store: {e}")

    def store_set(self, key, value):
        """Sets a value in the persistent store."""
        self._kv_store[key] = value
        self._save_store()

    def store_get(self, key, default=None):
        """Gets a value from the persistent store."""
        return self._kv_store.get(key, default)

    def store_delete(self, key):
        """Removes a key from the persistent store."""
        if key in self._kv_store:
            del self._kv_store[key]
            self._save_store()
            return True
        return False

    def _save_store(self):
        try:
            with open(self._store_file, "w") as f:
                json.dump(self._kv_store, f)
        except Exception as e:
            self.logger.error(f"Failed to save persistent store: {e}")
