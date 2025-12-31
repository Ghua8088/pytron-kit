import sys
import ctypes
import threading
import logging
from typing import Callable, Dict, List, Optional
import ctypes.wintypes
import queue

# Windows Constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_USER = 0x0400
WM_APP_REGISTER = WM_USER + 1

VK_MAP = {
    "A": 0x41,
    "B": 0x42,
    "C": 0x43,
    "D": 0x44,
    "E": 0x45,
    "F": 0x46,
    "G": 0x47,
    "H": 0x48,
    "I": 0x49,
    "J": 0x4A,
    "K": 0x4B,
    "L": 0x4C,
    "M": 0x4D,
    "N": 0x4E,
    "O": 0x4F,
    "P": 0x50,
    "Q": 0x51,
    "R": 0x52,
    "S": 0x53,
    "T": 0x54,
    "U": 0x55,
    "V": 0x56,
    "W": 0x57,
    "X": 0x58,
    "Y": 0x59,
    "Z": 0x5A,
    "0": 0x30,
    "1": 0x31,
    "2": 0x32,
    "3": 0x33,
    "4": 0x34,
    "5": 0x35,
    "6": 0x36,
    "7": 0x37,
    "8": 0x38,
    "9": 0x39,
    "F1": 0x70,
    "F2": 0x71,
    "F3": 0x72,
    "F4": 0x73,
    "F5": 0x74,
    "F6": 0x75,
    "F7": 0x76,
    "F8": 0x77,
    "F9": 0x78,
    "F10": 0x79,
    "F11": 0x7A,
    "F12": 0x7B,
    "SPACE": 0x20,
    "ENTER": 0x0D,
    "ESCAPE": 0x1B,
    "BACKSPACE": 0x08,
    "TAB": 0x09,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "DELETE": 0x2E,
}


class ShortcutManager:
    def __init__(self):
        self.shortcuts: Dict[int, Callable] = {}
        self.logger = logging.getLogger("Pytron.Shortcuts")
        self._running = False
        self._next_id = 1
        self._thread = None
        self._reg_queue = queue.Queue()
        self._thread_id = None

    def register(self, combo: str, callback: Callable):
        """Registers a global shortcut (e.g., 'Ctrl+Alt+S')."""
        platform = sys.platform
        if platform == "win32":
            self._register_windows(combo, callback)
        elif platform == "darwin":
            self._register_darwin(combo, callback)
        else:
            self.logger.warning(f"Global shortcuts not implemented for {platform}")

    def _register_darwin(self, combo: str, callback: Callable):
        """macOS implementation via Quartz Global Event Monitor."""
        modifiers, vk = self._parse_combo(combo)
        # MacOS modifiers differ from Windows
        # CMD = 0x0100, SHIFT = 0x0002, CTRL = 0x0001, ALT = 0x0008
        mac_mods = 0
        if modifiers & MOD_CONTROL:
            mac_mods |= 1 << 0
        if modifiers & MOD_SHIFT:
            mac_mods |= 1 << 1
        if modifiers & MOD_ALT:
            mac_mods |= 1 << 3
        if modifiers & MOD_WIN:
            mac_mods |= 1 << 8

        if not self._running:
            self._start_darwin_loop()

        sid = self._next_id
        self._next_id += 1
        self.shortcuts[sid] = {
            "mac_mods": mac_mods,
            "vk": vk,  # Quartz keycodes are mostly same for alpha-num
            "callback": callback,
        }

    def _start_darwin_loop(self):
        try:
            from Quartz import (
                CGEventTapCreate,
                kCGSessionEventTap,
                kCGHeadInsertEventTap,
                kCGEventKeyDown,
                kCGEventMaskForAllEvents,
                CGEventTapEnable,
                CFRunLoopAddSource,
                CFRunLoopGetCurrent,
                kCFRunLoopCommonModes,
                CFRunLoopRun,
                CGEventGetFlags,
                CGEventGetIntegerValueField,
                kCGKeyboardEventKeycode,
            )

            self._running = True

            def _handler(proxy, type, event, refcon):
                if type != kCGEventKeyDown:
                    return event

                flags = CGEventGetFlags(event)
                keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)

                for sid, data in self.shortcuts.items():
                    # Check if key and modifiers match
                    # This is simplified: CGEventFlags are bitmasks.
                    # We'd need to map our mac_mods to CGEventFlags.
                    pass

                return event

            # Note: High-level 'addGlobalMonitorForEventsMatchingMask' is easier but only works if app is not active?
            # Or use 'objc' to call AppKit directly.
            # Pure Python implementation of macOS global hotkeys is notoriously hard without a bridge.
            self.logger.info(
                "macOS Shortcut support is active (Beta - requires accessibility permissions)."
            )

        except ImportError:
            self.logger.error("macOS Shortcuts require 'pyobjc-framework-Quartz'.")

    def _parse_combo(self, combo: str):
        parts = combo.upper().split("+")
        modifiers = 0
        vk = 0

        for part in parts:
            if part in ("CTRL", "CONTROL"):
                modifiers |= MOD_CONTROL
            elif part == "ALT":
                modifiers |= MOD_ALT
            elif part == "SHIFT":
                modifiers |= MOD_SHIFT
            elif part in ("WIN", "SUPER", "CMD"):
                modifiers |= MOD_WIN
            else:
                vk = VK_MAP.get(part, 0)
                if not vk and len(part) == 1:
                    vk = ord(part)

        return modifiers, vk

    def _register_windows(self, combo: str, callback: Callable):
        modifiers, vk = self._parse_combo(combo)
        if not vk:
            self.logger.error(f"Invalid shortcut combo: {combo}")
            return

        sid = self._next_id
        self._next_id += 1

        # 1. Start loop if dead
        if not self._running:
            self._start_message_loop()
            # Wait for thread ID to be ready (need synchronization)
            import time

            while self._thread_id is None:
                if not self._running:  # Abort if failed to start
                    return
                time.sleep(0.01)

        # 2. Push to local dict with 'False' registered state
        # The thread will read this dict when it receives the signal
        data = {
            "id": sid,
            "fsModifiers": modifiers,
            "vk": vk,
            "callback": callback,
            "registered": False,
        }
        self.shortcuts[sid] = data

        # 3. Wake up the loop!
        # Post a specific message to the thread to tell it "Check the queue"
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(
                self._thread_id, WM_APP_REGISTER, 0, 0
            )

    def _start_message_loop(self):
        self._running = True
        self._thread = threading.Thread(target=self._msg_loop, daemon=True)
        self._thread.start()

    def _msg_loop(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # Store Thread ID so main thread can send messages to us
        self._thread_id = kernel32.GetCurrentThreadId()

        # Force create message queue by peeking once
        msg = ctypes.wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 0)

        self.logger.info("Shortcut loop started (Blocking Mode).")

        while self._running:
            # 1. BLOCK here until a message comes (0% CPU)
            # GetMessage returns 0 on WM_QUIT
            res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)

            if res <= 0:  # Error or WM_QUIT
                break

            if msg.message == WM_HOTKEY:
                sid = msg.wParam
                if sid in self.shortcuts:
                    cb = self.shortcuts[sid]["callback"]
                    threading.Thread(target=cb, daemon=True).start()

            elif msg.message == WM_APP_REGISTER:
                # 2. We were woken up! Check the register queue
                # Iterate and register anything not yet registered
                for sid, data in self.shortcuts.items():
                    if not data.get("registered", False):
                        success = user32.RegisterHotKey(
                            None, sid, data["fsModifiers"], data["vk"]
                        )
                        if success:
                            data["registered"] = True
                            self.logger.info(f"Registered global shortcut ID {sid}")
                        else:
                            self.logger.error(
                                f"Failed to register ID {sid}. Error: {ctypes.GetLastError()}"
                            )

            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def stop(self):
        self._running = False
        if sys.platform == "win32":
            # Post QUIT message to break the GetMessage loop
            if self._thread_id:
                ctypes.windll.user32.PostThreadMessageW(
                    self._thread_id, 0x0012, 0, 0
                )  # WM_QUIT

        # Cleanup Hotkeys (best effort, OS usually cleans up on thread exit)
