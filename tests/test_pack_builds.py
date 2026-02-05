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


@pytest.fixture
def mock_context(tmp_path):
    """Creates a mock BuildContext for testing."""
    context = MagicMock()
    context.script = tmp_path / "app.py"
    context.script.touch()
    context.out_name = "MyApp"
    context.settings = {"title": "MyApp", "version": "1.0"}
    context.app_icon = None
    context.package_dir = tmp_path
    context.add_data = []  # List of strings "src=dst"
    context.hidden_imports = []
    context.binaries = []
    context.runtime_hooks = []
    context.extra_args = []
    context.frontend_dist = None
    context.progress = MagicMock()
    context.task_id = 1
    # Defaults
    context.is_onefile = True
    context.is_secure = False

    # Mock package/pytron/dependencies path for tests
    (tmp_path / "pytron" / "dependancies").mkdir(parents=True, exist_ok=True)
    return context


def test_run_nuitka_build(mock_run, mock_context):
    # Setup Context Specifics
    mock_context.settings["console"] = False
    mock_context.is_onefile = True

    # Mock shutil.which to avoid install attempt
    with patch("shutil.which", return_value="nuitka"):
        # Mock sys.platform to ensure Windows flags are tested
        with patch("sys.platform", "win32"):
            # Mock get_python_executable/get_venv to avoid path errors
            with patch(
                "pytron.pack.nuitka.get_python_executable", return_value="python"
            ):
                with patch(
                    "pytron.pack.nuitka.get_venv_site_packages", return_value=Path(".")
                ):
                    run_nuitka_build(mock_context)

    mock_run.assert_called()
    cmd = mock_run.call_args[0][0]

    # Verify Nuitka flags
    assert "-m" in cmd
    assert "nuitka" in cmd
    assert "--onefile" in cmd
    assert "--windows-console-mode=disable" in cmd  # console=False
    assert f"--product-name=MyApp" in cmd


def test_run_pyinstaller_build(mock_run_pyi, mock_context):
    # Setup Context Specifics
    mock_context.settings["console"] = True
    mock_context.is_onefile = False

    # Mock cleanup_dist
    with patch("pytron.pack.pyinstaller.cleanup_dist"):
        # Mock build_installer
        with patch("pytron.pack.pyinstaller.build_installer"):
            # Mock helpers
            with patch(
                "pytron.pack.pyinstaller.get_python_executable", return_value="python"
            ):
                # Mock harvest hooks to avoid real file lookup
                with patch("pytron.pack.pyinstaller.generate_nuclear_hooks"):
                    # Mock Path.exists to pass the spec file check
                    with patch("pathlib.Path.exists", return_value=True):
                        run_pyinstaller_build(mock_context)

    # Should call run_command_with_output twice: once for makespec, once for build
    assert mock_run_pyi.call_count == 2

    # Check makespec command
    cmd_makespec = mock_run_pyi.call_args_list[0][0][0]
    assert "PyInstaller.utils.cliutils.makespec" in cmd_makespec
    assert "--name" in cmd_makespec
    assert "MyApp" in cmd_makespec
    assert "--console" in cmd_makespec
    assert "--onedir" in cmd_makespec  # context.is_onefile = False

    # Check build command
    cmd_build = mock_run_pyi.call_args_list[1][0][0]
    assert "PyInstaller" in cmd_build
    assert "MyApp.spec" in str(cmd_build[-1])
