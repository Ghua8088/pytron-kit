import subprocess
import os
import ctypes
from . import libs

def message_box(w, title, message, style=0):
    # Styles: 0=OK, 1=OK/cancel, 4=Yes/No
    # Return: 1=OK, 2=Cancel, 6=Yes, 7=No

    try:
        # TRY ZENITY (Common on GNOME/Ubuntu)
        args = ["zenity", "--title=" + title, "--text=" + message]
        if style == 4:
            args.append("--question")
        elif style == 1:  # OK/Cancel treated as Question for Zenity roughly
            args.append("--question")
        else:
            args.append("--info")

        subprocess.check_call(args)
        return 6 if style == 4 else 1  # Success (Yes or OK)
    except subprocess.CalledProcessError:
        return 7 if style == 4 else 2  # Failure/Cancel (No or Cancel)
    except FileNotFoundError:
        # TRY KDIALOG (KDE)
        try:
            args = ["kdialog", "--title", title]
            if style == 4:
                args += ["--yesno", message]
            else:
                args += ["--msgbox", message]

            subprocess.check_call(args)
            return 6 if style == 4 else 1
        except Exception:
            # If neither, just allow it (dev env probably?) or log warning
            print("Pytron Warning: No dialog tool (zenity/kdialog) found.")
            return 0

def notification(w, title, message, icon=None):
    # Try notify-send
    try:
        subprocess.Popen(["notify-send", title, message])
    except Exception:
        print("Pytron Warning: notify-send not found.")

def _run_subprocess_dialog(title, action, default_path, default_name):
    # Action: 0=Open, 1=Save, 2=Folder
    
    # Try ZENITY
    try:
        cmd = ["zenity", "--file-selection", "--title=" + title]

        if action == 1:
            cmd.append("--save")
            cmd.append("--confirm-overwrite")
        elif action == 2:
            cmd.append("--directory")

        if default_path:
            path = default_path
            if action == 1 and default_name:
                path = os.path.join(path, default_name)
            cmd.append(f"--filename={path}")

        output = subprocess.check_output(cmd, text=True).strip()
        return output
    except Exception:
        pass

    # Try KDIALOG
    try:
        cmd = ["kdialog", "--title", title]
        if action == 0:
            cmd += ["--getopenfilename"]
        elif action == 1:
            cmd += ["--getsavefilename"]
        elif action == 2:
            cmd += ["--getexistingdirectory"]

        start_dir = default_path or "."
        if action == 1 and default_name:
            start_dir = os.path.join(start_dir, default_name)
        cmd.append(start_dir)

        output = subprocess.check_output(cmd, text=True).strip()
        return output
    except Exception:
        pass

    print(
        "Pytron Warning: No file dialog provider (zenity/kdialog) found on Linux."
    )
    return None

def open_file_dialog(w, title, default_path=None, file_types=None):
    return _run_subprocess_dialog(title, 0, default_path, None)

def save_file_dialog(w, title, default_path=None, default_name=None, file_types=None):
    return _run_subprocess_dialog(title, 1, default_path, default_name)

def open_folder_dialog(w, title, default_path=None):
    return _run_subprocess_dialog(title, 2, default_path, None)

def set_app_id(app_id):
    if not libs.glib:
        return
    try:
        libs.glib.g_set_prgname.argtypes = [ctypes.c_char_p]
        libs.glib.g_set_prgname(app_id.encode("utf-8"))
        libs.glib.g_set_application_name.argtypes = [ctypes.c_char_p]
        libs.glib.g_set_application_name(app_id.encode("utf-8"))
    except Exception:
        pass

def set_launch_on_boot(app_name, exe_path, enable=True):
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    autostart_dir = os.path.join(config_home, "autostart")
    desktop_file = os.path.join(autostart_dir, f"{app_name}.desktop")

    if enable:
        try:
            os.makedirs(autostart_dir, exist_ok=True)
            content = f"""[Desktop Entry]
Type=Application
Name={app_name}
Exec={exe_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""
            with open(desktop_file, "w") as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"[Pytron] Failed to enable autostart on Linux: {e}")
            return False
    else:
        try:
            if os.path.exists(desktop_file):
                os.remove(desktop_file)
            return True
        except Exception as e:
            print(f"[Pytron] Failed to disable autostart on Linux: {e}")
            return False

def set_taskbar_progress(w, state="normal", value=0, max_value=100):
    pass
