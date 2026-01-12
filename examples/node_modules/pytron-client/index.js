/**
 * Pytron Client Library (Final Stable Version)
 */

// 1. LOCAL STATE
const state = {};

// 2. BACKEND READINESS CHECK
const isBackendReady = () => {
    // Priority: Check the injected flag
    if (window.pytron && window.pytron.is_ready) return true;

    // Fallback: Check for a known bound function
    const hasClose = typeof window.pytron_close === 'function';
    const hasDrag = typeof window.pytron_drag === 'function';

    // DEBUG LOG ONLY (Remove in prod if needed, but useful now)
    // console.log(`[Pytron Debug] Checking Backend: ready=${window.pytron?.is_ready}, hasClose=${hasClose}, hasDrag=${hasDrag}`);

    return typeof window !== 'undefined' && (hasClose || hasDrag);
};

// 3. WAIT LOGIC (Standalone Function)
const waitForBackend = (timeout = 3000) => {
    return new Promise((resolve, reject) => {
        if (isBackendReady()) return resolve();

        const start = Date.now();
        const interval = setInterval(() => {
            if (isBackendReady()) {
                clearInterval(interval);
                resolve();
            } else if (Date.now() - start > timeout) {
                clearInterval(interval);
                console.warn("[Pytron] Backend wait timed out.");
                resolve(); // resolve anyway to let the call proceed and fail naturally
            }
        }, 50);
    });
};

// 4. EVENT LISTENERS
const eventWrappers = new Map();

// 5. PUBLIC API OBJECT (The "Real" Object)
// We define the API explicitly first.
const pytronApi = {
    state: state,

    // Expose the wait function directly
    waitForBackend: waitForBackend,

    on: (event, callback) => {
        const wrapper = (e) => callback(e.detail !== undefined ? e.detail : e);
        if (!eventWrappers.has(callback)) eventWrappers.set(callback, wrapper);
        window.addEventListener(event, wrapper);
    },

    off: (event, callback) => {
        const wrapper = eventWrappers.get(callback);
        if (wrapper) {
            window.removeEventListener(event, wrapper);
            eventWrappers.delete(callback);
        }
    },

    log: async (message) => {
        console.log(`[Pytron Client] ${message}`);
        const logFunc = window.pytron_log || window.log;
        if (typeof logFunc === 'function') {
            try { await logFunc(message); } catch (e) { /* ignore */ }
        }
    },

    /**
     * Sends an event to ALL windows including this one.
     */
    publish: async (event, data) => {
        if (typeof window.app_publish === 'function') {
            return await window.app_publish(event, data);
        }
    },

    /**
     * Helper to resolve pytron:// assets to Data URIs or Blobs
     */
    asset: async (key) => {
        // Try the optimized binary bridge first (VAP)
        if (typeof window.__pytron_vap_get === 'function') {
            try {
                const asset = await window.__pytron_vap_get(key);
                if (asset) {
                    const bytes = new Uint8Array(asset.raw.length);
                    for (let i = 0; i < asset.raw.length; i++) {
                        bytes[i] = asset.raw.charCodeAt(i);
                    }
                    return new Blob([bytes], { type: asset.mime });
                }
            } catch (e) {
                console.error("[Pytron] VAP Asset resolution failed:", e);
            }
        }

        // Fallback for legacy / slower Base64 bridge
        if (typeof window.pytron_get_asset === 'function') {
            try {
                const asset = await window.pytron_get_asset(key);
                return asset ? asset.data : null;
            } catch (e) {
                console.error("[Pytron] Legacy Asset resolution failed:", e);
                return null;
            }
        }
        return null;
    }
};

// 6. GLOBAL ASSET INTERCEPTOR
// We only hook fetch if it hasn't been handled by the Pytron Core yet
if (typeof window !== 'undefined' && !window.__pytron_fetch_interceptor_active) {
    const originalFetch = window.fetch;
    window.fetch = async (...args) => {
        let [resource] = args;
        const url = (typeof resource === 'string') ? resource :
            (resource instanceof URL ? resource.href : (resource && resource.url));

        if (url && url.startsWith('pytron://')) {
            const key = url.replace('pytron://', '').split(/[?#]/)[0];
            const asset = await pytronApi.asset(key);
            if (asset) {
                if (asset instanceof Blob) return new Response(asset);
                return originalFetch(asset); // Data URI fallback
            }
        }
        return originalFetch(...args);
    };
    window.__pytron_fetch_interceptor_active = true;
}

// 6. THE PROXY (Only for dynamic Python calls)
const pytron = new Proxy(pytronApi, {
    get: (target, prop) => {
        // A. Local Method Check (Priority)
        // If the property exists on our defined API object, return it immediately.
        if (prop in target) {
            return target[prop];
        }

        // B. Ignore React/System Symbols
        if (typeof prop === 'symbol' || prop === 'then' || prop === 'toJSON') {
            return undefined;
        }

        // C. Python Bridge (Dynamic Wrapper)
        return async (...args) => {

            // 1. Wait for Backend (Using the standalone function)
            if (!isBackendReady()) {
                await waitForBackend(2000);
            }

            // 2. Execute Python Function
            const internalName = `pytron_${String(prop)}`; // e.g. pytron_minimize
            const directName = String(prop);                // e.g. greet

            // Try Internal (pytron_*)
            if (typeof window[internalName] === 'function') {
                try {
                    return await window[internalName](...args);
                } catch (err) {
                    console.error(`[Pytron] Internal error '${internalName}':`, err);
                    throw err;
                }
            }

            // Try Direct
            if (typeof window[directName] === 'function') {
                try {
                    return await window[directName](...args);
                } catch (err) {
                    console.error(`[Pytron] Python error '${directName}':`, err);
                    throw err;
                }
            }

            // 3. Not Found
            console.warn(`[Pytron] Method '${String(prop)}' not found.`);
            throw new Error(`Method '${String(prop)}' not found.`);
        };
    }
});

// Setup State Listener
if (typeof window !== 'undefined') {
    // Initial Sync
    (async () => {
        await waitForBackend(2000);
        if (typeof window.pytron_sync_state === 'function') {
            try {
                const initialState = await window.pytron_sync_state();
                Object.assign(state, initialState);
                
                // --- DYNAMIC PLUGIN UI INJECTION ---
                if (state.plugins && Array.isArray(state.plugins)) {
                    state.plugins.forEach(plugin => {
                        if (plugin.ui_entry) {
                            console.log(`[Pytron Client] Auto-loading Plugin UI: ${plugin.name} from ${plugin.ui_entry}`);
                            
                            // 1. Inject Script
                            const scriptId = `pytron-plugin-${plugin.name}`;
                            if (!document.getElementById(scriptId)) {
                                const script = document.createElement('script');
                                script.id = scriptId;
                                script.src = plugin.ui_entry;
                                script.type = 'module';
                                document.head.appendChild(script);
                                
                                // 2. Handle Auto-Slotted Components
                                if (plugin.slot) {
                                    script.onload = () => {
                                        const slotContainers = document.querySelectorAll(`[data-pytron-slot="${plugin.slot}"]`);
                                        slotContainers.forEach(container => {
                                            const tagName = `${plugin.name}-widget`;
                                            // Check if already injected in this container
                                            if (!container.querySelector(tagName)) {
                                                const el = document.createElement(tagName);
                                                container.appendChild(el);
                                            }
                                        });
                                    };
                                }
                            }
                        }
                    });
                }

                // Dispatch event so UI components can update
                window.dispatchEvent(new CustomEvent('pytron:state', { detail: { ...state } }));
            } catch (e) { /* ignore */ }
        }
    })();

    window.addEventListener('pytron:state-update', (e) => {
        const payload = e.detail;
        if (payload && typeof payload === 'object' && 'key' in payload) {
            state[payload.key] = payload.value;

            // 1. Dispatch specific event for the key
            const specificEvent = new CustomEvent(`state:${payload.key}`, { detail: payload.value });
            window.dispatchEvent(specificEvent);

            // 2. Dispatch legacy 'pytron:state' event with full state for components listening to everything
            const legacyEvent = new CustomEvent('pytron:state', { detail: { ...state } });
            window.dispatchEvent(legacyEvent);

            // 3. Handle Plugin Registration (if the 'plugins' key was updated)
            if (payload.key === 'plugins' && Array.isArray(payload.value)) {
                payload.value.forEach(plugin => {
                    if (plugin.ui_entry && !window.__pytron_loaded_plugins?.has(plugin.name)) {
                        injectPlugin(plugin);
                    }
                });
            }
        }
    });

    // Helper to inject plugin scripts and handle slots
    const injectPlugin = (plugin) => {
        if (!window.__pytron_loaded_plugins) window.__pytron_loaded_plugins = new Set();
        window.__pytron_loaded_plugins.add(plugin.name);

        console.log(`[Pytron Client] Loading UI for plugin: ${plugin.name} from ${plugin.ui_entry}`);
        
        const script = document.createElement('script');
        script.src = plugin.ui_entry;
        script.type = 'module';
        script.onload = () => {
            console.log(`[Pytron Client] Plugin script loaded: ${plugin.name}`);
            // Check for slot injection
            if (plugin.slot) {
                const containers = document.querySelectorAll(`[data-pytron-slot="${plugin.slot}"]`);
                containers.forEach(container => {
                    const el = document.createElement(`${plugin.name}-widget`);
                    container.appendChild(el);
                });
            }
        };
        document.head.appendChild(script);
    };

    // Listen for discrete plugin load events
    window.addEventListener('pytron:plugin-loaded', (e) => {
        injectPlugin(e.detail);
    });

    // Capture Global Errors
    window.addEventListener('error', (event) => {
        const errorData = {
            message: event.message,
            source: event.filename,
            lineno: event.lineno,
            colno: event.colno,
            stack: event.error ? event.error.stack : ''
        };
        if (typeof window.pytron_report_error === 'function') {
            window.pytron_report_error(errorData).catch(() => { });
        }
    });

    // Capture Unhandled Promise Rejections
    window.addEventListener('unhandledrejection', (event) => {
        const errorData = {
            message: event.reason ? String(event.reason) : 'Unhandled Promise Rejection',
            source: 'Promise',
            stack: event.reason && event.reason.stack ? event.reason.stack : ''
        };
        if (typeof window.pytron_report_error === 'function') {
            window.pytron_report_error(errorData).catch(() => { });
        }
    });

    // Global Drag & Drop Handler (Prevent browser navigation & dispatch to backend)
    // This allows the client library to manage file drops without backend injection
    window.addEventListener('dragover', (e) => e.preventDefault(), true);
    window.addEventListener('drop', (e) => {
        e.preventDefault();

        // Use pytronApi.log to print to Python Terminal for debugging visibility
        pytronApi.log("[Pytron Client] Drop Event Detected");

        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            pytronApi.log(`[Pytron Client] Found ${e.dataTransfer.files.length} files.`);
            const files = [];
            for (let i = 0; i < e.dataTransfer.files.length; i++) {
                const f = e.dataTransfer.files[i];
                // pytronApi.log(`[Pytron Client] File[${i}]: name=${f.name}, path=${f.path}, fullPath=${f.fullPath}`);

                // WebView2 / Electron usually exposes 'fullPath' or 'path' on File objects
                // We check both for maximum compatibility
                const path = f.path || f.fullPath;
                if (path) {
                    files.push(path);
                }
            }

            // Send to backend if paths are available
            // We use the direct binding 'pytron_native_drop' if available
            if (files.length > 0) {
                if (typeof window.pytron_native_drop === 'function') {
                    pytronApi.log("[Pytron Client] Dispatching to backend via pytron_native_drop");
                    window.pytron_native_drop(files);
                } else {
                    pytronApi.log("[Pytron Client] WARNING: window.pytron_native_drop is not defined!");
                }
            } else {
                pytronApi.log("[Pytron Client] WARNING: No paths could be extracted from dropped files. Browser Security may be blocking path access.");
            }
        }
    }, true);
}

// 7. ATTACH TO WINDOW
if (typeof window !== 'undefined') {
    window.pytron = pytron;
    // Backwards compatibility for templates using pytronApi
    window.pytronApi = pytronApi;
}

export default pytron;

