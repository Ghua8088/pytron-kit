---
description: How to compile the Pytron Native Engine (pytron_native)
---

# Compiling Pytron Native Engine

This workflow guides you through compiling the Rust-based native engine (`pytron_native`) and deploying it to the Python dependencies folder.

## Prerequisites

- **Rust Toolchain**: You must have Rust and `cargo` installed.
- **Python Development Headers**: Required by PyO3 to build the extension module.

## Steps

### 1. Compile and Deploy
Run the specialized build script which handles cargo compilation and artifact relocation.

// turbo
```powershell
python pytron/engines/native/build.py
```

### 2. Verify Output
Ensure that the native binary has been placed in the dependencies folder.

```powershell
ls pytron/dependencies/pytron_native.*
```

## Note for Publishing
When publishing to PyPI or distributing the package, ensure that you have compiled the native engine for the target platform. The `build.py` script automatically handles the naming conventions for Windows (.pyd), macOS (.so), and Linux (.so).
