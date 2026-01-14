import pytest
from unittest.mock import MagicMock, patch
from pytron import App


class DummyBridge:
    def hello(self):
        return "world"


def _mock_config_loader(self, *args):
    self.config = {}


def _mock_storage_setup(self, title):
    self.storage_path = "/tmp/mock_storage"
    self.resource_path = "/tmp/mock_resources"


@pytest.fixture
def mock_app_env():
    # We patch the methods on the Class so they apply to any instance created
    with patch(
        "pytron.application.App._setup_identity", return_value=("test-id", "test-title")
    ), patch(
        "pytron.application.App._load_config",
        autospec=True,
        side_effect=_mock_config_loader,
    ), patch(
        "pytron.application.App._setup_storage",
        autospec=True,
        side_effect=_mock_storage_setup,
    ):
        yield


def test_app_init(mock_app_env):
    app = App()
    assert app.windows == []
    assert hasattr(app, "state")
    assert hasattr(app, "router")
    assert app.config == {}
    assert app.storage_path == "/tmp/mock_storage"


def test_app_expose_function(mock_app_env):
    app = App()

    @app.expose
    def add(a, b):
        return a + b

    assert "add" in app._exposed_functions
    assert app._exposed_functions["add"]["func"](1, 2) == 3


def test_app_expose_renamed(mock_app_env):
    app = App()

    def subtract(a, b):
        return a - b

    app.expose(subtract, name="minus")

    assert "minus" in app._exposed_functions
    assert "subtract" not in app._exposed_functions
    assert app._exposed_functions["minus"]["func"](5, 2) == 3


def test_app_expose_class_instance(mock_app_env):
    app = App()
    bridge = DummyBridge()

    app.expose(bridge)

    assert "hello" in app._exposed_functions
    assert app._exposed_functions["hello"]["func"]() == "world"


def test_shortcuts(mock_app_env):
    app = App()

    @app.shortcut("Ctrl+S")
    def save():
        return "saved"

    assert "Ctrl+S" in app.shortcuts
    assert app.shortcuts["Ctrl+S"]() == "saved"


def test_on_exit_hook(mock_app_env):
    app = App()

    mock_hook = MagicMock()

    @app.on_exit
    def cleanup():
        mock_hook()

    # 1 default (thread pool) + 1 new
    assert len(app._on_exit_callbacks) == 2
