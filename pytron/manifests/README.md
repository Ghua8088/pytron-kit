# Windows UTF-8 Manifest (process opt-in)

This folder contains a process manifest that opts an application into Windows' "UTF-8 for worldwide language support" (the UTF-8 code page) for the C runtime.

- File: `windows-utf8.manifest`

Usage (PyInstaller .spec):

Add the manifest to the `EXE()` call in your `.spec` file, for example:

```python
exe = EXE(
    pyz,
    ...,
    manifest='pytron/manifests/windows-utf8.manifest',
    ...
)
```

Notes:
- The manifest adds the `<UseUnicodeUTF8>true</UseUnicodeUTF8>` setting for the process. This asks the Microsoft C runtime to treat the ANSI code page as UTF-8 for narrow-character (`char`/`printf`/`fopen`-style) APIs.
- Behavior depends on OS and CRT version. Test your application on target Windows versions.
- If you embed the manifest with other tools (e.g. `mt.exe`, `rcedit`, or build systems), pass the manifest as the application's resource/manifest.

If you want, I can also update `pytron` packaging helpers to automatically include this manifest when building Windows executables.
