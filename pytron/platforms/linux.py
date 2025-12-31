import ctypes
from ..bindings import lib
from .interface import PlatformInterface
import os
import sys


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

        # Try to load WebKit for scheme registration
        self.libwebkit = None
        try:
            self.libwebkit = ctypes.CDLL("libwebkit2gtk-4.1.so.0")
        except OSError:
            try:
                self.libwebkit = ctypes.CDLL("libwebkit2gtk-4.0.so.37")
            except OSError:
                pass

        # Keep global references to prevent GC of callbacks
        self._scheme_callbacks = []
        self._gio = None

    def _get_window(self, w):
        return lib.webview_get_window(w)

    def _get_child_webview(self, win_ptr):
        if not self.gtk:
            return None
        self.gtk.gtk_bin_get_child.argtypes = [ctypes.c_void_p]
        self.gtk.gtk_bin_get_child.restype = ctypes.c_void_p
        return self.gtk.gtk_bin_get_child(win_ptr)

    def minimize(self, w):
        if not self.gtk:
            return
        win = self._get_window(w)
        self.gtk.gtk_window_iconify(win)

    def set_bounds(self, w, x, y, width, height):
        if not self.gtk:
            return
        win = self._get_window(w)
        self.gtk.gtk_window_move(win, int(x), int(y))
        self.gtk.gtk_window_resize(win, int(width), int(height))

    def close(self, w):
        if not self.gtk:
            return
        win = self._get_window(w)
        self.gtk.gtk_window_close(win)

    def toggle_maximize(self, w):
        if not self.gtk:
            return False
        win = self._get_window(w)
        is_maximized = self.gtk.gtk_window_is_maximized(win)
        if is_maximized:
            self.gtk.gtk_window_unmaximize(win)
            return False
        else:
            self.gtk.gtk_window_maximize(win)
            return True

    def make_frameless(self, w):
        if not self.gtk:
            return
        win = self._get_window(w)
        self.gtk.gtk_window_set_decorated(win, 0)  # FALSE

    def start_drag(self, w):
        if not self.gtk:
            return
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

    def register_pytron_scheme(self, w, callback):
        """
        Registers 'pytron://' custom scheme on Linux WebKit2.

        callback(url) -> (data, mime_type)
        """
        if not self.libwebkit or not self.gtk:
            print("[Pytron] Cannot register scheme: WebKitGTK not found.")
            return

        # Load GLib/Gio for stream creation
        try:
            if not self._gio:
                self._gio = ctypes.CDLL("libgio-2.0.so.0")
        except OSError:
            pass

        if not self._gio:
            print("[Pytron] Cannot register scheme: libgio not found.")
            return

        win_ptr = self._get_window(w)
        child = self._get_child_webview(win_ptr)
        if not child:
            print("[Pytron] Could not find WebView widget for scheme registration.")
            return

        # 1. Enable File Access (Always good to have)
        try:
            self.libwebkit.webkit_web_view_get_settings.restype = ctypes.c_void_p
            settings = self.libwebkit.webkit_web_view_get_settings(child)
            if settings:
                self.libwebkit.webkit_settings_set_allow_file_access_from_file_urls(
                    settings, 1
                )
                self.libwebkit.webkit_settings_set_allow_universal_access_from_file_urls(
                    settings, 1
                )
        except Exception:
            pass

        # 2. Register Scheme
        try:
            # context = webkit_web_view_get_context(webview)
            self.libwebkit.webkit_web_view_get_context.argtypes = [ctypes.c_void_p]
            self.libwebkit.webkit_web_view_get_context.restype = ctypes.c_void_p
            ctx = self.libwebkit.webkit_web_view_get_context(child)

            if not ctx:
                print("[Pytron] Could not get WebContext.")
                return

            # Callback Definition
            # void (*WebKitURISchemeRequestCallback) (WebKitURISchemeRequest *request, gpointer user_data)
            URISchemeCallback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)

            def scheme_handler(request, user_data):
                try:
                    # Get URI
                    self.libwebkit.webkit_uri_scheme_request_get_uri.argtypes = [
                        ctypes.c_void_p
                    ]
                    self.libwebkit.webkit_uri_scheme_request_get_uri.restype = (
                        ctypes.c_char_p
                    )
                    uri_bytes = self.libwebkit.webkit_uri_scheme_request_get_uri(
                        request
                    )
                    uri = uri_bytes.decode("utf-8") if uri_bytes else ""

                    if uri.startswith("pytron://"):
                        data, mime = callback(uri)
                        if data:
                            # Create Memory Stream
                            # GInputStream * g_memory_input_stream_new_from_data (const void *data, gssize len, GDestroyNotify destroy);
                            # We copy data because python bytes might be GC'd?
                            # `g_memory_input_stream_new_from_data` doesn't copy by default, it expects data to persist.
                            # Usage of `g_memory_input_stream_new_from_bytes` is safer but requires GBytes.
                            # Let's use `g_memory_input_stream_add_data`.

                            # Simple approach: g_memory_input_stream_new() + add_data
                            self._gio.g_memory_input_stream_new.restype = (
                                ctypes.c_void_p
                            )
                            stream = self._gio.g_memory_input_stream_new()

                            self._gio.g_memory_input_stream_add_data.argtypes = [
                                ctypes.c_void_p,
                                ctypes.c_void_p,
                                ctypes.c_longlong,
                                ctypes.c_void_p,
                            ]
                            # Copy data to C buffer
                            c_data = ctypes.create_string_buffer(data, len(data))
                            # Note: This c_data must ideally persist until stream is read?
                            # Actually `add_data` documentation says "copies the data".
                            # Wait, "Note that the data is mocked (copied)..." depends on version.
                            # "Append data to stream... The data is copied." - Yes.

                            self._gio.g_memory_input_stream_add_data(
                                stream, c_data, len(data), None
                            )

                            # Finish Request
                            # webkit_uri_scheme_request_finish (req, stream, length, mime)
                            self.libwebkit.webkit_uri_scheme_request_finish.argtypes = [
                                ctypes.c_void_p,
                                ctypes.c_void_p,
                                ctypes.c_longlong,
                                ctypes.c_char_p,
                            ]
                            self.libwebkit.webkit_uri_scheme_request_finish(
                                request, stream, len(data), mime.encode("utf-8")
                            )

                            # Unref stream (webkit takes ownership? Docs say "The stream is not closed", but ownership transfer?)
                            # Actually `webkit_uri_scheme_request_finish` docs: "The stream will be read...".
                            # Usually we should unref our reference.
                            self._gio.g_object_unref(stream)
                            return

                    # Not found or error
                    # webkit_uri_scheme_request_finish_error (req, GError *error)
                    # For simplicity, we just finish with empty stream or generic error
                    # But proper way involves GError. We skip for brevity.

                except Exception as e:
                    print(f"Scheme Error: {e}")

            c_callback = URISchemeCallback(scheme_handler)
            self._scheme_callbacks.append(c_callback)  # Keep alive

            # void webkit_web_context_register_uri_scheme (WebKitWebContext *context, const gchar *scheme, WebKitURISchemeRequestCallback callback, gpointer user_data, GDestroyNotify user_data_destroy_func)
            self.libwebkit.webkit_web_context_register_uri_scheme.argtypes = [
                ctypes.c_void_p,
                ctypes.c_char_p,
                URISchemeCallback,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]

            self.libwebkit.webkit_web_context_register_uri_scheme(
                ctx, "pytron".encode("utf-8"), c_callback, None, None
            )
            print("[Pytron] Registered Linux scheme handler for pytron://")

        except Exception as e:
            print(f"[Pytron] Failed to register Linux scheme: {e}")

    # --- Daemon Capabilities ---
    def hide(self, w):
        if not self.gtk:
            return
        win = self._get_window(w)
        self.gtk.gtk_widget_hide(win)

    def show(self, w):
        if not self.gtk:
            return
        win = self._get_window(w)
        self.gtk.gtk_widget_show_all(win)
        self.gtk.gtk_window_present(win)

    def notification(self, w, title, message, icon=None):
        import subprocess

        # Try notify-send
        try:
            subprocess.Popen(["notify-send", title, message])
        except Exception:
            print("Pytron Warning: notify-send not found.")

    # --- File Dialogs Support ---
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

    def open_file_dialog(self, w, title, default_path=None, file_types=None):
        return self._run_subprocess_dialog(title, 0, default_path, None)

    def save_file_dialog(
        self, w, title, default_path=None, default_name=None, file_types=None
    ):
        return self._run_subprocess_dialog(title, 1, default_path, default_name)

    def open_folder_dialog(self, w, title, default_path=None):
        return self._run_subprocess_dialog(title, 2, default_path, None)

    # --- Taskbar Progress ---
    def set_taskbar_progress(self, w, state="normal", value=0, max_value=100):
        pass

    def set_window_icon(self, w, icon_path):
        if not self.gtk or not icon_path:
            return
        win = self._get_window(w)
        err = ctypes.c_void_p(0)
        res = self.gtk.gtk_window_set_icon_from_file(
            win, icon_path.encode("utf-8"), ctypes.byref(err)
        )
        if not res:
            print(f"[Pytron] Failed to set window icon from {icon_path}")

    def set_app_id(self, app_id):
        try:
            glib = ctypes.CDLL("libglib-2.0.so.0")
            glib.g_set_prgname.argtypes = [ctypes.c_char_p]
            glib.g_set_prgname(app_id.encode("utf-8"))
            glib.g_set_application_name.argtypes = [ctypes.c_char_p]
            glib.g_set_application_name(app_id.encode("utf-8"))
        except Exception:
            pass

    def set_launch_on_boot(self, app_name, exe_path, enable=True):
        import os

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
