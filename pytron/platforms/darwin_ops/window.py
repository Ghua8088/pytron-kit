import ctypes
from . import libs
from .utils import get_window, call, get_class, str_to_nsstring, msg_send


def minimize(w):
    win = get_window(w)
    call(win, "miniaturize:", None)


def set_bounds(w, x, y, width, height):
    pass


def close(w):
    win = get_window(w)
    call(win, "close")


def toggle_maximize(w):
    win = get_window(w)
    call(win, "zoom:", None)
    return True


def make_frameless(w):
    win = get_window(w)
    # NSWindowStyleMaskTitled = 1 << 0
    # NSWindowStyleMaskClosable = 1 << 1
    # NSWindowStyleMaskMiniaturizable = 1 << 2
    # NSWindowStyleMaskResizable = 1 << 3
    # NSWindowStyleMaskFullSizeContentView = 1 << 15

    # We want bits: 1|2|4|8|32768 = 32783
    call(win, "setStyleMask:", 32783)  # Standard macos "frameless but native controls"
    call(win, "setTitlebarAppearsTransparent:", 1)
    call(win, "setTitleVisibility:", 1)  # NSWindowTitleHidden


def start_drag(w):
    win = get_window(w)
    call(win, "setMovableByWindowBackground:", 1)


def hide(w):
    win = get_window(w)
    call(win, "orderOut:", None)


def is_visible(w):
    win = get_window(w)
    return bool(call(win, "isVisible"))


def show(w):
    win = get_window(w)
    call(win, "makeKeyAndOrderFront:", None)
    try:
        cls_app = get_class("NSApplication")
        ns_app = msg_send(cls_app, "sharedApplication")
        msg_send(ns_app, "activateIgnoringOtherApps:", True)
    except Exception:
        pass


def set_window_icon(w, icon_path):
    if not libs.objc or not icon_path:
        return
    try:
        cls_image = get_class("NSImage")
        img_alloc = msg_send(cls_image, "alloc")
        ns_path = str_to_nsstring(icon_path)
        ns_image = msg_send(img_alloc, "initWithContentsOfFile:", ns_path)

        if ns_image:
            cls_app = get_class("NSApplication")
            ns_app = msg_send(cls_app, "sharedApplication")
            msg_send(ns_app, "setApplicationIconImage:", ns_image)
    except Exception:
        pass


def center(w):
    win = get_window(w)
    call(win, "center")


def set_always_on_top(w, enable):
    win = get_window(w)
    # NSFloatingWindowLevel = 3, NSNormalWindowLevel = 0
    level = 3 if enable else 0
    call(win, "setLevel:", level)


def set_fullscreen(w, enable):
    win = get_window(w)
    # Check current style mask for NSWindowStyleMaskFullScreen (1 << 14)
    style_mask = call(win, "styleMask")
    is_fullscreen = (style_mask & (1 << 14)) != 0

    if is_fullscreen != enable:
        call(win, "toggleFullScreen:", None)
