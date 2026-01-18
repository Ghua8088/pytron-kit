import sys
import os
import io

# Best-effort: configure stdio to UTF-8 early when pytron is imported. This
# helps packaged apps avoid UnicodeEncodeError during prints/logging.
try:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8:surrogatepass")
except Exception:
    # Environment setup is best-effort
    pass


def _early_reconfigure():
    try:
        if getattr(sys.stdout, "buffer", None) is not None:
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer,
                encoding="utf-8",
                errors="surrogatepass",
                line_buffering=True,
            )
    except Exception:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="surrogatepass")
        except Exception:
            # Fallback failed, cannot reconfigure stdout
            pass

    try:
        if getattr(sys.stderr, "buffer", None) is not None:
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer,
                encoding="utf-8",
                errors="surrogatepass",
                line_buffering=True,
            )
    except Exception:
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="surrogatepass")
        except Exception:
            # Fallback failed, cannot reconfigure stderr
            pass


# Skip reconfiguration if running under pytest to avoid conflict with capture
if "pytest" not in sys.modules and "pytest" not in sys.argv[0]:
    _early_reconfigure()

# Fetch version from installed package metadata to avoid manual updates
try:
    if sys.version_info >= (3, 8):
        from importlib.metadata import version, PackageNotFoundError
    else:
        from importlib_metadata import version, PackageNotFoundError

    try:
        __version__ = version("pytron-kit")
    except PackageNotFoundError:
        __version__ = "0.0.0-dev"
except ImportError:
    __version__ = "0.0.0-dev"

# --- Plugin Configuration Namespace ---
import types


class PluginsNamespace(types.ModuleType):
    def __init__(self):
        super().__init__("plugins")
        self._registered_configs = {}

    def __getattr__(self, name):
        # Return a configurator for the requested plugin
        return PluginConfigurator(name, self._registered_configs)

    def get_registered_config(self, plugin_name):
        return self._registered_configs.get(plugin_name, {})


class PluginConfigurator:
    def __init__(self, plugin_name, registry):
        self.plugin_name = plugin_name
        self.registry = registry

    def __call__(self, **kwargs):
        self.registry[self.plugin_name] = kwargs
        return self


# Create the instance and inject it into sys.modules so 'import plugins' works
plugins = PluginsNamespace()
sys.modules["plugins"] = plugins
# print(f"[Pytron] Injected plugins namespace into sys.modules: {sys.modules['plugins']}")
# --------------------------------------

from .core import App, Webview, get_resource_path, Menu, MenuBar
from .plugin import Plugin
from .updater import Updater
