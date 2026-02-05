from . import libs
import ctypes

# In Native Engine architecture, 'w' is passed as the HWND/XID integer directly.


def get_window(w):
    return w


get_hwnd = get_window


def get_child_webview(win_ptr):
    if not libs.gtk:
        return None
    libs.gtk.gtk_bin_get_child.argtypes = [ctypes.c_void_p]
    libs.gtk.gtk_bin_get_child.restype = ctypes.c_void_p
    return libs.gtk.gtk_bin_get_child(win_ptr)
