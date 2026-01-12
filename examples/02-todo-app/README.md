# Example 02: Todo App (Reactive State)

This example demonstrates Pytron's reactive state system. Data changed in Python is automatically synchronized with the frontend.

## Key Features

- **Reactive State**: Using `app.state` to store and sync data.
- **State Listeners**: The frontend uses `pytron.on('pytron:state-update', ...)` to react to changes.
- **Pydantic Integration**: Using Pydantic models in Python for data validation before syncing.

## How it works

1.  In `app.py`, we initialize `app.state.todos`.
2.  Whenever a function like `add_todo` modifies `app.state.todos`, Pytron detects the assignment and pushes the new value to the frontend.
3.  The frontend receives the update and re-renders the list.

## Reactive Tips

To trigger a state update for lists or dictionaries, always assign a new copy or the modified object back to the state variable:
```python
# This triggers an update
app.state.my_list = app.state.my_list + [new_item]

# This might NOT trigger an update (depending on implementation details)
app.state.my_list.append(new_item) 
```
In this example, we always use the assignment pattern to ensure the frontend is notified.
