# power-pptx showcase decks

A self-contained suite of six example decks that exercises every
post-fork feature of `power-pptx` in a single, brand-aligned identity.
Each deck is small (1–6 slides) and isolates one feature area so the
output is easy to review side-by-side.

| Script | Feature area | Slides |
|---|---|---|
| `01_design_system.py`   | Tokens + recipes (`title`, `kpi`, `bullet`, `quote`, `image_hero`) plus a `Grid`-laid feature row | 6 |
| `02_charts.py`          | Chart palettes, quick layouts, per-series gradient, per-data-point coloring (column / line / bar / pie) | 4 |
| `03_visual_effects.py`  | Outer shadow, glow, soft edges, linear/radial/shape gradient fills, alpha-tinted glass cards | 4 |
| `04_animations.py`      | Sequenced entrance + emphasis, per-paragraph reveal, motion-path arc, deck-wide and per-slide transitions | 4 |
| `05_space_aware.py`     | `fit_text` vs naive sizing, `auto_size = TEXT_TO_FIT_SHAPE`, `slide.lint()` detection + `auto_fix` | 3 |
| `06_tables.py`          | Branded table with `Cell.borders`, alternating row fill, conditional delta coloring | 1 |

All scripts share `_tokens.py` (one design-token spec) and `_lint.py`
(a lint-or-die helper). Every deck runs the linter before save —
`05_space_aware` is the only one with a deliberately-broken slide kept
in for demonstration.

## Build everything

```bash
pip install -e .
python examples/showcase/build_all.py
```

Outputs land in `examples/showcase/_out/`:

```
_out/
├── 01_design_system.pptx
├── 02_charts.pptx
├── 03_visual_effects.pptx
├── 04_animations.pptx
├── 05_space_aware.pptx
├── 06_tables.pptx
└── thumbs/
    ├── 01_design_system/slide-1.png ... slide-6.png
    ├── 02_charts/slide-1.png ... slide-4.png
    └── ...
```

### Thumbnail rendering

`build_all.py` renders one PNG per slide via
`soffice --convert-to pdf` followed by `pdftoppm`. The shipped
`Presentation.render_thumbnails` shells out to
`soffice --convert-to png` directly, which only emits the first slide
of a deck. Going through PDF gives a PNG per slide.

Requires:

- LibreOffice with the Impress component (`libreoffice-impress` on
  Debian/Ubuntu)
- `pdftoppm` from `poppler-utils`

If either binary is missing, deck generation still succeeds and
thumbnail rendering is skipped with a warning.

## Run a single deck

Each script is independently runnable:

```bash
python examples/showcase/01_design_system.py
python examples/showcase/02_charts.py
# ...
```

Each writes its own `.pptx` into `_out/` and prints the path it wrote.

## Regenerate the hero asset

`assets/hero.jpg` is a Pillow-generated radial-gradient backdrop used
by `01_design_system.py`'s `image_hero_slide`. Regenerate with:

```bash
python examples/showcase/assets/_make_assets.py
```

## What to look for in each deck

**01 — Design system.** Token-driven palette and typography used by
every recipe; the closing "pillars" slide builds three styled cards on
a 12-column `Grid` rather than hand-arithmetic placement.

**02 — Charts.** Slide 1 shows a per-series linear gradient on the
FY26 column. Slide 3 colors each bar of a single-series chart from the
brand palette via `series.points[i].format.fill`. Slide 4 does the
same for the pie slices and shows a custom-dict quick layout.

**03 — Visual effects.** Each slide isolates one effect family — three
shadow intensities, two glows + soft edges, three gradient kinds, and
glass-card alpha tints over a brand backdrop.

**04 — Animations.** The deck-wide fade transition is set first, then
slide 1 is upgraded to Morph and slide 4 to Push. Slide 1 has a
sequenced entrance, slide 2 a per-paragraph reveal, slide 3 an
emphasis pulse on every KPI card, slide 4 an arc motion path. Open
in PowerPoint or LibreOffice slideshow mode to see effects in action.

**05 — Space-aware.** Slide 1 puts the same long string in two
identical boxes — the left one with naive `Pt(36)` (overflows), the
right with `fit_text` (fits). Slide 2 shows `auto_size =
TEXT_TO_FIT_SHAPE` baked into the XML for runtime resizing. Slide 3
deliberately ships an off-slide shape and an overflowing text box and
prints the lint report to stdout, then re-lints after `auto_fix()` to
show the residual issues.

**06 — Tables.** A 5×5 metrics scorecard with `Cell.borders.bottom`
rules, alternating row fills, a styled header band, and conditional
green / red coloring on the delta column.
