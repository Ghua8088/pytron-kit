import ctypes
from . import libs
from .utils import get_window, call, get_class, str_to_nsstring


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
    # setStyleMask: 8 (Resizable) | 0 (Borderless) -> But we usually want Titled | FullSizeContentView
    # To mimic standardized frameless:
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
        sel_shared = libs.objc.sel_registerName("sharedApplication".encode("utf-8"))
        ns_app = libs.objc.objc_msgSend(cls_app, sel_shared)

        sel_activate = libs.objc.sel_registerName(
            "activateIgnoringOtherApps:".encode("utf-8")
        )
        f_act = ctypes.CFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool
        )(libs.objc.objc_msgSend)
        f_act(ns_app, sel_activate, True)
    except Exception:
        pass


def set_window_icon(w, icon_path):
    if not libs.objc or not icon_path:
        return
    try:
        cls_image = get_class("NSImage")
        sel_alloc = libs.objc.sel_registerName("alloc".encode("utf-8"))
        sel_init_file = libs.objc.sel_registerName(
            "initWithContentsOfFile:".encode("utf-8")
        )

        img_alloc = libs.objc.objc_msgSend(cls_image, sel_alloc)
        ns_path = str_to_nsstring(icon_path)
        f_init = ctypes.CFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        )(libs.objc.objc_msgSend)
        ns_image = f_init(img_alloc, sel_init_file, ns_path)

        if ns_image:
            cls_app = get_class("NSApplication")
            sel_shared = libs.objc.sel_registerName("sharedApplication".encode("utf-8"))
            ns_app = libs.objc.objc_msgSend(cls_app, sel_shared)

            sel_set_icon = libs.objc.sel_registerName(
                "setApplicationIconImage:".encode("utf-8")
            )
            f_set = ctypes.CFUNCTYPE(
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
            )(libs.objc.objc_msgSend)
            f_set(ns_app, sel_set_icon, ns_image)
    except Exception:
        pass


def center(w):
    # macOS usually centers by default or we can implement if needed
    pass
