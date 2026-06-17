"""Picture + SVG torture: generate raster assets with Pillow, exercise every
picture effect (transparency / brightness / contrast / recolor presets /
duotone), and embed an SVG with an explicit PNG fallback (cairosvg-free).
"""

from __future__ import annotations

from pathlib import Path

from _util import blank, deck, save

from power_pptx.dml.color import RGBColor
from power_pptx.util import Inches

ASSETS = Path(__file__).parent / "_assets"


def _make_assets():
    from PIL import Image, ImageDraw

    ASSETS.mkdir(exist_ok=True)
    # A colourful gradient-ish JPEG
    jpg = ASSETS / "hero.jpg"
    img = Image.new("RGB", (800, 500))
    px = img.load()
    for y in range(500):
        for x in range(0, 800, 4):
            c = (x % 256, y % 256, (x + y) % 256)
            for dx in range(4):
                if x + dx < 800:
                    px[x + dx, y] = c
    img.save(jpg, "JPEG", quality=85)

    # A PNG with transparency
    png = ASSETS / "logo.png"
    p = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(p)
    d.ellipse([20, 20, 280, 280], fill=(79, 157, 255, 255))
    d.rectangle([110, 110, 190, 190], fill=(255, 255, 255, 255))
    p.save(png, "PNG")

    # A simple SVG + its PNG fallback
    svg = ASSETS / "mark.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
        '<rect width="200" height="200" fill="#0F2D6B"/>'
        '<circle cx="100" cy="100" r="70" fill="#4F9DFF"/>'
        "</svg>"
    )
    fallback = ASSETS / "mark.png"
    f = Image.new("RGB", (200, 200), (15, 45, 107))
    df = ImageDraw.Draw(f)
    df.ellipse([30, 30, 170, 170], fill=(79, 157, 255))
    f.save(fallback, "PNG")
    return jpg, png, svg, fallback


def build():
    jpg, png, svg, fallback = _make_assets()
    prs = deck()

    # --- Slide 1: continuous adjustments ---------------------------------
    s = blank(prs)
    pic = s.shapes.add_picture(str(jpg), Inches(0.5), Inches(0.5),
                               Inches(6), Inches(3.75))
    pic.effects.transparency = 0.3
    pic.effects.brightness = 0.10
    pic.effects.contrast = 0.05
    pic2 = s.shapes.add_picture(str(jpg), Inches(7), Inches(0.5),
                                Inches(6), Inches(3.75))
    pic2.effects.brightness = -0.2
    pic2.effects.contrast = 0.3

    # --- Slide 2: recolor presets ----------------------------------------
    s = blank(prs)
    for i, preset in enumerate(["grayscale", "sepia", "washout"]):
        pic = s.shapes.add_picture(str(jpg),
                                   Inches(0.4 + i * 4.3), Inches(2),
                                   Inches(4), Inches(2.5))
        pic.effects.recolor = preset
        tb = s.shapes.add_textbox(Inches(0.4 + i * 4.3), Inches(4.6),
                                  Inches(4), Inches(0.4))
        tb.text_frame.text = preset

    # --- Slide 3: duotone (RGBColor + hex + tuple forms) -----------------
    s = blank(prs)
    a = s.shapes.add_picture(str(jpg), Inches(0.5), Inches(1.5),
                             Inches(6), Inches(3.75))
    a.effects.set_duotone(RGBColor(0x12, 0x1E, 0x4D), "#A8C0FF")
    b = s.shapes.add_picture(str(jpg), Inches(7), Inches(1.5),
                             Inches(6), Inches(3.75))
    b.effects.set_duotone((77, 0, 30), (255, 220, 180))
    # clear on a third copy by re-setting then None
    b.effects.recolor = None

    # --- Slide 4: transparent PNG + SVG with PNG fallback ----------------
    s = blank(prs)
    s.shapes.add_picture(str(png), Inches(1), Inches(1), Inches(3), Inches(3))
    s.shapes.add_svg_picture(str(svg), Inches(5), Inches(1),
                             width=Inches(3), height=Inches(3),
                             png_fallback=str(fallback))

    return prs


if __name__ == "__main__":
    save(build(), "10_picture_svg_torture.pptx")
