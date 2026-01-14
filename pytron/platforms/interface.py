from abc import ABC, abstractmethod
from typing import Optional, Dict, List, TypeAlias

# Defines a "Handle" type for clarity -> Zero runtime cost, high readability.
WindowHandle: TypeAlias = int


class PlatformInterface(ABC):
    """
    PINNED STABILITY CONTRACT
    -------------------------
    This interface defines the immutable core contract for all platform implementations.
    Core lifecycle and window operations are abstract and MUST be implemented.
    Extended capabilities (Notifications, Taskbar, etc.) are virtual and optional.
    """

    # --- Core Window Operations (Pinned) ---

    @abstractmethod
    def show(self, w: WindowHandle) -> None:
        pass

    @abstractmethod
    def hide(self, w: WindowHandle) -> None:
        pass

    @abstractmethod
    def close(self, w: WindowHandle) -> None:
        pass

    @abstractmethod
    def minimize(self, w: WindowHandle) -> None:
        pass

    @abstractmethod
    def toggle_maximize(self, w: WindowHandle) -> bool:
        """Returns True if maximized, False if restored."""
        pass

    @abstractmethod
    def set_bounds(
        self, w: WindowHandle, x: int, y: int, width: int, height: int
    ) -> None:
        pass

    @abstractmethod
    def is_visible(self, w: WindowHandle) -> bool:
        pass

    @abstractmethod
    def center(self, w: WindowHandle) -> None:
        pass

    # --- Essential extensions (Should interpret 'w') ---

    def is_alive(self, w: WindowHandle) -> bool:
        """Checks if the native window handle is still valid. Default True to prevent crashes."""
        return True

    def make_frameless(self, w: WindowHandle) -> None:
        pass

    def start_drag(self, w: WindowHandle) -> None:
        pass

    def set_window_icon(self, w: WindowHandle, icon_path: str) -> None:
        pass

    def set_menu(self, w: WindowHandle, menu_bar: List) -> None:
        pass

    # --- System Dialogs & Interactions (Stable Extensions) ---

    def message_box(
        self, w: WindowHandle, title: str, message: str, style: int = 0
    ) -> int:
        return 0  # Default OK/Cancel result

    def open_file_dialog(
        self,
        w: WindowHandle,
        title: str,
        default_path: Optional[str] = None,
        file_types: Optional[str] = None,
    ) -> Optional[str]:
        return None

    def save_file_dialog(
        self,
        w: WindowHandle,
        title: str,
        default_path: Optional[str] = None,
        default_name: Optional[str] = None,
        file_types: Optional[str] = None,
    ) -> Optional[str]:
        return None

    def open_folder_dialog(
        self, w: WindowHandle, title: str, default_path: Optional[str] = None
    ) -> Optional[str]:
        return None

    def notification(
        self, w: WindowHandle, title: str, message: str, icon: Optional[str] = None
    ) -> None:
        pass

    def set_taskbar_progress(
        self, w: WindowHandle, state: str, value: int, max_value: int
    ) -> None:
        """
        Sets the taskbar/dock progress bar state.
        state: 'normal', 'error', 'paused', 'indeterminate', 'none'
        """
        pass

    # --- System Integration (OS Hooks) ---

    def register_protocol(self, scheme: str) -> bool:
        return False

    def set_launch_on_boot(
        self, app_name: str, exe_path: str, enable: bool = True
    ) -> bool:
        return False

    def set_app_id(self, app_id: str) -> None:
        pass

    def get_system_info(self) -> Dict:
        return {}

    # --- Clipboard ---

    def set_clipboard_text(self, text: str) -> bool:
        return False

    def get_clipboard_text(self) -> Optional[str]:
        return None

    # --- UI Polish ---

    def set_slim_titlebar(self, w: WindowHandle, enabled: bool) -> None:
        pass
