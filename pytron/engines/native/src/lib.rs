use pyo3::prelude::*;

pub mod events;
pub mod state;
pub mod utils;
pub mod protocol;
pub mod webview;
pub mod ipc;

use crate::webview::NativeWebview;
use crate::ipc::ChromeIPC;

#[pymodule]
fn pytron_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<NativeWebview>()?;
    m.add_class::<ChromeIPC>()?;
    Ok(())
}
