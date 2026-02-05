use serde::{Deserialize};
use std::path::Path;
use std::fs;

#[derive(Deserialize, Debug)]
pub struct Settings {
    pub title: Option<String>,
    #[allow(dead_code)]
    pub version: Option<String>,
    pub author: Option<String>,
}

pub fn load_settings(root: &Path, embedded: Option<String>) -> Option<Settings> {
    if let Some(json) = embedded {
        if let Ok(s) = serde_json::from_str(&json) {
            return Some(s);
        }
    }
    // Fallback to disk (legacy/dev support)
    let settings_path = root.join("settings.json");
    if !settings_path.exists() {
        return None;
    }
    let content = fs::read_to_string(settings_path).ok()?;
    serde_json::from_str(&content).ok()
}
