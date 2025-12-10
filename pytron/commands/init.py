import argparse
import subprocess
import sys
import os
import json
from pathlib import Path
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
        print(f"Target '{target}' already exists")
        return 1

    print(f"Creating new Pytron app at: {target}")
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
        "url": dist_path
    }
    settings_file.write_text(json.dumps(settings_data, indent=4))

    # Initialize Frontend
    if is_next:
        print("Initializing Next.js app...")
        try:
            # npx create-next-app@latest frontend --use-npm --no-git --ts --eslint --no-tailwind --src-dir --app --import-alias "@/*"
            # Using defaults but forcing non-interactive
            cmd = ['npx', '-y', 'create-next-app@latest', 'frontend', 
                   '--use-npm', '--no-git', '--ts', '--eslint', '--no-tailwind', '--src-dir', '--app', '--import-alias', '@/*']
            subprocess.run(cmd, cwd=str(target), shell=True, check=True)
            
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
                    print("Configured Next.js for static export (output: 'export')")
                else:
                    print("Warning: Could not automatically configure next.config.mjs for static export. Please add output: 'export' manually.")
            
        except subprocess.CalledProcessError as e:
            print(f"Failed to initialize Next.js app: {e}")
            
    else:
        # Initialize Vite app in frontend folder
        print(f"Initializing Vite {args.template} app...")
        # Using npx to create vite app non-interactively
        # We use a specific version (5.5.0) to avoid experimental prompts (like rolldown)
        # that appear in newer versions (v6+).
        try:
            subprocess.run(['npx', '-y', 'create-vite@5.5.0', 'frontend', '--template', args.template], cwd=str(target), shell=True, check=True)
            
            # Install dependencies including pytron-client
            print("Installing dependencies...")
            subprocess.run(['npm', 'install'], cwd=str(target / 'frontend'), shell=True, check=True)
            
            print("Installing pytron-client...")
            subprocess.run(['npm', 'install', 'pytron-client'], cwd=str(target / 'frontend'), shell=True, check=True)

            # Configure Vite for relative paths (base: './')
            vite_config_path = target / 'frontend' / 'vite.config.js'
            if not vite_config_path.exists():
                vite_config_path = target / 'frontend' / 'vite.config.ts'
            
            if vite_config_path.exists():
                content = vite_config_path.read_text()
                if "base:" not in content and "defineConfig({" in content:
                    new_content = content.replace(
                        "defineConfig({", 
                        "defineConfig({\n  base: './',"
                    )
                    vite_config_path.write_text(new_content)
                    print("Configured Vite for relative paths (base: './')")
            
        except subprocess.CalledProcessError as e:
            print(f"Failed to initialize Vite app: {e}")
            # Fallback to creating directory if failed
            frontend = target / 'frontend'
            if not frontend.exists():
                frontend.mkdir()
                (frontend / 'index.html').write_text(f'<!doctype html><html><body><h1>Pytron App ({args.template} Init Failed)</h1></body></html>')

    # Create README
    (target / 'README.md').write_text(f'# My Pytron App\n\nBuilt with Pytron CLI init template ({args.template}).\n\n## Structure\n- `app.py`: Main Python entrypoint\n- `settings.json`: Application configuration\n- `frontend/`: {args.template} Frontend')

    # Create virtual environment
    print("Creating virtual environment...")
    env_dir = target / 'env'
    try:
        subprocess.run([sys.executable, '-m', 'venv', str(env_dir)], check=True)
        
        # Determine pip path in new env
        if sys.platform == 'win32':
            pip_exe = env_dir / 'Scripts' / 'pip'
            python_exe = env_dir / 'Scripts' / 'python'
            activate_script = env_dir / 'Scripts' / 'activate'
        else:
            pip_exe = env_dir / 'bin' / 'pip'
            python_exe = env_dir / 'bin' / 'python'
            activate_script = env_dir / 'bin' / 'activate'
            
        print("Installing dependencies in virtual environment...")
        # Install pytron in the new env. 
        subprocess.run([str(pip_exe), 'install', 'pytron-kit'], check=True)
        
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
        print(f"Warning: Failed to set up virtual environment: {e}")

    print('Scaffolded app files:')
    print(f' - {app_file}')
    print(f' - {settings_file}')
    print(f' - {target}/frontend')

    # Do not print absolute env paths or activation commands here. Printing
    # explicit env activation instructions can lead users to activate the
    # environment and then run `pytron run` from inside the venv which may
    # confuse the CLI env resolution. Provide a concise, platform-agnostic
    # message instead.
    print('A virtual environment was created at: env/ (project root).')
    print('Install dependencies: pytron install')
    print('Run the app via the CLI: pytron run (the CLI will prefer env/ when present)')
    return 0
