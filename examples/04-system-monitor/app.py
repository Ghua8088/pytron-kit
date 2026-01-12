import time
import threading
import random
from pytron import App

app = App()

# Initial state for system stats
app.state.cpu_usage = 0
app.state.memory_usage = 0
app.state.is_monitoring = True

def monitor_loop():
    """Simulates a background thread monitoring system resources."""
    while True:
        if app.state.is_monitoring:
            # In a real app, you'd use psutil: 
            # app.state.cpu_usage = psutil.cpu_percent()
            app.state.cpu_usage = random.randint(2, 45)
            app.state.memory_usage = random.randint(20, 80)
        
        time.sleep(1)

@app.expose
def toggle_monitoring():
    app.state.is_monitoring = not app.state.is_monitoring
    return app.state.is_monitoring

if __name__ == "__main__":
    # Start the monitoring thread as a daemon so it exits with the app
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()
    
    app.run()
