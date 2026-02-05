const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('__pytron_native_bridge', {
    emit: (event, data) => ipcRenderer.send('pytron-message', { event, data }),
    on: (channel, func) => {
        ipcRenderer.on(channel, (event, ...args) => func(...args));
    }
});

window.addEventListener('DOMContentLoaded', () => {
    window.pytron_native_ready = true;
});
