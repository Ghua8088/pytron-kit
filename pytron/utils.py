import sys
import os

def get_resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller
    """
    # Check if absolute first
    if os.path.isabs(relative_path):
        return relative_path

    if getattr(sys, 'frozen', False):
        # PyInstaller: Check _MEIPASS first (internal)
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
            full_path = os.path.join(base_path, relative_path)
            if os.path.exists(full_path):
                return full_path
        
        # Fallback: Check executable directory (external/next to exe)
        # This is where 'pytron.ico' usually lives in one-dir builds
        base_path = os.path.dirname(sys.executable)
        return os.path.join(base_path, relative_path)
    else:
        # Dev Mode: Use current working directory or relative to this file?
        # Usually for user assets, CWD (where they ran the command) is best.
        # But for library assets, dirname is better.
        # Let's try CWD first for user convenience in finding 'pytron.ico'
        if os.path.exists(relative_path):
            return os.path.abspath(relative_path)
            
        base_path = os.path.dirname(__file__)
    
    return os.path.join(base_path, relative_path)
