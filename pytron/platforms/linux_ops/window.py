import ctypes
from . import libs
from .utils import get_window


def minimize(w):
    if not libs.gtk:
        return
    win = get_window(w)
    libs.gtk.gtk_window_iconify(win)


def set_bounds(w, x, y, width, height):
    if not libs.gtk:
        return
    win = get_window(w)
    libs.gtk.gtk_window_move(win, int(x), int(y))
    libs.gtk.gtk_window_resize(win, int(width), int(height))


def close(w):
    if not libs.gtk:
        return
    win = get_window(w)
    libs.gtk.gtk_window_close(win)


def toggle_maximize(w):
    if not libs.gtk:
        return False
    win = get_window(w)
    is_maximized = libs.gtk.gtk_window_is_maximized(win)
    if is_maximized:
        libs.gtk.gtk_window_unmaximize(win)
        return False
    else:
        libs.gtk.gtk_window_maximize(win)
        return True


def make_frameless(w):
    if not libs.gtk:
        return
    win = get_window(w)
    libs.gtk.gtk_window_set_decorated(win, 0)  # FALSE


def start_drag(w):
    if not libs.gtk:
        return
    win = get_window(w)
    # 1 = GDK_BUTTON_PRIMARY_MASK (approx), sometimes 0 works for timestamps
    libs.gtk.gtk_window_begin_move_drag(win, 1, 0, 0)


def hide(w):
    if not libs.gtk:
        return
    win = get_window(w)
    libs.gtk.gtk_widget_hide(win)


def is_visible(w):
    if not libs.gtk:
        return True
    win = get_window(w)
    return bool(libs.gtk.gtk_widget_get_visible(win))


def show(w):
    if not libs.gtk:
        return
    win = get_window(w)
    libs.gtk.gtk_widget_show_all(win)
    libs.gtk.gtk_window_present(win)


def set_window_icon(w, icon_path):
    if not libs.gtk or not icon_path:
        return
    win = get_window(w)
    err = ctypes.c_void_p(0)
    res = libs.gtk.gtk_window_set_icon_from_file(
        win, icon_path.encode("utf-8"), ctypes.byref(err)
    )
    if not res:
        print(f"[Pytron] Failed to set window icon from {icon_path}")


def center(w):
    # GTK handles centering via window position usually, but we can implement if needed.
    # For now, just a placeholder or basic implementation if GTK has a method.
    if not libs.gtk:
        return
    win = get_window(w)
    # GTK_WIN_POS_CENTER = 1
    libs.gtk.gtk_window_set_position(win, 1)
