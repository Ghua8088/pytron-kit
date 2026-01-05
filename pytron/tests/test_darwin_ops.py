import pytest
from unittest.mock import MagicMock, patch
from pytron.platforms.darwin_ops import window, system, libs

@pytest.fixture(autouse=True)
def mock_libs():
    with patch("pytron.platforms.darwin_ops.libs.objc", MagicMock()) as mock_objc, \
         patch("pytron.platforms.darwin_ops.libs.cocoa", MagicMock()) as mock_cocoa:
        yield mock_objc, mock_cocoa

@pytest.fixture
def mock_get_window():
    with patch("pytron.platforms.darwin_ops.window.get_window", return_value=12345) as m:
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
