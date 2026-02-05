![Pytron](https://raw.githubusercontent.com/Ghua8088/pytron/main/pytron-banner.png)

# Pytron Kit

[![PyPI Version](https://img.shields.io/pypi/v/pytron-kit.svg)](https://pypi.org/project/pytron-kit/)
[![Downloads](https://img.shields.io/pypi/dm/pytron-kit.svg)](https://pypi.org/project/pytron-kit/)
[![License](https://img.shields.io/pypi/l/pytron-kit.svg)](https://pypi.org/project/pytron-kit/)
[![GitHub](https://img.shields.io/badge/github-repo-000000?logo=github)](https://github.com/Ghua8088/pytron)
[![Website](https://img.shields.io/badge/official-website-blue)](https://pytron-kit.github.io/)


**Pytron-kit** is a high-performance framework for building native ("parasitic") desktop apps using Python and Web Technologies (React, Vite). It combines the computational depth of Python (AI/ML) with the UI flexibility of the web, achieving a **~5MB footprint** by utilizing the OS-native webview.

## Linux Requirements
On **Ubuntu/Debian**, you must install the WebKitGTK headers and glib bindings before installing Pytron:

```bash
sudo apt-get install -y libcairo2-dev libgirepository-2.0-dev libglib2.0-dev pkg-config python3-dev libwebkit2gtk-4.1-dev gir1.2-gtk-4.0
```

## Quick Start

```bash
# 1. Install
pip install pytron-kit

# 2. Create Project (React + Vite)
pytron init my_app

# 3. Run (Hot-Reloading)
pytron run --dev
```

## Hello World

**Python Backend** (`main.py`)
```python
from pytron import App

app = App()

@app.expose
def greet(name: str):
    return f"Hello, {name} from Python!"

app.run()
```

**Frontend** (`App.jsx`)
```javascript
import pytron from 'pytron-client';

const msg = await pytron.greet("User");
console.log(msg); // "Hello, User from Python!"
```

## Key Features
*   **Agentic Shield (God Mode)**: The world's first **Runtime-Audited Compiler**. Pytron executes your app to map 100% of dynamic dependencies (Crystal Mode), tree-shakes the code into a **Virtual Entry Point**, and compiles it to a **Native Extension** using Rust & Zig.
*   **Adaptive Runtime**: Use the **Native Webview** (~5MB) for efficiency or switch to the **Chrome Engine** (Electron) for 100% rendering parity.
*   **Zero-Copy Bridge**: Stream raw binary data (video/tensors) from Python to JS at 60FPS via `pytron://`, bypassing Base64 overhead.
*   **Type-Safe**: Automatically generates TypeScript definitions (`.d.ts`) from your Python type hints.
*   **Native Integration**: Global shortcuts, Taskbar progress, System Tray, and Native File Dialogs.

## The Agentic Shield

Pytron redefines Python distribution with a 3-stage security and optimization pipeline known as the **Agentic Shield**.

1.  **Crystal Audit (💎)**: Uses `sys.addaudithook` (PEP 578) to execute your application and strictly record every module implementation used. No more "Missing Import" errors.
2.  **Virtual Entry Point**: Automatically generates a synthesized entry file (`_virtual_root.py`) containing only the Python APIs you explicitly exposed.
3.  **Rust Engine (🦀)**: Compiles the virtual root into a native CPylib (`app.pyd` or `app.so`) using **Zig**, and bundles it with a custom **Rust Bootloader**.

## Packaging

```bash
# Standard Build (PyInstaller + Intelligent Hooks)
pytron package

# Crystal Build (Runtime Audit + Tree Shaking)
# *Requires user consent to execute code*
pytron package --crystal

# God Mode (Crystal Audit + Rust Compilation + Native Bootloader)
pytron package --engine rust --crystal
```

## Documentation

*   **[User Guide](USAGE.md)**: Configuration, advanced APIs, and UI components.
*   **[Architecture](ARCHITECTURE.md)**: Deep dive into the internal engineering and philosophy.
*   **[Roadmap](ROADMAP.md)**: Upcoming features.
*   **[Contributing](CONTRIBUTING.md)**: How to help.

## License
Apache License 2.0
