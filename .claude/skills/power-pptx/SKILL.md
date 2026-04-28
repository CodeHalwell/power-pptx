---
name: power-pptx
description: Build PowerPoint (.pptx) decks from Python with the power-pptx library — the actively-maintained fork of python-pptx. Use this skill whenever the user wants to generate, mutate, lint, theme, animate, or render PowerPoint decks programmatically. The headline reason this fork exists is **space-awareness**: text that doesn't overflow its box and shapes that don't slide off the edges of the slide. Reach for it especially when generation is dynamic (LLM, DB, CLI, JSON spec) and the deck has to look right without manual cleanup. Other post-fork features include visual effects, animations, transitions, theme writer, design tokens, slide recipes, slide thumbnails, chart palettes, SVG embedding, 3D, and SmartArt text substitution.
---

# power-pptx

`power-pptx` is the actively-maintained fork of `python-pptx`,
distributed on PyPI as `power-pptx` but imported as `import pptx`
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
| `references/lint.md` | Detail on `slide.lint()`, issue types, `auto_fix`, and the `from_spec(..., lint="raise")` hook. **Phase 2.** |
| `references/design.md` | `DesignTokens`, `shape.style` facade, `Grid` / `Stack` layout primitives (geometry-safe placement), slide recipes (`title_slide`, `bullet_slide`, `kpi_slide`, `quote_slide`, `image_hero_slide`), starter pack. **Phase 9.** |
| `references/basics.md` | The 1.0.2 surface: `Presentation`, slides, placeholders, shapes, textboxes, tables, pictures, charts. Quick-reference cheatsheet. |
| `references/effects.md` | Shadow, glow, soft edges, blur, reflection, alpha-tinted colors, gradient fills (linear / radial / rectangular / shape), line ends/caps/joins/compound. **Phase 3 + Phase 6.** |
| `references/animations.md` | `Entrance` / `Exit` / `Emphasis` presets, triggers, by-paragraph reveal, sequencing context manager, motion paths. **Phase 5.** |
| `references/transitions.md` | Per-slide and deck-wide transitions including Morph and other `p14:` extensions. **Phase 4.** |
| `references/compose.md` | `from_spec` (JSON authoring with built-in lint), `import_slide`, `apply_template`. **Phase 2 + Phase 7.** |
| `references/theme.md` | Reading + writing the theme palette and fonts; `theme.apply(...)`; theme-aware color resolution via `pptx.inherit.resolve_color`. **Phase 6 + Phase 7.** |
| `references/picture-effects.md` | Picture transparency / brightness / contrast / recolor (grayscale / sepia / washout / duotone) and SVG embedding. **Phase 6.** |
| `references/charts.md` | Chart palettes, quick layouts, per-series gradient/pattern fills, plus the inherited chart API. **Phase 10.** |
| `references/render.md` | Slide thumbnails via LibreOffice. **Phase 10.** |
| `references/three-d.md` | Bevels and extrusion via `shape.three_d`. **Phase 8.** |
| `references/smart-art.md` | Text substitution inside an existing template's SmartArt. **Phase 8.** |
| `references/tables.md` | The inherited table API, plus `Cell.borders`. **Phase 4.** |
| `references/end-to-end-deck.md` | A complete worked example: tokens, recipes, animations, transitions, charts, **and a lint pass before save**. |

## House rules for code you write

1. **Always `from pptx import Presentation`** — never invent another
   import path.
2. **Default to space-aware patterns** for any text the user controls
   at runtime: `fit_text` *or* `auto_size = TEXT_TO_FIT_SHAPE`, plus a
   `slide.lint()` pass before save.
3. **Reads should not mutate.** All effect / color / line proxies in
   power-pptx return `None` for unset properties; assign `None` to
   clear.
4. **Use EMU through helpers**: `Inches`, `Pt`, `Emu`, `Cm` from
   `pptx.util`. Never write raw EMU integers when a helper exists.
5. **Use `Grid` / `Stack` for placement** when you have more than two
   shapes on a slide — they compute geometry from the slide's real
   dimensions, so you can't accidentally walk off the right edge.
6. **Prefer recipes for whole-slide layouts** when the user wants a
   "good enough" pitch deck; drop down to direct `add_shape` /
   `add_textbox` only when the recipes don't fit.
7. **Save once at the end** — build the deck in memory, then call
   `prs.save(...)`. Don't open and re-save inside loops.
8. **For released-version constraints**: this fork is
   `power-pptx>=1.1.0`. Pin that in any requirements file you generate.

## A space-aware mini-template

The pattern you'll reach for most often:

```python
from pptx import Presentation
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.util import Inches

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
# (currently: nudges OffSlide shapes back in), so we re-lint to see
# the residual issues.
slide.lint().auto_fix()
report = slide.lint()
errors = [i for i in report.issues if i.severity.value == "error"]
if errors:
    raise RuntimeError("\n".join(str(e) for e in errors))

prs.save("out.pptx")
```

## Common pitfalls

- **Calling `shape.shadow.inherit`** raises `DeprecationWarning`. Read
  individual properties (`blur_radius`, `distance`, `direction`,
  `color`) and check for `None` instead.
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

## Where to look in the project

If the user has the `power-pptx` repo checked out alongside this
skill, these paths are useful for source-of-truth lookup:

- `src/pptx/lint.py` — `SlideLintReport`, `TextOverflow`, `OffSlide`,
  `ShapeCollision`, `LintSeverity`.
- `src/pptx/text/text.py`, `src/pptx/text/layout.py` — `fit_text`,
  `TextFitter`, `_best_fit_font_size`.
- `src/pptx/animation.py` — `Entrance`, `Exit`, `Emphasis`,
  `MotionPath`, `SlideAnimations`.
- `src/pptx/compose/` — `from_spec`, plus the `import_slide` /
  `apply_template` re-exports.
- `src/pptx/theme.py`, `src/pptx/inherit.py` — theme reader/writer and
  `resolve_color`.
- `src/pptx/dml/effect.py`, `src/pptx/dml/picture.py`,
  `src/pptx/dml/line.py` — Phase 3/6 visual effects, picture filters,
  line-end formatting.
- `src/pptx/design/` — `tokens`, `style`, `layout`, `recipes`.
- `src/pptx/chart/palettes.py`, `src/pptx/chart/quick_layouts.py`.
- `src/pptx/render.py` — slide-thumbnail renderer.
- `src/pptx/smart_art.py`, `src/pptx/_svg.py`.
- `examples/starter_pack/` — three example token sets and a build script.

The user-facing Sphinx documentation under `docs/user/` mirrors the
sections in this skill and is a good source of additional prose.
