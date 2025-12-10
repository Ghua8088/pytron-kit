from __future__ import annotations
import shutil
import subprocess
import json
import sys
from pathlib import Path

def get_venv_python_path(venv_dir: Path = Path('env')) -> Path:
    if sys.platform == 'win32':
        return venv_dir / 'Scripts' / 'python.exe'
    return venv_dir / 'bin' / 'python'

def get_python_executable() -> str:
    venv_python = get_venv_python_path()
    if venv_python.exists():
        return str(venv_python)
    return sys.executable

def get_venv_site_packages(python_exe: str) -> list[str]:
    """
    Get the site-packages directories for the given python executable.
    """
    try:
        # We use a subprocess to ask the venv python where its site-packages are.
        # We use json to safely parse the list.
        cmd = [
            python_exe, 
            '-c', 
            'import site; import json; print(json.dumps(site.getsitepackages()))'
        ]
        output = subprocess.check_output(cmd, text=True).strip()
        return json.loads(output)
    except Exception as e:
        print(f"[Pytron] Warning: Could not determine site-packages for {python_exe}: {e}")
        return []

def locate_frontend_dir(start_dir: Path | None = None) -> Path | None:
    base = (start_dir or Path('.')).resolve()
    if not base.exists():
        return None
    candidates = [base]
    candidates.extend([p for p in base.iterdir() if p.is_dir()])
    for candidate in candidates:
        pkg = candidate / 'package.json'
        if not pkg.exists():
            continue
        try:
            data = json.loads(pkg.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(data.get('scripts'), dict) and 'build' in data['scripts']:
            return candidate.resolve()
    return None


def run_frontend_build(frontend_dir: Path) -> bool | None:
    npm = shutil.which('npm')
    if not npm:
        print('[Pytron] npm not found, skipping frontend build.')
        return None
    print(f"[Pytron] Building frontend at: {frontend_dir}")
    # Ensure Next.js static export-friendly config when applicable
    # Determine if this is a Next.js project and ensure config if so
    is_next = False
    try:
        pkg = json.loads((frontend_dir / 'package.json').read_text())
        if 'next' in pkg.get('dependencies', {}) or 'next' in pkg.get('devDependencies', {}):
            ensure_next_config(frontend_dir)
            patch_nextjs_defaults(frontend_dir) # Patch default template paths
            is_next = True
    except Exception:
        pass

    try:
        # If this is a Next.js project, prefer `npx next build` (and export)
        if is_next:
            print('[Pytron] Detected Next.js project — running `npx next build`.')
            # Run build to create a static `out/` directory (Next.js 13.4+ with output: "export")
            subprocess.run(['npx', 'next', 'build'], cwd=str(frontend_dir), shell=True, check=True)
            return True

        # Fallback to the project's npm build script
        subprocess.run(['npm', 'run', 'build'], cwd=str(frontend_dir), shell=True, check=True)
        return True
    except subprocess.CalledProcessError as exc:
        print(f"[Pytron] Frontend build failed: {exc}")
        return False


def patch_nextjs_defaults(frontend_dir: Path):
    """
    Patches default Next.js template files to use relative paths for static assets.
    This fixes issues where /next.svg resolves to file:///next.svg instead of relative to the HTML file.
    """
    # 1. Patch page.tsx / page.js (Fixes Image src)
    for ext in ['tsx', 'jsx', 'js', 'ts']:
        page_file = frontend_dir / 'src' / 'app' / f'page.{ext}'
        if not page_file.exists():
            page_file = frontend_dir / 'app' / f'page.{ext}' # Older structure
        
        if page_file.exists():
            try:
                content = page_file.read_text(encoding='utf-8')
                new_content = content
                # Replace absolute paths with relative ones
                replacements = {
                    'src="/next.svg"': 'src="./next.svg"',
                    'src="/vercel.svg"': 'src="./vercel.svg"',
                    "src='/next.svg'": "src='./next.svg'",
                    "src='/vercel.svg'": "src='./vercel.svg'",
                }
                for old, new in replacements.items():
                    new_content = new_content.replace(old, new)
                
                if new_content != content:
                    page_file.write_text(new_content, encoding='utf-8')
                    print(f"[Pytron] Patched {page_file.name} to use relative image paths.")
            except Exception as e:
                print(f"[Pytron] Warning: Failed to patch {page_file.name}: {e}")

    # 2. Patch layout.tsx / layout.js (Fixes favicon)
    # Note: Next.js App Router handles favicon via convention (favicon.ico in app/ or public/),
    # but sometimes it's manually referenced in layout or head.
    # However, the default create-next-app usually relies on the file presence.
    # If the user sees 404 for favicon, it might be due to <link rel="icon" href="/favicon.ico"> generated by Next.
    # We can't easily patch the internal generation of that link without a custom Head component or metadata.
    # But if it's in the code:
    for ext in ['tsx', 'jsx', 'js', 'ts']:
        layout_file = frontend_dir / 'src' / 'app' / f'layout.{ext}'
        if not layout_file.exists():
            layout_file = frontend_dir / 'app' / f'layout.{ext}'
            
        if layout_file.exists():
             try:
                content = layout_file.read_text(encoding='utf-8')
                # Check for manual link tags if any (unlikely in new app router but possible)
                if 'href="/favicon.ico"' in content:
                    new_content = content.replace('href="/favicon.ico"', 'href="./favicon.ico"')
                    layout_file.write_text(new_content, encoding='utf-8')
                    print(f"[Pytron] Patched {layout_file.name} to use relative favicon path.")
             except Exception:
                 pass

def ensure_next_config(frontend_dir: Path) -> bool:
    """Ensure a `next.config.js` exists with static-export friendly settings.

    If no `next.config.js` exists, create one with the recommended config.
    If one exists but doesn't already set `output: 'export'`, back it up and overwrite
    with the recommended config. Returns True if a file was created/overwritten,
    False if no change was necessary.
    """
    next_config = frontend_dir / 'next.config.js'
    desired = """/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',          // required to generate static files (out/)
  images: { unoptimized: true }, // so Next won’t rewrite image loaders
  assetPrefix: './',         // makes asset paths relative
};

module.exports = nextConfig;
"""
    try:
        if not next_config.exists():
            next_config.write_text(desired, encoding='utf-8')
            print(f"[Pytron] Created {next_config} to enable static export.")
            return True
        content = next_config.read_text(encoding='utf-8')
        if ("output: 'export'" in content or 'output: "export"' in content) and ("assetPrefix: './'" in content or 'assetPrefix: "./"' in content):
            print(f"[Pytron] {next_config} already configures static export.")
            return False
        # Backup and overwrite to ensure static-friendly config
        backup = frontend_dir / 'next.config.js.bak'
        backup.write_text(content, encoding='utf-8')
        next_config.write_text(desired, encoding='utf-8')
        print(f"[Pytron] Backed up existing next.config.js to {backup} and injected export config.")
        return True
    except Exception as exc:
        print(f"[Pytron] Warning: could not ensure next.config.js: {exc}")
        return False
