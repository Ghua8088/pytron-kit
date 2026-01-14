import os
import sys
import json
import pytest
import tempfile
import shutil
from unittest.mock import MagicMock, patch
from pytron.plugin import Plugin, PluginError, discover_plugins


# Helper to create a dummy plugin structure
@pytest.fixture
def plugin_env():
    temp_dir = tempfile.mkdtemp()
    plugins_dir = os.path.join(temp_dir, "plugins")
    os.makedirs(plugins_dir)
    yield plugins_dir
    shutil.rmtree(temp_dir)


def create_plugin(base_dir, name, setup_code=None, manifest_extra=None):
    p_dir = os.path.join(base_dir, name)
    os.makedirs(p_dir)

    manifest = {
        "name": name,
        "version": "1.0.0",
        "entry_point": "main:init",
        "python_dependencies": [],
        "npm_dependencies": {},
    }
    if manifest_extra:
        manifest.update(manifest_extra)

    with open(os.path.join(p_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f)

    code = (
        setup_code
        or """
def init(app):
    return "initialized"
"""
    )
    with open(os.path.join(p_dir, "main.py"), "w") as f:
        f.write(code)

    return os.path.join(p_dir, "manifest.json")


def test_plugin_discovery(plugin_env):
    create_plugin(plugin_env, "plugin_a")
    create_plugin(plugin_env, "plugin_b")

    # Create an invalid one (no manifest)
    os.makedirs(os.path.join(plugin_env, "invalid_plugin"))

    plugins = discover_plugins(plugin_env)
    assert len(plugins) == 2
    names = {p.name for p in plugins}
    assert "plugin_a" in names
    assert "plugin_b" in names


def test_plugin_load_success(plugin_env):
    manifest_path = create_plugin(plugin_env, "test_plugin")
    plugin = Plugin(manifest_path)

    # Mock app
    app = MagicMock()
    app.storage_path = os.path.dirname(plugin_env)  # temp root

    plugin.load(app)
    assert plugin.instance == "initialized"


def test_plugin_load_class(plugin_env):
    code = """
class MyPlugin:
    def __init__(self, app):
        self.app = app
        self.started = False
        
    def setup(self):
        self.started = True
        
    def teardown(self):
        self.started = False
"""
    manifest_path = create_plugin(
        plugin_env, "class_plugin", code, {"entry_point": "main:MyPlugin"}
    )
    plugin = Plugin(manifest_path)

    app = MagicMock()
    app.storage_path = os.path.dirname(plugin_env)

    plugin.load(app)
    assert plugin.instance.started is True

    plugin.unload()
    assert not hasattr(plugin, "instance") or plugin.instance is None


def test_undefined_entry_point(plugin_env):
    manifest_path = create_plugin(
        plugin_env, "broken_plugin", manifest_extra={"entry_point": "main:missing_func"}
    )
    plugin = Plugin(manifest_path)
    app = MagicMock()

    with pytest.raises(PluginError) as exc:
        plugin.load(app)
    assert "Entry point 'missing_func' not found" in str(exc.value)


@patch("subprocess.check_call")
def test_install_dependencies_native(mock_subprocess, plugin_env):
    manifest_path = create_plugin(
        plugin_env, "dep_plugin", manifest_extra={"python_dependencies": ["requests"]}
    )
    plugin = Plugin(manifest_path)

    # Should call pip
    with patch("importlib.import_module", side_effect=ImportError):
        plugin.install_dependencies()
        mock_subprocess.assert_called()
        cmd = mock_subprocess.call_args[0][0]
        assert "pip" in cmd and "install" in cmd and "requests" in cmd


@patch("subprocess.check_call")
def test_install_dependencies_frozen_skipped(mock_subprocess, plugin_env):
    manifest_path = create_plugin(
        plugin_env,
        "frozen_plugin",
        manifest_extra={"python_dependencies": ["requests"]},
    )
    plugin = Plugin(manifest_path)

    # Simulate Frozen
    with patch.object(sys, "frozen", True, create=True):
        plugin.install_dependencies()

    # Should NOT call pip
    mock_subprocess.assert_not_called()


def test_load_non_callable_entry(plugin_env):
    # This reproduces the "NoneType object is not callable" scenario but with safeguards
    code = """
init = None
"""
    manifest_path = create_plugin(
        plugin_env, "none_plugin", code, {"entry_point": "main:init"}
    )
    plugin = Plugin(manifest_path)
    app = MagicMock()
    app.storage_path = os.path.dirname(plugin_env)

    # The load method catches exceptions internally (inside init_plugin) and logs them for resilience.
    plugin.load(app)

    # Since init failed, instance should not be set
    assert not hasattr(plugin, "instance")
