import os
import sys
import json
import logging
import threading
import socket
import uuid
import struct
import subprocess
import tempfile
import ctypes

try:
    from ...dependencies import pytron_native
except ImportError:
    pytron_native = None

logger = logging.getLogger("Pytron.ChromeAdapter")


class ChromeIPCServer:
    """
    A robust Platform-Native IPC server for the Chrome Engine.
    Uses TWO Simplex Named Pipes (Windows) or Sockets (Unix) to avoid Duplex Blocking Deadlocks.

    - Windows:
        - \\\\.\\pipe\\pytron-{uuid}-in  (Python Writes -> Electron Reads)
        - \\\\.\\pipe\\pytron-{uuid}-out (Electron Writes -> Python Reads)
    """

    def __init__(self):
        self.connected = False
        self._lock = threading.Lock()
        self.listening_event = threading.Event()
        self.pipe_path_base = None

        # Native implementation (Rust)
        self._native = None
        if pytron_native:
            try:
                self._native = pytron_native.ChromeIPC()
            except:
                pass

        # Windows Handles (Fallback)
        self._win_in_handle = None
        self._win_out_handle = None

        # Unix Sockets (Fallback)
        self._sock = None

        self.is_windows = sys.platform == "win32"

    def listen(self):
        uid = str(uuid.uuid4())

        if self._native:
            try:
                self.pipe_path_base = self._native.listen(uid)
                self.listening_event.set()
                logger.info(f"Mojo IPC (Native) listening on: {self.pipe_path_base}")
                self._native.wait_for_connection()
                self.connected = True
                logger.info("Mojo Shell connected via Native Pipes")
                return
            except Exception as e:
                logger.warning(
                    f"Native IPC failed to listen ({e}), falling back to ctypes."
                )

        if self.is_windows:
            self._listen_windows(uid)
        else:
            self._listen_unix(uid)

    def _listen_windows(self, uid):
        # We need TWO pipes.
        # 1. OUTBOUND (Python -> Electron)
        # 2. INBOUND (Electron -> Python)

        self.pipe_path_base = f"\\\\.\\pipe\\pytron-{uid}"
        path_in = self.pipe_path_base + "-in"  # We Write
        path_out = self.pipe_path_base + "-out"  # We Read

        PIPE_ACCESS_DUPLEX = 0x00000003  # Node.js expects Duplex even if we use simplex
        PIPE_TYPE_BYTE = 0x00000000
        PIPE_READMODE_BYTE = 0x00000000
        PIPE_WAIT = 0x00000000
        INVALID_HANDLE_VALUE = -1

        # 1. Create IN Pipe (Python Write)
        self._win_in_handle = ctypes.windll.kernel32.CreateNamedPipeW(
            path_in,
            PIPE_ACCESS_DUPLEX,  # 0x3
            PIPE_TYPE_BYTE | PIPE_WAIT,
            1,
            65536,
            65536,
            0,
            None,
        )

        # 2. Create OUT Pipe (Python Read)
        self._win_out_handle = ctypes.windll.kernel32.CreateNamedPipeW(
            path_out,
            PIPE_ACCESS_DUPLEX,  # 0x3
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
            1,
            65536,
            65536,
            0,
            None,
        )

        if (
            self._win_in_handle == INVALID_HANDLE_VALUE
            or self._win_out_handle == INVALID_HANDLE_VALUE
        ):
            raise RuntimeError(f"Failed to create Dual Named Pipes")

        # SIGNAL READY
        self.listening_event.set()
        logger.info(
            f"Mojo IPC listening on Dual Pipes: {self.pipe_path_base} (-in/-out)"
        )

        # BLOCK until client connects to BOTH
        # Electron must connect to IN (Reader) then OUT (Writer)

        # Connect IN
        logger.info("Waiting for Electron to connect to IN pipe...")
        # ConnectNamedPipe returns 0 on failure, non-zero on success.
        # But if client already connected between Create and Connect, it returns 0 and GetLastError=ERROR_PIPE_CONNECTED (535)
        conn_res_in = ctypes.windll.kernel32.ConnectNamedPipe(self._win_in_handle, None)
        if conn_res_in == 0:
            err = ctypes.GetLastError()
            if err != 535:  # ERROR_PIPE_CONNECTED
                logger.error(f"ConnectNamedPipe (IN) failed with error {err}")
                return

        # Connect OUT
        logger.info("Waiting for Electron to connect to OUT pipe...")
        conn_res_out = ctypes.windll.kernel32.ConnectNamedPipe(
            self._win_out_handle, None
        )
        if conn_res_out == 0:
            err = ctypes.GetLastError()
            if err != 535:  # ERROR_PIPE_CONNECTED
                logger.error(f"ConnectNamedPipe (OUT) failed with error {err}")
                return

        self.connected = True
        logger.info("Mojo Shell connected via Dual Pipes")

    def _listen_unix(self, uid):
        # Fallback to single socket for Unix for now unless requested
        self.pipe_path_base = os.path.join(tempfile.gettempdir(), f"pytron-{uid}.sock")
        if os.path.exists(self.pipe_path_base):
            os.remove(self.pipe_path_base)

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(self.pipe_path_base)
        self._sock.listen(1)

        self.listening_event.set()
        logger.info(f"Mojo IPC listening on UDS: {self.pipe_path_base}")

        self.conn, addr = self._sock.accept()
        self.conn.setblocking(True)
        self.connected = True
        logger.info(f"Mojo Shell connected from {addr}")

    def read_loop(self, callback):
        if self._native:
            try:
                # The native read loop runs in its own thread and calls back to Python
                self._native.start_read_loop(callback)
                # We need to block here like the original read_loop did, to keep the thread alive
                # or until disconnect.
                while self.connected:
                    threading.Event().wait(1.0)
                return
            except Exception as e:
                logger.error(f"Native IPC Read Loop Error: {e}")
                self.connected = False
                return

        while self.connected:
            try:
                # 1. Read 4-byte Header
                header = self._recv_bytes(4)
                if not header or len(header) != 4:
                    break
                msg_len = struct.unpack("<I", header)[0]

                # 2. Read Body
                body = self._recv_bytes(msg_len)
                if not body or len(body) != msg_len:
                    break

                # 3. Dispatch
                msg = json.loads(body.decode("utf-8"))
                callback(msg)
            except Exception as e:
                logger.error(f"IPC Read Error: {e}")
                break
        self.connected = False
        # Cleanup
        if self.is_windows:
            if self._win_in_handle:
                ctypes.windll.kernel32.CloseHandle(self._win_in_handle)
            if self._win_out_handle:
                ctypes.windll.kernel32.CloseHandle(self._win_out_handle)
        if not self.is_windows and self.pipe_path_base:
            try:
                os.remove(self.pipe_path_base)
            except:
                pass

    def _recv_bytes(self, n):
        if self.is_windows:
            buf = ctypes.create_string_buffer(n)
            read = ctypes.c_ulong(0)
            # Read from OUT handle
            res = ctypes.windll.kernel32.ReadFile(
                self._win_out_handle, buf, n, ctypes.byref(read), None
            )
            if res == 0:
                err = ctypes.GetLastError()
                # 109 = ERROR_BROKEN_PIPE (Normal EOF when client disconnects)
                if err != 109:
                    logger.error(f"ReadFile Failed. Error: {err}, Requested: {n}")
                else:
                    logger.warning(f"Pipe Disconnected (ERROR_BROKEN_PIPE).")
                return None

            if read.value != n:
                logger.error(f"ReadFile checking Partial Read: Got {read.value} / {n}")
                return None

            return buf.raw
        else:
            # Unix Socket
            data = bytearray()
            while len(data) < n:
                packet = self.conn.recv(n - len(data))
                if not packet:
                    return None
                data.extend(packet)
            return data

    def send(self, data_dict):
        if not self.connected:
            return
        with self._lock:
            try:
                body_str = json.dumps(data_dict)

                if self._native:
                    self._native.send(body_str)
                    return

                body = body_str.encode("utf-8")
                header = struct.pack("<I", len(body))
                full_msg = header + body

                if self.is_windows:
                    written = ctypes.c_ulong(0)
                    # Write to IN handle
                    ctypes.windll.kernel32.WriteFile(
                        self._win_in_handle,
                        full_msg,
                        len(full_msg),
                        ctypes.byref(written),
                        None,
                    )
                else:
                    self.conn.sendall(full_msg)

            except Exception as e:
                if self.connected:
                    logger.error(f"IPC Send Error: {e}")
                self.connected = False


class ChromeAdapter:
    def __init__(self, binary_path, config=None):
        self.binary_path = binary_path
        self.config = config or {}
        self.process = None
        self.ipc = None
        self.ready = False
        self._raw_callback = None
        self._queue = []
        self._flush_lock = threading.Lock()

    def start(self):
        self.ipc = ChromeIPCServer()

        # Start the server thread
        def _server_launcher():
            self.ipc.listen()
            self.ipc.read_loop(self._on_message)

        threading.Thread(target=_server_launcher, daemon=True).start()

        # WAIT FOR THE PIPE NAME
        if not self.ipc.listening_event.wait(timeout=10.0):
            raise RuntimeError("Failed to init IPC pipe within 10 seconds")

        app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "shell"))

        # FIX: Pass current working directory as root for pytron:// protocol
        pipe_arg = (
            self.ipc.pipe_path_base if self.ipc.is_windows else self.ipc.pipe_path_base
        )

        # Use explicit CWD from config if available (set by Engine calculation)
        # otherwise fall back to process CWD.
        pytron_root = self.config.get("cwd", os.getcwd())

        cmd = [
            self.binary_path,
            app_path,
            f"--pytron-pipe={pipe_arg}",
            f"--pytron-root={pytron_root}",
        ]

        # Force software rendering if needed (optional, good for VM stability)
        if self.config.get("software_render"):
            cmd.append("--disable-gpu")

        if self.config.get("debug"):
            cmd.append("--inspect")

        # FIX: Set the subprocess CWD to the Project Root (pytron_root)
        # instead of the Shell Binary Directory.
        # This ensures process.cwd() in Electron matches the Project Root,
        # which is critical for 'pytron://' protocol resolution if the flag is ignored.

        # Ensure we don't break binary loading, though.
        # binary_path is abs path, and app_path is abs path. Should be fine.

        logger.info(f"Spawning Mojo Process (IPC): {' '.join(cmd)}")
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=pytron_root,
            text=True,
            bufsize=1,
        )

        # Dead Man's Switch: Kill Python if Electron dies
        from ...apputils.deadmansswitch import DeadMansSwitch

        self._dms = DeadMansSwitch(self.process)

        threading.Thread(
            target=self._proxy_logs, args=(self.process.stdout, "STDOUT"), daemon=True
        ).start()
        threading.Thread(
            target=self._proxy_logs, args=(self.process.stderr, "STDERR"), daemon=True
        ).start()

    def _proxy_logs(self, pipe, prefix):
        try:
            while True:
                line = pipe.readline()
                if not line:
                    break

                content = line.strip()
                if not content:
                    continue

                # Filter out benign Electron noises
                if "DevTools listening on" in content:
                    continue
                if "GpuProcess" in content and "error" in content.lower():
                    # Common benign GPU errors in headless/embedded
                    continue

                if prefix == "STDOUT":
                    # If it's a console.log from our Shell.js, it might already have a tag
                    if content.startswith("[Mojo-Shell]"):
                        logger.info(content)
                    else:
                        logger.debug(f"[Electron] {content}")
                else:
                    # STDERR usually contains Chromium warnings
                    logger.warning(f"[Electron-Err] {content}")

        except Exception as e:
            logger.debug(f"Log proxy error: {e}")

    def _flush_queue(self):
        with self._flush_lock:
            count = len(self._queue)
            logger.info(f"Flushing {count} queued messages via IPC...")
            flushed = 0
            while self._queue:
                msg = self._queue.pop(0)
                try:
                    # Log the critical 'show' or 'init' commands to verify order
                    action = msg.get("action") if isinstance(msg, dict) else "unknown"
                    if action in ["init", "show", "navigate"]:
                        logger.info(f"Flushing critical command: {action}")

                    self.ipc.send(msg)
                    flushed += 1
                    # Reduced sleep to 0, relying on OS buffering
                except Exception as e:
                    logger.error(f"Failed to flush message {action}: {e}")
            logger.info(f"Flush complete. Sent {flushed}/{count} messages.")

    def _on_message(self, msg):
        if isinstance(msg, str):
            try:
                msg = json.loads(msg)
            except Exception as e:
                logger.error(f"Failed to parse native IPC message: {e}")
                return

        msg_type = msg.get("type")
        payload = msg.get("payload")
        logger.debug(f"Mojo Received: {msg_type} -> {payload}")

        if msg_type == "lifecycle" and payload == "app_ready":
            logger.info("Mojo Handshake (app_ready) received. Initiating flush.")
            self.ready = True
            threading.Thread(target=self._flush_queue, daemon=True).start()

        if self._raw_callback:
            self._raw_callback(msg)

    def send(self, payload):
        if self.ipc and self.ipc.connected and self.ready:
            self.ipc.send(payload)
        else:
            with self._flush_lock:
                self._queue.append(payload)

    def bind_raw(self, callback):
        self._raw_callback = callback
