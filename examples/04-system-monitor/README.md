# Example 04: System Monitor (Real-time Data)

This example demonstrates how to handle asynchronous data updates and background threading in Pytron.

## Key Features

- **Background Threads**: Running a Python `threading.Thread` alongside the main app.
- **Pushing Updates**: Automatically syncing state changes from a background loop to the UI.
- **Reactive UI**: The frontend uses CSS transitions and state listeners to create a smooth, real-time experience.

## How it works

1.  In `main.py`, a background thread starts a loop that updates `app.state.cpu_usage` and `app.state.memory_usage` Every second.
2.  Because `app.state` is reactive, every time the thread assigns a new value, Pytron broadcasts this change to the frontend.
3.  The frontend's `pytron.on('pytron:state-update', ...)` listener catches these changes and updates the progress bars.

## Pro Tip

For real hardware statistics, you can install `psutil` and replace the random number generation with actual system metrics:

```python
import psutil
# ... inside the loop ...
app.state.cpu_usage = psutil.cpu_percent()
```
