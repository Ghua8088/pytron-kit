import os
import sys
import json
import logging
import threading
import subprocess
import time
import uuid
import platform
import struct

logger = logging.getLogger("Pytron.ChromeIPC")


class ChromeIPCServer:
    """
    A robust Named Pipe server for Windows (or UDS for Unix).
    Uses length-prefixed binary framing (Mojo-style) for maximum reliability.
    """

    def __init__(self, pipe_name):
        self.pipe_name = pipe_name
        self.handle = None
        self.connected = False
        self._lock = threading.Lock()

    def listen(self):
        if platform.system() == "Windows":
            import ctypes
            from ctypes import windll, wintypes

            # Constants
            PIPE_ACCESS_DUPLEX = 0x00000003
            PIPE_TYPE_BYTE = 0x00000000
            PIPE_READMODE_BYTE = 0x00000000
            PIPE_WAIT = 0x00000000
            PIPE_UNLIMITED_INSTANCES = 255

            self.handle = windll.kernel32.CreateNamedPipeW(
                f"\\\\.\\pipe\\{self.pipe_name}",
                PIPE_ACCESS_DUPLEX,
                PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
                PIPE_UNLIMITED_INSTANCES,
                1024 * 1024,
                1024 * 1024,  # 1MB buffers
                0,
                None,
            )

            if self.handle == -1:
                raise Exception(f"Failed to create Named Pipe: {ctypes.GetLastError()}")

            logger.debug(f"Mojo Pipe created: {self.pipe_name}")

            # Blocking Connect
            connected = windll.kernel32.ConnectNamedPipe(self.handle, None)
            if (
                not connected and windll.kernel32.GetLastError() != 535
            ):  # ERROR_PIPE_CONNECTED
                raise Exception(f"Failed to connect pipe: {ctypes.GetLastError()}")

            self.connected = True
            logger.debug("Chrome Shell established Mojo connection.")

        else:
            import socket

            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock_path = f"/tmp/{self.pipe_name}"
            if os.path.exists(sock_path):
                os.remove(sock_path)
            self.sock.bind(sock_path)
            self.sock.listen(1)
            self.conn, _ = self.sock.accept()
            self.connected = True

    def read_loop(self, callback):
        """Reads length-prefixed messages."""
        import ctypes
        from ctypes import windll, byref, c_ulong, create_string_buffer

        while self.connected:
            try:
                # 1. Read 4-byte Header (Length)
                header = self._raw_read(4)
                if not header or len(header) < 4:
                    break

                msg_len = struct.unpack("<I", header)[0]

                # 2. Read Body
                body = self._raw_read(msg_len)
                if not body:
                    break

                # 3. Dispatch
                msg = json.loads(body.decode("utf-8"))
                callback(msg)

            except Exception as e:
                logger.error(f"IPC Read Error: {e}")
                break

        self.connected = False

    def _raw_read(self, n):
        import ctypes
        from ctypes import windll, byref, c_ulong, create_string_buffer

        if platform.system() == "Windows":
            buf = create_string_buffer(n)
            bytes_read = c_ulong(0)
            success = windll.kernel32.ReadFile(
                self.handle, buf, n, byref(bytes_read), None
            )
            if not success or bytes_read.value == 0:
                return None
            return buf.raw[: bytes_read.value]
        else:
            return self.conn.recv(n)

    def send(self, data_dict):
        """Sends a length-prefixed JSON message."""
        with self._lock:
            body = json.dumps(data_dict).encode("utf-8")
            header = struct.pack("<I", len(body))
            full_msg = header + body

            if platform.system() == "Windows":
                import ctypes
                from ctypes import windll, byref, c_ulong

                bytes_written = c_ulong(0)
                windll.kernel32.WriteFile(
                    self.handle, full_msg, len(full_msg), byref(bytes_written), None
                )
                windll.kernel32.FlushFileBuffers(self.handle)
            else:
                self.conn.sendall(full_msg)


class ChromeAdapter:
    def __init__(self, binary_path, config=None):
        self.binary_path = binary_path
        self.config = config or {}
        self.process = None
        self.ipc = None
        self.ready = False
        self.pipe_name = f"pytron-mojo-{uuid.uuid4().hex[:8]}"
        self._raw_callback = None

    def start(self):
        self.ipc = ChromeIPCServer(self.pipe_name)

        def _server_thread():
            self.ipc.listen()
            self.ipc.read_loop(self._on_message)

        threading.Thread(target=_server_thread, daemon=True).start()

        # Launch Shell
        full_pipe_path = (
            f"\\\\.\\pipe\\{self.pipe_name}"
            if platform.system() == "Windows"
            else f"/tmp/{self.pipe_name}"
        )

        cmd = [self.binary_path, f"--pytron-pipe={full_pipe_path}"]

        # Pass configuration flags to the shell process
        if self.config.get("debug"):
            cmd.append("--debug")

        if self.config.get("frameless"):
            cmd.append("--frameless")

        if self.config.get("transparent"):
            cmd.append("--transparent")

        # Pass initial dimensions
        dims = self.config.get("dimensions")
        if dims and len(dims) == 2:
            cmd.append(f"--width={dims[0]}")
            cmd.append(f"--height={dims[1]}")

        logger.info(f"Launching Chrome Shell: {cmd}")

        self.process = subprocess.Popen(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
            cwd=os.path.dirname(self.binary_path),
        )

    def _on_message(self, msg):
        if msg.get("type") == "lifecycle" and msg.get("payload") == "app_ready":
            self.ready = True

        if self._raw_callback:
            self._raw_callback(msg)

    def send(self, payload):
        if self.ipc and self.ipc.connected:
            self.ipc.send(payload)

    def bind_raw(self, callback):
        self._raw_callback = callback
