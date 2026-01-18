import sys
import pytest
from unittest.mock import MagicMock, patch
from pytron.platforms.darwin_ops import window, system, libs

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS only tests")


@pytest.fixture(autouse=True)
def mock_libs():
    with patch(
        "pytron.platforms.darwin_ops.libs.objc", MagicMock()
    ) as mock_objc, patch(
        "pytron.platforms.darwin_ops.libs.cocoa", MagicMock()
    ) as mock_cocoa:
        yield mock_objc, mock_cocoa


@pytest.fixture
def mock_get_window():
    with patch(
        "pytron.platforms.darwin_ops.window.get_window", return_value=12345
    ) as m:
        yield m


def test_window_minimize(mock_libs, mock_get_window):
    mock_objc, _ = mock_libs
    window.minimize("dummy_w")
    # Verify objc_msgSend was called
    mock_objc.objc_msgSend.assert_called()


def test_window_close(mock_libs, mock_get_window):
    mock_objc, _ = mock_libs
    window.close("dummy_w")
    mock_objc.objc_msgSend.assert_called()


def test_system_notification():
    with patch("subprocess.Popen") as mock_popen:
        system.notification("dummy_w", "Title", "Message")
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[0] == "osascript"


def test_system_message_box():
    with patch("subprocess.check_output", return_value="OK") as mock_check:
        ret = system.message_box("dummy_w", "Title", "Msg", 0)
        assert ret == 1
        mock_check.assert_called()


def test_window_set_always_on_top(mock_libs, mock_get_window):
    mock_objc, _ = mock_libs
    window.set_always_on_top("dummy_w", True)
    # Verify call to setLevel: (level 3 for floating)
    # The actual detailed verification of objc_msgSend args is complex,
    # so we rely on ensuring it was called.

    # We can check if 'setLevel:' selector was registered
    mock_objc.sel_registerName.assert_any_call("setLevel:".encode("utf-8"))


def test_window_set_fullscreen(mock_libs, mock_get_window):
    mock_objc, _ = mock_libs

    # Mock return of styleMask to simulate NOT being in fullscreen (so it toggles ON)
    # We need to ensure call() returns something that doesn't have the fullscreen bit
    with patch("pytron.platforms.darwin_ops.window.call", return_value=0) as mock_call:
        window.set_fullscreen("dummy_w", True)
        # Should call toggleFullScreen:
        mock_call.assert_any_call(12345, "toggleFullScreen:", None)

    # Mock return of styleMask to simulate BEING in fullscreen (so it toggles OFF)
    with patch(
        "pytron.platforms.darwin_ops.window.call", return_value=(1 << 14)
    ) as mock_call:
        window.set_fullscreen("dummy_w", False)
        # Should call toggleFullScreen:
        mock_call.assert_any_call(12345, "toggleFullScreen:", None)
