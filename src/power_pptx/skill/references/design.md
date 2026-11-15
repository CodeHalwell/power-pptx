# Design system layer (Phase 9)

For measured native `Row`, `Column`, `Card`, `Badge`, `MetricTile`, and
`NativeContent` components, read `authoring-workflows.md`. These add automatic
padding, gaps, child measurement, sizing, and deliberate background overlap.

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
> shape.fill.solid()
> shape.fill.fore_color.rgb = tokens.palette["primary"]   # ✓ pass RGBColor
> shape.fill.fore_color.rgb = "#4F9DFF"                    # ✓ hex string
> # Don't: RGBColor.from_hex(tokens.palette["primary"]) raises
> # AttributeError: 'RGBColor' object has no attribute 'startswith'
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
        # available for your own use. A bare number is POINTS: 44 and
        # 44.0 mean the same thing.
        "heading":  {"family": "Inter", "size": 44, "bold": True},
        "body":     {"family": "Inter", "size": 18},
        "caption":  {"family": "Inter", "size": 12, "italic": True},
    },
    "shadows": {
        # 'blur_radius' (or its alias 'blur') and 'distance' are points too.
        "card": {"blur_radius": 18, "distance": 4, "alpha": 0.18},
    },
    "radii":    {"card": 12, "button": 6},
    "spacings": {"sm": 8, "md": 16, "lg": 32},
})
```

**Units.** Every length field — typography `size`, `radii`, `spacings`,
shadow `blur_radius` / `distance` — takes either a `Length` (`Pt(8)`,
`Emu(101600)`, `Inches(0.1)`), which is kept exactly, or a bare number,
which is read as **points**. Integers and floats are the same (`36` ==
`36.0`), so a brand spec that went through JSON or YAML behaves like the
Python dict. The one exception is backward compatibility: a bare
*integer* of 12700 or more (one point in EMU) is still read as EMU, as
every bare integer used to be. Pass `Pt(...)` if a value that large
really is points.

Palette colours take a hex string (`"#4F9DFF"` or `"4F9DFF"`), an
`RGBColor`, or an `(r, g, b)` tuple — or an `[r, g, b]` list, which is
how JSON and YAML carry one.

**Keys are checked.** A typography token takes `family` (required),
`size`, `bold`, `italic`, `color`; a shadow token takes `blur_radius`
(alias `blur`), `distance`, `direction`, `color`, `alpha`. Anything else
raises `ValueError` with a did-you-mean hint (`'sise' (did you mean
'size'?)`) instead of being dropped, and errors name the token
(`typography.heading.size: ...`). At the top level, keys other than the
five sections are ignored so a brand file can carry its own data — but a
near-miss of a section name (`"palete"`, `"shadow"`) raises.

### Other constructors

```python
# Optional pyyaml dependency. Write lengths as plain numbers of points
# (`size: 36`, `radii: {md: 8}`).
tokens = DesignTokens.from_yaml("brand.yml")

# Extracts the six accent slots, dk1/dk2/lt1/lt2, hyperlink slots, and
# major/minor fonts from a deck or template. Takes a path (str or
# pathlib.Path), an open binary file, or a Presentation.
tokens = DesignTokens.from_pptx("template.pptx")

# Per-call tweaks: dotted paths or nested dicts, same unit rule
tokens = tokens.with_overrides({"typography.heading.size": 40,
                                "shadows.card.blur": 24})

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
rendered geometry doesn't depend on the host template's master. A
template with no layout named `Blank` (renamed or localised) gets the
layout with the fewest placeholders, and any placeholders it brings are
removed, so recipe slides always start empty.

The same module also has `section_divider`, `chart_slide`, `table_slide`,
`code_slide`, `timeline_slide`, `comparison_slide` and `figure_slide`;
`from_spec` reaches them by layout name (`"timeline"`, `"code"`, …).

**Recipes fit their content and fail loudly.** Where the text is known
at build time the fitting size is measured and written into the slide
(an autofit flag alone does nothing in PowerPoint until the text is
edited), never below 9pt. Content that cannot fit at 9pt raises
`ValueError` saying how many items fit — split it across slides:

| Recipe | Limit (10" × 7.5" / 13.33" × 7.5") |
|---|---|
| `kpi_slide` | 9 / 12 cards in the row |
| `timeline_slide` | 15 / 21 milestones |
| `comparison_slide` | 21 rows |
| `table_slide` | ~20 single-line rows; columns ≥ 0.4" |
| `bullet_slide` | as many bullets as fit at 9pt |
| `code_slide` | truncates with `… (+N more lines)`; `overflow="raise"` raises |

**Item dicts are validated.** `kpis` (`label`, `value`, optional
`delta` / `delta_text`), `milestones` (`label`, optional `date` /
`done`), comparison `rows` (`left`, `right`) and chart `series`
(`name`, `values`) must use exactly those keys; a typo raises with a
did-you-mean hint instead of rendering a blank card.

**Text meets 4.5:1 on the surface it sits on.** When a palette role
does not (e.g. `muted` on `surface`, which is 2.2–3.4:1 in every
built-in preset), the recipe darkens or lightens it, keeping its hue,
until it does; a palette whose roles already contrast is used as-is.

`kpi_slide` honours `palette["positive"]` / `palette["negative"]` when
tinting deltas (falls back to green/red when unset). It applies
`tokens.shadows["card"]` to each card when present, and sets one value,
label and delta size across the row.

`table_slide(widths=…)` reads bare numbers as relative weights —
`[50, 25, 25]`, `[2, 1, 1]` and `[0.5, 0.25, 0.25]` are the same table —
and `Length` values (`Inches(2)`) as exact widths. Columns past the end
of the list share what fractions summing below 1 leave (`[0.5]` on three
columns is 50/25/25); zero or negative widths raise.

`code_slide` writes one installed monospace family (Cascadia Code,
Consolas, Menlo, DejaVu Sans Mono, Liberation Mono or Courier New;
Consolas when none is found) flagged fixed-pitch, or the `font=` you
pass. Text and syntax colours follow the panel's brightness, so it is
readable with or without tokens. The code is fitted to the panel,
14pt down to 9pt.

`timeline_slide` alternates labels above and below the rail, keeps them
inside the slide margins and anchors labels above the rail at the
bottom, so the slide lints clean for 2–8 milestones on either size.

`figure_slide` contain-fits every figure kind (aspect ratio kept,
centred in the content area); `fit="cover"` crops to fill and
`fit="stretch"` distorts. It accepts Plotly / Matplotlib figures, SVG
or HTML markup, image paths, raw image bytes and binary file objects.
A figure it cannot embed (unknown kind, missing file, unreadable bytes,
rejected `plotly_options`) raises and leaves no half-built slide behind.

`chart_slide` takes `line`, `line_markers`, `bar`, `column`, `pie`,
`doughnut` and `area` (category charts; build XY scatter with
`slide.shapes.add_chart`). A `None` value leaves a gap.

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
# accessible for further per-deck tweaks. The value/label/delta stack
# is laid out for a 1.9" card and scales down with a shorter one;
# below 0.95" it raises ValueError.

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
# Each card needs at least 0.75" of width; more items raise ValueError.
```

## Starter pack

`examples/starter_pack/` ships three example token sets — `modern`,
`classic`, and `editorial` — each exporting both a raw `SPEC` dict and
a ready-to-use `TOKENS`:

```python
# run from a checkout of the power-pptx repository
from examples.starter_pack import modern, classic, editorial
from power_pptx import Presentation
from power_pptx.design.recipes import title_slide

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
        # Recipes look up "heading" and "body". Bare numbers are points.
        "heading": {"family": "Inter", "size": 44, "bold": True},
        "body":    {"family": "Inter", "size": 18},
    },
    "shadows": {"card": {"blur_radius": 18, "distance": 4, "alpha": 0.18}},
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
