![Pytron](https://raw.githubusercontent.com/Ghua8088/pytron/main/pytron-banner.png)
# Pytron Kit

[![PyPI Version](https://img.shields.io/pypi/v/pytron-kit.svg)](https://pypi.org/project/pytron-kit/)
[![Downloads](https://img.shields.io/pypi/dm/pytron-kit.svg)](https://pypi.org/project/pytron-kit/)
[![License](https://img.shields.io/pypi/l/pytron-kit.svg)](https://pypi.org/project/pytron-kit/)
[![GitHub](https://img.shields.io/badge/github-repo-000000?logo=github)](https://github.com/Ghua8088/pytron)
[![Website](https://img.shields.io/badge/official-website-blue)](https://pytron-kit.github.io/)
[![Tests](https://github.com/Ghua8088/pytron/actions/workflows/tests.yml/badge.svg)](https://github.com/Ghua8088/pytron/actions)

Pytron-kit is a modern framework for building desktop applications using Python for the backend and web technologies (React, Vite) for the frontend. It combines the power of Python's ecosystem with the rich user interfaces of the web.

## Framework workings

```mermaid
graph TD
    subgraph "Frontend Process (Web Technology)"
        UI[<b>Pytron UI</b><br>React Components / Web Components]
        Client[<b>Pytron Client</b><br>JavaScript Bridge & State Manager]
        AppJS[<b>User Frontend App</b><br>React/Vite/Next.js]
        
        UI --> AppJS
        AppJS --> Client
    end

    subgraph "IPC Bridge (Inter-Process Communication)"
        Msg[JSON Message Passing]
    end

    subgraph "Backend Process (Python)"
        Kit[<b>Pytron Kit</b><br>Window Manager & Server]
        UserPy[<b>User Backend Code</b><br>@app.expose / Business Logic]
        
        Kit --> UserPy
    end

    Client <-->|RPC Calls & Events| Msg
    Msg <-->|Bridge Interface| Kit

    %% Data Flow
    UserPy -.->|State Updates| Kit
    Kit -.->|Sync State| Client
    Client -.->|Update Signals| AppJS
```
## Features

*   **Type-Safe Bridge**: Automatically generate TypeScript definitions (`.d.ts`) from your Python code.
*   **Reactive State**: Synchronize state seamlessly between Python and JavaScript.
*   **Advanced Serialization**: Built-in support for Pydantic models, PIL Images, UUIDs, and more.
*   **System Integration**: Native file dialogs, notifications, and shortcuts.
*   **Developer Experience**: Hot-reloading, automatic virtual environment management, and easy packaging.

## New / Notable Features (latest)

- **Daemon & System Integration**: New `hide`/`show` APIs and `system_notification` support allow apps to run as daemons, show/hide windows programmatically, and emit native notifications across Windows/macOS/Linux.
- **Taskbar / Dock Progress & Icons**: APIs to set taskbar progress and update the application icon at runtime (Windows taskbar, macOS Dock badge, basic Linux support).
- **Native Dialogs**: Cross-platform native file dialogs (open/save/folder) using the OS tools (Windows common dialogs, macOS AppleScript, Linux `zenity`/`kdialog`) are exposed to the `Webview` layer.
- **Message Boxes**: Unified `message_box` with cross-platform fallbacks (native MessageBox on Windows, `zenity`/`kdialog` on Linux, AppleScript on macOS).
- **Agentic Shield**: A Rust-based secure bootloader that encrypts your Python logic using AES-256-GCM, preventing simple unpacking/decompilation.
- **Nuitka Integration**: Option to compile Python code into machine code for maximum performance and IP protection.
- **Android Support**: Experimental support for building and running Pytron apps on Android.
- **Smart Assets**: Automatically detects and bundles non-code files (images, configs) into your executable.
- **High-Performance VAP Bridge**: Zero-copy binary IPC using the `pytron://` protocol for streaming large data (frames, tensors) without Base64 overhead.
- **Serializer Enhancements**: `PytronJSONEncoder` gained broader support (Pydantic models, PIL images -> data URIs, dataclasses, enums, timedeltas, complex numbers, __slots__, and iterable fallbacks) for safer frontend bridging.
- **Platform Interface Expanded**: Platform backends now provide richer capabilities (notifications, dialogs, icon/app-id management, tray/daemon helpers).
- **Chrome/Electron Engine**: A production-grade alternative to the default webview. Uses Electron (Mojo Engine) for enhanced stability, modern DevTools, and pixel-perfect rendering, while maintaining full support for Pytron's native features (taskbar, menus, frameless).

## Prerequisites

- **Python 3.7+**
- **Node.js & npm** (for frontend development)

### Linux (Ubuntu/Debian) Requirements
Pytron relies on standard system libraries for the webview. You must install them using your package manager:
```bash
sudo apt install libwebkit2gtk-4.1-0 
```
If you encounter `ImportError` or `OSError` related to `gobject` or `glib` (especially on Ubuntu 24.04+), you may also need:
```bash
sudo apt install libcairo2-dev pkg-config python3-dev libgirepository1.0-dev libgirepository-2.0-dev
```

## Quick Start

1.  **Install Pytron**:
**Windows**:
    ```bash
    pip install pytron-kit
    ```

    **Linux / macOS (Recommended)**:
    ```bash
    pipx install pytron-kit
    ```
    *Note: On modern Linux distros (Ubuntu 23.04+), `pipx` involves less risk of breaking system packages (PEP 668).*

2.  **Initialize a New Project**:
    This command scaffolds a new project, creates a virtual environment (`env/`), installs initial dependencies, and sets up a frontend.
    ```bash
    # Default (React + Vite)
    pytron init my_app

    # Using a specific template (vue, svelte, next, etc.)
    pytron init my_app --template next
    ```
    Supported templates: `react` (default), `vue`, `svelte`, `next` (Next.js), `vanilla`, `preact`, `lit`, `solid`, `qwik`.

3.  **Install project dependencies (recommended)**:
    After cloning or when you need to install/update dependencies for the project, use the CLI-managed installer which will create/use the `env/` virtual environment automatically:
    ```bash
    # Creates env/ if missing and installs from requirements.txt
    pytron install
    ```

    Notes:
    - This creates an `env/` directory in the project root (if not already present) and runs `pip install -r requirements.txt` inside it.
    - All subsequent `pytron` commands (`run`, `package`, etc.) will automatically prefer the project's `env/` Python when present.

4.  **Run the App**:
    Start the app in development mode (hot-reloading enabled). The CLI will use `env/` Python automatically if an `env/` exists in the project root.
    *   **Windows**: `run.bat`
    *   **Linux/Mac**: `./run.sh`
    
    Or manually via the CLI:
    ```bash
    pytron run --dev
    ```

## Core Concepts

### 1. Exposing Python Functions
Use the `@app.expose` decorator to make Python functions available to the frontend.

```python
from pytron import App
from pydantic import BaseModel

app = App()

class User(BaseModel):
    name: str
    age: int

@app.expose
def get_user(user_id: int) -> User:
    return User(name="Alice", age=30)

app.generate_types() # Generates frontend/src/pytron.d.ts
app.run()
```

### 2. Calling from Frontend
Import the client and call your functions with full TypeScript support.
any  registered function with "pytron_" prefix will be available as pytron_{function_name}
and will not be proxied into the pytron object.
```typescript
import pytron from 'pytron-client';

async function loadUser() {
    const user = await pytron.get_user(1);
    console.log(user.name); // Typed as string
}
```

### 3. Global Shortcuts
Register global keyboard shortcuts that work even when the window is not focused.

**Python:**
```python
def toggle_visibility():
    if app.is_visible:
        app.hide()
    else:
        app.show()

# Register shortcut (Ctrl+Shift+SPACE)
app.shortcut("Ctrl+Shift+SPACE", toggle_visibility)
app.shortcut("Alt+K", lambda: print("Shortcut triggered!"))
```

**JavaScript (Frontend Listener as Fallback/Manager):**
Using `pytron-ui`'s `ShortcutHandler` allows you to manage these from React context if preferred, but the backend registration above is robust for global OS-level events.

### 4. Lifecycle Hooks
Run cleanup code when the application closes.

```python
@app.on_exit
def cleanup():
    # Close database connections, save state, or cleanup temp files
    print("Application is shutting down...")
    db.close()
```

### 5. System Integration
Pytron gives you direct access to native OS features.

**System Tray & Taskbar:**
```python
# Create a standard tray
tray = app.setup_tray_standard()

# Show progress in Taskbar (Windows) or Dock (macOS)
# State: "normal", "indeterminate", "error", "paused", "none"
window.set_taskbar_progress("normal", 45) 
```

**High-Performance Binary IPC (Virtual Asset Provider):**
Pytron includes a custom protocol `pytron://` that bypasses the slow JSON/Base64 bridge for binary data. This is perfect for local AI models, camera streams, or large datasets.

```python
# Serve large binary data (like images/buffers) via memory
# Available at pytron://my-raw-frame
window.serve_data("my-raw-frame", binary_content, "image/jpeg")
```

In the frontend, you can use these URLs directly in `<img>` tags or `fetch()`:
```javascript
// Zero-overhead binary fetch
const response = await fetch('pytron://my-raw-frame');
const blob = await response.blob();

// Or just use as src
<img src="pytron://my-raw-frame" />
```

**Native Dialogs & Notifications:**
```python
@app.expose
def export_data():
    # Native File Save Dialog
    path = app.dialog_save_file("Export Data", default_name="data.json")
    if path:
        # Show Native System Notification
        app.system_notification("Export Success", f"Saved to {path}")
        return True
    return False
```

## Chrome Engine (Electron)

For applications requiring maximum stability, modern web standards, or advanced video playback, Pytron offers a **Chrome Engine** (powered by Electron) as a drop-in replacement for the standard OS webview.

**Why use it?**
- **Consistency**: Same rendering engine (Blink) on all platforms.
- **Tools**: Full Chrome DevTools experience.
- **Stability**: Avoids OS-specific webview quirks (especially on older Windows versions).
- **Native Support**: Fully integrates with Pytron's native window controls (frameless, taskbar progress, minimization) via a robust IPC bridge.

**Usage:**

Run locally with Chrome engine:
```bash
pytron run --chrome
```

**Packaging with Chrome:**
To bundle the Chrome engine with your application (increases size by ~80MB but guarantees environment):
```bash
pytron package --chrome
```

To install the engine binaries globally for development:
```bash
pytron engine install chrome
```

## Configuration (settings.json)

Pytron uses a `settings.json` file in your project root to manage application configuration.

**Example `settings.json`:**
```json
{
    "title": "My App",
    "dimensions": [1024, 768],
    "frameless": true,
    "url": "frontend/dist/index.html",
    "debug": false,
    "icon": "icon.png",
    "version": "1.0.6",
    "splash_image": "splash.png",
    "author": "YourName",
    "description": "App Description",
    "copyright": "Copyright © 2025",
    "force-package": ["llama_cpp"],
    "frontend_provider": "npm",
    "default_context_menu": false,
    "close_to_tray": true
}
```

*   **title/author**: Used for the window title, application identity (AppUserModelID), and notification branding.
*   **splash_image**: Path to a PNG/JPG shown during the boot process of a packaged app.
*   **close_to_tray**: If `true`, clicking the 'X' button will hide the window to the system tray instead of exiting the process.
*   **force-package**: A list of Python modules that should be explicitly collected during `pytron package`.
*   **default_context_menu**: Set to `false` to disable the native browser right-click menu (highly recommended if using `pytron-ui` ContextMenu).
*   **url**: Entry point for the frontend. In `--dev` mode, this is overridden by the dev server.
*   **frontend_provider**: Choose your default JS package manager: `npm`, `yarn`, `pnpm`, or `bun`.

## UI Components

Pytron provides a set of UI components to help you build a modern desktop application.
They have preimplemented window controls and are ready to use.

# Usage
```bash
npm install pytron-ui
```
then import the webcomponents into your frontend app
```javascript
import "pytron-ui/webcomponents/TitleBar.js";
//usage
<pytron-title-bar></pytron-title-bar>
//for react
import { TitleBar } from "pytron-ui/react";
//usage
<TitleBar></TitleBar>
```
## Packaging

Distribute your app as a standalone executable. Pytron automatically reads your `settings.json` to determine the app name, version, and icon.
**Note on File Permissions**: When your app is installed in `Program Files`, it is read-only. If your app writes logs or databases using relative paths (e.g., `logging.basicConfig(filename='app.log')`), it will crash with `PermissionError`.
**Pytron Solution**: When running as a packaged app, Pytron automatically changes the Current Working Directory (CWD) to a safe user-writable path (e.g., `%APPDATA%/MyApp`). Your relative writes will safely end up there.

### 1. Standard Build
```bash
pytron package
```

### 2. Agentic Shield (Secure Build)
Protects your intellectual property by encrypting your source code and using a Rust-based bootloader to run it in memory.
```bash
pytron package --secure
```

### 3. Nuitka (C++ Compilation)
Compiles your Python code into a native C++ executable for maximum performance.
```bash
pytron package --nuitka
```

### 4. Build with Installer
```bash
pytron package --installer
```

### Cross-Compilation (Build for Linux/macOS from Windows)
PyInstaller doesn't support true cross-compilation. To build for other platforms, you have two options:
1.  **CI/CD (Recommended)**: Run `pytron workflow init` to generate a GitHub Actions file. Push your code, and GitHub will build binaries for Windows, Ubuntu, and macOS automatically.
2.  **Local (Linux only)**: Use **WSL** (Windows Subsystem for Linux) to run `pytron package` inside a Linux environment.

## CLI Reference

*   `pytron init <name> [--template <name>]`: Create a new project.
*   `pytron install [package]`: Install dependencies into the project `env/`.
*   `pytron run [--dev]`: Run the application.
*   `pytron package [--secure] [--nuitka] [--installer]`: Build standalone executable.
*   `pytron frontend [--provider npm|yarn|pnpm|bun] <args>`: Proxy command for JS package managers. Runs any command in the frontend directory (e.g., `pytron frontend --provider bun install`).
*   `pytron doctor`: Check system for missing dependencies and configuration issues.
*   `pytron info`: Show information about the current environment.
*   `pytron android <action>`: Experimental tools for Android (init, sync, build, run).
*   `pytron workflow init`: Generate GitHub Actions for multi-platform packaging (Windows/Linux/macOS).

## Architecture & Technology Decisions

Pytron uses a curated stack of robust open-source technologies to power its features. We explicitly acknowledge and explain our architectural choices below:

-   **Chrome Engine (Mojo)**: We integrate **[Electron](https://www.electronjs.org/)** as our high-performance rendering engine. We use a "headless" approach where Electron handles the view layer (Chromium), while all business logic remains in your Python process. This provides modern CSS support and DevTools without the complexity of a full Node.js backend.
-   **Native Engine**: For lightweight, zero-dependency apps, we use a custom implementation **inspired by [pywebview](https://github.com/r0x0r/pywebview)**. We rebuilt the core loop to support our VAP (Virtual Asset Provider) and deeper platform-specific integration (Win32/Cocoa/GTK) and a more NPM based frontend where python avoids direct injection of JS code and avoids direct interaction with the DOM.
-   **Security Layer**: The "Agentic Shield" secure bootloader is written in **[Rust](https://www.rust-lang.org/)**. We chose Rust for its memory safety and ability to securely handle AES-256-GCM decryption keys in memory, preventing typical Python bytecode extraction attacks.
-   **Packaging**:
    -   **[PyInstaller](https://pyinstaller.org/)**: The default choices for `pytron package` due to its excellent compatibility with complex scientific libraries (NumPy, Torch).
    -   **[Nuitka](https://nuitka.net/)**: Available via `--nuitka`. We support this for developers needing compilation to machine code (C++) for performance-critical applications.
-   **Frontend Tooling**: Our CLI scaffolds projects using **[Vite](https://vitejs.dev/)**. We customized the Vite config to proxy requests to our Python backend, enabling a seamless "Hot Module Replacement" experience for dual-stack development.

**Happy Coding with Pytron!**

## Repository Health
- [Roadmap](ROADMAP.md): Our vision and upcoming features.
- [Contributing](CONTRIBUTING.md): How to get involved in development.
- [Security Policy](SECURITY.md): How to report vulnerabilities.
- [Code of Conduct](CODE_OF_CONDUCT.md): Standards for community behavior.

## License
Pytron is licensed under the [Apache License 2.0](LICENSE).
