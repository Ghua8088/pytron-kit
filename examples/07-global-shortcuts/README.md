# Example 07: Global Shortcuts & Tray

This example demonstrates how to integrate your app deeply into the host Operating System.

## Key Features

- **Global Shortcuts**: Registering keyboard hooks that work even when the app is minimized or the user is in another application.
- **System Tray / Menu Bar**: Creating a presence in the system notification area.
- **Native Notifications**: Sending standard OS toasts/notifications.
- **Close to Tray**: Demonstrating how to keep the app running in the background.

## How it works

1.  **Shortcuts**: `app.shortcut("KeyCombo", callback)` uses platform-specific hooks to listen for keyboard events globally.
2.  **System Tray**: `app.setup_tray_standard()` initializes a tray icon with default behaviors (Show, Hide, Exit). 
3.  **Notifications**: `app.system_notification()` transparently handles Windows Toasts, macOS User Notifications, and Linux libnotify.

## Interaction

1. Run the app.
2. Press `Alt + K`. You should see a notification even if you switch to your browser.
3. Click "Initialize System Tray". An icon will appear in your taskbar/menu bar.
4. Close the window with the 'X' button. Notice the process doesn't exit (it stays in the tray).
5. Use `Ctrl + Shift + Space` to bring it back!
