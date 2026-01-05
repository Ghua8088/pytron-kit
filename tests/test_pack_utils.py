import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from pytron.pack.utils import cleanup_dist

def test_cleanup_dist(tmp_path):
    dist_dir = tmp_path / "dist" / "MyApp"
    dist_dir.mkdir(parents=True)
    
    # Create files/dirs to be removed
    (dist_dir / "node_modules").mkdir()
    (dist_dir / "node.exe").touch()
    (dist_dir / "package.json").touch()
    (dist_dir / "debug.pdb").touch()
    
    # Create files to keep
    (dist_dir / "MyApp.exe").touch()
    (dist_dir / "python3.dll").touch()
    (dist_dir / "resources").mkdir()
    (dist_dir / "resources" / "data.txt").touch()
    
    cleanup_dist(dist_dir)
    
    assert not (dist_dir / "node_modules").exists()
    assert not (dist_dir / "node.exe").exists()
    assert not (dist_dir / "package.json").exists()
    assert not (dist_dir / "debug.pdb").exists()
    
    assert (dist_dir / "MyApp.exe").exists()
    assert (dist_dir / "python3.dll").exists()
    assert (dist_dir / "resources" / "data.txt").exists()

def test_cleanup_dist_macos_bundle(tmp_path):
    # Simulate macOS .app structure
    with patch("sys.platform", "darwin"):
        app_bundle = tmp_path / "dist" / "MyApp.app"
        app_bundle.mkdir(parents=True)
        
        (app_bundle / "node_modules").mkdir()
        (app_bundle / "MyApp").touch()
        
        # Pass the inner dist path as PyInstaller usually outputs
        # But cleanup_dist handles finding the .app parent
        dist_inner = tmp_path / "dist" / "MyApp" 
        # Note: In onedir mode on mac, it might be dist/MyApp.app/Contents/MacOS/MyApp
        # The function logic is: if sys.platform == "darwin": app_path = dist_path.parent / name.app
        # If we pass dist/MyApp, parent is dist, so dist/MyApp.app.
        
        # We need to ensure dist_inner exists for the function to proceed
        # But wait, the function checks if target_path exists.
        # If we pass dist/MyApp, and it doesn't exist, it might fail early if logic is strict.
        # But the logic is: target_path = dist_path.parent / name.app
        # So it checks MyApp.app existence.
        
        cleanup_dist(dist_inner)
        
        assert not (app_bundle / "node_modules").exists()
        assert (app_bundle / "MyApp").exists()
