use pyo3::prelude::*;
use pyo3::types::PyList;
use std::env;
use std::path::{Path, PathBuf};

pub fn find_internal_dir() -> (PathBuf, PathBuf) {
    let exe_path = env::current_exe().unwrap_or_else(|_| PathBuf::from("app.exe"));
    let root_dir = exe_path.parent().unwrap_or_else(|| Path::new(".")).to_path_buf();
    let internal_dir = root_dir.join("_internal");
    
    if internal_dir.exists() {
        (root_dir, internal_dir)
    } else {
        (root_dir.clone(), root_dir)
    }
}

pub fn run_python_and_payload(root_dir: &Path, internal_dir: &Path, _base_zip: Option<&Path>) -> PyResult<()> {
    pyo3::prepare_freethreaded_python();

    let exe_path = env::current_exe().map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(format!("EXE check failed: {}", e)))?;
    
    Python::with_gil(|py| {
        let sys = py.import_bound("sys")?;
        let os = py.import_bound("os")?;

        sys.setattr("frozen", true)?;
        // CRITICAL: Point _MEIPASS to internal_dir so settings.json/assets are found
        sys.setattr("_MEIPASS", internal_dir.to_string_lossy())?;
        sys.setattr("executable", exe_path.to_string_lossy())?;

        if cfg!(windows) {
            let internal_str = internal_dir.to_string_lossy();
            if let Ok(add_dll_func) = os.getattr("add_dll_directory") {
                let _ = add_dll_func.call1((internal_str,));
            }
        }

        let path_list: Bound<PyList> = sys.getattr("path")?.extract()?;
        let int_str = internal_dir.to_string_lossy();
        let root_str = root_dir.to_string_lossy();
        
        // Add paths for module discovery
        let mut current_idx = 0;
        if let Some(bundle) = _base_zip {
            let bundle_str = bundle.to_string_lossy();
            if !path_list.contains(&bundle_str)? {
                path_list.insert(current_idx, bundle_str)?;
                current_idx += 1;
            }
        }

        if !path_list.contains(&int_str)? {
            path_list.insert(current_idx, int_str)?;
            current_idx += 1;
        }
        if !path_list.contains(&root_str)? {
            path_list.insert(current_idx, root_str)?;
        }

        // --- CLI Argument Forwarding ---
        let args: Vec<String> = env::args().collect();
        let py_args = PyList::new_bound(py, &args);
        sys.setattr("argv", py_args)?;

        // Load the compiled binary module 'app'
        // Cythonized modules execute their patched 'if True:' block upon import
        match py.import_bound("app") {
            Ok(_) => Ok(()),
            Err(e) => {
                let tb = py.import_bound("traceback")?;
                let tb_list = tb.call_method1("format_exception", (e.clone_ref(py),))?;
                
                // Use "".join() to convert the list of lines into one string
                let empty_str = pyo3::types::PyString::new_bound(py, "");
                let formatted_tb: String = empty_str.call_method1("join", (tb_list,))?.extract()?;
                
                Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                    format!("Shield Error: Failed to start native logic\n\n{}", formatted_tb)
                ))
            }
        }
    })
}
