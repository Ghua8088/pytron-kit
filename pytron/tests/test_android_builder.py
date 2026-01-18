import pytest
import subprocess
from unittest.mock import patch
from pytron.platforms.android.builder import AndroidBuilder


@pytest.fixture
def builder():
    return AndroidBuilder(arch="aarch64")


def test_fetch_prebuilt_wheel_method_success(builder, tmp_path):
    with patch("subprocess.check_call") as mock_call, patch(
        "os.listdir", return_value=["pkg-1.0-android_24_aarch64.whl"]
    ):

        assert builder._fetch_prebuilt_wheel("pkg", str(tmp_path)) is True

        # Check platform tags
        calls = mock_call.call_args_list
        # Should try at least one android tag
        assert any("android" in str(c) for c in calls)
        # Should use extra index
        assert any("beeware" in str(c) for c in calls)


def test_fetch_prebuilt_wheel_method_failure(builder, tmp_path):
    with patch(
        "subprocess.check_call", side_effect=subprocess.CalledProcessError(1, "cmd")
    ):
        assert builder._fetch_prebuilt_wheel("pkg", str(tmp_path)) is False


def test_build_wheel_uses_prebuilt(builder, tmp_path):
    package = "numpy"
    output_dir = str(tmp_path)

    # Mock _fetch_prebuilt_wheel to return True
    # Mock repair_wheel
    with patch.object(
        builder, "_fetch_prebuilt_wheel", return_value=True
    ) as mock_fetch, patch.object(builder, "repair_wheel") as mock_repair, patch(
        "os.listdir", return_value=["numpy.whl"]
    ):

        result = builder.build_wheel(package, output_dir)

        assert result is True
        mock_fetch.assert_called_with(package, output_dir)
        mock_repair.assert_called()

        # Ensure tools were NOT initialized (lazy loading)
        assert builder.zig_exe is None


def test_build_wheel_fallback_to_build(builder, tmp_path):
    package = "custom-pkg"
    output_dir = str(tmp_path)

    # Mock _fetch_prebuilt_wheel to return False
    # Mock _ensure_tools and the rest of the build process
    with patch.object(
        builder, "_fetch_prebuilt_wheel", return_value=False
    ) as mock_fetch, patch.object(builder, "_ensure_tools") as mock_ensure:

        # We expect it to fail because we didn't mock the full build process,
        # but we just want to verify it called _ensure_tools

        # Mock zig_exe to be None so it returns False early
        builder.zig_exe = None

        result = builder.build_wheel(package, output_dir)

        assert result is False
        mock_fetch.assert_called()
        mock_ensure.assert_called()
