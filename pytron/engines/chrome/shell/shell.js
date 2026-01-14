const { app, BrowserWindow, ipcMain, protocol, shell, session } = require('electron');
const path = require('path');
const net = require('net');
const fs = require('fs');

// Disable GPU if requested or for compatibility (user can toggle via flags if needed)
if (process.argv.includes('--disable-gpu')) {
    app.disableHardwareAcceleration();
}

// 1. Register 'pytron' as a secure, standard scheme
protocol.registerSchemesAsPrivileged([
    { scheme: 'pytron', privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, bypassCSP: true } }
]);

// Robust Synchronous Logging
const log = (msg) => {
    const stamped = `[Mojo-Shell][${new Date().toISOString()}] ${msg}`;
    try {
        // Prepare logs dir if needed, or just stdout
        // fs.writeSync(1, stamped + "\n");
    } catch (e) { }
    console.log(stamped);
};

log("--- MOJO SHELL BOOTING V7 (UNRESTRICTED) ---");

// Determine Root
const rootArg = process.argv.find(arg => arg.startsWith('--pytron-root='));
const PROJECT_ROOT = rootArg ? rootArg.split('=')[1] : null;

// Helper for MIME types
function getMimeType(filename) {
    if (filename.endsWith('.js')) return 'text/javascript';
    if (filename.endsWith('.css')) return 'text/css';
    if (filename.endsWith('.html')) return 'text/html';
    if (filename.endsWith('.json')) return 'application/json';
    if (filename.endsWith('.png')) return 'image/png';
    if (filename.endsWith('.jpg') || filename.endsWith('.jpeg')) return 'image/jpeg';
    if (filename.endsWith('.svg')) return 'image/svg+xml';
    if (filename.endsWith('.webp')) return 'image/webp';
    if (filename.endsWith('.ico')) return 'image/x-icon';
    return 'application/octet-stream';
}

const WINDOW_CONFIG = {
    show: false, // Wait until ready-to-show
    width: 1024,
    height: 768,
    backgroundColor: '#ffffff',
    webPreferences: {
        nodeIntegration: false, // Pruned: No Node in renderer
        contextIsolation: true, // Secure bridge
        sandbox: false,         // Unrestricted: Allow complex IPC/File access
        webSecurity: false,     // Unrestricted: CORS disabled, local files allowed
        partition: 'persist:main', // Ditto like webview: Persist session
        preload: path.join(__dirname, 'preload.js'),
        devTools: true
    }
};

let mainWindow;
let client = null;
let buffer = Buffer.alloc(0);
let initScripts = [];
let isAppReady = false;
let pendingCommands = [];

function connectToPytron() {
    const portArg = process.argv.find(arg => arg.startsWith('--pytron-port='));
    if (!portArg) {
        log("FATAL: No --pytron-port provided");
        return;
    }
    const port = parseInt(portArg.split('=')[1]);

    log(`Connecting to Python on port: ${port}`);
    client = new net.Socket();

    client.connect(port, '127.0.0.1', () => {
        log("✅ Connected to Pytron Core. Sending Handshake...");
        sendToPython('lifecycle', 'app_ready');
    });

    client.on('data', (chunk) => {
        buffer = Buffer.concat([buffer, chunk]);
        while (buffer.length >= 4) {
            const msgLen = buffer.readUInt32LE(0);
            if (buffer.length >= 4 + msgLen) {
                const bodyBytes = buffer.slice(4, 4 + msgLen);
                const bodyString = bodyBytes.toString('utf-8');
                handlePythonCommand(bodyString);
                buffer = buffer.slice(4 + msgLen);
            } else {
                break;
            }
        }
    });

    client.on('error', (err) => log(`Socket Error: ${err.message}`));
    client.on('close', () => {
        log("Socket Closed. Exiting.");
        app.quit();
    });
}

function sendToPython(type, payload) {
    if (client && !client.destroyed) {
        const bodyStr = JSON.stringify({ type, payload });
        const bodyBuf = Buffer.from(bodyStr, 'utf8');
        const headerBuf = Buffer.alloc(4);
        headerBuf.writeUInt32LE(bodyBuf.length, 0);
        client.write(Buffer.concat([headerBuf, bodyBuf]));
    }
}

function handlePythonCommand(cmd) {
    log(`Executing: ${cmd.substring(0, 100)}...`);

    if (!isAppReady) {
        log("Queueing command (App not ready)");
        pendingCommands.push(cmd);
        return;
    }

    try {
        const command = JSON.parse(cmd);
        switch (command.action) {
            case 'init':
                createWindow(command.options);
                break;
            case 'init_script':
                initScripts.push(command.js);
                if (mainWindow) mainWindow.webContents.executeJavaScript(command.js).catch(e => log(`Init Err: ${e.message}`));
                break;
            case 'navigate':
                if (mainWindow) {
                    log(`Navigating to: ${command.url}`);
                    mainWindow.loadURL(command.url);
                }
                break;
            case 'eval':
                if (mainWindow) mainWindow.webContents.executeJavaScript(command.code).catch(e => log(`Eval Err: ${e.message}`));
                break;
            case 'set_title':
                if (mainWindow) mainWindow.setTitle(command.title);
                break;
            case 'set_size':
                if (mainWindow) {
                    mainWindow.setSize(command.width, command.height);
                    mainWindow.show();
                }
                break;
            case 'center':
                if (mainWindow) mainWindow.center();
                break;
            case 'minimize':
                if (mainWindow) mainWindow.minimize();
                break;
            case 'toggle_maximize':
                if (mainWindow) {
                    if (mainWindow.isMaximized()) mainWindow.unmaximize();
                    else mainWindow.maximize();
                }
                break;
            case 'set_frameless':
                // Can't change frameless dynamically easily in Electron without recreation
                break;
            case 'set_progress':
                // command.value: 0.0 to 1.0.  -1 to remove.
                // command.mode: 'none', 'normal', 'indeterminate', 'error', 'paused'
                if (mainWindow) {
                    const val = command.value !== undefined ? command.value : -1;
                    const mode = command.mode || 'normal';
                    mainWindow.setProgressBar(val, { mode: mode });
                }
                break;
            case 'show': if (mainWindow) { mainWindow.show(); mainWindow.focus(); } break;
            case 'hide': if (mainWindow) mainWindow.hide(); break;
            case 'bind':
                const stub = `
                    window["${command.name}"] = (...args) => {
                        const seq = Math.random().toString(36).substr(2, 9);
                        return new Promise((resolve, reject) => {
                            window._pytron_promises = window._pytron_promises || {};
                            window._pytron_promises[seq] = { resolve, reject };
                            window.pytron.emit("${command.name}", { data: args, id: seq });
                        });
                    };
                `;
                initScripts.push(stub);
                if (mainWindow) mainWindow.webContents.executeJavaScript(stub).catch(() => { });
                break;
            case 'reply':
                if (mainWindow) {
                    const js = `
                        if (window._pytron_promises && window._pytron_promises["${command.id}"]) {
                            const p = window._pytron_promises["${command.id}"];
                            if (${command.status} === 0) p.resolve(${JSON.stringify(command.result)});
                            else p.reject(${JSON.stringify(command.result)});
                            delete window._pytron_promises["${command.id}"];
                        }
                    `;
                    mainWindow.webContents.executeJavaScript(js).catch(() => { });
                }
                break;
            case 'close': app.quit(); break;
        }
    } catch (e) { log(`Execution Error: ${e.message}`); }
}

async function createWindow(options = {}) {
    if (mainWindow) return;

    log("Creating BrowserWindow...");
    const config = { ...WINDOW_CONFIG, ...options };

    // Icon (Resolve absolute path if provided)
    if (options.icon) {
        config.icon = options.icon; // Electron handles absolute paths fine
    }

    // Enhanced Window Configuration
    config.resizable = options.resizable !== undefined ? options.resizable : true;
    config.alwaysOnTop = !!options.always_on_top;
    config.fullscreen = !!options.fullscreen;

    if (options.min_size) {
        config.minWidth = options.min_size[0];
        config.minHeight = options.min_size[1];
    }
    if (options.max_size) {
        config.maxWidth = options.max_size[0];
        config.maxHeight = options.max_size[1];
    }
    if (options.background_color) {
        config.backgroundColor = options.background_color;
    }

    // Pruned: Remove Frame by default if requested or generally if emulating a raw view
    // Ensure we respect the user's explicit config from Python
    if (options.frameless) {
        config.frame = false;
        config.titleBarStyle = 'hidden';
    }

    // Start Hidden Logic
    if (options.start_hidden) {
        config.show = false;
    }

    mainWindow = new BrowserWindow(config);

    // SEND HWND TO PYTHON (Critical for Taskbar/Native Ops)
    try {
        const handle = mainWindow.getNativeWindowHandle();
        let hwndStr = "0";
        if (handle.length === 8) {
            hwndStr = handle.readBigUInt64LE(0).toString();
        } else if (handle.length === 4) {
            hwndStr = handle.readUInt32LE(0).toString();
        }
        sendToPython('lifecycle', { event: 'window_created', hwnd: hwndStr });
    } catch (e) {
        log(`HWND Error: ${e.message}`);
    }

    // Simple Pruned Webview: Remove Menu
    mainWindow.setMenu(null);

    // External Links: Open in Default Browser (Ditto webview behavior)
    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        if (url.startsWith('https:') || url.startsWith('http:')) {
            shell.openExternal(url);
            return { action: 'deny' };
        }
        return { action: 'allow' };
    });

    if (config.debug) mainWindow.webContents.openDevTools();
    if (config.url) mainWindow.loadURL(config.url);

    mainWindow.once('ready-to-show', () => {
        log("Event: ready-to-show");
        applyInitScripts();
        sendToPython('lifecycle', 'ready');

        if (options.start_hidden) {
            return;
        }

        if (options.start_maximized) {
            mainWindow.maximize();
        } else {
            mainWindow.show();
            mainWindow.focus();
        }
    });

    mainWindow.on('close', () => sendToPython('lifecycle', 'close'));
    ipcMain.on('pytron-message', (event, arg) => sendToPython('ipc', arg));
}

function applyInitScripts() {
    if (!mainWindow) return;
    initScripts.forEach(js => {
        mainWindow.webContents.executeJavaScript(js).catch(() => { });
    });
}

app.whenReady().then(() => {
    log("Electron Ready");

    // 2. Intercept requests to pytron://
    // We register the handler on the SPECIFIC session partition used by the window.
    // The global 'protocol' module only affects session.defaultSession.
    const handler = (request) => {
        let urlPath = request.url.replace('pytron://', '');
        urlPath = urlPath.split('?')[0];

        if (!PROJECT_ROOT) {
            return new Response("Project Root Not Set", { status: 500 });
        }

        let filePath = path.join(PROJECT_ROOT, urlPath.replace('app/', ''));
        if (process.platform === 'win32') {
            // Handle windows absolute paths if accidentally passed?
        }
        log(`[Protocol] Serving: ${filePath}`);

        try {
            const data = fs.readFileSync(filePath);
            return new Response(data, {
                headers: { 'content-type': getMimeType(filePath) }
            });
        } catch (e) {
            log(`[Protocol] Error serving ${urlPath}: ${e.message}`);
            return new Response("Not Found", { status: 404 });
        }
    };

    protocol.handle('pytron', handler);
    session.fromPartition('persist:main').protocol.handle('pytron', handler);

    isAppReady = true;
    while (pendingCommands.length > 0) {
        handlePythonCommand(pendingCommands.shift());
    }
});

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });

// Start the client
connectToPytron();
