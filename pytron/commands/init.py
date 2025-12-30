import argparse
import subprocess
import sys
import shutil
import os
import json
from pathlib import Path
from ..console import log, console, get_progress, print_rule, Rule, run_command_with_output
from .. import __version__

TEMPLATE_APP = '''from pytron import App

def main():
    app = App()
    app.run()

if __name__ == '__main__':
    main()
'''

def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve()
    if target.exists():
        log(f"Target '{target}' already exists", style="error")
        return 1

    print_rule(f"Initializing Pytron App: {target.name}")
    log(f"Creating project at: {target}")
    target.mkdir(parents=True)

    # Create app.py
    app_file = target / 'app.py'
    app_file.write_text(TEMPLATE_APP)

    # Create settings.json
    is_next = args.template.lower() in ['next', 'nextjs']
    dist_path = "frontend/out/index.html" if is_next else "frontend/dist/index.html"
    
    settings_file = target / 'settings.json'
    settings_data = {
        "title": target.name,
        "pytron_version": __version__,
        "frontend_framework": args.template,
        "dimensions":[800, 600],
        "frameless": False,
        "default_context_menu": False,
        "icon": "pytron.ico",
        "url": dist_path,
        "author": "Your Name",
        "description": "A brief description of your app",
        "copyright": "Copyright © 2025 Your Name"
    }
    settings_file.write_text(json.dumps(settings_data, indent=4))

    # Copy Pytron icon
    try:
        pytron_pkg_dir = Path(__file__).resolve().parent.parent
        default_icon_src = pytron_pkg_dir / 'installer' / 'pytron.ico'
        if default_icon_src.exists():
            shutil.copy2(default_icon_src, target / 'pytron.ico')
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
            cmd = ['npx', '-y', 'create-next-app@latest', 'frontend', 
                   '--use-npm', '--no-git', '--ts', '--eslint', '--no-tailwind', '--src-dir', '--app', '--import-alias', '@/*']
            
            # log output while keeping progress bar alive
            run_command_with_output(cmd, cwd=str(target), shell=(sys.platform == 'win32'))
            
            progress.update(task, description="Configuring Next.js...", completed=40)
            # Configure Next.js for static export
            next_config_path = target / 'frontend' / 'next.config.mjs'
            if not next_config_path.exists():
                next_config_path = target / 'frontend' / 'next.config.js'
            
            if next_config_path.exists():
                content = next_config_path.read_text()
                # Simple injection for static export
                if "const nextConfig = {" in content:
                    new_content = content.replace(
                        "const nextConfig = {", 
                        "const nextConfig = {\n  output: 'export',\n  images: { unoptimized: true },"
                    )
                    next_config_path.write_text(new_content)
                    log("Configured Next.js for static export (output: 'export')", style="success")
                else:
                    log("Warning: Could not automatically configure next.config.mjs for static export. Please add output: 'export' manually.", style="warning")
            
            # Add browserslist to package.json for better compatibility
            package_json_path = target / 'frontend' / 'package.json'
            if package_json_path.exists():
                try:
                    pkg_data = json.loads(package_json_path.read_text())
                    pkg_data['browserslist'] = [">0.2%", "not dead", "not op_mini all", "not IE 11"]
                    package_json_path.write_text(json.dumps(pkg_data, indent=2))
                    log("Added browserslist to package.json", style="success")
                except Exception:
                    pass
            
        except subprocess.CalledProcessError as e:
            log(f"Failed to initialize Next.js app: {e}", style="error")
            progress.stop() # Ensure stopped if error
            
    else:
        # Initialize Vite app in frontend folder
        log(f"Initializing Vite {args.template} app...", style="info")
        progress.update(task, description=f"Creating Vite {args.template} App...", completed=10)
        # Using npx to create vite app non-interactively
        # We use a specific version (5.5.0) to avoid experimental prompts (like rolldown)
        # that appear in newer versions (v6+).
        try:
            ret = run_command_with_output(['npx', '-y', 'create-vite@5.5.0', 'frontend', '--template', args.template], 
                                    cwd=str(target), shell=(sys.platform == 'win32'))
            if ret != 0:
                raise subprocess.CalledProcessError(ret, "create-vite")
            
            # Update package.json first with all needed dependencies and config
            log("Configuring package.json dependencies...", style="dim")
            package_json_path = target / 'frontend' / 'package.json'
            if package_json_path.exists():
                try:
                    pkg_data = json.loads(package_json_path.read_text())
                    
                    # Ensure sections exist
                    if 'dependencies' not in pkg_data: pkg_data['dependencies'] = {}
                    if 'devDependencies' not in pkg_data: pkg_data['devDependencies'] = {}
                    
                    # Add pytron-client
                    pkg_data['dependencies']['pytron-client'] = '^0.1.8'
                    
                    # Add legacy polyfills
                    pkg_data['devDependencies']['@vitejs/plugin-legacy'] = '^5.4.1'
                    pkg_data['devDependencies']['terser'] = '^5.31.1'
                    
                    # Add browserslist
                    pkg_data['browserslist'] = [">0.2%", "not dead", "not op_mini all", "not IE 11"]
                    
                    package_json_path.write_text(json.dumps(pkg_data, indent=2))
                    log("Updated package.json with legacy polyfills and pytron-client", style="success")
                except Exception as e:
                    log(f"Warning: Failed to update package.json: {e}", style="warning")

            # Install ALL dependencies in one go
            log("Installing dependencies...", style="dim")
            progress.update(task, description="Installing Dependencies...", completed=40)
            ret = run_command_with_output(['npm', 'install'], cwd=str(target / 'frontend'), shell=(sys.platform == 'win32'))
            if ret != 0:
                log("Warning: npm install failed. You may need to run 'npm install' manually in the frontend folder.", style="warning")

            # Configure Vite for relative paths (base: './') and legacy polyfills
            vite_config_path = target / 'frontend' / 'vite.config.js'
            if not vite_config_path.exists():
                vite_config_path = target / 'frontend' / 'vite.config.ts'
            
            if vite_config_path.exists():
                content = vite_config_path.read_text()
                
                # Add legacy plugin import if missing
                if "import legacy from '@vitejs/plugin-legacy'" not in content:
                    content = "import legacy from '@vitejs/plugin-legacy'\n" + content
                
                if "defineConfig({" in content:
                    # Add base: './'
                    if "base:" not in content:
                        content = content.replace(
                            "defineConfig({", 
                            "defineConfig({\n  base: './',"
                        )
                    
                    # Add legacy plugin to plugins array
                    if "plugins: [" in content:
                        if "legacy(" not in content:
                            content = content.replace(
                                "plugins: [",
                                "plugins: [\n    legacy({\n      targets: ['defaults', 'not IE 11'],\n    }),"
                            )
                    else:
                        # Fallback for when plugins array is missing
                        content = content.replace(
                            "defineConfig({",
                            "defineConfig({\n  plugins: [\n    legacy({\n      targets: ['defaults', 'not IE 11'],\n    }),\n  ],"
                        )
                
                vite_config_path.write_text(content)
                log("Configured Vite for relative paths and legacy polyfills", style="success")
            else:
                # Create a default vite.config.js for templates that don't have one (like vanilla)
                vite_config_path = target / 'frontend' / 'vite.config.js'
                vite_config_path.write_text("import { defineConfig } from 'vite'\nimport legacy from '@vitejs/plugin-legacy'\n\nexport default defineConfig({\n  base: './',\n  plugins: [\n    legacy({\n      targets: ['defaults', 'not IE 11'],\n    }),\n  ],\n})\n")
                log("Created Vite config for relative paths and legacy polyfills", style="success")
            
        except subprocess.CalledProcessError as e:
            log(f"Failed to initialize Vite app: {e}", style="error")
            # Fallback to creating directory if failed
            frontend = target / 'frontend'
            if not frontend.exists():
                frontend.mkdir()
                (frontend / 'index.html').write_text(f'<!doctype html><html><body><h1>Pytron App ({args.template} Init Failed)</h1></body></html>')

    # Create README
    (target / 'README.md').write_text(f'# My Pytron App\n\nBuilt with Pytron CLI init template ({args.template}).\n\n## Structure\n- `app.py`: Main Python entrypoint\n- `settings.json`: Application configuration\n- `frontend/`: {args.template} Frontend')

    # Create virtual environment
    log("Creating virtual environment...", style="info")
    progress.update(task, description="Creating Virtual Environment...", completed=70)
    env_dir = target / 'env'
    try:
        run_command_with_output([sys.executable, '-m', 'venv', str(env_dir)])
        
        # Determine pip path in new env
        if sys.platform == 'win32':
            pip_exe = env_dir / 'Scripts' / 'pip'
            python_exe = env_dir / 'Scripts' / 'python'
            activate_script = env_dir / 'Scripts' / 'activate'
        else:
            pip_exe = env_dir / 'bin' / 'pip'
            python_exe = env_dir / 'bin' / 'python'
            activate_script = env_dir / 'bin' / 'activate'
            
        log("Installing dependencies in virtual environment...", style="dim")
        progress.update(task, description="Installing Python Dependencies...", completed=90)
        # Install pytron in the new env. 
        run_command_with_output([str(pip_exe), 'install', 'pytron-kit'])
        
        # Create requirements.json
        req_data = {"dependencies": ["pytron-kit"]}
        (target / 'requirements.json').write_text(json.dumps(req_data, indent=4))
        
        # Create helper run scripts
        if sys.platform == 'win32':
            run_script = target / 'run.bat'
            run_script.write_text('@echo off\ncall env\\Scripts\\activate.bat\npython app.py\npause')
        else:
            run_script = target / 'run.sh'
            run_script.write_text('#!/bin/bash\nsource env/bin/activate\npython app.py')
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
    console.print(f' - {app_file}', style="dim")
    console.print(f' - {settings_file}', style="dim")
    console.print(f' - {target}/frontend', style="dim")

    # Do not print absolute env paths or activation commands here. Printing
    # explicit env activation instructions can lead users to activate the
    # environment and then run `pytron run` from inside the venv which may
    # confuse the CLI env resolution. Provide a concise, platform-agnostic
    # message instead.
    print_rule("Initialization Complete", style="bold green")
    console.print('A virtual environment was created at: [bold]env/[/bold] (project root).')
    console.print('Install dependencies: [bold cyan]pytron install[/bold cyan]')
    console.print('Run the app via the CLI: [bold cyan]pytron run[/bold cyan] (the CLI will prefer env/ when present)')
    return 0
