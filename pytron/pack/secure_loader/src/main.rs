#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod security;
mod config;
mod patcher;
mod ui;
mod python_runtime;

use pyo3::prelude::*;
use std::env;
use crate::security::check_debugger;
use crate::config::load_settings;
use crate::patcher::check_and_apply_patches;
use crate::ui::{alert, init_com, set_app_id};
use crate::python_runtime::{find_internal_dir, run_python_and_payload};

fn main() -> PyResult<()> {
    // 1. CLI Argument Parsing and Console Allocation
    let args: Vec<String> = env::args().collect();
    let debug_mode = args.iter().any(|arg| arg == "--debug");

    if debug_mode {
        #[cfg(windows)]
        unsafe {
            if let Ok(func) = libloading::Library::new("kernel32.dll") {
                 let alloc: libloading::Symbol<unsafe extern "system" fn() -> i32> = func.get(b"AllocConsole").unwrap();
                 alloc();
            }
        }
    }

    // 2. Anti-Debugging & COM Init
    check_debugger();
    init_com();

    let (root_dir, internal_dir) = find_internal_dir();
    
    check_and_apply_patches(&root_dir);

    // Verify critical files (Compiled Payload)
    let ext = if cfg!(windows) { "pyd" } else { "so" };
    let payload_path = root_dir.join(format!("app.{}", ext));

    if !payload_path.exists() {
        // Also check in _internal for standard onedir layouts
        let internal_payload = internal_dir.join(format!("app.{}", ext));
        if !internal_payload.exists() {
            alert("Shield: Discovery Error", &format!(
                "Critical compiled asset 'app.{}' missing.\nChecked: {}\n\nDistribution may be corrupted.",
                ext, payload_path.display()
            ));
            std::process::exit(1);
        }
    }
    
    // Load config from settings.json (which is now in _internal)
    // The load_settings helper might need root_dir, but we point to internal_dir for search
    let settings = load_settings(&internal_dir, None);
    let app_title = settings.as_ref().and_then(|s| s.title.clone()).unwrap_or_else(|| "Pytron App".to_string());
    
    // Set App ID for Task Manager grouping
    let app_id = format!("Pytron.{}.{}", 
        settings.as_ref().and_then(|s| s.author.clone()).unwrap_or_else(|| "User".to_string()).replace(" ", ""),
        app_title.replace(" ", "")
    );
    set_app_id(&app_id);
    
    let app_bundle = internal_dir.join("app.bundle");

    // 2. DLL Discovery (Windows Fix for 'Everything in _internal')
    #[cfg(windows)]
    unsafe {
        if let Ok(lib) = libloading::Library::new("kernel32.dll") {
            let func: Result<libloading::Symbol<unsafe extern "system" fn(*const u16) -> i32>, _> = lib.get(b"SetDllDirectoryW");
            if let Ok(set_dll_dir) = func {
                use std::os::windows::ffi::OsStrExt;
                let mut path_v: Vec<u16> = internal_dir.as_os_str().encode_wide().collect();
                path_v.push(0);
                set_dll_dir(path_v.as_ptr());
            }
        }
    }

    // 2. Strict Environment Isolation
    env::remove_var("PYTHONPATH");
    env::remove_var("PYTHONHOME");
    
    // Everything is now in _internal, so we point HOME there
    env::set_var("PYTHONHOME", &internal_dir);
    
    let path_sep = if cfg!(windows) { ";" } else { ":" };
    let python_path = if app_bundle.exists() {
        format!("{}{}{}", internal_dir.display(), path_sep, app_bundle.display())
    } else {
        format!("{}", internal_dir.display())
    };
    
    env::set_var("PYTHONPATH", &python_path);
    env::set_var("PYTHONNOUSERSITE", "1");
    // Speed Optimizations
    env::set_var("PYTHONOPTIMIZE", "1");
    env::set_var("PYTHONDONTWRITEBYTECODE", "1");
    // Unicode Stability
    env::set_var("PYTHONUTF8", "1");

    // Run execution
    let res = run_python_and_payload(&root_dir, &internal_dir, if app_bundle.exists() { Some(&app_bundle) } else { None });
    if let Err(e) = res {
        alert(&app_title, &format!("Fatal Engine Error:\n{}", e));
    }
    Ok(())
}
