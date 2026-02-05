# Pytron User Guide

This guide covers core concepts, configuration, and advanced usage of the Pytron framework.

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

```typescript
import pytron from 'pytron-client';

async function loadUser() {
    const user = await pytron.get_user(1);
    console.log(user.name); // Typed as string
}
```

### 3. Global Shortcuts
Register global keyboard shortcuts that work even when the window is not focused.

```python
# Register shortcut (Ctrl+Shift+SPACE)
app.shortcut("Ctrl+Shift+SPACE", lambda: app.toggle_visibility())
```

### 4. System Integration
Pytron gives you direct access to native OS features.

```python
# Taskbar Progress
window.set_taskbar_progress("normal", 45)

# High-Performance Binary IPC (Virtual Asset Provider)
window.serve_data("my-raw-frame", binary_content, "image/jpeg")
```

Frontend consumption:
```javascript
const response = await fetch('pytron://my-raw-frame');
```

## Configuration (settings.json)

Pytron uses a `settings.json` file in your project root to manage application configuration.

```json
{
    "title": "My App",
    "dimensions": [1024, 768],
    "frameless": true,
    "url": "frontend/dist/index.html",
    "debug": false,
    "icon": "icon.png",
    "version": "1.0.6",
    "force-package": ["llama_cpp"],
    "frontend_provider": "npm",
    "close_to_tray": true
}
```

## Chrome Engine (Electron)

For applications requiring maximum stability or proprietary codecs, usage the Chrome Engine.

- **Run Dev**: `pytron run --chrome`
- **Build**: `pytron package --chrome`
- **Install Engine**: `pytron engine install chrome`

## UI Components

Pytron provides pre-built Web Components.

```bash
npm install pytron-ui
```

```javascript
import "pytron-ui/webcomponents/TitleBar.js";
// HTML: <pytron-title-bar></pytron-title-bar>
```

## Packaging Details

**Note on File Permissions**: When installed in `Program Files`, your app is read-only. Pytron automatically changes the CWD to `%APPDATA%/MyApp` at runtime so relative paths for logging/dbs work correctly.
