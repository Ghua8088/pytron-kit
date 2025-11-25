# Banner: pytron.png
![Pytron](/pytron/pytron.png)
# My Pytron App

Built with Pytron CLI init template.

## Structure
- `app.py`: Main Python entrypoint
- `settings.json`: Application configuration
- `frontend/`: Vite React Frontend

## Chat example (Ollama)

This example demonstrates a simple chat UI that sends messages to a local Ollama model.

Requirements:
- Ollama installed and running (or the Ollama Python SDK installed).
- The desired model available locally (the default model name is `ollama`, configurable in `settings.json` via `ollama_model`).

Run in development (hot-reload for the Python app, frontend dev server separately):

```powershell
# from the example folder
cd frontend
npm install
npm run dev

# in a separate terminal (from example folder)
pytron run --dev app.py
```

Build & run packaged (static frontend):

```powershell
cd frontend
npm install
npm run build

# then in example root
pytron run app.py
```

Notes:
- The frontend calls the exposed backend method `send_message` (available at `window.pywebview.api.send_message`) which delegates to Ollama.
- If the Ollama Python SDK is available the backend will prefer it; otherwise it will invoke the `ollama` CLI.