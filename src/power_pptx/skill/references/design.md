# Design system layer (Phase 9)

The `power_pptx.design` package turns the low-level API into something where
the *default* output looks good. Nothing here adds new XML — it's all
built on top of the foundations from earlier phases.

## Design tokens

`DesignTokens` is a source-agnostic container for brand tokens:
palette, typography, radii, shadows, spacings.

> **Reads return rich objects, not strings.** `tokens.palette[k]` returns
> an `RGBColor`, `tokens.typography[k]` returns a `TypographyToken`,
> `tokens.radii[k]` / `tokens.spacings[k]` return `Length`. Every public
> setter accepts the rich form, so usually you just pass the lookup
> through — no `RGBColor.from_hex(...)` round-trip required:
>
> ```python
> shape.fill.fore_color.rgb = tokens.palette["primary"]   # ✓ pass RGBColor
> shape.fill.fore_color.rgb = "#4F9DFF"                    # ✓ hex string
> # Don't:
> shape.fill.fore_color.rgb = RGBColor.from_hex(tokens.palette["primary"])
> # 'RGBColor' object has no attribute 'startswith'
> ```

```python
from power_pptx.design.tokens import DesignTokens

tokens = DesignTokens.from_dict({
    "palette": {
        "primary":    "#4F9DFF",
        "neutral":    "#1F2937",
        "background": "#FFFFFF",
        "positive":   "#10B981",
        "negative":   "#EF4444",
        "on_primary": "#FFFFFF",
    },
    "typography": {
        # Recipes look up the keys "heading" and "body". Other keys are
        # available for your own use. Bare floats are treated as POINTS;
        # bare ints are EMU. Use floats unless you know what you're doing.
        "heading":  {"family": "Inter", "size": 44.0, "bold": True},
        "body":     {"family": "Inter", "size": 18.0},
        "caption":  {"family": "Inter", "size": 12.0, "italic": True},
    },
    "shadows": {
        # 'blur' / 'distance' are bare-float points too.
        "card": {"blur": 18.0, "distance": 4.0, "alpha": 0.18},
    },
    "radii":    {"card": 12.0, "button": 6.0},
    "spacings": {"sm": 8.0, "md": 16.0, "lg": 32.0},
})
```

### Other constructors

```python
# Optional pyyaml dependency
tokens = DesignTokens.from_yaml("brand.yml")

# Extracts the six accent slots, dk1/dk2/lt1/lt2, hyperlink slots, and
# major/minor fonts from a deck or template
tokens = DesignTokens.from_pptx("template.pptx")

# Layer brand-spec overrides on top of a template-extracted base
tokens = DesignTokens.from_pptx("template.pptx").merge(
    DesignTokens.from_dict({"palette": {"accent": "#FF6600"}})
)
```

## Per-slide appearance overrides

A slide can depart from its master without you editing the master:

```python
slide.color_variant = "dark"            # swap bg/tx against the same theme
slide.color_variant = "light"           # the master's default mapping
slide.color_variant = None              # drop the override entirely

# Backgrounds: give the slide its own and inheritance breaks itself.
slide.background.fill.solid()
slide.background.fill.fore_color.rgb = "#102030"
slide.follow_master_background          # now False (read-only)
```

`color_variant` takes `"light"` / `"dark"` / `None` — **not** an index.
`"dark"` swaps backgrounds and text (`bg1=dk1`, `tx1=lt1`, …) so one
slide reads dark without touching the deck theme. Reading it back
returns `None` when the slide carries a custom mapping matching neither
named variant. For any other mapping use `set_clr_map_override(...)`.

`slide.design_group("kpi-card")` is a context manager that tags every
shape created inside it with the same `lint_group`, so a cluster of
deliberately-overlapping shapes is declared once rather than per shape:

```python
with slide.design_group("kpi-card-1"):
    card = slide.shapes.add_shape(...)
    label = slide.shapes.add_textbox(...)   # both tagged "kpi-card-1"
```

There are two adjacent spellings — `slide.shapes.lint_group_scope(name=...)`
is the same idea on the shape tree, and `slide.lint_group_overlaps(*shapes)`
tags shapes you already made. Reach for `design_group` while building,
`lint_group_overlaps` after the fact.


## Token-resolving shape style

Every shape exposes a `ShapeStyle` facade. Setters fan assignments out
to the low-level proxies:

```python
shape.style.fill        = tokens.palette["primary"]
shape.style.line        = tokens.palette["primary"]
shape.style.shadow      = tokens.shadows["card"]
shape.style.text_color  = tokens.palette["on_primary"]
shape.style.font        = tokens.typography["body"]
```

Partial `ShadowToken` assignments leave unset fields untouched, so
overrides are non-destructive. To clear an effect entirely:

```python
shape.style.shadow = None
```

## Layout primitives

Pure build-time geometry — no XML is read or mutated until `place()`.

### Grid

```python
from power_pptx.design.layout import Grid
from power_pptx.util import Pt

grid = Grid(slide, cols=12, rows=6, gutter=Pt(12), margin=Pt(48))

# Place a shape that spans columns 0..5, rows 0..3
grid.place(card1, col=0, row=0, col_span=6, row_span=4)
grid.place(card2, col=6, row=0, col_span=6, row_span=4)

# Or compute a Box without placing
box = grid.cell(col=0, row=4, col_span=12, row_span=2)
```

A grid doesn't have to span the whole slide — `Grid.from_box` puts one
over any region (a `BBox`, a `Box`, or a plain `(left, top, width,
height)` tuple), so a panel can carry its own grid with no slide
reference:

```python
from power_pptx import BBox

panel = BBox.from_inches(0.75, 2.4, 11.8, 3.6)
grid = Grid.from_box(panel, cols=5, rows=2, gutter=Pt(12))
grid.place(card, col=2, row=1)
```

For the plain "n equal boxes across this region" case, `panel.columns(5,
gap=Pt(12))` / `panel.rows(2, ...)` from `BBox` are shorter — reach for
`Grid` when you need column spans.

### Stack

```python
from power_pptx.design.layout import Stack

stack = Stack(direction="vertical", gap=Pt(8),
              left=Pt(48), top=Pt(48), width=Pt(600))

stack.place(title,    height=Pt(64))
stack.place(subtitle, height=Pt(28))
stack.place(body,     height=Pt(280))

stack.reset()                              # rewind cursor
```

`direction="horizontal"` walks left-to-right with `gap` between items.

## Slide recipes

Opinionated parameterized slide constructors. Each takes the host
`Presentation`, recipe-specific kwargs, an optional `DesignTokens`,
and an optional `transition=` name:

```python
from power_pptx.design.recipes import (
    title_slide, bullet_slide, kpi_slide,
    quote_slide, image_hero_slide,
)

title_slide(
    prs,
    title="Q4 Review",
    subtitle="April 2026",
    tokens=tokens,
    transition="morph",
)

bullet_slide(
    prs,
    title="Customer impact",
    bullets=[
        "Two flagship customers shipped this week.",
        "NPS improved 8 points QoQ.",
        "EU expansion ahead of plan.",
    ],
    tokens=tokens,
)

kpi_slide(
    prs,
    title="Run-rate metrics",
    kpis=[
        {"label": "ARR",         "value": "$182M", "delta": +0.27},
        {"label": "NDR",         "value": "131%",  "delta": +0.03},
        {"label": "CAC payback", "value": "8 mo",  "delta": -0.10},
    ],
    tokens=tokens,
)

quote_slide(
    prs,
    quote="The new dashboards saved my team a week per sprint.",
    attribution="Director of Eng, Flagship Customer",
    tokens=tokens,
)

image_hero_slide(
    prs,
    title="Q4 2026",
    image="hero.jpg",                    # path or binary file-like
    tokens=tokens,
)
```

Recipes use the `Blank` layout and place every shape themselves so the
rendered geometry doesn't depend on the host template's master.

`kpi_slide` honours `palette["positive"]` / `palette["negative"]` when
tinting deltas (falls back to green/red when unset). It applies
`tokens.shadows["card"]` to each card when present.

`image_hero_slide` uses `palette["on_primary"]` for overlay text and
tints the bottom band with `palette["primary"]` at 55% alpha.

## Shape-level building blocks

For mixed layouts where the slide-level recipes don't fit, reach for
the shape-level components in `power_pptx.design.components`. Both
honour the deck's `DesignTokens` and return small dataclasses
exposing the constituent shapes, so callers can compose them into
custom layouts without re-implementing the styling:

```python
from power_pptx import add_kpi_card, add_progress_bar
from power_pptx.util import Inches

kpi = add_kpi_card(
    slide,
    left=Inches(1), top=Inches(1),
    width=Inches(2.5), height=Inches(1.9),
    label="ARR",
    value="$182M",
    delta={"delta": +0.27},
    tokens=tokens,
)
# kpi.card / kpi.value_box / kpi.label_box / kpi.delta_box are
# accessible for further per-deck tweaks.

bar = add_progress_bar(
    slide,
    left=Inches(1), top=Inches(3),
    width=Inches(6), height=Inches(0.3),
    fraction=0.42,         # 0..1 — clamped if you go over
    tokens=tokens,
    fill_color="#4F9DFF",  # optional override
)
# bar.track / bar.fill — animate or restyle either independently.
```

All shape-level components tag their stacked shapes with
`lint_group` so the linter doesn't flag the intentional overlap
(label-on-card, fill-on-track) as a collision.

Other components in the same module:

```python
from power_pptx import (
    add_gauge,         # progress bar with optional target tick
    add_status_pill,   # coloured pill + centred label, e.g. "LIVE"
    add_stat_strip,    # n KPI tiles laid out across a strip with gutter
    add_article_card,  # title + blurb + optional CTA pill
)

add_gauge(slide, left=Inches(1), top=Inches(2), width=Inches(4),
          height=Inches(0.3), fraction=0.62, target=0.80, tokens=tokens)

add_stat_strip(slide, left=Inches(0.5), top=Inches(1.5),
               width=Inches(12), height=Inches(1.9),
               items=[{"label": "ARR", "value": "$182M"},
                      {"label": "NDR", "value": "131%", "delta": +0.03},
                      {"label": "CAC payback", "value": "8 mo"}],
               tokens=tokens)
```

## Starter pack

`examples/starter_pack/` ships three example token sets — `modern`,
`classic`, and `editorial` — each exporting both a raw `SPEC` dict and
a ready-to-use `TOKENS`:

```python
from examples.starter_pack import modern, classic, editorial

prs = Presentation()
title_slide(prs, title="Hello", subtitle="World", tokens=modern.TOKENS)
prs.save("modern.pptx")
```

Run `python -m examples.starter_pack.build_preview` to render one
preview deck per set into `examples/starter_pack/_out/`.

## End-to-end branded deck

```python
from power_pptx import Presentation
from power_pptx.design.tokens import DesignTokens
from power_pptx.design.recipes import (
    title_slide, bullet_slide, kpi_slide, quote_slide,
)

tokens = DesignTokens.from_dict({
    "palette": {
        "primary":   "#4F9DFF",
        "neutral":   "#1F2937",
        "positive":  "#10B981",
        "negative":  "#EF4444",
        "on_primary": "#FFFFFF",
    },
    "typography": {
        # Recipes look up "heading" and "body". Floats = points, ints = EMU.
        "heading": {"family": "Inter", "size": 44.0, "bold": True},
        "body":    {"family": "Inter", "size": 18.0},
    },
    "shadows": {"card": {"blur": 18.0, "distance": 4.0, "alpha": 0.18}},
})

prs = Presentation()
title_slide(prs, title="Q4 Review", subtitle="April 2026",
            tokens=tokens, transition="morph")
kpi_slide(prs, title="Run-rate metrics", kpis=[
    {"label": "ARR", "value": "$182M", "delta": +0.27},
    {"label": "NDR", "value": "131%",  "delta": +0.03},
], tokens=tokens)
bullet_slide(prs, title="Customer impact", bullets=[
    "Two flagship customers shipped this week.",
    "NPS improved 8 points QoQ.",
], tokens=tokens)
quote_slide(prs, quote="The new dashboards saved my team a week per sprint.",
            attribution="Director of Eng", tokens=tokens)

prs.save("q4-review.pptx")
```
