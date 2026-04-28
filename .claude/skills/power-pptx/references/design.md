# Design system layer (Phase 9)

The `pptx.design` package turns the low-level API into something where
the *default* output looks good. Nothing here adds new XML — it's all
built on top of the foundations from earlier phases.

## Design tokens

`DesignTokens` is a source-agnostic container for brand tokens:
palette, typography, radii, shadows, spacings.

```python
from pptx.design.tokens import DesignTokens

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
from pptx.design.layout import Grid
from pptx.util import Pt

grid = Grid(slide, cols=12, rows=6, gutter=Pt(12), margin=Pt(48))

# Place a shape that spans columns 0..5, rows 0..3
grid.place(card1, col=0, row=0, col_span=6, row_span=4)
grid.place(card2, col=6, row=0, col_span=6, row_span=4)

# Or compute a Box without placing
box = grid.cell(col=0, row=4, col_span=12, row_span=2)
```

### Stack

```python
from pptx.design.layout import Stack

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
from pptx.design.recipes import (
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
from pptx import Presentation
from pptx.design.tokens import DesignTokens
from pptx.design.recipes import (
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
