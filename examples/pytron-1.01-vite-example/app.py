from pytron import App
import ollama 
def main():
    app = App()
    window = app.create_window()
    def greet(name):
        return f"Hello, {name}! From Python."
    window.expose(greet)
    app.run(debug=True)

if __name__ == '__main__':
    main()
