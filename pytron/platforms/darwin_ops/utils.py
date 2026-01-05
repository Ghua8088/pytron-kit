import ctypes
from ...bindings import lib
from . import libs

def get_window(w):
    return lib.webview_get_window(w)

def call(obj, selector, *args):
    if not libs.objc:
        return None
    sel = libs.objc.sel_registerName(selector.encode("utf-8"))
    return libs.objc.objc_msgSend(obj, sel, *args)

def get_class(name):
    if not libs.objc:
        return None
    return libs.objc.objc_getClass(name.encode("utf-8"))

def str_to_nsstring(s):
    if not libs.objc:
        return None
    cls = get_class("NSString")
    sel = libs.objc.sel_registerName(
        "stringWithUTF8String:".encode("utf-8")
    )
    f = ctypes.CFUNCTYPE(
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p
    )(libs.objc.objc_msgSend)
    return f(cls, sel, s.encode("utf-8"))

def bool_to_nsnumber(b):
    if not libs.objc:
        return None
    cls = get_class("NSNumber")
    sel = libs.objc.sel_registerName("numberWithBool:".encode("utf-8"))
    f = ctypes.CFUNCTYPE(
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool
    )(libs.objc.objc_msgSend)
    return f(cls, sel, b)
