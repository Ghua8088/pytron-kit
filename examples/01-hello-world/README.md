# Example 01: Hello World

This is the most basic Pytron application. It demonstrates:

1.  Initializing a Pytron `App`.
2.  Exposing a Python function to the frontend using `@app.expose`.
3.  Calling that Python function from JavaScript using the `pytron-client`.
4.  Basic `settings.json` configuration.

## Key Files

- `app.py`: Backend logic and API exposure.
- `settings.json`: Application metadata and window configuration.
- `frontend/index.html`: The UI layer calling the Python backend.

## How it works

In `app.py`, we define a function `greet` and mark it with `@app.expose`. This makes it available in the frontend via the `window` object.

In `frontend/index.html`, we simply call `await window.greet(name)`.
