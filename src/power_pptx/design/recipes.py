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

import math
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
    _apply_background(slide, prs, tokens)

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
        shrink_to_fit=True,
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

    The list is fitted to the space under the title: the ``body`` size
    is the starting point and the largest size at which every bullet
    fits — never below 9pt — is baked into the slide.  A list that does
    not fit even at 9pt raises :class:`ValueError` saying how many
    bullets do; split it across slides.

    Tokens consumed:

    * **palette** — title from ``primary`` (fallback ``neutral``);
      bullet text from ``neutral``.
    * **typography** — ``heading`` for the title, ``body`` for the bullet
      lines.
    """
    if isinstance(bullets, (str, bytes)):
        raise ValueError(
            "bullet_slide: bullets must be a list of strings, not a single string"
        )
    slide_w, slide_h = _slide_dims(prs)
    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(1.0)
    body_top = Length(title_top + title_h + Inches(0.2))
    body_h = Length(slide_h - body_top - Inches(0.5))
    body_token = _typography(tokens, "body", default_size=Pt(18))
    texts = [f"•  {bullet}" for bullet in bullets]
    # Fit before touching the deck, so an over-long list leaves no half-built slide.
    body_pt, gap_pt = _fit_bullets(
        texts,
        int(slide_w - 2 * margin - Inches(0.2)),
        int(body_h - Inches(0.1)),
        body_token,
    )

    slide = _add_blank(prs)
    _apply_background(slide, prs, tokens)

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
        shrink_to_fit=True,
    )

    body_box = slide.shapes.add_textbox(
        margin, body_top, Length(slide_w - 2 * margin), body_h
    )
    body_color = _palette(tokens, ("neutral",))
    tf = body_box.text_frame
    tf.word_wrap = True
    for i, text in enumerate(texts):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = PP_ALIGN.LEFT
        run = para.add_run()
        run.text = text
        _apply_typography(run.font, body_token)
        if body_pt is not None:
            run.font.size = Pt(body_pt)
        if body_color is not None:
            run.font.color.rgb = body_color
        para.space_after = Pt(gap_pt)

    # The fitting size is baked in above (PowerPoint does not apply an
    # autofit flag until the text is edited); the flag stays so the list
    # keeps fitting when someone edits it later.
    from power_pptx.enum.text import MSO_AUTO_SIZE

    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    _apply_transition(slide, transition)
    return slide


# Gap after each bullet at the body size; scaled down with the text.
_BULLET_GAP_PT = 6.0


def _fit_bullets(
    texts: Sequence[str], width: int, height: int, token: TypographyToken
) -> tuple[Optional[int], float]:
    """Return ``(size_pt, gap_pt)`` at which the bullet paragraphs fit.

    *size_pt* is ``None`` when the list fits at the token's own size
    (nothing to override).  Raises :class:`ValueError`, saying how many
    bullets fit, when the list overflows even at the minimum size.
    """
    base_pt = token.size.pt if token.size is not None else 18.0
    top = int(math.ceil(base_pt))
    font_file = _font_file(token)
    height_pt = height / 12700.0

    def gap(size: int) -> float:
        return _BULLET_GAP_PT * min(1.0, size / base_pt)

    def heights(size: int) -> list[float]:
        line_h = _line_height_pt(size, font_file)
        return [
            _line_count(text, width, size, font_file) * line_h + gap(size) for text in texts
        ]

    floor = min(top, _MIN_FONT_PT)
    # A list too long for one line per bullet at the floor cannot fit at
    # any size; skip measuring every size for it.
    if len(texts) * (_line_height_pt(floor, font_file) + gap(floor)) <= height_pt:
        for size in range(top, floor - 1, -1):
            if sum(heights(size)) <= height_pt:
                return (None if size == top else size), round(gap(size), 1)

    fits, used = 0, 0.0
    for needed in heights(floor):
        if used + needed > height_pt:
            break
        used += needed
        fits += 1
    raise ValueError(
        f"bullet_slide: {len(texts)} bullets do not fit under the title at the "
        f"{floor}pt minimum; {fits} fit. Shorten the list or split it across slides."
    )


def kpi_slide(
    prs: "Presentation",
    *,
    title: str,
    kpis: Sequence[Mapping[str, Any]],
    tokens: Optional[DesignTokens] = None,
    transition: Optional[str] = None,
) -> "Slide":
    """Append a title + KPI card-row slide and return it.

    Each KPI dict takes (any other key raises :class:`ValueError`):

    * ``label`` *(required)* — the small caption under the value.
    * ``value`` *(required)* — the headline number / string.
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

    The cards share one row.  Each needs at least 0.75" of width, so a
    10" slide holds 9 and a 13.33" slide 12; more raise
    :class:`ValueError`.  Values, labels and deltas are measured and
    baked at one size per role across the row, so a long value shrinks
    every card's value rather than leaving the row uneven.

    Tokens consumed:

    * **palette** — title from ``primary`` (fallback ``neutral``); card
      fill from ``surface`` (fallback ``lt2``); card border from
      ``muted`` (fallback ``lt1``); value from ``primary`` (fallback
      ``neutral``); label from ``muted``; delta from ``positive`` /
      ``success`` (positive) and ``negative`` / ``danger`` (negative).
      Text colours that fall below 4.5:1 on the card fill are darkened
      or lightened, keeping their hue, until they meet it.
    * **typography** — ``heading`` for the title and the KPI value;
      ``body`` for the label and the delta line.
    * **shadows** — ``card`` (optional) is applied as a soft shadow on
      each KPI card.
    """
    _check_items("kpi_slide", "kpis", kpis, ("label", "value"), ("delta", "delta_text"))
    slide_w, _slide_h = _slide_dims(prs)
    margin = Inches(0.6)
    n = len(kpis)
    gap = Inches(0.25)
    card_w = Length(0)
    if n:
        card_w = Length(int((slide_w - 2 * margin - (n - 1) * gap) // n))
        if card_w < _KPI_MIN_CARD_W:
            fits = int((slide_w - 2 * margin + gap) // (_KPI_MIN_CARD_W + gap))
            raise ValueError(
                f"kpi_slide: {n} KPIs do not fit in one row on a slide this wide; at most "
                f"{fits} fit. Split them across slides."
            )

    slide = _add_blank(prs)
    _apply_background(slide, prs, tokens)

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
        shrink_to_fit=True,
    )

    top = Length(title_top + title_h + Inches(0.4))
    cards = [
        _kpi_card(
            slide,
            Length(margin + i * (card_w + gap)),
            top,
            card_w,
            _KPI_CARD_H,
            label=str(kpi["label"]),
            value=str(kpi["value"]),
            delta=kpi,
            tokens=tokens,
        )
        for i, kpi in enumerate(kpis)
    ]
    # One size per role across the row.
    for role in range(1, 4):
        _unify_sizes([card[role] for card in cards])

    _apply_transition(slide, transition)
    return slide


# Height of a KPI card as ``kpi_slide`` draws it; the inner layout below is
# specified at this height and scaled down for shorter cards.
_KPI_CARD_H = Inches(1.9)
# Narrowest / shortest card that can still hold a value, label and delta at
# a readable size.
_KPI_MIN_CARD_W = Inches(0.75)
_KPI_MIN_CARD_H = Inches(0.95)


def _kpi_card(
    slide: "Slide",
    left: Length,
    top: Length,
    width: Length,
    height: Length,
    *,
    label: str,
    value: str,
    delta: Optional[Mapping[str, Any]],
    tokens: Optional[DesignTokens],
    border_roles: Sequence[str] = ("muted", "lt1"),
) -> tuple[Any, Any, Any, Optional[Any]]:
    """Build one KPI card; return ``(card, value_box, label_box, delta_box)``.

    The single implementation behind :func:`kpi_slide` and
    :func:`power_pptx.design.components.add_kpi_card`.  The value, label
    and delta bands are laid out for a 1.9" card; a shorter card scales
    the bands (and their text insets) so the stack still ends inside it.
    """
    fill_color = _palette(tokens, ("surface", "lt2"))
    border_color = _palette(tokens, border_roles)
    # Text colours are checked against the card they sit on: ``muted`` on
    # ``surface`` is below 4.5:1 in every built-in preset.
    value_color = _legible(fill_color, _palette(tokens, ("primary", "neutral")))
    label_color = _legible(fill_color, _palette(tokens, ("muted",)))

    value_token = _typography(tokens, "heading", default_size=Pt(30), default_bold=True)
    label_token = _typography(tokens, "body", default_size=Pt(12))
    delta_token = _typography(tokens, "body", default_size=Pt(11), default_bold=True)

    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
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

    scale = min(1.0, int(height) / int(_KPI_CARD_H))

    def band(offset_in: float, height_in: float) -> Any:
        box = slide.shapes.add_textbox(
            left,
            Length(top + int(Inches(offset_in) * scale)),
            width,
            Length(int(Inches(height_in) * scale)),
        )
        if scale < 1.0:
            inset = Length(int(Inches(0.05) * scale))
            box.text_frame.margin_top = box.text_frame.margin_bottom = inset
        return box

    value_box = band(0.25, 0.85)
    _fill_text_frame(
        value_box.text_frame,
        value,
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
    label_box = band(1.10, 0.4)
    _fill_text_frame(
        label_box.text_frame,
        label,
        token=label_token,
        color=label_color,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.TOP,
        shrink_to_fit=True,
    )

    delta_box = None
    d_text, d_sign = _resolve_delta(delta) if delta is not None else (None, 0)
    if d_text is not None:
        delta_box = band(1.50, 0.35)
        _fill_text_frame(
            delta_box.text_frame,
            d_text,
            token=delta_token,
            color=_legible(fill_color, _delta_color(tokens, d_sign)),
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.TOP,
            shrink_to_fit=True,
        )

    return card, value_box, label_box, delta_box


def _unify_sizes(boxes: Sequence[Any]) -> None:
    """Set every run in *boxes* to the smallest size any of them was fitted to."""
    runs = [
        run
        for box in boxes
        if box is not None
        for para in box.text_frame.paragraphs
        for run in para.runs
        if run.font.size is not None
    ]
    if runs:
        smallest = min(run.font.size for run in runs)
        for run in runs:
            run.font.size = smallest


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
        shrink_to_fit=True,
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
      progress dot from ``on_primary``.  When ``on_primary`` is below
      4.5:1 on the backdrop (a mid-tone brand colour), the text uses
      black or white, whichever contrasts more.
    * **typography** — ``heading`` for the title; ``body`` for the
      eyebrow.
    """
    slide_w, slide_h = _slide_dims(prs)
    margin = Inches(0.8)
    dot_d = Inches(0.18)
    dot_gap = Inches(0.10)
    current = total = 0
    if progress is not None:
        current, total = int(progress[0]), int(progress[1])
        if total < 1 or current < 1 or current > total:
            raise ValueError(
                f"progress must be (1≤current≤total, total≥1); got {progress!r}"
            )
        fits = int((slide_w - 2 * margin + dot_gap) // (dot_d + dot_gap))
        if total > fits:
            raise ValueError(
                f"section_divider: a row of {total} progress dots does not fit on a slide "
                f"this wide; at most {fits} fit"
            )

    slide = _add_blank(prs)

    # Solid backdrop.
    bg_color = _palette(tokens, ("primary", "neutral")) or RGBColor(0x22, 0x22, 0x33)
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Emu(0), Emu(0), slide_w, slide_h
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = bg_color
    bg.line.fill.background()
    bg.text_frame.text = ""

    title_color = _legible(
        bg_color, _palette(tokens, ("on_primary",)) or RGBColor(0xFF, 0xFF, 0xFF)
    )

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
        shrink_to_fit=True,
    )

    # Progress dots: row of `total` dots, the `current`-th highlighted.
    if progress is not None:
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

    *chart_type* is one of ``"line"``, ``"line_markers"``, ``"bar"``
    (clustered horizontal bars), ``"column"`` (clustered vertical
    columns), ``"pie"``, ``"doughnut"`` or ``"area"``.  These are all
    category charts; an XY scatter chart needs x/y pairs rather than
    categories, so build one with ``slide.shapes.add_chart`` directly.

    *categories* is the list of x-axis labels (or pie-slice labels).
    Each *series* mapping is ``{"name": str, "values": Sequence[float]}``
    — both keys are required and any other key raises
    :class:`ValueError`.  A value of ``None`` leaves a gap at that
    category.  Pass a single-series list for pie / doughnut charts.

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

    _check_items("chart_slide", "series", series, ("name", "values"))
    chart_data = CategoryChartData()
    chart_data.categories = list(categories)
    for index, s in enumerate(series):
        values = s["values"]
        if isinstance(values, (str, bytes, Mapping)) or not isinstance(values, Sequence):
            raise ValueError(
                f"chart_slide: series[{index}] 'values' must be a list of numbers, "
                f"got {type(values).__name__}"
            )
        try:
            # ``None`` is a legitimate gap in a category chart.
            numbers = [None if v is None else float(v) for v in values]
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"chart_slide: series[{index}] 'values' must be numbers or None: {exc}"
            ) from exc
        chart_data.add_series(str(s["name"]), numbers)

    slide = _add_blank(prs)
    slide_w, slide_h = _slide_dims(prs)
    _apply_background(slide, prs, tokens)

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
        shrink_to_fit=True,
    )

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

    *widths* assigns column widths, one entry per column.  A bare
    number is a relative weight: ``[2, 1, 1]``, ``[50, 25, 25]`` and
    ``[0.5, 0.25, 0.25]`` all give the first column half the table.  A
    :class:`~power_pptx.util.Length` (``Inches(2)``) is an exact width;
    weights share whatever the lengths leave.  Columns past the end of
    the list split the remaining width evenly, which needs the numbers
    before them to be fractions summing to less than 1 (``[0.5]`` on
    three columns gives 50% / 25% / 25%).  Entries that are zero,
    negative or not numbers, more entries than columns, and lists that
    leave no room for a column raise :class:`ValueError`.

    *aligns* assigns horizontal alignment per column.  Accepts
    ``"left"`` / ``"center"`` / ``"right"``; defaults to ``"left"``
    for every column.  Useful for right-aligning numeric columns.

    *totals* adds a footer row that visually separates from the data.
    Mapping shape: ``{"label": "Total", "values": [n1, n2, ...]}`` or
    ``{"row": [c1, c2, c3, ...]}`` for a fully-explicit row.  The
    footer is bold and uses ``primary`` palette text on a subtle band.

    The table is fitted to the slide: cell text is measured (including
    wrapping in narrow columns) and the largest size at which every row
    fits, from the ``body`` size down to 9pt, is baked in.  A table that
    does not fit at 9pt raises :class:`ValueError` saying how many rows
    do — a 7.5" tall slide holds about 20 single-line rows — so split
    it across slides.  A row with more values than there are columns
    also raises rather than dropping the extras.

    Tokens consumed:

    * **palette** — title and header text from ``primary`` (fallback
      ``neutral``); header band fill from ``primary``; banded rows from
      ``surface`` (fallback ``lt2``); body text from ``neutral``;
      totals-row band from ``surface`` and totals text from ``primary``.
      Text that would fall below 4.5:1 on its band is replaced by a
      colour that meets it.
    * **typography** — ``heading`` for the title; ``body`` for the
      header (bold) and cell text.
    """
    if not columns:
        raise ValueError("table_slide requires at least one column")
    if isinstance(columns, (str, bytes)):
        raise ValueError("table_slide: columns must be a list of header strings")

    slide_w, slide_h = _slide_dims(prs)
    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(0.9)
    n_cols = len(columns)
    table_top = Length(title_top + title_h + Inches(0.2))
    table_h = Length(slide_h - table_top - Inches(0.5))
    table_w = Length(slide_w - 2 * margin)

    totals_row = _coerce_totals_row(totals, n_cols) if totals else None
    body_rows: list[list[str]] = []
    for r, row in enumerate(rows):
        if isinstance(row, (str, bytes, Mapping)) or not isinstance(row, Sequence):
            raise ValueError(
                f"table_slide: rows[{r}] must be a list with one value per column, "
                f"got {type(row).__name__}"
            )
        if len(row) > n_cols:
            raise ValueError(
                f"table_slide: rows[{r}] has {len(row)} values for {n_cols} columns"
            )
        body_rows.append([str(row[c]) if c < len(row) else "" for c in range(n_cols)])
    n_rows = len(body_rows) + 1 + (1 if totals_row is not None else 0)

    if widths is not None:
        col_widths = _column_widths(widths, int(table_w), n_cols)
    else:
        col_widths = [int(table_w) // n_cols] * n_cols
        if col_widths[0] < _TABLE_MIN_COL_W:
            raise ValueError(
                f"table_slide: {n_cols} columns do not fit on a slide this wide; at most "
                f"{int(table_w) // int(_TABLE_MIN_COL_W)} fit. Split the table across slides."
            )

    header_token = _typography(tokens, "body", default_size=Pt(14), default_bold=True)
    cell_token = _typography(tokens, "body", default_size=Pt(13))
    totals_token = _typography(tokens, "body", default_size=Pt(13), default_bold=True)

    # Fit before touching the deck: one (token, cells) entry per table row.
    layout = [(header_token, [str(name) for name in columns])]
    layout += [(cell_token, cells) for cells in body_rows]
    if totals_row is not None:
        layout.append((totals_token, [str(value) for value in totals_row]))
    shrink, row_heights = _fit_table(layout, col_widths, int(table_h), len(body_rows))
    if shrink:
        header_token, cell_token, totals_token = (
            _resized(token, _shrunk_pt(token, shrink))
            for token in (header_token, cell_token, totals_token)
        )

    slide = _add_blank(prs)
    _apply_background(slide, prs, tokens)

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
        shrink_to_fit=True,
    )

    gframe = slide.shapes.add_table(
        n_rows, n_cols, margin, table_top, table_w, table_h
    )
    table = gframe.table

    if widths is not None:
        for i, col_w in enumerate(col_widths):
            table.columns[i].width = Emu(col_w)
    for i, row_h in enumerate(row_heights):
        table.rows[i].height = Emu(row_h)
        # A cell's anchor lives on the cell, not its text body, so the
        # text frame's anchor alone leaves the text at the top of a row
        # taller than its text.
        for cell in table.rows[i].cells:
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE

    align_map = _coerce_aligns(aligns, n_cols)

    header_fill = _palette(tokens, ("primary", "neutral")) or RGBColor(0x33, 0x33, 0x33)
    header_text = _legible(
        header_fill, _palette(tokens, ("on_primary",)) or RGBColor(0xFF, 0xFF, 0xFF)
    )
    band_fill = _palette(tokens, ("surface", "lt2")) or RGBColor(0xF4, 0xF4, 0xF8)
    body_text = _palette(tokens, ("neutral",)) or RGBColor(0x22, 0x22, 0x22)
    banded_text = _legible(band_fill, body_text)
    totals_text = _legible(
        band_fill, _palette(tokens, ("primary", "neutral")) or RGBColor(0x22, 0x22, 0x22)
    )

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
    for r, cells in enumerate(body_rows):
        tinted = banded and (r % 2 == 0)
        for c in range(n_cols):
            cell = table.cell(r + 1, c)
            if tinted:
                cell.fill.solid()
                cell.fill.fore_color.rgb = band_fill
            else:
                cell.fill.background()
            _fill_text_frame(
                cell.text_frame,
                cells[c],
                token=cell_token,
                color=banded_text if tinted else body_text,
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


# Narrowest column an evenly-split table may have: cell insets plus room
# for a few characters at the minimum size.
_TABLE_MIN_COL_W = Inches(0.4)
# A table cell's default insets: 0.1" left/right, 0.05" top/bottom.
_CELL_INSET_X = Inches(0.2)
_CELL_INSET_Y_PT = 7.2


def _shrunk_pt(token: TypographyToken, shrink: int) -> float:
    """Size of *token* after shrinking by *shrink* points, floored at the minimum.

    A token already at or below the minimum is left alone.
    """
    size = token.size.pt if token.size is not None else float(_MIN_FONT_PT)
    return max(min(size, float(_MIN_FONT_PT)), size - shrink)


def _fit_table(
    layout: Sequence[tuple[TypographyToken, Sequence[str]]],
    col_widths: Sequence[int],
    table_h: int,
    n_body_rows: int,
) -> tuple[int, list[int]]:
    """Return ``(shrink, row_heights)`` fitting a table into *table_h* EMU.

    *layout* holds one ``(token, cell_texts)`` pair per table row, header
    first.  *shrink* is the number of points to take off every row's
    size (each floored at the minimum) so that the rows — measured with
    wrapping in their columns — fit; *row_heights* is in EMU and sums to
    at most *table_h*.  Rows keep an equal share of the height when that
    is enough for all of them, and otherwise each gets what its text
    needs plus an equal share of the slack.

    Raises :class:`ValueError`, saying how many data rows fit, when the
    table overflows with every row at the minimum size.
    """
    height_pt = table_h / 12700.0
    n_rows = len(layout)
    files = [_font_file(token) for token, _ in layout]
    max_shrink = max(
        0,
        int(
            math.ceil(
                max((token.size.pt if token.size is not None else 0.0) for token, _ in layout)
                - _MIN_FONT_PT
            )
        ),
    )

    def needs(shrink: int) -> list[float]:
        out = []
        for (token, cells), font_file in zip(layout, files):
            size = _shrunk_pt(token, shrink)
            whole = max(1, int(math.ceil(size)))
            lines = max(
                _line_count(text, width - int(_CELL_INSET_X), whole, font_file)
                for text, width in zip(cells, col_widths)
            )
            out.append(lines * _line_height_pt(size, font_file) + _CELL_INSET_Y_PT)
        return out

    # One line per row at the smallest sizes is the least a table can
    # need; when even that overflows there is nothing to measure.
    least = sum(
        _line_height_pt(_shrunk_pt(token, max_shrink), font_file) + _CELL_INSET_Y_PT
        for (token, _), font_file in zip(layout, files)
    )
    row_needs: list[float] = []
    chosen = None
    if least <= height_pt:
        for shrink in range(0, max_shrink + 1):
            row_needs = needs(shrink)
            if sum(row_needs) <= height_pt:
                chosen = shrink
                break
    if chosen is None:
        if least <= height_pt:
            floor_needs = row_needs
        else:
            floor_needs = [
                _line_height_pt(_shrunk_pt(token, max_shrink), font_file) + _CELL_INSET_Y_PT
                for (token, _), font_file in zip(layout, files)
            ]
        has_totals = n_rows - 1 - n_body_rows
        used = floor_needs[0] + (floor_needs[-1] if has_totals else 0.0)
        fits = 0
        for needed in floor_needs[1 : 1 + n_body_rows]:
            if used + needed > height_pt:
                break
            used += needed
            fits += 1
        raise ValueError(
            f"table_slide: {n_body_rows} rows do not fit on the slide at the "
            f"{_MIN_FONT_PT}pt minimum; {fits} fit. Split the table across slides."
        )

    equal = height_pt / n_rows
    if max(row_needs) <= equal:
        heights_pt = [equal] * n_rows
    else:
        slack = (height_pt - sum(row_needs)) / n_rows
        heights_pt = [needed + slack for needed in row_needs]
    return chosen, [int(h * 12700) for h in heights_pt]


# ---------------------------------------------------------------------------
# code_slide
# ---------------------------------------------------------------------------


def code_slide(
    prs: "Presentation",
    *,
    title: str,
    code: str,
    language: Optional[str] = None,
    font: Optional[str] = None,
    overflow: str = "truncate",
    tokens: Optional[DesignTokens] = None,
    transition: Optional[str] = None,
) -> "Slide":
    """Append a title + monospace code-block slide and return it.

    When *language* is supplied **and** Pygments is installed, the code
    block is syntax-highlighted with Pygments' lexer for that language
    (translated to per-token RGB runs).  Without Pygments — or without
    a *language* — the code is rendered as a plain monospace block on
    the panel fill.

    *font* names the monospace family to write.  A deck can only name
    one typeface per run (a CSS-style ``"Consolas, Menlo, monospace"``
    stack is read as a single unknown font), so when omitted the recipe
    picks the first of Cascadia Code, Consolas, Menlo, DejaVu Sans
    Mono, Liberation Mono and Courier New that is installed on the
    build machine, and Consolas when none is.  The run is also flagged
    fixed-pitch, so a viewer without that font substitutes another
    monospace face rather than a proportional one.

    The code is fitted to the panel: the size starts at 14pt and shrinks,
    down to 9pt, until every line fits — first without wrapping, then
    allowing long lines to wrap.  Tabs are expanded to four spaces.  A
    snippet that still does not fit at 9pt is handled per *overflow*:
    ``"truncate"`` (default) keeps the lines that fit and ends with a
    ``… (+N more lines)`` marker; ``"raise"`` raises :class:`ValueError`
    saying how many lines fit.

    Tokens consumed:

    * **palette** — title from ``primary`` (fallback ``neutral``); code
      panel fill from ``surface`` (fallback ``lt2``, then a dark
      default); plain code text from ``neutral``; panel border from
      ``muted`` (fallback ``lt1``).  Text and syntax colours are chosen
      from the panel's luminance — a light or a dark highlight set —
      and adjusted where needed to keep 4.5:1 contrast on the panel.
    * **typography** — ``heading`` for the title; ``body`` is **not**
      used for the code text (which is always a monospace family).
    """
    if overflow not in ("truncate", "raise"):
        raise ValueError(f"overflow must be 'truncate' or 'raise', got {overflow!r}")

    slide_w, slide_h = _slide_dims(prs)
    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(0.9)
    panel_top = Length(title_top + title_h + Inches(0.2))
    panel_h = Length(slide_h - panel_top - Inches(0.5))
    panel_w = Length(slide_w - 2 * margin)
    pad = Inches(0.25)
    mono_family = font or _monospace_family()

    # Tabs have no fixed width in a text frame (they jump to the next
    # tab stop, an inch by default), so they are expanded up front.
    lines = code.expandtabs(4).splitlines() or [""]

    # Fit before touching the deck, so ``overflow="raise"`` leaves no
    # half-built slide behind.  The text area is the panel less its
    # padding and the text box's own insets (0.1" each side, 0.05" top
    # and bottom).
    size_pt, shown = _fit_code(
        lines,
        int(panel_w - 2 * pad - Inches(0.2)),
        int(panel_h - 2 * pad - Inches(0.1)),
        mono_family,
    )
    hidden = len(lines) - shown
    if hidden and overflow == "raise":
        raise ValueError(
            f"code_slide: {len(lines)} lines of code do not fit the panel at the "
            f"{_MIN_FONT_PT}pt minimum; {shown} fit. Shorten the snippet, split it across "
            "slides, or pass overflow='truncate'."
        )

    slide = _add_blank(prs)
    _apply_background(slide, prs, tokens)

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
        shrink_to_fit=True,
    )

    panel = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, margin, panel_top, panel_w, panel_h
    )
    panel_fill = _palette(tokens, ("surface", "lt2")) or RGBColor(0x14, 0x14, 0x18)
    panel.fill.solid()
    panel.fill.fore_color.rgb = panel_fill
    border = _palette(tokens, ("muted", "lt1"))
    if border is not None:
        panel.line.color.rgb = border
        panel.line.width = Pt(0.75)
    else:
        panel.line.fill.background()
    # The preset's default corner (a sixth of the short edge) is nearly an
    # inch on a panel this size; start from a card-like corner and let a
    # ``radii.md`` token override it.
    panel.adjustments[0] = 0.03
    _apply_card_styling(panel, tokens)
    panel.text_frame.text = ""

    code_box = slide.shapes.add_textbox(
        Length(margin + pad),
        Length(panel_top + pad),
        Length(panel_w - 2 * pad),
        Length(panel_h - 2 * pad),
    )
    tf = code_box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP

    # Colours follow the panel, not a fixed theme: the plain-text colour
    # and the highlight set are picked from the panel's luminance, then
    # each is checked against the panel so nothing lands below 4.5:1.
    dark_panel = _luminance(panel_fill) < _DARK_SURFACE_LUMINANCE
    default_text = RGBColor(0xE6, 0xE6, 0xE6) if dark_panel else RGBColor(0x1F, 0x23, 0x28)
    text_color = _legible(panel_fill, _palette(tokens, ("neutral",)), default_text)

    # Try to highlight via Pygments; on any failure (missing dep,
    # unknown lexer) fall back to plain monospace text — the slide
    # renders correctly either way.
    highlighted = (
        _pygments_highlight("\n".join(lines), language, dark=dark_panel) if language else None
    )
    if highlighted is not None and len(highlighted) != len(lines):
        # Lexers normalise trailing newlines; re-align with the source lines.
        highlighted = (highlighted + [[]] * len(lines))[: len(lines)]

    def _code_paragraph(index: int) -> Any:
        p = tf.paragraphs[0] if index == 0 else tf.add_paragraph()
        if index == 0:
            p.text = ""
        p.alignment = PP_ALIGN.LEFT
        # An exact line pitch keeps the fit independent of whichever
        # monospace face the viewing machine ends up substituting.
        p.line_spacing = Pt(size_pt * _CODE_LINE_PITCH)
        return p

    def _code_run(p: Any, text: str, rgb: Optional[RGBColor]) -> None:
        run = p.add_run()
        run.text = text
        _set_monospace(run.font, mono_family)
        run.font.size = Pt(size_pt)
        if rgb is not None:
            run.font.color.rgb = rgb

    legible_cache: dict[Any, Optional[RGBColor]] = {None: text_color}
    for line_idx in range(shown):
        p = _code_paragraph(line_idx)
        if highlighted is None:
            _code_run(p, lines[line_idx], text_color)
            continue
        for text, rgb in highlighted[line_idx]:
            if not text:
                continue
            if rgb not in legible_cache:
                legible_cache[rgb] = _legible(panel_fill, rgb)
            _code_run(p, text, legible_cache[rgb])

    if hidden:
        marker = f"… (+{hidden} more line{'' if hidden == 1 else 's'})"
        _code_run(_code_paragraph(shown), marker, text_color)

    _apply_transition(slide, transition)
    return slide


# Candidate monospace families, most code-like first.  A run names exactly
# one typeface, so the first *installed* one is written; Consolas (bundled
# with Office on Windows and macOS) is the default when none can be found.
_MONO_CANDIDATES: tuple[str, ...] = (
    "Cascadia Code",
    "Consolas",
    "Menlo",
    "DejaVu Sans Mono",
    "Liberation Mono",
    "Courier New",
)
_MONO_DEFAULT = "Consolas"

# Largest and smallest code sizes the panel fit will choose.
_CODE_MAX_PT = 14
# Line pitch as a multiple of the font size, written as exact spacing.
_CODE_LINE_PITCH = 1.2
# Advance width assumed for a monospace glyph, in ems.  0.6 is the widest
# of the common faces (Courier New, DejaVu Sans Mono, Menlo); narrower ones
# (Consolas 0.55, Cascadia Code 0.59) are measured as if they were that
# wide so a substituted font can never wrap a line the fit kept whole.
_MONO_ADVANCE_EM = 0.6


def _monospace_family() -> str:
    """Return the first candidate monospace family installed on this machine."""
    from power_pptx.text.fonts import font_is_installed

    for name in _MONO_CANDIDATES:
        if font_is_installed(name):
            return name
    return _MONO_DEFAULT


def _set_monospace(font: Any, family: str) -> None:
    """Name *family* on *font* and flag it fixed-pitch for font substitution.

    ``pitchFamily="49"`` is ``FIXED_PITCH | FF_MODERN``: a renderer that
    lacks the named face then falls back to another monospace font
    instead of a proportional one.
    """
    font.name = family
    font._rPr.latin.set("pitchFamily", "49")  # pyright: ignore[reportPrivateUsage]


def _mono_advance_em(family: str) -> float:
    """Advance width of one glyph of *family* in ems, never below the usual 0.6."""
    from power_pptx.text.fonts import find_font_file

    font_file = find_font_file(family)
    if font_file is None:
        return _MONO_ADVANCE_EM
    try:
        from PIL import ImageFont

        measured = ImageFont.truetype(font_file, 1000).getlength("M") / 1000.0
    except (OSError, AttributeError):
        return _MONO_ADVANCE_EM
    return max(_MONO_ADVANCE_EM, measured)


def _wrapped_rows(line: str, columns: int) -> int:
    """Rows *line* occupies when wrapped at *columns* monospace characters.

    Mirrors what a text frame does: break at the last space that fits,
    or mid-token when a single token is longer than the row.
    """
    rows = 1
    rest = line.rstrip()
    while len(rest) > columns:
        cut = rest.rfind(" ", 1, columns + 1)
        # A break inside the indentation would leave an empty row; cut the
        # token itself instead.
        if cut <= 0 or not rest[:cut].strip():
            cut = columns
        rest = rest[cut:].lstrip(" ")
        rows += 1
    return rows


def _fit_code(lines: Sequence[str], width: int, height: int, family: str) -> tuple[int, int]:
    """Return ``(size_pt, lines_shown)`` fitting *lines* into a code panel.

    ``TextFrame.fit_text`` re-flows text word by word, which is wrong for
    code (it collapses indentation and cannot break a long token), so the
    fit is done here on the same basis — measured font metrics — using
    the fact that every monospace glyph has one advance width.

    Sizes are tried from :data:`_CODE_MAX_PT` down to the readable
    minimum, preferring a size at which no line wraps; if none exists,
    the largest size at which the wrapped lines fit.  When even the
    minimum overflows, the leading lines that fit are kept, leaving one
    row for the "more lines" marker.
    """
    advance = _mono_advance_em(family)
    width_pt, height_pt = width / 12700.0, height / 12700.0

    def capacity(size: int) -> tuple[int, int]:
        columns = int(width_pt / (advance * size))
        rows = int(height_pt / (size * _CODE_LINE_PITCH) + 1e-6)
        return columns, rows

    sizes = range(_CODE_MAX_PT, _MIN_FONT_PT - 1, -1)
    longest = max(len(line.rstrip()) for line in lines)
    for size in sizes:
        columns, rows = capacity(size)
        if longest <= columns and len(lines) <= rows:
            return size, len(lines)
    for size in sizes:
        columns, rows = capacity(size)
        if columns >= 1 and sum(_wrapped_rows(line, columns) for line in lines) <= rows:
            return size, len(lines)

    columns, rows = capacity(_MIN_FONT_PT)
    columns = max(1, columns)
    used = shown = 0
    for line in lines:
        needed = _wrapped_rows(line, columns)
        if used + needed > rows - 1:  # keep one row for the marker
            break
        used += needed
        shown += 1
    return _MIN_FONT_PT, shown


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

    Each milestone dict takes a ``label`` (required), an optional
    ``date`` shown in bold above it, and an optional ``done`` flag
    (default ``False``).  Any other key raises :class:`ValueError`.
    Completed milestones get the ``positive`` palette tint; pending
    ones use ``muted``.

    Milestones alternate above and below the rail.  The end markers are
    inset by half a label so every label stays inside the slide margins,
    labels above the rail are bottom-anchored so a wrapped label grows
    upwards, away from the rail, and the marker-on-rail overlap is
    declared to the linter — the slide lints clean.  Each label is at
    least an inch wide; more milestones than that allows (15 on a 10"
    slide, 21 on a 13.33" one) raise :class:`ValueError`.

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
    _check_items("timeline_slide", "milestones", milestones, ("label",), ("date", "done"))

    slide_w, slide_h = _slide_dims(prs)
    margin = Inches(0.6)
    content_w = int(slide_w - 2 * margin)
    n = len(milestones)

    # Labels alternate above / below the rail, so the nearest label on the
    # same side is two markers away: a label may be up to two pitches wide
    # (less a small gutter).  The first and last labels must also stay
    # inside the margins, which puts the end markers half a label in from
    # each side.  Solving both for the label width gives the cap below.
    label_gutter = int(Inches(0.1))
    min_label_w = int(Inches(1.0))
    label_w = int(Inches(2.4))
    if n > 1:
        label_w = min(label_w, (2 * content_w - (n - 1) * label_gutter) // (n + 1))
    label_w = min(label_w, content_w)
    if label_w < min_label_w:
        fits = max(1, (2 * content_w + label_gutter - min_label_w) // (min_label_w + label_gutter))
        raise ValueError(
            f"timeline_slide: {n} milestones do not fit on a slide this wide; at most "
            f"{fits} fit with readable labels. Split the timeline across slides."
        )

    slide = _add_blank(prs)
    _apply_background(slide, prs, tokens)

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
        shrink_to_fit=True,
    )

    # Equally space the markers; n=1 sits dead center.
    if n == 1:
        positions = [Length(slide_w // 2)]
    else:
        first = int(margin) + label_w // 2
        pitch = (content_w - label_w) / (n - 1)
        positions = [Length(first + int(round(i * pitch))) for i in range(n)]

    # Rail across the middle, from the first marker to the last.
    rail_y = Length(slide_h // 2)
    rail_h = Pt(2)
    if n == 1:
        rail_left = Length(margin + Inches(0.5))
        rail_right = Length(slide_w - margin - Inches(0.5))
    else:
        rail_left, rail_right = positions[0], positions[-1]
    rail = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, rail_left, Length(rail_y - rail_h // 2),
        Length(rail_right - rail_left), rail_h,
    )
    rail_color = _palette(tokens, ("muted", "lt1")) or RGBColor(0xBB, 0xBB, 0xBB)
    rail.fill.solid()
    rail.fill.fore_color.rgb = rail_color
    rail.line.fill.background()
    rail.text_frame.text = ""

    dot_d = Inches(0.28)
    body_token = _typography(tokens, "body", default_size=Pt(12))
    date_token = _typography(tokens, "body", default_size=Pt(11), default_bold=True)
    body_color = _palette(tokens, ("neutral",)) or RGBColor(0x22, 0x22, 0x22)
    pending_color = rail_color
    done_color = (
        _palette(tokens, ("positive", "success"))
        or RGBColor(0x00, 0x8A, 0x3C)
    )

    # One text box per milestone (date paragraph, then label).  Boxes above
    # the rail run from under the title to just above the marker and are
    # bottom-anchored; boxes below run from just under the marker to the
    # bottom margin and are top-anchored.  Either way the text sits next
    # to its marker and extra lines grow away from the rail.
    clearance = Inches(0.08)
    above_top = Length(title_top + title_h + Inches(0.1))
    above_h = Length(max(int(Inches(0.4)), rail_y - dot_d // 2 - clearance - above_top))
    below_top = Length(rail_y + dot_d // 2 + clearance)
    below_h = Length(max(int(Inches(0.4)), slide_h - Inches(0.5) - below_top))

    # Bake one size for every label: the largest at which each milestone's
    # text fits its box with whole words, so the row reads evenly.
    texts = [
        "\n".join(str(ms[key]) for key in ("date", "label") if str(ms.get(key, "") or ""))
        for ms in milestones
    ]
    label_pt = int(math.ceil(body_token.size.pt)) if body_token.size is not None else 12
    overflowing = False
    for i, text in enumerate(texts):
        if not text:
            continue
        box_h = above_h if i % 2 == 0 else below_h
        fit = _fit_pt(
            text, label_w - Inches(0.2), int(box_h) - Inches(0.1), body_token, label_pt
        )
        if fit is None:
            fit, overflowing = _MIN_FONT_PT, True
        label_pt = min(label_pt, fit)

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
        dot.fill.fore_color.rgb = (
            done_color if ms.get("done") else pending_color
        )
        dot.line.fill.background()
        dot.text_frame.text = ""
        dots.append(dot)

        if not texts[i]:
            continue
        # Alternate above / below the rail so labels don't fight for the
        # same vertical space when milestones are close together.
        above = (i % 2 == 0)
        box = slide.shapes.add_textbox(
            Length(cx - label_w // 2),
            above_top if above else below_top,
            Length(label_w),
            above_h if above else below_h,
        )
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.BOTTOM if above else MSO_ANCHOR.TOP
        if overflowing:
            from power_pptx.enum.text import MSO_AUTO_SIZE

            tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        first_para = True
        for key, token in (("date", date_token), ("label", body_token)):
            text = str(ms.get(key, "") or "")
            if not text:
                continue
            para = tf.paragraphs[0] if first_para else tf.add_paragraph()
            first_para = False
            para.alignment = PP_ALIGN.CENTER
            run = para.add_run()
            run.text = text
            _apply_typography(run.font, token)
            if token.size is None or token.size.pt > label_pt:
                run.font.size = Pt(label_pt)
            run.font.color.rgb = body_color

    # The markers sit on the rail by design; say so, so the linter does
    # not report every marker as colliding with it.
    slide.lint_group_overlaps(rail, *dots)

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

    Each *rows* mapping is ``{"left": str, "right": str}`` — both keys
    are required and any other key raises :class:`ValueError` (a label
    column is *not* drawn — the comparison is intended for prose
    bullets).  Rows are evenly spaced down the slide so the left and
    right entries always line up.

    Row text is measured and baked at one size for the whole table,
    shrinking from the ``body`` size to 9pt at the least.  Rows need
    0.22" each, so a 7.5" tall slide holds 21; more raise
    :class:`ValueError`.

    Tokens consumed:

    * **palette** — title from ``primary`` (fallback ``neutral``);
      column heading band from ``primary``; heading text from
      ``on_primary``; row text from ``neutral``; even-row tint from
      ``surface`` (fallback ``lt2``).  Heading and row text that would
      fall below 4.5:1 on its band is replaced by a colour that meets it.
    * **typography** — ``heading`` for the title and column headings;
      ``body`` for the row text.
    """
    _check_items("comparison_slide", "rows", rows, ("left", "right"))
    slide_w, slide_h = _slide_dims(prs)
    margin = Inches(0.6)
    title_top = Inches(0.5)
    title_h = Inches(0.9)
    head_h = Inches(0.6)
    col_top = Length(title_top + title_h + Inches(0.2))
    col_h = Length(slide_h - col_top - Inches(0.5))
    n_rows = max(1, len(rows))
    row_h = Length((col_h - head_h) // n_rows)
    if row_h < _COMPARISON_MIN_ROW_H:
        fits = max(0, int((col_h - head_h) // _COMPARISON_MIN_ROW_H))
        raise ValueError(
            f"comparison_slide: {len(rows)} rows do not fit on a slide this tall; at most "
            f"{fits} fit. Split the comparison across slides."
        )

    slide = _add_blank(prs)
    _apply_background(slide, prs, tokens)

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
        shrink_to_fit=True,
    )

    gap = Inches(0.3)
    col_w = Length((slide_w - 2 * margin - gap) // 2)

    head_color = _palette(tokens, ("primary", "neutral")) or RGBColor(0x33, 0x33, 0x33)
    head_text_color = _legible(
        head_color, _palette(tokens, ("on_primary",)) or RGBColor(0xFF, 0xFF, 0xFF)
    )
    row_text_color = _palette(tokens, ("neutral",)) or RGBColor(0x22, 0x22, 0x22)
    band_color = _palette(tokens, ("surface", "lt2")) or RGBColor(0xF4, 0xF4, 0xF8)
    banded_text_color = _legible(band_color, row_text_color)
    head_token = _typography(tokens, "heading", default_size=Pt(18), default_bold=True)
    row_token = _typography(tokens, "body", default_size=Pt(14))

    columns = [
        (margin, left_heading, "left"),
        (Length(margin + col_w + gap), right_heading, "right"),
    ]

    # Vertical padding inside a row: the usual 0.05" while the row has room
    # for it, squeezed towards zero as rows approach the minimum height so
    # a line of minimum-size text still fits.
    pad = Length(max(0, min(int(Inches(0.05)), (int(row_h) - int(Inches(0.16))) // 4)))

    row_boxes: list[Any] = []
    for col_left, heading, key in columns:
        # Heading band.
        band = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, col_left, col_top, col_w, head_h
        )
        band.fill.solid()
        band.fill.fore_color.rgb = head_color
        band.line.fill.background()
        band.text_frame.margin_top = band.text_frame.margin_bottom = Emu(0)
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
            banded = i % 2 == 0
            if banded:
                tile = slide.shapes.add_shape(
                    MSO_SHAPE.RECTANGLE, col_left, r_top, col_w, row_h
                )
                tile.fill.solid()
                tile.fill.fore_color.rgb = band_color
                tile.line.fill.background()
                tile.text_frame.text = ""
            tb = slide.shapes.add_textbox(
                Length(col_left + Inches(0.2)),
                Length(r_top + pad),
                Length(col_w - Inches(0.4)),
                Length(row_h - 2 * pad),
            )
            tb.text_frame.margin_top = tb.text_frame.margin_bottom = pad
            _fill_text_frame(
                tb.text_frame,
                str(row[key]),
                token=row_token,
                color=banded_text_color if banded else row_text_color,
                align=PP_ALIGN.LEFT,
                anchor=MSO_ANCHOR.MIDDLE,
                shrink_to_fit=True,
            )
            row_boxes.append(tb)

    # One size for every row, so a single long entry does not leave the
    # table with mixed text sizes.
    _unify_sizes(row_boxes)

    _apply_transition(slide, transition)
    return slide


# Shortest comparison row that still holds one line of minimum-size text.
_COMPARISON_MIN_ROW_H = Inches(0.22)


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
    html_options: Optional[dict[str, Any]] = None,
    plotly_options: Optional[dict[str, Any]] = None,
    fit: str = "contain",
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
    * raw image ``bytes`` (PNG, JPEG, …) or a binary file-like object
      such as ``io.BytesIO`` → sniffed: SVG and HTML markup go to the
      adapters above, anything else is embedded as a raster picture.

    *fit* places the figure in the content area under the title:
    ``"contain"`` (default) scales it to fit with its aspect ratio
    intact and centres it; ``"cover"`` fills the area and crops the
    overflow; ``"stretch"`` distorts it to the area's exact size.

    *figure_format* (``"auto"`` / ``"svg"`` / ``"png"``) is forwarded
    to the Plotly / Matplotlib adapter; ignored for SVG / HTML / image
    inputs.

    *html_options* forwards browser capture options such as ``selector``,
    ``viewport`` and ``wait_for_function`` when the input is HTML.

    *plotly_options* forwards ``backend``, ``browser_path``, pixel dimensions,
    and other export options to the Plotly adapter.

    *caption* is rendered in the bottom-right corner if supplied.

    Tokens consumed:

    * **palette** — title from ``primary`` (fallback ``neutral``);
      caption from ``muted`` (fallback ``neutral``).
    * **typography** — ``heading`` for the title; ``body`` for the
      caption.
    """
    if fit not in _FIGURE_FITS:
        raise ValueError(f"fit must be one of {sorted(_FIGURE_FITS)}, got {fit!r}")

    slide = _add_blank(prs)
    slide_w, slide_h = _slide_dims(prs)
    _apply_background(slide, prs, tokens)

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
        shrink_to_fit=True,
    )

    fig_top = Length(title_top + title_h + Inches(0.2))
    cap_h = Inches(0.4) if caption else Length(0)
    fig_h = Length(slide_h - fig_top - Inches(0.5) - cap_h)
    fig_w = Length(slide_w - 2 * margin)

    _embed_figure(
        slide, figure, margin, fig_top, fig_w, fig_h, figure_format,
        html_options, plotly_options, fit,
    )

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


_FIGURE_FITS = frozenset({"contain", "cover", "stretch"})


def _embed_figure(
    slide: "Slide",
    figure: Any,
    left: Length,
    top: Length,
    width: Length,
    height: Length,
    figure_format: str,
    html_options: Optional[dict[str, Any]] = None,
    plotly_options: Optional[dict[str, Any]] = None,
    fit: str = "contain",
) -> None:
    """Dispatch *figure* by type to the matching figures-module adapter.

    Every adapter places its picture at the full ``left/top/width/height``
    box; :func:`_fit_picture` then re-fits it per *fit*, so a square image
    is not stretched to a wide content area.  The HTML adapter has its
    own ``fit`` option and is handed *fit* directly.
    """
    from power_pptx.design import figures as _figures

    box = (left, top, width, height)
    html_kwargs = dict(html_options or {})
    html_kwargs.setdefault("fit", fit)

    # Plotly figure: detected by duck-typed .to_image().
    if hasattr(figure, "to_image") and callable(figure.to_image):
        picture = _figures.add_plotly_figure(
            slide, figure, *box, format=figure_format, **(plotly_options or {})
        )
        _fit_picture(picture, *box, fit)
        return

    # Matplotlib figure: detected by duck-typed .savefig().
    if hasattr(figure, "savefig") and callable(figure.savefig):
        picture = _figures.add_matplotlib_figure(slide, figure, *box, format=figure_format)
        _fit_picture(picture, *box, fit)
        return

    # File path: dispatch by extension.
    if isinstance(figure, (str, os.PathLike)) and not _is_markup_string(figure):
        ext = os.path.splitext(str(figure))[1].lower()
        if ext in {".html", ".htm"}:
            _figures.add_html_figure(slide, figure, *box, **html_kwargs)
            return
        if ext == ".svg":
            picture = _figures.add_svg_figure(slide, figure, *box)
        else:
            # A raster extension, or an unknown one — best-effort raster.
            picture = slide.shapes.add_picture(str(figure), *box)
        _fit_picture(picture, *box, fit)
        return

    # A binary file-like object (``io.BytesIO``, an open file): read it
    # and treat the content like raw bytes.
    if not isinstance(figure, (bytes, bytearray, str)) and callable(
        getattr(figure, "read", None)
    ):
        data = figure.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
        figure = bytes(data)

    # Bytes / strings: SVG sniff, then HTML, then a raster image.
    if isinstance(figure, (bytes, bytearray, str)):
        from power_pptx._svg import looks_like_svg

        blob = bytes(figure) if not isinstance(figure, str) else figure.encode("utf-8")
        head = blob.lstrip(b"\xef\xbb\xbf \t\r\n")
        if looks_like_svg(blob):
            picture = _figures.add_svg_figure(slide, figure, *box)
            _fit_picture(picture, *box, fit)
            return
        if head.startswith(b"<"):
            _figures.add_html_figure(slide, figure, *box, **html_kwargs)
            return
        if not isinstance(figure, str):
            import io

            picture = slide.shapes.add_picture(io.BytesIO(blob), *box)
            _fit_picture(picture, *box, fit)
            return

    raise TypeError(
        f"figure_slide can't dispatch a figure of type {type(figure).__name__!r}; "
        "pass a Plotly Figure, a Matplotlib Figure, an SVG / HTML "
        "string, an image path, raw image bytes, or a binary file-like object."
    )


def _fit_picture(
    picture: Any, left: Length, top: Length, width: Length, height: Length, fit: str
) -> None:
    """Re-place *picture* inside the box per *fit* using its pixel aspect ratio.

    ``"contain"`` scales the picture to fit and centres it; ``"cover"``
    fills the box and crops the overflow evenly; ``"stretch"`` leaves the
    picture at the box's size.  An SVG picture is measured through its
    PNG companion, which has the same aspect ratio.
    """
    if fit == "stretch":
        return
    try:
        px_w, px_h = picture.image.size
    except (AttributeError, ValueError, OSError):
        return
    if px_w <= 0 or px_h <= 0 or width <= 0 or height <= 0:
        return
    if fit == "contain":
        scale = min(int(width) / px_w, int(height) / px_h)
        fit_w, fit_h = int(round(px_w * scale)), int(round(px_h * scale))
        picture.left = Emu(int(left) + (int(width) - fit_w) // 2)
        picture.top = Emu(int(top) + (int(height) - fit_h) // 2)
        picture.width, picture.height = Emu(fit_w), Emu(fit_h)
        return
    picture.left, picture.top, picture.width, picture.height = left, top, width, height
    image_ratio, box_ratio = px_w / px_h, int(width) / int(height)
    picture.crop_left = picture.crop_right = picture.crop_top = picture.crop_bottom = 0.0
    if image_ratio > box_ratio:
        picture.crop_left = picture.crop_right = (1 - box_ratio / image_ratio) / 2
    else:
        picture.crop_top = picture.crop_bottom = (1 - image_ratio / box_ratio) / 2


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
    s = value.lstrip("\ufeff \t\r\n")
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
    """Append a slide the recipe can lay out from scratch.

    Uses the layout named ``Blank`` when the template has one.  A
    template whose layouts are renamed or localised has no such layout;
    the last layout — "Vertical Title and Text" in the stock set — was
    the old fallback and left two empty placeholders under the recipe's
    own shapes.  Instead the layout that contributes the fewest
    placeholders to a new slide is chosen, and any it does contribute
    are removed, so the recipe always starts from an empty slide.
    """
    layouts = prs.slide_layouts
    blank = layouts.get_by_name("Blank")
    if blank is not None:
        return prs.slides.add_slide(blank)
    emptiest = min(
        layouts, key=lambda layout: sum(1 for _ in layout.iter_cloneable_placeholders())
    )
    slide = prs.slides.add_slide(emptiest)
    for placeholder in list(slide.placeholders):
        placeholder._element.getparent().remove(placeholder._element)
    return slide


def _apply_background(
    slide: "Slide", prs: "Presentation", tokens: Optional[DesignTokens]
) -> None:
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


# Smallest size a recipe will bake into a slide: the linter's ``MinFontSize``
# legibility threshold.  Content that cannot fit at it is rejected (or, for
# free text, left to the linter to report) rather than shrunk further.
_MIN_FONT_PT = 9

# WCAG AA contrast for body text — the ratio ``slide.lint()`` enforces.
_MIN_CONTRAST = 4.5

# Luminance below which white text out-contrasts black text on a surface.
_DARK_SURFACE_LUMINANCE = 0.18


def _luminance(rgb: Any) -> float:
    """WCAG relative luminance of an ``RGBColor``."""

    def channel(value: int) -> float:
        c = value / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2])


def _contrast(rgb_a: Any, rgb_b: Any) -> float:
    """WCAG contrast ratio between two colours."""
    la, lb = _luminance(rgb_a), _luminance(rgb_b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _legible(
    surface: Optional[RGBColor], *candidates: Optional[RGBColor]
) -> Optional[RGBColor]:
    """Return a text colour that reads on *surface* at 4.5:1 or better.

    The palette roles a recipe uses are not guaranteed to contrast with
    each other — ``muted`` on ``surface`` is 2.2–3.4:1 in every built-in
    preset — so each recipe passes the colour it would like to use
    together with the fill it is about to draw the text on:

    * the first candidate that already meets the ratio is returned
      untouched, so a palette whose roles do contrast is not altered;
    * otherwise the first candidate keeps its hue and saturation and
      has its lightness moved away from the surface until it complies
      (``muted`` stays a grey, ``positive`` stays green);
    * black or white, whichever contrasts more, is the last resort.

    ``None`` candidates are skipped.  With no *surface* (an unfilled
    card, or text on a slide background the recipe does not draw) there
    is nothing to measure against and the first candidate is returned.
    """
    options = [c for c in candidates if c is not None]
    if not options:
        return None
    if surface is None:
        return options[0]
    for option in options:
        if _contrast(option, surface) >= _MIN_CONTRAST:
            return option

    import colorsys

    preferred = options[0]
    hue, lightness, saturation = colorsys.rgb_to_hls(*(c / 255.0 for c in preferred))
    target = 1.0 if _luminance(preferred) >= _luminance(surface) else 0.0
    for step in range(1, 51):
        shifted = lightness + (target - lightness) * step / 50.0
        candidate = RGBColor(
            *(int(round(c * 255)) for c in colorsys.hls_to_rgb(hue, shifted, saturation))
        )
        if _contrast(candidate, surface) >= _MIN_CONTRAST:
            return candidate

    black, white = RGBColor(0x00, 0x00, 0x00), RGBColor(0xFF, 0xFF, 0xFF)
    return black if _contrast(black, surface) >= _contrast(white, surface) else white


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


def _resized(token: TypographyToken, size_pt: float) -> TypographyToken:
    """Return *token* with its size replaced by *size_pt* points."""
    return TypographyToken(
        family=token.family,
        size=Pt(size_pt),
        bold=token.bold,
        italic=token.italic,
        color=token.color,
    )


# Stand-ins used to measure text whose own font is not installed, widest
# first: a fit made with a wide face still holds when the real (or the
# renderer's substitute) font turns out narrower, whereas the reverse
# breaks words across lines.
_FALLBACK_METRIC_FAMILIES: tuple[str, ...] = (
    "DejaVu Sans",
    "Verdana",
    "Liberation Sans",
    "Arial",
    "Helvetica",
)


def _font_file(token: TypographyToken) -> Optional[str]:
    """Path of a font file to measure *token*'s text with, or ``None``.

    The token's own face when it is installed.  Otherwise the same style
    of a common wide sans, so the fit errs towards smaller text — a
    brand font missing on the build machine is the normal case in CI,
    and no warning is raised for it.  ``None`` (nothing suitable
    installed) makes the measuring helpers use Pillow's bundled font: an
    estimate, which is still far better than not measuring.
    """
    from power_pptx.text.fonts import find_font_file

    bold, italic = bool(token.bold), bool(token.italic)
    if token.family:
        own = find_font_file(token.family, bold, italic)
        if own is not None:
            return own
    for family in _FALLBACK_METRIC_FAMILIES:
        stand_in = find_font_file(family, bold, italic) or find_font_file(family, bold, False)
        if stand_in is not None:
            return stand_in
    return None


def _fit_pt(
    text: str, width: int, height: int, token: TypographyToken, max_pt: float
) -> Optional[int]:
    """Largest whole point size ≤ *max_pt* at which *text* fits the box.

    Uses the same metrics-based fitter as ``TextFrame.fit_text``: text is
    wrapped at whole words and must fit both *width* and *height* (EMU,
    insets already removed).  The search stops at :data:`_MIN_FONT_PT`;
    ``None`` means the text does not fit even at that size.  A *max_pt*
    at or below the minimum is returned as-is — there is nothing to
    shrink towards.
    """
    from power_pptx.text.layout import TextFitter

    top = int(math.ceil(max_pt))
    if top <= _MIN_FONT_PT or not text.strip() or width <= 0 or height <= 0:
        return top
    try:
        return TextFitter.best_fit_font_size(
            text,
            (width, height),
            top,
            _font_file(token),
            min_size=_MIN_FONT_PT,
            line_spacing=1.0,
        )
    except (OSError, ValueError):
        # An unreadable font file must not fail the recipe; leave the size.
        return top


def _line_count(text: str, width: int, size_pt: int, font_file: Optional[str]) -> int:
    """Number of lines *text* occupies when wrapped to *width* EMU at *size_pt*."""
    from power_pptx.text.layout import _rendered_size
    from power_pptx.text.measurement import measure_text

    if not text:
        return 1
    single_line = "\n" not in text and "\v" not in text
    if single_line and _rendered_size(text, size_pt, font_file)[0] <= width:
        return 1
    if width <= 0:
        return max(1, len(text))
    try:
        return len(measure_text(text, Emu(width), size_pt=size_pt, font_file=font_file).lines)
    except ValueError:
        # A word wider than the box: the renderer breaks it mid-word.
        return sum(
            max(1, math.ceil(_rendered_size(part, size_pt, font_file)[0] / width))
            for part in text.replace("\v", "\n").split("\n")
        )


def _line_height_pt(size_pt: float, font_file: Optional[str]) -> float:
    """Height of one single-spaced line of *size_pt* text, in points."""
    from power_pptx.text.layout import _line_height_em

    return size_pt * max(1.2, _line_height_em(font_file))


def _did_you_mean(word: str, candidates: Sequence[str]) -> str:
    """Return ``" (did you mean 'x'?)"`` for the closest candidate, or ``""``."""
    import difflib

    matches = difflib.get_close_matches(str(word), list(candidates), n=1, cutoff=0.6)
    return f" (did you mean {matches[0]!r}?)" if matches else ""


def _check_items(
    recipe: str,
    field: str,
    items: Any,
    required: Sequence[str],
    optional: Sequence[str] = (),
) -> None:
    """Validate the item dicts of a list argument such as ``kpis``.

    Recipes read item fields with ``.get``, so a misspelt key used to
    produce a blank card / marker / row rather than an error.  Every
    item must be a mapping, carry each *required* key, and use no key
    outside *required* + *optional*; anything else raises
    :class:`ValueError` naming the item and suggesting the closest
    accepted key.
    """
    if isinstance(items, (str, bytes, Mapping)) or not isinstance(items, Sequence):
        raise ValueError(
            f"{recipe}: {field} must be a list of mappings, got {type(items).__name__}"
        )
    accepted = [*required, *optional]
    for index, item in enumerate(items):
        where = f"{recipe}: {field}[{index}]"
        if not isinstance(item, Mapping):
            raise ValueError(
                f"{where} must be a mapping with keys {accepted}, got {type(item).__name__}"
            )
        problems = []
        unknown = sorted(str(key) for key in item if key not in accepted)
        if unknown:
            hints = ", ".join(f"{key!r}{_did_you_mean(key, accepted)}" for key in unknown)
            problems.append(f"unknown key(s) {hints}")
        missing = [key for key in required if key not in item]
        if missing:
            problems.append("missing required key(s) " + ", ".join(repr(key) for key in missing))
        if problems:
            raise ValueError(
                f"{where}: {'; '.join(problems)}. Required: {list(required)}; "
                f"optional: {list(optional)}."
            )


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
    if shrink_to_fit and word_wrap and token.size is not None:
        # The autofit flag alone is not enough: PowerPoint only applies it
        # once the text is edited, so a freshly generated deck opens with
        # the text at its authored size, overflowing.  The text is known
        # here, so measure it and bake the size that fits.  Text that does
        # not fit even at the minimum is set to the minimum and left to
        # the flag (and to ``slide.lint()``) rather than shrunk to
        # illegibility.
        width, height = text_frame._extents  # pyright: ignore[reportPrivateUsage]
        fit = _fit_pt(text, int(width), int(height), token, token.size.pt)
        if fit is None:
            run.font.size = Pt(_MIN_FONT_PT)
        elif fit < token.size.pt:
            run.font.size = Pt(fit)


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
    code: str, language: Optional[str], *, dark: bool = True
) -> Optional[list[list[tuple[str, Optional[RGBColor]]]]]:
    """Return per-line lists of ``(text, RGBColor)`` runs, or ``None``.

    *dark* selects the highlight set: the dark-panel colours (light,
    pastel) or the light-panel ones (saturated, dark).  A colour of
    ``None`` means "use the plain-text colour".

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
        # ``stripnl=False`` keeps leading blank lines so the highlighted
        # lines stay aligned with the source lines.
        lexer = get_lexer_by_name(language, stripnl=False)
    except Exception:
        return None

    # A small token-class → hex map, one column per panel brightness.
    # Pygments has built-in styles but they're tuned for HTML output;
    # using a hand-picked map keeps the slide colors in a single,
    # reviewable place.  The pastel set is only readable on a dark panel
    # (1.8–1.9:1 on a light one), hence the second column.
    #
    # Operator/Punctuation/Text are mapped to the sentinel ``None`` so
    # they fall through to the plain-text colour at render time.
    # Hard-coding a light grey here would render as nearly-invisible
    # punctuation on light panels — and ``.`` in member access
    # (``optimiser.zero_grad``) is its own Pygments token, so the
    # consequence was code reading as ``optimiser zero_grad``.
    themed: dict[Any, Optional[tuple[str, str]]] = {
        #                           dark panel  light panel
        Token.Keyword:            ("#C586C0", "#AF00DB"),
        Token.Keyword.Constant:   ("#569CD6", "#0000FF"),
        Token.Keyword.Namespace:  ("#C586C0", "#AF00DB"),
        Token.Name.Function:      ("#DCDCAA", "#795E26"),
        Token.Name.Class:         ("#4EC9B0", "#267F99"),
        Token.Name.Builtin:       ("#4EC9B0", "#267F99"),
        Token.Name.Decorator:     ("#DCDCAA", "#795E26"),
        Token.String:             ("#CE9178", "#A31515"),
        Token.String.Doc:         ("#608B4E", "#008000"),
        Token.Number:             ("#B5CEA8", "#098658"),
        Token.Comment:            ("#6A9955", "#008000"),
        Token.Comment.Single:     ("#6A9955", "#008000"),
        Token.Comment.Multiline:  ("#6A9955", "#008000"),
        Token.Operator:           None,
        Token.Punctuation:        None,
        Token.Text:               None,
    }
    color_map: dict[Any, Optional[str]] = {
        tok: (None if pair is None else pair[0 if dark else 1]) for tok, pair in themed.items()
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


def _column_widths(
    widths: Sequence[Union[float, Length]],
    table_w: int,
    n_cols: int,
) -> list[int]:
    """Resolve a ``widths`` argument into one EMU width per column.

    * A :class:`Length` is an exact width.
    * A bare number is a relative weight over the width the lengths
      leave: ``[2, 1, 1]``, ``[50, 25, 25]`` and ``[0.5, 0.25, 0.25]``
      are the same table.  (Numbers were once read as raw EMU from 5
      upwards, which turned ``[50, 25, 25]`` into an invisible table.)
    * Columns past the end of the list split what remains evenly.  That
      only has a meaning when the numbers before them are fractions of
      the table — they must sum to less than 1.

    Anything that would produce a zero-width column raises
    :class:`ValueError`: entries that are zero, negative or not numbers,
    more entries than columns, and lists that leave no room.
    """
    if isinstance(widths, (str, bytes)) or not isinstance(widths, Sequence):
        raise ValueError("table_slide: widths must be a list of numbers or Length values")
    if len(widths) > n_cols:
        raise ValueError(
            f"table_slide: widths has {len(widths)} entries for {n_cols} columns"
        )
    fixed: dict[int, int] = {}
    weights: dict[int, float] = {}
    for i, width in enumerate(widths):
        if isinstance(width, Length):
            if int(width) <= 0:
                raise ValueError(f"table_slide: widths[{i}] must be positive, got {width!r}")
            fixed[i] = int(width)
        elif (
            isinstance(width, bool)
            or not isinstance(width, (int, float))
            or not math.isfinite(width)
            or width <= 0
        ):
            raise ValueError(
                f"table_slide: widths[{i}] must be a positive number (a relative weight) "
                f"or a Length, got {width!r}"
            )
        else:
            weights[i] = float(width)

    unspecified = n_cols - len(widths)
    remaining = table_w - sum(fixed.values())
    if (weights or unspecified) and remaining <= 0:
        raise ValueError(
            "table_slide: the fixed widths leave no room for the other columns"
        )
    out = [0] * n_cols
    for i, width_emu in fixed.items():
        out[i] = width_emu
    total = sum(weights.values())
    if unspecified:
        if total >= 1.0 - 1e-9:
            raise ValueError(
                f"table_slide: widths covers {len(widths)} of {n_cols} columns and leaves no "
                "room for the rest; give every column a width, or use fractions that sum to "
                "less than 1"
            )
        for i, weight in weights.items():
            out[i] = int(round(remaining * weight))
        share = remaining * (1.0 - total) / unspecified
        for i in range(len(widths), n_cols):
            out[i] = int(round(share))
    else:
        for i, weight in weights.items():
            out[i] = int(round(remaining * weight / total))
    # Put the rounding remainder in the last flexible column so the
    # columns add up to the table width exactly.
    flexible = [i for i in range(n_cols) if i not in fixed]
    if flexible:
        out[flexible[-1]] += remaining - sum(out[i] for i in flexible)
    return out


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
