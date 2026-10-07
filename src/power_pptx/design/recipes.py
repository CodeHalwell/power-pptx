"""Opinionated parameterized slide recipes.

Each recipe is a small callable that produces a fully-styled slide using a
shared :class:`~power_pptx.design.tokens.DesignTokens` palette/typography set.
Recipes are deliberately additive: they sit on top of the low-level shape
APIs and the :class:`~power_pptx.design.style.ShapeStyle` facade, and never invent
new OOXML semantics.

The five recipes cover the slide types that account for most of a
typical pitch deck:

* :func:`title_slide`        — title + subtitle hero slide.
* :func:`bullet_slide`       — title + bulleted body.
* :func:`kpi_slide`          — title + KPI card row.
* :func:`quote_slide`        — large pull-quote with attribution.
* :func:`image_hero_slide`   — full-bleed image with overlay caption.

All recipes accept an optional :class:`DesignTokens` argument; when omitted,
they fall back to PowerPoint's defaults (black text, no fill).  Each
recipe also accepts an optional ``transition`` keyword that names a
:class:`~power_pptx.enum.presentation.MSO_TRANSITION_TYPE` member by lowercase
name (``"fade"``, ``"morph"``, ...).

Example::

    from power_pptx import Presentation
    from power_pptx.design.tokens import DesignTokens
    from power_pptx.design.recipes import title_slide, bullet_slide, kpi_slide

    prs = Presentation()
    tokens = DesignTokens.from_dict({
        "palette": {"primary": "#3C2F80", "neutral": "#222222",
                     "accent":  "#FF6600", "muted":   "#777777"},
        "typography": {
            "heading": {"family": "Inter", "size": 36.0, "bold": True},
            "body":    {"family": "Inter", "size": 16.0},
        },
    })

    title_slide(prs, title="Q4 Review", subtitle="April 2026",
                 tokens=tokens, transition="morph")
    bullet_slide(prs, title="Highlights",
                  bullets=["Two flagships shipped.", "NPS +8 QoQ."],
                  tokens=tokens)
    kpi_slide(prs, title="Run-rate metrics",
               kpis=[{"label": "ARR", "value": "$182M", "delta": +0.27},
                     {"label": "NDR", "value": "131%",  "delta": +0.03}],
               tokens=tokens)

    prs.save("review.pptx")
"""

from __future__ import annotations

import contextlib
import math
import os
import re
from dataclasses import replace
from typing import IO, TYPE_CHECKING, Any, Mapping, Optional, Sequence, Union

from power_pptx.design.tokens import DesignTokens, TypographyToken
from power_pptx.dml.color import RGBColor
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from power_pptx.util import Emu, Inches, Length, Pt

if TYPE_CHECKING:
    from power_pptx.presentation import Presentation
    from power_pptx.slide import Slide

__all__ = (
    "title_slide",
    "bullet_slide",
    "kpi_slide",
    "quote_slide",
    "image_hero_slide",
    "section_divider",
    "chart_slide",
    "table_slide",
    "code_slide",
    "timeline_slide",
    "comparison_slide",
    "figure_slide",
)


# ---------------------------------------------------------------------------
# Public recipes
# ---------------------------------------------------------------------------


def title_slide(
    prs: "Presentation",
    *,
    title: str,
    subtitle: Optional[str] = None,
    tokens: Optional[DesignTokens] = None,
    transition: Optional[str] = None,
) -> "Slide":
    """Append a title-hero slide to *prs* and return it.

    Uses the ``Blank`` layout so the recipe owns the geometry and styling
    decisions end-to-end.  Title text is centered horizontally and sits in
    the top half of the slide; the subtitle, if provided, sits just below.

    Tokens consumed:

    * **palette** — title color from ``primary`` (fallback ``neutral``);
      subtitle color from ``muted`` (fallback ``neutral``).
    * **typography** — ``heading`` for the title, ``body`` for the
      subtitle.  Both fall back to Calibri at sensible sizes when the
      token isn't set.
    """
    slide = _add_blank(prs)
    slide_w, slide_h = _slide_dims(prs)
    _apply_background(slide, prs, tokens)

    margin = Inches(1.0)
    title_top = Length(int(slide_h * 0.38))
    title_h = Inches(1.6)
    title_box = slide.shapes.add_textbox(margin, title_top, Length(slide_w - 2 * margin), title_h)
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(44), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        shrink_to_fit=True,
    )

    if subtitle:
        sub_top = Length(title_top + title_h + Inches(0.1))
        sub_h = Inches(0.8)
        sub_box = slide.shapes.add_textbox(margin, sub_top, Length(slide_w - 2 * margin), sub_h)
        _fill_text_frame(
            sub_box.text_frame,
            subtitle,
            token=_typography(tokens, "body", default_size=Pt(20)),
            color=_palette(tokens, ("muted", "neutral")),
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.TOP,
        )

    _apply_transition(slide, transition)
    return slide


def bullet_slide(
    prs: "Presentation",
    *,
    title: str,
    bullets: Sequence[str],
    tokens: Optional[DesignTokens] = None,
    transition: Optional[str] = None,
) -> "Slide":
    """Append a title + bulleted-content slide and return it.

    Tokens consumed:

    * **palette** — title from ``primary`` (fallback ``neutral``);
      bullet text from ``neutral``.
    * **typography** — ``heading`` for the title, ``body`` for the bullet
      lines.
    """
    slide = _add_blank(prs)
    slide_w, slide_h = _slide_dims(prs)
    _apply_background(slide, prs, tokens)

    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(1.0)
    title_box = slide.shapes.add_textbox(margin, title_top, Length(slide_w - 2 * margin), title_h)
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(32), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
        shrink_to_fit=True,
    )

    body_top = Length(title_top + title_h + Inches(0.2))
    body_h = Length(slide_h - body_top - Inches(0.5))
    body_box = slide.shapes.add_textbox(margin, body_top, Length(slide_w - 2 * margin), body_h)
    body_token = _typography(tokens, "body", default_size=Pt(18))
    body_color = _palette(tokens, ("neutral",))
    tf = body_box.text_frame
    tf.word_wrap = True
    for i, bullet in enumerate(bullets):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = PP_ALIGN.LEFT
        run = para.add_run()
        run.text = f"•  {bullet}"
        _apply_typography(run.font, body_token)
        if body_color is not None:
            run.font.color.rgb = body_color
        para.space_after = Pt(6)

    # Space-awareness: a long bullet list (common from LLM output) would
    # otherwise overflow the body box off the bottom of the slide.  Tell
    # PowerPoint to shrink the text to fit the reserved region.
    from power_pptx.enum.text import MSO_AUTO_SIZE

    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    _apply_transition(slide, transition)
    return slide


def kpi_slide(
    prs: "Presentation",
    *,
    title: str,
    kpis: Sequence[Mapping[str, Any]],
    tokens: Optional[DesignTokens] = None,
    transition: Optional[str] = None,
) -> "Slide":
    """Append a title + KPI card-row slide and return it.

    Each KPI dict accepts:

    * ``label`` — the small caption under the value.
    * ``value`` — the headline number / string.
    * ``delta`` *(optional)* — numeric change.  Magnitude with absolute
      value at most ``1.0`` is treated as a fraction (``0.27`` → ``+27%``);
      anything larger is rendered as-is with one decimal
      (``14.0`` → ``+14.0``).  Pass a *string* to opt out of the
      auto-format and render the delta verbatim (``"+14 pts"``,
      ``"−$2.3M"``).  Positive deltas are tinted with the palette's
      ``positive`` slot, negative with ``negative`` (falling back to
      green / red).
    * ``delta_text`` *(optional)* — explicit string passthrough; takes
      precedence over ``delta`` when both are set.

    Tokens consumed:

    * **palette** — title from ``primary`` (fallback ``neutral``); card
      fill from ``surface`` (fallback ``lt2``); card border from
      ``muted`` (fallback ``lt1``); value from ``primary`` (fallback
      ``neutral``); label from ``muted``; delta from ``positive`` /
      ``success`` (positive) and ``negative`` / ``danger`` (negative).
    * **typography** — ``heading`` for the title and the KPI value;
      ``body`` for the label and the delta line.
    * **shadows** — ``card`` (optional) is applied as a soft shadow on
      each KPI card.
    """
    slide = _add_blank(prs)
    slide_w, _slide_h = _slide_dims(prs)
    _apply_background(slide, prs, tokens)

    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(0.9)
    title_box = slide.shapes.add_textbox(margin, title_top, Length(slide_w - 2 * margin), title_h)
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(28), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
        shrink_to_fit=True,
    )

    n = len(kpis)
    if n == 0:
        _apply_transition(slide, transition)
        return slide

    card_h = Inches(1.9)
    gap = Inches(0.25)
    available = slide_w - 2 * margin - (n - 1) * gap
    card_w = Length(int(available // n))
    top = Length(title_top + title_h + Inches(0.4))

    fill_color = _palette(tokens, ("surface", "lt2"))
    border_color = _palette(tokens, ("muted", "lt1"))
    value_color = _palette(tokens, ("primary", "neutral"))
    label_color = _palette(tokens, ("muted",))

    value_token = _typography(tokens, "heading", default_size=Pt(30), default_bold=True)
    label_token = _typography(tokens, "body", default_size=Pt(12))
    delta_token = _typography(tokens, "body", default_size=Pt(11), default_bold=True)

    for i, kpi in enumerate(kpis):
        left = Length(margin + i * (card_w + gap))

        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, card_w, card_h)
        if fill_color is not None:
            card.fill.solid()
            card.fill.fore_color.rgb = fill_color
        else:
            card.fill.background()
        if border_color is not None:
            card.line.color.rgb = border_color
            card.line.width = Pt(0.75)
        # Drop a soft card shadow + corner radius from the tokens.
        _apply_card_styling(card, tokens)
        # Suppress the default text on the autoshape so it doesn't peek
        # through behind our textboxes.
        card.text_frame.text = ""

        # Value
        v_box = slide.shapes.add_textbox(left, Length(top + Inches(0.25)), card_w, Inches(0.85))
        _fill_text_frame(
            v_box.text_frame,
            str(kpi.get("value", "")),
            token=value_token,
            color=value_color,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            shrink_to_fit=True,
        )

        # Label — ``shrink_to_fit=True`` keeps a long label like
        # "Lines of code per slide" inside the 0.4" reserved row
        # instead of wrapping to a second line that overlaps the
        # delta below (IMPROVEMENTS item 11 trailing note).
        l_box = slide.shapes.add_textbox(left, Length(top + Inches(1.10)), card_w, Inches(0.4))
        _fill_text_frame(
            l_box.text_frame,
            str(kpi.get("label", "")),
            token=label_token,
            color=label_color,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.TOP,
            shrink_to_fit=True,
        )

        d_text, d_sign = _resolve_delta(kpi)
        if d_text is not None:
            d_color = _delta_color(tokens, d_sign)
            d_box = slide.shapes.add_textbox(left, Length(top + Inches(1.50)), card_w, Inches(0.35))
            _fill_text_frame(
                d_box.text_frame,
                d_text,
                token=delta_token,
                color=d_color,
                align=PP_ALIGN.CENTER,
                anchor=MSO_ANCHOR.TOP,
                shrink_to_fit=True,
            )

    _apply_transition(slide, transition)
    return slide


def quote_slide(
    prs: "Presentation",
    *,
    quote: str,
    attribution: Optional[str] = None,
    tokens: Optional[DesignTokens] = None,
    transition: Optional[str] = None,
) -> "Slide":
    """Append a centered pull-quote slide with optional attribution.

    *attribution*, when supplied, is rendered with an em-dash prefix
    (``— Person``).  A leading dash / em-dash / en-dash on the input
    is stripped so callers can pass either ``"Person"`` or ``"— Person"``
    without doubling the dash.

    Tokens consumed:

    * **palette** — quote text from ``primary`` (fallback ``neutral``);
      attribution from ``muted`` (fallback ``neutral``).
    * **typography** — ``heading`` for the quote (italic by default);
      ``body`` for the attribution.
    """
    slide = _add_blank(prs)
    slide_w, slide_h = _slide_dims(prs)
    _apply_background(slide, prs, tokens)

    margin = Inches(1.2)
    quote_h = Inches(3.5)
    quote_top = Length((slide_h - quote_h) // 2)
    box = slide.shapes.add_textbox(margin, quote_top, Length(slide_w - 2 * margin), quote_h)
    _fill_text_frame(
        box.text_frame,
        f"“{quote}”",
        token=_typography(tokens, "heading", default_size=Pt(32), default_italic=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        word_wrap=True,
        shrink_to_fit=True,
    )

    if attribution:
        att_top = Length(quote_top + quote_h + Inches(0.1))
        att_box = slide.shapes.add_textbox(
            margin, att_top, Length(slide_w - 2 * margin), Inches(0.6)
        )
        # Strip any leading dash variants the caller may have already
        # written (``-``, ``–`` en-dash, ``—`` em-dash) so the recipe's
        # em-dash isn't doubled — the silent-doubling failure mode is
        # easy to miss in PR review.
        att_clean = _strip_attribution_dash(attribution)
        _fill_text_frame(
            att_box.text_frame,
            f"— {att_clean}",
            token=_typography(tokens, "body", default_size=Pt(16)),
            color=_palette(tokens, ("muted", "neutral")),
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.TOP,
        )

    _apply_transition(slide, transition)
    return slide


def image_hero_slide(
    prs: "Presentation",
    *,
    title: str,
    image: Union[str, IO[bytes]],
    caption: Optional[str] = None,
    tokens: Optional[DesignTokens] = None,
    transition: Optional[str] = None,
) -> "Slide":
    """Append a full-bleed image slide with an overlaid title (and caption).

    The image is added at the slide origin and stretched to the slide's
    full extent.  The title sits in a tinted band across the bottom third
    so it remains readable regardless of the underlying image.

    Tokens consumed:

    * **palette** — band fill from ``primary`` (fallback ``neutral``,
      then black); title and caption text from ``on_primary`` (falling
      back to white / near-white).
    * **typography** — ``heading`` for the title, ``body`` for the
      caption.
    """
    slide = _add_blank(prs)
    slide_w, slide_h = _slide_dims(prs)

    slide.shapes.add_picture(image, Emu(0), Emu(0), slide_w, slide_h)

    band_h = Inches(1.6 if caption else 1.2)
    band_top = Length(slide_h - band_h)
    band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(0), band_top, slide_w, band_h)
    band.line.fill.background()
    band_color = _palette(tokens, ("primary", "neutral")) or RGBColor(0, 0, 0)
    band.fill.solid()
    band.fill.fore_color.rgb = band_color
    band.fill.fore_color.alpha = 0.55
    band.text_frame.text = ""

    margin = Inches(0.6)
    title_box = slide.shapes.add_textbox(
        margin,
        Length(band_top + Inches(0.2)),
        Length(slide_w - 2 * margin),
        Inches(0.8),
    )
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(28), default_bold=True),
        color=_palette(tokens, ("on_primary",)) or RGBColor(0xFF, 0xFF, 0xFF),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
        shrink_to_fit=True,
    )

    if caption:
        cap_box = slide.shapes.add_textbox(
            margin,
            Length(band_top + Inches(1.0)),
            Length(slide_w - 2 * margin),
            Inches(0.5),
        )
        _fill_text_frame(
            cap_box.text_frame,
            caption,
            token=_typography(tokens, "body", default_size=Pt(14)),
            color=_palette(tokens, ("on_primary",)) or RGBColor(0xEE, 0xEE, 0xEE),
            align=PP_ALIGN.LEFT,
            anchor=MSO_ANCHOR.TOP,
        )

    _apply_transition(slide, transition)
    return slide


# ---------------------------------------------------------------------------
# section_divider
# ---------------------------------------------------------------------------


def section_divider(
    prs: "Presentation",
    *,
    title: str,
    eyebrow: Optional[str] = None,
    progress: Optional[tuple[int, int]] = None,
    tokens: Optional[DesignTokens] = None,
    transition: Optional[str] = None,
) -> "Slide":
    """Append a full-bleed section-divider slide and return it.

    The slide is a coloured backdrop with a left-aligned section title,
    an optional small eyebrow line above the title (e.g. ``"PART TWO"``),
    and an optional progress dot pair like *3 of 7* drawn as a small row
    of dots in the bottom-right corner — useful for orienting the
    audience between deck sections.

    *progress* is a ``(current, total)`` tuple; ``current`` is 1-indexed
    so ``progress=(3, 7)`` highlights the third dot in a row of seven.

    Tokens consumed:

    * **palette** — backdrop fill from ``primary`` (fallback ``neutral``);
      title and eyebrow text from ``on_primary`` (fallback white);
      inactive progress dots from ``muted`` (fallback ``lt2``); active
      progress dot from ``on_primary``.
    * **typography** — ``heading`` for the title; ``body`` for the
      eyebrow.
    """
    slide = _add_blank(prs)
    slide_w, slide_h = _slide_dims(prs)

    # Solid backdrop.
    bg_color = _palette(tokens, ("primary", "neutral")) or RGBColor(0x22, 0x22, 0x33)
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(0), Emu(0), slide_w, slide_h)
    bg.fill.solid()
    bg.fill.fore_color.rgb = bg_color
    bg.line.fill.background()
    bg.text_frame.text = ""

    margin = Inches(0.8)
    title_color = _palette(tokens, ("on_primary",)) or RGBColor(0xFF, 0xFF, 0xFF)

    # Eyebrow above the title (small uppercase-ish caption).
    if eyebrow:
        eb_box = slide.shapes.add_textbox(
            margin,
            Length(slide_h // 2 - Inches(1.0)),
            Length(slide_w - 2 * margin),
            Inches(0.4),
        )
        _fill_text_frame(
            eb_box.text_frame,
            eyebrow,
            token=_typography(tokens, "body", default_size=Pt(14), default_bold=True),
            color=title_color,
            align=PP_ALIGN.LEFT,
            anchor=MSO_ANCHOR.TOP,
        )

    title_top = Length(slide_h // 2 - Inches(0.5))
    title_box = slide.shapes.add_textbox(
        margin, title_top, Length(slide_w - 2 * margin), Inches(2.0)
    )
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(48), default_bold=True),
        color=title_color,
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.MIDDLE,
    )

    # Progress dots: row of `total` dots, the `current`-th highlighted.
    if progress is not None:
        current, total = int(progress[0]), int(progress[1])
        if total < 1 or current < 1 or current > total:
            raise ValueError(f"progress must be (1≤current≤total, total≥1); got {progress!r}")
        dot_d = Inches(0.18)
        dot_gap = Inches(0.10)
        row_w = total * dot_d + (total - 1) * dot_gap
        row_left = Length(slide_w - margin - row_w)
        row_top = Length(slide_h - margin - dot_d)
        active_color = title_color
        inactive_color = _palette(tokens, ("muted", "lt2")) or RGBColor(0x99, 0x99, 0xAA)
        for i in range(total):
            dot_left = Length(row_left + i * (dot_d + dot_gap))
            dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, dot_left, row_top, dot_d, dot_d)
            dot.fill.solid()
            dot.fill.fore_color.rgb = active_color if (i + 1) == current else inactive_color
            dot.line.fill.background()
            dot.text_frame.text = ""

    _apply_transition(slide, transition)
    return slide


# ---------------------------------------------------------------------------
# chart_slide
# ---------------------------------------------------------------------------


def chart_slide(
    prs: "Presentation",
    *,
    title: str,
    chart_type: str = "line",
    categories: Sequence[str],
    series: Sequence[Mapping[str, Any]],
    chart_palette: Optional[Union[str, Sequence[Any]]] = None,
    legend: bool = True,
    smooth: bool = False,
    data_labels: bool = False,
    tokens: Optional[DesignTokens] = None,
    transition: Optional[str] = None,
) -> "Slide":
    """Append a title + chart slide and return it.

    *chart_type* is one of ``"line"``, ``"bar"`` (clustered horizontal
    bars), ``"column"`` (clustered vertical columns), ``"pie"``,
    ``"area"``, ``"line_markers"``, or ``"doughnut"``.  Every one of
    these plots *categories* against numbers; for an XY scatter chart
    build the chart yourself with ``slide.shapes.add_chart`` and
    :class:`~power_pptx.chart.data.XyChartData`.

    *categories* is the list of x-axis labels (or pie-slice labels).
    Each *series* mapping is ``{"name": str, "values": Sequence[float]}``;
    pass a single-series list for pie / doughnut charts.

    *chart_palette* recolours every series.  Accepts:

    * a named built-in (``"modern"``, ``"vibrant"``, ``"monochrome_blue"``,
      …, see :func:`power_pptx.chart.palettes.palette_names`),
    * a list of colours (hex strings, RGBColor, 3-tuples), or
    * ``None`` (default) — falls back to a palette derived from
      *tokens* (``primary`` → ``accent1`` → … → ``positive`` →
      ``negative`` → ``muted``) when at least one of those slots is
      set, and otherwise leaves PowerPoint's default chart_style in
      place.

    *legend* toggles the chart legend (default ``True``).  *smooth*
    smooths the line for line charts (no-op on non-line charts).
    *data_labels* turns on series-level data labels.

    Tokens consumed:

    * **palette** — title from ``primary`` (fallback ``neutral``).
      Series colours are derived from the same palette unless an
      explicit *chart_palette* is supplied.
    * **typography** — ``heading`` for the title.
    """
    from power_pptx.chart.data import CategoryChartData
    from power_pptx.enum.chart import XL_CHART_TYPE

    chart_map = {
        "line": XL_CHART_TYPE.LINE,
        "line_markers": XL_CHART_TYPE.LINE_MARKERS,
        "bar": XL_CHART_TYPE.BAR_CLUSTERED,
        "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
        "pie": XL_CHART_TYPE.PIE,
        "doughnut": XL_CHART_TYPE.DOUGHNUT,
        "area": XL_CHART_TYPE.AREA,
    }
    if chart_type not in chart_map:
        raise ValueError(f"Unknown chart_type {chart_type!r}; choose from {sorted(chart_map)}")

    slide = _add_blank(prs)
    slide_w, slide_h = _slide_dims(prs)
    _apply_background(slide, prs, tokens)

    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(0.9)
    title_box = slide.shapes.add_textbox(margin, title_top, Length(slide_w - 2 * margin), title_h)
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(28), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
        shrink_to_fit=True,
    )

    chart_data = CategoryChartData()
    chart_data.categories = list(categories)
    for s in series:
        chart_data.add_series(str(s.get("name", "")), [float(v) for v in s.get("values", ())])

    chart_top = Length(title_top + title_h + Inches(0.2))
    chart_h = Length(slide_h - chart_top - Inches(0.5))
    gframe = slide.shapes.add_chart(
        chart_map[chart_type],
        margin,
        chart_top,
        Length(slide_w - 2 * margin),
        chart_h,
        chart_data,
    )
    chart = gframe.chart

    # Apply palette (explicit > token-derived > leave default).
    resolved_palette = chart_palette
    if resolved_palette is None:
        resolved_palette = _token_chart_palette(tokens)
    if resolved_palette is not None:
        try:
            if chart_type in ("pie", "doughnut"):
                chart.color_by_category(resolved_palette)
            else:
                chart.apply_palette(resolved_palette)
        except Exception:
            # A misconfigured palette shouldn't fail the whole recipe;
            # the chart still renders with PowerPoint defaults.
            pass

    chart.has_legend = bool(legend)

    if smooth and chart_type in ("line", "line_markers"):
        for s in chart.series:
            with contextlib.suppress(Exception):
                s.smooth = True

    if data_labels:
        for plot in chart.plots:
            with contextlib.suppress(Exception):
                plot.has_data_labels = True

    _apply_transition(slide, transition)
    return slide


# ---------------------------------------------------------------------------
# table_slide
# ---------------------------------------------------------------------------


def table_slide(
    prs: "Presentation",
    *,
    title: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
    banded: bool = True,
    widths: Optional[Sequence[Union[float, Length]]] = None,
    aligns: Optional[Sequence[str]] = None,
    totals: Optional[Mapping[str, Any]] = None,
    tokens: Optional[DesignTokens] = None,
    transition: Optional[str] = None,
) -> "Slide":
    """Append a title + data-table slide and return it.

    *columns* are header strings; each entry of *rows* is a sequence
    with one value per column.  Values are coerced to ``str`` for
    display.

    *banded* (default ``True``) tints alternating data rows with the
    palette's ``surface`` slot to improve scanning.

    *widths* assigns column widths.  Accepts a sequence of either
    fractions of the table width (``[0.5, 0.25, 0.25]``) or absolute
    :class:`~power_pptx.util.Length` values.  Fractions that name every
    column are rescaled to fill the table; when fewer widths than columns are
    given, those columns keep exactly the width asked for and the unspecified
    ones split what remains evenly (``widths=[0.25, 0.25]`` on four columns
    gives four equal columns).  Widths that leave nothing for the unspecified
    columns raise :class:`ValueError`.

    *aligns* assigns horizontal alignment per column.  Accepts
    ``"left"`` / ``"center"`` / ``"right"``; defaults to ``"left"``
    for every column.  Useful for right-aligning numeric columns.

    *totals* adds a footer row that visually separates from the data.
    Mapping shape: ``{"label": "Total", "values": [n1, n2, ...]}`` or
    ``{"row": [c1, c2, c3, ...]}`` for a fully-explicit row.  The label
    takes column 0 and the values fill the last columns, so there can be at
    most one value fewer than there are columns; more raise
    :class:`ValueError`.  The footer is bold and uses ``primary`` palette
    text on a subtle band.

    The table fills the space under the title and its rows share that height
    equally.  When there are too many rows for the text to fit its row, the
    cell margins are tightened first and then the font is shrunk a point at a
    time (never below 9 pt); a table that still cannot fit raises
    :class:`ValueError` suggesting you split it across slides.  Cells are
    assumed to hold a single line of text: a cell that wraps makes its row
    taller than this check can know.

    Tokens consumed:

    * **palette** — title and header text from ``primary`` (fallback
      ``neutral``); header band fill from ``primary``; banded rows from
      ``surface`` (fallback ``lt2``); body text from ``neutral``;
      totals-row band from ``surface`` and totals text from ``primary``.
    * **typography** — ``heading`` for the title; ``body`` for the
      header (bold) and cell text.
    """
    if not columns:
        raise ValueError("table_slide requires at least one column")

    # Everything that can reject the input runs before the slide is added, so a
    # ValueError never leaves a half-built slide behind in the deck.
    slide_w, slide_h = _slide_dims(prs)
    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(0.9)

    n_cols = len(columns)
    totals_row = _coerce_totals_row(totals, n_cols) if totals else None
    n_rows = len(rows) + 1 + (1 if totals_row is not None else 0)
    table_top = Length(title_top + title_h + Inches(0.2))
    table_h = Length(slide_h - table_top - Inches(0.5))
    table_w = Length(slide_w - 2 * margin)
    col_widths = _resolve_column_widths(widths, table_w, n_cols) if widths is not None else None
    align_map = _coerce_aligns(aligns, n_cols)

    header_token = _typography(tokens, "body", default_size=Pt(14), default_bold=True)
    cell_token = _typography(tokens, "body", default_size=Pt(13))
    totals_token = _typography(tokens, "body", default_size=Pt(13), default_bold=True)
    row_tokens = [header_token]
    if rows:
        row_tokens.append(cell_token)
    if totals_row is not None:
        row_tokens.append(totals_token)
    shrink_pt, cell_margin_y = _fit_table_rows(
        n_data=len(rows),
        has_totals=totals_row is not None,
        table_h=int(table_h),
        sizes_pt=[t.size.pt for t in row_tokens if t.size is not None],
    )
    header_token = _shrink_token(header_token, shrink_pt)
    cell_token = _shrink_token(cell_token, shrink_pt)
    totals_token = _shrink_token(totals_token, shrink_pt)

    slide = _add_blank(prs)
    _apply_background(slide, prs, tokens)

    title_box = slide.shapes.add_textbox(margin, title_top, Length(slide_w - 2 * margin), title_h)
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(28), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
        shrink_to_fit=True,
    )

    gframe = slide.shapes.add_table(n_rows, n_cols, margin, table_top, table_w, table_h)
    table = gframe.table

    if col_widths is not None:
        for index, width in enumerate(col_widths):
            table.columns[index].width = Emu(width)

    header_fill = _palette(tokens, ("primary", "neutral")) or RGBColor(0x33, 0x33, 0x33)
    header_text = _palette(tokens, ("on_primary",)) or RGBColor(0xFF, 0xFF, 0xFF)
    band_fill = _palette(tokens, ("surface", "lt2")) or RGBColor(0xF4, 0xF4, 0xF8)
    body_text = _palette(tokens, ("neutral",)) or RGBColor(0x22, 0x22, 0x22)
    totals_text = _palette(tokens, ("primary", "neutral")) or RGBColor(0x22, 0x22, 0x22)

    # Header
    for c, name in enumerate(columns):
        cell = table.cell(0, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = header_fill
        _fill_text_frame(
            cell.text_frame,
            str(name),
            token=header_token,
            color=header_text,
            align=align_map[c],
            anchor=MSO_ANCHOR.MIDDLE,
        )

    # Body
    for r, row in enumerate(rows):
        for c in range(n_cols):
            cell = table.cell(r + 1, c)
            if banded and (r % 2 == 0):
                cell.fill.solid()
                cell.fill.fore_color.rgb = band_fill
            else:
                cell.fill.background()
            value = row[c] if c < len(row) else ""
            _fill_text_frame(
                cell.text_frame,
                str(value),
                token=cell_token,
                color=body_text,
                align=align_map[c],
                anchor=MSO_ANCHOR.MIDDLE,
            )

    # Totals row (footer): tinted band + bold text in the primary palette.
    if totals_row is not None:
        footer_idx = n_rows - 1
        for c in range(n_cols):
            cell = table.cell(footer_idx, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = band_fill
            _fill_text_frame(
                cell.text_frame,
                str(totals_row[c]),
                token=totals_token,
                color=totals_text,
                align=align_map[c],
                anchor=MSO_ANCHOR.MIDDLE,
            )

    for table_row in table.rows:
        for cell in table_row.cells:
            # A table cell takes its vertical alignment from ``a:tcPr``; the ``anchor``
            # that _fill_text_frame puts on the cell's text body is ignored.
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            if cell_margin_y is not None:
                cell.margin_top = cell.margin_bottom = Emu(cell_margin_y)

    _apply_transition(slide, transition)
    return slide


# ---------------------------------------------------------------------------
# code_slide
# ---------------------------------------------------------------------------


def code_slide(
    prs: "Presentation",
    *,
    title: str,
    code: str,
    language: Optional[str] = None,
    tokens: Optional[DesignTokens] = None,
    transition: Optional[str] = None,
) -> "Slide":
    """Append a title + monospace code-block slide and return it.

    When *language* is supplied **and** Pygments is installed, the code
    block is syntax-highlighted using Pygments' ``terminal`` lexer
    output (translated to per-token RGB runs).  Without Pygments — or
    without a *language* — the code is rendered as a plain monospace
    block on the surface fill.

    The code is set in Consolas at 14 pt.  Long snippets shrink a point at a
    time, never below 9 pt, until they fit the panel — lines that wrap count
    for as many lines as they take — and the text frame is also marked to
    shrink at render time as a last resort.  Tabs are expanded to four spaces.
    A snippet that does not fit even at 9 pt raises :class:`ValueError`
    suggesting you split it across slides.

    Tokens consumed:

    * **palette** — title from ``primary`` (fallback ``neutral``); code
      panel fill from ``surface`` (fallback ``lt2``, then a dark
      default); plain code text from ``neutral`` — or white / near-black,
      whichever reads better, when ``neutral`` is unset or too close to the
      panel colour; panel border from ``muted`` (fallback ``lt1``).
    * **typography** — ``heading`` for the title; ``body`` is **not**
      used for the code text (which is locked to Consolas, a single
      monospace family name — an OOXML typeface holds one name, so a
      fallback list such as ``"Menlo, monospace"`` would leave PowerPoint
      and LibreOffice with a proportional face).
    """
    slide_w, slide_h = _slide_dims(prs)
    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(0.9)
    panel_top = Length(title_top + title_h + Inches(0.2))
    panel_h = Length(slide_h - panel_top - Inches(0.5))
    panel_w = Length(slide_w - 2 * margin)
    pad = Inches(0.25)
    code_w = Length(panel_w - 2 * pad)
    code_h = Length(panel_h - 2 * pad)

    # Tab stops are 1 in apart in PowerPoint, which would indent tab-indented code by
    # several inches and invalidate the fit below, so indentation becomes spaces.
    code = code.expandtabs(4)
    # Try to highlight via Pygments; on any failure (missing dep,
    # unknown lexer) fall back to plain monospace text — the slide
    # renders correctly either way.
    highlighted = _pygments_highlight(code, language) if language else None
    lines = (
        highlighted
        if highlighted is not None
        else [[(line, None)] for line in (code.splitlines() or [""])]
    )
    # Decide the size before touching the deck: a snippet that cannot fit raises here,
    # not after a half-built slide has been appended.
    mono_size = _fit_code_size(lines, code_w, code_h)
    mono_family = _CODE_FAMILY

    slide = _add_blank(prs)
    _apply_background(slide, prs, tokens)

    title_box = slide.shapes.add_textbox(margin, title_top, Length(slide_w - 2 * margin), title_h)
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(28), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
        shrink_to_fit=True,
    )

    panel_fill = _palette(tokens, ("surface", "lt2")) or RGBColor(0x14, 0x14, 0x18)
    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, margin, panel_top, panel_w, panel_h)
    panel.fill.solid()
    panel.fill.fore_color.rgb = panel_fill
    border = _palette(tokens, ("muted", "lt1"))
    if border is not None:
        panel.line.color.rgb = border
        panel.line.width = Pt(0.75)
    else:
        panel.line.fill.background()
    _apply_card_styling(panel, tokens)
    panel.text_frame.text = ""

    code_box = slide.shapes.add_textbox(
        Length(margin + pad), Length(panel_top + pad), code_w, code_h
    )
    tf = code_box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP

    # Plain code, and any token the highlighter leaves uncoloured (punctuation, names),
    # takes this colour.  The text box has no fill of its own, so the linter cannot see
    # that it sits on the panel; make sure it reads there.
    fallback_color = _readable_on(_palette(tokens, ("neutral",)), panel_fill)

    para = tf.paragraphs[0]
    para.text = ""
    for line_idx, line_tokens in enumerate(lines):
        p = para if line_idx == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        for text, rgb in line_tokens:
            if not text:
                continue
            run = p.add_run()
            run.text = text
            run.font.name = mono_family
            run.font.size = Pt(mono_size)
            run.font.color.rgb = rgb if rgb is not None else fallback_color

    # A blank line has no run to carry the size, and an empty paragraph falls back
    # to the 18 pt default for its height unless its end mark says otherwise.
    from power_pptx.text.text import Font

    for p in tf.paragraphs:
        end_mark = Font(p._p.get_or_add_endParaRPr())  # pyright: ignore[reportPrivateUsage]
        end_mark.name = mono_family
        end_mark.size = Pt(mono_size)

    # The size above is the baked, measured fit; autofit is the render-time fallback.
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    _apply_transition(slide, transition)
    return slide


# ---------------------------------------------------------------------------
# timeline_slide
# ---------------------------------------------------------------------------

#: Narrowest date / label box a timeline may shrink to; more milestones than that allows raise.
_TIMELINE_MIN_LABEL_W = Inches(0.7)


def timeline_slide(
    prs: "Presentation",
    *,
    title: str,
    milestones: Sequence[Mapping[str, Any]],
    tokens: Optional[DesignTokens] = None,
    transition: Optional[str] = None,
) -> "Slide":
    """Append a horizontal-timeline slide with evenly-spaced milestones.

    Each milestone dict accepts ``date``, ``label``, and an optional
    ``done`` flag (default ``False``).  Completed milestones get the
    ``positive`` palette tint; pending ones use ``muted``.

    The date and label boxes share the rail's width, so a slide can label only
    so many milestones: past about 21 on a 4:3 slide (29 on 16:9) each box would
    be under 0.7 in wide, and the call raises :class:`ValueError` without adding
    a slide.

    Tokens consumed:

    * **palette** — title from ``primary`` (fallback ``neutral``);
      timeline rail from ``muted`` (fallback ``lt1``); pending markers
      from ``muted``; completed markers from ``positive`` (fallback
      ``success``); date / label text from ``neutral``.
    * **typography** — ``heading`` for the title; ``body`` for dates
      and labels.
    """
    if not milestones:
        raise ValueError("timeline_slide requires at least one milestone")

    slide_w, slide_h = _slide_dims(prs)
    margin = Inches(0.6)
    side_gap = Inches(0.1)  # clear space between two text boxes on the same side
    content_w = int(slide_w) - 2 * int(margin)

    # Text boxes on one side sit two milestones apart, so each may be up to two steps
    # wide: the more milestones, the narrower the boxes, until a date no longer reads.
    n = len(milestones)
    label_w = Length(min(int(Inches(2.4)), (2 * content_w - int(side_gap) * (n - 1)) // (n + 1)))
    if label_w < _TIMELINE_MIN_LABEL_W:
        capacity = (2 * content_w + int(side_gap) - int(_TIMELINE_MIN_LABEL_W)) // (
            int(_TIMELINE_MIN_LABEL_W) + int(side_gap)
        )
        raise ValueError(
            f"timeline_slide: {n} milestones leave each label only "
            f"{Emu(label_w).inches:.2f} in on this slide; at most {capacity} fit, "
            "so split the roadmap across slides"
        )

    slide = _add_blank(prs)
    _apply_background(slide, prs, tokens)

    title_top = Inches(0.5)
    title_h = Inches(0.9)
    title_box = slide.shapes.add_textbox(margin, title_top, Length(slide_w - 2 * margin), title_h)
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(28), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
        shrink_to_fit=True,
    )

    # Geometry.  A rail runs through the middle of the slide and milestone text
    # alternates above / below it, so neighbours don't fight for the same space.
    rail_y = Length(slide_h // 2)
    rail_h = Pt(2)
    dot_d = Inches(0.28)
    date_h = Inches(0.3)
    label_h = Inches(0.7)
    text_gap = Inches(0.1)  # clear space between a dot and the text above / below it

    if n == 1:
        rail_left = Length(margin + Inches(0.5))
        rail_right = Length(slide_w - margin - Inches(0.5))
        positions = [Length(rail_left + (rail_right - rail_left) // 2)]
    else:
        # The rail is inset by half a box at either end, which keeps the first and last
        # box inside the slide margins while every box stays centred on its dot.
        rail_left = Length(margin + label_w // 2)
        rail_right = Length(slide_w - margin - label_w // 2)
        span = int(rail_right) - int(rail_left)
        positions = [Length(rail_left + int(round(i * span / (n - 1)))) for i in range(n)]

    rail = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        rail_left,
        Length(rail_y - rail_h // 2),
        Length(rail_right - rail_left),
        rail_h,
    )
    rail_color = _palette(tokens, ("muted", "lt1")) or RGBColor(0xBB, 0xBB, 0xBB)
    rail.fill.solid()
    rail.fill.fore_color.rgb = rail_color
    rail.line.fill.background()
    rail.text_frame.text = ""

    date_texts = [str(ms.get("date", "")) for ms in milestones]
    label_texts = [str(ms.get("label", "")) for ms in milestones]
    # The deck's body size is not necessarily 11-12 pt, but the boxes are fixed: bake
    # one size per row at which every date / label actually fits its box.
    inner_w = int(label_w) - 2 * int(_DEFAULT_INSET_X)
    date_token = _fit_token(
        _typography(tokens, "body", default_size=Pt(11), default_bold=True),
        date_texts,
        inner_w,
        int(date_h) - 2 * int(_DEFAULT_INSET_Y),
    )
    body_token = _fit_token(
        _typography(tokens, "body", default_size=Pt(12)),
        label_texts,
        inner_w,
        int(label_h) - 2 * int(_DEFAULT_INSET_Y),
    )
    body_color = _palette(tokens, ("neutral",)) or RGBColor(0x22, 0x22, 0x22)
    pending_color = rail_color
    done_color = _palette(tokens, ("positive", "success")) or RGBColor(0x00, 0x8A, 0x3C)

    dots: list[Any] = []
    for i, ms in enumerate(milestones):
        cx = positions[i]
        # Milestone dot.
        dot = slide.shapes.add_shape(
            MSO_SHAPE.OVAL,
            Length(cx - dot_d // 2),
            Length(rail_y - dot_d // 2),
            dot_d,
            dot_d,
        )
        dot.fill.solid()
        dot.fill.fore_color.rgb = done_color if ms.get("done") else pending_color
        dot.line.fill.background()
        dot.text_frame.text = ""
        dots.append(dot)

        # Above the rail the label sits next to the dot and the date above it; below
        # the rail the date sits next to the dot and the label under it.  Either way
        # the date is read first, and neither box touches the rail or the dot.
        if i % 2 == 0:
            label_top = Length(rail_y - dot_d // 2 - text_gap - label_h)
            date_top = Length(label_top - date_h)
        else:
            date_top = Length(rail_y + dot_d // 2 + text_gap)
            label_top = Length(date_top + date_h)

        left = Length(cx - label_w // 2)
        if date_texts[i]:
            db = slide.shapes.add_textbox(left, date_top, label_w, date_h)
            _fill_text_frame(
                db.text_frame,
                date_texts[i],
                token=date_token,
                color=body_color,
                align=PP_ALIGN.CENTER,
                anchor=MSO_ANCHOR.TOP,
                shrink_to_fit=True,
            )
        if label_texts[i]:
            lb = slide.shapes.add_textbox(left, label_top, label_w, label_h)
            _fill_text_frame(
                lb.text_frame,
                label_texts[i],
                token=body_token,
                color=body_color,
                align=PP_ALIGN.CENTER,
                anchor=MSO_ANCHOR.TOP,
                shrink_to_fit=True,
            )

    # The dots sit on the rail by design.  Allow exactly those overlaps — a blanket
    # lint group would also hide a text box that really did land on the rail.
    rail.allow_overlap_with(*dots)

    _apply_transition(slide, transition)
    return slide


# ---------------------------------------------------------------------------
# comparison_slide
# ---------------------------------------------------------------------------


def comparison_slide(
    prs: "Presentation",
    *,
    title: str,
    left_heading: str,
    right_heading: str,
    rows: Sequence[Mapping[str, Any]],
    tokens: Optional[DesignTokens] = None,
    transition: Optional[str] = None,
) -> "Slide":
    """Append a two-column comparison slide with matched left/right rows.

    Each *rows* mapping is ``{"left": str, "right": str}`` (a label
    column is *not* drawn — the comparison is intended for prose
    bullets).  Rows are evenly spaced down the slide so the left and
    right entries always line up.

    Tokens consumed:

    * **palette** — title from ``primary`` (fallback ``neutral``);
      column heading band from ``primary``; heading text from
      ``on_primary``; row text from ``neutral``; even-row tint from
      ``surface`` (fallback ``lt2``).
    * **typography** — ``heading`` for the title and column headings;
      ``body`` for the row text.  The headings sit in bands a fixed 0.6 in
      tall, so their size is the token's size reduced (never below 9 pt) just
      far enough that both fit their band.
    """
    slide = _add_blank(prs)
    slide_w, slide_h = _slide_dims(prs)
    _apply_background(slide, prs, tokens)

    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(0.9)
    title_box = slide.shapes.add_textbox(margin, title_top, Length(slide_w - 2 * margin), title_h)
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(28), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
        shrink_to_fit=True,
    )

    gap = Inches(0.3)
    col_w = Length((slide_w - 2 * margin - gap) // 2)
    col_top = Length(title_top + title_h + Inches(0.2))
    col_h = Length(slide_h - col_top - Inches(0.5))

    head_h = Inches(0.6)
    head_color = _palette(tokens, ("primary", "neutral")) or RGBColor(0x33, 0x33, 0x33)
    head_text_color = _palette(tokens, ("on_primary",)) or RGBColor(0xFF, 0xFF, 0xFF)
    row_text_color = _palette(tokens, ("neutral",)) or RGBColor(0x22, 0x22, 0x22)
    band_color = _palette(tokens, ("surface", "lt2")) or RGBColor(0xF4, 0xF4, 0xF8)
    # The bands are a fixed height, whatever size the deck's heading type is: bake the one
    # size at which both headings fit (never larger than the token's own).
    head_token = _fit_token(
        _typography(tokens, "heading", default_size=Pt(18), default_bold=True),
        [left_heading, right_heading],
        int(col_w) - 2 * int(_DEFAULT_INSET_X),
        int(head_h) - 2 * int(_DEFAULT_INSET_Y),
    )
    row_token = _typography(tokens, "body", default_size=Pt(14))

    columns = [
        (margin, left_heading, "left"),
        (Length(margin + col_w + gap), right_heading, "right"),
    ]

    n_rows = max(1, len(rows))
    row_h = Length((col_h - head_h) // n_rows)

    for col_left, heading, key in columns:
        # Heading band.
        band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, col_left, col_top, col_w, head_h)
        band.fill.solid()
        band.fill.fore_color.rgb = head_color
        band.line.fill.background()
        _fill_text_frame(
            band.text_frame,
            heading,
            token=head_token,
            color=head_text_color,
            align=PP_ALIGN.LEFT,
            anchor=MSO_ANCHOR.MIDDLE,
            shrink_to_fit=True,
        )
        # Rows.
        for i, row in enumerate(rows):
            r_top = Length(col_top + head_h + i * row_h)
            if i % 2 == 0:
                tile = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, col_left, r_top, col_w, row_h)
                tile.fill.solid()
                tile.fill.fore_color.rgb = band_color
                tile.line.fill.background()
                tile.text_frame.text = ""
            text = str(row.get(key, ""))
            tb = slide.shapes.add_textbox(
                Length(col_left + Inches(0.2)),
                Length(r_top + Inches(0.05)),
                Length(col_w - Inches(0.4)),
                Length(row_h - Inches(0.1)),
            )
            _fill_text_frame(
                tb.text_frame,
                text,
                token=row_token,
                color=row_text_color,
                align=PP_ALIGN.LEFT,
                anchor=MSO_ANCHOR.MIDDLE,
                shrink_to_fit=True,
            )

    _apply_transition(slide, transition)
    return slide


# ---------------------------------------------------------------------------
# figure_slide — embed Plotly / Matplotlib / SVG / HTML / image figures.
# ---------------------------------------------------------------------------


def figure_slide(
    prs: "Presentation",
    *,
    title: str,
    figure: Any,
    caption: Optional[str] = None,
    figure_format: str = "auto",
    tokens: Optional[DesignTokens] = None,
    transition: Optional[str] = None,
) -> "Slide":
    """Append a title + embedded-figure slide and return it.

    *figure* is dispatched by type:

    * a Plotly ``Figure`` (or anything with ``.to_image``) → rendered
      via :func:`power_pptx.design.figures.add_plotly_figure`.
    * a Matplotlib ``Figure`` (or anything with ``.savefig``) →
      :func:`add_matplotlib_figure`.
    * a string starting with ``"<svg"`` (after lstrip) or ``bytes``
      whose head matches the SVG sniff → :func:`add_svg_figure`.  Inline
      markup needs ``cairosvg`` (``pip install cairosvg``) to draw the PNG
      companion that PowerPoint requires; without it
      :class:`~power_pptx._svg.CairoSvgUnavailable` is raised, and
      calling :func:`add_svg_figure` yourself with ``png_fallback=`` is
      the way around that.
    * a string starting with ``"<"`` (any other tag) → treated as an
      HTML snippet and rendered via :func:`add_html_figure` (needs
      Playwright).
    * a path to a file → routed to ``add_picture`` for raster types
      (.png/.jpg/.jpeg/.bmp/.tif/.gif) or ``add_svg_picture`` for
      ``.svg``.

    *figure_format* (``"auto"`` / ``"svg"`` / ``"png"``) is forwarded
    to the Plotly / Matplotlib adapter; ignored for SVG / HTML / image
    inputs.

    *caption* is rendered in the bottom-right corner if supplied.

    Tokens consumed:

    * **palette** — title from ``primary`` (fallback ``neutral``);
      caption from ``muted`` (fallback ``neutral``).
    * **typography** — ``heading`` for the title; ``body`` for the
      caption.
    """
    slide = _add_blank(prs)
    slide_w, slide_h = _slide_dims(prs)
    _apply_background(slide, prs, tokens)

    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(0.9)
    title_box = slide.shapes.add_textbox(margin, title_top, Length(slide_w - 2 * margin), title_h)
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(28), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
        shrink_to_fit=True,
    )

    fig_top = Length(title_top + title_h + Inches(0.2))
    cap_h = Inches(0.4) if caption else Length(0)
    fig_h = Length(slide_h - fig_top - Inches(0.5) - cap_h)
    fig_w = Length(slide_w - 2 * margin)

    _embed_figure(slide, figure, margin, fig_top, fig_w, fig_h, figure_format)

    if caption:
        cap_top = Length(slide_h - Inches(0.5) - cap_h)
        cap_box = slide.shapes.add_textbox(margin, cap_top, fig_w, cap_h)
        _fill_text_frame(
            cap_box.text_frame,
            caption,
            token=_typography(tokens, "body", default_size=Pt(12), default_italic=True),
            color=_palette(tokens, ("muted", "neutral")),
            align=PP_ALIGN.RIGHT,
            anchor=MSO_ANCHOR.TOP,
        )

    _apply_transition(slide, transition)
    return slide


_RASTER_EXTS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"})


def _embed_figure(
    slide: "Slide",
    figure: Any,
    left: Length,
    top: Length,
    width: Length,
    height: Length,
    figure_format: str,
) -> None:
    """Dispatch *figure* by type to the matching figures-module adapter."""
    from power_pptx.design import figures as _figures

    # Plotly figure: detected by duck-typed .to_image().
    if hasattr(figure, "to_image") and callable(figure.to_image):
        _figures.add_plotly_figure(slide, figure, left, top, width, height, format=figure_format)
        return

    # Matplotlib figure: detected by duck-typed .savefig().
    if hasattr(figure, "savefig") and callable(figure.savefig):
        _figures.add_matplotlib_figure(
            slide, figure, left, top, width, height, format=figure_format
        )
        return

    # File path: dispatch by extension.
    if isinstance(figure, (str, os.PathLike)) and not _is_markup_string(figure):
        ext = os.path.splitext(str(figure))[1].lower()
        if ext == ".svg":
            _figures.add_svg_figure(slide, figure, left, top, width, height)
            return
        if ext in _RASTER_EXTS:
            slide.shapes.add_picture(str(figure), left, top, width, height)
            return
        # Unknown extension — best-effort raster.
        slide.shapes.add_picture(str(figure), left, top, width, height)
        return

    # Bytes / strings: SVG sniff vs HTML.
    if isinstance(figure, (bytes, bytearray, str)):
        data = figure.encode("utf-8", "replace") if isinstance(figure, str) else bytes(figure)
        head = data[:512].lstrip(b"\xef\xbb\xbf").lstrip()  # a UTF-8 BOM, then blanks
        if head.startswith(b"<?xml") or b"<svg" in head[:200]:
            # add_svg_picture reads a ``str`` as a *path* (and a ``bytes`` as the
            # document itself), so inline markup has to be handed over encoded.
            _figures.add_svg_figure(slide, data, left, top, width, height)
            return
        if head.startswith(b"<"):
            _figures.add_html_figure(
                slide, figure if isinstance(figure, str) else data, left, top, width, height
            )
            return

    raise TypeError(
        f"figure_slide can't dispatch a figure of type {type(figure).__name__!r}; "
        "pass a Plotly Figure, a Matplotlib Figure, an SVG / HTML "
        "string, an image path, or raw bytes."
    )


def _is_markup_string(value: Any) -> bool:
    """Return True when *value* looks like inline SVG / HTML rather than a path.

    Markup detection has to come *before* the path-separator check because
    inline SVG routinely contains namespace URLs (``xmlns="http://..."``)
    whose ``/`` characters would otherwise mis-route the figure to
    :meth:`add_picture` and raise :class:`FileNotFoundError`.

    Recognised markup forms:

    * ``<?xml`` declarations
    * ``<!DOCTYPE`` declarations
    * ``<!--`` comments
    * ``<svg``, ``<html``, or any other ``<tagname`` opening tag
    * ``</tagname>`` closing tags

    Anything else starting with ``<`` (e.g. an exotic filename) falls
    through to the path heuristic.
    """
    if not isinstance(value, str):
        return False
    # A byte-order mark survives ``open(path).read()`` on a BOM-prefixed file and is
    # not whitespace to ``str.lstrip``.
    s = value.lstrip("﻿").lstrip()
    if not s.startswith("<"):
        return False
    # XML declarations, doctypes, comments.
    if s.startswith(("<?xml", "<!DOCTYPE", "<!--", "<svg", "<html")):
        return True
    # ``<tagname`` (opening) or ``</tagname>`` (closing) — both are
    # markup; differentiate from a stray ``<`` in a filename by
    # requiring an ASCII letter after the optional ``/``.
    # A truly unrecognised ``<…`` is treated as a path (rare on real
    # input, but preserves the historical behaviour for the corner case
    # of weird filenames that happen to start with ``<``).
    rest = s[2:] if s.startswith("</") else s[1:]
    return bool(rest and rest[0].isalpha())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _add_blank(prs: "Presentation") -> "Slide":
    layouts = prs.slide_layouts
    blank = layouts.get_by_name("Blank")
    if blank is None:
        blank = layouts[-1]
    return prs.slides.add_slide(blank)


def _apply_background(slide: "Slide", prs: "Presentation", tokens: Optional[DesignTokens]) -> None:
    """Lay down a full-bleed ``palette["background"]`` rectangle behind a recipe.

    No-op unless the token set defines a ``background`` palette slot, so the
    default (master-inherited white) is preserved for callers who don't opt
    in.  When set, a deck that mixes hand-built slides (which honour the token
    background) with recipe slides stays visually consistent instead of
    showing two different "whites".  The rectangle is added first so it sits
    behind every other shape the recipe places.
    """
    if tokens is None:
        return
    bg = tokens.palette.get("background")
    if bg is None:
        return
    slide_w, slide_h = _slide_dims(prs)
    rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(0), Emu(0), slide_w, slide_h)
    rect.fill.solid()
    rect.fill.fore_color.rgb = bg
    rect.line.fill.background()
    rect.text_frame.text = ""


def _slide_dims(prs: "Presentation") -> tuple[Length, Length]:
    width = prs.slide_width or Inches(13.333)
    height = prs.slide_height or Inches(7.5)
    return width, height


def _palette(tokens: Optional[DesignTokens], names: Sequence[str]) -> Optional[RGBColor]:
    if tokens is None:
        return None
    for name in names:
        rgb = tokens.palette.get(name)
        if rgb is not None:
            return rgb
    return None


def _typography(
    tokens: Optional[DesignTokens],
    name: str,
    *,
    default_size: Length,
    default_bold: Optional[bool] = None,
    default_italic: Optional[bool] = None,
) -> TypographyToken:
    """Return the named token from *tokens* or a sensible default."""
    if tokens is not None:
        existing = tokens.typography.get(name)
        if existing is not None:
            # Backfill any unset fields from the recipe defaults so callers
            # don't have to repeat them.
            return TypographyToken(
                family=existing.family,
                size=existing.size if existing.size is not None else default_size,
                bold=existing.bold if existing.bold is not None else default_bold,
                italic=existing.italic if existing.italic is not None else default_italic,
                color=existing.color,
            )
    return TypographyToken(
        family="Calibri",
        size=default_size,
        bold=default_bold,
        italic=default_italic,
    )


def _apply_typography(font: Any, token: TypographyToken) -> None:
    font.name = token.family
    if token.size is not None:
        font.size = token.size
    if token.bold is not None:
        font.bold = token.bold
    if token.italic is not None:
        font.italic = token.italic
    if token.color is not None:
        font.color.rgb = token.color


def _fill_text_frame(
    text_frame: Any,
    text: str,
    *,
    token: TypographyToken,
    color: Optional[RGBColor],
    align: PP_ALIGN,
    anchor: MSO_ANCHOR,
    word_wrap: bool = True,
    shrink_to_fit: bool = False,
) -> None:
    text_frame.word_wrap = word_wrap
    text_frame.vertical_anchor = anchor
    if shrink_to_fit:
        # Tell PowerPoint to scale the text down when it doesn't fit
        # the reserved frame.  Used by the recipe titles whose
        # text-region height is fixed by the recipe geometry — without
        # this, a long title wraps to a second line that overlaps the
        # body region below (see IMPROVEMENTS item 11).
        from power_pptx.enum.text import MSO_AUTO_SIZE

        text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    para = text_frame.paragraphs[0]
    para.alignment = align
    # Clear any default text and add a fresh run we can style.
    para.text = ""
    run = para.add_run()
    run.text = text
    _apply_typography(run.font, token)
    if color is not None:
        run.font.color.rgb = color


# ---------------------------------------------------------------------------
# Text measurement — a deterministic fit model that needs no font file
# ---------------------------------------------------------------------------
#
# A recipe owns the geometry of the boxes it fills, so it has to know whether
# the text fits *before* anything renders.  ``TextFrame.fit_text`` is the right
# tool when a real font file is at hand, but it flows a whole frame as a single
# paragraph (explicit line breaks and indentation are ignored) and warns when
# the named family isn't installed.  The recipes therefore use the small
# conservative model below: the per-character width and line pitch that the
# linter's own overflow heuristic assumes, plus a greedy word wrap that honours
# line breaks.  It over-estimates slightly, which is the safe direction.

_EMU_PER_PT = 12700
#: Average advance of a mixed-case proportional face, as a fraction of the font size.
_PROPORTIONAL_EM = 0.55
#: ... of its bold weight.
_BOLD_EM = 0.58
#: Widest common monospace advance (Courier New, Menlo, DejaVu Sans Mono).
_MONOSPACE_EM = 0.6
#: Rendered line height as a multiple of the font size.
_LINE_PITCH = 1.2
#: Smallest size the recipes shrink text to; matches the linter's MinFontSize threshold.
_MIN_LEGIBLE_PT = 9.0
#: Inset python-pptx text frames carry until told otherwise (left/right, top/bottom).
_DEFAULT_INSET_X = Inches(0.1)
_DEFAULT_INSET_Y = Inches(0.05)


def _wrapped_line_count(
    text: str, width: int, size_pt: float, *, bold: bool = False, mono: bool = False
) -> int:
    """Estimate the lines *text* occupies in a box *width* EMU wide at *size_pt*.

    Explicit line breaks start a new line, words wrap greedily at spaces, and a
    word wider than the box is broken mid-word — the way PowerPoint and
    LibreOffice both lay out a wrapped text frame.  Monospace text keeps its
    leading indentation (tabs count as four columns); proportional text does
    not need to, but is handled by the same loop.
    """
    em = _MONOSPACE_EM if mono else (_BOLD_EM if bold else _PROPORTIONAL_EM)
    per_line = max(1, int(width / (em * size_pt * _EMU_PER_PT)))
    total = 0
    for line in re.split(r"[\n\v]", text):
        if mono:
            line = line.expandtabs(4)
        lines, used = 1, 0
        for token in re.findall(r"\s+|\S+", line):
            n = len(token)
            if token.isspace():
                # Whitespace that overruns the box is swallowed by the break, so
                # it only ever fills the line; the next word decides to wrap.
                used = min(per_line, used + n)
                continue
            if used + n > per_line and used > 0:
                lines += 1
                used = 0
            while n > per_line:
                lines += 1
                n -= per_line
            used += n
        total += lines
    return total


def _text_height(
    text: str, width: int, size_pt: float, *, bold: bool = False, mono: bool = False
) -> int:
    """Estimated height in EMU of *text* wrapped to *width* EMU at *size_pt*."""
    lines = _wrapped_line_count(text, width, size_pt, bold=bold, mono=mono)
    return int(lines * size_pt * _LINE_PITCH * _EMU_PER_PT)


def _fit_font_size(
    text: str,
    width: int,
    height: int,
    *,
    max_pt: float,
    min_pt: float = _MIN_LEGIBLE_PT,
    bold: bool = False,
    mono: bool = False,
) -> Optional[float]:
    """Return the largest size at which *text* fits *width* × *height* EMU, or ``None``.

    Tries *max_pt* first (so a size that already fits is never changed), then
    each whole point below it down to *min_pt*.  ``None`` means even *min_pt*
    overflows.  A *max_pt* already below *min_pt* is its own floor — the model
    never enlarges text it was asked to keep small.
    """
    floor = min(min_pt, max_pt)
    size = float(max_pt)
    while size >= floor:
        if _text_height(text, width, size, bold=bold, mono=mono) <= height:
            return size
        size = float(math.ceil(size) - 1)
    return None


def _fit_token(
    token: TypographyToken, texts: Sequence[str], width: int, height: int
) -> TypographyToken:
    """Return *token* resized so every one of *texts* fits a *width* × *height* box.

    A row of sibling labels reads as one system only when they share a size, so
    the size is the smallest any single text needs, and never larger than the
    token's own.  A text that does not fit even at the legibility floor pins the
    result to that floor; the box's autofit flag is the last line of defence.
    """
    max_pt = token.size.pt if token.size is not None else 12.0
    floor = min(_MIN_LEGIBLE_PT, max_pt)
    chosen = max_pt
    for text in texts:
        if not text:
            continue
        fit = _fit_font_size(text, width, height, max_pt=max_pt, bold=bool(token.bold))
        chosen = min(chosen, floor if fit is None else fit)
    return replace(token, size=Pt(chosen))


def _apply_transition(slide: "Slide", transition: Optional[str]) -> None:
    if not transition:
        return
    from power_pptx.enum.presentation import MSO_TRANSITION_TYPE

    key = transition.upper().replace("-", "_")
    member = getattr(MSO_TRANSITION_TYPE, key, None)
    if member is None:
        raise ValueError(
            f"Unknown transition {transition!r}; "
            f"see power_pptx.enum.presentation.MSO_TRANSITION_TYPE for valid values"
        )
    slide.transition.kind = member


def _delta_color(tokens: Optional[DesignTokens], sign: int) -> RGBColor:
    """Return the palette color tinting a delta with ``sign`` (+1 / -1 / 0).

    ``sign == 0`` and ``sign > 0`` both use the positive slot; only
    strictly-negative deltas use the negative slot.
    """
    if sign >= 0:
        return _palette(tokens, ("positive", "success")) or RGBColor(0x00, 0x8A, 0x3C)
    return _palette(tokens, ("negative", "danger")) or RGBColor(0xCC, 0x00, 0x00)


# Magnitude at or below which a numeric delta is treated as a fraction
# (``0.27`` → ``+27%``).  Outside this range we render the raw number
# with one decimal so callers who already pass percentages — ``14.0`` —
# don't get them silently multiplied by 100.
_DELTA_FRACTION_LIMIT = 1.0


def _resolve_delta(kpi: Mapping[str, Any]) -> tuple[Optional[str], int]:
    """Resolve the formatted delta string and sign from a KPI dict.

    Returns ``(text, sign)`` where *text* is ``None`` when no delta was
    supplied.  The auto-detect rules:

    * ``delta_text="…"`` — explicit string passthrough wins outright.
    * ``delta="…"`` (string) — used verbatim; sign is inferred from a
      leading ``-`` / ``−`` if present.
    * ``delta`` (numeric) with ``|delta| <= 1.0`` — formatted as a
      signed percentage.
    * ``delta`` (numeric) with ``|delta| > 1.0`` — formatted as a
      signed number with one decimal place.
    """
    explicit = kpi.get("delta_text")
    if explicit is not None:
        s = str(explicit)
        sign = -1 if s.lstrip().startswith(("-", "−", "–")) else 1
        return s, sign

    delta = kpi.get("delta")
    if delta is None:
        return None, 0
    if isinstance(delta, str):
        sign = -1 if delta.lstrip().startswith(("-", "−", "–")) else 1
        return delta, sign

    d_val = float(delta)
    sign = -1 if d_val < 0 else 1
    sign_glyph = "+" if d_val >= 0 else "−"  # proper minus glyph
    if abs(d_val) <= _DELTA_FRACTION_LIMIT:
        text = f"{sign_glyph}{abs(d_val):.0%}"
    else:
        text = f"{sign_glyph}{abs(d_val):.1f}"
    return text, sign


def _pygments_highlight(
    code: str, language: Optional[str]
) -> Optional[list[list[tuple[str, Optional[RGBColor]]]]]:
    """Return per-line lists of ``(text, RGBColor)`` runs, or ``None``.

    ``None`` covers every soft-failure path: Pygments missing, lexer
    unknown, formatter error.  Callers fall back to plain text in that
    case so the slide still renders.
    """
    if not language:
        return None
    try:
        from pygments import lex  # type: ignore[import-not-found]
        from pygments.lexers import get_lexer_by_name  # type: ignore[import-not-found]
        from pygments.token import Token  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        lexer = get_lexer_by_name(language)
    except Exception:
        return None

    # A small token-class → hex map.  Pygments has built-in styles but
    # they're tuned for HTML output; using a hand-picked map keeps the
    # slide colors in a single, reviewable place.
    #
    # Operator/Punctuation/Text are mapped to the sentinel ``None`` so
    # they fall through to ``fallback_color`` at render time.  Hard-coding
    # ``#D4D4D4`` (a light grey) here would render as nearly-invisible
    # punctuation on light token themes — and ``.`` in member access
    # (``optimiser.zero_grad``) is its own Pygments token, so the
    # consequence was code reading as ``optimiser zero_grad`` on slides
    # that used a light surface.  Routing these through ``fallback_color``
    # keeps them legible on whichever theme the caller is using.
    color_map: dict[Any, Optional[str]] = {
        Token.Keyword: "#C586C0",
        Token.Keyword.Constant: "#569CD6",
        Token.Keyword.Namespace: "#C586C0",
        Token.Name.Function: "#DCDCAA",
        Token.Name.Class: "#4EC9B0",
        Token.Name.Builtin: "#4EC9B0",
        Token.Name.Decorator: "#DCDCAA",
        Token.String: "#CE9178",
        Token.String.Doc: "#608B4E",
        Token.Number: "#B5CEA8",
        Token.Comment: "#6A9955",
        Token.Comment.Single: "#6A9955",
        Token.Comment.Multiline: "#6A9955",
        Token.Operator: None,
        Token.Punctuation: None,
        Token.Text: None,
    }

    def _color_for(tok_type: Any) -> Optional[RGBColor]:
        # Pygments token types are hierarchical: walk up to the nearest
        # mapped ancestor so e.g. ``Token.String.Single`` reuses the
        # ``Token.String`` color.  A mapped entry of ``None`` means
        # "use the fallback colour" — explicit no-color rather than
        # falling further up the hierarchy.
        t = tok_type
        while t is not None:
            if t in color_map:
                hex_str = color_map[t]
                if hex_str is None:
                    return None
                hex_str = hex_str.lstrip("#")
                return RGBColor(
                    int(hex_str[0:2], 16),
                    int(hex_str[2:4], 16),
                    int(hex_str[4:6], 16),
                )
            t = getattr(t, "parent", None)
        return None

    try:
        tokens = list(lex(code, lexer))
    except Exception:
        return None

    lines: list[list[tuple[str, Optional[RGBColor]]]] = [[]]
    for tok_type, value in tokens:
        rgb = _color_for(tok_type)
        # Pygments emits newlines as their own runs / inside strings;
        # split here so we honour them as paragraph breaks rather than
        # rendering literal newline characters in a single-line run.
        chunks = value.split("\n")
        for j, chunk in enumerate(chunks):
            if chunk:
                lines[-1].append((chunk, rgb))
            if j < len(chunks) - 1:
                lines.append([])
    return lines


def _readable_on(preferred: Optional[RGBColor], background: RGBColor) -> RGBColor:
    """Return *preferred* if it reads on *background* (WCAG AA), else white or near-black.

    Whichever of the two defaults contrasts more with *background* is used when
    *preferred* is missing or too close to it.
    """
    from power_pptx.lint import (
        _CONTRAST_THRESHOLD,  # pyright: ignore[reportPrivateUsage]
        _contrast_ratio,  # pyright: ignore[reportPrivateUsage]
    )

    if preferred is not None and _contrast_ratio(preferred, background) >= _CONTRAST_THRESHOLD:
        return preferred
    dark, light = RGBColor(0x22, 0x22, 0x22), RGBColor(0xF2, 0xF2, 0xF2)
    return max((dark, light), key=lambda color: _contrast_ratio(color, background))


#: Typeface of ``code_slide``.  One family name: an OOXML ``a:latin typeface`` is not a
#: CSS font stack, so a comma-separated fallback list resolves to no font at all.
_CODE_FAMILY = "Consolas"
#: Size ``code_slide`` starts from before shrinking long snippets.
_CODE_MAX_PT = 14.0


def _fit_code_size(
    lines: Sequence[Sequence[tuple[str, Optional[RGBColor]]]], width: int, height: int
) -> float:
    """Return the largest size at which *lines* of code fit a *width* × *height* text box.

    Wrapped lines count as the lines they occupy and the text frame's default insets
    are subtracted.  Raises :class:`ValueError` when even the legibility floor does not
    fit, saying how much would.
    """
    text = "\n".join("".join(chunk for chunk, _ in line) for line in lines)
    inner_w = int(width) - 2 * int(_DEFAULT_INSET_X)
    inner_h = int(height) - 2 * int(_DEFAULT_INSET_Y)
    size = _fit_font_size(text, inner_w, inner_h, max_pt=_CODE_MAX_PT, mono=True)
    if size is None:
        rows = int(inner_h / (_MIN_LEGIBLE_PT * _LINE_PITCH * _EMU_PER_PT))
        columns = int(inner_w / (_MONOSPACE_EM * _MIN_LEGIBLE_PT * _EMU_PER_PT))
        raise ValueError(
            f"code_slide: {len(lines)} lines of code do not fit on one slide, even at "
            f"{_MIN_LEGIBLE_PT:g} pt (about {rows} lines of up to {columns} characters fit); "
            "split the snippet across several slides or trim it"
        )
    return size


_ALIGN_MAP: dict[str, PP_ALIGN] = {
    "left": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
}


def _coerce_aligns(aligns: Optional[Sequence[str]], n_cols: int) -> list[PP_ALIGN]:
    if aligns is None:
        return [PP_ALIGN.LEFT] * n_cols
    out: list[PP_ALIGN] = []
    for i in range(n_cols):
        if i >= len(aligns):
            out.append(PP_ALIGN.LEFT)
            continue
        a = aligns[i]
        if isinstance(a, PP_ALIGN):
            out.append(a)
            continue
        key = str(a).lower()
        if key not in _ALIGN_MAP:
            raise ValueError(f"align[{i}] must be one of {sorted(_ALIGN_MAP)}, got {a!r}")
        out.append(_ALIGN_MAP[key])
    return out


def _resolve_column_widths(
    widths: Sequence[Union[float, Length]], table_w: int, n_cols: int
) -> list[int]:
    """Turn *widths* into one EMU width per column.

    Supports two input modes:

    * **Fractions**: values < 5 are treated as fractions of *table_w*.
    * **Absolute lengths**: any :class:`Length` (or value ≥ 5) is taken
      verbatim.

    When *widths* names every column and uses fractions, they are rescaled to fill
    *table_w* if they stray more than 1% from it (so a slightly-off list still lays
    out).  When it names *fewer* columns, the named ones keep exactly the width
    asked for and the rest share what remains evenly, the remainder going to the
    last one so the columns add up to *table_w*.  Raises :class:`ValueError` if
    nothing remains for the unspecified columns — they would be zero-width.
    """
    specified: list[int] = []
    uses_fractions = False
    for w in widths[:n_cols]:
        if isinstance(w, Length):
            specified.append(int(w))
        elif float(w) < 5:
            uses_fractions = True
            specified.append(int(round(float(w) * table_w)))
        else:
            specified.append(int(w))

    unspecified = n_cols - len(specified)
    if unspecified > 0:
        remaining = table_w - sum(specified)
        if remaining <= 0:
            raise ValueError(
                f"widths= names {len(specified)} of {n_cols} columns but already takes "
                f"{Emu(sum(specified)).inches:.2f} in of the {Emu(table_w).inches:.2f} in "
                f"table, leaving no room for the other {unspecified}; give the named "
                "columns less width or name every column"
            )
        share, extra = divmod(remaining, unspecified)
        specified += [share] * unspecified
        specified[-1] += extra
    elif uses_fractions:
        total = sum(specified)
        if total > 0 and abs(total - table_w) > table_w * 0.01:
            specified = [int(round(v * table_w / total)) for v in specified]
            specified[-1] += table_w - sum(specified)
    return specified


#: Top/bottom cell margin a table cell has until told otherwise.
_TABLE_CELL_MARGIN_Y = int(_DEFAULT_INSET_Y)
#: Margin ``table_slide`` drops to, before shrinking any text, when rows run short.
_TABLE_COMPACT_MARGIN_Y = int(Inches(0.02))


def _table_row_need(size_pt: float, margin_y: int) -> int:
    """EMU a row needs for one line of *size_pt* text: its line height plus both margins."""
    return int(size_pt * _LINE_PITCH * _EMU_PER_PT) + 2 * margin_y


def _shrunk_pt(size_pt: float, shrink_pt: float) -> float:
    """*size_pt* reduced by *shrink_pt*, but not below the legibility floor.

    Text already smaller than the floor is left alone rather than enlarged.
    """
    return max(size_pt - shrink_pt, min(size_pt, _MIN_LEGIBLE_PT))


def _shrink_token(token: TypographyToken, shrink_pt: float) -> TypographyToken:
    """Return *token* with its size reduced by *shrink_pt* (see :func:`_shrunk_pt`)."""
    if not shrink_pt or token.size is None:
        return token
    return replace(token, size=Pt(_shrunk_pt(token.size.pt, shrink_pt)))


def _fit_table_rows(
    *, n_data: int, has_totals: bool, table_h: int, sizes_pt: Sequence[float]
) -> tuple[float, Optional[int]]:
    """Choose how far a table must be tightened for its rows to hold their text.

    The table's rows share *table_h* equally, and each has to be at least as tall
    as one line of its text plus the cell margins.  The cheapest change that gets
    there wins: nothing at all, then compact cell margins, then compact margins and
    a font shrunk a point at a time (never below the legibility floor).  Returns
    ``(shrink_pt, margin_y)`` where ``margin_y`` is ``None`` for "leave the margins
    alone".  Raises :class:`ValueError`, naming how many rows would fit, when even
    the tightest setting leaves the rows too short.
    """
    n_rows = n_data + 1 + (1 if has_totals else 0)
    row_h = table_h // n_rows
    if max(_table_row_need(s, _TABLE_CELL_MARGIN_Y) for s in sizes_pt) <= row_h:
        return 0.0, None
    shrink = 0.0
    while True:
        need = max(
            _table_row_need(_shrunk_pt(s, shrink), _TABLE_COMPACT_MARGIN_Y) for s in sizes_pt
        )
        if need <= row_h:
            return shrink, _TABLE_COMPACT_MARGIN_Y
        if all(_shrunk_pt(s, shrink) <= min(s, _MIN_LEGIBLE_PT) for s in sizes_pt):
            break
        shrink += 1.0
    tightest = max(
        _table_row_need(min(s, _MIN_LEGIBLE_PT), _TABLE_COMPACT_MARGIN_Y) for s in sizes_pt
    )
    capacity = max(0, table_h // tightest - 1 - (1 if has_totals else 0))
    raise ValueError(
        f"table_slide: {n_data} data rows do not fit on one slide; at most {capacity} data "
        f"rows fit at {_MIN_LEGIBLE_PT:g} pt. Please split the table across several slides."
    )


def _coerce_totals_row(totals: Mapping[str, Any], n_cols: int) -> list[Any]:
    """Resolve a totals-row spec into a per-column list of cell values."""
    if "row" in totals:
        row = list(totals["row"])
        if len(row) != n_cols:
            raise ValueError(f"totals.row must have {n_cols} entries, got {len(row)}")
        return row
    label = totals.get("label", "Total")
    values = list(totals.get("values", []))
    if len(values) > n_cols - 1:
        raise ValueError(
            f"totals.values takes at most {n_cols - 1} value(s) for a {n_cols}-column table "
            f"(column 0 holds the label), got {len(values)}; use totals.row to spell out "
            "every column"
        )
    # Right-pad values with empty strings, place label in column 0,
    # values fill from the right.  This matches how spreadsheet
    # totals usually read.
    out: list[Any] = [""] * n_cols
    out[0] = label
    # Place values in the *last* len(values) columns.
    for i, v in enumerate(values):
        out[n_cols - len(values) + i] = v
    return out


_TOKEN_CHART_SLOTS: tuple[str, ...] = (
    "primary",
    "accent1",
    "accent2",
    "accent3",
    "accent4",
    "accent5",
    "accent6",
    "secondary",
    "tertiary",
    "positive",
    "negative",
    "muted",
    "neutral",
)


def _token_chart_palette(
    tokens: Optional[DesignTokens],
) -> Optional[list[Any]]:
    """Build an ordered chart palette from a token set, or ``None``.

    Pulls every chart-suitable slot in priority order (primary first,
    then accent1..6, then positive / negative, then muted / neutral as
    filler) and de-duplicates by RGB.  Returns ``None`` when fewer than
    two distinct colours are available — a one-colour palette would
    just paint every series the same hue, which is worse than
    PowerPoint's default theme colours.
    """
    if tokens is None:
        return None
    seen: set[tuple[int, int, int]] = set()
    out: list[Any] = []
    for slot in _TOKEN_CHART_SLOTS:
        rgb = tokens.palette.get(slot)
        if rgb is None:
            continue
        key = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        if key in seen:
            continue
        seen.add(key)
        out.append(rgb)
    return out if len(out) >= 2 else None


def _apply_card_styling(shape: Any, tokens: Optional[DesignTokens]) -> None:
    """Apply the ``shadows.card`` and ``radii.md`` tokens to *shape*.

    A no-op for token sets that don't define those slots, so it's safe
    to call unconditionally from recipes.  When ``radii.md`` is present
    *and* the shape is a rounded rectangle, the adjustment value is
    nudged to roughly match the requested corner radius (the OOXML
    ``adj`` is a fraction of the smaller bbox edge, so we clamp to
    ``[0, 0.5]`` to avoid overlapping curves on small cards).
    """
    if tokens is None:
        return
    shadow = tokens.shadows.get("card")
    if shadow is not None:
        # Some shape types (graphic frames, group shapes) don't carry a
        # shadow facade.  Silently skip rather than fail the whole recipe
        # — the caller can layer one on by hand.
        with contextlib.suppress(Exception):
            shape.style.shadow = shadow
    md = tokens.radii.get("md")
    if md is not None:
        try:
            # ``ROUNDED_RECTANGLE`` exposes a single adjustment whose
            # value is a fraction (0..50000 maps to 0..0.5 of the
            # shorter edge).  Translating ``radii.md`` directly is
            # approximate but visually consistent across card sizes.
            adj_list = shape.adjustments
            if len(adj_list) >= 1:
                short_edge = min(int(shape.width or 1), int(shape.height or 1))
                if short_edge > 0:
                    frac = max(0.0, min(0.5, float(md) / float(short_edge)))
                    adj_list[0] = frac
        except Exception:
            pass


def _strip_attribution_dash(attribution: str) -> str:
    """Remove a leading dash variant + whitespace from *attribution*.

    Handles ``-``, ``–`` (en-dash), and ``—`` (em-dash) so callers can
    pass either ``"Person"`` or ``"— Person"`` without producing
    ``"— — Person"`` in the rendered slide.
    """
    s = attribution.lstrip()
    while s and s[0] in ("-", "–", "—"):
        s = s[1:].lstrip()
    return s
