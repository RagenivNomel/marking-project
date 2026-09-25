"""Offline-only conversion of approved mascot art into fixed-cell runtime PNGs.

This never runs in the teacher application. Sprite Maker's documented pack,
anchor, transparent-output, and fixed-cell normalization rules guide the build.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter


HERE = Path(__file__).resolve().parent
PHASE_A = HERE.parent / "phase-a"
OUT = HERE.parents[2] / "desktop" / "assets" / "mascot"
OUT.mkdir(parents=True, exist_ok=True)

FRAME = 64
def remove_background(image: Image.Image, respect_alpha: bool) -> Image.Image:
    """Select warm art and attached outlines, excluding source sheet borders."""
    image = image.convert("RGBA")
    pixels = image.load()
    warm = Image.new("L", image.size)
    warm_pixels = warm.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, _ = pixels[x, y]
            if r > b + 14 and r > g - 9:
                warm_pixels[x, y] = 255
    near_warm = warm.filter(ImageFilter.MaxFilter(21))
    near_pixels = near_warm.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, alpha = pixels[x, y]
            foreground = warm_pixels[x, y] or (near_pixels[x, y] and max(r, g, b) < 105)
            if respect_alpha and alpha <= 80:
                foreground = False
            pixels[x, y] = (r, g, b, 255 if foreground else 0)
    return image


def keep_largest_component(image: Image.Image) -> Image.Image:
    """Drop disconnected guide lines around the generated celebration poses."""
    width, height = image.size
    alpha = image.getchannel("A")
    data = alpha.tobytes()
    seen = bytearray(width * height)
    largest: list[int] = []
    for start, value in enumerate(data):
        if not value or seen[start]:
            continue
        queue = deque([start])
        seen[start] = 1
        component = []
        while queue:
            index = queue.popleft()
            component.append(index)
            x, y = index % width, index // width
            for ny in range(max(0, y - 1), min(height, y + 2)):
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = ny * width + nx
                    if data[neighbor] and not seen[neighbor]:
                        seen[neighbor] = 1
                        queue.append(neighbor)
        if len(component) > len(largest):
            largest = component
    kept = bytearray(width * height)
    for index in largest:
        kept[index] = 255
    image.putalpha(Image.frombytes("L", image.size, bytes(kept)))
    return image


def cleaned_cell(source: Image.Image, index: int, count: int, blue: bool,
                 name: str) -> Image.Image:
    cell_width = source.width // count
    top = 150 if name == "happy" else 70
    bottom = source.height - (150 if name == "happy" else 75)
    cell = source.crop((index * cell_width + 18, top,
                        (index + 1) * cell_width - 18, bottom))
    cell = remove_background(cell, respect_alpha=not blue)
    return keep_largest_component(cell) if name == "happy" else cell


def make_sheet(name: str, count: int, fps: float, blue: bool = False) -> dict:
    source = Image.open(HERE / "source" / f"{name}-strip.png").convert("RGBA")
    assert source.width % count == 0, (name, source.size)
    cells = [cleaned_cell(source, i, count, blue, name) for i in range(count)]
    boxes = [cell.getchannel("A").getbbox() for cell in cells]
    assert all(boxes), name
    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[2] for box in boxes)
    bottom = max(box[3] for box in boxes)
    box = (left, top, right, bottom)
    scale = min((FRAME - 4) / (right - left), (FRAME - 4) / (bottom - top))
    target = (max(1, round((right - left) * scale)),
              max(1, round((bottom - top) * scale)))
    sheet = Image.new("RGBA", (FRAME * count, FRAME))
    for index, cell in enumerate(cells):
        sprite = cell.crop(box).resize(target, Image.Resampling.NEAREST)
        x = index * FRAME + (FRAME - target[0]) // 2
        y = FRAME - target[1] - 2
        sheet.alpha_composite(sprite, (x, y))
    path = OUT / f"cat-{name}.png"
    sheet.save(path, optimize=True)
    return {"file": path.name, "frames": count, "frameWidth": FRAME,
            "frameHeight": FRAME, "fps": fps, "baselineY": FRAME - 2}


def make_prop(source_name: str, output_name: str, canvas: tuple[int, int]) -> None:
    source = Image.open(PHASE_A / "assets" / "props" / source_name).convert("RGBA")
    box = source.getchannel("A").getbbox()
    assert box is not None
    cropped = source.crop(box)
    scale = min((canvas[0] - 4) / cropped.width,
                (canvas[1] - 4) / cropped.height)
    size = (max(1, round(cropped.width * scale)),
            max(1, round(cropped.height * scale)))
    art = cropped.resize(size, Image.Resampling.NEAREST)
    result = Image.new("RGBA", canvas)
    result.alpha_composite(art, ((canvas[0] - size[0]) // 2,
                                 canvas[1] - size[1] - 2))
    result.save(OUT / output_name, optimize=True)


def main() -> None:
    animations = {
        "walk": make_sheet("walk", 4, 4, blue=True),
        "sleep": make_sheet("sleep", 3, 1.1),
        "read": make_sheet("read", 4, 1.5),
        "mark": make_sheet("mark", 4, 3),
        "play": make_sheet("play", 3, 2.5),
        "happy": make_sheet("happy", 4, 5),
    }
    make_prop("cat-house.png", "cat-house.png", (76, 76))
    make_prop("composition-paper.png", "composition-paper.png", (36, 44))
    make_prop("red-pen.png", "red-pen.png", (28, 28))
    make_prop("paper-stack.png", "paper-stack.png", (42, 36))
    (OUT / "sprites.json").write_text(
        json.dumps({"format": "fixed-cell-png", "animations": animations}, indent=2),
        encoding="utf-8",
    )
    for name, meta in animations.items():
        print(name, meta["frames"], meta["file"])


if __name__ == "__main__":
    main()
