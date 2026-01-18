---
description: How to package Pytron for macOS
---

To package your Pytron application for macOS, follow these steps:

1. **Install macOS-specific dependencies**:
   Ensure you have the required Python-Objective-C bridges for native features.
   ```bash
   pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa
   ```

2. **Run the package command**:
   Use the `pytron package` command with the appropriate flags.
   ```bash
   pytron package --smart-assets --installer
   ```

3. **Verify the bundle**:
   The output will be located in the `dist/` directory as a `.app` bundle (and potentially a `.dmg`).

// turbo
4. **Build with Chrome Engine (Optional)**:
   If you need the Chrome engine for macOS:
   ```bash
   pytron package --chrome --smart-assets
   ```
