/**
 * Pytron Client Library
 * Provides a seamless bridge to the Python backend.
 */

// Interface for dynamic backend methods.
// Users can augment this interface to add their own methods for IntelliSense.
export interface PytronAPI {
    [methodName: string]: any;
}

export interface PytronClient extends PytronAPI {
    /**
     * Local state cache synchronized with the backend.
     */
    state: Record<string, any>;

    /**
     * Listen for an event sent from the Python backend.
     * @param event - The event name.
     * @param callback - The function to call when event triggers.
     */
    on(event: string, callback: (data: any) => void): void;

    /**
     * Remove an event listener.
     * @param event - The event name.
     * @param callback - The function to remove.
     */
    off(event: string, callback: (data: any) => void): void;

    /**
     * Wait for the backend to be connected.
     * @param timeout - Timeout in milliseconds. Default is 5000.
     */
    waitForBackend(timeout?: number): Promise<void>;

    /**
     * Log a message to the Python console (if supported).
     * @param message - The message to log.
     */
    log(message: string): Promise<void>;

    /**
     * Resolve a pytron:// asset to a Data URI.
     * @param key - The asset key.
     */
    asset(key: string): Promise<string | null>;
}

declare const pytron: PytronClient;

export default pytron;
