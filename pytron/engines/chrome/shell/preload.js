const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('pytron', {
    emit: (event, data) => ipcRenderer.send('pytron-message', { event, data }),
    on: (channel, func) => {
        // Simple subscription provided by Electron
        ipcRenderer.on(channel, (event, ...args) => func(...args));
    }
});

window.addEventListener('DOMContentLoaded', () => {
    window.pytron_native_ready = true;
});
