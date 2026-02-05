import sys
import os
import time
import threading
import json
import pytest

# Add dependencies to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pytron", "dependencies")))

try:
    import pytron_native
    HAS_NATIVE = True
except ImportError:
    HAS_NATIVE = False

@pytest.mark.skipif(not HAS_NATIVE, reason="pytron_native module not found")
def test_chrome_ipc_handshake():
    ipc = pytron_native.ChromeIPC()
    uid = "test-handshake"
    pipe_path = ipc.listen(uid)
    
    assert "pytron-test-handshake" in pipe_path
    
    received_msgs = []
    def callback(msg):
        received_msgs.append(msg)

    # Mock Electron Client in a separate thread
    def mock_electron():
        time.sleep(0.2) # Wait for listen
        if sys.platform == "win32":
            import ctypes
            # Connect to In-Pipe (Python writes to this)
            h_in = ctypes.windll.kernel32.CreateFileW(
                f"{pipe_path}-in",
                0x80000000, # GENERIC_READ
                0, None, 3, 0, None
            )
            # Connect to Out-Pipe (Python reads from this)
            h_out = ctypes.windll.kernel32.CreateFileW(
                f"{pipe_path}-out",
                0x40000000, # GENERIC_WRITE
                0, None, 3, 0, None
            )
            
            # Send Handshake
            msg = json.dumps({"type": "lifecycle", "payload": "app_ready"})
            body = msg.encode('utf-8')
            header = len(body).to_bytes(4, 'little')
            written = ctypes.c_ulong(0)
            ctypes.windll.kernel32.WriteFile(h_out, header, 4, ctypes.byref(written), None)
            ctypes.windll.kernel32.WriteFile(h_out, body, len(body), ctypes.byref(written), None)
            
            # Read something back
            buf = ctypes.create_string_buffer(1024)
            read = ctypes.c_ulong(0)
            ctypes.windll.kernel32.ReadFile(h_in, buf, 4, ctypes.byref(read), None)
            msg_len = int.from_bytes(buf[:4], 'little')
            ctypes.windll.kernel32.ReadFile(h_in, buf, msg_len, ctypes.byref(read), None)
            resp = json.loads(buf[:msg_len].decode('utf-8'))
            assert resp["action"] == "test_action"
            
            ctypes.windll.kernel32.CloseHandle(h_in)
            ctypes.windll.kernel32.CloseHandle(h_out)
        else:
            import socket
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(pipe_path)
            
            # Send
            msg = json.dumps({"type": "lifecycle", "payload": "app_ready"})
            body = msg.encode('utf-8')
            header = len(body).to_bytes(4, 'little')
            sock.sendall(header + body)
            
            # Read
            header = sock.recv(4)
            msg_len = int.from_bytes(header, 'little')
            body = sock.recv(msg_len)
            resp = json.loads(body.decode('utf-8'))
            assert resp["action"] == "test_action"
            sock.close()

    t = threading.Thread(target=mock_electron)
    t.start()
    
    # Python Side: Wait for connection (This used to deadlock)
    ipc.wait_for_connection()
    
    # Start Read Loop
    ipc.start_read_loop(callback)
    
    # Send a message to Electron
    ipc.send(json.dumps({"action": "test_action"}))
    
    # Wait for callback
    start_time = time.time()
    while len(received_msgs) == 0 and time.time() - start_time < 2:
        time.sleep(0.1)
    
    assert len(received_msgs) > 0
    msg = json.loads(received_msgs[0])
    assert msg["type"] == "lifecycle"
    assert msg["payload"] == "app_ready"
    
    t.join()

if __name__ == "__main__":
    # Manual run support
    try:
        test_chrome_ipc_handshake()
        print(" Rust IPC Integration Test Passed!")
    except Exception as e:
        print(f" Rust IPC Integration Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
