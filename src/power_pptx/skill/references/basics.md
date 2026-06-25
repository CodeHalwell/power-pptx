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

### Run-level type styling

`font` exposes the run-property knobs that separate "looks branded" from
"looks generated" — set them on a paragraph's `font` or a specific run's
`font`:

```python
eyebrow.font.all_caps = True          # or .small_caps = True (mutually exclusive)
eyebrow.font.letter_spacing = Pt(2)   # tracking; negative tightens
old.font.strikethrough = True
units.font.superscript = True         # or .subscript (share one baseline)
```

All are tri-state: `None` (the default) inherits from the theme/master,
`True`/`False` write an explicit override. They round-trip and validate
against the OOXML schema.

### Text effects (outline, shadow, glow)

Per-run glyph effects live on `run.font`, mirroring shape
`.line`/`.shadow`/`.glow`:

```python
run.font.outline.color.rgb = "FF0000"   # coloured glyph outline...
run.font.outline.width = Pt(1)          # ...of a given stroke width
run.font.shadow.color.rgb = "808080"; run.font.shadow.blur_radius = Pt(3)
run.font.glow.color.rgb = "00B0F0";   run.font.glow.radius = Pt(6)
```

Reads are non-mutating — nothing is written until you assign, so theme
inheritance is preserved.

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

### Anchored placement

`add_picture`, `add_shape`, and `add_textbox` accept an
``anchor=`` keyword that collapses the
``add → measure → reposition`` idiom for branding elements:

```python
# Logo at bottom-right with a 0.25" margin, height-only sizing:
slide.shapes.add_picture(
    "logo.png",
    anchor="bottom-right",
    margin=Inches(0.25),
    height=Inches(0.32),
)

# Title centred in the top half of a parent card:
slide.shapes.add_textbox(
    Inches(0), Inches(0), Inches(2), Inches(0.5),
    anchor="top-center", margin=Inches(0.25),
    container=card,         # any shape with .width / .height
)
```

`anchor` is one of `top-left`, `top-center`, `top-right`,
`middle-left`, `middle-center` (or bare `center`),
`middle-right`, `bottom-left`, `bottom-center`, `bottom-right`.
Both `center` / `centre` spellings are accepted. `container` is the
slide by default; pass any shape (or anything exposing
`.width` / `.height`) to anchor inside a card / group / placeholder.

## Grouping shapes

`slide.shapes.add_group_shape()` returns a `GroupShape` whose
`.shapes` collection has the same `add_*` methods as a slide. The
group's offset/extent shrink-wrap to its members as you add them.

```python
group = slide.shapes.add_group_shape()
group.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1))
group.shapes.add_shape(MSO_SHAPE.OVAL, Inches(4), Inches(2), Inches(1), Inches(1))

group.fill.solid()                 # tint the whole group (members paint on top)
group.fill.fore_color.rgb = "1F4E79"
group.move(Inches(0.5), Inches(0)) # translate group + every member, O(1)

for shape in group.walk():         # depth-first, recurses into nested groups
    ...                            # filter shape.shape_type for leaves only

group.fit_to_children()            # re-tighten bbox after editing members directly
promoted = group.ungroup()         # dissolve; members keep their on-screen geometry
```

- A group admits a **fill** but not a **line** — the OOXML schema has
  no `a:ln` on `p:grpSpPr`, so there is intentionally no `group.line`.
  (Outline a group by outlining a backing rectangle inside it.)
- `ungroup()` returns the promoted shapes and preserves z-order. It
  raises `ValueError` on a rotated/flipped group; reset rotation and
  flip to 0 first.

## Tables

```python
table_shape = slide.shapes.add_table(
    rows=4, cols=3,
    left=Inches(1), top=Inches(2),
    width=Inches(8), height=Inches(3),
    style="clean",   # disable inherited style flags for hand-styled tables
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

Pass `style="clean"` whenever you plan to apply custom cell borders
or fills. The default inherited table style otherwise overlays them
and renders inconsistently across PowerPoint and LibreOffice.

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

Arithmetic on lengths is fine — power-pptx coerces float coordinates
to integer EMU at the API boundary, so this works:

```python
card_w = (Inches(12.33) - Inches(0.25)) / 2   # produces a float
slide.shapes.add_chart(chart_type, x, y, card_w, height, data)
slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, card_w, h)
shape.width = card_w   # setter coerces too
```

Both ``/`` (true division → float) and ``//`` (floor division → int)
work; pick whichever reads more cleanly. The coercion is round-half-
to-even, so it's unbiased over long expression chains.

### International & layout text properties

```python
p = tf.paragraphs[0]
p.rtl = True                       # right-to-left (Hebrew / Arabic / Farsi)
p.start_at = 5                     # numbered list starting at 5 (arabicPeriod)
p.set_numbered("romanLcPeriod", 3) # i. ii. iii. starting at 3

tf.column_count = 2                # two-column text body
tf.column_spacing = Pt(18)         # gutter between columns

p.tab_stops.add_tab_stop(Inches(1), "center")   # left | center | right | decimal
```
