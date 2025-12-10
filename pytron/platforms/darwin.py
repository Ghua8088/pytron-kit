import ctypes
import ctypes.util
from ..bindings import lib
from .interface import PlatformInterface

class DarwinImplementation(PlatformInterface):
    def __init__(self):
        try:
            # Load Cocoa
            self.cocoa = ctypes.cdll.LoadLibrary(ctypes.util.find_library('Cocoa'))
            
            # Setup objc_msgSend
            self.objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))
            
            self.objc.objc_getClass.restype = ctypes.c_void_p
            self.objc.objc_getClass.argtypes = [ctypes.c_char_p]
            
            self.objc.sel_registerName.restype = ctypes.c_void_p
            self.objc.sel_registerName.argtypes = [ctypes.c_char_p]
            
            self.objc.objc_msgSend.restype = ctypes.c_void_p
            self.objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            
        except Exception as e:
            print(f"Pytron Warning: Cocoa/ObjC not found: {e}")
            self.objc = None

    def _get_window(self, w):
        return lib.webview_get_window(w) 

    def _call(self, obj, selector, *args):
        if not self.objc: return None
        sel = self.objc.sel_registerName(selector.encode('utf-8'))
        return self.objc.objc_msgSend(obj, sel, *args)
    
    # Helper for boolean args (True/False -> 1/0)
    def _bool(self, val):
        return 1 if val else 0
        
    def minimize(self, w):
        win = self._get_window(w)
        self._call(win, "miniaturize:", None)

    def set_bounds(self, w, x, y, width, height):
        win = self._get_window(w)
        # Create NSRect (x, y, w, h) - Struct handling in ctypes is needed for SetFrame
        # This is complex in pure ctypes without defining structures. 
        # Simplified approach: many simple Cocoa calls take primitives, but setFrame:display: takes a struct.
        # We might skip exact bounds setting for now or implement NSRect struct.
        pass 

    def close(self, w):
        win = self._get_window(w)
        self._call(win, "close")

    def toggle_maximize(self, w):
        win = self._get_window(w)
        self._call(win, "zoom:", None)
        return True # Approximation

    def make_frameless(self, w):
        win = self._get_window(w)
        # NSWindowStyleMaskBorderless = 0
        # NSWindowStyleMaskResizable = 8
        # setStyleMask: 8
        self._call(win, "setStyleMask:", 8)
        self._call(win, "setTitlebarAppearsTransparent:", 1)
        self._call(win, "setTitleVisibility:", 1) # NSWindowTitleHidden

    def start_drag(self, w):
        win = self._get_window(w)
        # performWindowDragWithEvent: requires an event.
        # movableByWindowBackground is cleaner
        self._call(win, "setMovableByWindowBackground:", 1)
