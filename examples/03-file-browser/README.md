# Example 03: File Browser (Native APIs)

This example explores Pytron's native OS integration, specifically file system dialogs and system shell operations.

## Key Features

- **Native Folder Dialog**: Using `app.dialog_open_folder` to let users pick directories using the OS-native UI.
- **Python File System Access**: Using Python's `os` module to read directory contents safely.
- **System Shell Integration**: Using `Shell.open_external` to open files in their default system applications (Images in viewers, text in editors, etc.).

## How it works

1.  The user clicks "Browse", which triggers `app.dialog_open_folder` in the Python backend.
2.  Once a path is selected, Python's `os.scandir` is used to get details about all files and folders.
3.  The frontend renders these items. Clicking a folder navigates deeper, while clicking a file tells the OS to open it using the `Shell` utility.
