# Geometry, text, arrows, and diagrams (v2.8+)

This reference covers the high-level helpers added in v2.8 for building
slides programmatically without writing EMU arithmetic or XML for
arrowheads. Everything here is built on top of the inherited 1.0.2 API
— the underlying ``add_shape`` / ``add_connector`` / ``text_frame``
surface still works exactly as it always did.

**Reach for these helpers** when you're generating decks dynamically
(LLM, JSON spec, DB rows). Reach for the lower-level APIs only when
the helpers don't cover your case.

---

## The `BBox` value object

Every rectangular region on a slide can be expressed as a
:class:`BBox` (importable from the package root):

```python
from power_pptx import BBox
from power_pptx.util import Inches

bb = BBox.from_inches(1, 2, 8, 4)        # left, top, width, height
bb.right                                  # Emu(9 inches)
bb.cx, bb.cy                              # centre
bb.area                                   # int (EMU²)
```

`BBox` is immutable, frozen-dataclass, and unpacks to `(left, top,
width, height)` — so it splats straight into add_shape and friends:

```python
slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *bb)
slide.shapes.add_textbox(*bb.inset(all=Inches(0.2)))
```

### Constructors

```python
BBox.from_inches(1, 2, 4, 3)
BBox.from_emu(914400, 1828800, 3657600, 2743200)
BBox.from_shape(some_shape)              # snapshot
BBox.from_slide(slide)                   # full slide
```

`shape.bbox` is the same as `BBox.from_shape(shape)` — a snapshot of
the shape's current geometry. Mutating the shape afterwards does not
update the box. `bb.apply_to(shape)` pushes a box back onto a shape.

### Transforms

```python
bb.shifted(dx=Inches(1))                 # translate
bb.resized(width=Inches(6))              # change one dimension
bb.inset(all=Inches(0.2))                # shrink uniformly
bb.inset(x=Inches(0.5), y=Inches(0.2))   # per-axis
bb.inset(left=Inches(0.1), right=Inches(0.5), top=Inches(0.2))
bb.sub(0.25, 0, 0.5, 1.0)                # normalised sub-box
```

`inset()` with no args is a no-op; negative values expand outward.

### Splits

```python
bb.split_h([1, 1])                       # two equal columns
bb.split_h([2, 1])                       # 66%/33%
bb.split_h([1, 1, 1], gap=Inches(0.1))
bb.split_v([1, 2])                       # vertical
bb.grid(3, 2, gap_x=Inches(0.1))         # row-major 3x2 cells
```

### Predicates

```python
a.contains(b)                            # b fully inside a
a.intersects(b)
a.intersection(b)                        # overlap region (BBox)
a.union(b)                               # smallest enclosing
```

---

## One-call text — `slide.shapes.add_text`

The historical pattern (add_textbox + tf.word_wrap + tf.text + paragraph
alignment + run font.name/size/bold/color) collapses to one call:

```python
slide.shapes.add_text(
    BBox.from_inches(1, 1, 8, 1),
    text="Q4 revenue overview",
    font="Inter",
    size_pt=24,
    bold=True,
    color="#0B5CFF",                     # hex, RGBColor, or (r,g,b) all OK
    align="center",                      # str shortcut; no enum import
    anchor="middle",                     # vertical anchor
    margin_pt=4,
    word_wrap=True,
)
```

Positional length form also works for back-compat:
`add_text(Inches(1), Inches(2), Inches(8), Inches(1), text="…")`.

Returns the textbox shape so further mutation is possible.

---

## Hex-string colour shortcuts

`shape.fill_hex(hex)` and `shape.line_hex(hex, weight_pt=)` replace the
three-line `fill.solid(); fore_color.rgb = RGBColor(...)` ritual. Both
return `self` for chaining:

```python
slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *bb) \
    .fill_hex("#0B5CFF") \
    .line_hex("#0D0D0D", weight_pt=1.25)
```

`hex_color=None` clears the fill (transparent background).

---

## Format-preserving text replacement

`shape.set_text_preserving_format(new_text)` is what you want for
templated placeholders (e.g. `"<TITLE>"`) — it captures the first
run's font face / size / colour / bold / italic, rebuilds the text,
and re-applies the formatting to every new run:

```python
title_shape.set_text_preserving_format("Q4 revenue overview")
# Font, size, colour, bold all preserved verbatim.
```

Multi-line works (`"line one\nline two"`); every paragraph inherits
the template formatting.

---

## Arrows that actually have arrowheads

`add_connector(MSO_CONNECTOR.STRAIGHT, x1, y1, x2, y2)` returns a line
with no arrowhead. **Use `add_arrow` instead**:

```python
slide.shapes.add_arrow(
    start=box_a,                         # Shape, BBox, or (x, y)
    end=box_b,
    head="triangle",                     # "triangle"|"arrow"|"stealth"|"diamond"|"oval"|"none"
    tail=None,
    color="#0B5CFF",
    weight_pt=1.5,
    style="solid",                       # "solid"|"dashed"|"dotted"
    inset_pt=6.0,                        # pull endpoints back from shape edges
    end_side="auto",                     # "top"|"right"|"bottom"|"left"|"auto"
    route="straight",                    # "straight"|"elbow"|"curved"
)
```

When `start` / `end` is a Shape or BBox, the arrow auto-routes to the
mid-edge nearest the opposite endpoint. `inset_pt` is the small pullback
applied so the arrowhead triangle doesn't bleed into the target box.

---

## Picture replacement and container detection

For a picture that's broken or sub-quality:

```python
def diagram(slide, bbox):
    left, right = bbox.split_h([1, 1], gap=Inches(0.1))
    slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *left).fill_hex("#0B5CFF")
    slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *right).fill_hex("#FFFFFF")

picture.replace_with(diagram, padding=Inches(0.1))
```

The picture is deleted; the builder is called with a `BBox` sized to
the picture's old footprint (minus optional padding). The builder
draws native shapes in the freed area.

When the picture sits inside a "card" rectangle plus a heading,
`picture.enclosing_container()` returns the bbox of the enclosing card
(trimmed to avoid sibling text). This is the bbox you actually want
to redraw into, not the picture's own bbox:

```python
container_bbox = picture.enclosing_container(exclude_text=True)
picture.replace_with(builder, padding=Inches(0.05))
```

---

## Slide-level helpers

```python
slide.slide_bbox()                       # BBox of the full slide
slide.content_bbox()                     # BBox of all non-decorative shapes
slide.find_empty_region(min_width=Inches(2), min_height=Inches(1))
slide.tidy()                             # lint + auto_fix(safe subset)
```

`tidy()` is the one-call cleanup before save: it lints, runs the safe
subset of auto-fixes (OffSlide clamp, TextOverflow flip), and returns
the list of fixes applied.

---

## Diagram recipes — `power_pptx.diagrams`

Six built-in diagram patterns covering ~80% of architecture-deck
content. Each takes a slide, a `BBox`, and a small content spec:

```python
from power_pptx.diagrams import (
    horizontal_pipeline, vertical_pipeline,
    hub_and_spoke, cycle, decision_tree,
    comparison_columns,
)

# Pipeline
horizontal_pipeline(
    slide, bbox,
    steps=["Extract", "Classify", "Enrich", "Output"],
    accent="#0B5CFF",
)

# Hub-and-spoke
hub_and_spoke(
    slide, bbox,
    centre="Agent",
    spokes=["Memory", "Tools", "Planning", "Perception"],
)

# Cyclic loop
cycle(
    slide, bbox,
    steps=["Observe", "Orient", "Decide", "Act"],
)

# Decision tree (one level of children optional)
decision_tree(
    slide, bbox,
    root="Is the deck dynamic?",
    branches=[
        {"label": "Yes", "children": ["Use lint()", "Use fit_text"]},
        {"label": "No", "children": ["Author manually"]},
    ],
)

# N-column comparison
comparison_columns(
    slide, bbox,
    columns=[
        {"title": "Pros", "body": ["Fast", "Cheap", "Composable"]},
        {"title": "Cons", "body": ["New API"]},
    ],
)
```

Each recipe returns a small dataclass (`PipelineResult`, `HubAndSpokeResult`,
…) exposing the underlying shapes for further tweaks.

Step / column dicts accept per-item `fill` and `text_color` overrides:

```python
horizontal_pipeline(
    slide, bbox,
    steps=[
        {"label": "Cleaned",   "fill": "#E8F0FF", "text_color": "#0B3D9C"},
        {"label": "Features",  "fill": "#FFFFFF"},
    ],
)
```

---

## End-to-end audit — `power_pptx.audit`

For agents producing a full deck, `audit(prs)` returns a structured
"what I shipped" summary:

```python
from power_pptx import audit

report = audit(prs)
print(report.markdown())

# Or programmatically:
report.has_errors                        # bool
report.lint_issues                       # [(slide_idx, LintIssue), ...]
report.broken_pictures                   # [(idx, picture), ...]
report.empty_slides                      # [idx, ...]
report.font_warnings                     # [(idx, font), ...]
report.size_warnings                     # [(idx, name, bytes), ...]
```

The audit is read-only — it never mutates the deck. The markdown
output is structured for chat replies.

---

## Render helpers

`render_slides(prs, slides=[0, 1, 2], out_dir="thumbs",
name_template="slide-{:02d}.png")` is the friendlier wrapper around
`render_slide_thumbnails` — same engine, but with sensible argument
naming and a `name_template` for clean file names.
