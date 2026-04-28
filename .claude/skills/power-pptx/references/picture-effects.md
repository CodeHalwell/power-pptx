# Picture effects + native SVG (Phase 6)

Pictures gain a dedicated `effects` accessor that wraps the OOXML
`<a:blip>` filters, plus native SVG support with PNG fallback.

## Picture filters

```python
from pptx import Presentation
from pptx.util import Inches
from pptx.dml.color import RGBColor

prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

pic = slide.shapes.add_picture(
    "hero.jpg", Inches(0), Inches(0),
    width=prs.slide_width, height=prs.slide_height,
)

# Continuous adjustments — all in [-1.0, 1.0] (or [0.0, 1.0] for transparency)
pic.effects.transparency = 0.3        # 30% see-through
pic.effects.brightness   = 0.10
pic.effects.contrast     = 0.05
```

## Recolor presets

```python
pic.effects.recolor("grayscale")
pic.effects.recolor("sepia")
pic.effects.recolor("washout")        # PowerPoint's "Washout"
pic.effects.recolor("black_and_white")
```

## Duotone

```python
pic.effects.set_duotone(
    RGBColor(0x12, 0x1E, 0x4D),       # shadow color
    "#A8C0FF",                         # highlight color (hex with or without '#')
)

# Plain RGB tuples are also accepted
pic.effects.set_duotone((18, 30, 77), (168, 192, 255))
```

To clear:

```python
pic.effects.clear_recolor()           # drops any duotone / grayscale / etc.
```

## Native SVG with PNG fallback

`add_svg_picture` embeds both an SVG and a PNG fallback inside the
same `<a:blip>` so PowerPoint and earlier viewers each render the
right one.

```python
# Auto-rasterise via the optional `cairosvg` dependency
slide.shapes.add_svg_picture("logo.svg", Inches(0.5), Inches(0.5))

# Bring your own fallback PNG
slide.shapes.add_svg_picture(
    "logo.svg",
    Inches(0.5), Inches(0.5),
    width=Inches(1.5), height=Inches(1.5),
    png_fallback="logo.png",
)
```

If `cairosvg` isn't installed and you don't pass `png_fallback`, the
call raises `pptx._svg.CairoSvgUnavailable` with a clear install hint.

The `image/svg+xml` content type is registered with the package so
SVG parts authored elsewhere round-trip through PowerPoint untouched.

## End-to-end: tinted photo with overlay text

```python
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[6])

# Full-bleed hero image, duotoned to brand colors
pic = slide.shapes.add_picture(
    "hero.jpg", 0, 0,
    width=prs.slide_width, height=prs.slide_height,
)
pic.effects.set_duotone(RGBColor(0x12, 0x1E, 0x4D), "#A8C0FF")

# Bottom band with overlay text
band = slide.shapes.add_shape(
    MSO_SHAPE.RECTANGLE,
    0, prs.slide_height - Inches(1.5),
    prs.slide_width, Inches(1.5),
)
band.fill.solid()
band.fill.fore_color.rgb   = RGBColor(0x12, 0x1E, 0x4D)
band.fill.fore_color.alpha = 0.55
band.line.fill.background()

box = slide.shapes.add_textbox(
    Inches(0.6), prs.slide_height - Inches(1.2),
    prs.slide_width - Inches(1.2), Inches(0.9),
)
p = box.text_frame.paragraphs[0]
p.text = "Q4 2026"
p.font.size = Pt(40)
p.font.bold = True
p.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

prs.save("hero.pptx")
```
