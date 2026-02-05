use pyo3::prelude::*;

pub enum UserEvent {
    Eval(String),
    Bind(String, PyObject),   
    Dispatch(PyObject, String, String), // Func, Seq, MethodName
    DispatchData(PyObject, String, String, String), // Func, Seq, Args, MethodName
    CallPython(PyObject, String, String, String), 
    
    Return(String, i32, String),
    SetTitle(String),
    SetSize(i32, i32, u32),
    Navigate(String),
    Quit,
    Minimize,
    SetMaximized(bool),
    SetVisible(bool),
    DragWindow,
    SetAlwaysOnTop(bool),
    Notification(String, String), // Title, Message
    TaskbarProgress(i32, i32, i32), // State, Value, Max
    SetResizable(bool),
    SetFullscreen(bool),
    CenterWindow,
    SetPreventClose(bool),
    CreateTray(String, String), // icon_path, tooltip
    TrayMenuClick(String), // id
    SetDecorations(bool),
    MessageBox(String, String, String, String), // Title, Message, Level, Seq
    OpenExternal(String),
}
