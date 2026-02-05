import sys
import json
import subprocess
import time
import os
import signal
from pathlib import Path
from typing import Set, Dict, List, Optional
from ..console import log


class AppAuditor:
    """
    The 'Crystal' Runtime Auditor.
    Executes the application under PEP 578 surveillance to capture the 'Live Code' universe.
    """

    def __init__(self, script_path: Path, timeout: int = 10):
        self.script_path = script_path
        self.timeout = timeout
        self.manifest_path = script_path.parent / "requirements.lock.json"

    def _generate_surveillance_runner(self) -> str:
        """
        Generates the Python code that acts as the audit harness.
        """
        # We need to robustly handle the user script execution
        escaped_script = (
            str(self.script_path.resolve()).replace("\\", "\\\\").replace('"', '\\"')
        )
        escaped_manifest = (
            str(self.manifest_path.resolve()).replace("\\", "\\\\").replace('"', '\\"')
        )

        return f"""
import sys
import json
import time
import threading
import os
import builtins
from pathlib import Path
import dis

# --- SURVEILLANCE SYSTEM ---
live_modules = set()
live_files = set()

def audit_hook(event, args):
    try:
        if event == "import":
            module, filename, sys_path, sys_meta_path, sys_path_hooks = args
            live_modules.add(module)
            if filename:
                live_files.add(str(filename))
        elif event == "open" and len(args) > 0:
            # Heuristic: file opens might be data assets
            path = args[0]
            if isinstance(path, (str, bytes, os.PathLike)):
                live_files.add(str(path))
    except Exception:
        pass

# --- RECURSIVE ANALYSIS SYSTEM ---
import inspect
visited_functions = set()

def recursive_inspect(func, depth=0):
    if depth > 5: return # Anti-recursion depth limit
    if func in visited_functions: return
    try:
        visited_functions.add(func)
    except:
        return

    try:
        # Helper to trigger standard audit event so our hook captures it
        def _report(name, file=None):
             if name:
                 # Mimic the standard import event arguments: (module, filename, sys.path, sys.meta_path, sys.path_hooks)
                 sys.audit("import", name, file, None, None, None)

        # 1. Handle Classes/Instances
        if inspect.isclass(func) or (not callable(func) and hasattr(func, "__dict__")):
            if hasattr(func, "__module__") and func.__module__:
                 _report(func.__module__)
            for attr_name in dir(func):
                if attr_name.startswith("_"): continue
                try:
                    val = getattr(func, attr_name)
                    if inspect.isfunction(val) or inspect.ismethod(val):
                        recursive_inspect(val, depth+1)
                except: pass
            return

        if hasattr(func, "__module__") and func.__module__:
            _report(func.__module__)
        
        # 2. Inspect closures and globals
        closures = inspect.getclosurevars(func)
        
        for name, value in closures.globals.items():
            if inspect.ismodule(value):
                _report(value.__name__, getattr(value, "__file__", None))
            elif hasattr(value, "__module__") and value.__module__:
                _report(value.__module__)
                if inspect.isfunction(value) or inspect.isclass(value):
                    recursive_inspect(value, depth+1)
                    
        for name, value in closures.nonlocals.items():
            if hasattr(value, "__module__") and value.__module__:
                _report(value.__module__)
                if inspect.isfunction(value):
                    recursive_inspect(value, depth+1)
        
        # 3. Bytecode Analysis
        if hasattr(func, "__code__"):
            for instr in dis.get_instructions(func):
                if instr.opname == "IMPORT_NAME":
                    _report(instr.argval)

    except Exception:
        pass

# --- AUDIT SYSTEM REGISTRATION ---
# CRITICAL: Register the hook defined above
sys.addaudithook(audit_hook)


# --- MANIFEST DUMPER ---
# --- MANIFEST DUMPER ---
def dump_manifest():
    # 1. Trigger App Heuristics (find hidden deps)
    try:
        import gc
        import pytron
        # Look for App in memory
        for obj in gc.get_objects():
            if isinstance(obj, pytron.App):
                print("[Crystal] Triggering App.audit_dependencies()...")
                if hasattr(obj, "audit_dependencies"):
                    obj.audit_dependencies()
                break
    except: pass

    # 2. Load existing lock file to merge
    existing_data = {{"modules": [], "files": []}}
    if os.path.exists(f"{escaped_manifest}"):
        try:
            with open(f"{escaped_manifest}", "r") as f:
                 existing_data = json.load(f)
        except: pass

    # 3. Merge
    final_modules = sorted(list(set(existing_data.get("modules", []) + list(live_modules))))
    final_files = sorted(list(set(existing_data.get("files", []) + list(live_files))))

    data = {{
        "modules": final_modules,
        "files": final_files
    }}
    try:
        with open(f"{escaped_manifest}", "w") as f:
            json.dump(data, f, indent=4)
        print(f"[Crystal] Lock File Updated: {{len(final_modules)}} modules, {{len(final_files)}} files.")
    except Exception as e:
        print(f"[Crystal] Failed to dump manifest: {{e}}")

# Register exit handler to ensure we dump data even if app crashes or exits
import atexit
atexit.register(dump_manifest)


# --- MONKEY PATCHING PYTRON ---
# We want to intercept app.expose calls
def patch_pytron_app():
    try:
        # We try to import pytron from the sys.path (which includes target dir)
        import pytron
        OriginalApp = pytron.App
        
        class AuditedApp(OriginalApp):
            def expose(self, func=None, name=None, secure=False, run_in_thread=True):
                # Trigger analysis immediately if we have a function
                if func is not None:
                    try:
                        n = getattr(func, "__name__", str(func))
                        print(f"[Crystal] Analyzing exposed: {{n}}")
                        recursive_inspect(func)
                    except: pass
                
                # IMPORTANT: Support default args/kwargs to avoid breaking complex @expose usages
                return super().expose(func, name=name, secure=secure, run_in_thread=run_in_thread)
        
        pytron.App = AuditedApp
        print("[Crystal] 'pytron.App.expose' patched successfully.")
    except Exception:
        pass

# Apply patch before running script
patch_pytron_app()

print("[Crystal] Surveillance Active. Launching Target...")

# --- TARGET LAUNCH ---
target_script = "{escaped_script}"
target_dir = os.path.dirname(target_script)

# Set cwd to target script dir to mimic real execution
os.chdir(target_dir)
sys.path.insert(0, target_dir)

try:
    # We use runpy or exec to run the script in this process
    with open(target_script, "r", encoding="utf-8") as f:
        code = compile(f.read(), target_script, "exec")
        exec(code, {{'__name__': '__main__', '__file__': target_script}})
except SystemExit:
    pass
except Exception as e:
    # App usage errors are expected if arguments are missing, but imports should have happened
    print(f"[Crystal] Target Execution Interrupted: {{e}}")

# Dump one last time
dump_manifest()
"""

    def run_audit(self) -> Optional[Dict]:
        """
        Spawns the surveillance subprocess and monitors it.
        Returns the loaded manifest data.
        """
        log("Initializing Crystal Surveillance (PEP 578 Audit)...", style="cyan")
        log("Running imports  please terminate if not needed", style="yellow")
        runner_code = self._generate_surveillance_runner()
        runner_path = self.script_path.parent / "crystal_runner.py"
        runner_path.write_text(runner_code, encoding="utf-8")

        python_exe = sys.executable

        p = None
        try:
            # Run the audit process
            # We don't want to capture output, we want the user to see it if the app prints stuff
            # But we also don't want it to block forever.
            log(
                f"  + Launching {self.script_path.name} in audit mode (Timeout: {self.timeout}s)...",
                style="dim",
            )

            p = subprocess.Popen(
                [python_exe, str(runner_path)],
                cwd=str(self.script_path.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Wait for timeout or completion
            try:
                # We give it some time to initialize imports and settle
                stdout, stderr = p.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                log(
                    "  + Timeout reached. Terminating application to harvest data...",
                    style="dim",
                )
                p.terminate()
                try:
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    p.kill()

            if self.manifest_path.exists():
                try:
                    data = json.loads(self.manifest_path.read_text())
                    log(
                        f"Crystal Audit Complete. Captured {len(data.get('modules', []))} live modules.",
                        style="success",
                    )
                    return data
                except Exception as e:
                    log(f"Failed to parse Crystal manifest: {e}", style="error")
            else:
                log("Crystal Audit failed to produce a manifest.", style="error")
                if p and p.stderr:
                    log(f"Stderr: {p.stderr.read()}", style="dim")

        except Exception as e:
            log(f"Crystal Surveillance Error: {e}", style="error")
        finally:
            # Cleanup
            if runner_path.exists():
                os.remove(runner_path)
            # We keep the manifest for inspection/reference

        return None
