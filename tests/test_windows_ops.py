import sys
import pytest
from unittest.mock import MagicMock, patch
from pytron.platforms.windows_ops import window, system, constants

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only tests")


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
    with patch(
        "ctypes.windll.shell32.Shell_NotifyIconW", return_value=1
    ) as mock_notify:
        # We also need to mock LoadImageW and LoadIconW to avoid crashes or failures
        with patch("ctypes.windll.user32.LoadImageW", return_value=999), patch(
            "ctypes.windll.user32.LoadIconW", return_value=888
        ):
            system.notification("dummy_w", "Title", "Message")
            assert mock_notify.call_count >= 1


def test_system_message_box(mock_hwnd_system):
    with patch("ctypes.windll.user32.MessageBoxW", return_value=1) as mock_msg:
        ret = system.message_box("dummy_w", "Title", "Msg", 0)
        assert ret == 1
        mock_msg.assert_called_with(12345, "Msg", "Title", 0)


def test_window_set_always_on_top(mock_hwnd_window):
    with patch("ctypes.windll.user32.SetWindowPos") as mock_swp:
        window.set_always_on_top("dummy_w", True)
        # HWND_TOPMOST = -1
        # Flags: SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE = 0x0002 | 0x0001 | 0x0010 = 0x0013 (19)
        mock_swp.assert_called_with(12345, -1, 0, 0, 0, 0, 19)


def test_window_set_fullscreen(mock_hwnd_window):
    # Mock return values for complex ctypes calls
    with patch("ctypes.windll.user32.GetWindowRect") as mock_gwr, patch(
        "ctypes.windll.user32.GetWindowLongW", return_value=0
    ) as mock_gwl, patch("ctypes.windll.user32.MonitorFromWindow") as mock_mfw, patch(
        "ctypes.windll.user32.GetMonitorInfoW"
    ) as mock_gmi, patch(
        "ctypes.windll.user32.SetWindowLongW"
    ) as mock_swl, patch(
        "ctypes.windll.user32.SetWindowPos"
    ) as mock_swp:

        window.set_fullscreen("dummy_w", True)
        assert mock_swl.called
        assert mock_swp.called
