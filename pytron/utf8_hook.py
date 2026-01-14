"""Runtime hook for Pytron.

This hook attempts to make a frozen Pytron app robust when printing or logging
modern Unicode (emoji, CJK, astral-plane characters) on Windows and other
platforms. It is best-effort and will not crash the application if any step
fails.
"""

import os
import sys
import io
import locale
import logging


def _set_utf8_mode():
    # Best-effort environment hints for subprocesses and libraries
    try:
        os.environ.setdefault("PYTHONUTF8", "1")
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        os.environ.setdefault("LANG", "en_US.UTF-8")
    except Exception:
        pass

    # Prefer the user's locale if possible (no-op on failure)
    try:
        locale.setlocale(locale.LC_ALL, "")
    except Exception:
        pass

    # Override locale.getpreferredencoding() to return utf-8 so libraries
    # that consult it will prefer UTF-8.
    try:
        import locale as _locale

        _locale.getpreferredencoding = lambda do_setlocale=False: "utf-8"
    except Exception:
        pass

    # On Windows try to set the console code page to UTF-8 (65001).
    if sys.platform.startswith("win"):
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32

            # Harden: Explicitly define signatures for robustness
            kernel32.SetConsoleOutputCP.argtypes = [ctypes.c_uint]
            kernel32.SetConsoleOutputCP.restype = ctypes.c_int

            kernel32.SetConsoleCP.argtypes = [ctypes.c_uint]
            kernel32.SetConsoleCP.restype = ctypes.c_int

            # Check return values (Non-zero is success)
            if kernel32.SetConsoleOutputCP(65001) == 0:
                err = ctypes.get_last_error()
                # We don't want to crash on this, but we acknowledge the failure
                # logging.warning(f"Failed to SetConsoleOutputCP: {err}")
                pass

            if kernel32.SetConsoleCP(65001) == 0:
                err = ctypes.get_last_error()
                pass

        except Exception:
            pass

    # Wrap or reconfigure stdio streams to UTF-8 with surrogatepass to avoid
    # raising UnicodeEncodeError when printing characters that the system
    # code page cannot represent.
    def wrap_stream(stream):
        try:
            buf = getattr(stream, "buffer", None)
            if buf is not None:
                return io.TextIOWrapper(
                    buf, encoding="utf-8", errors="surrogatepass", line_buffering=True
                )
            # Fallback: try reconfigure (Python 3.7+)
            try:
                stream.reconfigure(encoding="utf-8", errors="surrogatepass")
            except Exception:
                pass
        except Exception:
            pass
        return stream

    try:
        if sys.stdin is not None:
            sys.stdin = wrap_stream(sys.stdin)
        if sys.stdout is not None:
            sys.stdout = wrap_stream(sys.stdout)
        if sys.stderr is not None:
            sys.stderr = wrap_stream(sys.stderr)
    except Exception:
        pass

    # Patch logging.StreamHandler so that handlers created after this hook will
    # get their stream wrapped as well.
    try:
        _orig_init = logging.StreamHandler.__init__

        def _patched_init(self, stream=None):
            _orig_init(self, stream=stream)
            try:
                if getattr(self, "stream", None) is not None:
                    self.stream = wrap_stream(self.stream)
            except Exception:
                pass

        logging.StreamHandler.__init__ = _patched_init
    except Exception:
        pass


_set_utf8_mode()
