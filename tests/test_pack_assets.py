import os
import pytest
from pathlib import Path
from pytron.pack.assets import get_smart_assets

def test_get_smart_assets_basic(tmp_path):
    # Setup a dummy project structure
    (tmp_path / "app.py").touch()
    (tmp_path / "settings.json").touch() # Should be excluded by EXCLUDE_FILES
    (tmp_path / "README.md").touch() # Should be excluded by EXCLUDE_SUFFIXES
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "image.png").touch()
    (tmp_path / "assets" / "data.txt").touch()
    
    assets = get_smart_assets(tmp_path)
    
    # Convert to list of source paths for easier checking
    src_paths = [a.split(os.pathsep)[0] for a in assets]
    
    # Check inclusions
    assert str(tmp_path / "assets" / "image.png") in src_paths
    assert str(tmp_path / "assets" / "data.txt") in src_paths
    
    # Check exclusions
    assert str(tmp_path / "app.py") not in src_paths
    assert str(tmp_path / "settings.json") not in src_paths
    assert str(tmp_path / "README.md") not in src_paths

def test_get_smart_assets_exclude_dirs(tmp_path):
    (tmp_path / "venv").mkdir()
    (tmp_path / "venv" / "lib.py").touch()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").touch()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "code.py").touch() # .py excluded
    (tmp_path / "src" / "resource.dat").touch() # included
    
    assets = get_smart_assets(tmp_path)
    src_paths = [a.split(os.pathsep)[0] for a in assets]
    
    assert str(tmp_path / "venv" / "lib.py") not in src_paths
    assert str(tmp_path / "node_modules" / "pkg.js") not in src_paths
    assert str(tmp_path / "src" / "resource.dat") in src_paths

def test_get_smart_assets_frontend_exclusion(tmp_path):
    frontend_dist = tmp_path / "frontend" / "dist"
    frontend_dist.mkdir(parents=True)
    (frontend_dist / "index.html").touch()
    
    # Pass frontend_dist to exclude it (it's handled separately in package.py)
    assets = get_smart_assets(tmp_path, frontend_dist=frontend_dist)
    src_paths = [a.split(os.pathsep)[0] for a in assets]
    
    assert str(frontend_dist / "index.html") not in src_paths
