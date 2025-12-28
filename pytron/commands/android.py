
import os
import shutil
import subprocess
import sys
import time
import glob
import zipfile
import importlib.metadata
from ..platforms.android.builder import AndroidBuilder
from ..console import log, console, get_progress, print_rule, run_command_with_output
import json
def run_command(cmd, cwd=None, env=None):
    # console.print(f"[dim][{cwd or '.'}] $ {' '.join(cmd)}[/dim]")
    return run_command_with_output(cmd, cwd=cwd, env=env, style="dim", shell=True)

def cmd_android(args):
    action = args.action
    
    # Paths
    # Current project dir (where the user runs the command)
    project_root = os.getcwd()
    
    # The 'Template' is the shell we just built in the library
    # We find it relative to this file
    this_file = os.path.abspath(__file__) # pytron/commands/android.py
    pytron_root = os.path.dirname(os.path.dirname(this_file)) # pytron/
    template_dir = os.path.join(pytron_root, 'platforms', 'android', 'shell')
    
    # Target android directory in user project
    target_android_dir = os.path.join(project_root, 'android')
    
    if action == 'init':
        if os.path.exists(target_android_dir):
            if not args.force:
                log("Android folder already exists. Use --force to overwrite.", style="warning")
                return
            shutil.rmtree(target_android_dir)
        
        log(f"Copying Android template to {target_android_dir}...")
        
        # Helper to ignore some build files
        def ignore_patterns(path, names):
            return [n for n in names if n in ['build', '.gradle', '.idea', 'local.properties']]

        shutil.copytree(template_dir, target_android_dir, ignore=ignore_patterns)
        
        # Create local.properties with SDK location if ANDROID_HOME is set
        sdk_dir = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
        if sdk_dir:
            with open(os.path.join(target_android_dir, 'local.properties'), 'w') as f:
                # Escape backslashes for Windows
                sdk_dir_safe = sdk_dir.replace('\\', '\\\\')
                f.write(f"sdk.dir={sdk_dir_safe}")
                
        log("Android project initialized!", style="success")
        
    elif action == 'reset':
        if os.path.exists(target_android_dir):
            log(f"Removing existing Android folder: {target_android_dir}", style="warning")
            shutil.rmtree(target_android_dir)
        
        # Call init logic internally
        # We construct a mock args object or just invoke init directly if we refactored
        # But cleanest is recursively calling cmd_android with 'init' action
        # However, args is an argparse config. Let's just copy-paste the core init logic or refactor.
        # Actually, simpler: just run the init block from here. 
        
        log(f"Re-creating Android template at {target_android_dir}...")
        
        def ignore_patterns(path, names):
            return [n for n in names if n in ['build', '.gradle', '.idea', 'local.properties']]

        shutil.copytree(template_dir, target_android_dir, ignore=ignore_patterns)
        
        sdk_dir = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
        if sdk_dir:
            with open(os.path.join(target_android_dir, 'local.properties'), 'w') as f:
                sdk_dir_safe = sdk_dir.replace('\\', '\\\\')
                f.write(f"sdk.dir={sdk_dir_safe}")
                
        log("Android project reset complete!", style="success")

        
    elif action == 'sync':
        # Copies current project assets to the android project
        if not os.path.exists(target_android_dir):
            log("Android project not found. Run 'pytron android init' first.", style="error")
            return

        assets_dir = os.path.join(target_android_dir, 'app', 'src', 'main', 'assets')
        python_dir = os.path.join(assets_dir, 'python')
        www_dir = os.path.join(assets_dir, 'www')
        site_packages_dir = os.path.join(python_dir, 'site-packages')
        os.makedirs(site_packages_dir, exist_ok=True)
        
        log(f"Syncing to {assets_dir}...")
        
        # 1. Frontend (www)
        # Search for standard build output locations
        frontend_candidates = [
            os.path.join(project_root, 'frontend', 'dist'),
            os.path.join(project_root, 'frontend', 'build'),
            os.path.join(project_root, 'dist'),
            os.path.join(project_root, 'build'),
        ]
        
        frontend_src = None
        for cand in frontend_candidates:
            if os.path.exists(cand) and os.path.isdir(cand):
                frontend_src = cand
                break
        
        # Clean existing www
        if os.path.exists(www_dir): shutil.rmtree(www_dir)
        
        if frontend_src:
            console.print(f"  [Frontend] Found at {os.path.relpath(frontend_src, project_root)}", style="dim")
            console.print(f"  [Frontend] Copying to assets/www...", style="dim")
            shutil.copytree(frontend_src, www_dir)
        else:
            console.print("  [Frontend] No built frontend found (checked frontend/dist, dist, etc). Creating empty www.", style="warning")
            os.makedirs(www_dir, exist_ok=True)
            with open(os.path.join(www_dir, 'index.html'), 'w') as f:
                f.write('<html><body><h1>Pytron App</h1><p>Frontend not found. Run build!</p></body></html>')
            
        # 2. Python Backend
        # Copy essentially the whole current folder except excluded items
        console.print("  [Backend]  Copying Python backend...", style="dim")
        
        # Items to IGNORE in the root
        ignore_list = [
            'android', 'node_modules', '.git', '__pycache__', 'dist', 'build', 
            'frontend', '.idea', '.vscode', 'venv', 'env', '.gradle'
        ]
        
        for item in os.listdir(project_root):
            if item in ignore_list or item.startswith('.'):
                continue
                
            src = os.path.join(project_root, item)
            dst = os.path.join(python_dir, item)
            
            # Skip if it is the target android dir itself (redundancy check)
            if os.path.abspath(src) == os.path.abspath(target_android_dir):
                continue

            if os.path.isfile(src):
                # Only copy python-related files or config
                if src.endswith(('.py', '.json', '.yaml', '.toml', '.env')):
                    shutil.copy2(src, dst)
            elif os.path.isdir(src):
                # Recursive copy for submodules/packages
                if os.path.exists(dst): shutil.rmtree(dst)
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))

        # 2b. Vendor Dependencies (venv site-packages)
        # We need to copy packages from the local env to android
        # Try to find 'env' or 'venv'
        venv_dir = None
        for vname in ['env', 'venv', '.venv']:
             vpath = os.path.join(project_root, vname)
             if os.path.exists(vpath) and os.path.isdir(vpath):
                 venv_dir = vpath
                 break
        
        if venv_dir:
             # Find site-packages
             # Windows: env/Lib/site-packages
             # Unix: env/lib/pythonX.Y/site-packages
             sp_candidates = [
                 os.path.join(venv_dir, 'Lib', 'site-packages'),
             ]
             # Unix check
             lib_unix = os.path.join(venv_dir, 'lib')
             if os.path.exists(lib_unix):
                 for d in os.listdir(lib_unix):
                     if d.startswith('python'):
                         sp_candidates.append(os.path.join(lib_unix, d, 'site-packages'))
            
             source_sp = None
             for cand in sp_candidates:
                 if os.path.exists(cand):
                     source_sp = cand
                     break
             
             if source_sp:
                 console.print(f"  [Deps]     Copying dependencies from {os.path.relpath(source_sp, project_root)}...", style="dim")
                 # Copy everything except pip, setuptools, wheel, pkg_resources, __pycache__
                 # And pytron (we handle it specifically later)
                 ignore_deps = ['pip', 'setuptools', 'wheel', 'pkg_resources', 'pytron', '_distutils_hack']
                 
                 for item in os.listdir(source_sp):
                     if item.startswith('.') or item == '__pycache__': continue
                     if item in ignore_deps: continue
                     if item.endswith('.dist-info'): continue # Skip metadata for now to save space/time? Actually needed for importlib.metadata
                     
                     # Actually we NEED dist-info for importlib.metadata to work in step 5!
                     # So let's keep it.
                     
                     if any(item.startswith(x) for x in ignore_deps): continue

                     src = os.path.join(source_sp, item)
                     dst = os.path.join(site_packages_dir, item) # assets/python/site-packages
                     
                     if os.path.isdir(src):
                         if os.path.exists(dst): shutil.rmtree(dst)
                         shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                     else:
                         shutil.copy2(src, dst)
        else:
             console.print("  [Deps]     No virtual environment found (checked env, venv). Skipping dependency copy.", style="warning")
                
        # 3. Vendor Pytron Library
        # Check if we are running in Dev Mode (project_root contains pytron package source)
        local_pytron_source = None
        
        # Candidate 1: Inside current project? (unlikely but possible)
        cand1 = os.path.join(project_root, 'pytron')
        
        # Candidate 2: Sibling directory? (d:\playground\test-android -> d:\playground\pytron)
        # This is the Repo Root
        cand2_repo = os.path.join(os.path.dirname(project_root), 'pytron')
        # This is the Package Root
        cand2_pkg = os.path.join(cand2_repo, 'pytron')
        
        if os.path.exists(cand1) and os.path.exists(os.path.join(cand1, '__init__.py')):
             local_pytron_source = cand1
        elif os.path.exists(cand2_pkg) and os.path.exists(os.path.join(cand2_pkg, '__init__.py')):
             local_pytron_source = cand2_pkg
        elif os.path.exists(os.path.join(pytron_root, '__init__.py')):
             # Fallback to the code running this command (might be installed or local)
             local_pytron_source = pytron_root

        # Decide source
        # We check if local_pytron_source is NOT the system site-packages to label it "LOCAL"
        import site
        is_dev = False
        if local_pytron_source:
             if local_pytron_source == cand1 or local_pytron_source == cand2_pkg:
                  is_dev = True
        
        if local_pytron_source and os.path.exists(local_pytron_source) and is_dev:
             pytron_pkg_dir = local_pytron_source
             console.print(f"  [Vendor]   Development Mode: Copying pytron library from LOCAL source: {pytron_pkg_dir}", style="bold blue")
        else:
             # Fallback to standard import mechanism (safest for installed users)
             import pytron
             pytron_pkg_dir = os.path.dirname(pytron.__file__)
             console.print(f"  [Vendor]   Copying pytron library from INSTALLED package: {pytron_pkg_dir}", style="dim")

        
        target_pytron_dir = os.path.join(site_packages_dir, 'pytron')
        
        if os.path.exists(target_pytron_dir):
            shutil.rmtree(target_pytron_dir)
            
        # Ignore 'dependancies' (heavy dlls) and standard cruft
        shutil.copytree(pytron_pkg_dir, target_pytron_dir, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'installer', 'commands', 'dependancies'))
        
        # AGGRESSIVE CLEANUP: Remove platform implementations from device
        # We only need 'interface.py' and '__init__.py' in platforms
        # Everything else (windows, linux, darwin, especially ANDROID/SHELL) should be purged
        target_platforms = os.path.join(target_pytron_dir, 'platforms')
        if os.path.exists(target_platforms):
            for item in os.listdir(target_platforms):
                if item.endswith('.py') or item == '__pycache__': continue
                # Delete checking it is a dir
                p_item = os.path.join(target_platforms, item)
                if os.path.isdir(p_item):
                    shutil.rmtree(p_item)
            console.print("  [Vendor]   Pruned 'platforms' directory (removed shell templates/native impls).", style="dim")
        
        # We exclude heavy submodules that aren't needed on Android runtime to save space
        # e.g. 'installer' (PyInstaller stuff), 'commands' (CLI stuff), 'platforms' (except android base?)
        # Actually 'platforms' contains core logic, so let's be careful.
        # But definitely don't need 'nsis-setup.exe' etc.
        
        # 4. Unzip Standard Library & Fix .so files (User Request)
        # We do this at build time to avoid runtime unzip and to fix filenames
        python_zip = os.path.join(python_dir, 'python314.zip')
        if os.path.exists(python_zip):
            console.print(f"  [StdLib]   Unzipping {python_zip}...", style="dim")
            try:
                with zipfile.ZipFile(python_zip, 'r') as zip_ref:
                    zip_ref.extractall(python_dir)
                
                console.print("  [StdLib]   Extraction complete. Removing zip.", style="dim")
                os.remove(python_zip)
                

            except Exception as e:
                log(f"  [StdLib]   Error unzipping: {e}", style="error")

        # 4b. ALWAYS Fix .so filenames (Shared Libraries)
        # We do this regardless of whether we just unzipped or if it was already there
        search_paths = [
            os.path.join(python_dir, 'Lib', 'lib-dynload'),
            os.path.join(python_dir, 'lib-dynload')
        ]
        
        for lib_dynload in search_paths:
            if os.path.exists(lib_dynload):
                console.print(f"  [Fixes]    Scanning for .so files in {os.path.basename(lib_dynload)}...", style="dim")
                count = 0
                for f in os.listdir(lib_dynload):
                     if ".cpython-" in f and f.endswith(".so"):
                         # e.g. _struct.cpython-313-android-x86_64.so -> _struct.so
                         parts = f.split(".cpython-")
                         simple_name = parts[0] + ".so"
                         src = os.path.join(lib_dynload, f)
                         dst = os.path.join(lib_dynload, simple_name)
                         
                         if not os.path.exists(dst):
                             try:
                                 os.rename(src, dst)
                                 count += 1
                             except Exception as e:
                                 console.print(f"             Failed rename {f}: {e}", style="error")
                if count > 0:
                    console.print(f"             Renamed {count} shared libraries for Android compatibility.", style="dim")
                
                # Verify critical modules
                critical_modules = ['_random', '_ctypes', '_socket', '_ssl']
                for mod in critical_modules:
                    if os.path.exists(os.path.join(lib_dynload, f"{mod}.so")):
                         console.print(f"             [OK] Found critical module: {mod}.so", style="success")
                    else:
                         console.print(f"             [WARNING] Missing critical module: {mod}.so (Runtime fails likely)", style="warning")


        # 5. Native Extensions Handling
        # We must re-compile any C-extensions for ARM64 because we copied x86/Windows binaries.
        # Inverted Logic: Only scan if --native is explicitly passed
        # We wrap the logic in a simple check, but indentation for the big block below is hard to change in one go.
        # Instead, we will set skip_native internally if args.native is False, but wait, the logic flow is continuous.
        # Let's just indent the initialization variables.

        if not getattr(args, 'native', False):
             console.print("  [Native]   Skipping native extension compilation (Use --native to enable).", style="dim")
        else:
             console.print("  [Native]   Scanning for native extensions to cross-compile...", style="dim")
        
        # We only run the scan loop if native is enabled. But the code below is not indented.
        # Strategically: We can check 'if not native: continue' inside the loop? 
        # But the loop iterates over site-packages.
        # Let's initialize 'should_compile_native = getattr(args, 'native', False)'
        
        should_compile_native = getattr(args, 'native', False)

        # We need the path to headers for the builder


        
        # We need the path to headers for the builder
        # They should be in the shell template we just copied/synced to
        # android/app/src/main/cpp/include
        cpp_include = os.path.join(target_android_dir, 'app', 'src', 'main', 'cpp', 'include')
        
        # Cache dir for wheels to avoid rebuilding every sync
        cache_dir = os.path.join(target_android_dir, 'wheels_cache')
        os.makedirs(cache_dir, exist_ok=True)
        
        # Get mapping of module -> distribution (e.g. cv2 -> opencv-python)
        # We use the current environment because that's where we copied from.
        try:
            packages_dists = importlib.metadata.packages_distributions()
        except Exception:
            packages_dists = {}

        # Scan site-packages
        builder = None 
        
        for item in os.listdir(site_packages_dir):
            if not should_compile_native:
                 break # Skip the loop entirely
                 
            item_path = os.path.join(site_packages_dir, item)
            if not os.path.isdir(item_path):
                continue
                
            if item == "pytron": continue # We handle pytron separately
            
            # Check for binaries
            # recursive glob for .pyd or .so
            # Note: valid android .so files might already be there if we synced before? 
            # But sync deletes and recopies, so they are definitely from host.
            
            has_binary = False
            for root, dirs, files in os.walk(item_path):
                for f in files:
                    if f.endswith('.pyd') or (f.endswith('.so') and 'android' not in f):
                         has_binary = True
                         break
                if has_binary: break
            
            if has_binary:
                dist_name = packages_dists.get(item, [item])[0]
                console.print(f"  [Native]   Found binary extension in '{item}' (Package: {dist_name})", style="info")
                
                # Check Cache
                # Look for wheel starting with dist_name in cache
                # e.g. numpy-*.whl
                cached_wheels = glob.glob(os.path.join(cache_dir, f"{dist_name}-*.whl"))
                
                target_wheel = None
                if cached_wheels:
                    # Filter for Android/Linux/ARM64 wheels
                    valid_wheels = [
                        w for w in cached_wheels 
                        if 'aarch64' in w or 'android' in w or 'linux' in w
                    ]
                    if valid_wheels:
                        valid_wheels.sort(key=os.path.getmtime)
                        target_wheel = valid_wheels[-1]
                        console.print(f"             Using cached wheel: {os.path.basename(target_wheel)}", style="dim")
                
                if not target_wheel:
                    # Build it
                    if not builder:
                         console.print("             Initializing Android NDK Builder...", style="dim")
                         builder = AndroidBuilder(arch='aarch64')
                         if not builder.ndk_info:
                             console.print("             [WARNING] Android NDK or Nano-Sysroot fallback failed. Skipping native build. App may crash.", style="warning")
                             continue
                    
                    console.print(f"             Compiling {dist_name} for Android (ARM64)... This may take a while.", style="info")
                    if builder.build_wheel(dist_name, cache_dir, cpp_include):
                        # Find the generated wheel
                        generated = glob.glob(os.path.join(cache_dir, f"{dist_name}-*.whl"))
                        if generated:
                             valid_generated = [
                                w for w in generated 
                                if 'aarch64' in w or 'android' in w or 'linux' in w
                             ]
                             if valid_generated:
                                 valid_generated.sort(key=os.path.getmtime)
                                 target_wheel = valid_generated[-1]
                    else:
                        console.print(f"             [FAILED] Could not build {dist_name}.", style="error")
                
                if target_wheel:
                     console.print(f"             Installing {dist_name} to assets...", style="dim")
                     try:
                         with zipfile.ZipFile(target_wheel, 'r') as z:
                             z.extractall(site_packages_dir)
                     except Exception as e:
                         console.print(f"             Error installing wheel {os.path.basename(target_wheel)}: {e}", style="error")

        # 6. Finalize Dependency Flattening: Copy flattened libs to jniLibs
        if builder and builder.flattened_libs_dir:
            jni_libs_dir = os.path.join(target_android_dir, 'app', 'src', 'main', 'jniLibs', 'arm64-v8a')
            os.makedirs(jni_libs_dir, exist_ok=True)
            
            console.print(f"  [Native]   Finalizing Dependency Flattening (Syncing jniLibs)...", style="dim")
            # 6a. Copy flattened libraries from builder cache
            for lib_file in os.listdir(builder.flattened_libs_dir):
                src = os.path.join(builder.flattened_libs_dir, lib_file)
                dst = os.path.join(jni_libs_dir, lib_file)
                if not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst):
                    shutil.copy2(src, dst)
                    console.print(f"             Added flattened lib: {lib_file}", style="dim")
            
            # 6b. Ensure libpython is also in jniLibs if provided by builder (Minimalist approach)
            if hasattr(builder, 'ndk_info') and builder.ndk_info and builder.ndk_info.get('lib'):
                 libpy_src = os.path.join(builder.ndk_info['lib'], 'libpython3.14.so')
                 if os.path.exists(libpy_src):
                     shutil.copy2(libpy_src, os.path.join(jni_libs_dir, 'libpython3.14.so'))

        # 7. Inject Project Metadata (Name, Author, Version)
        log("  [Metadata] Injecting project details...", style="dim")
        try:
            settings_path = os.path.join(project_root, 'settings.json')
            config = {}
            if os.path.exists(settings_path):
                 with open(settings_path, 'r') as f: config = json.load(f)
            
            app_title = config.get('title', 'Pytron App')
            author = config.get('author', 'PytronUser')
            version = config.get('version', '1.0.0') # Fallback
            
            # Sanitize for IDs
            safe_title = "".join(c if c.isalnum() else '_' for c in app_title).lower().strip('_')
            safe_author = "".join(c if c.isalnum() else '_' for c in author).lower().strip('_')
            
            # 7a. Update strings.xml (App Name)
            res_val_dir = os.path.join(target_android_dir, 'app', 'src', 'main', 'res', 'values')
            os.makedirs(res_val_dir, exist_ok=True)
            strings_xml = os.path.join(res_val_dir, 'strings.xml')
            
            strings_content = f"""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">{app_title}</string>
</resources>"""
            with open(strings_xml, 'w') as f:
                f.write(strings_content)
                
            # 7b. Update Manifest (Label)
            manifest_path = os.path.join(target_android_dir, 'app', 'src', 'main', 'AndroidManifest.xml')
            if os.path.exists(manifest_path):
                with open(manifest_path, 'r') as f: m_content = f.read()
                
                # Replace hardcoded label with reference
                if 'android:label="Pytron App"' in m_content:
                    m_content = m_content.replace('android:label="Pytron App"', 'android:label="@string/app_name"')
                    with open(manifest_path, 'w') as f: f.write(m_content)
            
            # 7c. Update build.gradle (Version & ID)
            gradle_path = os.path.join(target_android_dir, 'app', 'build.gradle')
            if os.path.exists(gradle_path):
                 with open(gradle_path, 'r') as f: g_lines = f.readlines()
                 
                 new_lines = []
                 app_id = f"com.{safe_author}.{safe_title}"
                 for line in g_lines:
                      if "versionName" in line:
                          new_lines.append(f'        versionName "{version}"\n')
                      elif "applicationId" in line:
                          new_lines.append(f'        applicationId "{app_id}"\n')
                      else:
                          new_lines.append(line)
                          
                 with open(gradle_path, 'w') as f: f.writelines(new_lines)
                 console.print(f"             Updated Metadata: ID={app_id}, Ver={version}, Name={app_title}", style="dim")

            # 7d. Update App Icon
            app_icon_rel = config.get('icon')
            if app_icon_rel:
                app_icon_src = os.path.join(project_root, app_icon_rel)
                if os.path.exists(app_icon_src):
                    console.print(f"             Updating App Icon: {app_icon_rel}", style="dim")
                    # Android template currently uses mipmap-xxhdpi
                    mipmap_dir = os.path.join(target_android_dir, 'app', 'src', 'main', 'res', 'mipmap-xxhdpi')
                    os.makedirs(mipmap_dir, exist_ok=True)
                    
                    # Copy to both standard and round icon names
                    shutil.copy2(app_icon_src, os.path.join(mipmap_dir, 'ic_launcher.png'))
                    shutil.copy2(app_icon_src, os.path.join(mipmap_dir, 'ic_launcher_round.png'))
                else:
                    console.print(f"             Warning: Icon file not found at {app_icon_src}", style="warning")

        except Exception as e:
            console.print(f"             Warning: Failed to inject metadata: {e}", style="warning")

        log("Sync complete.", style="success")

    elif action == 'build':
        if not os.path.exists(target_android_dir):
            log("Run init first.", style="error")
            return

        # Ensure gradlew is executable
        gradlew = os.path.join(target_android_dir, 'gradlew')
        if os.name != 'nt':
            os.chmod(gradlew, 0o755)
            
        is_aab = getattr(args, 'aab', False)
        if is_aab:
            log("Building Android App Bundle (.aab) for Release...", style="info")
            task = 'bundleRelease'
        else:
            log("Building APK (Debug)...", style="info")
            task = 'assembleDebug'

        cmd = [gradlew, task]
        if os.name == 'nt':
            cmd = [gradlew + '.bat', task]
            
        run_command(cmd, cwd=target_android_dir)
        
        if is_aab:
            aab_path = os.path.join(target_android_dir, 'app', 'build', 'outputs', 'bundle', 'release', 'app-release.aab')
             # Note: If not signed, it might be in a different place or named differently, but bundleRelease usually goes here
            if os.path.exists(aab_path):
                log(f"Build Success! AAB: {aab_path}", style="success")
            else:
                # Fallback check for unsigned
                unsigned_aab = os.path.join(target_android_dir, 'app', 'build', 'outputs', 'bundle', 'release', 'app-release-unsigned.aab')
                if os.path.exists(unsigned_aab):
                    log(f"Build Success! AAB (Unsigned): {unsigned_aab}", style="success")
                else:
                    log("Build seemed to succeed but AAB not found?", style="warning")
        else:
            apk_path = os.path.join(target_android_dir, 'app', 'build', 'outputs', 'apk', 'debug', 'app-debug.apk')
            if os.path.exists(apk_path):
                log(f"Build Success! APK: {apk_path}", style="success")
            else:
                log("Build seemed to succeed but APK not found?", style="warning")

    elif action == 'run':
        # Install and Launch
        log("Installing...", style="info")
        # Find the APK - it might have a different name if we customized the build
        apk_path = os.path.join(target_android_dir, 'app', 'build', 'outputs', 'apk', 'debug', 'app-debug.apk')
        run_command(['adb', 'install', '-r', apk_path], cwd=project_root)
        
        log("Launching...", style="info")
        # Dynamically determine Package Name from build.gradle
        pkg_name = "com.pytron.android" # Fallback
        gradle_path = os.path.join(target_android_dir, 'app', 'build.gradle')
        if os.path.exists(gradle_path):
            with open(gradle_path, 'r') as f:
                for line in f:
                    if 'applicationId' in line:
                        pkg_name = line.split('"')[1]
                        break
        
        run_command(['adb', 'shell', 'am', 'start', '-n', f'{pkg_name}/com.pytron.android.MainActivity'])
        
        log("Starting Logcat...", style="info")
        run_command(['adb', 'logcat', '-v', 'time', '*:S', 'Pytron:V', 'PytronNative:V', 'PytronPython:V', 'AndroidRuntime:E', 'chromium:I'])
        
    elif action == 'logcat':
        run_command(['adb', 'logcat', '-v', 'time', '*:S', 'Pytron:V', 'PytronNative:V', 'PytronPython:V', 'AndroidRuntime:E', 'chromium:I'])
