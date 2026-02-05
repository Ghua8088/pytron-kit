import os
import shutil
import sys
import pytest
from pathlib import Path
from pytron.pack.modules import AssetModule
from pytron.pack.pipeline import BuildContext

class MockProgress:
    def add_task(self, name, total=100): return 0
    def update(self, *args, **kwargs): pass
    def start(self): pass
    def stop(self): pass

def test_asset_module_mandatory_resources(tmp_path):
    # Setup project structure
    script_dir = tmp_path / "project"
    script_dir.mkdir(parents=True, exist_ok=True)
    (script_dir / "app.py").touch()
    
    # Create resources folder
    resources_dir = script_dir / "resources"
    resources_dir.mkdir(parents=True, exist_ok=True)
    (resources_dir / "config.yaml").write_text("key: value")
    (resources_dir / "subdir").mkdir(parents=True, exist_ok=True)
    (resources_dir / "subdir" / "blob.dat").touch()
    
    # Create build dir
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    
    # Setup context
    ctx = BuildContext(
        script=script_dir / "app.py",
        out_name="test_app",
        app_icon=None,
        settings={},
        engine="chrome",
        is_secure=False,
        is_nuitka=False,
        is_onefile=True,
        progress=MockProgress(),
        task_id=0
    )
    ctx.build_dir = build_dir
    
    # Run AssetModule
    module = AssetModule()
    module.prepare(ctx)
    
    # Check if resources folder was added to add_data
    # Format: src_path + os.pathsep + dest_rel_path
    resource_entry = next((item for item in ctx.add_data if "resources" in item), None)
    
    assert resource_entry is not None
    src, dest = resource_entry.split(os.pathsep)
    assert os.path.exists(src)
    assert dest == "resources"
    assert "config.yaml" in os.listdir(src)

if __name__ == "__main__":
    # Manual run support
    try:
        from pytron.pack.pipeline import BuildModule # Check imports
        test_dir = Path("./tmp_test_res").resolve()
        if test_dir.exists():
            shutil.rmtree(test_dir)
        test_asset_module_mandatory_resources(test_dir)
        if test_dir.exists():
            shutil.rmtree(test_dir)
        print(" Asset Module Mandatory Resources Test Passed!")
    except Exception as e:
        print(f"Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
