from pytron import App

app = App()

# 1. Register a Global OS-level Shortcut
# This works even when the app is minimized or out of focus.
@app.shortcut("Ctrl+Shift+Space")
def toggle_visibility():
    """Toggles the window visibility."""
    if app.is_visible:
        app.hide()
    else:
        app.show()
        # Optionally bring to front
        # app.windows[0].center() 

@app.shortcut("Alt+K")
def notify_me():
    """Trigger a notification via shortcut."""
    app.system_notification("Pytron Shortcut", "You pressed Alt+K!")

@app.expose
def setup_tray():
    """Initializes the system tray with a menu."""
    tray = app.setup_tray_standard() # Creates a tray with basic 'Show/Hide/Exit'
    
    # You can also manually add items (advanced)
    # app.tray.add_item("Custom Action", lambda: print("Action clicked"))
    
    return "Tray initialized! Look at your system tray / menu bar."

@app.expose
def send_test_notification():
    app.system_notification(
        title="Pytron Demo",
        message="This is a native system notification!"
    )

if __name__ == "__main__":
    app.run()
