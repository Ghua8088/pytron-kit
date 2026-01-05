from ...bindings import lib
from . import libs
import ctypes

def get_window(w):
    return lib.webview_get_window(w)

def get_child_webview(win_ptr):
    if not libs.gtk:
        return None
    libs.gtk.gtk_bin_get_child.argtypes = [ctypes.c_void_p]
    libs.gtk.gtk_bin_get_child.restype = ctypes.c_void_p
    return libs.gtk.gtk_bin_get_child(win_ptr)
