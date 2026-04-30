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

import os
from typing import IO, TYPE_CHECKING, Any, Mapping, Optional, Sequence, Union

from power_pptx.design.tokens import DesignTokens, TypographyToken
from power_pptx.dml.color import RGBColor
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import PP_ALIGN, MSO_ANCHOR
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

    margin = Inches(1.0)
    title_top = Length(int(slide_h * 0.38))
    title_h = Inches(1.6)
    title_box = slide.shapes.add_textbox(
        margin, title_top, Length(slide_w - 2 * margin), title_h
    )
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(44), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )

    if subtitle:
        sub_top = Length(title_top + title_h + Inches(0.1))
        sub_h = Inches(0.8)
        sub_box = slide.shapes.add_textbox(
            margin, sub_top, Length(slide_w - 2 * margin), sub_h
        )
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

    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(1.0)
    title_box = slide.shapes.add_textbox(
        margin, title_top, Length(slide_w - 2 * margin), title_h
    )
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(32), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
    )

    body_top = Length(title_top + title_h + Inches(0.2))
    body_h = Length(slide_h - body_top - Inches(0.5))
    body_box = slide.shapes.add_textbox(
        margin, body_top, Length(slide_w - 2 * margin), body_h
    )
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

    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(0.9)
    title_box = slide.shapes.add_textbox(
        margin, title_top, Length(slide_w - 2 * margin), title_h
    )
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(28), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
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

        card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, left, top, card_w, card_h
        )
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
        v_box = slide.shapes.add_textbox(
            left, Length(top + Inches(0.25)), card_w, Inches(0.85)
        )
        _fill_text_frame(
            v_box.text_frame,
            str(kpi.get("value", "")),
            token=value_token,
            color=value_color,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )

        # Label
        l_box = slide.shapes.add_textbox(
            left, Length(top + Inches(1.10)), card_w, Inches(0.4)
        )
        _fill_text_frame(
            l_box.text_frame,
            str(kpi.get("label", "")),
            token=label_token,
            color=label_color,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.TOP,
        )

        d_text, d_sign = _resolve_delta(kpi)
        if d_text is not None:
            d_color = _delta_color(tokens, d_sign)
            d_box = slide.shapes.add_textbox(
                left, Length(top + Inches(1.50)), card_w, Inches(0.35)
            )
            _fill_text_frame(
                d_box.text_frame,
                d_text,
                token=delta_token,
                color=d_color,
                align=PP_ALIGN.CENTER,
                anchor=MSO_ANCHOR.TOP,
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

    margin = Inches(1.2)
    quote_h = Inches(3.5)
    quote_top = Length((slide_h - quote_h) // 2)
    box = slide.shapes.add_textbox(
        margin, quote_top, Length(slide_w - 2 * margin), quote_h
    )
    _fill_text_frame(
        box.text_frame,
        f"“{quote}”",
        token=_typography(tokens, "heading", default_size=Pt(32), default_italic=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        word_wrap=True,
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
    band = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Emu(0), band_top, slide_w, band_h
    )
    band.line.fill.background()
    band_color = _palette(tokens, ("primary", "neutral")) or RGBColor(0, 0, 0)
    band.fill.solid()
    band.fill.fore_color.rgb = band_color
    band.fill.fore_color.alpha = 0.55
    band.text_frame.text = ""

    margin = Inches(0.6)
    title_box = slide.shapes.add_textbox(
        margin, Length(band_top + Inches(0.2)),
        Length(slide_w - 2 * margin), Inches(0.8),
    )
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(28), default_bold=True),
        color=_palette(tokens, ("on_primary",)) or RGBColor(0xFF, 0xFF, 0xFF),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
    )

    if caption:
        cap_box = slide.shapes.add_textbox(
            margin, Length(band_top + Inches(1.0)),
            Length(slide_w - 2 * margin), Inches(0.5),
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
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Emu(0), Emu(0), slide_w, slide_h
    )
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
            raise ValueError(
                f"progress must be (1≤current≤total, total≥1); got {progress!r}"
            )
        dot_d = Inches(0.18)
        dot_gap = Inches(0.10)
        row_w = total * dot_d + (total - 1) * dot_gap
        row_left = Length(slide_w - margin - row_w)
        row_top = Length(slide_h - margin - dot_d)
        active_color = title_color
        inactive_color = _palette(tokens, ("muted", "lt2")) or RGBColor(0x99, 0x99, 0xAA)
        for i in range(total):
            dot_left = Length(row_left + i * (dot_d + dot_gap))
            dot = slide.shapes.add_shape(
                MSO_SHAPE.OVAL, dot_left, row_top, dot_d, dot_d
            )
            dot.fill.solid()
            dot.fill.fore_color.rgb = (
                active_color if (i + 1) == current else inactive_color
            )
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
    ``"area"``, ``"line_markers"``, ``"scatter"``, or ``"doughnut"``.

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
        "line":          XL_CHART_TYPE.LINE,
        "line_markers":  XL_CHART_TYPE.LINE_MARKERS,
        "bar":           XL_CHART_TYPE.BAR_CLUSTERED,
        "column":        XL_CHART_TYPE.COLUMN_CLUSTERED,
        "pie":           XL_CHART_TYPE.PIE,
        "doughnut":      XL_CHART_TYPE.DOUGHNUT,
        "area":          XL_CHART_TYPE.AREA,
    }
    if chart_type not in chart_map:
        raise ValueError(
            f"Unknown chart_type {chart_type!r}; "
            f"choose from {sorted(chart_map)}"
        )

    slide = _add_blank(prs)
    slide_w, slide_h = _slide_dims(prs)

    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(0.9)
    title_box = slide.shapes.add_textbox(
        margin, title_top, Length(slide_w - 2 * margin), title_h
    )
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(28), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
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
            try:
                s.smooth = True
            except Exception:
                pass

    if data_labels:
        for plot in chart.plots:
            try:
                plot.has_data_labels = True
            except Exception:
                pass

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
    fractions summing to ~1.0 (``[0.5, 0.25, 0.25]``) or absolute
    :class:`~power_pptx.util.Length` values.  Unspecified columns split
    the remaining width evenly.

    *aligns* assigns horizontal alignment per column.  Accepts
    ``"left"`` / ``"center"`` / ``"right"``; defaults to ``"left"``
    for every column.  Useful for right-aligning numeric columns.

    *totals* adds a footer row that visually separates from the data.
    Mapping shape: ``{"label": "Total", "values": [n1, n2, ...]}`` or
    ``{"row": [c1, c2, c3, ...]}`` for a fully-explicit row.  The
    footer is bold and uses ``primary`` palette text on a subtle band.

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

    slide = _add_blank(prs)
    slide_w, slide_h = _slide_dims(prs)

    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(0.9)
    title_box = slide.shapes.add_textbox(
        margin, title_top, Length(slide_w - 2 * margin), title_h
    )
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(28), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
    )

    totals_row = _coerce_totals_row(totals, len(columns)) if totals else None
    n_rows = len(rows) + 1 + (1 if totals_row is not None else 0)
    n_cols = len(columns)
    table_top = Length(title_top + title_h + Inches(0.2))
    table_h = Length(slide_h - table_top - Inches(0.5))
    table_w = Length(slide_w - 2 * margin)

    gframe = slide.shapes.add_table(
        n_rows, n_cols, margin, table_top, table_w, table_h
    )
    table = gframe.table

    if widths is not None:
        _apply_column_widths(table, widths, table_w, n_cols)

    align_map = _coerce_aligns(aligns, n_cols)

    header_token = _typography(tokens, "body", default_size=Pt(14), default_bold=True)
    cell_token = _typography(tokens, "body", default_size=Pt(13))
    totals_token = _typography(tokens, "body", default_size=Pt(13), default_bold=True)
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

    Tokens consumed:

    * **palette** — title from ``primary`` (fallback ``neutral``); code
      panel fill from ``surface`` (fallback ``lt2``); plain code text
      from ``neutral``; panel border from ``muted`` (fallback ``lt1``).
    * **typography** — ``heading`` for the title; ``body`` is **not**
      used for the code text (which is locked to a monospace family —
      Cascadia Code → Consolas → Menlo → monospace).
    """
    slide = _add_blank(prs)
    slide_w, slide_h = _slide_dims(prs)

    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(0.9)
    title_box = slide.shapes.add_textbox(
        margin, title_top, Length(slide_w - 2 * margin), title_h
    )
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(28), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
    )

    panel_top = Length(title_top + title_h + Inches(0.2))
    panel_h = Length(slide_h - panel_top - Inches(0.5))
    panel_w = Length(slide_w - 2 * margin)
    panel = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, margin, panel_top, panel_w, panel_h
    )
    panel.fill.solid()
    panel.fill.fore_color.rgb = (
        _palette(tokens, ("surface", "lt2")) or RGBColor(0x14, 0x14, 0x18)
    )
    border = _palette(tokens, ("muted", "lt1"))
    if border is not None:
        panel.line.color.rgb = border
        panel.line.width = Pt(0.75)
    else:
        panel.line.fill.background()
    _apply_card_styling(panel, tokens)
    panel.text_frame.text = ""

    pad = Inches(0.25)
    code_box = slide.shapes.add_textbox(
        Length(margin + pad),
        Length(panel_top + pad),
        Length(panel_w - 2 * pad),
        Length(panel_h - 2 * pad),
    )
    tf = code_box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP

    fallback_color = _palette(tokens, ("neutral",)) or RGBColor(0x22, 0x22, 0x22)
    mono_size = Pt(14)
    mono_family = "Cascadia Code, Consolas, Menlo, monospace"

    # Try to highlight via Pygments; on any failure (missing dep,
    # unknown lexer) fall back to plain monospace text — the slide
    # renders correctly either way.
    highlighted = _pygments_highlight(code, language) if language else None

    para = tf.paragraphs[0]
    para.text = ""
    para.alignment = PP_ALIGN.LEFT
    if highlighted is None:
        for line_idx, line in enumerate(code.splitlines() or [""]):
            p = para if line_idx == 0 else tf.add_paragraph()
            p.alignment = PP_ALIGN.LEFT
            run = p.add_run()
            run.text = line
            run.font.name = mono_family
            run.font.size = mono_size
            run.font.color.rgb = fallback_color
    else:
        for line_idx, line_tokens in enumerate(highlighted):
            p = para if line_idx == 0 else tf.add_paragraph()
            p.alignment = PP_ALIGN.LEFT
            for text, rgb in line_tokens:
                if not text:
                    continue
                run = p.add_run()
                run.text = text
                run.font.name = mono_family
                run.font.size = mono_size
                run.font.color.rgb = rgb if rgb is not None else fallback_color

    _apply_transition(slide, transition)
    return slide


# ---------------------------------------------------------------------------
# timeline_slide
# ---------------------------------------------------------------------------


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

    slide = _add_blank(prs)
    slide_w, slide_h = _slide_dims(prs)

    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(0.9)
    title_box = slide.shapes.add_textbox(
        margin, title_top, Length(slide_w - 2 * margin), title_h
    )
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(28), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
    )

    # Rail across the middle.
    rail_y = Length(slide_h // 2)
    rail_h = Pt(2)
    rail_left = Length(margin + Inches(0.5))
    rail_right = Length(slide_w - margin - Inches(0.5))
    rail = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, rail_left, Length(rail_y - rail_h // 2),
        Length(rail_right - rail_left), rail_h,
    )
    rail_color = _palette(tokens, ("muted", "lt1")) or RGBColor(0xBB, 0xBB, 0xBB)
    rail.fill.solid()
    rail.fill.fore_color.rgb = rail_color
    rail.line.fill.background()
    rail.text_frame.text = ""

    n = len(milestones)
    span = rail_right - rail_left
    # Equally space milestones along the rail; n=1 sits dead center.
    if n == 1:
        positions = [Length(rail_left + span // 2)]
    else:
        positions = [
            Length(rail_left + int(i * span / (n - 1))) for i in range(n)
        ]

    dot_d = Inches(0.28)
    label_w = Inches(2.4)
    body_token = _typography(tokens, "body", default_size=Pt(12))
    date_token = _typography(tokens, "body", default_size=Pt(11), default_bold=True)
    body_color = _palette(tokens, ("neutral",)) or RGBColor(0x22, 0x22, 0x22)
    pending_color = rail_color
    done_color = (
        _palette(tokens, ("positive", "success"))
        or RGBColor(0x00, 0x8A, 0x3C)
    )

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
        dot.fill.fore_color.rgb = (
            done_color if ms.get("done") else pending_color
        )
        dot.line.fill.background()
        dot.text_frame.text = ""

        date_text = str(ms.get("date", ""))
        label_text = str(ms.get("label", ""))
        # Alternate above / below the rail so labels don't fight for the
        # same vertical space when milestones are close together.
        above = (i % 2 == 0)
        if above:
            date_top = Length(rail_y - dot_d // 2 - Inches(0.6))
            label_top = Length(date_top + Inches(0.25))
        else:
            date_top = Length(rail_y + dot_d // 2 + Inches(0.15))
            label_top = Length(date_top + Inches(0.3))

        if date_text:
            db = slide.shapes.add_textbox(
                Length(cx - label_w // 2), date_top, label_w, Inches(0.3)
            )
            _fill_text_frame(
                db.text_frame, date_text,
                token=date_token, color=body_color,
                align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.TOP,
            )
        if label_text:
            lb = slide.shapes.add_textbox(
                Length(cx - label_w // 2), label_top, label_w, Inches(0.7)
            )
            _fill_text_frame(
                lb.text_frame, label_text,
                token=body_token, color=body_color,
                align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.TOP,
            )

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
      ``body`` for the row text.
    """
    slide = _add_blank(prs)
    slide_w, slide_h = _slide_dims(prs)

    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(0.9)
    title_box = slide.shapes.add_textbox(
        margin, title_top, Length(slide_w - 2 * margin), title_h
    )
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(28), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
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
    head_token = _typography(tokens, "heading", default_size=Pt(18), default_bold=True)
    row_token = _typography(tokens, "body", default_size=Pt(14))

    columns = [
        (margin, left_heading, "left"),
        (Length(margin + col_w + gap), right_heading, "right"),
    ]

    n_rows = max(1, len(rows))
    row_h = Length((col_h - head_h) // n_rows)

    for col_left, heading, key in columns:
        # Heading band.
        band = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, col_left, col_top, col_w, head_h
        )
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
        )
        # Rows.
        for i, row in enumerate(rows):
            r_top = Length(col_top + head_h + i * row_h)
            if i % 2 == 0:
                tile = slide.shapes.add_shape(
                    MSO_SHAPE.RECTANGLE, col_left, r_top, col_w, row_h
                )
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
      whose head matches the SVG sniff → :func:`add_svg_figure`.
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

    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(0.9)
    title_box = slide.shapes.add_textbox(
        margin, title_top, Length(slide_w - 2 * margin), title_h
    )
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(28), default_bold=True),
        color=_palette(tokens, ("primary", "neutral")),
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
    )

    fig_top = Length(title_top + title_h + Inches(0.2))
    cap_h = Inches(0.4) if caption else Length(0)
    fig_h = Length(slide_h - fig_top - Inches(0.5) - cap_h)
    fig_w = Length(slide_w - 2 * margin)

    _embed_figure(slide, figure, margin, fig_top, fig_w, fig_h, figure_format)

    if caption:
        cap_top = Length(slide_h - Inches(0.5) - cap_h)
        cap_box = slide.shapes.add_textbox(
            margin, cap_top, fig_w, cap_h
        )
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
        _figures.add_plotly_figure(
            slide, figure, left, top, width, height, format=figure_format
        )
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
        head = figure if isinstance(figure, (bytes, bytearray)) else figure.encode("utf-8", "replace")
        head = bytes(head[:512]).lstrip()
        if head.startswith(b"<?xml") or b"<svg" in head[:200]:
            _figures.add_svg_figure(slide, figure, left, top, width, height)
            return
        if head.startswith(b"<"):
            _figures.add_html_figure(slide, figure, left, top, width, height)
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
    s = value.lstrip()
    if not s.startswith("<"):
        return False
    # XML declarations, doctypes, comments.
    if s.startswith(("<?xml", "<!DOCTYPE", "<!--", "<svg", "<html")):
        return True
    # ``<tagname`` (opening) or ``</tagname>`` (closing) — both are
    # markup; differentiate from a stray ``<`` in a filename by
    # requiring an ASCII letter after the optional ``/``.
    rest = s[2:] if s.startswith("</") else s[1:]
    if rest and rest[0].isalpha():
        return True
    # Truly unrecognised ``<…``: treat as a path (rare on real input,
    # but preserves the historical behaviour for the corner case of
    # weird filenames that happen to start with ``<``).
    return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _add_blank(prs: "Presentation") -> "Slide":
    layouts = prs.slide_layouts
    blank = layouts.get_by_name("Blank")
    if blank is None:
        blank = layouts[-1]
    return prs.slides.add_slide(blank)


def _slide_dims(prs: "Presentation") -> tuple[Length, Length]:
    width = prs.slide_width or Inches(13.333)
    height = prs.slide_height or Inches(7.5)
    return width, height


def _palette(
    tokens: Optional[DesignTokens], names: Sequence[str]
) -> Optional[RGBColor]:
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
) -> None:
    text_frame.word_wrap = word_wrap
    text_frame.vertical_anchor = anchor
    para = text_frame.paragraphs[0]
    para.alignment = align
    # Clear any default text and add a fresh run we can style.
    para.text = ""
    run = para.add_run()
    run.text = text
    _apply_typography(run.font, token)
    if color is not None:
        run.font.color.rgb = color


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


_ALIGN_MAP: dict[str, PP_ALIGN] = {
    "left":   PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right":  PP_ALIGN.RIGHT,
}


def _coerce_aligns(
    aligns: Optional[Sequence[str]], n_cols: int
) -> list[PP_ALIGN]:
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
            raise ValueError(
                f"align[{i}] must be one of {sorted(_ALIGN_MAP)}, got {a!r}"
            )
        out.append(_ALIGN_MAP[key])
    return out


def _apply_column_widths(
    table: Any,
    widths: Sequence[Union[float, Length]],
    table_w: Length,
    n_cols: int,
) -> None:
    """Set table column widths from a sequence of fractions or Lengths.

    Supports two input modes:

    * **Fractions**: values < 5 are treated as fractions of *table_w*;
      they should sum to ~1.0 (we normalise on a defensive basis so a
      slightly-off list still lays out reasonably).
    * **Absolute lengths**: any :class:`Length` (or value ≥ 5) is taken
      verbatim.

    Columns past ``len(widths)`` keep their default share of the
    remaining width.
    """
    total_table_w = int(table_w)
    spec_lengths: list[int] = []
    spec_is_fraction = False
    for w in widths[:n_cols]:
        if isinstance(w, Length):
            spec_lengths.append(int(w))
        elif isinstance(w, (int, float)) and float(w) < 5:
            spec_is_fraction = True
            spec_lengths.append(int(round(float(w) * total_table_w)))
        else:
            spec_lengths.append(int(w))

    # Normalise fractions defensively if they don't sum to ~1.
    if spec_is_fraction:
        total_spec = sum(spec_lengths)
        if total_spec > 0 and abs(total_spec - total_table_w) > total_table_w * 0.01:
            scale = total_table_w / total_spec
            spec_lengths = [int(round(v * scale)) for v in spec_lengths]

    used = sum(spec_lengths)
    remaining = max(0, total_table_w - used)
    unspecified = n_cols - len(spec_lengths)
    fill = (remaining // unspecified) if unspecified > 0 else 0

    for i in range(n_cols):
        col = table.columns[i]
        if i < len(spec_lengths):
            col.width = Emu(spec_lengths[i])
        else:
            col.width = Emu(fill)


def _coerce_totals_row(
    totals: Mapping[str, Any], n_cols: int
) -> list[Any]:
    """Resolve a totals-row spec into a per-column list of cell values."""
    if "row" in totals:
        row = list(totals["row"])
        if len(row) != n_cols:
            raise ValueError(
                f"totals.row must have {n_cols} entries, got {len(row)}"
            )
        return row
    label = totals.get("label", "Total")
    values = list(totals.get("values", []))
    # Right-pad values with empty strings, place label in column 0,
    # values fill from the right.  This matches how spreadsheet
    # totals usually read.
    out: list[Any] = [""] * n_cols
    out[0] = label
    if values:
        # Place values in the *last* len(values) columns.
        start = max(1, n_cols - len(values))
        for i, v in enumerate(values):
            if start + i < n_cols:
                out[start + i] = v
    return out


_TOKEN_CHART_SLOTS: tuple[str, ...] = (
    "primary",
    "accent1", "accent2", "accent3", "accent4", "accent5", "accent6",
    "secondary", "tertiary",
    "positive", "negative",
    "muted", "neutral",
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
        try:
            shape.style.shadow = shadow
        except Exception:
            # Some shape types (graphic frames, group shapes) don't
            # carry a shadow facade.  Silently skip rather than fail
            # the whole recipe — the caller can layer one on by hand.
            pass
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
