import sys
import os
import json
import threading
from .exceptions import StateError


def _get_global_store():
    # Helper to access standard sys overrides
    # (Used for Python-mock fallback if native fails)
    SOVEREIGN_KEY = "_pytron_sovereign_state_store_"
    store = getattr(sys, SOVEREIGN_KEY, None)
    if store is None:
        import builtins

        store = getattr(builtins, SOVEREIGN_KEY, None)
    return store


def _set_global_store(store):
    SOVEREIGN_KEY = "_pytron_sovereign_state_store_"
    setattr(sys, SOVEREIGN_KEY, store)
    import builtins

    setattr(builtins, SOVEREIGN_KEY, store)


def json_safe_dump(obj):
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    if isinstance(obj, dict):
        return {str(k): json_safe_dump(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [json_safe_dump(x) for x in obj]
    if hasattr(obj, "to_dict"):
        try:
            return json_safe_dump(obj.to_dict())
        except:
            pass
    return str(obj)


def log_shield(msg):
    try:
        if getattr(sys, "frozen", False):
            # In frozen apps, stderr might be captured or lost, but it's safe
            sys.stderr.write(f"[SHIELD] {msg}\n")
            sys.stderr.flush()
    except:
        pass


class ReactiveState:
    def __init__(self, app):
        object.__setattr__(self, "_app", app)

        # 1. Retrieve or Create the Global Store
        store = _get_global_store()

        if store is None:
            # TRY LOAD NATIVE via CANONICAL RESOLVER
            from .utils import resolve_native_module

            native_mod = resolve_native_module()
            NativeState = (
                getattr(native_mod, "NativeState", None) if native_mod else None
            )

            if NativeState:
                try:
                    store = NativeState()
                    mode = "Rust-Backed (Sovereign)"
                except Exception as e:
                    store = self._create_mock_store()
                    mode = f"Mock-Fallback (Rust Error: {e})"
            else:
                store = self._create_mock_store()
                mode = "Python-Mock"

            _set_global_store(store)
            log_shield(f"Sovereign State Initialized (Mode: {mode})")
        else:
            log_shield("ReactiveState: Inherited Sovereign Anchor")

        object.__setattr__(self, "_store", store)

    def _create_mock_store(self):
        class MockStore:
            def __init__(self):
                self.data = {}
                self._lock = threading.RLock()

            def set(self, k, v):
                with self._lock:
                    self.data[k] = v

            def get(self, k):
                with self._lock:
                    return self.data.get(k)

            def to_dict(self):
                with self._lock:
                    return dict(self.data)

            def update(self, m):
                with self._lock:
                    self.data.update(m)

        return MockStore()

    def __setattr__(self, key, value):
        if key.startswith("_"):
            object.__setattr__(self, key, value)
            return

        store = object.__getattribute__(self, "_store")
        app_ref = object.__getattribute__(self, "_app")

        try:
            safe_val = json_safe_dump(value)
            store.set(key, safe_val)
            if app_ref and hasattr(app_ref, "config") and app_ref.config.get("debug"):
                log_shield(f"State Update: {key}")
        except Exception as e:
            raise StateError(f"Failed to set state for key '{key}': {e}") from e

        # Python-side propagation (legacy fallback, Iron Bridge handles native)
        if app_ref:
            try:
                windows = getattr(app_ref, "windows", [])
                for window in list(windows):
                    try:
                        window.emit(
                            "pytron:state-update", {"key": key, "value": safe_val}
                        )
                    except:
                        pass
            except:
                pass

    def __getattr__(self, key):
        if key.startswith("_"):
            return object.__getattribute__(self, key)
        try:
            return object.__getattribute__(self, "_store").get(key)
        except:
            return None

    def to_dict(self):
        try:
            store = object.__getattribute__(self, "_store")
            return json_safe_dump(store.to_dict())
        except Exception as e:
            log_shield(f"to_dict failure: {e}")
            return {}

    def update(self, mapping: dict):
        if not isinstance(mapping, dict):
            return
        try:
            store = object.__getattribute__(self, "_store")
            store.update(json_safe_dump(mapping))
        except:
            pass
