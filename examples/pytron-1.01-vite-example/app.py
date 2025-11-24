from pytron import App
import ollama 

def main():
    app = App()
    
    # Global function available to all windows
    @app.expose
    def get_version():
        return "1.0.0"
        
    # Initialize some state
    app.state.counter = 0

    window = app.create_window()
    
    # Window specific function
    @window.expose
    def greet(name):
        # Update state automatically!
        app.state.counter += 1
        return f"Hello, {name}! From Python. (Calls: {app.state.counter})"
        
    app.run(debug=True)

if __name__ == '__main__':
    main()
