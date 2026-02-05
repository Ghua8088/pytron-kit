use std::borrow::Cow;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::collections::HashMap;
use pyo3::prelude::*;
use wry::http::{Response, header, StatusCode, Method, Request};

pub fn handle_pytron_protocol(
    request: Request<Vec<u8>>,
    protocol_root: PathBuf,
    callbacks: Arc<Mutex<HashMap<String, PyObject>>>,
) -> Response<Cow<'static, [u8]>> {
    let uri = request.uri();
    let method = request.method();
    
    // 1. Handle CORS Preflight
    if method == Method::OPTIONS {
        return Response::builder()
            .header("Access-Control-Allow-Origin", "*")
            .header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
            .header("Access-Control-Allow-Headers", "*")
            .body(Cow::from(Vec::new())).unwrap();
    }

    // 2. Extract the path correctly
    let path = uri.path().trim_start_matches('/');
    
    // 3. Clean up the path
    let clean_path = path.strip_prefix("app/").unwrap_or(path);
    
    if clean_path == "about:blank" {
         return Response::builder()
            .status(StatusCode::OK)
            .body(Cow::from(Vec::new()))
            .unwrap();
    }

    let decoded = urlencoding::decode(clean_path).unwrap_or(Cow::Borrowed(clean_path));
    
    // 4. Join with root and handle directories
    let mut final_path = protocol_root.join(decoded.as_ref());
    
    if final_path.is_dir() {
        final_path = final_path.join("index.html");
    }

    match std::fs::read(&final_path) {
        Ok(data) => {
            let mime = mime_guess::from_path(&final_path).first_or_octet_stream();
            let mime_str = mime.to_string();
            let mut resp_data = data;

            // Manual Bridge Injection
            if mime.subtype() == "html" {
                if let Ok(content) = String::from_utf8(resp_data.clone()) {
                    let mut method_bindings = String::new();
                    if let Ok(cbs) = callbacks.lock() {
                        for name in cbs.keys() {
                            method_bindings.push_str(&format!(
                                "window['{}'] = (...args) => window.__pytron_native_bridge('{}', args);\n",
                                name, name
                            ));
                        }
                    }

                    let bridge_script = format!(r#"
                    <script>
                    window.pytron_is_native = true;
                    window.pytron = window.pytron || {{}};
                    window.pytron.is_ready = true;
                    window.__pytron_native_bridge = (method, args) => {{
                        const seq = Math.random().toString(36).substring(2, 10);
                        window.ipc.postMessage(JSON.stringify({{id: seq, method: method, params: args}}));
                        return new Promise((resolve, reject) => {{
                            window._rpc = window._rpc || {{}};
                            window._rpc[seq] = {{resolve, reject}};
                        }});
                    }};
                    window.pytron_close = () => window.__pytron_native_bridge('pytron_close', []);
                    window.pytron_drag = () => window.__pytron_native_bridge('pytron_drag', []);
                    window.pytron_log = (msg) => window.__pytron_native_bridge('pytron_log', [msg]);
                    
                    // Override alert to use native message box
                    window.alert = (msg) => {{
                        window.__pytron_native_bridge('pytron_message_box', ["Alert", String(msg), "info"]);
                    }};
                    {}
                    </script>
                    "#, method_bindings);

                    let injected = if content.contains("</head>") {
                        content.replace("</head>", &format!("{}</head>", bridge_script))
                    } else {
                        content.replace("<body>", &format!("<body>{}", bridge_script))
                    };
                    resp_data = injected.into_bytes();
                }
            }

            Response::builder()
                .status(StatusCode::OK)
                .header(header::CONTENT_TYPE, mime_str)
                .header("Access-Control-Allow-Origin", "*")
                .body(Cow::from(resp_data))
                .unwrap()
        }
        Err(_) => {
            // Fallback to VAP
            let mut served_data: Option<(Vec<u8>, String)> = None;
            let func_opt = {
                if let Ok(cbs) = callbacks.lock() {
                     cbs.get("pytron_serve_asset").map(|f| Python::with_gil(|py| f.clone_ref(py)))
                } else {
                    None
                }
            };

            if let Some(func) = func_opt {
                 Python::with_gil(|py| {
                     if let Ok(res) = func.call1(py, (decoded.as_ref(),)) {
                         if let Ok((data, mime)) = res.extract::<(Vec<u8>, String)>(py) {
                             served_data = Some((data, mime));
                         }
                     }
                 });
            }

            if let Some((data, mime)) = served_data {
                 Response::builder()
                    .status(StatusCode::OK)
                    .header(header::CONTENT_TYPE, mime)
                    .header("Access-Control-Allow-Origin", "*")
                    .body(Cow::from(data))
                    .unwrap()
            } else {
                Response::builder().status(StatusCode::NOT_FOUND).body(Cow::from(Vec::new())).unwrap()
            }
        }
    }
}
