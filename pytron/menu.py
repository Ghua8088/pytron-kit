import ctypes
from typing import List, Optional, Callable


class Menu:
    """
    Abstraction for a native system menu.
    """

    def __init__(self, title: str = ""):
        self.title = title
        self.items: List["MenuItem"] = []
        self._hmenu = None

    def add_item(
        self, label: str, callback: Optional[Callable] = None, shortcut: str = ""
    ):
        item = MenuItem(label, callback, shortcut)
        self.items.append(item)
        return item

    def add_submenu(self, title: str):
        submenu = Menu(title)
        item = MenuItem(title, submenu=submenu)
        self.items.append(item)
        return submenu

    def add_separator(self):
        item = MenuItem("", is_separator=True)
        self.items.append(item)
        return item


class MenuItem:
    def __init__(
        self,
        label: str,
        callback: Optional[Callable] = None,
        shortcut: str = "",
        submenu: Optional[Menu] = None,
        is_separator: bool = False,
    ):
        self.label = label
        self.callback = callback
        self.shortcut = shortcut
        self.submenu = submenu
        self.is_separator = is_separator
        self.enabled = True
        self.checked = False
        self.id = None  # Assigned by the platform when starting


class MenuBar:
    """
    A collection of Menus that forms the application's top menu bar.
    """

    def __init__(self):
        self.menus: List[Menu] = []
        self._id_counter = 1000
        self._callbacks = {}

    def add_menu(self, menu: Menu):
        self.menus.append(menu)
        return menu

    def build_for_windows(self, hwnd):
        """Creates and attaches a Win32 menu to the given HWND."""
        user32 = ctypes.windll.user32
        from .platforms.windows_ops.constants import (
            MF_STRING,
            MF_POPUP,
            MF_SEPARATOR,
            MF_GRAYED,
            MF_CHECKED,
        )

        h_menubar = user32.CreateMenu()

        def _build_recursive(menu_obj, is_top=False):
            if is_top:
                h_menu = h_menubar
            else:
                h_menu = user32.CreatePopupMenu() if not is_top else h_menubar

            for item in menu_obj.items:
                flags = 0
                if item.is_separator:
                    user32.AppendMenuW(h_menu, MF_SEPARATOR, 0, None)
                    continue

                if item.submenu:
                    h_sub = _build_recursive(item.submenu)
                    user32.AppendMenuW(h_menu, MF_STRING | MF_POPUP, h_sub, item.label)
                else:
                    self._id_counter += 1
                    item.id = self._id_counter
                    if item.callback:
                        self._callbacks[item.id] = item.callback

                    if not item.enabled:
                        flags |= MF_GRAYED
                    if item.checked:
                        flags |= MF_CHECKED

                    label = item.label
                    if item.shortcut:
                        label += f"\t{item.shortcut}"

                    user32.AppendMenuW(h_menu, flags | MF_STRING, item.id, label)

            return h_menu

        for top_menu in self.menus:
            h_sub = _build_recursive(top_menu)
            user32.AppendMenuW(h_menubar, MF_STRING | MF_POPUP, h_sub, top_menu.title)

        user32.SetMenu(hwnd, h_menubar)
        return h_menubar

    def handle_command(self, cmd_id):
        """Dispatches a menu command to the appropriate callback."""
        if cmd_id in self._callbacks:
            import threading

            threading.Thread(target=self._callbacks[cmd_id], daemon=True).start()
            return True
        return False
