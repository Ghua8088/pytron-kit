import os
import sys
import pytest
from unittest.mock import MagicMock, patch, call
from pytron.apputils.windows import WindowMixin


# Mock App class that uses the mixin
class MockApp(WindowMixin):
    def __init__(self):
        self.config = {"title": "Test App", "width": 800, "height": 600}
        self.windows = []
        self._exposed_functions = {}
        self.logger = MagicMock()
        self.app_root = os.getcwd()
        self.storage_path = os.path.join(os.getcwd(), "storage")
        self.shortcuts = {}
        self.shortcut_manager = MagicMock()
        self.tray = None
        self._on_exit_callbacks = []
        self.is_running = False


@pytest.fixture
def app():
    return MockApp()


@pytest.fixture
def mock_webview():
    with patch("pytron.apputils.windows.Webview") as mock:
        # Setup the mock instance returned by the constructor
        instance = mock.return_value
        instance.config = {}
        yield mock


def test_create_window_defaults(app, mock_webview):
    window = app.create_window()

    # Should create a Webview with merged config
    mock_webview.assert_called_once()
    call_args = mock_webview.call_args[1]["config"]
    assert call_args["title"] == "Test App"
    assert call_args["navigate_on_init"] is False

    # Should add to windows list
    assert window in app.windows
    assert len(app.windows) == 1

    # Should center by default
    window.center.assert_called_once()


def test_create_window_url_resolution(app, mock_webview):
    # Test relative path resolution
    app.create_window(url="index.html")

    # Check if navigate was called with resolved path
    # Note: logic in create_window modifies kwargs["url"] before creating Webview
    # but navigate is called with window_config.get("url")

    # Since we are mocking, we need to check what was passed to Webview or navigate
    window = app.windows[0]
    window.navigate.assert_called()
    args = window.navigate.call_args[0]
    assert "index.html" in args[0]
    if not sys.platform == "win32":  # On windows paths might be different
        assert os.path.isabs(args[0])


def test_create_window_exposed_functions(app, mock_webview):
    # Setup exposed functions
    mock_func = MagicMock()
    app._exposed_functions["my_func"] = {"func": mock_func, "secure": False}

    window = app.create_window()

    # Should bind the function
    window.bind.assert_called_with(
        "my_func", mock_func, secure=False, run_in_thread=True
    )


def test_broadcast(app, mock_webview):
    # Create two windows
    win1 = app.create_window()
    win2 = app.create_window()

    app.broadcast("test-event", {"data": 123})

    win1.emit.assert_called_with("test-event", {"data": 123})
    win2.emit.assert_called_with("test-event", {"data": 123})


def test_window_management_methods(app, mock_webview):
    win = app.create_window()

    app.hide()
    win.hide.assert_called_once()

    app.show()
    win.show.assert_called_once()

    app.notify("Title", "Msg")
    win.notify.assert_called_with("Title", "Msg", "info", 5000)

    app.quit()
    win.close.assert_called_with(force=True)


def test_run_lifecycle(app, mock_webview):
    # Mock pyi_splash
    with patch.dict(sys.modules, {"pyi_splash": MagicMock()}):
        app.run()

    # Should create a window if none exist
    assert len(app.windows) == 1

    # Should start the first window
    app.windows[0].start.assert_called_once()

    # Should stop shortcut manager
    app.shortcut_manager.stop.assert_called_once()


def test_run_cleanup_dev_storage(app, mock_webview):
    app.config["debug"] = True
    # Use actual PID to match the check in windows.py
    temp_storage = os.path.join(os.getcwd(), f"_Dev_{os.getpid()}")
    os.makedirs(temp_storage, exist_ok=True)

    with patch("shutil.rmtree") as mock_rmtree:
        app.run(storage_path=temp_storage)

        # Should attempt to remove dev storage
        mock_rmtree.assert_called_with(temp_storage, ignore_errors=True)

    # Cleanup if mock didn't actually delete
    if os.path.exists(temp_storage):
        os.rmdir(temp_storage)
