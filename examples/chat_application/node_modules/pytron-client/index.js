/**
 * Pytron Client Library
 * Provides a seamless bridge to the Python backend.
 */

// Event storage
const listeners = {};

// Local state cache
const state = {};

// The main Pytron Proxy
const pytron = new Proxy({
    state: state, // Expose state object directly

    /**
     * Listen for an event sent from the Python backend.
     * @param {string} event - The event name.
     * @param {function} callback - The function to call when event triggers.
     */
    on: (event, callback) => {
        if (!listeners[event]) listeners[event] = [];
        listeners[event].push(callback);
    },

    /**
     * Remove an event listener.
     * @param {string} event - The event name.
     * @param {function} callback - The function to remove.
     */
    off: (event, callback) => {
        if (!listeners[event]) return;
        listeners[event] = listeners[event].filter(cb => cb !== callback);
    }
}, {
    get: (target, prop) => {
        // Return local methods/properties if they exist
        if (prop in target) return target[prop];

        // Otherwise, proxy to the backend
        return async (...args) => {
            if (typeof window === 'undefined' || !window.pywebview || !window.pywebview.api) {
                console.warn(`[Pytron] Backend not connected. Call to '${String(prop)}' failed.`);
                throw new Error("Pytron backend not connected");
            }

            if (typeof window.pywebview.api[prop] !== 'function') {
                throw new Error(`Method '${String(prop)}' not found on Pytron backend.`);
            }

            try {
                return await window.pywebview.api[prop](...args);
            } catch (error) {
                console.error(`[Pytron] Error calling '${String(prop)}':`, error);
                throw error;
            }
        };
    }
});

// Internal dispatcher called by Python
window.__pytron_dispatch = (event, data) => {
    // Handle internal state updates automatically
    if (event === 'pytron:state-update') {
        state[data.key] = data.value;
        // We also re-emit it as a generic event so users can subscribe to specific keys if they want
        // e.g. pytron.on('state:username', ...)
        if (listeners[`state:${data.key}`]) {
            listeners[`state:${data.key}`].forEach(cb => cb(data.value));
        }
    }

    if (listeners[event]) {
        listeners[event].forEach(cb => cb(data));
    }
};

export default pytron;
