import threading


class ReactiveState:
    """
    A magic object that syncs its attributes to the frontend automatically.
    """

    def __init__(self, app):
        # Use super().__setattr__ to avoid triggering our own hook for internal vars
        super().__setattr__("_app", app)
        super().__setattr__("_data", {})
        # Re-entrant lock to allow nested access from same thread
        super().__setattr__("_lock", threading.RLock())

    def __setattr__(self, key, value):
        # Store the value and broadcast in a thread-safe manner to ensure order
        with self._lock:
            # Check if value actually changed to prevent redundant IPC
            if self._data.get(key) == value:
                return
            self._data[key] = value

            app_ref = getattr(self, "_app", None)
            if app_ref and app_ref.is_running:
                # PERFORMANCE: Only send the delta (key/value)
                for window in list(app_ref.windows):
                    try:
                        window.emit("pytron:state-update", {"key": key, "value": value})
                    except Exception as e:
                        # Silently ignore errors during shutdown
                        if app_ref.is_running:
                            print(
                                f"[Pytron] Error emitting state update for key '{key}': {e}"
                            )

    def __getattr__(self, key):
        lock = getattr(self, "_lock", None)
        if lock is not None:
            with lock:
                return self._data.get(key)
        return self._data.get(key)

    def to_dict(self):
        lock = getattr(self, "_lock", None)
        if lock is not None:
            with lock:
                return dict(self._data)
        return dict(self._data)

    def update(self, mapping: dict):
        """
        Atomically update multiple keys and emit updates for each key.
        Use this when you want to set multiple state values from another thread
        without causing intermediate inconsistent states.
        """
        if not isinstance(mapping, dict):
            raise TypeError("mapping must be a dict")

        lock = getattr(self, "_lock", None)
        if lock is not None:
            with lock:
                self._data.update(mapping)
        else:
            self._data.update(mapping)

        app_ref = getattr(self, "_app", None)
        if app_ref:
            for key, value in mapping.items():
                for window in list(app_ref.windows):
                    try:
                        window.emit("pytron:state-update", {"key": key, "value": value})
                    except Exception as e:
                        print(
                            f"[Pytron] Error emitting state update for key '{key}': {e}"
                        )
