import pytest
import os
import json
import tempfile
from pytron.application import App
from pytron.exceptions import PytronError, ConfigError, ResourceNotFoundError


class TestExceptions:
    def test_pytron_error_hierarchy(self):
        err = ConfigError("Test config error")
        assert isinstance(err, PytronError)
        assert str(err) == "Test config error"


class TestAppConfig:
    def test_app_init_defaults(self):
        # Should initialize with default settings if file not found (or log warning)
        # But wait, current implementation:
        # if path exists: load.
        # else: log warning.
        app = App(config_file="non_existent_settings.json")
        assert app.config == {}

    def test_app_init_invalid_json(self):
        # Create a temp file with invalid json
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as tmp:
            tmp.write("{ invalid json ")
            tmp_path = tmp.name

        try:
            with pytest.raises(ConfigError) as excinfo:
                App(config_file=tmp_path)
            assert "Invalid JSON" in str(excinfo.value)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_app_init_valid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as tmp:
            tmp.write('{"title": "Test App", "debug": true}')
            tmp_path = tmp.name

        try:
            app = App(config_file=tmp_path)
            assert app.config["title"] == "Test App"
            assert app.config["debug"] is True
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
