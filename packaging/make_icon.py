"""Make the app icon from the mascot sprite: `pixi run python packaging/make_icon.py`.

Writes desktop/assets/app-icon.png (1024x1024). PyInstaller converts it to
.icns/.ico when packaging, and the window uses it at runtime.
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SPRITE = ROOT / "desktop" / "assets" / "mascot" / "cat-happy.png"
TARGET = ROOT / "desktop" / "assets" / "app-icon.png"

SIZE = 1024
TILE_MARGIN = 100      # macOS icon grid: an 824 px tile inside the 1024 canvas
TILE_RADIUS = 185
OUTLINE = 28
SHADOW = 24
TILE_COLOR = "#87CEEB"  # Theme.sky blue
INK = "#000000"


def solid_sprite(sprite):
    """Fill see-through gaps inside the outline (mouth, chin) with cream fur.

    The app draws the cat on cream, which hides them; the blue tile would not.
    """
    width, height = sprite.size
    mask = Image.new("L", (width + 2, height + 2), 0)
    mask.paste(sprite.getchannel("A").point(lambda a: 255 if a >= 128 else 0), (1, 1))
    ImageDraw.floodfill(mask, (0, 0), 128)  # everything reachable from outside
    solid = sprite.copy()
    pixels, outside = solid.load(), mask.load()
    for y in range(height):
        for x in range(width):
            if outside[x + 1, y + 1] == 128:
                pixels[x, y] = (0, 0, 0, 0)
            elif pixels[x, y][3] < 255:
                r, g, b, a = pixels[x, y]
                pixels[x, y] = (255, 241, 204, 255) if a < 128 else (r, g, b, 255)
    return solid


def main():
    frame = Image.open(SPRITE).convert("RGBA").crop((0, 0, 64, 64))
    cat = solid_sprite(frame.crop(frame.getbbox()))

    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    low, high = TILE_MARGIN, SIZE - TILE_MARGIN - SHADOW
    draw.rounded_rectangle((low + SHADOW, low + SHADOW, high + SHADOW, high + SHADOW), TILE_RADIUS, fill=INK)
    draw.rounded_rectangle((low, low, high, high), TILE_RADIUS, fill=TILE_COLOR, outline=INK, width=OUTLINE)

    # Whole-number nearest-neighbour scaling keeps every sprite pixel square.
    inner = high - low - 2 * OUTLINE
    scale = int(inner * 0.78) // max(cat.size)
    cat = cat.resize((cat.width * scale, cat.height * scale), Image.NEAREST)
    left = low + (high - low - cat.width) // 2
    top = low + (high - low - cat.height) // 2 + scale  # optical centre: sit slightly low
    icon.alpha_composite(cat, (left, top))
    icon.save(TARGET)
    print(f"Wrote {TARGET.relative_to(ROOT)} (sprite scaled x{scale})")


if __name__ == "__main__":
    main()
