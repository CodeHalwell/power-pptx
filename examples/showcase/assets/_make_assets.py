"""Generate the synthetic hero image used by the showcase decks.

Run once: ``python examples/showcase/assets/_make_assets.py``
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).parent


def _radial_gradient(size: tuple[int, int], inner: tuple[int, int, int],
                     outer: tuple[int, int, int]) -> Image.Image:
    w, h = size
    cx, cy = w / 2, h / 2
    max_r = (cx ** 2 + cy ** 2) ** 0.5
    img = Image.new("RGB", size, outer)
    px = img.load()
    for y in range(h):
        for x in range(w):
            r = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / max_r
            r = min(max(r, 0.0), 1.0)
            px[x, y] = tuple(
                int(inner[i] * (1 - r) + outer[i] * r) for i in range(3)
            )
    return img


def make_hero(path: Path) -> None:
    size = (1600, 900)
    base = _radial_gradient(size, inner=(99, 102, 241), outer=(15, 23, 42))

    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for cx, cy, r, alpha in [
        (300, 700, 320, 70),
        (1300, 200, 260, 60),
        (900, 500, 380, 40),
    ]:
        draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                     fill=(255, 255, 255, alpha))
    overlay = overlay.filter(ImageFilter.GaussianBlur(80))
    base = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    base.save(path, "JPEG", quality=88)
    print(f"wrote {path}  ({size[0]}x{size[1]})")


if __name__ == "__main__":
    make_hero(HERE / "hero.jpg")
