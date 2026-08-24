# Composition: from_spec, import_slide, apply_template (Phase 2 + 7)

The `power_pptx.compose` package collects entry points for higher-level
authoring and cross-presentation operations.

## JSON authoring with `from_spec`

The single entry point for generator scripts (LLM or otherwise). The
spec dict is validated for known keys and value shapes before
construction (no JSON Schema is involved):

```python
from power_pptx.compose import from_spec

prs = from_spec({
    # 16:9 widescreen — the modern default. Other shorthands:
    # "4:3", "16:10", "a4", "letter". Or pass an (w, h) pair / dict
    # in inches.
    "slide_size": "16:9",
    # Brand tokens. Inline dict / preset / yaml / DesignTokens — all
    # supported. ``"theme"`` is a friendly alias when ``"tokens"`` is
    # absent.
    "tokens": {"preset": "modern_light"},
    "slides": [
        {
            "layout": "title",
            "title": "Q4 Review",
            "subtitle": "April 2026",
            "transition": "morph",
        },
        {
            "layout": "kpi",
            "title": "Run-rate metrics",
            "kpis": [
                {"label": "ARR", "value": "$182M", "delta": +0.27},
                {"label": "NDR", "value": "131%",  "delta": +0.03},
            ],
        },
        {
            "layout": "bullets",
            "title": "Customer impact",
            "bullets": [
                "Two flagship customers shipped this week.",
                "NPS improved 8 points QoQ.",
            ],
        },
    ],
    "lint": "raise",                       # fail loudly on bad output
})

prs.save("q4-review.pptx")
```

When `tokens` is present, the legacy alias names `"title"` and
`"bullets"` are silently upgraded to the styled recipes
(`"title_recipe"` / `"bullets_recipe"`); this used to be silent and
strand the deck on default placeholder styling.  Pass an explicit
recipe layout name (e.g. `"kpi"`, `"chart"`, `"table"`, `"quote"`)
to skip the alias step and reach the styled recipe directly.

An unrecognized `"layout"` name raises `ValueError` (with the closest
valid layout suggested) rather than silently producing a blank slide —
so a typo like `"titel"` fails loudly. Use `"layout": "blank"`
explicitly when you actually want a blank slide.

`tokens` accepts five shapes:

- A preset by name: `{"preset": "modern_light"}` (optionally with
  `"overrides": {...}` to layer brand-specific tweaks on top).
- A YAML brand file: `{"yaml": "brand.yml"}`.
- An inline dict matching `DesignTokens.from_dict` (palette,
  typography, radii, shadows, spacings).
- A `DesignTokens` instance — handy when the same token bag is
  reused between imperative recipe calls and `from_spec`.
- `None` (omitted) — falls through to the placeholder layouts on
  the host template; the recipe slides render with their built-in
  defaults.

`slide_size` is optional. With no setting, the bundled template's
4:3 dimensions (10" × 7.5") are used. The shorthand resolves
through `_SLIDE_SIZE_PRESETS`; pass an inches pair like
`(13.333, 7.5)` for any custom dimension.

Layout names map either to Phase-9 design recipes (where supplied) or
to a small built-in set of layouts using the host presentation's
master.

The `lint` field accepts `"off"`, `"warn"`, or `"raise"`:

- ``"off"`` (default) — no lint pass.
- ``"warn"`` — log every issue through the stdlib ``logging`` module.
- ``"raise"`` — raise ``power_pptx.exc.LintError`` if any error-severity
  issue is found.

`from_spec` runs the lint pass internally; outside of `from_spec`,
iterate the slides yourself (see `lint.md`).

## Free-standing shapes on a spec slide

Layouts and recipes place their own shapes. When you need something a
layout doesn't provide, a slide entry may carry a `shapes` list, applied
*after* the layout runs:

```python
{
    "layout": "blank",
    "shapes": [
        {"name": "card", "shape": "rounded_rectangle",
         "left": 1, "top": 1, "width": 4, "height": 2,
         "layer": "card"},
        {"name": "badge", "shape": "oval", "text": "NEW",
         "left": 4.4, "top": 0.7, "width": 1.2, "height": 0.8,
         "layer_above": "card"},
    ],
}
```

Keys: `left` / `top` / `width` / `height` (required; inches, or a
`Length`), `name`, `shape` (an `MSO_SHAPE` member name,
case-insensitive — default `"textbox"`), `text`, and the four
overlap-intent fields below. Unknown keys are rejected with a
did-you-mean hint rather than silently ignored.

This is deliberately minimal — geometry, type, text, intent. It is not a
drawing DSL; reach for the Python API when you need fills, effects, or
anything structural.

### Declaring intentional overlaps in a spec

An LLM writing a spec can declare *at generation time* that an overlap
is deliberate, so the built deck lints clean without a manual pass. All
three mechanisms from `lint.md` are spec-level fields:

```python
{"name": "badge", ..., "lint_group": "kpi-1"}          # n-ary tag
{"name": "badge", ..., "allow_overlap_with": "card"}   # one pair
{"name": "badge", ..., "allow_overlap_with": ["card", "rule"]}
{"name": "card",  ..., "layer": "card"}                # asserts z-order
{"name": "badge", ..., "layer_above": "card"}
```

`allow_overlap_with` names other shapes by their spec `name`, not by
shape id — ids don't exist until the deck is built. Resolution happens
after every shape on the slide exists, so a **forward reference works**:
naming a shape defined later in the same list is fine.

Names must be unique within a slide, and a reference must stay within
its slide — an allowance is keyed on shape id, and ids are only unique
per slide. Both mistakes raise a `ValueError` locating the bad entry as
`slides[i].shapes[j]`.

## Cross-presentation operations

```python
from power_pptx import Presentation
from power_pptx.compose import import_slide, apply_template
```

### Importing a slide

```python
src = Presentation("source.pptx")
dst = Presentation("destination.pptx")

# Clone src.slides[3] into dst, including its layout reference.
import_slide(dst, src.slides[3], merge_master="dedupe")
```

Image-rename collisions, layout references, and master/theme parts are
handled automatically. Two strategies for masters:

- `merge_master="dedupe"` (default-ish, recommended) reuses an
  equivalent master in the destination if one matches.
- `merge_master="clone"` always brings a fresh copy of the source
  master alongside.

### Applying a template

```python
apply_template(dst, "brand-template.potx")
```

Re-points every slide's layout/master/theme at masters from the
`.potx` (or `.pptx`). Slide content is preserved. Layout matching:
name → type → first layout. Unreferenced old masters / layouts /
themes are dropped from the saved package.

## End-to-end pipeline

A typical "we have a master deck and need to bolt on N report slides"
script:

```python
from power_pptx import Presentation
from power_pptx.compose import import_slide, apply_template, from_spec

# 1. Generate the body slides from data
body = from_spec({
    "slides": [
        {"layout": "kpi_grid", "title": team["name"], "kpis": team["kpis"]}
        for team in teams
    ],
})

# 2. Open the cover deck and append the body slides
deck = Presentation("cover.pptx")
for slide in body.slides:
    import_slide(deck, slide, merge_master="dedupe")

# 3. Re-skin everything against the latest brand template
apply_template(deck, "brand-2026.potx")

# 4. Lint and save (or set prs.lint_on_save = "raise" and just save)
from power_pptx.exc import LintError

errors = []
for slide in deck.slides:
    slide.lint().auto_fix()
    errors.extend(
        i for i in slide.lint().issues if i.severity.value == "error"
    )
if errors:
    raise LintError("; ".join(str(e) for e in errors))

deck.save("final.pptx")
```

## When NOT to use `from_spec`

`from_spec` is intentionally bounded — small built-in layouts plus the
recipes from `power_pptx.design.recipes`. If you need something the recipe
library doesn't ship, drop down to direct shape construction (or write
a recipe and contribute it back). Don't try to express arbitrary
geometry through the spec dict.
