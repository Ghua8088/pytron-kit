import subprocess
import os
import ctypes
from . import libs
from .utils import get_class, str_to_nsstring

def message_box(w, title, message, style=0):
    # Use osascript for native-look dialogs
    script = ""
    if style == 4:
        script = f'display alert "{title}" message "{message}" buttons {{"No", "Yes"}} default button "Yes"'
    elif style == 1:
        script = f'display alert "{title}" message "{message}" buttons {{"Cancel", "OK"}} default button "OK"'
    else:
        script = f'display alert "{title}" message "{message}" buttons {{"OK"}} default button "OK"'

    try:
        output = subprocess.check_output(["osascript", "-e", script], text=True)
        if "Yes" in output or "OK" in output:
            return 6 if style == 4 else 1
        return 7 if style == 4 else 2
    except subprocess.CalledProcessError:
        return 7 if style == 4 else 2
    except Exception:
        return 6

def notification(w, title, message, icon=None):
    script = f'display notification "{message}" with title "{title}"'
    try:
        subprocess.Popen(["osascript", "-e", script])
    except Exception:
        pass

def _run_osascript_dialog(script):
    try:
        proc = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
        return None
    except Exception:
        return None

def open_file_dialog(w, title, default_path=None, file_types=None):
    script = f'POSIX path of (choose file with prompt "{title}"'
    if default_path:
        script += f' default location "{default_path}"'
    script += ")"
    return _run_osascript_dialog(script)

def save_file_dialog(w, title, default_path=None, default_name=None, file_types=None):
    script = f'POSIX path of (choose file name with prompt "{title}"'
    if default_path:
        script += f' default location "{default_path}"'
    if default_name:
        script += f' default name "{default_name}"'
    script += ")"
    return _run_osascript_dialog(script)

def open_folder_dialog(w, title, default_path=None):
    script = f'POSIX path of (choose folder with prompt "{title}"'
    if default_path:
        script += f' default location "{default_path}"'
    script += ")"
    return _run_osascript_dialog(script)

def set_app_id(app_id):
    if not libs.objc:
        return
    try:
        cls_proc = get_class("NSProcessInfo")
        sel_info = libs.objc.sel_registerName("processInfo".encode("utf-8"))
        proc_info = libs.objc.objc_msgSend(cls_proc, sel_info)
        sel_set_name = libs.objc.sel_registerName("setProcessName:".encode("utf-8"))

        name_str = str_to_nsstring(app_id)
        f_set = ctypes.CFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        )(libs.objc.objc_msgSend)
        f_set(proc_info, sel_set_name, name_str)
    except Exception:
        pass

def set_launch_on_boot(app_name, exe_path, enable=True):
    import shlex

    home = os.path.expanduser("~")
    launch_agents = os.path.join(home, "Library/LaunchAgents")
    plist_file = os.path.join(
        launch_agents, f"com.{app_name.lower()}.startup.plist"
    )

    if enable:
        try:
            os.makedirs(launch_agents, exist_ok=True)
            args = shlex.split(exe_path)
            array_str = "\n".join([f"    <string>{a}</string>" for a in args])
            content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.{app_name.lower()}.startup</string>
    <key>ProgramArguments</key>
    <array>
{array_str}
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
            with open(plist_file, "w") as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"[Pytron] Failed to enable launch agent on macOS: {e}")
            return False
    else:
        try:
            if os.path.exists(plist_file):
                os.remove(plist_file)
            return True
        except Exception as e:
            print(f"[Pytron] Failed to disable launch agent on macOS: {e}")
            return False

def set_taskbar_progress(w, state="normal", value=0, max_value=100):
    if not libs.objc:
        return
    try:
        cls_app = get_class("NSApplication")
        sel_shared = libs.objc.sel_registerName("sharedApplication".encode("utf-8"))
        ns_app = libs.objc.objc_msgSend(cls_app, sel_shared)

        sel_dock = libs.objc.sel_registerName("dockTile".encode("utf-8"))
        f_dock = ctypes.CFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        )(libs.objc.objc_msgSend)
        dock_tile = f_dock(ns_app, sel_dock)

        sel_set_badge = libs.objc.sel_registerName("setBadgeLabel:".encode("utf-8"))
        f_set = ctypes.CFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        )(libs.objc.objc_msgSend)

        badge_text = None
        if state in ("normal", "error", "paused") and max_value > 0:
            pct = int((value / max_value) * 100)
            badge_text = str_to_nsstring(f"{pct}%")
        elif state == "indeterminate":
            badge_text = str_to_nsstring("...")

        f_set(dock_tile, sel_set_badge, badge_text)

        sel_display = libs.objc.sel_registerName("display".encode("utf-8"))
        libs.objc.objc_msgSend(dock_tile, sel_display)

    except Exception:
        pass
