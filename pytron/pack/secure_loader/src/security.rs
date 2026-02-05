use std::env;
// use std::fs;
// use std::io::{Read, Seek, SeekFrom};
// use aes_gcm::{
//     aead::{Aead, KeyInit},
//     Aes256Gcm, Nonce
// };
use obfstr::obfstr;

#[cfg(windows)]
extern crate winapi;

use crate::ui::alert;

pub fn check_debugger() {
    #[cfg(windows)]
    unsafe {
        // 1. Standard Check
        if winapi::um::debugapi::IsDebuggerPresent() != 0 {
            alert(obfstr!("Security Alert"), obfstr!("Process integrity check failed (D1)."));
            std::process::exit(0xDEAD);
        }

        // 2. Remote Debugger Check
        let mut is_remote_debugger_present = 0;
        winapi::um::debugapi::CheckRemoteDebuggerPresent(
            winapi::um::processthreadsapi::GetCurrentProcess(),
            &mut is_remote_debugger_present,
        );
        if is_remote_debugger_present != 0 {
            alert(obfstr!("Security Alert"), obfstr!("Unauthorized debugger detected (D2)."));
            std::process::exit(0xDEAB);
        }
        
        // 3. Timing check (debuggers slow down execution)
        let start = std::time::Instant::now();
        let mut x = 0;
        for i in 0..10_000 { 
            x = std::hint::black_box(x + i); 
        }
        // If it takes more than 5ms for a simple loop, something is wrong
        if start.elapsed().as_millis() > 5 {
             alert(obfstr!("Security Alert"), obfstr!("Timing anomaly detected. Binary compromised."));
             std::process::exit(0xDEAC);
        }
    }
}

// Footer format removed - switching to Cython compilation
