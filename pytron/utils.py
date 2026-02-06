import sys
import os
import threading
import importlib.util

# --- SINGLE ORIGIN LOCKDOWN ---
# We store the resolved native module here to ensure
# we never load it twice from different paths.
_NATIVE_CACHE = {"module": None, "origin": None, "lock": threading.Lock()}


def get_resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller
    """
    if os.path.isabs(relative_path):
        return relative_path

    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            base_path = sys._MEIPASS
            full_path = os.path.join(base_path, relative_path)
            if os.path.exists(full_path):
                return full_path

        exe_path = os.path.dirname(sys.executable)
        full_path = os.path.join(exe_path, relative_path)
        if os.path.exists(full_path):
            return full_path

        try:
            base_path = os.path.dirname(__file__)
            return os.path.join(base_path, relative_path)
        except Exception:
            return os.path.join(exe_path, relative_path)
    else:
        if os.path.exists(relative_path):
            return os.path.abspath(relative_path)
        base_path = os.path.dirname(__file__)

    return os.path.join(base_path, relative_path)


def resolve_native_module():
    """
    STRICT SINGLETON RESOLVER for pytron_native.pyd.

    Rule: Exactly one NativeState may exist per process.
    Priority:
      1. Frozen _MEIPASS (highest)
      2. Frozen _internal
      3. Frozen Root
      4. Dev / Venv
      5. Fallback Package Import (lowest)

    This function discovers the module once, locks it, and returns the
    exact same module object for every subsequent call.
    """
    with _NATIVE_CACHE["lock"]:
        if _NATIVE_CACHE["module"]:
            return _NATIVE_CACHE["module"]

        # Explicit Priorities (Lower is Higher Priority)
        PRIORITY_FROZEN_MEIPASS = 10
        PRIORITY_FROZEN_INTERNAL = 20
        PRIORITY_FROZEN_ROOT = 30
        PRIORITY_DEV_LOCAL = 40
        PRIORITY_PACKAGE_FALLBACK = 99

        candidate_modules = []  # List of (priority, origin, mod)
        search_paths = []  # List of (priority, path)

        # 1. SEARCH STRATEGY
        if getattr(sys, "frozen", False):
            # FROZEN PRIORITY
            if hasattr(sys, "_MEIPASS"):
                # PyInstaller Temp Dir
                search_paths.append(
                    (
                        PRIORITY_FROZEN_MEIPASS,
                        os.path.join(sys._MEIPASS, "pytron", "dependencies"),
                    )
                )

            # Executable Dir (Nuitka / OneDir)
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            search_paths.append(
                (
                    PRIORITY_FROZEN_INTERNAL,
                    os.path.join(exe_dir, "_internal", "pytron", "dependencies"),
                )
            )

            # Also check direct executable root for flat layouts
            search_paths.append(
                (PRIORITY_FROZEN_ROOT, os.path.join(exe_dir, "dependencies"))
            )

        else:
            # DEV PRIORITY
            # Check relative to this file (pytron/utils.py -> pytron/dependencies)
            base_utils = os.path.dirname(os.path.abspath(__file__))
            search_paths.append(
                (PRIORITY_DEV_LOCAL, os.path.join(base_utils, "dependencies"))
            )

            # Site-packages fallback happens implicitly via imports below

        # Windows DLL Handling
        if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
            for _, p in search_paths:
                if os.path.exists(p):
                    try:
                        os.add_dll_directory(p)
                    except:
                        pass

        # 2. DISCOVERY

        # A) Explicit Path Discovery
        img_ext = ".pyd" if sys.platform == "win32" else ".so"
        for priority, path in search_paths:
            pyd_path = os.path.join(path, "pytron_native" + img_ext)
            if os.path.exists(pyd_path):
                try:
                    spec = importlib.util.spec_from_file_location(
                        "pytron.dependencies.pytron_native", pyd_path
                    )
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        # Don't register to sys.modules yet, we are vetting
                        spec.loader.exec_module(mod)
                        if hasattr(mod, "NativeState"):
                            candidate_modules.append((priority, pyd_path, mod))
                except Exception:
                    pass

        # B) Package Import Discovery (Fallback)
        if not candidate_modules:
            try:
                # Import without crashing
                from . import dependencies
                import importlib

                try:
                    native_pkg = importlib.import_module(
                        ".pytron_native", package="pytron.dependencies"
                    )
                    path = getattr(native_pkg, "__file__", "package_import")
                    candidate_modules.append(
                        (PRIORITY_PACKAGE_FALLBACK, path, native_pkg)
                    )
                except:
                    pass
            except:
                pass

        # 3. SELECTION & LOCKDOWN
        selected_mod = None
        selected_origin = None

        if candidate_modules:
            # Sort explicitly by priority (lowest number first)
            candidate_modules.sort(key=lambda x: x[0])

            # Pick FIRST (Highest Priority)
            _, selected_origin, selected_mod = candidate_modules[0]

            # Cache it
            _NATIVE_CACHE["module"] = selected_mod
            _NATIVE_CACHE["origin"] = selected_origin

            # Enforce sys.modules consistency to prevent re-importing
            sys.modules["pytron.dependencies.pytron_native"] = selected_mod
            sys.modules["pytron_native"] = selected_mod

            # Log Identity
            _log_shield(f"NativeState LOCKED to: {selected_origin}")
            _log_shield(f"NativeState Memory ID: {id(selected_mod)}")

            return selected_mod

        _log_shield("NativeState Resolution FAILED: No candidates found.")
        return None


def _log_shield(msg):
    # Internal logging helper
    try:
        if getattr(sys, "frozen", False):
            sys.stderr.write(f"[SHIELD] {msg}\n")
            sys.stderr.flush()
        # Debug log file
        with open("D:/pytron_debug.log", "a") as f:
            f.write(f"[SHIELD] {msg}\n")
    except:
        pass
