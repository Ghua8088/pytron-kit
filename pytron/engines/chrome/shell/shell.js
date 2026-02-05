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

// 16. Robust Synchronous Logging
const isDebug = process.argv.includes('--pytron-debug') || process.argv.includes('--inspect');

const log = (msg) => {
    const stamped = `[Mojo-Shell][${new Date().toISOString()}] ${msg}`;
    try {
        // Prepare logs dir if needed, or just stdout
        // fs.writeSync(1, stamped + "\n");
        console.log(stamped);
    } catch (e) {
        // Silent catch for EPIPE (Broken Pipe) or other stdout issues during shutdown
    }
};

log("--- MOJO SHELL BOOTING V7 (UNRESTRICTED) ---");

// Determine Root
const rootArg = process.argv.find(arg => arg.startsWith('--pytron-root='));
let PROJECT_ROOT = rootArg ? rootArg.split('=')[1] : null;
if (PROJECT_ROOT && PROJECT_ROOT.startsWith('"') && PROJECT_ROOT.endsWith('"')) {
    PROJECT_ROOT = PROJECT_ROOT.substring(1, PROJECT_ROOT.length - 1);
}

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
let clientIn = null;  // We Read
let clientOut = null; // We Write
let client = null;    // Legacy TCP or Unix Socket
let buffer = Buffer.alloc(0);
let initScripts = [];
let isAppReady = false;
let pendingCommands = [];

function connectToPytron() {
    const portArg = process.argv.find(arg => arg.startsWith('--pytron-port='));
    const pipeArg = process.argv.find(arg => arg.startsWith('--pytron-pipe='));

    if (pipeArg) {
        const pipeBase = pipeArg.split('=')[1];

        // Check if Windows (via path format)
        if (pipeBase.startsWith('\\\\.\\pipe\\')) {
            log(`Connecting to Dual Pipe IPC: ${pipeBase}`);

            // 1. Connect INBOUND (We Read, Python Writes)
            clientIn = new net.Socket();
            // 2. Connect OUTBOUND (We Write, Python Reads)
            clientOut = new net.Socket();

            let connectedCount = 0;
            const checkReady = () => {
                connectedCount++;
                if (connectedCount === 2) {
                    log("✅ Connected to Pytron Core (Dual Pipe). Sending Handshake...");
                    sendToPython('lifecycle', 'app_ready');
                }
            };

            clientIn.connect(pipeBase + '-in', () => {
                log("Connected to Pipe-IN (Reading)");
                checkReady();
            });

            clientOut.connect(pipeBase + '-out', () => {
                log("Connected to Pipe-OUT (Writing)");
                checkReady();
            });

            // Setup Reader on clientIn
            clientIn.on('data', (chunk) => {
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

            clientIn.on('error', (err) => log(`Pipe-IN Error: ${err.message}`));
            clientOut.on('error', (err) => log(`Pipe-OUT Error: ${err.message} (Code: ${err.code})`));

            clientIn.on('end', () => log("Pipe-IN Received FIN (End)"));
            clientOut.on('end', () => log("Pipe-OUT Received FIN (End)"));

            clientIn.on('close', (hadError) => {
                log(`Pipe-IN Closed. Had Error: ${hadError}`);
                app.quit();
            });
            clientOut.on('close', (hadError) => {
                log(`Pipe-OUT Closed. Had Error: ${hadError}`);
            });

        } else {
            // Unix Socket (Single)
            log(`Connecting to Unix Socket: ${pipeBase}`);
            client = new net.Socket();
            client.connect(pipeBase, () => {
                log("✅ Connected to Pytron Core (Unix Socket). Sending Handshake...");
                sendToPython('lifecycle', 'app_ready');
            });
            setupClientListeners(client);
        }

    } else if (portArg) {
        // TCP Fallback
        const port = parseInt(portArg.split('=')[1]);
        log(`Connecting to Python on port: ${port}`);

        client = new net.Socket();
        client.connect(port, '127.0.0.1', () => {
            log("✅ Connected to Pytron Core (TCP). Sending Handshake...");
            sendToPython('lifecycle', 'app_ready');
        });
        setupClientListeners(client);
    } else {
        log("FATAL: No --pytron-port or --pytron-pipe provided");
        return;
    }
}

function setupClientListeners(socket) {
    socket.on('data', (chunk) => {
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
    socket.on('error', (err) => log(`Socket Error: ${err.message}`));
    socket.on('close', () => {
        log("Socket Closed. Exiting.");
        app.quit();
    });
}

function sendToPython(type, payload) {
    const target = clientOut || client;

    if (target && !target.destroyed) {
        try {
            const bodyStr = JSON.stringify({ type, payload });
            const bodyBuf = Buffer.from(bodyStr, 'utf8');
            const headerBuf = Buffer.alloc(4);
            headerBuf.writeUInt32LE(bodyBuf.length, 0);
            target.write(Buffer.concat([headerBuf, bodyBuf]));
        } catch (e) {
            log(`Send Error: ${e.message}`);
        }
    }
}

function handlePythonCommand(cmd) {
    if (isDebug) log(`Executing: ${cmd.substring(0, 100)}...`);

    if (!isAppReady) {
        log("Queueing command (App not ready)");
        pendingCommands.push(cmd);
        return;
    }

    try {
        const command = JSON.parse(cmd);
        switch (command.action) {
            case 'init':
                if (command.options && command.options.root) {
                    PROJECT_ROOT = command.options.root;
                    log(`Updating PROJECT_ROOT to: ${PROJECT_ROOT}`);
                }
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
                if (mainWindow) mainWindow.webContents.executeJavaScript(command.code).catch(e => log(`Eval Err: ${e.message}`)); // nosemgrep
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
            case 'show':
                if (mainWindow) {
                    log("Force Show command received");
                    mainWindow.show();
                    mainWindow.focus();
                } else {
                    log("Received Show command but mainWindow is NULL");
                }
                break;
            case 'hide': if (mainWindow) mainWindow.hide(); break;
            case 'bind':
                const stub = `
                    window["${command.name}"] = (...args) => {
                        const seq = Math.random().toString(36).substr(2, 9);
                        return new Promise((resolve, reject) => {
                            window._pytron_promises = window._pytron_promises || {};
                            window._pytron_promises[seq] = { resolve, reject };
                            if (window.__pytron_native_bridge) {
                                window.__pytron_native_bridge.emit("${command.name}", { data: args, id: seq });
                            } else if (window.pytron && window.pytron.emit) {
                                window.pytron.emit("${command.name}", { data: args, id: seq });
                            }
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
            case 'serve_data':
                // command: { action: 'serve_data', key: '...', data: 'BASE64...', mime: '...' }
                if (global.serveAsset) {
                    global.serveAsset(command.key, command.data, command.mime);
                }
                break;
            case 'unserve_data':
                if (global.unserveAsset) {
                    global.unserveAsset(command.key);
                }
                break;
            case 'debugger':
                try {
                    // Evaluate JS on the main process if needed
                    eval(command.code); // nosemgrep
                } catch (e) { log(`Debugger Error: ${e.message}`); }
                break;
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
    config.resizable = options.resizable !== undefined ? !!options.resizable : true;
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

    // Transparent
    if (options.transparent) {
        config.transparent = true;
    }

    // Robust Frameless with Snapping (Windows-first logic)
    if (options.frameless) {
        config.frame = false;
        // On macOS/Windows, 'hidden' allows the OS to still handle snapping/resize margins 
        // while the titlebar stays invisible.
        config.titleBarStyle = 'hidden';
    }

    config.show = false; // Always start false, show on ready

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

    // External Links: Open in Default Browser (Maintain "Application" vibe)
    mainWindow.webContents.on('will-navigate', (event, url) => {
        if (!url.startsWith('pytron://') && !url.startsWith('https://pytron.') && url !== 'about:blank') {
            event.preventDefault();
            shell.openExternal(url);
        }
    });

    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        if (!url.startsWith('pytron://') && !url.startsWith('https://pytron.') && url !== 'about:blank') {
            shell.openExternal(url);
            return { action: 'deny' };
        }
        return { action: 'allow' };
    });

    if (config.debug) mainWindow.webContents.openDevTools();
    if (config.url) mainWindow.loadURL(config.url);

    mainWindow.once('ready-to-show', () => {
        log("Event: ready-to-show. Processing start state.");
        applyInitScripts();
        sendToPython('lifecycle', 'ready');

        if (options.start_hidden) {
            log("Starting Hidden");
            return;
        }

        if (options.start_minimized) {
            mainWindow.minimize();
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

const gotTheLock = app.requestSingleInstanceLock()
if (!gotTheLock) {
    app.quit()
} else {
    app.whenReady().then(() => {
        log("Electron Ready");

        // 2. Intercept requests to pytron://
        // We register the handler on the SPECIFIC session partition used by the window.
        // The global 'protocol' module only affects session.defaultSession.
        const servedData = new Map();

        // Export internal serve function for IPC usage
        global.serveAsset = (key, dataBase64, mimeType) => {
            const buffer = Buffer.from(dataBase64, 'base64');
            servedData.set(key, { buffer, mimeType });
            log(`[Protocol] Memory Asset Served: ${key} (${mimeType})`);
        };

        global.unserveAsset = (key) => {
            if (servedData.has(key)) {
                servedData.delete(key);
                log(`[Protocol] Memory Asset Removed: ${key}`);
            }
        };

        const handler = (request) => {
            let urlPath = request.url.replace('pytron://', '');
            urlPath = urlPath.split('?')[0];

            // 1. Check Memory Store (O(1) Lookup for Dynamic Assets)
            if (servedData.has(urlPath)) {
                const asset = servedData.get(urlPath);
                return new Response(asset.buffer, {
                    headers: { 'content-type': asset.mimeType }
                });
            }

            // 2. Fallback to Disk (Project Root)
            if (!PROJECT_ROOT) {
                return new Response("Project Root Not Set", { status: 500 });
            }

            // Normalize urlPath: Remove leading 'app/' or '/'
            let normalizedPath = urlPath;
            if (normalizedPath.startsWith('app/')) {
                normalizedPath = normalizedPath.substring(4);
            } else if (normalizedPath.startsWith('/')) {
                normalizedPath = normalizedPath.substring(1);
            }

            let filePath = path.join(PROJECT_ROOT, normalizedPath);
            // log(`[Protocol] Request: ${request.url} -> ${filePath}`);

            try {
                if (fs.existsSync(filePath) && fs.lstatSync(filePath).isFile()) {
                    const data = fs.readFileSync(filePath);
                    return new Response(data, {
                        headers: { 'content-type': getMimeType(filePath) }
                    });
                }
                // log(`[Protocol] File Not Found: ${filePath}`);
                return new Response("Not Found", { status: 404 });
            } catch (e) {
                log(`[Protocol] Error serving ${urlPath}: ${e.message}`);
                return new Response("Internal Error", { status: 500 });
            }
        };

        protocol.handle('pytron', handler);
        session.fromPartition('persist:main').protocol.handle('pytron', handler);

        isAppReady = true;
        while (pendingCommands.length > 0) {
            handlePythonCommand(pendingCommands.shift());
        }
    });
}

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });

// Start the client
connectToPytron();
