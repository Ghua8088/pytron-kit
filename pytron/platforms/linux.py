import ctypes
from ..bindings import lib
from .interface import PlatformInterface

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

