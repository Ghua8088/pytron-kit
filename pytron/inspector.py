import logging
import traceback
import base64
import time
import os
import platform
from collections import deque
from .serializer import pytron_serialize


class DequeHandler(logging.Handler):
    def __init__(self, maxlen=300):
        super().__init__()
        self.logs = deque(maxlen=maxlen)
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
            )
        )

    def emit(self, record):
        try:
            msg = self.format(record)
            self.logs.append(
                {
                    "time": time.strftime("%H:%M:%S"),
                    "level": record.levelname,
                    "msg": record.getMessage(),
                    "full": msg,
                }
            )
        except Exception:
            self.handleError(record)


class Inspector:
    def __init__(self, app):
        self.app = app
        self.start_time = time.time()
        self.handler = DequeHandler(maxlen=300)
        self.handler.setLevel(logging.DEBUG)

        # Add to the root logger to capture everything
        logging.getLogger().addHandler(self.handler)

        self.ipc_history = deque(maxlen=200)
        self.inspector_window = None

        # Prime psutil for CPU tracking
        self._proc = None
        try:
            import psutil

            self._proc = psutil.Process(os.getpid())
            self._proc.cpu_percent()
        except Exception as e:
            logging.debug(f"Failed to init psutil: {e}")

    def log_ipc(self, name, args, result=None, error=None, duration=0):
        """Called by the bridge when an IPC call occurs."""
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "function": name,
            "args": args,
            "result": pytron_serialize(result) if result is not None else None,
            "error": str(error) if error else None,
            "duration": round(duration * 1000, 2),  # ms
        }
        self.ipc_history.append(entry)

    def get_stats(self):
        """Returns live system and process metrics."""
        try:
            import psutil

            if not self._proc:
                self._proc = psutil.Process(os.getpid())

            # Non-blocking CPU call
            cpu = self._proc.cpu_percent()
            mem = self._proc.memory_info().rss / (1024 * 1024)
            sys_mem = psutil.virtual_memory().percent

            return {
                "process_cpu": cpu,
                "process_mem": round(mem, 2),
                "system_mem": sys_mem,
                "uptime": round(time.time() - self.start_time, 1),
                "pid": os.getpid(),
                "threads": self._proc.num_threads(),
                "platform": f"{platform.system()} {platform.release()}",
            }
        except Exception:
            return {
                "uptime": round(time.time() - self.start_time, 1),
                "pid": os.getpid(),
            }

    def get_app_data(self):
        """Aggregated data for the dashboard."""
        try:
            win_data = []
            for i, w in enumerate(self.app.windows):
                is_vis = True
                try:
                    if hasattr(w, "is_visible") and callable(w.is_visible):
                        is_vis = w.is_visible()
                except Exception as e:
                    logging.debug(f"Failed to check visibility for window {i}: {e}")

                # Use config for more accurate metadata
                config = getattr(w, "config", {})
                win_data.append(
                    {
                        "id": i,
                        "title": config.get("title", f"Window {i}"),
                        "url": config.get("url", "N/A"),
                        "visible": is_vis,
                        "dimensions": config.get("dimensions", [0, 0]),
                    }
                )

            return {
                "state": self.app.state.to_dict(),
                "stats": self.get_stats(),
                "windows": win_data,
                "plugins": getattr(self.app, "plugin_statuses", []),
                "ipc_history": list(self.ipc_history),
            }
        except Exception as e:
            return {"error": str(e), "traceback": traceback.format_exc()}

    def get_logs(self):
        """Returns the captured logs."""
        return list(self.handler.logs)

    def eval_code(self, code):
        """Executes arbitrary Python code in the context of the app."""
        try:
            # Check for special 'console' object or similar?
            # For now, just app/state
            try:
                res = eval(  # nosemgrep
                    code, {"app": self.app, "state": self.app.state, "inspector": self}
                )  # nosec B307
                return {"result": pytron_serialize(res)}
            except SyntaxError:
                exec_globals = {
                    "app": self.app,
                    "state": self.app.state,
                    "inspector": self,
                }
                exec(code, exec_globals)  # nosec B102 # nosemgrep
                return {"result": "Statement executed successfully."}
        except Exception as e:
            return {"error": str(e), "traceback": traceback.format_exc()}

    def toggle(self):
        # Add a more robust check to see if the window is truly alive
        if self.inspector_window:
            try:
                if self.inspector_window.is_alive():
                    self.inspector_window.show()
                    return
                else:
                    self.inspector_window = None
            except Exception:
                self.inspector_window = None

        from .inspector_ui import INSPECTOR_HTML

        try:
            self.inspector_window = self.app.create_window(
                title="Pytron Inspector", width=1200, height=800, debug=True
            )

            self.inspector_window.bind("inspector_get_data", self.get_app_data)
            self.inspector_window.bind("inspector_get_logs", self.get_logs)
            self.inspector_window.bind("inspector_eval", self.eval_code)
            self.inspector_window.bind("inspector_window_action", self.window_action)

            b64_html = base64.b64encode(INSPECTOR_HTML.encode("utf-8")).decode("utf-8")
            data_url = f"data:text/html;base64,{b64_html}"
            self.inspector_window.navigate(data_url)
        except Exception as e:
            logging.error(f"Failed to open inspector: {e}")

    def window_action(self, index, action):
        try:
            win = self.app.windows[index]
            if action == "show":
                win.show()
            elif action == "hide":
                win.hide()
            elif action == "close":
                win.close()
            elif action == "center":
                win.center()
            return True
        except Exception as e:
            return {"error": str(e)}
