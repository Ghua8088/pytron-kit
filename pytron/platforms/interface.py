class PlatformInterface:
    def minimize(self, w): pass
    def set_bounds(self, w, x, y, width, height): pass
    def close(self, w): pass
    def toggle_maximize(self, w): return False
    def make_frameless(self, w): pass
    def start_drag(self, w): pass
    def message_box(self, w, title, message, style=0): return 6 # Default Yes
    
    # New Cross-platform Daemon/Notification Capabilities
    def notification(self, w, title, message, icon=None): pass
    def hide(self, w): pass
    def show(self, w): pass
    def set_window_icon(self, w, icon_path): pass
    def set_app_id(self, app_id): pass
    
    # Dialogs
    def open_file_dialog(self, w, title, default_path=None, file_types=None): return None
    def save_file_dialog(self, w, title, default_path=None, default_name=None, file_types=None): return None
    def open_folder_dialog(self, w, title, default_path=None): return None
    def set_slim_titlebar(self, w, enabled): pass
    def set_launch_on_boot(self, app_name, exe_path, enable=True): pass
