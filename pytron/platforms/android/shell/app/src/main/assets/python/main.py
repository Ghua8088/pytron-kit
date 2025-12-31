import sys
import os
import json
import time

# --- 1. SETUP PATHS ---
current_dir = os.path.dirname(os.path.abspath(__file__))
# Ensure current dir is first so we can import 'app'
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

site_packages = os.path.join(current_dir, "site-packages")
if site_packages not in sys.path:
    sys.path.append(site_packages)

import _pytron_android


# --- HELPER: Send Logs to Android Logcat ---
def log(msg):
    _pytron_android.send_to_android(
        json.dumps({"method": "log", "args": {"message": str(msg)}})
    )


def main():
    try:
        log("Booting Pytron Bootstrap...")

        # -----------------------------------------------------
        # 1. FIX SHARED LIBRARIES (Critical for Android)
        # -----------------------------------------------------
        # (Simplified: We assume your static build is good,
        # but adding lib-dynload to path is safe)
        lib_dynload = os.path.join(current_dir, "lib-dynload")
        if os.path.exists(lib_dynload) and lib_dynload not in sys.path:
            sys.path.insert(1, lib_dynload)

        # Also check Lib/lib-dynload (standard structure)
        lib_dynload_std = os.path.join(current_dir, "Lib", "lib-dynload")
        if os.path.exists(lib_dynload_std) and lib_dynload_std not in sys.path:
            sys.path.insert(1, lib_dynload_std)

        log(f"sys.path: {sys.path}")

        # -----------------------------------------------------
        # 2. LAUNCH USER APP (app.py)
        # -----------------------------------------------------
        log(" Launching app.py...")

        import app  # <--- THIS IS THE KEY!

        if hasattr(app, "main"):
            # This will run app.main(), which calls app.expose() and app.run()
            # On Android, app.run() is non-blocking (returns immediately)
            app.main()
            log(" app.main() executed successfully.")
        else:
            log(" Error: app.py has no main() function")

        # -----------------------------------------------------
        # 3. KEEP ALIVE LOOP
        # -----------------------------------------------------
        # Since app.run() returns immediately on Android, we must
        # keep the Python thread alive so callbacks can fire.
        log(" Entering Keep-Alive Loop (Listening for Events)...")
        while True:
            time.sleep(1)

    except Exception as e:
        import traceback

        tb = traceback.format_exc()
        log(f" CRASH: {tb}")
        _pytron_android.send_to_android(
            json.dumps(
                {
                    "method": "message_box",
                    "args": {"title": "Python Crash", "message": f"{str(e)}\n\n{tb}"},
                }
            )
        )


if __name__ == "__main__":
    main()
