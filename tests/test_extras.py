import os
import pytest
from unittest.mock import MagicMock, patch
from pytron.apputils.extras import ExtrasMixin
from pytron.exceptions import PytronError

# Mock PluginError since we can't easily import it if it's inside a function in the mixin
# Wait, the mixin imports it from ..plugin. Let's mock that module.

class MockApp(ExtrasMixin):
    def __init__(self):
        self.config = {"title": "Test App", "icon": "app.ico"}
        self.plugins = []
        self.logger = MagicMock()
        self.app_root = os.getcwd()
        self.tray = None
        
        # Mock methods needed by setup_tray_standard
        self.show = MagicMock()
        self.hide = MagicMock()
        self.quit = MagicMock()

@pytest.fixture
def app():
    return MockApp()

def test_load_plugin_success(app):
    # Patch the source module since it's imported inside the function
    with patch("pytron.plugin.Plugin") as MockPlugin:
        plugin_instance = MockPlugin.return_value
        plugin_instance.name = "TestPlugin"
        plugin_instance.version = "1.0.0"
        
        app.load_plugin("plugin.json")
        
        MockPlugin.assert_called_with("plugin.json")
        plugin_instance.check_dependencies.assert_called_once()
        plugin_instance.load.assert_called_with(app)
        
        assert plugin_instance in app.plugins
        app.logger.info.assert_called()

def test_load_plugin_failure(app):
    # Mock PluginError in the source module
    mock_plugin_module = MagicMock()
    class FakePluginError(Exception): pass
    
    # We need to patch the actual module that is imported
    with patch("pytron.plugin.Plugin", side_effect=FakePluginError("Invalid manifest")):
        # We also need to ensure PluginError is caught. 
        # The code does `except PluginError`. 
        # If we raise FakePluginError, we need `PluginError` in the code to match `FakePluginError`.
        # Since we can't easily change what `from ..plugin import PluginError` binds to inside the function
        # without patching sys.modules['pytron.plugin'], let's do that.
        
        with patch.dict("sys.modules", {"pytron.plugin": mock_plugin_module}):
            mock_plugin_module.PluginError = FakePluginError
            # Re-patch Plugin on the mock module
            mock_plugin_module.Plugin.side_effect = FakePluginError("Invalid manifest")
            
            # But wait, the function does `from ..plugin import Plugin`.
            # If we patch sys.modules, that import will get our mock.
            
            app.load_plugin("bad.json")
             
        # Should log error but not raise
        app.logger.error.assert_called()
        assert len(app.plugins) == 0

def test_setup_tray(app):
    with patch("pytron.apputils.extras.SystemTray") as MockTray:
        tray = app.setup_tray()
        
        MockTray.assert_called()
        args = MockTray.call_args[0]
        assert args[0] == "Test App" # Title
        # Icon path resolution check
        assert "app.ico" in args[1] 
        
        assert app.tray == MockTray.return_value

def test_setup_tray_custom_args(app):
    with patch("pytron.apputils.extras.SystemTray") as MockTray:
        app.setup_tray(title="Custom Title", icon="custom.ico")
        
        MockTray.assert_called()
        args = MockTray.call_args[0]
        assert args[0] == "Custom Title"
        assert "custom.ico" in args[1]

def test_setup_tray_standard(app):
    with patch("pytron.apputils.extras.SystemTray") as MockTray:
        tray_instance = MockTray.return_value
        
        app.setup_tray_standard()
        
        # Should add standard items
        assert tray_instance.add_item.call_count >= 3
        tray_instance.add_separator.assert_called()
        
        # Check callbacks
        # We can't easily check the exact callback function equality without more work,
        # but we can check the labels
        calls = tray_instance.add_item.call_args_list
        labels = [c[0][0] for c in calls]
        assert "Show App" in labels
        assert "Hide App" in labels
        assert "Quit" in labels
