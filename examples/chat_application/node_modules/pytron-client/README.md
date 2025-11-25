# Banner: pytron.png
![Pytron](/pytron/pytron.png)
# Pytron Client

A compact client module that provides a clean, actionable API for controlling application windows and calling backend methods from the frontend.

Pytron Client aims to feel like a real application module rather than a low-level transport. It exposes a straightforward set of window-management helpers (minimize, maximize, restore, toggle fullscreen, resize, move, destroy) plus the ability to call arbitrary backend functions as async methods.

## Install

Install from npm:

```bash
npm install pytron-client
```

Or install locally from the repository's package folder during development:

```bash
npm install ../pytron-client/package
```

## Quick Start

Import the default export and call its functions. All calls are async and will reject if the runtime bridge to the native backend is not available.

```js
import pytron from 'pytron-client';

// Window management
await pytron.minimize();
await pytron.maximize();
await pytron.restore();
await pytron.toggle_fullscreen();
await pytron.resize(1024, 768);
await pytron.move(100, 50);
await pytron.destroy();

// Call an arbitrary backend function (the backend should expose this function)
const result = await pytron.calculateSomething(42);
console.log(result);
```

Notes:

- Methods are forwarded to the backend bridge as async calls — treat them like remote procedure calls.
- Method names are lower_snake_case to match common backend naming (e.g. `toggle_fullscreen`).

## API Reference

Window management helpers

- `minimize()` — Minimize the current window.
- `maximize()` — Maximize the current window.
- `restore()` — Restore the window from minimized/maximized state.
- `toggle_fullscreen()` — Toggle fullscreen mode.
- `resize(width, height)` — Resize the window to `width` × `height`.
- `move(x, y)` — Move the window to the coordinate (`x`, `y`).
- `destroy()` — Close/destroy the window.

General backend RPC

- Any other property accessed on the `pytron` object will behave as an async function that calls the backend with the same name and arguments. For example, `pytron.ping()` will attempt to call a `ping` function on the backend and return its result.

Behavior and errors

- Calls return a Promise and throw/reject if the backend bridge is not available or the backend reports an error.
- Errors include helpful messages when a method is missing or the runtime bridge is not connected.

## Example (local dev)

The repository includes a small example app under `pytron-package/examples/pytron-1.01-vite-example/frontend`. From that folder, run:

```powershell
npm install
npm run dev
```

Then import `pytron` in your frontend code and use the window API as shown above.

## Implementation notes

- The package is shipped as a single ESM entrypoint at `package/index.js` for easy bundling with modern toolchains (Vite, Rollup, Webpack).
- At runtime `pytron` forwards calls to the native/backend bridge provided by the host; this is intentionally abstracted so consumers can think in terms of a module API rather than transport details.

## Development

- Entrypoint: `package/index.js`.
- To run the example app, use the Vite frontend example above.

Contributing

- Open issues or PRs at `https://github.com/Ghua8088/pytron-client`.

## Troubleshooting

- "Backend not connected" — ensure your host application exposes the backend bridge before calling the API.
- "Method not found" — confirm the backend exposes the method name you’re calling.

## License

This project is licensed under the ISC License — see `package/package.json` for details.

## Maintainers

- `Ghua8088`

---

Would you like me to also:
- Add a tiny standalone HTML example that demonstrates the window API, or
- Update the example project's `README.md` with specific steps showing `pytron` calls?


