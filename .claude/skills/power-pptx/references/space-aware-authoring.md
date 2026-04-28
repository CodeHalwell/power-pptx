# Space-aware authoring

This is the **headline reason `power-pptx` exists**. Generated decks
break in two predictable ways:

1. Text overflows its container.
2. Boxes sit off the slide.

The library gives you three layered tools to prevent both — used in
this order, they catch ~all real-world cases:

1. **Pre-flight measurement** — choose a font size that fits *before*
   committing the text.
2. **Auto-fit on the text frame** — let PowerPoint shrink the font on
   the way down if the text is dynamic.
3. **The linter** — catch what slipped through, before save.

Use all three. They compose. None of them require Microsoft PowerPoint
to be installed.

## 1. Pre-flight measurement: pick the right size up front

`TextFrame.fit_text(...)` measures with Pillow font metrics and sets
the largest whole-point font size that fits the box:

```python
from pptx.util import Inches, Pt

box = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(1.5))
tf = box.text_frame
tf.text = dynamic_title

# Largest whole-point size ≤ max_size that fits in the box's extents
tf.fit_text(font_family="Inter", max_size=44, bold=True)
```

`fit_text` also sets `auto_size = MSO_AUTO_SIZE.NONE`, so PowerPoint
won't second-guess the size at render time. On Linux / serverless
environments without the requested font installed, it falls back to
Pillow's bundled default — you still get a usable size, no exception.

For finer control (e.g. you want to size text *for* a known box but
leave styling to a recipe), use the underlying fitter directly:

```python
from pptx.text.layout import TextFitter

best_pt = TextFitter.best_fit_font_size(
    text="Q4 2026 Customer Outcomes Review",
    extents=(Inches(8), Inches(1.5)),
    max_size=44,
    font_file="/usr/share/fonts/truetype/inter/Inter-Bold.ttf",
)
```

`best_fit_font_size` returns an int point size; the caller decides what
to do with it.

## 2. Auto-fit: let PowerPoint shrink at render time

When the text isn't fully known at authoring time (or you want
PowerPoint to adapt as the user edits the deck), set
`text_frame.auto_size`:

```python
from pptx.enum.text import MSO_AUTO_SIZE

# Shrink the text to fit
tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

# Or grow the shape to fit the text
tf.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT

# Or do nothing (the default — overflowing text is just clipped)
tf.auto_size = MSO_AUTO_SIZE.NONE
```

`TEXT_TO_FIT_SHAPE` is the right default for headline / KPI / bullet
cards where the box geometry is fixed and the text is dynamic.
`SHAPE_TO_FIT_TEXT` is the right default for body copy where the box
should grow vertically.

> ⚠ `auto_size` is rendered by PowerPoint itself — `power-pptx` only
> writes the flag.  If you want determinism (CI screenshots, PDF
> export pipelines), prefer `fit_text` so the size is baked into the
> XML.

## 3. The linter: catch what slipped through

Run `slide.lint()` before save. It uses Pillow font metrics so it
catches overflow even on auto-fit text frames, and it knows the slide's
real dimensions so off-slide shapes are caught regardless of slide
size:

```python
from pptx.lint import OffSlide, TextOverflow, ShapeCollision
from pptx.exc import LintError

errors = []
for slide in prs.slides:
    report = slide.lint()

    # Cheap auto-fix first (currently nudges off-slide shapes back in)
    report.auto_fix()

    # Re-collect what's left
    for issue in slide.lint().issues:
        if issue.severity.value == "error":
            errors.append(issue)

if errors:
    raise LintError("; ".join(str(e) for e in errors))

prs.save("out.pptx")
```

For decks built through `pptx.compose.from_spec(...)`, fold the linter
into the spec itself:

```python
prs = from_spec({
    "slides": [...],
    "lint": "raise",          # also "warn", "off"
})
```

## Putting it together: a robust headline

```python
from pptx import Presentation
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.util import Inches

def add_headline(prs, slide, text):
    box = slide.shapes.add_textbox(
        Inches(0.6), Inches(0.4),
        Inches(prs.slide_width.inches - 1.2), Inches(1.2),
    )
    tf = box.text_frame
    tf.word_wrap = True
    tf.text = text

    # 1. Pre-flight size pass — bakes a determined size into the XML
    tf.fit_text(font_family="Inter", max_size=44, bold=True)

    # 2. Belt-and-braces: if the user later types more, PowerPoint
    #    will shrink rather than overflow.
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    return box

# 3. Linter as the safety net at save time
for slide in prs.slides:
    slide.lint().auto_fix()

prs.save("headline.pptx")
```

## Geometry helpers — never hand-place EMUs

Off-slide shapes nearly always come from arithmetic mistakes when
positioning. Use the design layer's `Grid` and `Stack` instead of
adding `Inches(...)`s by hand:

```python
from pptx.design.layout import Grid, Stack
from pptx.util import Pt

# 12-column grid with a uniform gutter and outer margin
grid = Grid(slide, cols=12, rows=6, gutter=Pt(12), margin=Pt(48))
grid.place(card1, col=0, row=0, col_span=6, row_span=4)
grid.place(card2, col=6, row=0, col_span=6, row_span=4)

# Vertical cursor with a known total width
stack = Stack(direction="vertical", gap=Pt(8),
              left=Pt(48), top=Pt(48), width=Pt(600))
stack.place(title, height=Pt(64))
stack.place(body,  height=Pt(280))
```

Both compute geometry from the slide's actual dimensions, so you can't
accidentally walk off the right edge — and they're pure arithmetic
(no XML reads or writes) until `place()` is called.

## Why not just slap `auto_size = SHAPE_TO_FIT_TEXT` on everything?

It's tempting, but it fights with the design. A "Customer impact"
title that grows to two lines pushes the body content down, which
might collide with a chart, which the linter then flags. The chain
keeps moving the failure further from the cause.

The robust pattern is:

- **Fixed geometry, fixed font size** for branded slides where the
  designer made a deliberate choice. Use `fit_text` to *verify* the
  size still fits when content is dynamic.
- **`TEXT_TO_FIT_SHAPE`** as the catch-all for headlines / KPI cards.
- **`SHAPE_TO_FIT_TEXT`** only when the slide is a "wall of text" type
  where vertical growth is acceptable.
- **Linter at the end**, always — it's the only thing that sees the
  *whole* slide instead of one shape at a time.
