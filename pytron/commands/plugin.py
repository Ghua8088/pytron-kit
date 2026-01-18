import argparse
import os
import shutil
import zipfile
import requests
import json
import subprocess
from pathlib import Path
from ..console import log, print_rule
from .login import get_github_token
from .helpers import get_python_executable, get_config


def cmd_plugin(args: argparse.Namespace) -> int:
    if args.plugin_command == "install":
        return plugin_install(args)
    elif args.plugin_command == "list":
        return plugin_list(args)
    elif args.plugin_command == "uninstall":
        return plugin_uninstall(args)
    elif args.plugin_command == "create":
        return plugin_create(args)
    else:
        log(
            "No plugin command specified. Use 'install', 'list', 'uninstall', or 'create'.",
            style="error",
        )
        return 1


def plugin_create(args):
    name = args.name

    # Check if we are in a Pytron app project
    # We look for common markers like settings.json or a requirements.json
    is_pytron_project = os.path.exists("settings.json") or os.path.exists(
        "requirements.json"
    )

    if is_pytron_project:
        plugins_dir = Path("plugins")
        if not plugins_dir.exists():
            log("Pytron project detected. Creating 'plugins/' directory.", style="info")
            plugins_dir.mkdir()
        plugin_path = plugins_dir / name
    else:
        log(
            "Standalone mode: Creating plugin directory in current folder.",
            style="info",
        )
        plugin_path = Path(name)

    if plugin_path.exists():
        log(f"Plugin directory '{name}' already exists.", style="error")
        return 1

    plugin_path.mkdir()

    # 1. manifest.json
    manifest = {
        "name": name,
        "version": "1.0.0",
        "entry_point": f"main:{name.capitalize()}Plugin",
        "ui_entry": f"{name}_widget.js",
        "python_dependencies": [],
        "npm_dependencies": {},
        "description": "Auto-generated Pytron plugin",
    }
    (plugin_path / "manifest.json").write_text(json.dumps(manifest, indent=4))

    # 2. Python Code
    python_code = f"""import logging

class {name.capitalize()}Plugin:
    def __init__(self, app):
        self.app = app
        self.logger = logging.getLogger(f"Plugin.{name}")

    def setup(self):
        \"\"\"Standard Pytron plugin setup hook.\"\"\"
        self.app.expose(self.greet, name="{name}_greet")
        
        # Example usage of Scoped Storage
        count = self.app.storage.get("load_count", 0)
        self.app.storage.set("load_count", count + 1)
        self.logger.info(f"Plugin loaded {{count + 1}} times.")

    def greet(self, user="User"):
        return f"Hello {{user}} from {name} plugin!"
"""
    (plugin_path / "main.py").write_text(python_code)

    # 3. JS Widget
    js_code = f"""/**
 * {name} Web Component
 */
class {name.capitalize()}Widget extends HTMLElement {{
    constructor() {{
        super();
        this.attachShadow({{ mode: 'open' }});
    }}

    connectedCallback() {{
        this.render();
    }}

    async callGreet() {{
        const welcome = await window.pytron.{name}_greet("Explorer");
        alert(welcome);
    }}

    render() {{
        this.shadowRoot.innerHTML = `
            <style>
                :host {{
                    display: block;
                    padding: 1rem;
                    background: #1e293b;
                    border-radius: 8px;
                    color: white;
                    border: 1px solid #334155;
                }}
                button {{
                    background: #38bdf8;
                    border: none;
                    padding: 5px 15px;
                    border-radius: 4px;
                    cursor: pointer;
                    font-weight: bold;
                }}
            </style>
            <div>
                <strong>{name.capitalize()} Plugin</strong>
                <p>Welcome to your new isolated plugin!</p>
                <button onclick="this.getRootNode().host.callGreet()">Test Bridge</button>
            </div>
        `;
    }}
}}

if (!customElements.get('{name}-widget')) {{
    customElements.define('{name}-widget', {name.capitalize()}Widget);
}}
"""
    (plugin_path / f"{name}_widget.js").write_text(js_code)

    log(f"Successfully scaffolded plugin: {name}", style="success")
    log(f"Location: {plugin_path}")
    return 0


def plugin_install(args):
    return perform_plugin_install(args.identifier)


def perform_plugin_install(identifier: str) -> int:
    parts = identifier.split(".")

    if len(parts) < 2:
        log(
            "Invalid identifier format. Use 'username.repo' or 'username.repo.version'",
            style="error",
        )
        return 1

    username = parts[0]
    repo = parts[1]
    version = parts[2] if len(parts) > 2 else "latest"

    # Resolve target plugins directory
    plugins_dir = Path("plugins")
    if not plugins_dir.exists():
        log("No 'plugins/' directory found in current project. Creating it...")
        plugins_dir.mkdir()

    # Use username_repo to avoid collisions between different authors
    plugin_id = f"{username}_{repo}"
    target_plugin_path = plugins_dir / plugin_id
    if target_plugin_path.exists():
        log(
            f"Plugin '{plugin_id}' already exists at {target_plugin_path}. Use uninstall first if you want to reinstall.",
            style="warning",
        )
        return 1

    print_rule(f"Installing Plugin: {username}/{repo} ({version})")

    # GitHub API Authentication
    headers = {}
    token = get_github_token()
    if token:
        headers["Authorization"] = f"token {token}"
        # We don't want to log the token itself, but we can confirm login status
        log("Authenticated with GitHub (via keyring or env).")
    else:
        log(
            "Note: Unauthenticated. GitHub API rate limits will apply. Run 'pytron login' to authenticate.",
            style="info",
        )

    try:
        if version == "latest":
            api_url = f"https://api.github.com/repos/{username}/{repo}/releases/latest"
        else:
            api_url = f"https://api.github.com/repos/{username}/{repo}/releases/tags/{version}"

        log(f"Fetching release info from: {api_url}")
        response = requests.get(api_url, headers=headers, timeout=30)

        if response.status_code == 404:
            log(
                f"No release found for {username}/{repo}. Checking main branch source...",
                style="warning",
            )
            zip_url = (
                f"https://github.com/{username}/{repo}/archive/refs/heads/main.zip"
            )
        elif response.status_code != 200:
            log(
                f"GitHub API Error: {response.status_code} - {response.text}",
                style="error",
            )
            return 1
        else:
            rel_data = response.json()
            zip_url = rel_data.get("zipball_url")
            log(f"Found release: {rel_data.get('tag_name')}")

        if not zip_url:
            log("Could not find a valid zip download URL.", style="error")
            return 1

        # Download
        log(f"Downloading from: {zip_url}")
        zip_response = requests.get(zip_url, headers=headers, stream=True, timeout=30)
        zip_tmp = Path("plugin_tmp.zip")

        with open(zip_tmp, "wb") as f:
            for chunk in zip_response.iter_content(chunk_size=8192):
                f.write(chunk)

        # Extract
        log("Extracting plugin...")
        extract_tmp = Path("plugin_extract_tmp")
        if extract_tmp.exists():
            shutil.rmtree(extract_tmp)

        with zipfile.ZipFile(zip_tmp, "r") as zip_ref:
            # SAFETY: Zip Slip Protection
            for member in zip_ref.namelist():
                member_path = os.path.normpath(member)
                if member_path.startswith("..") or member_path.startswith("/"):
                    log(
                        f"Security Warning: Skipping malicious file path in zip: {member}",
                        style="warning",
                    )
                    continue
                zip_ref.extract(member, extract_tmp)

            # GitHub zips have a top-level folder 'user-repo-hash'
            # We want to extract its contents into plugins/repo
            top_folder = zip_ref.namelist()[0].split("/")[0]

        # Move to target
        shutil.move(extract_tmp / top_folder, target_plugin_path)

        # Cleanup
        os.remove(zip_tmp)
        shutil.rmtree(extract_tmp)

        # 1. Verify Manifest and Install Dependencies
        manifest_path = target_plugin_path / "manifest.json"
        if manifest_path.exists():
            log(f"Successfully installed '{plugin_id}'", style="success")
            install_dependencies(target_plugin_path)
            with open(manifest_path, "r") as f:
                data = json.load(f)
                log(f"Plugin Metadata: {data.get('name')} v{data.get('version')}")
        else:
            log(
                f"Warning: Installed plugin '{plugin_id}' is missing a manifest.json. It may not load correctly.",
                style="warning",
            )

        return 0

    except Exception as e:
        log(f"Extraction failed: {e}", style="error")
        return 1


def install_dependencies(plugin_path: Path):
    manifest_path = plugin_path / "manifest.json"
    if not manifest_path.exists():
        return

    try:
        with open(manifest_path, "r") as f:
            data = json.load(f)

        # 1. Handle Python Dependencies
        py_deps = data.get("python_dependencies", [])
        if py_deps:
            log(
                f"Installing {len(py_deps)} Python dependencies for plugin...",
                style="info",
            )
            # USE THE PROJECT'S VENV PYTHON
            python_exe = get_python_executable()
            cmd = [python_exe, "-m", "pip", "install"] + py_deps
            subprocess.check_call(cmd)  # nosec B603

        # 2. Handle JS Dependencies
        js_deps = data.get(
            "npm_dependencies", {}
        )  # Keep key for manifest compat but rename internally
        if js_deps:
            # Install inside the plugin folder for isolation
            target_dir = plugin_path

            # Detect Provider
            config = get_config()
            provider = config.get("frontend_provider", "npm")

            log(
                f"Installing {len(js_deps)} JS packages using '{provider}' in {target_dir} for isolation...",
                style="info",
            )

            # Use plugin's package.json if it exists, otherwise create a temporary one
            pkg_json = target_dir / "package.json"
            if not pkg_json.exists():
                pkg_data = {
                    "name": f"pytron-plugin-{plugin_path.name}",
                    "dependencies": js_deps,
                }
                target_dir.mkdir(parents=True, exist_ok=True)
                pkg_json.write_text(json.dumps(pkg_data, indent=2))

            # Run installation command
            # Check for binary existence
            provider_bin = shutil.which(provider)
            if not provider_bin:
                log(
                    f"Warning: JS Provider '{provider}' not found in PATH. Skipping JS dependencies.",
                    style="warning",
                )
            else:
                # Most managers use 'install', but we should be safe
                install_cmd = "install"
                subprocess.check_call(
                    [provider_bin, install_cmd], cwd=target_dir, shell=False
                )  # nosec B603

    except subprocess.CalledProcessError as e:
        log(f"Dependency installation failed: {e}", style="error")
    except Exception as e:
        log(f"Error processing manifest for dependencies: {e}", style="error")


def plugin_list(args):
    plugins_dir = Path("plugins")
    if not plugins_dir.exists():
        log("No plugins/ directory found.")
        return 0

    print_rule("Installed Plugins")
    found = False
    for item in plugins_dir.iterdir():
        if item.is_dir():
            found = True
            manifest = item / "manifest.json"
            if manifest.exists():
                try:
                    with open(manifest, "r") as f:
                        data = json.load(f)
                    display_name = data.get("name", item.name)
                    version = data.get("version", "unknown")
                    # If the folder name contains a username prefix, show it as the identifier
                    if "_" in item.name:
                        log(
                            f"- [bold teal]{display_name}[/] [dim]({item.name})[/dim] (v{version})",
                            markup=True,
                        )
                    else:
                        log(f"- [bold teal]{display_name}[/] (v{version})", markup=True)
                except Exception:
                    log(f"- {item.name} (Broken Manifest)", style="warning")
            else:
                log(f"- {item.name} (No Manifest)", style="warning")

    if not found:
        log("No plugins installed.")

    return 0


def plugin_uninstall(args):
    target = args.name
    plugins_dir = Path("plugins")
    if not plugins_dir.exists():
        log("No plugins/ directory found.", style="error")
        return 1

    # 1. Try direct match (folder name)
    plugin_path = plugins_dir / target

    # 2. Try match by username.repo format
    if not plugin_path.exists() and "." in target:
        parts = target.split(".")
        plugin_path = plugins_dir / f"{parts[0]}_{parts[1]}"

    # 3. Try fuzzy match by repo name only if unique
    if not plugin_path.exists():
        matches = [
            p
            for p in plugins_dir.iterdir()
            if p.is_dir() and p.name.endswith(f"_{target}")
        ]
        if len(matches) == 1:
            plugin_path = matches[0]
        elif len(matches) > 1:
            log(f"Multiple plugins found matching '{target}':", style="error")
            for m in matches:
                log(f"  - {m.name}")
            log(
                "Please use the full identifier (username.repo or folder_name).",
                style="info",
            )
            return 1

    if plugin_path.exists() and plugin_path.is_dir():
        log(f"Removing plugin: {plugin_path.name}...")
        try:
            shutil.rmtree(plugin_path)
            log("Done.", style="success")
        except Exception as e:
            log(f"Failed to remove plugin: {e}", style="error")
            return 1
    else:
        log(f"Plugin '{target}' not found.", style="error")
    return 0
