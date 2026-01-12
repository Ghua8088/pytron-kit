# Pytron Examples

This directory contains a collection of examples demonstrating various features and capabilities of the Pytron framework.

## Example Index

| # | Example | Description | Core Features |
|---|---------|-------------|---------------|
| 01 | [Hello World](./01-hello-world) | Absolute basics of Pytron | App initialization, basic JS call |
| 02 | [Todo App](./02-todo-app) | State synchronization demo | Reactive state, Pydantic models |
| 03 | [File Browser](./03-file-browser) | Native OS file system access | File dialogs, system shell, OS interactions |
| 04 | [System Monitor](./04-system-monitor) | Real-time system data streaming | Threading, background updates, progress bars |
| 05 | [Database CRUD](./05-database-crud) | SQLite database integration | Persistent storage, async operations |
| 06 | [Image Processing](./06-image-processing) | High-performance binary data (VAP) | Virtual Asset Provider, PIL/OpenCV integration |
| 07 | [Global Shortcuts](./07-global-shortcuts) | System-wide integration | Global keyboard hooks, tray icons, notifications |

---

## How to run the examples

To run any of these examples, navigate to the example directory and use the `pytron run` command:

```bash
cd 01-hello-world
pytron run
```

*Note: Pytron looks for `app.py` by default. If you renamed it back to `main.py`, you would need `pytron run main.py`.*
