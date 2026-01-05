import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from pytron.pack.nuitka import run_nuitka_build
from pytron.pack.pyinstaller import run_pyinstaller_build

@pytest.fixture
def mock_run():
    with patch("pytron.pack.nuitka.run_command_with_output", return_value=0) as m:
        yield m

@pytest.fixture
def mock_run_pyi():
    with patch("pytron.pack.pyinstaller.run_command_with_output", return_value=0) as m:
        yield m

def test_run_nuitka_build(mock_run, tmp_path):
    args = MagicMock()
    args.name = "MyApp"
    args.console = False
    args.installer = False
    
    script = tmp_path / "app.py"
    script.touch()
    
    settings = {"title": "MyApp", "version": "1.0"}
    
    # Mock shutil.which to avoid install attempt
    with patch("shutil.which", return_value="nuitka"):
        run_nuitka_build(
            args, 
            script, 
            "MyApp", 
            settings, 
            None, # icon
            str(tmp_path), # package_dir
            [], # add_data
            None, # frontend_dist
            MagicMock(), # progress
            MagicMock() # task
        )
        
    mock_run.assert_called()
    cmd = mock_run.call_args[0][0]
    
    # Verify Nuitka flags
    assert "-m" in cmd
    assert "nuitka" in cmd
    assert "--onefile" in cmd
    assert "--windows-console-mode=disable" in cmd # console=False
    assert f"--product-name=MyApp" in cmd

def test_run_pyinstaller_build(mock_run_pyi, tmp_path):
    args = MagicMock()
    args.name = "MyApp"
    args.console = True
    args.engine = "webview2"
    
    script = tmp_path / "app.py"
    script.touch()
    
    settings = {}
    
    # Mock cleanup_dist to avoid errors
    with patch("pytron.pack.pyinstaller.cleanup_dist"):
        # Mock spec file existence check
        with patch("pathlib.Path.exists", return_value=True):
            run_pyinstaller_build(
                args,
                script,
                "MyApp",
                settings,
                None,
                str(tmp_path),
                [],
                None, # manifest
                MagicMock(),
                MagicMock()
            )
            
    # Should call run_command_with_output twice: once for makespec, once for build
    assert mock_run_pyi.call_count == 2
    
    # Check makespec command
    cmd_makespec = mock_run_pyi.call_args_list[0][0][0]
    assert "PyInstaller.utils.cliutils.makespec" in cmd_makespec
    assert "--name" in cmd_makespec
    assert "MyApp" in cmd_makespec
    assert "--console" in cmd_makespec
    
    # Check build command
    cmd_build = mock_run_pyi.call_args_list[1][0][0]
    assert "PyInstaller" in cmd_build
    assert "MyApp.spec" in str(cmd_build[-1])
