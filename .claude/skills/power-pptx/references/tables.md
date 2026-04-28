# Tables

Most of the table API is unchanged from upstream `python-pptx`. The
post-fork addition is `Cell.borders` — see the bottom of this file.

## Adding a table

```python
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

shape = slide.shapes.add_table(
    rows=4, cols=3,
    left=Inches(1), top=Inches(2),
    width=Inches(8), height=Inches(3),
)
table = shape.table
```

## Headers and cell text

```python
HEADERS = ["Metric", "Value", "Δ QoQ"]
for col, label in enumerate(HEADERS):
    cell = table.cell(0, col)
    cell.text = label
    cell.text_frame.paragraphs[0].font.bold = True
    cell.text_frame.paragraphs[0].font.size = Pt(14)

ROWS = [
    ("ARR",         "$182M", "+27%"),
    ("NDR",         "131%",  "+3%"),
    ("CAC payback", "8 mo",  "−1 mo"),
]
for r, row in enumerate(ROWS, start=1):
    for c, value in enumerate(row):
        table.cell(r, c).text = value
```

## Column widths and row heights

```python
table.columns[0].width = Inches(3.5)
table.columns[1].width = Inches(2.5)
table.columns[2].width = Inches(2.0)

table.rows[0].height = Inches(0.6)
for r in range(1, len(table.rows)):
    table.rows[r].height = Inches(0.5)
```

## Cell fill

```python
cell = table.cell(0, 0)
cell.fill.solid()
cell.fill.fore_color.rgb = RGBColor(0x1F, 0x29, 0x37)
cell.text_frame.paragraphs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
```

## Vertical anchor

```python
from pptx.enum.text import MSO_VERTICAL_ANCHOR

cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
```

## Cell borders (Phase 4 — post-fork addition)

`cell.borders` exposes per-edge `LineFormat` proxies plus convenience
helpers. Backed by the OOXML `a:lnL/lnR/lnT/lnB/lnTlToBr/lnBlToTr`
children of `a:tcPr`.

### Per-edge

```python
cell.borders.left.color.rgb       = RGBColor(0xE5, 0xE7, 0xEB)
cell.borders.left.width           = Pt(0.5)
cell.borders.bottom.color.rgb     = RGBColor(0x1F, 0x29, 0x37)
cell.borders.bottom.width         = Pt(1.5)
cell.borders.diagonal_down.color.rgb = RGBColor(0xEF, 0x44, 0x44)
```

### All edges in one call

```python
cell.borders.all(width=Pt(0.5), color=RGBColor(0xE5, 0xE7, 0xEB))
cell.borders.outer(width=Pt(1.0), color=RGBColor(0x1F, 0x29, 0x37))
cell.borders.none()                # clears every edge
```

### Zebra-striped borders pattern

```python
LIGHT = RGBColor(0xE5, 0xE7, 0xEB)
DARK  = RGBColor(0x1F, 0x29, 0x37)

# Header row — bottom edge dark
for col in range(len(HEADERS)):
    table.cell(0, col).borders.bottom.color.rgb = DARK
    table.cell(0, col).borders.bottom.width     = Pt(1.5)

# Body rows — light row separator
for r in range(1, len(table.rows)):
    for c in range(len(HEADERS)):
        cell = table.cell(r, c)
        cell.borders.bottom.color.rgb = LIGHT
        cell.borders.bottom.width     = Pt(0.5)
```

## Reading borders

Reads on an unset edge return a `LineFormat` whose properties read as
`None` — matching the rest of the library's "reads don't mutate"
contract:

```python
if cell.borders.bottom.width is None:
    print("inherits border from style")
```
