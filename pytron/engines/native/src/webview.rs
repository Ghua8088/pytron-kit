use pyo3::prelude::*;
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::path::PathBuf;

use tao::{
    event::{Event, WindowEvent},
    event_loop::{ControlFlow, EventLoopBuilder, EventLoopProxy, EventLoop},
    window::WindowBuilder,
};
use tray_icon::{TrayIconBuilder, menu::{Menu, MenuItemBuilder, PredefinedMenuItem}};
use wry::WebViewBuilder;

#[cfg(target_os = "windows")]
use wry::WebViewBuilderExtWindows; 

use crate::events::UserEvent;
use crate::state::RuntimeState;
use crate::utils::{setup_panic_hook, SendWrapper, load_icon};
use crate::protocol::handle_pytron_protocol;

#[pyclass]
pub struct NativeWebview {
    pub proxy: EventLoopProxy<UserEvent>,
    runner: Mutex<Option<EventLoop<UserEvent>>>,
    state_ptr: Mutex<Option<usize>>, 
    hwnd: usize,
    callbacks: Arc<Mutex<HashMap<String, PyObject>>>,
}

unsafe impl Send for NativeWebview {}
unsafe impl Sync for NativeWebview {}

#[pymethods]
impl NativeWebview {
    #[new]
    pub fn new(debug: bool, url_str: String, root_path: String, resizable: bool, frameless: bool) -> PyResult<Self> {
        setup_panic_hook();

        let safe_url = if url_str == "about:blank" {
             url_str
        } else if url_str.starts_with("pytron://") {
             url_str
        } else if url_str.starts_with("http") {
             url_str
        } else {
             format!("pytron://app/{}", url_str.trim_start_matches('/'))
        };

        println!("[PYTRON NATIVE] Init. Target: {} | Root: {}", safe_url, root_path);

        let event_loop = EventLoopBuilder::<UserEvent>::with_user_event().build();
        let proxy = event_loop.create_proxy();
        
        let window = WindowBuilder::new()
            .with_title("Pytron App")
            .with_visible(false)
            .with_resizable(resizable)
            .with_decorations(!frameless)
            .build(&event_loop)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Failed to create window: {}", e)))?;
        
        #[cfg(target_os = "windows")]
        let hwnd = {
            use tao::platform::windows::WindowExtWindows;
            window.hwnd() as usize
        };
        #[cfg(not(target_os = "windows"))]
        let hwnd = 0;

        let root = PathBuf::from(&root_path);
        let callbacks = Arc::new(Mutex::new(HashMap::<String, PyObject>::new()));
        let cbs_for_ipc = callbacks.clone();
        let proxy_for_ipc = proxy.clone();

        let mut builder = WebViewBuilder::new(&window)
            .with_devtools(debug)
            .with_url(&safe_url);

        // --- Custom Protocol Handler ---
        let protocol_root = root.clone();
        let cbs_for_protocol = callbacks.clone();
        
        builder = builder.with_custom_protocol("pytron".into(), move |request| {
            handle_pytron_protocol(request, protocol_root.clone(), cbs_for_protocol.clone())
        });
        
        #[cfg(target_os = "windows")]
        {
             builder = builder.with_https_scheme(true);
        }

        let proxy_for_nav = proxy.clone();
        builder = builder.with_navigation_handler(move |url: String| {
            // Check if it's an internal application link or an external one
            if !url.starts_with("pytron://") && !url.starts_with("https://pytron.") && url != "about:blank" {
                // External! Send to system browser
                let _ = proxy_for_nav.send_event(UserEvent::OpenExternal(url.clone()));
                return false; // Prevent internal navigation
            }
            true // Allow internal navigation
        });

        let proxy_for_new_window = proxy.clone();
        builder = builder.with_new_window_req_handler(move |url: String| {
            // For new windows (target="_blank"), always prefer external browser
            let _ = proxy_for_new_window.send_event(UserEvent::OpenExternal(url.clone()));
            false // Prevent internal window creation
        });

        builder = builder.with_initialization_script(r#"
            window.pytron_is_native = true;
            
            // --- DE-BROWSERIFY CORE ---
            (function() {
                const isDebug = window.location.search.includes('debug=true') || window.__PYTRON_DEBUG__;
                
                // 1. Kill Context Menu (Unless debugging)
                if (!isDebug) {
                    document.addEventListener('contextmenu', e => e.preventDefault());
                }

                // 2. Kill "Ghost" Drags (images/links flying around)
                document.addEventListener('dragstart', e => {
                    if (e.target.tagName === 'IMG' || e.target.tagName === 'A') e.preventDefault();
                });

                // 3. Kill Browser Shortcuts
                window.addEventListener('keydown', e => {
                    const forbidden = ['r', 'p', 's', 'j', 'u', 'f'];
                    if (e.ctrlKey && forbidden.includes(e.key.toLowerCase())) e.preventDefault();
                    if (e.key === 'F5' || e.key === 'F3' || (e.ctrlKey && e.key === 'f')) e.preventDefault();
                    // Block Zoom
                    if (e.ctrlKey && (e.key === '=' || e.key === '-' || e.key === '0')) e.preventDefault();
                }, true);

                // 4. Kill System UI Styles (Selection, Outlines, Rubber-banding)
                const style = document.createElement('style');
                style.textContent = `
                    * { 
                        -webkit-user-select: none; 
                        user-select: none;
                        -webkit-user-drag: none; 
                        -webkit-tap-highlight-color: transparent;
                        outline: none !important;
                    }
                    input, textarea, [contenteditable], [contenteditable] * { 
                        -webkit-user-select: text !important; 
                        user-select: text !important;
                    }
                    html, body {
                        overscroll-behavior: none !important;
                        cursor: default;
                    }
                    a, button, input[type="button"], input[type="submit"] {
                        cursor: pointer;
                    }
                `;
                document.head ? document.head.appendChild(style) : document.addEventListener('DOMContentLoaded', () => document.head.appendChild(style));
            })();

            window.pytron = window.pytron || {};
            window.pytron.is_ready = true;
            window.__pytron_native_bridge = (method, args) => {
                const seq = Math.random().toString(36).substring(2, 10);
                window.ipc.postMessage(JSON.stringify({id: seq, method: method, params: args}));
                return new Promise((resolve, reject) => {
                    window._rpc = window._rpc || {};
                    window._rpc[seq] = {resolve, reject};
                });
            };
            window.pytron_close = () => window.__pytron_native_bridge('pytron_close', []);
            window.pytron_drag = () => window.__pytron_native_bridge('pytron_drag', []);
            window.pytron_log = (msg) => window.__pytron_native_bridge('pytron_log', [msg]);

            // Override alert to use native message box
            window.alert = (msg) => {
                window.__pytron_native_bridge('pytron_message_box', ["Alert", String(msg), "info"]);
            };
        "#);

        builder = builder.with_ipc_handler(move |request| {
            let msg = request.body().clone();
            if let Ok(val) = serde_json::from_str::<serde_json::Value>(&msg) {
                let seq = val["id"].as_str().unwrap_or("").to_string();
                let method = val["method"].as_str().unwrap_or("").to_string();
                let params = val["params"].to_string(); 
                
                // 1. Check Special Native Methods (Zero Overhead / Native Speed)
                if method == "pytron_drag" || method == "drag" {
                    let _ = proxy_for_ipc.send_event(UserEvent::DragWindow);
                    return;
                }
                if method == "pytron_close" || method == "close" || method == "app_quit" {
                    let _ = proxy_for_ipc.send_event(UserEvent::Quit);
                    return;
                }

                // Native handling for parameterized system calls
                if method == "system_notification" || method == "pytron_system_notification" {
                    if let Ok(args) = serde_json::from_str::<Vec<String>>(&params) {
                        if args.len() >= 2 {
                            let _ = proxy_for_ipc.send_event(UserEvent::Notification(args[0].clone(), args[1].clone()));
                            return;
                        }
                    }
                }

                if method == "set_taskbar_progress" || method == "pytron_set_taskbar_progress" {
                    if let Ok(args) = serde_json::from_str::<Vec<i32>>(&params) {
                         if args.len() >= 3 {
                             let _ = proxy_for_ipc.send_event(UserEvent::TaskbarProgress(args[0], args[1], args[2]));
                             return;
                         }
                    }
                }

                // Native Handling for message boxes (blocking is fine as it runs on native thread, but we use a specialized event for it)
                if method == "pytron_message_box" || method == "message_box" {
                    if let Ok(args) = serde_json::from_str::<Vec<String>>(&params) {
                        if args.len() >= 3 {
                             let _ = proxy_for_ipc.send_event(UserEvent::MessageBox(args[0].clone(), args[1].clone(), args[2].clone(), seq));
                             return;
                        }
                    }
                }

                // 2. Search for bound Python Functions
                let mut found_func: Option<PyObject> = None;
                if let Ok(cbs) = cbs_for_ipc.lock() {
                    if let Some(f) = cbs.get(&method) {
                        Python::with_gil(|py| { found_func = Some(f.clone_ref(py)); });
                    }
                }

                if let Some(func) = found_func {
                    let _ = proxy_for_ipc.send_event(UserEvent::CallPython(func, seq, params, method));
                } else {
                    // Method not found - return error to JS
                    let error_msg = format!("\"Method '{}' not found.\"", method);
                    let _ = proxy_for_ipc.send_event(UserEvent::Return(seq, 1, error_msg));
                }
            }
        });

        let webview = builder.build()
             .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Failed to build WebView: {}", e)))?;

        let state = Box::into_raw(Box::new(RuntimeState { 
            webview, 
            window, 
            callbacks: callbacks.clone(), 
            tray: None, 
            prevent_close: false 
        }));

        Ok(NativeWebview {
            proxy,
            runner: Mutex::new(Some(event_loop)),
            state_ptr: Mutex::new(Some(state as usize)),
            hwnd,
            callbacks,
        })
    }

    pub fn run(&self, py: Python<'_>) -> PyResult<()> {
        let event_loop = self.runner.lock().unwrap().take();
        let state_ptr_val = self.state_ptr.lock().unwrap().take();

        if let (Some(el), Some(ptr)) = (event_loop, state_ptr_val) {
            let state = unsafe { Box::from_raw(ptr as *mut RuntimeState) };
            let cbs_arc = state.callbacks.clone();
            let w_el = SendWrapper::new(el);
            let w_state = SendWrapper::new(state);

            // Spawn Menu Event Listener Thread
            let proxy_for_menu = self.proxy.clone();
            std::thread::spawn(move || {
                let receiver = tray_icon::menu::MenuEvent::receiver();
                loop {
                    if let Ok(event) = receiver.recv() {
                        let id = event.id.0;
                         let _ = proxy_for_menu.send_event(UserEvent::TrayMenuClick(id));
                    }
                }
            });

            py.allow_threads(move || {
                let el = w_el.take();
                let mut state = w_state.take();
                
                el.run(move |event, _, control_flow| {
                    *control_flow = ControlFlow::Wait;
                    
                    match event {
                        Event::UserEvent(ue) => {
                             // DEBUG LOGGING
                             match &ue {
                                 UserEvent::CallPython(_, seq, _, method) => {
                                     println!("[PYTRON BRIDGE] CALL: {} (seq={})", method, seq);
                                 },
                                 UserEvent::Eval(_) => { /* Mute eval logs, too spammy for state sync */ },
                                 UserEvent::Navigate(u) => println!("[PYTRON NAVIGATE] Request: '{}'", u),
                                 UserEvent::Return(_seq, _status, _) => {
                                     // println!("[PYTRON BRIDGE] RETURN: seq={} status={}", seq, status);
                                 },
                                 _ => {},
                             }
                             
                             match ue {
                                UserEvent::Quit => *control_flow = ControlFlow::Exit,
                                UserEvent::Eval(js) => { let _ = state.webview.evaluate_script(&js); }
                                UserEvent::SetTitle(t) => { state.window.set_title(&t); }
                                UserEvent::SetSize(w, h, _) => { state.window.set_inner_size(tao::dpi::LogicalSize::new(w, h)); }
                                
                                UserEvent::Navigate(u) => { 
                                    let _ = state.webview.load_url(&u);
                                }

                                UserEvent::Bind(name, _) => {
                                    // Map is already updated in NativeWebview::bind
                                    let js = format!(r#"window['{}'] = (...args) => window.__pytron_native_bridge('{}', args);"#, name, name);
                                    let _ = state.webview.evaluate_script(&js);
                                }
                                UserEvent::CallPython(f, seq, args, _) => { 
                                    Python::with_gil(|py| { let _ = f.call1(py, (seq, args, 0)); }); 
                                }
                                UserEvent::Dispatch(f, seq, _) => { 
                                     Python::with_gil(|py| { let _ = f.call1(py, (seq, "[]", 0)); }); 
                                }
                                UserEvent::DispatchData(f, seq, args, _) => { 
                                     Python::with_gil(|py| { let _ = f.call1(py, (seq, args, 0)); }); 
                                }

                                UserEvent::Return(seq, status, res) => {
                                    let js = format!(r#"if (window._rpc && window._rpc['{seq}']) {{ if ({status} === 0) window._rpc['{seq}'].resolve({res}); else window._rpc['{seq}'].reject({res}); delete window._rpc['{seq}']; }}"#, seq=seq, status=status, res=res);
                                    let _ = state.webview.evaluate_script(&js);
                                }
                                UserEvent::SetVisible(v) => { 
                                    state.window.set_visible(v); 
                                    if v { 
                                        state.window.set_focus(); 
                                        state.window.set_minimized(false); 
                                    } 
                                }
                                UserEvent::Minimize => { state.window.set_minimized(true); }
                                UserEvent::SetMaximized(m) => { 
                                    if m {
                                         if !state.window.is_maximized() { state.window.set_maximized(true); }
                                    } else {
                                         state.window.set_maximized(false);
                                    }
                                }
                                UserEvent::DragWindow => { let _ = state.window.drag_window(); }
                                
                                UserEvent::SetAlwaysOnTop(t) => { state.window.set_always_on_top(t); }
                                UserEvent::SetResizable(r) => { state.window.set_resizable(r); }
                                UserEvent::SetFullscreen(f) => { 
                                    if f { state.window.set_fullscreen(Some(tao::window::Fullscreen::Borderless(None))); } 
                                    else { state.window.set_fullscreen(None); }
                                }
                                UserEvent::CenterWindow => {
                                     if let Some(monitor) = state.window.current_monitor() {
                                         let screen_size = monitor.size();
                                         let window_size = state.window.inner_size();
                                         let x = (screen_size.width - window_size.width) / 2;
                                         let y = (screen_size.height - window_size.height) / 2;
                                         state.window.set_outer_position(tao::dpi::PhysicalPosition::new(x, y));
                                     }
                                }
                                
                                UserEvent::Notification(title, msg) => {
                                    #[cfg(target_os = "windows")]
                                    {
                                        let _ = notify_rust::Notification::new()
                                            .summary(&title)
                                            .body(&msg)
                                            .appname("Pytron")
                                            .show();
                                    }
                                }
                                
                                UserEvent::TaskbarProgress(state_code, val, _max) => {
                                    #[cfg(target_os = "windows")]
                                    {
                                        use tao::window::ProgressState;
                                        let s = match state_code {
                                            2 => ProgressState::Normal,
                                            4 => ProgressState::Error,
                                            8 => ProgressState::Paused,
                                            1 => ProgressState::Indeterminate,
                                            _ => ProgressState::None,
                                        };
                                        state.window.set_progress_bar(tao::window::ProgressBarState {
                                            state: Some(s),
                                            progress: Some(val as u64),
                                            desktop_filename: None,
                                        });
                                    }
                                }

                                UserEvent::CreateTray(icon_path, tooltip) => {
                                    if let Ok(ic) = load_icon(std::path::Path::new(&icon_path)) {
                                        let menu = Menu::new();
                                        let show_item = MenuItemBuilder::new().text("Show App").id("1000".into()).enabled(true).build();
                                        let quit_item = MenuItemBuilder::new().text("Quit").id("1001".into()).enabled(true).build();
                                        let _ = menu.append(&show_item);
                                        let _ = menu.append(&PredefinedMenuItem::separator());
                                        let _ = menu.append(&quit_item);

                                        let tray_res = TrayIconBuilder::new().with_menu(Box::new(menu)).with_tooltip(&tooltip).with_icon(ic).build();
                                        if let Ok(t) = tray_res { state.tray = Some(t); }
                                    }
                                }
                                UserEvent::TrayMenuClick(id) => {
                                    let mut found: Option<PyObject> = None;
                                    if let Ok(cbs) = cbs_arc.lock() {
                                        if let Some(f) = cbs.get("pytron_tray_click") {
                                             Python::with_gil(|py| { found = Some(f.clone_ref(py)); });
                                        }
                                    }
                                    if let Some(f) = found {
                                        Python::with_gil(|py| { let _ = f.call1(py, (id,)); }); 
                                    }
                                }

                                UserEvent::SetDecorations(d) => { state.window.set_decorations(d); }

                                UserEvent::MessageBox(title, msg, level, seq) => {
                                    let l = match level.as_str() {
                                        "error" => rfd::MessageLevel::Error,
                                        "warning" => rfd::MessageLevel::Warning,
                                        _ => rfd::MessageLevel::Info,
                                    };
                                    let res = rfd::MessageDialog::new()
                                        .set_title(&title)
                                        .set_description(&msg)
                                        .set_level(l)
                                        .show();
                                    
                                    let ret = match res {
                                        rfd::MessageDialogResult::Ok | rfd::MessageDialogResult::Yes => "true",
                                        _ => "false"
                                    };
                                    
                                    if !seq.is_empty() {
                                        let js = format!(r#"if (window._rpc && window._rpc['{seq}']) {{ window._rpc['{seq}'].resolve({ret}); delete window._rpc['{seq}']; }}"#, seq=seq, ret=ret);
                                        let _ = state.webview.evaluate_script(&js);
                                    }
                                }

                                UserEvent::OpenExternal(url) => {
                                    #[cfg(target_os = "windows")]
                                    {
                                        // Use powershell to ensure the URL is handled correctly by the default browser
                                        let _ = std::process::Command::new("powershell")
                                            .arg("-NoProfile")
                                            .arg("-Command")
                                            .arg(format!("Start-Process '{}'", url))
                                            .spawn();
                                    }
                                    #[cfg(target_os = "macos")]
                                    {
                                        let _ = std::process::Command::new("open")
                                            .arg(&url)
                                            .spawn();
                                    }
                                    #[cfg(target_os = "linux")]
                                    {
                                        let _ = std::process::Command::new("xdg-open")
                                            .arg(&url)
                                            .spawn();
                                    }
                                }

                                _ => {} 
                            }
                        }
                        
                        Event::WindowEvent { event: WindowEvent::CloseRequested, .. } => {
                             if state.prevent_close {
                                 let mut found: Option<PyObject> = None;
                                 if let Ok(cbs) = cbs_arc.lock() {
                                     if let Some(f) = cbs.get("pytron_on_close") {
                                         Python::with_gil(|py| { found = Some(f.clone_ref(py)); });
                                     }
                                 }
                                 if let Some(f) = found {
                                     Python::with_gil(|py| { let _ = f.call0(py); }); 
                                 }
                                 *control_flow = ControlFlow::Wait;
                             } else {
                                 *control_flow = ControlFlow::Exit; 
                             }
                        }
                        _ => (),
                    }
                });
            });
        }
        Ok(())
    }

    pub fn set_title(&self, t: String) { let _ = self.proxy.send_event(UserEvent::SetTitle(t)); }
    pub fn set_size(&self, w: i32, h: i32, hints: u32) { let _ = self.proxy.send_event(UserEvent::SetSize(w, h, hints)); }
    pub fn navigate(&self, u: String) { let _ = self.proxy.send_event(UserEvent::Navigate(u)); }
    pub fn eval(&self, j: String) { let _ = self.proxy.send_event(UserEvent::Eval(j)); }
    pub fn bind(&self, n: String, f: PyObject) { 
        if let Ok(mut cbs) = self.callbacks.lock() {
            Python::with_gil(|py| { cbs.insert(n.clone(), f.clone_ref(py)); });
        }
        let _ = self.proxy.send_event(UserEvent::Bind(n, f)); 
    }
    pub fn return_result(&self, s: String, st: i32, r: String) { let _ = self.proxy.send_event(UserEvent::Return(s, st, r)); }
    pub fn terminate(&self) { let _ = self.proxy.send_event(UserEvent::Quit); }
    pub fn show(&self) { let _ = self.proxy.send_event(UserEvent::SetVisible(true)); }
    pub fn hide(&self) { let _ = self.proxy.send_event(UserEvent::SetVisible(false)); }
    pub fn minimize(&self) { let _ = self.proxy.send_event(UserEvent::Minimize); }
    pub fn maximize(&self) { let _ = self.proxy.send_event(UserEvent::SetMaximized(true)); }
    pub fn unmaximize(&self) { let _ = self.proxy.send_event(UserEvent::SetMaximized(false)); }
    pub fn start_drag(&self) { let _ = self.proxy.send_event(UserEvent::DragWindow); }
    pub fn system_notification(&self, t: String, m: String) { let _ = self.proxy.send_event(UserEvent::Notification(t, m)); }
    pub fn set_taskbar_progress(&self, s: i32, v: i32, m: i32) { let _ = self.proxy.send_event(UserEvent::TaskbarProgress(s, v, m)); }
    pub fn get_hwnd(&self) -> usize { self.hwnd }
    
    pub fn set_fullscreen(&self, e: bool) { let _ = self.proxy.send_event(UserEvent::SetFullscreen(e)); }
    pub fn set_always_on_top(&self, e: bool) { let _ = self.proxy.send_event(UserEvent::SetAlwaysOnTop(e)); }
    pub fn set_resizable(&self, e: bool) { let _ = self.proxy.send_event(UserEvent::SetResizable(e)); }
    pub fn set_decorations(&self, e: bool) { let _ = self.proxy.send_event(UserEvent::SetDecorations(e)); }
    pub fn center(&self) { let _ = self.proxy.send_event(UserEvent::CenterWindow); }

    #[pyo3(signature = (title, dir=None, filters=None))]
    pub fn dialog_open_file(&self, title: String, dir: Option<String>, filters: Option<String>) -> PyResult<Option<String>> {
        #[cfg(target_os = "windows")]
        {
            let mut d = rfd::FileDialog::new().set_title(&title);
            if let Some(p) = dir { d = d.set_directory(PathBuf::from(p)); }
            if let Some(f) = filters {
                 for group in f.split(';') {
                     let parts: Vec<&str> = group.split(':').collect();
                     if parts.len() == 2 {
                         let exts: Vec<&str> = parts[1].split(',').collect();
                         d = d.add_filter(parts[0], &exts);
                     }
                 }
            }
            let res = d.pick_file();
            Ok(res.map(|p| p.to_string_lossy().to_string()))
        }
        #[cfg(not(target_os = "windows"))]
        { Ok(None) }
    }

    #[pyo3(signature = (title, dir=None, name=None, filters=None))]
    pub fn dialog_save_file(&self, title: String, dir: Option<String>, name: Option<String>, filters: Option<String>) -> PyResult<Option<String>> {
         #[cfg(target_os = "windows")]
        {
            let mut d = rfd::FileDialog::new().set_title(&title);
            if let Some(p) = dir { d = d.set_directory(PathBuf::from(p)); }
            if let Some(n) = name { d = d.set_file_name(&n); }
             if let Some(f) = filters {
                 for group in f.split(';') {
                     let parts: Vec<&str> = group.split(':').collect();
                     if parts.len() == 2 {
                         let exts: Vec<&str> = parts[1].split(',').collect();
                         d = d.add_filter(parts[0], &exts);
                     }
                 }
            }
            let res = d.save_file();
            Ok(res.map(|p| p.to_string_lossy().to_string()))
        }
        #[cfg(not(target_os = "windows"))]
        { Ok(None) }
    }
    
    #[pyo3(signature = (title, dir=None))]
    pub fn dialog_open_folder(&self, title: String, dir: Option<String>) -> PyResult<Option<String>> {
         #[cfg(target_os = "windows")]
        {
            let mut d = rfd::FileDialog::new().set_title(&title);
            if let Some(p) = dir { d = d.set_directory(PathBuf::from(p)); }
            let res = d.pick_folder();
            Ok(res.map(|p| p.to_string_lossy().to_string()))
        }
        #[cfg(not(target_os = "windows"))]
        { Ok(None) }
    }

    pub fn message_box(&self, title: String, msg: String, level: String) -> PyResult<bool> {
        #[cfg(target_os = "windows")]
        {
             let l = match level.as_str() {
                 "error" => rfd::MessageLevel::Error,
                 "warning" => rfd::MessageLevel::Warning,
                 _ => rfd::MessageLevel::Info,
             };
             let res = rfd::MessageDialog::new().set_title(&title).set_description(&msg).set_level(l).show();
             let ret = match res {
                 rfd::MessageDialogResult::Ok | rfd::MessageDialogResult::Yes => true,
                 _ => false
             };
             Ok(ret)
        }
         #[cfg(not(target_os = "windows"))]
        { Ok(false) }
    }

    pub fn set_prevent_close(&self, p: bool) {
        let _ = self.proxy.send_event(UserEvent::SetPreventClose(p));
    }
    
    pub fn create_tray(&self, icon_path: String, tooltip: String) {
        let _ = self.proxy.send_event(UserEvent::CreateTray(icon_path, tooltip));
    }
}
