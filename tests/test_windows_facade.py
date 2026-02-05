import sys
import pytest
from unittest.mock import patch, MagicMock
from pytron.platforms.windows import WindowsImplementation

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only tests")


@pytest.fixture
def windows_impl():
    with patch("ctypes.windll.user32"), patch("ctypes.windll.shcore"):
        return WindowsImplementation()


def test_facade_minimize(windows_impl):
    with patch("pytron.platforms.windows_ops.window.minimize") as mock_minimize:
        windows_impl.minimize("dummy_w")
        mock_minimize.assert_called_once_with("dummy_w")


def test_facade_notification(windows_impl):
    with patch("pytron.platforms.windows_ops.system.notification") as mock_notify:
        windows_impl.notification("dummy_w", "Title", "Msg")
        mock_notify.assert_called_once_with("dummy_w", "Title", "Msg", None)


def test_facade_register_scheme(windows_impl):
    with patch(
        "pytron.platforms.windows_ops.webview.register_pytron_scheme"
    ) as mock_reg:
        cb = MagicMock()
        windows_impl.register_pytron_scheme("dummy_w", cb)
        mock_reg.assert_called_once_with("dummy_w", cb)
