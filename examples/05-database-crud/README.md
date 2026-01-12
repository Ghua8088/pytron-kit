# Example 05: Database CRUD (SQLite)

This example demonstrates how to integrate a persistent SQLite database with Pytron.

## Key Features

- **Local Storage**: Using Python's built-in `sqlite3` module to store data permanently.
- **Async API**: Calling Python functions that perform DB operations and updating the UI upon completion.
- **CRUD Operations**: Create, Read, and Delete (Update is left as an exercise for the reader!).

## How it works

1.  On startup, `main.py` initializes the database and creates the `notes` table if it doesn't exist.
2.  The frontend calls `pytron.get_notes()` on load to fetch all existing records.
3.  When a user saves a note, the frontend waits for the Python `add_note` function to finish before refreshing the list.

## Database Location

In this example, `tasks.db` is created in the current working directory. 

*Note: For packaged apps, Pytron automatically shifts the working directory to a user-writable path (like %APPDATA%), so your database will still work correctly without manual path handling.*
