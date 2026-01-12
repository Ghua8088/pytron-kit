# Example 06: Image Processing (VAP)

This example demonstrates the **Virtual Asset Provider (VAP)**, Pytron's high-performance bridge for binary data.

## Key Features

- **Binary IPC**: Transferring large binary blobs (like images) without the 33% overhead of Base64 encoding.
- **Pillow Integration**: Returning `PIL.Image` objects directly from Python functions.
- **Custom Protocol**: Using the `pytron://` scheme to reference in-memory assets in the frontend.

## How it works

1.  In `main.py`, the `generate_noise` function creates a `PIL.Image`.
2.  When this function is called from the frontend, Pytron's serializer:
    - Saves the image to an in-memory buffer.
    - Generates a unique ID (e.g., `gen_img_abcd1234`).
    - Stores the buffer in the window's VAP provider.
    - Returns `pytron://gen_img_abcd1234` as a string to JS.
3.  The frontend sets this URL as the `src` of an `<img>` tag.
4.  The browser attempts to fetch the URL, which is intercepted by Pytron's injected bridge to serve the raw binary data.

## Why use VAP?

Traditional bridges (Json/Base64) are slow for binary data because strings are immutable and encoding adds significant CPU/memory overhead. VAP allows Pytron to handle live camera streams, real-time AI visualizations, and large datasets at native-like speeds.
