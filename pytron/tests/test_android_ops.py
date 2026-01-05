import os
import sys
import pytest
from unittest.mock import MagicMock, patch, call
from pathlib import Path

# Import the modules to test
from pytron.platforms.android.ops.init import init_android_project, reset_android_project
from pytron.platforms.android.ops.build import build_android_project
from pytron.platforms.android.ops.run import run_android_project

@pytest.fixture
def mock_run_command():
    with patch("pytron.platforms.android.ops.utils.run_command_with_output") as m:
        yield m

@pytest.fixture
def mock_log():
    with patch("pytron.platforms.android.ops.init.log") as m:
        yield m

@pytest.fixture
def mock_log_build():
    with patch("pytron.platforms.android.ops.build.log") as m:
        yield m

@pytest.fixture
def mock_log_run():
    with patch("pytron.platforms.android.ops.run.log") as m:
        yield m

def test_init_android_project(tmp_path, mock_log):
    # Mock shutil.copytree
    with patch("shutil.copytree") as mock_copy:
        init_android_project(str(tmp_path))
        
        mock_copy.assert_called_once()
        # Check if log was called with success
        assert mock_log.call_count >= 1
        assert "initialized" in mock_log.call_args_list[-1][0][0]

def test_init_android_project_exists_no_force(tmp_path, mock_log):
    (tmp_path / "android").mkdir()
    
    with patch("shutil.copytree") as mock_copy:
        init_android_project(str(tmp_path), force=False)
        
        mock_copy.assert_not_called()
        assert "already exists" in mock_log.call_args[0][0]

def test_init_android_project_exists_force(tmp_path, mock_log):
    (tmp_path / "android").mkdir()
    
    with patch("shutil.copytree") as mock_copy, \
         patch("shutil.rmtree") as mock_rm:
        init_android_project(str(tmp_path), force=True)
        
        mock_rm.assert_called_once()
        mock_copy.assert_called_once()

def test_build_android_project_no_init(tmp_path, mock_log_build):
    build_android_project(str(tmp_path))
    assert "Run init first" in mock_log_build.call_args[0][0]

def test_build_android_project_success(tmp_path, mock_run_command, mock_log_build):
    android_dir = tmp_path / "android"
    android_dir.mkdir()
    (android_dir / "gradlew").touch()
    
    # Mock os.name to control gradlew call
    with patch("os.name", "posix"):
        with patch("os.chmod") as mock_chmod:
            build_android_project(str(tmp_path))
            mock_chmod.assert_called()
            
            mock_run_command.assert_called()
            cmd = mock_run_command.call_args[0][0]
            assert "assembleDebug" in cmd

def test_run_android_project_no_apk(tmp_path, mock_log_run):
    android_dir = tmp_path / "android"
    android_dir.mkdir()
    
    run_android_project(str(tmp_path))
    assert "APK not found" in mock_log_run.call_args[0][0]

def test_run_android_project_success(tmp_path, mock_run_command, mock_log_run):
    android_dir = tmp_path / "android"
    android_dir.mkdir(parents=True)
    
    apk_dir = android_dir / "app/build/outputs/apk/debug"
    apk_dir.mkdir(parents=True)
    (apk_dir / "app-debug.apk").touch()
    
    # Mock build.gradle reading
    gradle_file = android_dir / "app/build.gradle"
    gradle_file.parent.mkdir(parents=True, exist_ok=True)
    gradle_file.write_text('applicationId "com.test.app"')
    
    with patch("pytron.platforms.android.ops.run.run_logcat"):
        run_android_project(str(tmp_path))
        
        assert mock_run_command.call_count >= 2
        # Install
        assert "install" in mock_run_command.call_args_list[0][0][0]
        # Launch
        assert "am" in mock_run_command.call_args_list[1][0][0]
        assert "com.test.app" in mock_run_command.call_args_list[1][0][0][5]
