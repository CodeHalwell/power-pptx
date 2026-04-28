# Basics — the inherited 1.0.2 surface

Everything in this file works the same as upstream `python-pptx 1.0.2`.
It's here so you don't have to leave the skill for boring boilerplate.

## Open / create / save

```python
from pptx import Presentation

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
from pptx.util import Inches

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
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

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
from pptx.enum.shapes import MSO_SHAPE

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
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE

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
from pptx.util import Inches, Pt, Cm, Emu, Mm

Inches(1)   # 914400 EMU
Pt(12)      # 152400 EMU
Cm(2.54)    # ≈ Inches(1)
```

Use these everywhere — never write the EMU integers directly.
