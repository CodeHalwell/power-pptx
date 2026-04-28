# Composition: from_spec, import_slide, apply_template (Phase 2 + 7)

The `pptx.compose` package collects entry points for higher-level
authoring and cross-presentation operations.

## JSON authoring with `from_spec`

The single entry point for generator scripts (LLM or otherwise). The
spec dict is validated for known keys and value shapes before
construction (no JSON Schema is involved):

```python
from pptx.compose import from_spec

prs = from_spec({
    "theme": {"palette": "modern_blue", "fonts": "inter"},
    "slides": [
        {
            "layout": "title",
            "title": "Q4 Review",
            "subtitle": "April 2026",
            "transition": "morph",
        },
        {
            "layout": "kpi_grid",
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

Layout names map either to Phase-9 design recipes (where supplied) or
to a small built-in set of layouts using the host presentation's
master.

The `lint` field accepts `"off"`, `"warn"`, or `"raise"`:

- ``"off"`` (default) — no lint pass.
- ``"warn"`` — log every issue through the stdlib ``logging`` module.
- ``"raise"`` — raise ``pptx.exc.LintError`` if any error-severity
  issue is found.

`from_spec` runs the lint pass internally; outside of `from_spec`,
iterate the slides yourself (see `lint.md`).

## Cross-presentation operations

```python
from pptx import Presentation
from pptx.compose import import_slide, apply_template
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
from pptx import Presentation
from pptx.compose import import_slide, apply_template, from_spec

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

# 4. Lint and save (no Presentation-level lint hook in 1.1; iterate)
from pptx.exc import LintError

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
recipes from `pptx.design.recipes`. If you need something the recipe
library doesn't ship, drop down to direct shape construction (or write
a recipe and contribute it back). Don't try to express arbitrary
geometry through the spec dict.
