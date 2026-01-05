import os
import json
import pytest
import logging
from unittest.mock import MagicMock, patch
from pytron.apputils.config import ConfigMixin
from pytron.exceptions import ConfigError

# Mock State object
class MockState:
    def __init__(self):
        self.launch_url = None

# Test Class inheriting from ConfigMixin
class MockApp(ConfigMixin):
    def __init__(self):
        self.state = MockState()
        self.logger = logging.getLogger("TestApp")

@pytest.fixture
def app():
    return MockApp()

def test_setup_logging(app):
    app._setup_logging()
    assert app.logger.name == "Pytron"
    assert app.logger.level == logging.NOTSET  # Default level

def test_load_config_valid(app, tmp_path):
    # Create a dummy config file
    config_data = {"title": "Test App", "debug": True}
    config_file = tmp_path / "settings.json"
    with open(config_file, "w") as f:
        json.dump(config_data, f)
    
    # Mock get_resource_path to return our temp file
    with patch("pytron.apputils.config.get_resource_path", return_value=str(config_file)):
        app._load_config("settings.json")
        
    assert app.config["title"] == "Test App"
    assert app.config["debug"] is True
    # Debug mode should set logger level to DEBUG
    assert app.logger.level == logging.DEBUG

def test_load_config_missing(app):
    # Should handle missing file gracefully (log warning, empty config)
    with patch("pytron.apputils.config.get_resource_path", return_value="non_existent.json"):
        app._load_config("non_existent.json")
        
    assert app.config == {}

def test_load_config_invalid_json(app, tmp_path):
    config_file = tmp_path / "bad_settings.json"
    with open(config_file, "w") as f:
        f.write("{invalid_json")
        
    with patch("pytron.apputils.config.get_resource_path", return_value=str(config_file)):
        with pytest.raises(ConfigError):
            app._load_config("bad_settings.json")

def test_setup_identity(app):
    app.config = {"title": "My Cool App", "author": "Me"}
    
    # Mock platform implementations to avoid side effects
    with patch("sys.platform", "win32"):
        with patch("pytron.platforms.windows.WindowsImplementation") as mock_win:
            title, safe_title = app._setup_identity()
            
            assert title == "My Cool App"
            assert safe_title == "My_Cool_App"
            mock_win.return_value.set_app_id.assert_called_with("Me.My_Cool_App.App")

def test_setup_storage(app, tmp_path):
    app.config = {"title": "TestApp"}
    
    # Mock environment to control storage path
    with patch.dict(os.environ, {"LOCALAPPDATA": str(tmp_path)}):
        with patch("sys.platform", "win32"):
            app._setup_storage("TestApp")
            
    expected_path = tmp_path / "TestApp"
    assert app.storage_path == str(expected_path)
    assert os.path.exists(expected_path)
    assert os.getcwd() == str(expected_path)

