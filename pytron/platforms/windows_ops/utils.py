from ...bindings import lib


def get_hwnd(w):
    try:
        return lib.webview_get_window(w)
    except:
        return 0
