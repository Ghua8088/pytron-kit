import os
import sys
import shutil
import subprocess
from pathlib import Path
from ..console import log, run_command_with_output


class MetadataEditor:
    """Universal Metadata Editor for Pytron binaries using rcedit on Windows."""

    def __init__(self, package_dir=None):
        if package_dir:
            self.package_dir = Path(package_dir)
        else:
            import pytron

            self.package_dir = Path(pytron.__file__).resolve().parent.parent

        self.rcedit = self.package_dir / "pytron" / "rcedit-x64.exe"

        try:
            import metaedit

            self.has_metaedit = True
        except ImportError:
            self.has_metaedit = False

    def update(self, binary_path, icon_path, settings, dist_dir=None):
        binary_path = Path(binary_path)

        if self.has_metaedit:
            log(f"Applying metadata to {binary_path.name} using metaedit", style="info")
            try:
                import metaedit

                author = settings.get("author", "Pytron User")
                title = settings.get("title", binary_path.stem)

                meta = {
                    "icon": (
                        str(icon_path)
                        if icon_path and os.path.exists(icon_path)
                        else None
                    ),
                    "version": str(settings.get("version", "1.0.0")),
                    "CompanyName": author,
                    "FileDescription": settings.get("description", "Pytron App"),
                    "LegalCopyright": settings.get(
                        "copyright", f"Copyright © {author}"
                    ),
                    "ProductName": title,
                }

                # Filter out None values
                meta = {k: v for k, v in meta.items() if v is not None}

                # Windows-specific surgery
                if sys.platform == "win32":
                    meta["InternalName"] = binary_path.stem
                    meta["OriginalFilename"] = f"{binary_path.stem}.exe"

                metaedit.update(str(binary_path), **meta)
                log(f"Metadata Applied via metaedit on {sys.platform}", style="success")

                # If macOS, we still need to return the bundled binary path if metaedit moved it
                if sys.platform == "darwin":
                    app_bundle = binary_path.parent / f"{title}.app"
                    bundled_bin = app_bundle / "Contents" / "MacOS" / binary_path.name
                    if bundled_bin.exists():
                        return bundled_bin

                return binary_path
            except Exception as e:
                log(
                    f"metaedit failed: {e}. Falling back to legacy methods...",
                    style="warning",
                )

        if sys.platform == "win32":
            return self._update_windows(binary_path, icon_path, settings)
        elif sys.platform == "darwin":
            return self._update_macos(binary_path, icon_path, settings, dist_dir)
        elif sys.platform == "linux":
            return self._update_linux(binary_path, icon_path, settings, dist_dir)
        return binary_path

    def _update_windows(self, binary_path, icon_path, settings):
        """Windows Fallback: Uses rcedit."""
        if not self.rcedit.exists():
            log(
                f"Warning: rcedit not found at {self.rcedit}. Skipping metadata update.",
                style="warning",
            )
            return binary_path

        log(
            f"Applying Windows metadata to {binary_path.name} using rcedit",
            style="info",
        )

        # 1. Update Icon
        if icon_path and os.path.exists(icon_path):
            try:
                cmd = [str(self.rcedit), str(binary_path), "--set-icon", str(icon_path)]
                run_command_with_output(cmd, style="dim")
            except Exception as e:
                log(f"Icon update failed: {e}", style="warning")

        # 2. Update Version
        version = str(settings.get("version", "1.0.0"))
        try:
            cmd = [
                str(self.rcedit),
                str(binary_path),
                "--set-file-version",
                version,
                "--set-product-version",
                version,
            ]
            run_command_with_output(cmd, style="dim")
        except Exception as e:
            log(f"Version update failed: {e}", style="warning")

        # 3. Update Strings
        author = settings.get("author", "Pytron User")
        patch_map = {
            "CompanyName": author,
            "FileDescription": settings.get("description", "Pytron App"),
            "LegalCopyright": settings.get("copyright", f"Copyright © {author}"),
            "ProductName": settings.get("title", binary_path.stem),
        }

        try:
            cmd = [str(self.rcedit), str(binary_path)]
            for key, value in patch_map.items():
                cmd.extend(["--set-version-string", key, str(value)])
            run_command_with_output(cmd, style="dim")
        except Exception as e:
            log(f"Metadata update failed: {e}", style="warning")

        return binary_path

    def _update_macos(self, binary_path, icon_path, settings, dist_dir):
        """macOS Fallback: Manual Bundle Synthesis."""
        import plistlib

        out_name = binary_path.stem
        app_name = settings.get("title", out_name)
        app_bundle = dist_dir / f"{app_name}.app"
        contents_dir = app_bundle / "Contents"
        macos_dir = contents_dir / "MacOS"
        resources_dir = contents_dir / "Resources"

        for d in [macos_dir, resources_dir]:
            d.mkdir(parents=True, exist_ok=True)

        bundled_binary = macos_dir / out_name
        if binary_path.exists():
            shutil.move(str(binary_path), str(bundled_binary))

        version = str(settings.get("version", "1.0.0"))
        author = settings.get("author", "Pytron User")
        bundle_id = settings.get(
            "bundle_id", f"com.{author.replace(' ', '').lower()}.{out_name.lower()}"
        )

        info_plist = {
            "CFBundleExecutable": out_name,
            "CFBundleIconFile": "app.icns",
            "CFBundleIdentifier": bundle_id,
            "CFBundleName": app_name,
            "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": version,
            "CFBundleVersion": version,
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": settings.get(
                "copyright", f"Copyright © {author}"
            ),
        }

        # Merge user custom plist settings
        custom_plist = settings.get("macos_plist")
        if custom_plist and isinstance(custom_plist, dict):
            info_plist.update(custom_plist)
            log(f"Merged {len(custom_plist)} custom Info.plist overrides", style="dim")

        plist_path = contents_dir / "Info.plist"
        with open(plist_path, "wb") as f:
            plistlib.dump(info_plist, f)

        if icon_path and os.path.exists(icon_path):
            if str(icon_path).endswith(".icns"):
                shutil.copy(icon_path, resources_dir / "app.icns")

        return bundled_binary

    def _update_linux(self, binary_path, icon_path, settings, dist_dir):
        """Linux Fallback: Manual .desktop entry."""
        out_name = binary_path.stem
        app_name = settings.get("title", out_name)

        desktop_content = f"""[Desktop Entry]
Type=Application
Name={app_name}
Exec=./{out_name}
Icon=./icon.png
Terminal=false
"""
        (dist_dir / f"{out_name}.desktop").write_text(desktop_content)
        if icon_path and os.path.exists(icon_path):
            shutil.copy(icon_path, dist_dir / "icon.png")
        return binary_path
