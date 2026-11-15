# Basics — the inherited 1.0.2 surface

Everything in this file works the same as upstream `python-pptx 1.0.2`.
It's here so you don't have to leave the skill for boring boilerplate.

## Open / create / save

```python
from power_pptx import Presentation

prs = Presentation()                     # blank deck, 4:3 (10" x 7.5") by default
prs = Presentation("template.pptx")      # open existing
prs.save("out.pptx")
```

Templates (`.potx`) and slide shows (`.ppsx`) open the same way, and the
file name given to `save()` decides what is written: `"brand.potx"` saves
a template, `"show.ppsx"` a slide show, anything else a presentation.
Saving to a path is atomic — if it fails part-way, an existing file there
is left untouched.

A file that is not a package this library can read (a legacy `.ppt`, a
password-protected deck, a truncated download) raises
`power_pptx.exc.InvalidPackageError`; a path with no file raises
`PackageNotFoundError`, which `InvalidPackageError` subclasses:

```python
from power_pptx.exc import PackageNotFoundError

try:
    prs = Presentation("upload.pptx")
except PackageNotFoundError as exc:    # missing, or not a readable package
    print(f"cannot open the deck: {exc}")
```

`Presentation(...)` also accepts a binary file-like object, and `save()`
writes to one — useful for HTTP responses or in-memory generation:

```python
import io

def deck_bytes(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)                      # a stream always gets a .pptx
    return buf.getvalue()
```

## Slide size

```python
from power_pptx.util import Inches, Pt

prs.slide_width  = Inches(13.333)        # 16:9 widescreen
prs.slide_height = Inches(7.5)

prs.set_slide_size(Inches(13.333), Inches(7.5))   # both in one call
```

### Limits, and sizes that exceed them (LED walls, banners)

A slide is between 1 and 56 inches a side — PowerPoint's limit, exposed
as `MIN_SLIDE_SIZE` / `MAX_SLIDE_SIZE` in `power_pptx.util`. A video
wall specified in pixels is usually bigger than that. `fit=True` scales
the size to the nearest one **in the same proportions** that is allowed,
and returns the factor so the content can follow:

```python
# 7680 x 1080 px wall, at 96 px to the inch = 80" x 11.25" -- too wide
size = prs.set_slide_size(Inches(7680 / 96), Inches(1080 / 96), fit=True)
size.width.inches, size.height.inches, size.scale     # (56.0, 7.875, 0.7)

px = size.scale * Inches(1) / 96           # one wall pixel, on the slide
box = slide.shapes.add_textbox(1920 * px, 120 * px, 3840 * px, 400 * px)
box.text_frame.paragraphs[0].font.size = Pt(160 * size.scale)   # fonts too
```

- The return value is a `(width, height, scale)` named tuple
  (`SlideSize`). `scale` is `1.0` when nothing had to change; multiply
  coordinates and font sizes worked out for the requested size by it.
- A size that already fits is never enlarged; a too-small one is scaled
  *up* to the minimum (`scale > 1`).
- Without `fit=True` an out-of-range size raises `ValueError` naming the
  dimension and the limits in inches, and changes nothing. Shapes more
  elongated than 56:1 cannot be fitted at all and raise either way.
- `fit_slide_size(width, height)` (also in `power_pptx.util`) does the
  arithmetic without a presentation, e.g. to plan a layout first.
- Existing shapes, layouts, and masters are not moved or resized.

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

## Removing and duplicating slides

```python
prs.slides.remove(prs.slides[2])               # PowerPoint's "Delete Slide"

copy = prs.slides.duplicate(slide)             # right after `slide`, returned
copy = prs.slides.duplicate(slide, index=-1)   # prs.slides[index] is the copy
copy = prs.slides.duplicate(slide, index=0)    # first in the deck

for slide in list(prs.slides):                 # iterate over a copy to remove
    if not slide.shapes:
        prs.slides.remove(slide)
```

- `remove` also takes the slide out of its section and any custom show,
  and unlinks every shape or text run that jumped to it (click and hover,
  on slides, notes, layouts, masters) — the shape keeps its text. Its
  notes, charts and media no other slide uses are not saved. Never delete
  through `prs.slides._sldIdLst` + `drop_rel`: that leaves an orphan slide
  in the package, reached through any link to it.
- `duplicate` gives the copy its own shapes, notes, chart and chart
  workbook (edit one, the other is unchanged); pictures and media are
  shared. Links to other slides are kept; a self-link points at the copy.
  The copy keeps the original's layout and joins the section of the slide
  before it.
- A slide from another deck raises `ValueError` (copy it with
  `prs.import_slide(slide)`); a non-`Slide` argument raises `TypeError`,
  and an out-of-range `index` raises `IndexError`.

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

### One call instead of per-run styling

Setting `font.*` on every paragraph is the single most common source of
bloated deck-building code, and it silently misses runs you didn't
enumerate. `set_paragraph_defaults` applies to *every* paragraph and run
in the frame, including ones added later in the same breath:

```python
tf.text = "Headline"
tf.add_paragraph().text = "Supporting line"

tf.set_paragraph_defaults(
    font_name="Inter", size=Pt(14), bold=True, color="#333333",
)
```

Accepted kwargs are exactly `font_name`, `size`, `bold`, `italic`,
`color` — all keyword-only, all optional. Note it does **not** take
spacing arguments; `space_before` / `space_after` / `line_spacing` are
per-paragraph (below).

### Spacing and margins

```python
p.space_before = Pt(6)
p.space_after  = Pt(6)
p.line_spacing = 1.2               # multiple, or Pt(20) for exact

tf.margin_left = Inches(0.2)       # also margin_right/top/bottom
```

Paragraphs can also be built run-by-run when you need mixed styling in
one line:

```python
p = tf.add_paragraph()
run = p.add_run(); run.text = "Bold lead-in. "
run.font.bold = True
run.font.underline = True
p.add_line_break()                 # soft break, stays in the paragraph
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
useful for hairline dividers, glow shapes, and translucent overlays.
Assign after a colour is set:

```python
divider.line.color.rgb   = RGBColor(0x0D, 0x0D, 0x0D)
divider.line.color.alpha = 0.08     # 8% opaque hairline
```

### Two-stop linear gradients

```python
bar.fill.linear_gradient("#06D6FE", "#B14AED", angle=270)  # top→bottom
```

`angle` is **counter-clockwise**, like an angle in maths: `0` runs
left→right, `90` bottom→top, `180` right→left, `270` (or `-90`)
top→bottom. The first colour sits where the gradient starts, so
`angle=270` puts it at the top and `angle=90` at the bottom. (This is
the reverse of the clockwise `ang` in the XML: `angle=90` is stored as
`ang="16200000"`.)

→ **Multi-stop gradients, gradient kinds, mutable stop lists, and the
full alpha surface live in `effects.md`** — the canonical fills and
effects reference. Don't go looking in two places.

## Pictures

```python
pic = slide.shapes.add_picture(
    "hero.jpg",
    left=Inches(0), top=Inches(0),
    width=prs.slide_width, height=prs.slide_height,
)
```

### Cropping

Crop values are *fractions of the original image*, not lengths — `0.1`
trims 10% off that edge. They compose with the placement box, so crop
first, then size:

```python
pic = slide.shapes.add_picture("hero.png", Inches(1), Inches(1),
                               width=Inches(4))
pic.crop_left = 0.10               # also crop_right/top/bottom
pic.crop_top  = 0.05
pic.alt_text  = "Q4 revenue by segment"   # set this; screen readers need it
                                          # (the file name add_picture writes
                                          # counts as missing in audits)
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

## Knowing what a shape is

Before touching a shape you found by iteration, ask what it actually is
— the accessors raise rather than return `None` when the shape has no
such content:

```python
for shape in slide.shapes:
    if shape.has_text_frame:
        print(shape.text_frame.text)
    if shape.has_table:
        print(shape.table.rows)
    if shape.has_chart:
        print(shape.chart.chart_type)
    if shape.is_placeholder:
        print("placeholder idx", shape.placeholder_format.idx,
              "type", shape.placeholder_format.type)
    print(shape.shape_id, shape.name)   # shape_id is unique per slide
```

`shape.delete()` removes a shape *and* purges any animation timing
entries that targeted it — PowerPoint silently "repairs" decks with
orphan timing references, so prefer it over detaching the element by
hand.

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

Placeholder `left` / `top` / `width` / `height` setters coerce the same
way (from 2.15.0; earlier releases raised `TypeError` for a float).

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

### Sections, slide order, and speaker notes

```python
# Named sections (PowerPoint outline / slide-sorter groupings)
prs.sections.add("Intro", start_slide_index=0)
prs.sections.add("Body",  start_slide_index=2)
for section in prs.sections:
    print(section.name, section.slide_ids)   # section.name is read/write

# Reorder slides without touching XML
prs.slides.move(0, 2)              # send slide 0 to position 2
prs.slides.reorder([2, 0, 1])     # full permutation (indices or Slide objects)

# First-class speaker notes
slide.notes = "Remember to thank the sponsors."   # creates the notes slide
print(slide.notes)                # "" when the slide has no notes
```

`start_slide_index` claims every slide from that position to the deck
end. `move` raises `IndexError` out of range; `reorder` raises
`ValueError` unless given a clean permutation.

Sections follow the new order. A moved slide behaves as if dragged in
the slide sorter: it stays in its section if it lands next to it, and
otherwise joins the section of the slide before it (after it, when it
becomes first) — so `move(5, 0)` puts slide 5 in the first section.
`reorder` keeps every slide's section when each section stays in one
piece (a reversed deck reverses its sections too); otherwise the
slides that kept their relative order keep their sections and the rest
are placed as `move` would place them. A section can end up empty.

## Running as a slide show

### Slide-show settings (loop, kiosk)

`prs.slide_show` is PowerPoint's *Set Up Slide Show* dialog. The settings
live in `ppt/presProps.xml` (not `presentation.xml`); there is no need
to edit that part by hand:

```python
show = prs.slide_show
show.loop = True                # "Loop continuously until 'Esc'"
show.show_type = "kiosk"        # "speaker" (default) | "window" | "kiosk"
show.use_timings = True         # False = advance manually, ignore timings
show.show_narration = True      # False = "Show without narration"
show.show_animation = True      # False = "Show without animation"
```

A deck that has to run by itself on a display needs three things — the
loop, a show type, and an advance time on the slides (`loop` alone only
changes what happens after the last slide):

```python
from power_pptx.enum.presentation import MSO_TRANSITION

prs.slide_show.loop = True
prs.slide_show.show_type = "kiosk"        # full screen, a click does not advance
prs.set_transition(MSO_TRANSITION.FADE, advance_after=5000)   # ms per slide
```

- The advance time belongs to each slide's transition. Name a transition
  kind with it (`CUT` for no visible effect): LibreOffice ignores the
  advance time of a slide whose transition has no kind.
- `show_type` takes a string or a `PP_SLIDE_SHOW_TYPE` member
  (`from power_pptx.enum.slide_show import PP_SLIDE_SHOW_TYPE`) and always
  reads back as a member (`SPEAKER`, `WINDOW`, `KIOSK`). The bools take
  `True`/`False` only — `show.loop = "false"` raises `TypeError`.
- PowerPoint always loops a kiosk show; set `loop` too so other viewers
  (LibreOffice honours `loop` and `use_timings`) do the same.
- Reads never modify the deck. A deck with no settings reports
  `loop=False`, `SPEAKER`, and `True` for the other three. The
  `<p:showPr>` element — and `presProps.xml` itself, for a deck written by
  a tool that leaves it out — is created on the first real change and
  removed again when every setting is back at its default. Pen colour,
  colour history, and extension lists in the same part are left alone.

### Hidden slides

```python
slide.hidden = True      # stays in the deck, skipped in the slide show
slide.hidden             # True
slide.hidden = False     # shown again (removes the attribute, no show="1")

for slide, rows in zip(prs.slides, tables):   # drop empty slides from a
    slide.hidden = not rows                   # generated show, no renumbering
```

This replaces `slide._element.set("show", "0")`. Only `True`/`False` are
accepted. Hidden slides are still linted and still rendered, so
`slide_indexes=[n]` always means `prs.slides[n]`.
