# Basics — the inherited 1.0.2 surface

Everything in this file works the same as upstream `python-pptx 1.0.2`.
It's here so you don't have to leave the skill for boring boilerplate.

## Open / create / save

```python
from power_pptx import Presentation

prs = Presentation()                     # blank deck, default 16:9
prs = Presentation("template.pptx")      # open existing
prs.save("out.pptx")
```

`Presentation(...)` also accepts a binary file-like object — useful for
HTTP responses or in-memory generation:

```python
import io
buf = io.BytesIO()
prs.save(buf)
buf.seek(0)
return buf.getvalue()
```

## Slide size

```python
from power_pptx.util import Inches

prs.slide_width  = Inches(13.333)        # 16:9 widescreen
prs.slide_height = Inches(7.5)
```

## Adding slides

```python
title_layout = prs.slide_layouts[0]      # 0 = Title, 1 = Title+Content,
blank_layout = prs.slide_layouts[6]      # 5 = Title only, 6 = Blank, ...

slide = prs.slides.add_slide(title_layout)
slide.shapes.title.text = "Q4 Review"
slide.placeholders[1].text = "April 2026"
```

Layouts are master-dependent; use `prs.slide_master.slide_layouts` if you
want to be explicit, or iterate `for L in prs.slide_layouts: print(L.name)`
to discover what the template ships.

## Text boxes

```python
from power_pptx.util import Inches, Pt
from power_pptx.dml.color import RGBColor

box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(1))
tf = box.text_frame
tf.word_wrap = True

p = tf.paragraphs[0]
p.text = "Hello world"
p.font.name = "Inter"
p.font.size = Pt(36)
p.font.bold = True
p.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)

p2 = tf.add_paragraph()
p2.text = "Subtitle goes here"
p2.font.size = Pt(18)
```

## Auto shapes

```python
from power_pptx.enum.shapes import MSO_SHAPE

card = slide.shapes.add_shape(
    MSO_SHAPE.ROUNDED_RECTANGLE,
    left=Inches(1), top=Inches(2),
    width=Inches(4), height=Inches(2.5),
)
card.fill.solid()
card.fill.fore_color.rgb = RGBColor(0xF8, 0xFA, 0xFC)
card.line.color.rgb = RGBColor(0xE5, 0xE7, 0xEB)
card.line.width = Pt(1)
```

### Per-color alpha (transparency)

Both fill and line colours expose `alpha` in the `[0.0, 1.0]` range —
useful for glow shapes, depth effects, and translucent overlays.
Assign after a colour is set:

```python
glow = slide.shapes.add_shape(MSO_SHAPE.OVAL, ...)
glow.fill.solid()
glow.fill.fore_color.rgb = RGBColor(0x06, 0xD6, 0xFE)
glow.fill.fore_color.alpha = 0.12   # 12% opaque
```

`shape.line.color.alpha` and gradient stop colour alphas
(`stops[0].color.alpha`) work the same way. Assigning `None` removes
the explicit alpha and restores full opacity.

### Two-stop linear gradients

```python
bar.fill.linear_gradient("#06D6FE", "#B14AED", angle=90)   # top→bottom
# Multi-stop:
bar.fill.linear_gradient(
    [("#06D6FE", 0.0), ("#FFFFFF", 0.5), ("#B14AED", 1.0)],
    angle=45,
)
```

`angle` follows the OOXML convention: `0` is left→right, `90` is
top→bottom, `180` is right→left, `270` is bottom→top.

## Pictures

```python
pic = slide.shapes.add_picture(
    "hero.jpg",
    left=Inches(0), top=Inches(0),
    width=prs.slide_width, height=prs.slide_height,
)
```

## Tables

```python
table_shape = slide.shapes.add_table(
    rows=4, cols=3,
    left=Inches(1), top=Inches(2),
    width=Inches(8), height=Inches(3),
)
table = table_shape.table

# Header
for i, label in enumerate(("Metric", "Value", "Δ QoQ")):
    cell = table.cell(0, i)
    cell.text = label
    cell.text_frame.paragraphs[0].font.bold = True

# Body
for row, (k, v, d) in enumerate([("ARR", "$182M", "+27%"),
                                  ("NDR", "131%",  "+3%"),
                                  ("CAC payback", "8 mo", "−1 mo")], start=1):
    table.cell(row, 0).text = k
    table.cell(row, 1).text = v
    table.cell(row, 2).text = d
```

(See `tables.md` for `Cell.borders`, the post-fork addition.)

## Charts

```python
from power_pptx.chart.data import CategoryChartData
from power_pptx.enum.chart import XL_CHART_TYPE

data = CategoryChartData()
data.categories = ["Q1", "Q2", "Q3", "Q4"]
data.add_series("ARR", (100, 130, 155, 182))

chart_shape = slide.shapes.add_chart(
    XL_CHART_TYPE.COLUMN_CLUSTERED,
    Inches(1), Inches(2), Inches(8), Inches(4.5),
    data,
)
chart = chart_shape.chart
chart.has_title = True
chart.chart_title.text_frame.text = "ARR ($M)"
```

(See `charts.md` for chart palettes, quick layouts, and per-series fills.)

## Iterating an existing deck

```python
prs = Presentation("input.pptx")
for slide in prs.slides:
    for shape in slide.shapes:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    print(run.text)
```

## Common units

```python
from power_pptx.util import Inches, Pt, Cm, Emu, Mm

Inches(1)   # 914400 EMU
Pt(12)      # 152400 EMU
Cm(2.54)    # ≈ Inches(1)
```

Use these everywhere — never write the EMU integers directly.
