---
description: How to prepare and publish a Pytron application
---

# Publishing Pytron Applications

This workflow covers the end-to-end process of preparing, compiling, and packaging your Pytron application for release.

## 1. Compile Native Engine
Before packaging, ensure the native engine is compiled for the current platform.

// turbo
```powershell
python pytron/engines/native/build.py
```

## 2. Build Frontend
Ensure your frontend assets are built and optimized.

// turbo
```powershell
pytron build-frontend frontend
```

## 3. Package for Distribution
Create a standalone executable. Use `--secure` for rust-bootloader protection and `--installer` to generate a setup.exe (Windows).

// turbo
```powershell
pytron package app.py --smart-assets --secure --installer
```

## 4. Verify Release
Check the `dist/` directory for your packaged application and installer.

```powershell
ls dist/
```

## Platform Specifics
- **Windows**: Use `--installer` (NSIS required).
- **macOS**: Ensure dependencies from `/macos-package` are installed.
- **Linux**: Build an AppImage or .deb (coming soon).

## Automated CI/CD (GitHub Actions)
You can also trigger these builds automatically using the provided GitHub Actions:
- **.github/workflows/publish.yml**: Handles PyPI releases.
- **.github/workflows/windows-package.yml**: Builds and uploads a Windows `.exe` and installer on every version tag (`v*`).
- **.github/workflows/macos-package.yml**: Builds and uploads a macOS `.app` bundle on every version tag.
