# power-pptx playground decks

A second wave of example decks (alongside `examples/showcase/`),
designed to stretch the library across a wider range of design styles
and slide shapes. Each script writes its own `.pptx` and is
independently runnable.

The playground decks share one design identity (the SUNSET tokens in
`_brand.py`) so the suite reads as a coherent magazine — coral primary,
deep navy text, cream surface, DejaVu Serif headings — distinct from
the indigo/cyan of `examples/showcase/`.

| Script | Theme |
|---|---|
| `01_editorial_data_story.py` | Magazine-style data story: cover, KPI strip, line chart, conditionally-coloured table, full-bleed pull quote, callout pillars. |
| `02_research_findings.py`    | Research-paper aesthetic: cover with overlapping shapes, methods cards, **XY scatter** with brand-coloured markers, **stacked bar**, **donut** with side legend and stat block, **2×2 small multiples**, gradient-backdrop conclusion. |
| `03_product_launch.py`       | Visual-effects-heavy product launch: teaser, **radial-gradient hero**, feature grid with shadow + glow, **alpha-glass pricing tiers** over a saturated gradient, dotted **roadmap timeline**, sign-off. Sets a deck-wide FADE with MORPH overrides between cover/hero. |
| `04_sales_playbook.py`       | Mixed-layout sales playbook: split cover, agenda Stack, do/don't two-column, five-step process flow, **100% stacked bar**, 2×2 objection cards, KPI dashboard with supporting chart, big-text close. Deck-wide PUSH transition. |
| `05_from_spec_declarative.py` | Declarative authoring via `from_spec(SPEC)` — token-aware recipes from a single dict, lint-on-save, per-slide transitions. Kept 4:3 (the recipes' assumed canvas). |

All five scripts run the linter via `_common.lint_or_die` before save —
none of them ship a deliberately-broken slide.

## Build everything

```bash
pip install -e .
python examples/playground/build_all.py
```

Outputs land in `examples/playground/_out/`:

```
_out/
├── 01_editorial_data_story.pptx
├── 02_research_findings.pptx
├── 03_product_launch.pptx
├── 04_sales_playbook.pptx
├── 05_from_spec_declarative.pptx
└── thumbs/
    ├── 01_editorial_data_story/slide-1.png ... slide-6.png
    ├── 02_research_findings/slide-1.png ... slide-7.png
    └── ...
```

## Thumbnail rendering

`build_all.py` shells out to `soffice --convert-to pdf` followed by
`pdftoppm` for one PNG per slide (the shipped
`Presentation.render_thumbnails` only emits the first slide). Requires:

- LibreOffice with the Impress component (`libreoffice-impress`)
- `pdftoppm` (`poppler-utils`)

If either is missing, deck generation still succeeds and thumbnail
rendering is skipped with a warning.

## Run a single deck

```bash
python examples/playground/01_editorial_data_story.py
```

Each script writes its own `.pptx` into `_out/` and prints the path.
To render thumbnails for one deck without rebuilding everything:

```python
from pathlib import Path
import sys
sys.path.insert(0, "examples/playground")
from _render import render

render(Path("examples/playground/_out/01_editorial_data_story.pptx"))
```

## Improvements log

`IMPROVEMENTS.md` collects every library and docs paper-cut I hit while
authoring these decks — eleven items as of writing, ranging from
"docs example never worked" (`from_spec`'s `theme` key) to "scatter
markers were silently invisible" (line-on-by-default for
`XL_CHART_TYPE.XY_SCATTER` when you brand-colour the line). It's a
plain-text triage queue for the maintainers, not a planned commit.
