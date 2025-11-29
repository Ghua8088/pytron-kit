UNIX/Windows Unicode support for pytron packaged apps
===============================================

Purpose
-------
This document explains how to make Pytron-packaged (PyInstaller) apps robust when printing or logging modern Unicode (CJK, emoji, astral-plane characters, etc.) on Windows and other platforms.

Core idea
---------
- Enable Python UTF-8 mode where possible (`PYTHONUTF8=1`).
- Force terminal / stdio wrappers to use UTF-8 with `errors='surrogatepass'` so undecodable bytes are preserved rather than causing exceptions.
- On Windows, attempt to set the console code page to UTF-8 (65001) at runtime.

Files
-----
- `runtime_hooks/set_unicode_runtime_hook.py` — runtime hook to include in your PyInstaller build. It sets `PYTHONUTF8`, attempts to set the Windows console CP to UTF-8, and replaces `sys.stdin/stdout/stderr` with UTF-8 wrappers.

How to include the runtime hook
------------------------------
- Command-line PyInstaller:

```powershell
pyinstaller --onefile --runtime-hook=d:/pytron/pytron-package/runtime_hooks/set_unicode_runtime_hook.py your_app.py
```

- In a `.spec` file (add or modify `runtime_hooks`):

```python
a = Analysis(...,
             runtime_hooks=['d:/pytron/pytron-package/runtime_hooks/set_unicode_runtime_hook.py'],
             ...)
```

PowerShell / Batch wrappers (recommended)
----------------------------------------
Using a small wrapper ensures environment is configured the same way when users double-click or run the exe.

PowerShell wrapper (`run.ps1`):

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
.\MyApp.exe
```

Windows batch wrapper (`run.bat`):

```bat
@echo off
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
MyApp.exe
```

Notes on encoding choices
-------------------------
- `utf-8` is the best single choice for modern Unicode support. There is no single "newer" encoding that replaces UTF-8 for Unicode; UTF-8 remains the de-facto standard.
- To avoid crashes when the underlying terminal or system cannot represent a character, the runtime hook uses `errors='surrogatepass'` for stdio wrappers. This preserves the byte sequences and lets your program handle or log them safely.

In-app defensive code (optional)
--------------------------------
If you prefer to change the application source instead of using runtime hooks, add at the very start of your main module (before any prints/logging):

```python
import sys
import io
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='surrogatepass')
    sys.stderr.reconfigure(encoding='utf-8', errors='surrogatepass')
except Exception:
    try:
        import io
        sys.stdout = io.TextIOWrapper(getattr(sys.stdout,'buffer',sys.stdout), encoding='utf-8', errors='surrogatepass', line_buffering=True)
        sys.stderr = io.TextIOWrapper(getattr(sys.stderr,'buffer',sys.stderr), encoding='utf-8', errors='surrogatepass', line_buffering=True)
    except Exception:
        pass
```

Testing and verification
------------------------
1. Build with the runtime hook.
2. Open PowerShell and run the wrapper (`run.ps1`) or set the env vars and run the exe.
3. Print or log a string containing CJK characters and emoji (e.g., `print('孙悟空 🐒')`).

If you still see encoding errors:
- Confirm the hook path is actually included in the built binary (`pyinstaller` log shows runtime hooks loaded).
- Try running the exe from PowerShell and from cmd.exe to compare behavior.
- As a last resort, you can catch encoding errors in your logging/print points and encode with `errors='replace'`.

Advanced: fonts and console support
----------------------------------
Even if your app prints UTF-8 bytes correctly, the console font must support the glyphs. Windows' default raster fonts may not display emoji or some CJK glyphs; recommend using modern fonts (e.g., "Consolas", "Cascadia Code", or an appropriate CJK-capable font) in the terminal.

If you want, I can:
- Add the runtime hook to specific apps in this repo (patch the `.spec` files), or
- Patch a sample entrypoint to call `reconfigure` directly.
