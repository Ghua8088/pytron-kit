import sys
import subprocess
import argparse
import shutil
import json
from pathlib import Path
from ..console import (
    log,
    console,
    get_progress,
    print_rule,
    run_command_with_output,
)
from .. import __version__

TEMPLATE_APP = """from pytron import App

def main():
    app = App()
    
    # Expose Python function to Frontend
    @app.expose
    def greet(name):
        return f"Hello, {name}! From Python"

    app.run()

if __name__ == '__main__':
    main()
"""


def get_frontend_runner(provider: str) -> str:
    if provider == "bun":
        return "bunx"
    if provider == "pnpm":
        return "pnpx"
    return "npx"


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve()
    if target.exists():
        log(f"Target '{target}' already exists", style="error")
        return 1

    print_rule(f"Initializing Pytron App: {target.name}")
    log(f"Creating project at: {target}")
    target.mkdir(parents=True)

    # Create app.py
    app_file = target / "app.py"
    app_file.write_text(TEMPLATE_APP, encoding="utf-8")

    # Create settings.json
    is_next = args.template.lower() in ["next", "nextjs"]
    dist_path = "frontend/out/index.html" if is_next else "frontend/dist/index.html"

    # Resolve provider
    provider = getattr(args, "provider", "npm")
    provider_bin = shutil.which(provider)
    if not provider_bin:
        log(f"Warning: '{provider}' not found. Defaulting to 'npm'.", style="warning")
        provider = "npm"

    settings_file = target / "settings.json"
    settings_data = {
        # Identity
        "title": target.name,
        "version": "1.0.0",
        "author": "Your Name",
        "description": "A brief description of your app",
        "copyright": f"Copyright \u00a9 2026 Your Name",
        "pytron_version": __version__,
        # Window Configuration
        "dimensions": [800, 600],
        "min_size": None,
        "max_size": None,
        "resizable": True,
        "frameless": False,
        "fullscreen": False,
        "always_on_top": False,
        "transparent": False,
        "background_color": "#ffffff",
        "start_maximized": False,
        "start_hidden": False,
        "default_context_menu": False,
        # Application
        "url": dist_path,
        "icon": "pytron.ico",
        "engine": "native",  # Options: 'native', 'chrome'
        "single_instance": True,
        "close_to_tray": False,
        "debug": False,
        # Frontend
        "frontend_framework": args.template,
        "frontend_provider": provider,
        "dev_port": None,
        # Plugins
        "plugins_dir": None,
        "plugins": [],
        # Packaging & Build
        "crystal_mode": False,  # High-Security Runtime Audit
        "virtual_entry_point": False,  # Synthesized Entry Point Strategy
        "splash_image": None,
        "force-package": [],
        "include_patterns": [],
        "exclude_patterns": [],
        "macos_plist": {},
        "signing": {},
    }
    settings_file.write_text(json.dumps(settings_data, indent=4))

    # Copy Pytron icon
    try:
        pytron_pkg_dir = Path(__file__).resolve().parent.parent
        default_icon_src = pytron_pkg_dir / "installer" / "pytron.ico"
        if default_icon_src.exists():
            shutil.copy2(default_icon_src, target / "pytron.ico")
            log("Added default Pytron icon", style="success")
    except Exception as e:
        log(f"Warning: Could not copy default icon: {e}", style="warning")

    progress = get_progress()
    progress.start()
    task = progress.add_task("Initializing...", total=100)

    # Initialize Frontend
    if is_next:
        log("Initializing Next.js app...", style="info")
        progress.update(task, description="Creating Next.js App...", completed=10)
        try:
            # npx create-next-app@latest frontend --use-npm --no-git --ts --eslint --no-tailwind --src-dir --app --import-alias "@/*"
            # Using defaults but forcing non-interactive
            runner = "npx"
            if provider == "bun":
                runner = "bunx"
            elif provider == "pnpm":
                runner = "pnpx"

            # Resolve full path for Windows compatibility (npx.cmd)
            runner_path = shutil.which(runner)
            if runner_path:
                runner = runner_path

            cmd = [
                runner,
                "-y",
                "create-next-app@latest",
                "frontend",
                f"--use-{provider}" if provider in ["npm", "pnpm", "yarn"] else "",
                "--no-git",
                "--ts",
                "--eslint",
                "--no-tailwind",
                "--src-dir",
                "--app",
                "--import-alias",
                "@/*",
            ]
            # Remove empty strings if any
            cmd = [c for c in cmd if c]

            # log output while keeping progress bar alive
            run_command_with_output(cmd, cwd=str(target), shell=False)

            progress.update(task, description="Configuring Next.js...", completed=40)
            # Configure Next.js for static export
            # Configure Next.js for static export
            next_config_path = target / "frontend" / "next.config.mjs"
            if not next_config_path.exists():
                next_config_path = target / "frontend" / "next.config.js"

            # Force overwrite with known good config for Pytron
            next_conf_content = """/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  images: { unoptimized: true },
};

export default nextConfig;
"""
            next_config_path.write_text(next_conf_content, encoding="utf-8")
            log(
                "Configured Next.js for static export (forced overwrite)",
                style="success",
            )

            # Add browserslist to package.json for better compatibility
            package_json_path = target / "frontend" / "package.json"
            if package_json_path.exists():
                try:
                    pkg_data = json.loads(package_json_path.read_text())
                    pkg_data["browserslist"] = [
                        ">0.2%",
                        "not dead",
                        "not op_mini all",
                        "not IE 11",
                    ]
                    package_json_path.write_text(json.dumps(pkg_data, indent=2))
                    log("Added browserslist to package.json", style="success")
                except Exception:
                    pass

        except subprocess.CalledProcessError as e:
            log(f"Failed to initialize Next.js app: {e}", style="error")
            progress.stop()  # Ensure stopped if error

    else:
        # Initialize Vite app in frontend folder
        log(f"Initializing Vite {args.template} app...", style="info")
        progress.update(
            task, description=f"Creating Vite {args.template} App...", completed=10
        )
        # Using npx to create vite app non-interactively
        # We use a specific version (5.5.0) to avoid experimental prompts (like rolldown)
        # that appear in newer versions (v6+).
        try:
            runner = get_frontend_runner(provider)
            # Resolve full path for Windows compatibility
            runner_path = shutil.which(runner)
            if runner_path:
                runner = runner_path

            ret = run_command_with_output(
                [
                    runner,
                    "-y",
                    "create-vite@5.5.0",
                    "frontend",
                    "--template",
                    args.template,
                ],
                cwd=str(target),
                shell=False,
            )
            if ret != 0:
                raise subprocess.CalledProcessError(ret, "create-vite")

            # Update package.json first with all needed dependencies and config
            log("Configuring package.json dependencies...", style="dim")
            package_json_path = target / "frontend" / "package.json"
            if package_json_path.exists():
                try:
                    pkg_data = json.loads(package_json_path.read_text())

                    # Ensure sections exist
                    if "dependencies" not in pkg_data:
                        pkg_data["dependencies"] = {}
                    if "devDependencies" not in pkg_data:
                        pkg_data["devDependencies"] = {}

                    # Add pytron-client
                    pkg_data["dependencies"]["pytron-client"] = "^0.1.8"

                    # Add legacy polyfills
                    pkg_data["devDependencies"]["@vitejs/plugin-legacy"] = "^5.4.1"
                    pkg_data["devDependencies"]["terser"] = "^5.31.1"

                    # Add browserslist
                    pkg_data["browserslist"] = [
                        ">0.2%",
                        "not dead",
                        "not op_mini all",
                        "not IE 11",
                    ]

                    package_json_path.write_text(json.dumps(pkg_data, indent=2))
                    log(
                        "Updated package.json with legacy polyfills and pytron-client",
                        style="success",
                    )
                except Exception as e:
                    log(f"Warning: Failed to update package.json: {e}", style="warning")

            # Install ALL dependencies in one go
            log("Installing dependencies...", style="dim")
            progress.update(
                task, description="Installing Dependencies...", completed=40
            )
            # Resolve full path for Windows compatibility
            provider_path = shutil.which(provider)
            if provider_path:
                provider_cmd = provider_path
            else:
                provider_cmd = provider

            ret = run_command_with_output(
                [provider_cmd, "install"],
                cwd=str(target / "frontend"),
                shell=False,
            )
            if ret != 0:
                log(
                    f"Warning: {provider} install failed. You may need to run '{provider} install' manually in the frontend folder.",
                    style="warning",
                )

            # Configure Vite for relative paths (base: './') and legacy polyfills
            # We FORCE overwrite the config to ensure stability, rather than patching.
            vite_config_path = target / "frontend" / "vite.config.js"
            if (target / "frontend" / "vite.config.ts").exists():
                vite_config_path = target / "frontend" / "vite.config.ts"

            # Detect framework plugin based on template arg to ensure we don't break HMR
            framework_plugin_import = ""
            framework_plugin_usage = ""

            if "react" in args.template:
                framework_plugin_import = "import react from '@vitejs/plugin-react'"
                framework_plugin_usage = "react(),"
            elif "vue" in args.template:
                framework_plugin_import = "import vue from '@vitejs/plugin-vue'"
                framework_plugin_usage = "vue(),"
            elif "svelte" in args.template:
                framework_plugin_import = (
                    "import { svelte } from '@sveltejs/vite-plugin-svelte'"
                )
                framework_plugin_usage = "svelte(),"

            vite_conf_content = f"""
import {{ defineConfig }} from 'vite'
import legacy from '@vitejs/plugin-legacy'
import {{ resolve }} from 'path'

{framework_plugin_import}

// Pytron Enforced Config ({args.template})
export default defineConfig({{
  base: './', // Critical for file:// protocol
  plugins: [
    {framework_plugin_usage}
    legacy({{
      targets: ['defaults', 'not IE 11'],
    }}),
  ],
  resolve: {{
    alias: {{
      '@': resolve(__dirname, './src'),
    }},
  }},
}})
"""
            vite_config_path.write_text(vite_conf_content, encoding="utf-8")
            log(
                "Configured Vite for relative paths and legacy polyfills (forced overwrite)",
                style="success",
            )

            # --- INJECT STARTER CODE ---
            if "react" in args.template:
                app_jsx = target / "frontend" / "src" / "App.jsx"
                if not app_jsx.exists():
                    app_jsx = target / "frontend" / "src" / "App.tsx"

                if app_jsx.exists():
                    app_jsx.write_text("""import { useState } from 'react'
import pytron from 'pytron-client'
import './App.css'

function App() {
  const [msg, setMsg] = useState("Click to greet Python ")

  const handleGreet = async () => {
    try {
      const response = await pytron.greet("React Developer")
      setMsg(response)
    } catch (err) {
      console.error(err)
      setMsg("Error: Check console (Is Python running?)")
    }
  }

  return (
    <div style={{ textAlign: "center", marginTop: "50px", fontFamily: "system-ui" }}>
        <h1> Pytron + React</h1>
        <p style={{ fontSize: "1.2rem", color: "#666" }}>{msg}</p>
        <button 
          onClick={handleGreet}
          style={{ padding: "10px 20px", fontSize: "1rem", cursor: "pointer" }}
        >
          Call Backend
        </button>
    </div>
  )
}

export default App
""")
                    log(
                        "Injected React starter code with Pytron Client",
                        style="success",
                    )

            elif "vue" in args.template:
                app_vue = target / "frontend" / "src" / "App.vue"
                if app_vue.exists():
                    app_vue.write_text("""<script setup>
import { ref } from 'vue'
import pytron from 'pytron-client'

const msg = ref("Click to greet Python ")

async function greet() {
  try {
    msg.value = await pytron.greet("Vue Developer")
  } catch (err) {
    console.error(err)
    msg.value = "Error: " + err
  }
}
</script>

<template>
  <div class="container">
    <h1>Pytron + Vue</h1>
    <p class="msg">{{ msg }}</p>
    <button @click="greet">Call Backend</button>
  </div>
</template>

<style scoped>
.container {
  text-align: center;
  margin-top: 50px;
  font-family: system-ui;
}
.msg {
  font-size: 1.2rem;
  color: #666;
}
button {
  padding: 10px 20px;
  font-size: 1rem;
  cursor: pointer;
}
</style>
""")
                    log("Injected Vue starter code with Pytron Client", style="success")

        except subprocess.CalledProcessError as e:
            log(f"Failed to initialize Vite app: {e}", style="error")
            # Fallback to creating directory if failed
            frontend = target / "frontend"
            if not frontend.exists():
                frontend.mkdir()
                (frontend / "index.html").write_text(
                    f"<!doctype html><html><body><h1>Pytron App ({args.template} Init Failed)</h1></body></html>"
                )

    # Create README
    (target / "README.md").write_text(
        f"# My Pytron App\n\nBuilt with Pytron CLI init template ({args.template}).\n\n## Structure\n- `app.py`: Main Python entrypoint\n- `settings.json`: Application configuration\n- `frontend/`: {args.template} Frontend"
    )

    # Create virtual environment
    log("Creating virtual environment...", style="info")
    progress.update(task, description="Creating Virtual Environment...", completed=70)
    env_dir = target / "env"
    try:
        run_command_with_output([sys.executable, "-m", "venv", str(env_dir)])

        # Determine pip path in new env
        if sys.platform == "win32":
            pip_exe = env_dir / "Scripts" / "pip"
        else:
            pip_exe = env_dir / "bin" / "pip"

        log("Installing dependencies in virtual environment...", style="dim")
        progress.update(
            task, description="Installing Python Dependencies...", completed=90
        )
        # Install pytron in the new env.
        run_command_with_output([str(pip_exe), "install", "pytron-kit"])

        # Create requirements.json
        req_data = {"dependencies": ["pytron-kit"]}
        (target / "requirements.json").write_text(json.dumps(req_data, indent=4))

        # Create helper run scripts
        if sys.platform == "win32":
            run_script = target / "run.bat"
            run_script.write_text(
                "@echo off\ncall env\\Scripts\\activate.bat\npython app.py\npause"
            )
        else:
            run_script = target / "run.sh"
            run_script.write_text(
                "#!/bin/bash\nsource env/bin/activate\npython app.py", encoding="utf-8"
            )
            # Make it executable
            try:
                run_script.chmod(run_script.stat().st_mode | 0o111)
            except Exception:
                pass

    except Exception as e:
        log(f"Warning: Failed to set up virtual environment: {e}", style="warning")

    progress.update(task, description="Done!", completed=100)
    progress.stop()

    log("Scaffolded app files:", style="success")
    console.print(f" - {app_file}", style="dim")
    console.print(f" - {settings_file}", style="dim")
    console.print(f" - {target}/frontend", style="dim")

    # Do not print absolute env paths or activation commands here. Printing
    # explicit env activation instructions can lead users to activate the
    # environment and then run `pytron run` from inside the venv which may
    # confuse the CLI env resolution. Provide a concise, platform-agnostic
    # message instead.
    print_rule("Initialization Complete", style="bold green")
    console.print(
        "A virtual environment was created at: [bold]env/[/bold] (project root)."
    )
    console.print("Install dependencies: [bold cyan]pytron install[/bold cyan]")
    console.print(
        "Run the app via the CLI: [bold cyan]pytron run[/bold cyan] (the CLI will prefer env/ when present)"
    )
    return 0
