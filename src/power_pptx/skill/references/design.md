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

tokens = DesignTokens.from_dict(
    {
        "palette": {
            # RGBColor, a hex string, or an [r, g, b] list / tuple.
            "primary": "#4F9DFF",
            "neutral": "#1F2937",
            "background": "#FFFFFF",
            "positive": "#10B981",
            "negative": "#EF4444",
            "on_primary": "#FFFFFF",
        },
        "typography": {
            # Recipes look up the keys "heading" and "body". Other keys are
            # available for your own use. Bare floats are treated as POINTS;
            # bare ints are EMU, so write 44.0 (or Pt(44)), never 44.
            "heading": {"family": "Inter", "size": 44.0, "bold": True},
            "body": {"family": "Inter", "size": 18.0},
            "caption": {"family": "Inter", "size": 12.0, "italic": True},
        },
        "shadows": {
            # 'blur_radius' / 'distance' are bare-float points too; 'alpha'
            # is 0-1.
            "card": {"blur_radius": 18.0, "distance": 4.0, "alpha": 0.18},
        },
        "radii": {"card": 12.0, "button": 6.0},
        "spacings": {"sm": 8.0, "md": 16.0, "lg": 32.0},
    }
)
```

### Units and validation

Every length in a token dict — a font `size`, a radius, a spacing, a
shadow `blur_radius` / `distance` — follows one rule:

| You write | It means |
| --- | --- |
| `36.0` (a float) | 36 **points** |
| `Pt(36)`, `Emu(457200)` (a `Length`) | exactly that |
| `36` (a bare int) | 36 **EMU**, about 0.003 pt |

The bare-int-is-EMU rule is kept for backwards compatibility. It is also
the trap a JSON or YAML file falls into: `"size": 36` is a 36-EMU font
that used to fail much later, inside a recipe, with no location. So
coercion now rejects the values that can only be a mistake, with a
`ValueError` that names the token (the unit errors end in "use a float
for points, or Pt(...)"):

- a typography `size` outside 1–4000 pt
  (`tokens.typography.heading.size`);
- a radius, spacing or shadow `blur_radius` / `distance` given as a bare
  int of 1–99 EMU (`tokens.radii.md`). `0` is accepted — it has no unit
  to get wrong — and so is any `Length`, however small;
- a shadow `alpha` outside 0–1, including one set through
  `with_overrides({"shadows.card.alpha": 2.0})`
  (`tokens.shadows.card.alpha`).

`tokens.with_overrides(...)` validates exactly as `from_dict` does and
leaves the base untouched when it raises; a key with more than three
segments (`typography.heading.size.x`) is rejected. Each category
(`palette`, `typography`, `radii`, `shadows`, `spacings`) must be a
mapping — `{"palette": "modern_blue"}` raises rather than being read as
a named palette; start from a built-in with
`DesignTokens.from_preset("modern_light")`.

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
slide.color_variant = "dark"  # swap bg/tx against the same theme
slide.color_variant = "light"  # the master's default mapping
slide.color_variant = None  # drop the override entirely

# Backgrounds: give the slide its own and inheritance breaks itself.
slide.background.fill.solid()
slide.background.fill.fore_color.rgb = "#102030"
slide.follow_master_background  # now False (read-only)
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
    label = slide.shapes.add_textbox(...)  # both tagged "kpi-card-1"
```

There are two adjacent spellings — `slide.shapes.lint_group_scope(name=...)`
is the same idea on the shape tree, and `slide.lint_group_overlaps(*shapes)`
tags shapes you already made. Reach for `design_group` while building,
`lint_group_overlaps` after the fact.


## Token-resolving shape style

Every shape exposes a `ShapeStyle` facade. Setters fan assignments out
to the low-level proxies:

```python
shape.style.fill = tokens.palette["primary"]
shape.style.line = tokens.palette["primary"]
shape.style.shadow = tokens.shadows["card"]
shape.style.text_color = tokens.palette["on_primary"]
shape.style.font = tokens.typography["body"]
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

`cols` and `rows` are counts: they must be integers `>= 1`. A float such
as `cols=2.5` or a `bool` raises `ValueError` instead of being
truncated to a grid you didn't ask for.

### Stack

```python
from power_pptx.design.layout import Stack

stack = Stack(direction="vertical", gap=Pt(8), left=Pt(48), top=Pt(48), width=Pt(600))

stack.place(title, height=Pt(64))
stack.place(subtitle, height=Pt(28))
stack.place(body, height=Pt(280))

stack.reset()  # rewind cursor
```

`direction="horizontal"` walks left-to-right with `gap` between items.

`width=` / `height=` on the constructor are the default size of every
cell, so a row of equal cards needs no per-call size; a size passed to
`next()` / `place()` overrides it for that one cell:

```python
row = Stack(
    direction="horizontal", gap=Pt(12), left=Pt(48), top=Pt(400), width=Pt(200), height=Pt(120)
)
row.place(card_a)
row.place(card_b)
row.place(card_c, width=Pt(320))  # this one is wider
```

A stack needs a width and a height from one place or the other;
`next()` raises `TypeError` naming the one that is missing.

## Slide recipes

Opinionated parameterized slide constructors. Each takes the host
`Presentation`, recipe-specific kwargs, an optional `DesignTokens`,
and an optional `transition=` name:

```python
from power_pptx.design.recipes import (
    title_slide,
    bullet_slide,
    kpi_slide,
    quote_slide,
    image_hero_slide,
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
        {"label": "ARR", "value": "$182M", "delta": +0.27},
        {"label": "NDR", "value": "131%", "delta": +0.03},
        {"label": "CAC payback", "value": "8 mo", "delta": -0.10},
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
    image="hero.jpg",  # path or binary file-like
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

### Recipes that size themselves or refuse

`table_slide`, `code_slide`, `timeline_slide`, `comparison_slide` and
`figure_slide` take content of unpredictable size, so they measure it
before placing it and either fit it on the slide (4:3 or 16:9) or raise a
`ValueError` saying what to change. A rejected call adds no slide to the
deck.

```python
from power_pptx.design.recipes import (
    code_slide,
    figure_slide,
    table_slide,
    timeline_slide,
)

table_slide(
    prs,
    title="Regional results",
    columns=["Region", "Revenue", "Growth", "Margin"],
    rows=rows,  # up to ~27 data rows on one slide (one fewer with totals)
    widths=[0.4, 0.2],  # fewer widths than columns: the rest split what's left
    aligns=["left", "right", "right", "right"],
    totals={"label": "Total", "values": ["$660M", "", "75%"]},  # label + up to n-1 values
    tokens=tokens,
)

code_slide(prs, title="Retry loop", code=snippet, language="python", tokens=tokens)

timeline_slide(
    prs,
    title="Roadmap",
    milestones=[{"date": "Q1", "label": "Kickoff", "done": True}, {"date": "Q2", "label": "Beta"}],
    tokens=tokens,
)

figure_slide(prs, title="Architecture", figure="<svg ...>...</svg>")  # inline SVG
```

- **`table_slide`** — `widths` may name fewer columns than the table has
  (fractions or `Length`s); the named columns keep exactly that width and
  the rest share the remainder, and widths that leave nothing for them
  raise. `totals["values"]` takes at most one value fewer than there are
  columns (column 0 holds the label); more raise. When rows are too many
  for their text, the cell margins tighten first, then the font shrinks a
  point at a time (floor 9 pt); past that it raises and says how many data
  rows fit, so split the table. It assumes single-line cells: a cell that
  wraps makes its row taller than that check can know.
- **`code_slide`** — set in `Consolas` (one family name; OOXML does not
  accept a CSS font stack) at 14 pt, shrunk until the code, wrapped lines
  included, fits the panel (floor 9 pt, about 32 lines); beyond that it
  raises, so split the snippet. Tabs become four spaces. Text colour is
  chosen to read on the panel, including the dark default used without
  tokens.
- **`timeline_slide`** — every box stays inside the slide margins and
  clear of the rail; the rail is inset by half a label so the end labels
  line up with the margins. The deck's body size is shrunk (floor 9 pt)
  until every date and label fits its box. Past about 21 milestones on a
  4:3 slide (29 on 16:9) the boxes would be under 0.7 in wide, so it
  raises and tells you how many fit: split the roadmap.
- **`comparison_slide`** — the two column headings sit in bands a fixed
  0.6 in tall, so they share one size: the deck's heading size, reduced
  (floor 9 pt) until both fit their band.
- **`figure_slide`** — an inline SVG string (or bytes) is embedded;
  rasterising its PNG companion needs `cairosvg`, otherwise
  `CairoSvgUnavailable` is raised. `chart_slide` plots categories against
  values (`line`, `line_markers`, `bar`, `column`, `pie`, `doughnut`,
  `area`); for an XY scatter build the chart with `XyChartData`.

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
    left=Inches(1),
    top=Inches(1),
    width=Inches(2.5),
    height=Inches(1.9),
    label="ARR",
    value="$182M",
    delta={"delta": +0.27},
    tokens=tokens,
)
# kpi.card / kpi.value_box / kpi.label_box / kpi.delta_box are
# accessible for further per-deck tweaks.

bar = add_progress_bar(
    slide,
    left=Inches(1),
    top=Inches(3),
    width=Inches(6),
    height=Inches(0.3),
    fraction=0.42,  # 0..1 — clamped if you go over
    tokens=tokens,
    fill_color="#4F9DFF",  # optional override
)
# bar.track / bar.fill — animate or restyle either independently.
```

All shape-level components tag their stacked shapes with
`lint_group` so the linter doesn't flag the intentional overlap
(label-on-card, fill-on-track) as a collision.

The cards lay their insides out from their own size, and raise a
`ValueError` naming the size needed when the content cannot fit (nothing
is added to the slide):

- **`add_kpi_card`** derives the value / label / delta rows from
  `height`. At the default 1.9 in they are exactly the `kpi_slide` rows; a
  taller card centres them and a shorter one squeezes them, down to a
  minimum of about 1.3 in with the default type (more with large token
  sizes) — below that the rows would hang under the card. The delta row is
  reserved even when no delta is shown, so the cards of a strip keep their
  values aligned.
- **`add_article_card`** sizes its type for the card, not the deck: the
  title is at most 16 pt and the blurb at most 11 pt whatever the
  tokens' `heading` / `body` sizes are. A title that needs more than two
  lines shrinks (to 12 pt) and its box grows, with the blurb placed
  underneath; a long blurb shrinks (to 9 pt) to its box. A card too short
  for the title, a line of blurb and the CTA, or too narrow for text,
  raises.

Other components in the same module:

```python
from power_pptx import (
    add_gauge,  # progress bar with optional target tick
    add_status_pill,  # coloured pill + centred label, e.g. "LIVE"
    add_stat_strip,  # n KPI tiles laid out across a strip with gutter
    add_article_card,  # title + blurb + optional CTA pill
)

add_gauge(
    slide,
    left=Inches(1),
    top=Inches(2),
    width=Inches(4),
    height=Inches(0.3),
    fraction=0.62,
    target=0.80,
    tokens=tokens,
)

add_stat_strip(
    slide,
    left=Inches(0.5),
    top=Inches(1.5),
    width=Inches(12),
    height=Inches(1.9),
    items=[
        {"label": "ARR", "value": "$182M"},
        {"label": "NDR", "value": "131%", "delta": +0.03},
        {"label": "CAC payback", "value": "8 mo"},
    ],
    tokens=tokens,
)
```

## Ring diagrams

`power_pptx.diagrams.hub_and_spoke` and `cycle` (see
`geometry-and-arrows.md` for the whole family) put their nodes on a ring
that touches the edge of the `BBox`'s shorter side. The nodes keep their
default size (hub 0.25 and spokes 0.2 of that side; cycle cards 0.22) for
up to about eight of them; beyond that the diameters shrink together,
keeping their proportions, until no two nodes — and no spoke and the hub —
overlap and the arrows have room to show. Labels are fitted to the text
area an ellipse really has, so a small node gets a small font rather than
a word broken in the middle.

These diagrams declare only the overlaps they mean — each arrow with the
shapes it joins, via `allow_overlap_with` — instead of tagging everything
as one `lint_group`, so `slide.lint()` reports two spokes or cards that
really collide. Keep a ring to roughly 12 nodes at most: by then the
labels are down to 8–10 pt and short words work best.

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
    title_slide,
    bullet_slide,
    kpi_slide,
    quote_slide,
)

tokens = DesignTokens.from_dict(
    {
        "palette": {
            "primary": "#4F9DFF",
            "neutral": "#1F2937",
            "positive": "#10B981",
            "negative": "#EF4444",
            "on_primary": "#FFFFFF",
        },
        "typography": {
            # Recipes look up "heading" and "body". Floats = points, ints = EMU.
            "heading": {"family": "Inter", "size": 44.0, "bold": True},
            "body": {"family": "Inter", "size": 18.0},
        },
        "shadows": {"card": {"blur": 18.0, "distance": 4.0, "alpha": 0.18}},
    }
)

prs = Presentation()
title_slide(prs, title="Q4 Review", subtitle="April 2026", tokens=tokens, transition="morph")
kpi_slide(
    prs,
    title="Run-rate metrics",
    kpis=[
        {"label": "ARR", "value": "$182M", "delta": +0.27},
        {"label": "NDR", "value": "131%", "delta": +0.03},
    ],
    tokens=tokens,
)
bullet_slide(
    prs,
    title="Customer impact",
    bullets=[
        "Two flagship customers shipped this week.",
        "NPS improved 8 points QoQ.",
    ],
    tokens=tokens,
)
quote_slide(
    prs,
    quote="The new dashboards saved my team a week per sprint.",
    attribution="Director of Eng",
    tokens=tokens,
)

prs.save("q4-review.pptx")
```
