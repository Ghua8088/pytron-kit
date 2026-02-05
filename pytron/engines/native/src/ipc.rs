use pyo3::prelude::*;
use std::sync::{Arc, Mutex};
use std::thread;

#[cfg(target_os = "windows")]
use windows::{
    core::PCWSTR,
    Win32::Foundation::{HANDLE, CloseHandle},
    Win32::System::Pipes::{CreateNamedPipeW, ConnectNamedPipe, NAMED_PIPE_MODE},
    Win32::Storage::FileSystem::{WriteFile, ReadFile, FILE_FLAGS_AND_ATTRIBUTES},
};

#[cfg(not(target_os = "windows"))]
use std::os::unix::net::{UnixListener, UnixStream};
#[cfg(not(target_os = "windows"))]
use std::io::{Read, Write};

const PIPE_ACCESS_DUPLEX: u32 = 0x00000003;
const PIPE_TYPE_BYTE: u32 = 0x00000000;
const PIPE_READMODE_BYTE: u32 = 0x00000000;
const PIPE_WAIT: u32 = 0x00000000;

#[pyclass]
pub struct ChromeIPC {
    #[cfg(target_os = "windows")]
    handle_in: Arc<Mutex<Option<usize>>>, 
    #[cfg(target_os = "windows")]
    handle_out: Arc<Mutex<Option<usize>>>,
    
    #[cfg(not(target_os = "windows"))]
    stream: Arc<Mutex<Option<UnixStream>>>,
    
    connected: Arc<Mutex<bool>>,
    pipe_path: String,
}

#[pymethods]
impl ChromeIPC {
    #[new]
    fn new() -> Self {
        Self {
            #[cfg(target_os = "windows")]
            handle_in: Arc::new(Mutex::new(None)),
            #[cfg(target_os = "windows")]
            handle_out: Arc::new(Mutex::new(None)),
            #[cfg(not(target_os = "windows"))]
            stream: Arc::new(Mutex::new(None)),
            connected: Arc::new(Mutex::new(false)),
            pipe_path: String::new(),
        }
    }

    fn listen(&mut self, uid: String) -> PyResult<String> {
        #[cfg(target_os = "windows")]
        {
            let base_path = format!(r#"\\.\pipe\pytron-{}"#, uid);
            let path_in = format!("{}-in", base_path);
            let path_out = format!("{}-out", base_path);
            
            self.pipe_path = base_path.clone();

            let w_path_in = encode_wide(&path_in);
            let w_path_out = encode_wide(&path_out);

            let h_in = unsafe {
                CreateNamedPipeW(
                    PCWSTR(w_path_in.as_ptr()),
                    FILE_FLAGS_AND_ATTRIBUTES(PIPE_ACCESS_DUPLEX),
                    NAMED_PIPE_MODE(PIPE_TYPE_BYTE | PIPE_WAIT),
                    1,
                    65536,
                    65536,
                    0,
                    None,
                )
            };

            if h_in.is_invalid() {
                return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Failed to create IN pipe"));
            }

            let h_out = unsafe {
                CreateNamedPipeW(
                    PCWSTR(w_path_out.as_ptr()),
                    FILE_FLAGS_AND_ATTRIBUTES(PIPE_ACCESS_DUPLEX),
                    NAMED_PIPE_MODE(PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT),
                    1,
                    65536,
                    65536,
                    0,
                    None,
                )
            };

            if h_out.is_invalid() {
                unsafe { let _ = CloseHandle(h_in); }
                return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Failed to create OUT pipe"));
            }

            *self.handle_in.lock().unwrap() = Some(h_in.0 as usize);
            *self.handle_out.lock().unwrap() = Some(h_out.0 as usize);

            Ok(base_path)
        }

        #[cfg(not(target_os = "windows"))]
        {
            let path = format!("/tmp/pytron-{}.sock", uid);
            self.pipe_path = path.clone();
            if std::path::Path::new(&path).exists() {
                let _ = std::fs::remove_file(&path);
            }
            Ok(path)
        }
    }

    fn wait_for_connection(&self, py: Python<'_>) -> PyResult<()> {
        #[cfg(target_os = "windows")]
        {
            let h_in_val = self.handle_in.lock().unwrap().ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Pipes not initialized"))?;
            let h_out_val = self.handle_out.lock().unwrap().ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Pipes not initialized"))?;
            
            let h_in = HANDLE(h_in_val as _);
            let h_out = HANDLE(h_out_val as _);

            // CRITICAL: Release GIL during blocking Win32 call
            py.allow_threads(move || unsafe {
                let _ = ConnectNamedPipe(h_in, None);
                let _ = ConnectNamedPipe(h_out, None);
            });

            *self.connected.lock().unwrap() = true;
            Ok(())
        }

        #[cfg(not(target_os = "windows"))]
        {
            let path = self.pipe_path.clone();
            let stream = py.allow_threads(move || {
                let listener = UnixListener::bind(&path).unwrap();
                let (s, _) = listener.accept().unwrap();
                s
            });
            *self.stream.lock().unwrap() = Some(stream);
            *self.connected.lock().unwrap() = true;
            Ok(())
        }
    }

    fn start_read_loop(&self, callback: PyObject) -> PyResult<()> {
        let connected = self.connected.clone();
        
        #[cfg(target_os = "windows")]
        let h_out_val = self.handle_out.lock().unwrap().ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Pipes not initialized"))?;
        
        #[cfg(not(target_os = "windows"))]
        let mut stream_read = self.stream.lock().unwrap().as_ref().map(|s| s.try_clone().unwrap());

        thread::spawn(move || {
            #[cfg(target_os = "windows")]
            let h_out = HANDLE(h_out_val as _);

            while *connected.lock().unwrap() {
                #[cfg(target_os = "windows")]
                {
                    let mut header = [0u8; 4];
                    let mut bytes_read = 0u32;
                    unsafe {
                        let res = ReadFile(h_out, Some(&mut header), Some(&mut bytes_read), None);
                        if res.is_err() || bytes_read != 4 { break; }
                    }
                    let msg_len = u32::from_le_bytes(header) as usize;

                    let mut body = vec![0u8; msg_len];
                    unsafe {
                        let res = ReadFile(h_out, Some(&mut body), Some(&mut bytes_read), None);
                        if res.is_err() || bytes_read as usize != msg_len { break; }
                    }

                    if let Ok(msg_str) = String::from_utf8(body) {
                        Python::with_gil(|py| {
                            let _ = callback.call1(py, (msg_str,));
                        });
                    }
                }

                #[cfg(not(target_os = "windows"))]
                {
                    if let Some(mut stream) = stream_read.as_mut() {
                        let mut header = [0u8; 4];
                        if stream.read_exact(&mut header).is_err() { break; }
                        let msg_len = u32::from_le_bytes(header) as usize;
                        let mut body = vec![0u8; msg_len];
                        if stream.read_exact(&mut body).is_err() { break; }
                        
                        if let Ok(msg_str) = String::from_utf8(body) {
                            Python::with_gil(|py| {
                                let _ = callback.call1(py, (msg_str,));
                            });
                        }
                    } else { break; }
                }
            }
            *connected.lock().unwrap() = false;
        });

        Ok(())
    }

    fn send(&self, py: Python<'_>, data: String) -> PyResult<()> {
        if !*self.connected.lock().unwrap() {
            return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Not connected"));
        }

        let body = data.into_bytes();
        let msg_len = body.len() as u32;
        let header = msg_len.to_le_bytes();
        let mut full_msg = Vec::with_capacity(4 + body.len());
        full_msg.extend_from_slice(&header);
        full_msg.extend_from_slice(&body);

        #[cfg(target_os = "windows")]
        {
            let h_in_val = self.handle_in.lock().unwrap().ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Pipe not connected"))?;
            let h_in = HANDLE(h_in_val as _);
            py.allow_threads(move || {
                let mut bytes_written = 0u32;
                unsafe {
                    let _ = WriteFile(h_in, Some(&full_msg), Some(&mut bytes_written), None);
                }
            });
            Ok(())
        }

        #[cfg(not(target_os = "windows"))]
        {
            let mut lock = self.stream.lock().unwrap();
            if let Some(mut stream) = lock.as_mut() {
                py.allow_threads(move || {
                    let _ = stream.write_all(&full_msg);
                });
            }
            Ok(())
        }
    }
}

#[cfg(target_os = "windows")]
fn encode_wide(s: &str) -> Vec<u16> {
    use std::os::windows::ffi::OsStrExt;
    std::ffi::OsStr::new(s).encode_wide().chain(std::iter::once(0)).collect()
}
