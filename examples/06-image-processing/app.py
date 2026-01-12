from pytron import App
from PIL import Image, ImageDraw, ImageFilter
import random
import io

app = App()


@app.expose
def generate_noise(width: int = 400, height: int = 300):
    """Generates a random noise image and returns it as a PIL object."""
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    for x in range(width):
        for y in range(height):
            pixels[x, y] = (
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255),
            )

    # Pytron automatically detects PIL images and serves them via pytron:// protocol
    # significantly reducing IPC overhead compared to Base64.
    return img


@app.expose
def create_abstract_art():
    """Creates a simple abstract image using ImageDraw."""
    img = Image.new("RGB", (500, 500), color=(20, 20, 20))
    draw = ImageDraw.Draw(img)

    for _ in range(20):
        x1, y1 = random.randint(0, 500), random.randint(0, 500)
        x2, y2 = random.randint(0, 500), random.randint(0, 500)
        # PIL requires [x0, y0, x1, y1] where x0 <= x1 and y0 <= y1
        box = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
        color = (
            random.randint(100, 255),
            random.randint(100, 255),
            random.randint(100, 255),
        )
        draw.ellipse(box, outline=color, width=random.randint(1, 5))

    return img.filter(ImageFilter.GaussianBlur(radius=2))


if __name__ == "__main__":
    app.run()
