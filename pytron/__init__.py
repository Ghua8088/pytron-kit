import sys
import os
import io

# Best-effort: configure stdio to UTF-8 early when pytron is imported. This
# helps packaged apps avoid UnicodeEncodeError during prints/logging.
try:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8:surrogatepass")
except Exception:
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

from .core import App, Webview, get_resource_path
from .plugin import Plugin
from .updater import Updater
