import pytest
from unittest.mock import MagicMock, patch
from pytron.platforms.linux_ops import window, system, libs

@pytest.fixture(autouse=True)
def mock_libs():
    # Mock the libs module attributes
    with patch("pytron.platforms.linux_ops.libs.gtk", MagicMock()) as mock_gtk, \
         patch("pytron.platforms.linux_ops.libs.webkit", MagicMock()) as mock_webkit, \
         patch("pytron.platforms.linux_ops.libs.glib", MagicMock()) as mock_glib, \
         patch("pytron.platforms.linux_ops.libs.gio", MagicMock()) as mock_gio:
        yield mock_gtk, mock_webkit, mock_glib, mock_gio

@pytest.fixture
def mock_get_window():
    with patch("pytron.platforms.linux_ops.window.get_window", return_value=12345) as m:
        yield m

def test_window_minimize(mock_libs, mock_get_window):
    mock_gtk, _, _, _ = mock_libs
    window.minimize("dummy_w")
    mock_gtk.gtk_window_iconify.assert_called_with(12345)

def test_window_close(mock_libs, mock_get_window):
    mock_gtk, _, _, _ = mock_libs
    window.close("dummy_w")
    mock_gtk.gtk_window_close.assert_called_with(12345)

def test_system_notification():
    with patch("subprocess.Popen") as mock_popen:
        system.notification("dummy_w", "Title", "Message")
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args == ["notify-send", "Title", "Message"]

def test_system_message_box_zenity():
    with patch("subprocess.check_call") as mock_check_call:
        ret = system.message_box("dummy_w", "Title", "Msg", 0)
        assert ret == 1
        mock_check_call.assert_called()
        args = mock_check_call.call_args[0][0]
        assert args[0] == "zenity"
