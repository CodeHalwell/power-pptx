# End-to-end: a complete branded deck

A worked example that exercises most of the post-fork features in one
script: design tokens, recipes, transitions, animations, a chart with
a custom palette, a layout pass through the linter, and an optional
thumbnail render.

```python
"""
Build a branded Q4 review deck.

Demonstrates: DesignTokens, recipes, deck-wide transitions,
sequenced animations, chart palette, lint-on-save, thumbnails.
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.animation import Emphasis, Entrance, Trigger
from pptx.chart.data import CategoryChartData
from pptx.design.recipes import (
    bullet_slide,
    image_hero_slide,
    kpi_slide,
    quote_slide,
    title_slide,
)
from pptx.design.tokens import DesignTokens
from pptx.dml.color import RGBColor
from pptx.enum.presentation import MSO_TRANSITION_TYPE
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches, Pt


# ---- Tokens ------------------------------------------------------------------

TOKENS = DesignTokens.from_dict(
    {
        "palette": {
            "primary":    "#4F9DFF",
            "neutral":    "#1F2937",
            "background": "#FFFFFF",
            "positive":   "#10B981",
            "negative":   "#EF4444",
            "on_primary": "#FFFFFF",
        },
        "typography": {
            # NB: recipes look up the keys "heading" and "body". Bare
            # floats are treated as POINTS; bare ints are EMU.
            "heading": {"family": "Inter", "size": 44.0, "bold": True},
            "body":    {"family": "Inter", "size": 18.0},
        },
        "shadows": {
            "card": {"blur": 18.0, "distance": 4.0, "alpha": 0.18},
        },
        "radii":    {"card": 12.0},
        "spacings": {"sm": 8.0, "md": 16.0, "lg": 32.0},
    }
)


# ---- Build the deck ----------------------------------------------------------

def build(out_path: str | Path) -> Presentation:
    prs = Presentation()
    prs.slide_width  = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # Cover
    title_slide(
        prs,
        title="Q4 2026 Review",
        subtitle="April 2026",
        tokens=TOKENS,
    )

    # KPIs
    kpi_slide(
        prs,
        title="Run-rate metrics",
        kpis=[
            {"label": "ARR",         "value": "$182M", "delta": +0.27},
            {"label": "NDR",         "value": "131%",  "delta": +0.03},
            {"label": "CAC payback", "value": "8 mo",  "delta": -0.10},
        ],
        tokens=TOKENS,
    )

    # Bullets — annotated with a sequenced paragraph reveal.
    # bullet_slide adds the title textbox first and the body textbox
    # second, so shapes[1] is reliably the body.
    bs = bullet_slide(
        prs,
        title="Customer impact",
        bullets=[
            "Two flagship customers shipped this week.",
            "NPS improved 8 points QoQ.",
            "EU expansion ahead of plan.",
        ],
        tokens=TOKENS,
    )
    body_tf = bs.shapes[1].text_frame
    Entrance.fade(bs, body_tf, by_paragraph=True)

    # Custom chart slide — chart palette + quick layout
    cs = prs.slides.add_slide(prs.slide_layouts[5])
    cs.shapes.title.text = "ARR by segment ($M)"
    data = CategoryChartData()
    data.categories = ["Enterprise", "Mid-market", "SMB", "Self-serve"]
    data.add_series("FY25", (62, 41, 18,  9))
    data.add_series("FY26", (94, 55, 23, 10))
    chart_shape = cs.shapes.add_chart(
        XL_CHART_TYPE.BAR_CLUSTERED,
        Inches(1), Inches(1.8), Inches(11), Inches(5.0),
        data,
    )
    chart = chart_shape.chart
    chart.apply_palette("modern")
    chart.apply_quick_layout("title_axes_legend_bottom")
    chart.chart_title.text_frame.text = "ARR by segment ($M)"

    # Quote
    # Recipes use the Blank layout, so slide.shapes.title is None;
    # quote_slide adds the quote textbox first (shapes[0]).
    qs = quote_slide(
        prs,
        quote="The new dashboards saved my team a week per sprint.",
        attribution="Director of Eng, Flagship Customer",
        tokens=TOKENS,
    )
    Emphasis.pulse(qs, qs.shapes[0], trigger=Trigger.AFTER_PREVIOUS)

    # Hero closer (supply your own image path)
    image_hero_slide(
        prs,
        title="Thank you",
        image="assets/closer.jpg",
        tokens=TOKENS,
    )

    # Deck-wide fade transition, then upgrade the cover to Morph
    prs.set_transition(kind=MSO_TRANSITION_TYPE.FADE, duration=400)
    prs.slides[0].transition.kind     = MSO_TRANSITION_TYPE.MORPH
    prs.slides[0].transition.duration = 1500

    # Space-aware safety net: lint every slide, auto-fix off-slide
    # shapes, and bail loudly if anything is still error-severity.
    _lint_or_die(prs)

    prs.save(out_path)
    return prs


def _lint_or_die(prs: Presentation) -> None:
    from pptx.exc import LintError

    # Pass 1: nudge off-slide shapes inside the slide bounds
    for slide in prs.slides:
        slide.lint().auto_fix()

    # Pass 2: collect anything still failing
    errors = []
    for i, slide in enumerate(prs.slides):
        for issue in slide.lint().issues:
            if issue.severity.value == "error":
                errors.append(f"slide {i + 1}: {issue}")

    if errors:
        raise LintError("\n".join(errors))


# ---- Optional: rasterise thumbnails ------------------------------------------

def render_thumbnails(prs: Presentation, out_dir: str | Path) -> list[Path]:
    """Best-effort thumbnail render. Skips gracefully if soffice is missing."""
    from pptx.render import ThumbnailRendererUnavailable

    try:
        return prs.render_thumbnails(out_dir=out_dir)
    except ThumbnailRendererUnavailable as exc:
        print(f"thumbnail render skipped: {exc}")
        return []


if __name__ == "__main__":
    deck = build("q4-review.pptx")
    render_thumbnails(deck, "thumbs")
```

## What this exercises

- **Phase 9** — `DesignTokens.from_dict`, four recipes (`title_slide`,
  `kpi_slide`, `bullet_slide`, `quote_slide`, `image_hero_slide`),
  shape-style fan-out via `tokens=`.
- **Phase 5** — `Entrance.fade(..., by_paragraph=True)` for a reveal,
  `Emphasis.pulse(..., trigger=Trigger.AFTER_PREVIOUS)` chained off
  the previous click.
- **Phase 4** — `Slide.transition` for the per-slide Morph,
  `Presentation.set_transition` for the deck-wide fade.
- **Phase 10** — `Chart.apply_palette("modern")` and
  `Chart.apply_quick_layout("title_axes_legend_bottom")`.
- **Phase 2** — `_lint_or_die(...)` as a generation safety net:
  `slide.lint().auto_fix()` on every slide to nudge off-slide shapes
  back inside, then a second pass that raises `LintError` on any
  remaining error-severity issue (text overflow, residual off-slide,
  etc).
- **Phase 10** — optional `render_thumbnails(...)` for downstream
  tooling, with graceful fall-through when LibreOffice isn't
  installed.

## Adapting for production

- Persist `TOKENS` separately (YAML or `.pptx`) and load with
  `DesignTokens.from_yaml(...)` / `DesignTokens.from_pptx(...)`. That
  way design and code evolve independently.
- In production, run `_lint_or_die(...)` (or its equivalent) explicitly
  before save. Use `slide.lint().auto_fix()` to repair what can be
  fixed automatically (currently: nudge `OffSlide` shapes back inside
  the slide bounds), then decide what to do with the residual issues —
  log warning-severity issues but ship the deck, raise on
  error-severity issues. Keep the stricter "raise on any error"
  behaviour in CI.
- There is no `Presentation`-level lint hook in 1.1; iterate
  `prs.slides` and call `slide.lint()` per slide, or use
  `pptx.compose.from_spec(..., lint="raise")` if you can express the
  deck as a spec.
- If you want the chart palette to align with brand tokens rather than
  the built-in `"modern"`, pass an explicit list:
  `chart.apply_palette([TOKENS.palette["primary"], ...])`.
