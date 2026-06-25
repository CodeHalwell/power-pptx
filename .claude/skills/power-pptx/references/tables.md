# Tables

Most of the table API is unchanged from upstream `python-pptx`. The
post-fork addition is `Cell.borders` — see the bottom of this file.

## Adding a table

```python
from power_pptx.util import Inches, Pt
from power_pptx.dml.color import RGBColor

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
from power_pptx.enum.text import MSO_VERTICAL_ANCHOR

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

Reads on an unset edge return a `LineFormat` and never mutate the XML
(the "reads don't mutate" contract). `LineFormat.width` reads back as
`Emu(0)` when no width has been set — the same as a plain shape's
`shape.line.width` — so test for a falsy width, not `None`:

```python
if not cell.borders.bottom.width:        # Emu(0) when unset
    print("inherits border from style")
```

`color.rgb` on an unset edge does read back as `None`.

## Rotated / stacked cell text

Use `cell.text_direction` for matrix-style or rotated column headers:

```python
cell.text_direction = "rotate90"    # "horizontal" (default), "rotate90",
cell.text_direction = "stacked"     # "rotate270", "stacked"
cell.vertical_anchor = MSO_ANCHOR.MIDDLE   # t / ctr / b within the cell
```

Reading returns the friendly string (`"horizontal"` when unset); assigning
`"horizontal"` or `None` clears it. Maps to `<a:tcPr vert="…">` /
`anchor="…"` — schema-valid and round-trip clean.

## Built-in table styles

Apply any of PowerPoint's ~70 built-in table styles by name or GUID:

```python
table.style = "Medium Style 2 - Accent 1"      # friendly name
table.style = "Table Grid"
table.style = "{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"  # raw GUID also OK
print(table.style)        # -> friendly name (or raw GUID / None)
table.style = None        # detach (same as table.clear_style())
```

Discover valid names via `from power_pptx.table_styles import TABLE_STYLES`.
An unknown name raises `ValueError` with a "did you mean" suggestion.
Writing just the style GUID is schema-valid — nothing is added to
`tableStyles.xml`.
