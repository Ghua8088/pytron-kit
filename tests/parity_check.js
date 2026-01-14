// parity_check.js
// Run this inside the DevTools console or via a test runner hook

const assert = (condition, msg) => {
    if (!condition) throw new Error(`❌ FAILED: ${msg}`);
    console.log(`✅ PASS: ${msg}`);
};

async function runParityTests() {
    console.group("🛡️ PYTRON PARITY PROTOCOL");

    try {
        // 1. Core Bridge
        // Assuming echo is custom, defaulting to simple check
        if (pytron.echo) {
            const echo = await pytron.echo("ping");
            assert(echo === "ping", "Bridge Roundtrip");
        }

        // 2. Window Control
        // Wait for system to stabilize
        await new Promise(r => setTimeout(r, 100));

        // Note: isMaximized might depend on specific backend implementation support
        if (pytron.window && pytron.window.isMaximized) {
            const startState = await pytron.window.isMaximized();
            console.log("Initial Max State:", startState);

            await pytron.window.toggleMaximize();
            // Wait for animation/IPC lag
            await new Promise(r => setTimeout(r, 1000));

            const endState = await pytron.window.isMaximized();
            console.log("End Max State:", endState);

            assert(startState !== endState, "Window Maximize Toggle");

            // Restore
            await pytron.window.toggleMaximize();
        }

        // 3. File System (The dangerous one)
        if (pytron.fs) {
            const testPath = "parity_test.tmp";
            await pytron.fs.write(testPath, "S0LID_AF");
            const content = await pytron.fs.read(testPath);
            assert(content === "S0LID_AF", "File I/O Consistency");
            await pytron.fs.delete(testPath);
        }

        console.log("🎉 ALL SYSTEMS NORMAL. ENGINE IS SOLID.");
    } catch (e) {
        console.error("🚨 BREACH DETECTED:", e);
        if (pytron.app && pytron.app.quit) {
            pytron.app.quit(1); // Exit with error code
        }
    }
    console.groupEnd();
}

// Auto-run if loaded via script injection usually?
// Or let user call it.
// runParityTests();
