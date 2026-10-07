# Composition: from_spec, import_slide, apply_template (Phase 2 + 7)

The `power_pptx.compose` package collects entry points for higher-level
authoring and cross-presentation operations.

## JSON authoring with `from_spec`

The single entry point for generator scripts (LLM or otherwise). The
spec dict is validated for known keys and value shapes before
construction (no JSON Schema is involved):

```python
from power_pptx.compose import from_spec

prs = from_spec(
    {
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
                    {"label": "NDR", "value": "131%", "delta": +0.03},
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
        "lint": "raise",  # fail loudly on bad output
    }
)

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
  `"overrides": {...}` to layer brand-specific tweaks on top). The
  presets are `corporate_navy`, `modern_dark`, `modern_light` and
  `vibrant`.
- A YAML brand file: `{"yaml": "brand.yml"}` (it takes `"overrides"`
  too).
- An inline dict matching `DesignTokens.from_dict` (palette,
  typography, radii, shadows, spacings). Lengths follow the token unit
  rule — a float is points, a bare int is EMU, and a size that small
  is rejected; see "Design tokens" in `design.md`.
- A `DesignTokens` instance — handy when the same token bag is
  reused between imperative recipe calls and `from_spec`.
- `None` (omitted) — falls through to the placeholder layouts on
  the host template; the recipe slides render with their built-in
  defaults.

A `preset` or `yaml` spec takes nothing but `"overrides"` beside it:
`{"preset": "modern_light", "palette": {...}}` raises (put the palette
under `"overrides"`), and so do `preset` together with `yaml`, and
`overrides` with no base. `"theme"` is an alias for `"tokens"` when
`"tokens"` is absent, with the same shapes — `{"theme": {"palette":
"modern_blue"}}` is not one of them.

A slide may carry its own `tokens` (the same shapes), which replace the
deck-level ones **for that slide**; `"tokens": null` opts the slide out.
A slide-level `tokens` also upgrades `"title"` / `"bullets"` in a deck
that has none. Placeholder layouts other than those two take their look
from the template and reject a non-null slide-level `tokens`.

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

### What `from_spec` validates

Everything below is checked before the slide is built and raises a
`ValueError` that names the slide (`slides[3]`) or the field
(`slides[3].kpis`), so a fault in a 40-slide spec is findable:

- **Unknown keys are rejected on every layout**, with a did-you-mean
  hint (`subtitlz` → `subtitle`). That includes the placeholder layouts,
  which used to drop what they did not read. What they read, besides
  `title`, `transition` and `shapes`:

  | Layout | Also reads |
  | --- | --- |
  | `title` | `subtitle` |
  | `bullets` | `bullets` |
  | `section` | `subtitle` or `text` |
  | `two_column`, `comparison_layout` | `left` / `right` (or `content_left` / `content_right`) |
  | `kpi_grid` | `kpis` — cards are 2.2" wide at most and share the width when there are too many for one row |
  | `picture` | `image` (inserted into the picture placeholder) and `caption` |
  | `title_only`, `blank`, `caption`, a template's own layout name | nothing more |

  A template's own layout name (`"Title Slide"`) fills only the title;
  the alias (`"title"`) also fills the subtitle.
- **Values have the right type.** Each slide must be a mapping and
  `layout` a string. Text fields (`title`, `subtitle`, `text`, `left`,
  `right`, `caption`, `quote`, `attribution`, `code`, `chart_type`, …)
  must be strings — YAML reads `subtitle: 2026` as a number, so quote
  it. List fields must be lists of the right thing: `kpis`, `milestones`,
  `series` and the rows of a `comparison` are lists of mappings; the
  `rows` of a `table` are lists of lists; `bullets`, `categories`,
  `columns`, `widths`, `aligns` and each series' `values` are lists.
  `image` is a file path or a binary file, `progress` a
  `[current, total]` pair and `totals` a mapping.
- **`null` is not a value.** An optional field given as null (YAML's
  `bullets:` with nothing after it) is treated as not given; a required
  key given as null (`title:`) is reported as missing.
- **A bare string is not a one-item list.** `bullets: "one line"` raises
  rather than being iterated per character (it used to render as a
  bullet per letter).

### Variables

`vars` (and the `vars=` argument) fill `{{name}}` — or `{{a.b}}` into
nested mappings — in every string of the spec; an unknown name raises
`KeyError`. **A slide's `code` field is the exception:** it is shown
exactly as written, so a `code` slide can display a Jinja, Handlebars or
Go template (`Hello {{ user.name }}!`) without being treated as a
variable reference. Other fields have no escape syntax.

## Free-standing shapes on a spec slide

Layouts and recipes place their own shapes. When you need something a
layout doesn't provide, a slide entry may carry a `shapes` list, applied
*after* the layout runs:

```python
{
    "layout": "blank",
    "shapes": [
        {
            "name": "card",
            "shape": "rounded_rectangle",
            "left": 1,
            "top": 1,
            "width": 4,
            "height": 2,
            "layer": "card",
        },
        {
            "name": "badge",
            "shape": "oval",
            "text": "NEW",
            "left": 4.4,
            "top": 0.7,
            "width": 1.2,
            "height": 0.8,
            "layer_above": "card",
        },
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

Both operations are methods of the presentation being changed,
`Presentation.import_slide()` and `Presentation.apply_template()`. (The
functions of the same names in `power_pptx.compose` are the lower-level
entry points: they take the underlying parts, with the arguments in a
different order, and are not what you want from a script.)

```python
from power_pptx import Presentation
```

### Importing a slide

```python
src = Presentation("source.pptx")
dst = Presentation("destination.pptx")

# Clone src.slides[3] into dst, including its layout reference.
dst.import_slide(src.slides[3], merge_master="dedupe")
```

Image-rename collisions, layout references, and master/theme parts are
handled automatically. Two strategies for masters:

- `merge_master="dedupe"` (default-ish, recommended) reuses an
  equivalent master in the destination if one matches.
- `merge_master="clone"` always brings a fresh copy of the source
  master alongside.

Images the destination already holds (identical bytes) are reused, not
stored twice. A hyperlink that jumps to another slide of the *source*
deck cannot be kept, because that slide is not coming along: the jump is
removed from the copy and one `UserWarning` says how many were dropped.
A jump to the imported slide itself is kept, and so are jumps to other
slides when you copy a slide within one deck.

### Applying a template

```python
dst.apply_template("brand-template.potx")
```

Re-points every slide's layout/master/theme at masters from the
`.potx` (or `.pptx`). Slide content is preserved. Layout matching:
name → type → first layout. Unreferenced old masters / layouts /
themes are dropped from the saved package. Pictures on the template's
masters, layouts and theme (logos, background images) come along, and the
deck is usable straight away: `dst.slide_layouts`, `dst.slides.add_slide(...)`
and a further `save()` all work without a save-and-reopen. A template
with no slide layouts at all leaves the deck unchanged and emits a
`UserWarning`.

## End-to-end pipeline

A typical "we have a master deck and need to bolt on N report slides"
script:

```python
from power_pptx import Presentation
from power_pptx.compose import from_spec

# 1. Generate the body slides from data
body = from_spec(
    {
        "slides": [
            {"layout": "kpi_grid", "title": team["name"], "kpis": team["kpis"]} for team in teams
        ],
    }
)

# 2. Open the cover deck and append the body slides
deck = Presentation("cover.pptx")
for slide in body.slides:
    deck.import_slide(slide, merge_master="dedupe")

# 3. Re-skin everything against the latest brand template
deck.apply_template("brand-2026.potx")

# 4. Lint and save (or set prs.lint_on_save = "raise" and just save)
from power_pptx.exc import LintError

errors = []
for slide in deck.slides:
    slide.lint().auto_fix()
    errors.extend(i for i in slide.lint().issues if i.severity.value == "error")
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
