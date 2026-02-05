use std::panic;

pub fn setup_panic_hook() {
    static ONCE: std::sync::Once = std::sync::Once::new();
    ONCE.call_once(|| {
        panic::set_hook(Box::new(|info| {
            let location = info.location().map(|l| format!("{}:{}:{}", l.file(), l.line(), l.column())).unwrap_or_else(|| "unknown".to_string());
            let msg = match info.payload().downcast_ref::<&str>() {
                Some(s) => *s,
                None => match info.payload().downcast_ref::<String>() {
                    Some(s) => &s[..],
                    None => "Box<Any>",
                },
            };
            eprintln!("[PYTRON PANIC] Fatal Error at {}: {}", location, msg);
        }));
    });
}

pub struct SendWrapper<T>(T);
unsafe impl<T> Send for SendWrapper<T> {}
unsafe impl<T> Sync for SendWrapper<T> {}
impl<T> SendWrapper<T> { 
    pub fn new(val: T) -> Self { Self(val) }
    pub fn take(self) -> T { self.0 } 
}

pub fn load_icon(path: &std::path::Path) -> Result<tray_icon::Icon, Box<dyn std::error::Error>> {
    let image = image::open(path)?;
    let rgba = image.to_rgba8();
    let (width, height) = rgba.dimensions();
    let rgba_bytes = rgba.into_raw();
    Ok(tray_icon::Icon::from_rgba(rgba_bytes, width, height)?)
}
