import ctypes
import ctypes.util

cocoa = None
objc = None

def load_libs():
    global cocoa, objc
    try:
        # Load Cocoa
        cocoa = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Cocoa"))

        # Setup objc_msgSend
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))

        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]

        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]

        objc.objc_msgSend.restype = ctypes.c_void_p
        # Do NOT set argtypes for objc_msgSend as it is variadic

    except Exception as e:
        print(f"Pytron Warning: Cocoa/ObjC not found: {e}")
        objc = None

load_libs()
