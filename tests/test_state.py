import pytest
import threading
from unittest.mock import MagicMock
from pytron.state import ReactiveState


def test_state_init():
    app = MagicMock()
    state = ReactiveState(app)
    assert state.to_dict() == {}


def test_state_update_emits_event():
    app = MagicMock()
    # Mock windows list
    win1 = MagicMock()
    app.windows = [win1]
    app.is_running = True

    state = ReactiveState(app)
    state.count = 1

    # Verify local update
    assert state.count == 1
    assert state._data["count"] == 1

    # Verify emission
    win1.emit.assert_called_with("pytron:state-update", {"key": "count", "value": 1})


def test_state_no_emit_if_unchanged():
    app = MagicMock()
    win1 = MagicMock()
    app.windows = [win1]
    app.is_running = True

    state = ReactiveState(app)
    state.count = 1
    win1.emit.reset_mock()

    # Update with same value
    state.count = 1
    win1.emit.assert_not_called()


def test_state_bulk_update():
    app = MagicMock()
    win1 = MagicMock()
    app.windows = [win1]
    app.is_running = True

    state = ReactiveState(app)
    state.update({"a": 10, "b": 20})

    assert state.a == 10
    assert state.b == 20

    # Verify multiple emissions
    calls = win1.emit.call_args_list
    assert len(calls) == 2
    # Order isn't guaranteed by dict iteration usually, but let's check content
    args_list = [c[0] for c in calls]  # [("pytron:state-update", {...}), ...]
    payloads = [
        c[1] for c in calls if len(c) > 1
    ]  # kwargs? No, assert_called_with uses positional if called that way

    # Just check that both keys were emitted
    keys_emitted = set()
    for call_args in calls:
        # call_args is (name, data), ... wait, mock call args structure:
        # call_args[0] is positional args tuple
        data = call_args[0][1]
        keys_emitted.add(data["key"])

    assert "a" in keys_emitted
    assert "b" in keys_emitted


def test_state_thread_safety():
    """Verify concurrent updates don't corrupt the internal dict."""
    app = MagicMock()
    state = ReactiveState(app)

    def worker(start, end):
        for i in range(start, end):
            state.counter = i

    t1 = threading.Thread(target=worker, args=(0, 100))
    t2 = threading.Thread(target=worker, args=(100, 200))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # We can't deterministically predict the final value of counter,
    # but we can ensure internal integrity (it didn't crash and holds a valid int).
    assert isinstance(state.counter, int)
    assert 0 <= state.counter < 200
