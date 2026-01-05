import pytest
from unittest.mock import MagicMock, patch
from pytron.platforms.windows_ops import window, system, constants

@pytest.fixture(autouse=True)
def mock_hwnd_window():
    with patch("pytron.platforms.windows_ops.window.get_hwnd", return_value=12345) as m:
        yield m

@pytest.fixture(autouse=True)
def mock_hwnd_system():
    with patch("pytron.platforms.windows_ops.system.get_hwnd", return_value=12345) as m:
        yield m

def test_window_minimize(mock_hwnd_window):
    with patch("ctypes.windll.user32.ShowWindow") as mock_show:
        window.minimize("dummy_w")
        mock_show.assert_called_with(12345, constants.SW_MINIMIZE)

def test_window_close(mock_hwnd_window):
    with patch("ctypes.windll.user32.PostMessageW") as mock_post:
        window.close("dummy_w")
        mock_post.assert_called_with(12345, constants.WM_CLOSE, 0, 0)

def test_system_notification(mock_hwnd_system):
    with patch("ctypes.windll.shell32.Shell_NotifyIconW", return_value=1) as mock_notify:
        # We also need to mock LoadImageW and LoadIconW to avoid crashes or failures
        with patch("ctypes.windll.user32.LoadImageW", return_value=999), \
             patch("ctypes.windll.user32.LoadIconW", return_value=888):
            system.notification("dummy_w", "Title", "Message")
            assert mock_notify.call_count >= 1

def test_system_message_box(mock_hwnd_system):
    with patch("ctypes.windll.user32.MessageBoxW", return_value=1) as mock_msg:
        ret = system.message_box("dummy_w", "Title", "Msg", 0)
        assert ret == 1
        mock_msg.assert_called_with(12345, "Msg", "Title", 0)
