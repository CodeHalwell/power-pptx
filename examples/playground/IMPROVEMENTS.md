# Improvement notes from building the playground examples

Logged while exploring the library to build a wider set of example decks.
File is appended to as I find things; nothing in here is a planned commit
to the library — these are observations the maintainers can triage.

> **Status (v2.7.0):** Every item in this file has been addressed —
> see ``HISTORY.rst`` for the per-item release notes.  Reproductions
> and rationale are preserved here as the "why" trail behind those
> changes.

## Format

Each entry: short title, severity (info / nit / bug), and a code-ish
description plus suggested fix.

---

## 1. `DesignTokens.palette[key]` returns `RGBColor`, not a hex string

**Severity:** nit (docs)

The `references/design.md` examples (and most snippets in `effects.md`)
read tokens with `RGBColor.from_hex(P["primary"])`, which crashes
because `P["primary"]` is already an `RGBColor`. The right call is just
`P["primary"]`. The fork's setters accept `RGBColor`, hex strings, and
tuples interchangeably so this isn't a runtime bug — but the docs
should make the return type unambiguous, ideally with a one-line
example near the top of `references/design.md`:

```python
# DesignTokens.palette[k] -> RGBColor (not a hex string)
shape.fill.fore_color.rgb = tokens.palette["primary"]
```

Today you only find out by reading `src/pptx/design/tokens.py` or by
hitting the `AttributeError` (`'RGBColor' object has no attribute
'startswith'`) at runtime.

---

## 2. `Chart.apply_palette` silently has no visible effect on LINE charts

**Severity:** bug

`apply_palette` only writes `series.format.fill.fore_color.rgb`, which
translates to `c:spPr/a:solidFill`. For a `XL_CHART_TYPE.LINE` chart
the visible color is the *line stroke* (`c:spPr/a:ln/a:solidFill`), so
the call appears to do nothing and the renderer falls back to the
default Office palette. Reproduce:

```python
shape = slide.shapes.add_chart(
    XL_CHART_TYPE.LINE, Inches(1), Inches(1), Inches(8), Inches(4), data
)
shape.chart.apply_palette(["#E04E39", "#5C677D"])
# In LibreOffice / PowerPoint the lines render blue / orange — the
# default Office palette — because only spPr/solidFill was set.
```

The same problem applies to `XL_CHART_TYPE.LINE_MARKERS`,
`LINE_STACKED`, `LINE_STACKED_100`, `LINE_MARKERS_STACKED`, etc.

Suggested fix: in `Chart.apply_palette`, also set
`series.format.line.color.rgb = colors[idx % len(colors)]` (and maybe
`series.format.line.width` if unset), or special-case the line family
to set line stroke instead of/as well as fill. A minimal workaround:

```python
for idx, series in enumerate(chart.series):
    series.format.line.color.rgb = colors[idx]
```

…but this should not be on the caller.

A related point: the same color-likes that work for fills should work
on `series.format.line.color.rgb`, and they do, but the call requires
a *concrete* color rather than letting `apply_palette` handle it.

---

## 3. Default text alignment on a fresh textbox renders as centered in LibreOffice

**Severity:** info (cross-renderer)

A textbox created via `slide.shapes.add_textbox(...)` produces a
paragraph with no `a:pPr/@algn` attribute. PowerPoint renders that as
left-aligned (the OOXML default), but LibreOffice (which is what
`render_thumbnails` shells out to) renders it as centered. The
practical impact: any script that thumbnails via LibreOffice and
relies on the implicit default sees a centered render that doesn't
match how PowerPoint will show it.

Workarounds:
1. Set `paragraph.alignment = PP_ALIGN.LEFT` explicitly on every
   paragraph — verbose but deterministic.
2. Update the design recipes / docs to call out this footgun and set
   an explicit alignment in every recipe.

If `Presentation.render_thumbnails` is documented as the canonical
preview path, it would be worth either patching the alignment in
known-default cases or adding a note in `references/render.md` that
"thumbnails may differ slightly from PowerPoint for un-aligned text".

### 3a. Refinement: `wrap="none" + spAutoFit` (the textbox default) breaks placement under LibreOffice

A freshly added `slide.shapes.add_textbox(...)` ends up with
`<a:bodyPr wrap="none"><a:spAutoFit/></a:bodyPr>`. PowerPoint shrinks
the box around its anchor point and renders the text at the declared
`x`. LibreOffice apparently re-centers the shrunken box inside its
*original* declared width, so a kicker line declared at
`left=Inches(1.1), width=Inches(11)` ends up rendered in the middle
of the slide instead of near the left edge — even though `pPr/@algn`
is `"l"`.

The workaround in this directory is `tf.word_wrap = True` on every
textbox, which suppresses `spAutoFit` and keeps the declared geometry
intact. Worth either:

1. Defaulting `word_wrap = True` in `add_textbox(...)` (matches how
   90% of generated decks use it), or
2. Calling this out alongside the rendering note in #3.

---

## 4. `table.horz_banding = False` doesn't suppress the default-style banding

**Severity:** nit

`slide.shapes.add_table(...)` attaches a default `tableStyleId` ("Medium
Style 2 — Accent 1"). When you start setting per-cell fills on a few
rows, the *un-filled* rows still pick up the default style's alternating
band colors. The fix that *should* work — `table.horz_banding = False`
+ `table.first_row = False` — is silent: those toggles only mean "the
attached style shouldn't render bands", but the style's own banded-row
overlay still applies in LibreOffice (and PowerPoint may behave
similarly depending on which built-in style is attached).

The reliable workaround is to fill every cell explicitly (even the ones
you wanted to leave "default"). It would be nicer to have either:

- `Table.style = None` to detach the default style entirely, or
- `Table.clear_style()` that drops `tblPr/@tableStyleId`.

Either would let "I want to do all my own styling" be one line.

---

## 5. `XL_CHART_TYPE.XY_SCATTER` writes `scatterStyle="lineMarker"` instead of `"marker"`

**Severity:** info (subtle)

For markers-only scatter (`XL_CHART_TYPE.XY_SCATTER`), the xml writer
emits `<c:scatterStyle val="lineMarker"/>` and then *separately*
suppresses the line by writing
`<c:spPr><a:ln><a:noFill/></a:ln></c:spPr>` on each series. The two
together get the right visual result, but it's fragile: any caller
that does `series.format.line.color.rgb = ...` to recolor the series
also overwrites the `noFill` — and silently flips the chart to
"lines with markers". (This is what I hit when trying to brand-color
a scatter.)

It would be more robust to either:

1. Emit `<c:scatterStyle val="marker"/>` for `XY_SCATTER` so the
   chart type itself communicates "no lines", and the per-series ln
   override isn't load-bearing.
2. Or have a `series.color = ...` convenience that knows to update
   only the fill when the chart type is markers-only.

Today the foot-gun is that "color this scatter the brand colors" needs
to touch `series.format.fill.fore_color.rgb` only — touching line is
a quiet visual bug.

---

## 6. Emoji glyphs render as tofu under the LibreOffice thumbnail pipeline

**Severity:** info (rendering env, not library)

Decks generated with emoji (`"☕"`, `"📐"`, etc.) render correctly in
PowerPoint with the default Segoe UI Emoji fallback, but under the
documented `soffice + pdftoppm` thumbnail pipeline they come out as
empty-rectangle tofu. The skill's "review with a screenshot" loop is
therefore subtly broken for any deck that uses emoji.

Not a library bug — the rendering env just doesn't have an emoji
font. Worth noting in `references/render.md` as a known thumbnail
limitation, with a recommendation to use Unicode glyphs from the
shipped DejaVu families (`•`, `→`, `★`, `‹›`, `■`, etc.) when
generating decks meant to be thumbnail-reviewed on the same machine.

---

## 7. `fit_text` + `slide.lint()` missed an obvious title overflow

**Severity:** bug

Reproduction — a Blank-layout slide with a single textbox:

```python
head = slide.shapes.add_textbox(
    Inches(0.9), Inches(2.5), Inches(11.5), Inches(2.0),
)
tf = head.text_frame
tf.word_wrap = True
tf.text = "Ship the next deck before lunch."
tf.fit_text(font_family="DejaVu Serif", max_size=72, bold=True)
tf.paragraphs[0].font.color.rgb = some_color
```

`fit_text` settled on 72pt. The text wraps to two lines, each ~72pt
tall + descenders + line spacing → roughly 2.4 inches of visual
height — but the box is only 2.0 inches tall, so the second line
("before lunch.") spills below the box. Subsequent content (a
contact-row textbox positioned at top=4.6in) ends up sitting under
the overflowed second line.

`slide.lint()` returned **no issues** for that slide. Two things are
worth tightening:

1. `fit_text` should fail closed when even the smallest valid size
   overflows the box — currently it picked 72pt presumably because
   the un-wrapped one-line measurement fit, but the wrapped layout
   didn't.
2. `slide.lint()`'s `TextOverflow` heuristic should catch this case.
   The text actually IS overflowing; my own visual inspection saw it.
   If the lint is checking against `fit_text`'s baked size rather
   than measuring the wrapped layout, it's checking the wrong thing.

The 1.5x-of-text-frame-height threshold mentioned elsewhere in the
codebase may be too lenient when the *first* line already eats the
whole box.

---

## 8. `from_spec` documents a `theme` key that has no effect

**Severity:** bug (docs vs implementation drift)

The reference example in `compose.md` and the skill docs reads:

```python
prs = from_spec({
    "theme": {"palette": "modern_blue", "fonts": "inter"},
    "slides": [...],
})
```

`"theme"` is listed in `_VALID_TOP_KEYS` so the spec validates fine,
but `from_spec` only reads `spec.get("tokens")`. The `theme` key is
silently ignored — and the recipes therefore fall back to their
defaults, producing an un-styled deck without any error message. The
spec example as written shows no styling regardless of what palette /
fonts you put in `theme`.

Two fixes:

1. Drop `"theme"` from `_VALID_TOP_KEYS` or wire it up to either
   alias `"tokens"` or build a `DesignTokens` from `palette`/`fonts`
   sub-keys.
2. Fix the docs example to use `"tokens"`.

Related: `_resolve_tokens` requires a `Mapping`, so a raw
`DesignTokens` instance is rejected with `"'tokens' must be a
mapping"`. Either accept `DesignTokens` directly (the natural ergonomic
when reusing tokens between imperative + declarative call sites) or
add a docs note that you must round-trip through `.to_dict()` first.
(There is no `DesignTokens.to_dict()` today either, so the only way
to share tokens between imperative + `from_spec` paths is to keep a
plain dict around and call `DesignTokens.from_dict(...)` at every
imperative site.)

---

## 9. `from_spec` legacy layout names (`"title"`, `"bullets"`) silently bypass tokens

**Severity:** info

The dispatch table treats `"title_recipe"` / `"bullets_recipe"` / `"kpi"`
/ `"quote"` etc. as token-aware recipes. The shorter names
`"title"` / `"bullets"` are valid spec values but resolve to the
*placeholder* layouts on the host template — they don't go through
the recipes, so the token palette is silently ignored.

This is documented in the docstring (legacy vs recipe layouts) but
extremely easy to miss: the deck saves cleanly, lint passes, and the
user sees a default-styled slide.

Suggested fix: when `tokens` is present in the spec, route `"title"` →
`"title_recipe"` and `"bullets"` → `"bullets_recipe"` automatically, or
emit a warning when a legacy layout is used in a token-providing spec.

---

## 10. `from_spec` has no `slide_size` / aspect ratio field

**Severity:** nit

There's no spec field for slide dimensions. The default
`Presentation()` template is 4:3 (10" x 7.5"). Most modern decks are
16:9, so every spec-driven deck either looks 4:3 or requires post-
processing:

```python
prs = from_spec(spec)
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)
```

Worse: the recipes laid out their shapes against the *original* 10"
width, so resizing the slide afterwards leaves a wide unused right
margin (visible in 05_from_spec_declarative.pptx slide 2's KPI cards).
The honest fix is to ship a widescreen blank template inside
`power_pptx` and document `template:` as the right knob — or add a
`slide_size: "16:9"` shorthand.

---

## 11. Recipe layout collisions when the title wraps to two lines

**Severity:** bug

`title_slide`, `bullet_slide`, `kpi_slide` all reserve a fixed
height for the title region (looks like ~1.0–1.2in). When the title
text is long enough to wrap to a second line at the recipe's chosen
font size, the wrapped second line spills *below* the reserved
region and overlaps the body content. Reproduced cleanly in
`examples/playground/05_from_spec_declarative.pptx` slide 2
(title "Why declarative authoring" — 2 lines, overlaps the KPI cards)
and slide 3 (title "What `from_spec` ships out of the box" —
2 lines, overlaps the bullet list).

Additionally, `slide.lint()` did not flag this as a `ShapeCollision`
issue. The recipe-drawn title shape and the recipe-drawn body shape
are demonstrably overlapping in the rendered PDF.

Two fixes worth considering:

1. Make the recipe title region use `auto_size = TEXT_TO_FIT_SHAPE`
   so multi-line titles shrink to fit instead of growing past the
   reserved area.
2. Have `slide.lint()`'s `ShapeCollision` check measure the rendered
   text height (via Pillow font metrics) rather than the declared
   text-frame height — a 1.2in title box with 2.4in of text inside
   should be flagged as occupying 2.4in for collision purposes.

The same recipes also lay out the KPI value + label + delta with a
fixed line stack that doesn't account for label-wrap, so a long
KPI label like "Lines of code per slide" wraps onto a second line
and pushes the delta on top of it (visible in 05_from_spec slide 2).
