import subprocess
import os
import shutil
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
            kdialog = shutil.which("kdialog") or "kdialog"
            args = [kdialog, "--title", title]
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
        ns = shutil.which("notify-send") or "notify-send"
        subprocess.Popen([ns, title, message])  # nosec B603
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

        output = subprocess.check_output(cmd, text=True).strip()  # nosec B603
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

        output = subprocess.check_output(cmd, text=True).strip()  # nosec B603
        return output
    except Exception:
        pass

    print("Pytron Warning: No file dialog provider (zenity/kdialog) found on Linux.")
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
    except Exception as e:
        print(f"[Pytron] Debug: Failed to set app name: {e}")


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


def register_protocol(scheme):
    try:
        import sys

        # Get absolute path to this executable or script
        exe_path = os.path.abspath(sys.executable)
        if not getattr(sys, "frozen", False):
            # If running as script, we need the script path too
            main_script = sys.modules["__main__"].__file__
            exe_path = f'"{exe_path}" "{os.path.abspath(main_script)}"'
        else:
            exe_path = f'"{exe_path}"'

        # Local desktop file name based on scheme
        desktop_filename = f"pytron-handler-{scheme}.desktop"
        apps_dir = os.path.expanduser("~/.local/share/applications")
        os.makedirs(apps_dir, exist_ok=True)
        desktop_path = os.path.join(apps_dir, desktop_filename)

        content = f"""[Desktop Entry]
Type=Application
Name=Pytron {scheme.capitalize()} Handler
Exec={exe_path} %u
MimeType=x-scheme-handler/{scheme};
NoDisplay=true
Terminal=false
"""
        with open(desktop_path, "w") as f:
            f.write(content)

        # Update mime database and register
        try:
            udd = shutil.which("update-desktop-database") or "update-desktop-database"
            subprocess.run([udd, apps_dir], capture_output=True)  # nosec B603

            xm = shutil.which("xdg-mime") or "xdg-mime"
            subprocess.run(
                [xm, "default", desktop_filename, f"x-scheme-handler/{scheme}"],
                capture_output=True,
            )  # nosec B603
            return True
        except Exception:
            # Fallback if tools are missing
            return os.path.exists(desktop_path)
    except Exception as e:
        print(f"[Pytron] Failed to register protocol on Linux: {e}")
        return False


# -------------------------------------------------------------------------
# Native Drag & Drop Support (Linux/GTK3)
# -------------------------------------------------------------------------
_drag_callbacks = {}  # Keep references alive


def enable_drag_drop(w, callback):
    """
    Connects to the 'drag-data-received' signal on the GtkWindow/GtkWidget.
    """
    if not libs.gtk or not libs.glib:
        print("[Pytron] GTK/GLib not found, cannot enable drag & drop.")
        return

    # We need dragging constants

    # Define Target Entry
    # drag_dest_set expects an array of GtkTargetEntry
    # But usually webview already accepts drags (for the browser).
    # We might just need to connect the signal!

    # Let's try just connecting the signal first.

    # Callback Sig: void user_function (GtkWidget *widget, GdkDragContext *context, gint x, gint y, GtkSelectionData *data, guint info, guint time, gpointer user_data)
    CALLBACK_TYPE = ctypes.CFUNCTYPE(
        None,
        ctypes.c_void_p,  # widget
        ctypes.c_void_p,  # context
        ctypes.c_int,  # x
        ctypes.c_int,  # y
        ctypes.c_void_p,  # data (GtkSelectionData*)
        ctypes.c_uint,  # info
        ctypes.c_uint,  # time
        ctypes.c_void_p,  # user_data
    )

    def on_drag_data_received(widget, context, x, y, data, info, time, user_data):
        try:
            # gtk_selection_data_get_uris (data) -> gchar**
            libs.gtk.gtk_selection_data_get_uris.restype = ctypes.POINTER(
                ctypes.c_char_p
            )
            libs.gtk.gtk_selection_data_get_uris.argtypes = [ctypes.c_void_p]

            uris_ptr = libs.gtk.gtk_selection_data_get_uris(data)
            files = []

            if uris_ptr:
                # Iterate null-terminated array
                i = 0
                while uris_ptr[i]:
                    uri_str = uris_ptr[i].decode("utf-8")
                    # Convert file:// URI to path
                    if uri_str.startswith("file://"):
                        # Basic unquoting (replace %20 with space, etc)
                        import urllib.parse

                        path = urllib.parse.unquote(uri_str.replace("file://", ""))
                        # Sanitize line endings
                        files.append(path.strip())
                    else:
                        files.append(uri_str)
                    i += 1

                # Free strings? GTK owns them usually in this context or we need to free the array?
                # g_strfreev(uris_ptr) usually.
                if libs.glib and hasattr(libs.glib, "g_strfreev"):
                    libs.glib.g_strfreev(uris_ptr)

            if files:
                callback(files)

            # Finish drag
            libs.gtk.gtk_drag_finish(context, True, False, time)
        except Exception as e:
            print(f"[Pytron] Linux DragDrop Error: {e}")
            libs.gtk.gtk_drag_finish(context, False, False, time)

    c_callback = CALLBACK_TYPE(on_drag_data_received)

    # Keep alive
    _drag_callbacks[w] = c_callback

    # Function sig: gulong g_signal_connect_data (gpointer instance, const gchar *detailed_signal, GCallback c_handler, gpointer data, GClosureNotify destroy_data, GConnectFlags connect_flags)
    libs.glib.g_signal_connect_data.restype = ctypes.c_ulong
    libs.glib.g_signal_connect_data.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        CALLBACK_TYPE,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
    ]

    libs.glib.g_signal_connect_data(
        ctypes.c_void_p(w),
        "drag-data-received".encode("utf-8"),
        c_callback,
        None,
        None,
        0,
    )

    # Also ensure it is a drop destination
    # gtk_drag_dest_set (widget, GTK_DEST_DEFAULT_ALL, NULL, 0, GDK_ACTION_COPY)
    # Actually, we should probably add URI targets. This is verbose in ctypes.
    # Assuming WebKit view already sets some drop targets.
