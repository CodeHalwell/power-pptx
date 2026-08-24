---
name: power-pptx
description: Build PowerPoint (.pptx) decks from Python with the power-pptx library — the actively-maintained fork of python-pptx. Use this skill whenever the user wants to generate, mutate, lint, theme, animate, or render PowerPoint decks programmatically. The headline reason this fork exists is **space-awareness**: text that doesn't overflow its box and shapes that don't slide off the edges of the slide. Reach for it especially when generation is dynamic (LLM, DB, CLI, JSON spec) and the deck has to look right without manual cleanup. Other post-fork features include visual effects, animations, transitions, theme writer, design tokens, slide recipes, slide thumbnails, chart palettes, SVG embedding, 3D, and SmartArt text substitution.
---

# power-pptx

`power-pptx` is the actively-maintained fork of `python-pptx`,
distributed on PyPI as `power-pptx` but imported as `import power_pptx`
(drop-in compatible). Use it for every PowerPoint generation /
mutation task.

## The headline: space-aware authoring

The single biggest reason this fork exists is to make programmatic
decks **physically correct**: text doesn't overflow its container,
shapes don't sit off the slide, and elements that overlap do so on
purpose. Three layered tools — used together — catch ~all real-world
issues:

1. **`TextFrame.fit_text(...)`** measures with Pillow font metrics
   and bakes a fitting size into the XML *before* save.
2. **`text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE`** lets
   PowerPoint shrink at render time as a fallback.
3. **`slide.lint()`** catches what slipped through; `auto_fix()`
   nudges off-slide shapes back inside.

**Read `references/space-aware-authoring.md` first** if the user is
generating decks from any dynamic input. It's the reason this skill
exists.

The whole upstream 1.0.2 API still works — the rest of this skill
focuses on the post-fork additions because they're what's most often
missed by snippets pulled from the wider internet.

## Cheat sheet (most common operations)

The 25 calls that cover ~90% of deck-generation tasks. Reach for
`references/geometry-and-arrows.md` for the full surface; this is the
working set:

```python
from power_pptx import Presentation, BBox, audit
from power_pptx.diagrams import horizontal_pipeline, hub_and_spoke, cycle
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.util import Inches, Pt

# --- open / save ---
prs = Presentation()                       # new blank deck
prs = Presentation("file.pptx")            # open existing
prs.save("out.pptx")

# --- slides ---
slide = prs.slides.add_slide(prs.slide_layouts[5])   # Title Only
slide = prs.slides.add_slide(prs.slide_layouts[6])   # Blank

# --- geometry (BBox is splattable into add_*) ---
bb = BBox.from_inches(1, 2, 8, 4)
left, right = bb.split_h([1, 1], gap=Inches(0.2))
inner = bb.inset(all=Inches(0.2))

# --- n-up rows/grids: never hand-compute (avail - (n-1)*gap) / n ---
for cell in bb.columns(3, gap=Pt(16)):     # equal columns; .rows(n) too
    slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, *cell)

# --- text (one call) ---
slide.shapes.add_text(bb, text="Hello",
                      size_pt=24, bold=True,
                      color="#0B5CFF", align="center")

# --- shape with chainable colour ---
slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *bb) \
    .fill_hex("#FFFFFF").line_hex("#0D0D0D", weight_pt=1.25)

# --- flat card: no theme drop-shadow, radius in points ---
card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, *inner)
card.shadow.clear()                        # kills the inherited effectRef too
card.corner_radius = Pt(6)                 # not adjustments[0]

# --- arrow with proper triangular head + auto edge routing ---
start_shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *left)
end_shape   = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *right)
slide.shapes.add_arrow(start=start_shape, end=end_shape,
                       head="triangle", color="#0B5CFF", weight_pt=1.5)

# --- format-preserving text replacement (templated placeholders) ---
title_shape.set_text_preserving_format("New title")

# --- picture replacement (broken / sub-quality picture → native shapes) ---
picture.replace_with(lambda slide, bbox: ..., padding=Inches(0.1))

# --- diagram recipes ---
horizontal_pipeline(slide, bb, steps=["Extract", "Classify", "Enrich"])
hub_and_spoke(slide, bb, centre="Agent",
              spokes=["Memory", "Tools", "Planning"])

# --- table styling without dropping to raw fill/font loops ---
table.format_cells(rows=0, fill="#1F2937", color="#FFFFFF", bold=True)
table.format_cells(rows=slice(1, None), size_pt=11, align="right")

# --- space-aware fit (returns the size it applied) ---
size = tf.fit_text(font_family="Inter", max_size=24)

# --- single-call cleanup before save ---
slide.tidy()                               # lints + safe auto-fixes

# --- tell the linter an overlap is deliberate (widest -> narrowest) ---
slide.lint_group_overlaps(card, accent, label)   # one visual cluster
badge.allow_overlap_with(card)                   # exactly this one pair
card.layer, badge.layer_above = "card", "card"   # also asserts z-order

# --- validate at save time (off by default) ---
prs.lint_on_save = "raise"                 # or "warn"; raises before writing

# --- whole-deck audit (markdown summary) ---
print(audit(prs).markdown())

# --- render thumbnails ---
from power_pptx.render import render_slides
render_slides(prs, slides=[0, 1, 2], out_dir="thumbs",
              name_template="slide-{:02d}.png")
```

That whole sheet fits on one screen — it's the working set.

## When to use this skill

- The user wants to **generate a deck** from Python or a JSON / dict spec
- The user is concerned about **text overflow** or **layout correctness**
  in generated decks (lead with `space-aware-authoring.md`)
- The user wants to **add visual effects** (shadow, glow, soft edges,
  blur, reflection, alpha) to shapes
- The user wants **animations**, **transitions**, or **motion paths**
- The user wants to **read or write a theme** (palette + fonts), or
  apply one from a `.potx`
- The user wants to **lint / auto-fix** geometry issues
- The user wants to **import a slide** between decks or **apply a template**
- The user wants a **design system** (tokens, recipes, Grid/Stack layout)
- The user wants **chart palettes**, **quick layouts**, or per-series
  gradient/pattern fills
- The user wants **slide thumbnails** rendered to PNG
- The user wants **3D** primitives (bevels / extrusion) or **SmartArt
  text substitution**
- The user wants **native SVG embedding** with PNG fallback

## Install

```bash
pip install power-pptx
```

The `cairosvg` dependency is optional — install only if you want
`add_svg_picture(...)` to auto-rasterise the PNG fallback. `pyyaml` is
optional too — install only if you want `DesignTokens.from_yaml`.

## Reference snippets

This skill ships a `references/` directory with focused recipe
collections. Read just the file you need — they're self-contained.

| File | What it covers |
|---|---|
| `references/space-aware-authoring.md` | **READ THIS FIRST.** Pre-flight measurement (`fit_text`, `TextFitter.best_fit_font_size`), `auto_size` flags, the linter, and a robust layout pattern. **Phase 2 + Phase 6 text-fit estimator.** |
| `references/geometry-and-arrows.md` | `BBox` value object (`columns`/`rows`/`split_h`/`grid`), `add_text` / `add_arrow` / `fill_hex` / `line_hex` convenience, `set_text_preserving_format`, `Picture.replace_with`, `Slide.tidy()`, diagram recipes (`horizontal_pipeline`, `hub_and_spoke`, `cycle`, `decision_tree`, `comparison_columns`), `audit(prs)`. **v2.8.** |
| `references/lint.md` | Detail on `slide.lint()`, issue types, `auto_fix`, and the `from_spec(..., lint="raise")` hook. **Phase 2.** |
| `references/design.md` | `DesignTokens`, `shape.style` facade, `Grid` / `Stack` layout primitives (geometry-safe placement), slide recipes (`title_slide`, `bullet_slide`, `kpi_slide`, `quote_slide`, `image_hero_slide`), starter pack. **Phase 9.** |
| `references/basics.md` | The 1.0.2 surface: `Presentation`, slides, placeholders, shapes, textboxes, tables, pictures, charts. Quick-reference cheatsheet. |
| `references/effects.md` | **The canonical fills-and-effects reference.** Shadow (including `shadow.clear()`), glow, soft edges, blur, reflection, alpha-tinted colors, gradient fills (linear / radial / rectangular / shape), line ends/caps/joins/compound. Other files link here rather than repeat it. **Phase 3 + Phase 6.** |
| `references/animations.md` | `Entrance` / `Exit` / `Emphasis` presets, triggers, by-paragraph reveal, sequencing context manager, motion paths. **Phase 5.** |
| `references/transitions.md` | Per-slide and deck-wide transitions including Morph and other `p14:` extensions. **Phase 4.** |
| `references/compose.md` | `from_spec` (JSON authoring with built-in lint), `import_slide`, `apply_template`. **Phase 2 + Phase 7.** |
| `references/theme.md` | Reading + writing the theme palette and fonts; `theme.apply(...)`; theme-aware color resolution via `power_pptx.inherit.resolve_color`. **Phase 6 + Phase 7.** |
| `references/picture-effects.md` | Picture transparency / brightness / contrast / recolor (grayscale / sepia / washout / duotone) and SVG embedding. **Phase 6.** |
| `references/charts.md` | Chart palettes, quick layouts, per-series gradient/pattern fills, plus the inherited chart API. **Phase 10.** |
| `references/render.md` | Slide thumbnails via LibreOffice. **Phase 10.** |
| `references/three-d.md` | Bevels and extrusion via `shape.three_d`. **Phase 8.** |
| `references/smart-art.md` | Text substitution inside an existing template's SmartArt. **Phase 8.** |
| `references/tables.md` | The inherited table API, plus `cell.format(...)` / `table.format_cells(...)` styling, `Cell.borders`, and `fit_to_box`. |
| `references/end-to-end-deck.md` | A complete worked example: tokens, recipes, animations, transitions, charts, **and a lint pass before save**. |

## Top-level imports beyond `Presentation`

These are stable package-root re-exports — prefer them over deeper
import paths:

```python
from power_pptx import (
    Presentation,
    # Immutable rectangular region; splats into add_* APIs.
    BBox,
    # One-call deck audit (lint + picture + empty-slide + font checks).
    audit, AuditReport,
    # Figure adapters — Plotly / Matplotlib / SVG / HTML → slide picture.
    # Third-party deps are imported lazily; missing deps surface a clear
    # FigureBackendUnavailable with the right pip install command.
    add_plotly_figure, add_matplotlib_figure,
    add_svg_figure,    add_html_figure,
    FigureBackendUnavailable,
    # Shape-level building blocks (token-driven; return small
    # dataclasses exposing constituent shapes for further tweaks).
    add_kpi_card, add_progress_bar,
    KpiCard,      ProgressBar,
)
```

## House rules for code you write

1. **Always `from power_pptx import Presentation`** — never invent another
   import path.
2. **Default to space-aware patterns** for any text the user controls
   at runtime: `fit_text` *or* `auto_size = TEXT_TO_FIT_SHAPE`, plus a
   `slide.lint()` pass before save.
3. **Reads should not mutate.** All effect / color / line proxies in
   power-pptx return `None` for unset properties; assign `None` to
   clear.
4. **Use EMU through helpers**: `Inches`, `Pt`, `Emu`, `Cm` from
   `power_pptx.util`. Never write raw EMU integers when a helper exists.
5. **Use `BBox` / `Grid` / `Stack` for placement** when you have more
   than two shapes on a slide — they compute geometry from the slide's
   real dimensions (or a region you hand them), so you can't
   accidentally walk off the right edge, and there's no column
   arithmetic to get wrong.
6. **Prefer recipes for whole-slide layouts** when the user wants a
   "good enough" pitch deck; drop down to direct `add_shape` /
   `add_textbox` only when the recipes don't fit.
7. **Save once at the end** — build the deck in memory, then call
   `prs.save(...)`. Don't open and re-save inside loops.
8. **For released-version constraints**: pin `power-pptx>=2.8.0`
   when generating requirements files — that's the minimum that
   ships the `BBox`, `add_text`, `add_arrow`, `diagrams`, and
   `audit` surface used in this skill.

## A space-aware mini-template

The pattern you'll reach for most often:

```python
from power_pptx import Presentation
from power_pptx.enum.text import MSO_AUTO_SIZE
from power_pptx.util import Inches

prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[5])
slide.shapes.title.text = "Q4 Review"

# Body box that has to swallow runtime-supplied text
box = slide.shapes.add_textbox(Inches(0.6), Inches(1.6),
                                Inches(12), Inches(5))
tf = box.text_frame
tf.word_wrap = True
tf.text = USER_SUPPLIED_BODY

# Belt: pick a determined size now using Pillow font metrics
tf.fit_text(font_family="Inter", max_size=24)

# Braces: let PowerPoint shrink on the way down if a user later edits
tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

# Catch anything that slipped through. auto_fix() mutates the slide
# (nudges OffSlide shapes in, autofits overflowing frames, restacks
# contradicted layer declarations) and refreshes report.issues itself.
slide.lint().auto_fix()
report = slide.lint()
errors = [i for i in report.issues if i.severity.value == "error"]
if errors:
    raise RuntimeError("\n".join(str(e) for e in errors))

prs.save("out.pptx")
```

## Recent additions worth knowing

These changes ship after v2.5 and are easy to miss:

- **`Chart.recolour(palette)`** is the recommended single entry
  point — auto-dispatches per chart type (per-point on pie /
  doughnut, per-series otherwise). `apply_palette` warns and
  routes when called on a doughnut.
- **`Chart.line_color`** and **`Chart.apply_dark_theme(text=, line=)`**
  pin axis lines + gridlines for dark-deck styling.
- **Horizontal bar charts (`BAR_*`)** now default to top-to-bottom
  reading order (`reverse_order=True`). Override with
  `chart.category_axis.reverse_order = False` for legacy ordering.
  Column charts are unaffected.
- **`anchor=` keyword on `add_picture` / `add_shape` / `add_textbox`**
  collapses corner / centre placement to one call (see
  `references/basics.md`).
- **`add_table(..., style="clean")`** disables every inherited style
  flag — use it whenever you'll set custom cell borders or fills.
- **`add_kpi_card(slide, ...)` / `add_progress_bar(slide, ...)`** —
  shape-level building blocks beneath the slide-level recipes
  (see `references/design.md`).
- **`shape.shadow.clear()`** is the way to guarantee *no* shadow.
  Clearing the individual shadow properties (or the deprecated
  `shadow.inherit = False`) leaves the shape's `<a:effectRef idx="2"/>`
  in place — a soft drop shadow in most themes — so cards keep a
  phantom shadow nobody asked for. `clear()` drops the explicit shadow
  elements *and* re-points the effect reference, keeping glow / soft
  edges / blur / reflection intact.
- **`shape.corner_radius`** reads and writes a rounded rectangle's
  radius as a real length (`card.corner_radius = Pt(6)`), instead of the
  `adjustments[0]` fraction-of-the-shorter-side that has to be eyeballed
  per shape size.
- **`BBox.columns(n, gap=...)` / `BBox.rows(n, gap=...)`** replace the
  `(available - (n - 1) * gap) / n` loop for card rows, stat grids, and
  panels. `Grid.from_box(box, cols=..., rows=...)` puts a full grid over
  a region rather than the whole slide.
- **`cell.format(...)` / `table.format_cells(rows=..., cols=..., ...)`**
  style table cells with the same keywords as `add_text` (`fill`,
  `color`, `bold`, `size_pt`, `align`, `anchor`, `margin`) — no more
  `cell.fill.solid(); cell.fill.fore_color.rgb = ...` loops.
- **`fit_text` is explicit about fallback metrics.** It returns the size
  it applied, and warns (`FontMetricsWarning`) when a *named* family
  isn't installed and measurement silently drops to Pillow's default
  font — naming one is what makes it audible, so omitting `font_family`
  stays quiet while `font_family="Calibri"` does not. `strict=True`
  raises instead; `power_pptx.text.fonts.font_is_installed("Inter")`
  checks up front.
- **Float coordinates from arithmetic are coerced** at constructor
  entry and at `shape.left/top/width/height` setters, so
  `(Inches(N) - gutter) / 2` style expressions can be passed straight
  through. Pre-2.6.1 these produced float-valued `<a:off>` / `<a:ext>`
  attributes that PowerPoint rejected with the "Repair?" dialog.

## Anti-patterns to avoid

LLM-generated power-pptx code falls into the same handful of traps.
Flagging them up front saves the trial-and-error round.

- **Don't** access `tf.paragraphs` twice and compare wrapper objects
  with `is`. The property returns *fresh* `_Paragraph` objects every
  call, so `p is not para` is always true — your filter will remove
  the wrong paragraph. Use `set_text_preserving_format(new_text)` for
  the common "replace text, keep formatting" case.
- **Don't** assume `add_connector(MSO_CONNECTOR.STRAIGHT, ...)` puts
  an arrowhead on the line. It produces a bare line. Use
  `slide.shapes.add_arrow(start, end, head="triangle")` — it sets the
  arrowhead, inset, edge routing, and colour in one call.
- **Don't** size a diagram to a broken picture's bbox when there's an
  enclosing card. The card area is what you want. Use
  `picture.enclosing_container()` to find the right box, then
  `picture.replace_with(builder)`.
- **Don't** delete a picture and then assume sibling shape indexes
  are stable. Process in reverse index order, or capture the shapes
  to mutate *before* iterating.
- **Don't** import `RGBColor` / `PP_ALIGN` / `MSO_VERTICAL_ANCHOR`
  for every styling call. Use the hex-string and short-name kwargs:
  `slide.shapes.add_text(bb, text="…", color="#0B5CFF", align="center",
  anchor="middle")`. Hex strings, tuples, and `RGBColor` all work
  everywhere a colour is accepted.
- **Don't** write raw EMU integers. `BBox.from_inches(1, 2, 8, 4)`
  for regions, `Inches(1)` / `Pt(12)` for individual lengths. Float
  arithmetic on EMU is fine — coordinates are coerced at the setter.
- **Don't** lint + auto_fix + lint again to clear safe issues. Use
  `slide.tidy()` — it's the one-call wrapper.
- **Don't** hand-roll `col_w = (avail - (n - 1) * gap) / n` and a running
  cursor for card rows or stat grids. `bb.columns(n, gap=Pt(16))` (and
  `bb.rows(...)`, `bb.grid(cols, rows)`, `Grid.from_box(bb, cols=...)`)
  return exact, drift-free boxes.
- **Don't** try to remove a shadow by assigning `None` to
  `shadow.blur_radius` / `distance`, or by `shadow.inherit = False`.
  Neither touches the theme effect style, so the shadow is still
  rendered. Use `shape.shadow.clear()` — the only call that does.
- **Don't** set a corner radius by guessing `adjustments[0]` (it's a
  fraction of the shorter side, so the same value means a different
  radius on every differently-sized card). Use
  `shape.corner_radius = Pt(6)`.
- **Don't** style table cells with `cell.fill.solid()` +
  `cell.fill.fore_color.rgb` + per-run font loops. Use
  `cell.format(...)` / `table.format_cells(...)` — and note that a
  cell's anchor and insets belong on the cell, not on its text frame.
- **Don't** trust `fit_text` when the font isn't installed. The
  measurement falls back to Pillow's default metrics and the result is
  an estimate — bundle the `.ttf` and pass `font_file=`, or pass
  `strict=True` so the build fails instead of shipping a guess.

## Common pitfalls

- **Calling `shape.shadow.inherit`** raises `DeprecationWarning`. Read
  individual properties (`blur_radius`, `distance`, `direction`,
  `color`) and check for `None` instead; to *remove* a shadow call
  `shape.shadow.clear()`.
- **`fit_text` degrades to a best guess for uninstalled fonts.** Font
  metrics come from the machine running the build, so a brand face that
  isn't installed (the usual case in a container or CI) is measured with
  Pillow's default font. Check with
  `power_pptx.text.fonts.font_is_installed(...)`, pass `font_file=` with
  the real `.ttf`, or use `strict=True`. `slide.lint()` is unaffected —
  its overflow check is font-agnostic — which is why the lint pass is
  worth keeping even when the metrics are exact.
- **Bare-int sizes in `DesignTokens` typography** are interpreted as
  **EMU**, not points. Use floats (`44.0`) or `Pt(44)` to mean
  44-point font.
- **Recipes use the Blank layout**, so `slide.shapes.title` is `None`.
  Address shapes by index (`slide.shapes[0]`, `slide.shapes[1]`, …).
- **`add_svg_picture` without `cairosvg` and without a `png_fallback`**
  raises `CairoSvgUnavailable`. Either install cairosvg or supply a
  pre-rasterised PNG.
- **`TextOverflow` is reported but not auto-fixed**. The current
  `report.auto_fix()` only handles `OffSlide`. For overflow, use
  `tf.fit_text(...)` or `auto_size = TEXT_TO_FIT_SHAPE`.
- **Slide thumbnails require `soffice` on PATH** (LibreOffice).
  Otherwise you get `ThumbnailRendererUnavailable`.
- **`MSO_PATTERN_TYPE.ERCENT_40`** is the upstream typo and emits a
  `DeprecationWarning`. Use `PERCENT_40`.
- **Calling `chart.apply_palette` on a pie / doughnut** emits a
  `UserWarning` and routes through `color_by_category`. Use
  `chart.recolour(palette)` directly to silence it.

## Where to look in the project

If the user has the `power-pptx` repo checked out alongside this
skill, these paths are useful for source-of-truth lookup:

- `src/power_pptx/lint.py` — `SlideLintReport`, `TextOverflow`, `OffSlide`,
  `ShapeCollision`, `LayerOrderViolation`, `LintSeverity`.
- `src/power_pptx/shapes/base.py` — `lint_group`, `lint_skip`,
  `allow_overlap_with`, `layer` / `layer_above` (overlap intent).
- `src/power_pptx/text/text.py`, `src/power_pptx/text/layout.py` — `fit_text`,
  `TextFitter`, `_best_fit_font_size`.
- `src/power_pptx/animation.py` — `Entrance`, `Exit`, `Emphasis`,
  `MotionPath`, `SlideAnimations`.
- `src/power_pptx/compose/` — `from_spec`, plus the `import_slide` /
  `apply_template` re-exports.
- `src/power_pptx/theme.py`, `src/power_pptx/inherit.py` — theme reader/writer and
  `resolve_color`.
- `src/power_pptx/dml/effect.py`, `src/power_pptx/dml/picture.py`,
  `src/power_pptx/dml/line.py` — Phase 3/6 visual effects, picture filters,
  line-end formatting.
- `src/power_pptx/design/` — `tokens`, `style`, `layout`, `recipes`.
- `src/power_pptx/chart/palettes.py`, `src/power_pptx/chart/quick_layouts.py`.
- `src/power_pptx/render.py` — slide-thumbnail renderer.
- `src/power_pptx/smart_art.py`, `src/power_pptx/_svg.py`.
- `examples/starter_pack/` — three example token sets and a build script.

The user-facing Sphinx documentation under `docs/user/` mirrors the
sections in this skill and is a good source of additional prose.
