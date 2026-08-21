# Tables

Most of the table API is unchanged from upstream `python-pptx`. The
post-fork additions are `cell.format(...)` / `table.format_cells(...)`
styling, `Cell.borders`, and `Table.fit_to_box` — reach for those before
dropping to raw fill/font mutation.

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
    table.cell(0, col).text = label

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

## Styling cells: `format` and `format_cells`

`cell.format(...)` sets fill and text styling in one call, using the
same keyword vocabulary as `slide.shapes.add_text(...)`. Every argument
is optional and `None` means "leave alone", so calls layer:

```python
table.cell(0, 0).format(
    fill="#1F2937",        # hex / (r, g, b) / RGBColor — or "none"
    color="#FFFFFF",       # text colour
    font="Inter",
    size_pt=12,
    bold=True,
    italic=False,
    align="center",        # left / center / right / justify
    anchor="middle",       # top / middle / bottom
    margin=(2, 8, 2, 8),   # points: scalar, or (top, right, bottom, left)
    word_wrap=True,
)
```

`table.format_cells(rows=..., cols=..., ...)` applies the same keywords
across a selection. `rows` / `cols` each accept `None` (all), an `int`
(negative counts from the end), a `slice`, or any iterable of indices —
so a whole table's look is a handful of calls:

```python
table.format_cells(rows=0, fill="#1F2937", color="#FFFFFF", bold=True)
table.format_cells(rows=slice(1, None), size_pt=11, anchor="middle")
table.format_cells(rows=range(2, len(table.rows), 2), fill="#F6F7F9")  # banding
table.format_cells(cols=-1, align="right")                            # numbers
```

Both return the cell / table, so they chain. Spanned (merged-away)
cells are skipped; style the merge origin instead.

Either order works — style an empty header row and then assign
`cell.text`, or populate first and style afterwards. The formatting is
recorded as the cell's text-body defaults (`<a:lstStyle>`) as well as on
its current runs, and a text replacement leaves those defaults alone.

> A cell's vertical anchor and insets live on `<a:tcPr>`, not on its
> text frame's `<a:bodyPr>` — PowerPoint reads the cell properties and
> ignores the body ones. `format(anchor=..., margin=...)` writes them to
> the right place; setting `cell.text_frame.vertical_anchor` does not.

The low-level surface is still there when you need it
(`cell.fill.solid()`, `cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE`,
per-run `font` objects) — `format` just removes the loop.

## Detaching the default table style

Every table created via `slide.shapes.add_table(...)` is born with
the "Medium Style 2 — Accent 1" `tableStyleId` attached. The style
ships a banded-row overlay that PowerPoint and LibreOffice render
on top of any per-cell fills you set — and that overlay survives
`table.horz_banding = False` and `table.first_row = False`, because
those flags only suppress `bandRow` / `firstRow` markup, not the
style's own banding rules.

When you want full control of every cell's appearance, detach the
default style outright:

```python
table.clear_style()                       # drops <a:tableStyleId>
table.format_cells(fill="#FFFFFF")        # now every cell is yours
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
