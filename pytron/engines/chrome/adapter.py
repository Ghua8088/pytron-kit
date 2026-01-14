import os
import sys
import json
import logging
import threading
import socket
import time
import uuid
import platform
import struct
import subprocess

logger = logging.getLogger("Pytron.ChromeAdapter")


class ChromeIPCServer:
    """
    A robust TCP-based IPC server for the Chrome Engine.
    Uses length-prefixed binary framing (Mojo-style).
    TCP is chosen over Named Pipes for better cross-runtime stability on Windows.
    """

    def __init__(self):
        self.host = "127.0.0.1"
        self.port = 0  # OS will assign a random free port
        self.server_sock = None
        self.conn = None
        self.connected = False
        self._lock = threading.Lock()
        self.listening_event = threading.Event()

    def listen(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.port = self.server_sock.getsockname()[1]
        self.server_sock.listen(1)

        # SIGNAL THAT PORT IS READY!
        self.listening_event.set()

        logger.info(f"Mojo IPC listening on TCP port {self.port}")

        # This will block until Electron connects
        self.conn, addr = self.server_sock.accept()
        self.conn.setblocking(True)
        self.connected = True
        logger.info(f"Mojo Shell connected from {addr}")

    def read_loop(self, callback):
        while self.connected:
            try:
                # 1. Read 4-byte Header
                header = self._recv_all(4)
                if not header:
                    break
                msg_len = struct.unpack("<I", header)[0]

                # 2. Read Body
                body = self._recv_all(msg_len)
                if not body:
                    break

                # 3. Dispatch
                msg = json.loads(body.decode("utf-8"))
                callback(msg)
            except Exception as e:
                logger.error(f"IPC Read Error: {e}")
                break
        self.connected = False

    def _recv_all(self, n):
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
                body = body_str.encode("utf-8")
                header = struct.pack("<I", len(body))
                full_msg = header + body
                self.conn.sendall(full_msg)
            except Exception as e:
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

        # WAIT FOR THE PORT (No more sleep!)
        if not self.ipc.listening_event.wait(timeout=10.0):
            raise RuntimeError("Failed to bind IPC port within 10 seconds")

        app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "shell"))

        # FIX: Pass current working directory as root for pytron:// protocol
        cmd = [
            self.binary_path,
            app_path,
            f"--pytron-port={self.ipc.port}",
            f"--pytron-root={os.getcwd()}",
        ]

        # Force software rendering if needed (optional, good for VM stability)
        if self.config.get("software_render"):
            cmd.append("--disable-gpu")

        if self.config.get("debug"):
            cmd.append("--inspect")

        logger.info(f"Spawning Mojo Process (TCP): {' '.join(cmd)}")
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(self.binary_path),
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

        except Exception:
            pass

    def _flush_queue(self):
        with self._flush_lock:
            time.sleep(0.5)
            logger.info(f"Flushing {len(self._queue)} queued messages via TCP...")
            while self._queue:
                msg = self._queue.pop(0)
                self.ipc.send(msg)
                time.sleep(0.01)

    def _on_message(self, msg):
        msg_type = msg.get("type")
        payload = msg.get("payload")
        logger.debug(f"Mojo Received: {msg_type} -> {payload}")

        if msg_type == "lifecycle" and payload == "app_ready":
            logger.info("Mojo TCP Handshake (app_ready) received. Initiating flush.")
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
