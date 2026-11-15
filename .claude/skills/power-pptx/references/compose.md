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

Unknown fields are rejected for both legacy and recipe layouts. For example,
`{"layout": "title", "subtitel": "..."}` raises a `ValueError` locating
`slides[0]` and suggesting `subtitle`; `bullets` layouts similarly validate
the `bullets` field. Non-mapping slide entries and non-string layout values
raise contextual errors. Named standard layouts such as `"Title Slide"`
accept and populate the same fields as their aliases.

Values are type-checked too, before anything is built — nothing is
silently dropped or mangled:

- Text fields (`title`, `subtitle`, `quote`, `code`, `caption`, …) must
  be strings: write `"2026"`, not `2026`.
- `bullets` is a list. Each item is a string or `{"text": ..., "level": n}`
  (0–8). The placeholder `bullets` / `two_column` / `comparison_layout`
  layouts indent by level; the token-styled recipe draws a flat list and
  rejects a nested level. A bare string is an error, not one bullet per
  character.
- `kpis`, `milestones`, chart `series` and comparison `rows` are lists of
  mappings; table `rows` are lists of cell values, no longer than
  `columns` (a longer row is an error rather than a truncated one).
- `progress` is `[current, total]`; `chart_palette` is a built-in palette
  name (`"modern"`, …) or a list of colours; a typo is reported.
- A key the layout cannot place is an error: a `title` on a `blank` slide
  (or on a slide with no `layout`, which means blank) would vanish, so it
  raises. `null` is the same as leaving a key out.

`comparison_layout` takes `left_heading` / `right_heading` as well as the
`left` / `right` content (the template's Comparison layout has a heading
and a content placeholder on each side).

### Errors

Everything wrong with a spec's content raises
`power_pptx.compose.SpecError` — a `ValueError` subclass, so existing
`except ValueError` handlers still work. The message starts with the
location of the offending value and `.path` carries it on its own, which
makes the error easy to hand back to whatever wrote the spec:

```python
from power_pptx.compose import SpecError, from_spec

try:
    from_spec(spec)
except SpecError as exc:
    print(exc.path)   # "slides[2].kpis[0]"
    print(exc)        # "slides[2].kpis[0]: expected a mapping like {...}; got str 'ARR'"
```

Missing files, templates that are not presentations and failures inside a
recipe are reported the same way, chained from the original exception. A
missing optional dependency (Playwright, Kaleido) is still an `ImportError`.

### Tokens

`tokens` accepts:

- A preset by name: `{"preset": "modern_light"}`.
- A YAML brand file: `{"yaml": "brand.yml"}`.
- An inline dict matching `DesignTokens.from_dict` (palette,
  typography, radii, shadows, spacings).
- Any mix of those plus `"overrides"` (dotted paths or nested dicts).
  They layer in a fixed order — preset, then the YAML file, then the
  inline sections, then `overrides` — so `{"preset": "modern_light",
  "palette": {"primary": "#FF0000"}}` really does change the primary
  colour, and inline typography/shadow entries change only the fields
  they name.
- A `DesignTokens` instance — handy when the same token bag is
  reused between imperative recipe calls and `from_spec`.
- `None` (omitted) — falls through to the placeholder layouts on
  the host template; the recipe slides render with their built-in
  defaults.

Any other key (`"palete"`, `"fonts"`) is rejected with a did-you-mean
hint. Bare numbers in length fields are points (`"size": 36` is 36pt);
see `design.md`.

A recipe slide may carry its own `tokens`, in the same forms. A `preset`
or `yaml` there replaces the deck's tokens for that slide; inline sections
and `overrides` are layered over the deck's. `"tokens": null` opts the
slide out. Placeholder layouts take their look from the template and
reject a slide-level `tokens`.

`slide_size` is optional. With no setting, the bundled template's
4:3 dimensions (10" × 7.5") are used. The shorthand resolves
through `_SLIDE_SIZE_PRESETS`; pass an inches pair like
`(13.333, 7.5)` for any custom dimension (1–56 inches each). Resizing
rescales the template's masters and layouts too, so placeholder layouts
fill the new width instead of keeping their 4:3 positions.

### Variables

`"vars": {"company": "ACME"}` (or `from_spec(spec, vars=...)`) turns on
`{{company}}` substitution in every string of the spec; `{{a.b}}` walks
nested mappings and an unknown name raises `SpecError`. Without `vars`
nothing is substituted, so code samples keep their braces. When a deck
uses variables *and* shows template syntax:

- write `\{{` (in JSON, `"\\{{"`) for a literal `{{`, or
- set `"interpolate": false` on the slide — or at the top level for the
  whole spec — to leave its strings exactly as written:

```python
{"layout": "code", "title": "CI step", "interpolate": False,
 "code": "run: echo ${{ github.sha }}"}
```

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

## Specs from a model or a user: `safe=True`

A spec is data, and when you did not write it — an LLM produced it, a user
uploaded it — build it in safe mode:

```python
prs = from_spec(spec, safe=True, base_dir="/srv/decks/job-42")
# from_yaml("deck.yml", safe=True, base_dir=...) works the same way.
```

- Every file the spec names — `template`, a token `yaml`, `image`, a
  `figure` path — must resolve inside `base_dir`, after following
  symlinks. `../` and absolute paths elsewhere raise `SpecError`.
  `base_dir` defaults to the current working directory; relative paths
  are resolved against it whether or not `safe` is set.
- HTML and Plotly figures are captured with `allow_network=False`: the
  page may load `data:` URLs and its own document directory, nothing
  else. A figure that asks for more fails with a `SpecError` naming the
  blocked URLs instead of fetching them. A safe spec cannot set
  `"allow_network": true`.

Independently of `safe`, a spec can never choose the browser executable:
`browser_path` in `html_options` / `plotly_options` raises. Set
`POWER_PPTX_CHROMIUM`, or pass `browser_path=` to the Python functions
(`add_html_figure`, `from_html`, …), which keep it.

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
did-you-mean hint rather than silently ignored. Geometry is checked:
sizes cannot be negative, `left` / `top` may bleed off the slide but
nothing may exceed PowerPoint's 56-inch limit, and `NaN` / infinity
are rejected — the error names the shape.

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
new_slide = import_slide(dst, src.slides[3], merge_master="dedupe")
```

The destination comes first; the slide is appended to it and returned.
`dst.import_slide(src.slides[3])` is the same operation as a method.

Image-rename collisions, layout references, and master/theme parts are
handled automatically. A picture or media file the destination already
holds is reused rather than copied again. Two strategies for masters:

- `merge_master="dedupe"` (the default, recommended) reuses an
  equivalent master in the destination if one matches.
- `merge_master="clone"` always brings a fresh copy of the source
  master alongside.

Any other value raises `ValueError`.

Only the slide you name is imported. A "jump to slide" link on it
(`shape.click_action.target_slide`) is kept when its target is already in
the destination — a same-deck import, or a slide imported earlier into
the same `Presentation` object — and removed otherwise, so import a
link's target before the slide that links to it.

### Applying a template

```python
apply_template(dst, "brand-template.potx")
```

Re-points every slide's layout/master/theme at masters from the
`.potx` (or `.pptx`). The template can be a path, a file-like object or
an open `Presentation`; `dst.apply_template(...)` is the method form.
Slide content is preserved. Layout matching: name → type → first
layout. The template's masters, layouts, themes and their pictures are
copied in; the old masters / layouts / themes are dropped from the
saved package.

`SlideMaster` / `SlideLayout` objects fetched *before* the call belong
to the replaced masters — read `dst.slide_layouts` again afterwards.
A template with no slide master (or no layouts, when the deck has
slides) raises `ValueError` and leaves the deck untouched.

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
