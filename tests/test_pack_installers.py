import sys
import os
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from pytron.pack.installers import build_installer, build_windows_installer, build_linux_installer

@pytest.fixture
def mock_run():
    with patch("pytron.pack.installers.run_command_with_output", return_value=0) as m:
        yield m

@pytest.fixture
def mock_subprocess():
    with patch("subprocess.run") as m:
        yield m

def test_build_installer_dispatch():
    with patch("sys.platform", "win32"):
        with patch("pytron.pack.installers.build_windows_installer") as m:
            build_installer("App", Path("."), None)
            m.assert_called_once()

    with patch("sys.platform", "linux"):
        with patch("pytron.pack.installers.build_linux_installer") as m:
            build_installer("App", Path("."), None)
            m.assert_called_once()

    with patch("sys.platform", "darwin"):
        with patch("pytron.pack.installers.build_mac_installer") as m:
            build_installer("App", Path("."), None)
            m.assert_called_once()

def test_build_windows_installer_nsis_missing(mock_run, tmp_path):
    with patch("shutil.which", return_value=None):
        with patch("os.path.exists", return_value=False):
            # Should fail if makensis not found
            ret = build_windows_installer("App", tmp_path, None)
            assert ret == 1

def test_build_windows_installer_success(mock_run, tmp_path):
    # Mock makensis existence
    with patch("shutil.which", return_value="makensis.exe"):
        # Mock build dir existence
        # The function looks for "dist" in CWD. We must change CWD or patch Path("dist")
        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            (tmp_path / "dist" / "App").mkdir(parents=True)
            (tmp_path / "dist" / "App" / "App.exe").touch()
            
            # Create dummy installer.nsi
            (tmp_path / "installer.nsi").touch()
            
            ret = build_windows_installer("App", tmp_path, None)
            
            assert ret == 0
            mock_run.assert_called()
            cmd = mock_run.call_args[0][0]
            assert "makensis.exe" in cmd
            assert "/DNAME=App" in cmd
        finally:
            os.chdir(cwd)

def test_build_linux_installer_missing_dpkg(mock_run, tmp_path):
    with patch("shutil.which", return_value=None):
        ret = build_linux_installer("App", tmp_path, None)
        assert ret == 1

def test_build_linux_installer_success(tmp_path):
    with patch("shutil.which", return_value="/usr/bin/dpkg-deb"):
        with patch("subprocess.call", return_value=0) as mock_call:
            # Setup source dir
            (tmp_path / "dist" / "App").mkdir(parents=True)
            
            # We need to change cwd to tmp_path because the function looks for "dist" in CWD
            # or we patch Path("dist")
            cwd = os.getcwd()
            os.chdir(tmp_path)
            try:
                ret = build_linux_installer("App", tmp_path, None)
            finally:
                os.chdir(cwd)
                
            assert ret == 0
            mock_call.assert_called()
            args = mock_call.call_args[0][0]
            assert args[0] == "dpkg-deb"
            assert args[1] == "--build"
