import os
from pytron import App
from pytron.apputils.shell import Shell

app = App()

@app.expose
def select_directory():
    """Opens a native folder selection dialog."""
    path = app.dialog_open_folder("Select a directory to browse")
    return path

@app.expose
def list_contents(path: str):
    """Lists files and directories in the given path."""
    if not path or not os.path.exists(path):
        return {"error": "Invalid path"}
    
    try:
        items = []
        for entry in os.scandir(path):
            items.append({
                "name": entry.name,
                "path": entry.path,
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else 0
            })
        # Sort: directories first, then files
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return items
    except Exception as e:
        return {"error": str(e)}

@app.expose
def open_path(path: str):
    """Opens a file or folder using the system's default application."""
    Shell.open_external(path)

if __name__ == "__main__":
    app.run()
