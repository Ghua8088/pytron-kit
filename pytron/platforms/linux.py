import ctypes
from ..bindings import lib
from .interface import PlatformInterface
import os
class LinuxImplementation(PlatformInterface):
    def __init__(self):
        try:
            self.gtk = ctypes.CDLL("libgtk-3.so.0")
        except OSError:
            try:
                self.gtk = ctypes.CDLL("libgtk-3.so")
            except OSError:
                 # Fallback or silent failure if GTK not present
                 print("Pytron Warning: GTK3 not found. Window controls may fail.")
                 self.gtk = None

    def _get_window(self, w):
        return lib.webview_get_window(w)

    def minimize(self, w):
        if not self.gtk: return
        win = self._get_window(w)
        self.gtk.gtk_window_iconify(win)

    def set_bounds(self, w, x, y, width, height):
        if not self.gtk: return
        win = self._get_window(w)
        self.gtk.gtk_window_move(win, int(x), int(y))
        self.gtk.gtk_window_resize(win, int(width), int(height))

    def close(self, w):
        if not self.gtk: return
        win = self._get_window(w)
        self.gtk.gtk_window_close(win)

    def toggle_maximize(self, w):
        if not self.gtk: return False
        win = self._get_window(w)
        is_maximized = self.gtk.gtk_window_is_maximized(win)
        if is_maximized:
            self.gtk.gtk_window_unmaximize(win)
            return False
        else:
            self.gtk.gtk_window_maximize(win)
            return True

    def make_frameless(self, w):
        if not self.gtk: return
        win = self._get_window(w)
        self.gtk.gtk_window_set_decorated(win, 0) # FALSE

    def start_drag(self, w):
        if not self.gtk: return
        win = self._get_window(w)
        # 1 = GDK_BUTTON_PRIMARY_MASK (approx), sometimes 0 works for timestamps
        self.gtk.gtk_window_begin_move_drag(win, 1, 0, 0)

    def message_box(self, w, title, message, style=0):
        # Fallback to subprocess for reliability (zenity/kdialog/notify-send)
        import subprocess
        # Styles: 0=OK, 1=OK/cancel, 4=Yes/No
        # Return: 1=OK, 2=Cancel, 6=Yes, 7=No
        
        try:
            # TRY ZENITY (Common on GNOME/Ubuntu)
            args = ["zenity", "--title=" + title, "--text=" + message]
            if style == 4:
                args.append("--question")
            elif style == 1: # OK/Cancel treated as Question for Zenity roughly
                args.append("--question") 
            else:
                args.append("--info")
            
            subprocess.check_call(args)
            return 6 if style == 4 else 1 # Success (Yes or OK)
        except subprocess.CalledProcessError:
            return 7 if style == 4 else 2 # Failure/Cancel (No or Cancel)
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
    # ... (existing methods)

    def register_pytron_scheme(self, w, root_path):
        """
        Attempts to force file access on Linux WebKit2.
        """
        # We now use ctypes directly, no need for PyGObject imports here
        self._register_scheme_ctypes(w, root_path)

    def _register_scheme_ctypes(self, w, root_path):
        """
        Uses ctypes to call webkit_web_context_register_uri_scheme.
        """
        if not self.gtk:
            return

        win_ptr = self._get_window(w)

        try:
            # Get the direct child of the GtkWindow (which is a GtkBin)
            self.gtk.gtk_bin_get_child.argtypes = [ctypes.c_void_p]
            self.gtk.gtk_bin_get_child.restype = ctypes.c_void_p

            child = self.gtk.gtk_bin_get_child(win_ptr)
            if not child:
                print("[Pytron] Could not find child widget in GtkWindow.")
                return

            # Load WebKit2GTK lib (try 4.1 then 4.0)
            libwebkit = None
            try:
                libwebkit = ctypes.CDLL("libwebkit2gtk-4.1.so.0")
            except OSError:
                try:
                    libwebkit = ctypes.CDLL("libwebkit2gtk-4.0.so.37")
                except OSError:
                    print("[Pytron] Could not find libwebkit2gtk shared library.")
                    return

            # Prepare WebKit functions
            libwebkit.webkit_web_view_get_settings.argtypes = [ctypes.c_void_p]
            libwebkit.webkit_web_view_get_settings.restype = ctypes.c_void_p

            libwebkit.webkit_settings_set_allow_file_access_from_file_urls.argtypes = [ctypes.c_void_p, ctypes.c_int]
            libwebkit.webkit_settings_set_allow_universal_access_from_file_urls.argtypes = [ctypes.c_void_p, ctypes.c_int]

            settings = libwebkit.webkit_web_view_get_settings(child)
            if settings:
                print(f"[Pytron] Found WebKitSettings at {settings}, enabling file access.")
                libwebkit.webkit_settings_set_allow_file_access_from_file_urls(settings, 1)
                libwebkit.webkit_settings_set_allow_universal_access_from_file_urls(settings, 1)
                return

            print("[Pytron] Direct child was not a WebView; deep traversal skipped to avoid GTK warnings.")

        except Exception as e:
            print(f"[Pytron] Error ensuring file access on Linux: {e}")

    # --- Daemon Capabilities ---
    def hide(self, w):
        if not self.gtk: return
        win = self._get_window(w)
        # gtk_widget_hide
        self.gtk.gtk_widget_hide(win)

    def show(self, w):
        if not self.gtk: return
        win = self._get_window(w)
        # gtk_widget_show_all
        self.gtk.gtk_widget_show_all(win)
        # gtk_window_present to bring to front
        self.gtk.gtk_window_present(win)

    def notification(self, w, title, message, icon=None):
        import subprocess
        # Try notify-send
        try:
            subprocess.Popen(['notify-send', title, message])
        except Exception:
             print("Pytron Warning: notify-send not found.")

    
    # --- File Dialogs Support ---
    def _run_gtk_dialog(self, w, title, action, default_path, default_name):
        if not self.gtk: return None
        
        # Actions: 0=OPEN, 1=SAVE, 2=SELECT_FOLDER, 3=CREATE_FOLDER
        # Buttons: "Cancel" -> GTK_RESPONSE_CANCEL (-6), "Open"/"Save" -> GTK_RESPONSE_ACCEPT (-3)
        
        win = self._get_window(w)
        
        # Labels
        accept_label = "Save" if action == 1 else "Open"
        
        # gtk_file_chooser_dialog_new(title, parent, action, first_button_text, first_button_id, ..., NULL)
        # Using varargs in ctypes is tricky.
        # Alternative: Create dialog, then add buttons.
        # But 'new' is varargs.
        # Fallback: create typical dialog window or use `zenity`?
        # Trying `zenity` first as it's robust for 'simple' setups without complex ctypes varargs.
        # Actually, let's just use zenity/kdialog for Linux file dialogs to act 'native' to the DE
        # (KDE uses kdialog, Gnome uses zenity). Using GTK dialog inside a potentially non-GTK DE is less ideal.
        # AND it avoids complex ctypes definitions for all the GtkFileChooser methods.
        return self._run_subprocess_dialog(title, action, default_path, default_name)

    def _run_subprocess_dialog(self, title, action, default_path, default_name):
        # Action: 0=Open, 1=Save, 2=Folder
        import subprocess
        import os
        
        # Try ZENITY
        try:
            cmd = ["zenity", "--file-selection", "--title=" + title]
            
            if action == 1:
                cmd.append("--save")
                cmd.append("--confirm-overwrite")
            elif action == 2:
                cmd.append("--directory")
                
            if default_path:
                # If save and default_name exists, append it
                path = default_path
                if action == 1 and default_name:
                    path = os.path.join(path, default_name)
                cmd.append(f"--filename={path}")
                
            # Filters? Zenity supports --file-filter="Name | *.ext"
            # But we passed `file_types` to the public calls, need to handle that.
            # Simplified for now.
            
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
                
             # KDialog path argument
            start_dir = default_path or "."
            if action == 1 and default_name:
                start_dir = os.path.join(start_dir, default_name)
            cmd.append(start_dir)

            output = subprocess.check_output(cmd, text=True).strip()
            return output
        except Exception:
            pass
        
        print("Pytron Warning: No file dialog provider (zenity/kdialog) found on Linux.")
        return None

    def open_file_dialog(self, w, title, default_path=None, file_types=None):
        return self._run_subprocess_dialog(title, 0, default_path, None)

    def save_file_dialog(self, w, title, default_path=None, default_name=None, file_types=None):
        return self._run_subprocess_dialog(title, 1, default_path, default_name)

    def open_folder_dialog(self, w, title, default_path=None):
        return self._run_subprocess_dialog(title, 2, default_path, None)

    # --- Taskbar Progress ---
    def set_taskbar_progress(self, w, state="normal", value=0, max_value=100):
        # Linux DEs (Gnome/KDE) don't have a standardized Taskbar Progress API.
        # Ubuntu Unity used to have a Launcher API. 
        # Modern Gnome Shell might have extensions.
        # For now, we no-op to prevent crashes.
        pass

    def set_window_icon(self, w, icon_path):
        if not self.gtk or not icon_path: return
        win = self._get_window(w)
        err = ctypes.c_void_p(0)
        # gtk_window_set_icon_from_file(GtkWindow *window, const gchar *filename, GError **err);
        res = self.gtk.gtk_window_set_icon_from_file(win, icon_path.encode('utf-8'), ctypes.byref(err))
        if not res:
             print(f"[Pytron] Failed to set window icon from {icon_path}")

    def set_app_id(self, app_id):
        try:
            glib = ctypes.CDLL("libglib-2.0.so.0")
            glib.g_set_prgname.argtypes = [ctypes.c_char_p]
            glib.g_set_prgname(app_id.encode('utf-8'))
            # Also g_set_application_name often used by GTK
            glib.g_set_application_name.argtypes = [ctypes.c_char_p]
            glib.g_set_application_name(app_id.encode('utf-8'))
        except Exception:
            pass

    def set_launch_on_boot(self, app_name, exe_path, enable=True):
        import os
        
        # XDG Autostart
        config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        autostart_dir = os.path.join(config_home, 'autostart')
        desktop_file = os.path.join(autostart_dir, f"{app_name}.desktop")
        
        if enable:
            try:
                os.makedirs(autostart_dir, exist_ok=True)
                
                # Check if we need to run python explicitly if not frozen (Linux usually needs shebang/env)
                # But implementation in App.py passes full command string if needed.
                # However, .desktop Exec key doesn't like complex quoting sometimes.
                # Let's write what we got.
                
                content = f"""[Desktop Entry]
Type=Application
Name={app_name}
Exec={exe_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""
                with open(desktop_file, 'w') as f:
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

