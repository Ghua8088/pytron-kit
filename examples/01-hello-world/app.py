from pytron import App

app = App()


@app.expose
def greet(name: str) -> str:
    """A simple function exposed to the frontend."""
    return f"Hello, {name}! Welcome to Pytron."


if __name__ == "__main__":
    app.run()
