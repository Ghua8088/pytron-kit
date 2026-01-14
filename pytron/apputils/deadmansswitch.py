import sys
import time
import os
import threading
import signal
import logging


class DeadMansSwitch:
    """
    Ensures that if the UI process (Child) dies, the Backend (Parent) commits seppuku immediately.
    Preventing zombie python processes in the background.
    """

    def __init__(self, ui_process):
        """
        ui_process: The subprocess.Popen object of electron.exe or webview
        """
        self.proc = ui_process
        self.running = True
        self.logger = logging.getLogger("Pytron.DeadMansSwitch")
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()

    def _monitor(self):
        while self.running:
            try:
                # 1. Check if Child (UI) is alive
                if self.proc.poll() is not None:
                    self.logger.warning(
                        f"UI Process {self.proc.pid} died. Exiting backend..."
                    )
                    self.kill_backend()

                # 2. Check if Parent (Launcher) is alive
                # (Only needed if Pytron itself is launched by another tool)
                # if os.getppid() == 1: # On Linux, adopted by init
                #     self.kill_backend()

                time.sleep(1)  # Low overhead polling
            except Exception:
                # If we can't poll, something is wrong
                self.kill_backend()

    def kill_backend(self):
        self.running = False
        self.logger.critical("Dead Man's Switch Triggered.")
        # Hard exit to ensure we don't hang on cleanup
        os._exit(0)
