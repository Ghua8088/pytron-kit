from pytron import App
from pydantic import BaseModel
from typing import List
import uuid

app = App()

class TodoItem(BaseModel):
    id: str
    text: str
    completed: bool = False

# Initialize state with some defaults
app.state.todos = [
    {"id": str(uuid.uuid4()), "text": "Learn Pytron", "completed": True},
    {"id": str(uuid.uuid4()), "text": "Build an amazing app", "completed": False}
]

@app.expose
def add_todo(text: str):
    if not text.strip():
        return
    new_todo = TodoItem(id=str(uuid.uuid4()), text=text)
    # We update the state by assigning a new list to trigger the reactive update
    app.state.todos = app.state.todos + [new_todo.dict()]

@app.expose
def toggle_todo(todo_id: str):
    newList = []
    for todo in app.state.todos:
        if todo['id'] == todo_id:
            todo['completed'] = not todo['completed']
        newList.append(todo)
    app.state.todos = newList

@app.expose
def delete_todo(todo_id: str):
    app.state.todos = [t for t in app.state.todos if t['id'] != todo_id]

if __name__ == "__main__":
    app.run()
