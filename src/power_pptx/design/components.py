"""Shape-level building blocks layered on top of the slide recipes.

The :mod:`power_pptx.design.recipes` module covers whole-slide layouts
(``title_slide``, ``kpi_slide``, …); this module exposes the components
those recipes are built from so callers can compose mixed layouts with
brand-consistent components.

Two public callables today, both intentionally small:

* :func:`add_kpi_card` — a single KPI tile (label + headline value +
  optional delta), styled from a :class:`DesignTokens` instance.
* :func:`add_progress_bar` — a track + fill rounded-rectangle pair
  representing a 0..1 fraction.

Both accept an optional ``tokens`` argument that drives palette and
typography. When omitted, sensible defaults derived from the chart
palette are used. Each component is created using the existing
``slide.shapes.add_*`` primitives and returns a small dataclass
exposing the constituent shapes — callers can reach into ``.card`` /
``.value_box`` / ``.fill`` / ``.track`` for further per-deck tweaks
without re-implementing the layout.

The intentional shape stacking inside these components (label box on
top of card, fill bar on top of track) is tagged with
``shape.lint_group`` so :mod:`power_pptx.lint` does not flag them as
overlap warnings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping, Optional

from power_pptx.design.tokens import DesignTokens
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from power_pptx.util import Inches, Length, Pt

# Re-use the private helpers from recipes rather than reimplement them.
# Same package, same module-private convention.
from power_pptx.design.recipes import (
    _apply_card_styling,
    _delta_color,
    _fill_text_frame,
    _palette,
    _resolve_delta,
    _typography,
)

if TYPE_CHECKING:
    from power_pptx.shapes.autoshape import Shape
    from power_pptx.slide import Slide


__all__ = (
    "KpiCard",
    "ProgressBar",
    "Gauge",
    "StatusPill",
    "StatStrip",
    "ArticleCard",
    "add_kpi_card",
    "add_progress_bar",
    "add_gauge",
    "add_status_pill",
    "add_stat_strip",
    "add_article_card",
)


@dataclass
class KpiCard:
    """Bundle of shapes produced by :func:`add_kpi_card`.

    Use ``card`` for global tweaks (border colour, fill, shadow), the
    text boxes for typography or content edits.
    """

    card: Any
    value_box: Any
    label_box: Any
    delta_box: Optional[Any] = None


@dataclass
class ProgressBar:
    """Bundle of shapes produced by :func:`add_progress_bar`.

    ``track`` is the full-width background; ``fill`` is the
    proportionally-sized foreground.
    """

    track: Any
    fill: Any


def add_kpi_card(
    slide: "Slide",
    *,
    left: Length,
    top: Length,
    width: Length,
    height: Length,
    label: str,
    value: str,
    delta: Optional[Mapping[str, Any]] = None,
    tokens: Optional[DesignTokens] = None,
) -> KpiCard:
    """Add a single KPI card (label + value + optional delta) to *slide*.

    `delta`, when supplied, is a mapping with the same shape consumed
    by :func:`power_pptx.design.recipes.kpi_slide` — ``{"delta": 0.27}``
    renders as ``+27%``, ``{"delta_text": "+14 pts"}`` renders verbatim.
    Tinted from the palette's ``positive`` / ``negative`` slot.

    Returns a :class:`KpiCard` bundle so callers can reach into the
    constituent shapes for per-deck tweaks without re-implementing
    the layout.
    """
    fill_color = _palette(tokens, ("surface", "lt2"))
    # Border tracks the brand: fall through muted → lt1 → neutral → primary so
    # the outline never lands on an off-palette default (a clashing pale blue
    # on a non-blue scheme) or silently disappears when muted/lt1 are unset.
    border_color = _palette(tokens, ("muted", "lt1", "neutral", "primary"))
    value_color = _palette(tokens, ("primary", "neutral"))
    label_color = _palette(tokens, ("muted",))

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
    _apply_card_styling(card, tokens)
    card.text_frame.text = ""

    # Vertical layout inside the card. Heights chosen to mirror
    # kpi_slide's existing recipe so the visual matches when used in
    # the same deck.
    value_h = Inches(0.85)
    label_h = Inches(0.4)
    delta_h = Inches(0.35)
    inner_top = Length(top + Inches(0.25))
    label_top = Length(top + Inches(1.10))
    delta_top = Length(top + Inches(1.50))

    value_box = slide.shapes.add_textbox(left, inner_top, width, value_h)
    _fill_text_frame(
        value_box.text_frame,
        str(value),
        token=value_token,
        color=value_color,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        shrink_to_fit=True,
    )

    label_box = slide.shapes.add_textbox(left, label_top, width, label_h)
    _fill_text_frame(
        label_box.text_frame,
        str(label),
        token=label_token,
        color=label_color,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.TOP,
        shrink_to_fit=True,
    )

    delta_box = None
    if delta is not None:
        d_text, d_sign = _resolve_delta(delta)
        if d_text is not None:
            delta_box = slide.shapes.add_textbox(left, delta_top, width, delta_h)
            _fill_text_frame(
                delta_box.text_frame,
                d_text,
                token=delta_token,
                color=_delta_color(tokens, d_sign),
                align=PP_ALIGN.CENTER,
                anchor=MSO_ANCHOR.TOP,
                shrink_to_fit=True,
            )

    # Tag the stack so the lint pass treats them as one intentional
    # group, not three overlapping shapes.
    group_name = f"kpi_card@{int(left)},{int(top)}"
    for shape in (card, value_box, label_box, delta_box):
        if shape is None:
            continue
        try:
            shape.lint_group = group_name
        except (AttributeError, NotImplementedError):
            pass

    return KpiCard(
        card=card, value_box=value_box, label_box=label_box, delta_box=delta_box
    )


def add_progress_bar(
    slide: "Slide",
    *,
    left: Length,
    top: Length,
    width: Length,
    height: Length,
    fraction: float,
    tokens: Optional[DesignTokens] = None,
    fill_color: Any = None,
    track_color: Any = None,
) -> ProgressBar:
    """Add a horizontal progress bar (track + fill) to *slide*.

    `fraction` is clamped to ``[0.0, 1.0]``. The fill shape's width is
    ``round(fraction * width)``; when the fraction is zero the fill is
    still emitted (with zero width) so callers can mutate it later
    (e.g. animate the fill on click).

    Colours fall back to the design tokens' ``primary`` / ``surface``
    palette slots when ``fill_color`` / ``track_color`` are ``None``.
    Pass any colour-like (``RGBColor``, hex string, ``(r, g, b)``)
    to override.
    """
    if not 0.0 <= float(fraction) <= 1.0:
        # Clamp rather than raise — values from live data sources are
        # often 99.x or 100.1 due to rounding; raising on those is
        # hostile.
        fraction = max(0.0, min(1.0, float(fraction)))

    # Track colour: when the caller doesn't pin one, prefer a translucent
    # ``neutral`` overlay rather than the opaque ``surface`` slot.  ``surface``
    # is nearly identical to a dark slide background, so the track (and a
    # gauge's target tick floating on it) would vanish on dark decks; a
    # low-alpha neutral reads against both light and dark backgrounds.
    track_alpha: Optional[float] = None
    if track_color is not None:
        from power_pptx._color import coerce_color

        resolved_track = coerce_color(track_color)
    else:
        neutral = _palette(tokens, ("neutral",))
        if neutral is not None:
            resolved_track = neutral
            track_alpha = 0.14
        else:
            resolved_track = _palette(tokens, ("surface", "lt2"))
    resolved_fill = _coerce_or_token(fill_color, tokens, ("primary", "accent", "neutral"))

    track = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    if resolved_track is not None:
        track.fill.solid()
        track.fill.fore_color.rgb = resolved_track
        if track_alpha is not None:
            track.fill.fore_color.alpha = track_alpha
    else:
        track.fill.background()
    track.line.fill.background()
    track.text_frame.text = ""

    fill_w = Length(int(round(int(width) * fraction)))
    fill = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, fill_w, height)
    if resolved_fill is not None:
        fill.fill.solid()
        fill.fill.fore_color.rgb = resolved_fill
    else:
        fill.fill.background()
    fill.line.fill.background()
    fill.text_frame.text = ""

    group_name = f"progress_bar@{int(left)},{int(top)}"
    for shape in (track, fill):
        try:
            shape.lint_group = group_name
        except (AttributeError, NotImplementedError):
            pass

    return ProgressBar(track=track, fill=fill)


def _coerce_or_token(value, tokens, fallback_keys):
    """Return an RGBColor for ``value``, or read from ``tokens`` palette."""
    if value is None:
        return _palette(tokens, fallback_keys)
    from power_pptx._color import coerce_color

    return coerce_color(value)


# ---------------------------------------------------------------------------
# Linear gauge (fraction visualised as a slim horizontal bar with target tick)
# ---------------------------------------------------------------------------


@dataclass
class Gauge:
    """Bundle of shapes produced by :func:`add_gauge`.

    A linear gauge is shaped like a progress bar but adds a small
    target tick — useful for "62 of 80 target". The radial variant
    is intentionally not implemented in this module: arc rendering
    needs a freeform path and produces visibly different geometry
    on PowerPoint vs LibreOffice.
    """

    track: Any
    fill: Any
    target_tick: Optional[Any]


def add_gauge(
    slide: "Slide",
    *,
    left: Length,
    top: Length,
    width: Length,
    height: Length,
    fraction: float,
    target: Optional[float] = None,
    tokens: Optional[DesignTokens] = None,
    fill_color: Any = None,
    track_color: Any = None,
    target_color: Any = None,
) -> Gauge:
    """Add a linear gauge: progress bar plus optional target tick.

    `fraction` and `target` are both ``[0.0, 1.0]`` (clamped). When
    ``target`` is ``None`` no tick is drawn — the gauge degrades to a
    lightly-styled progress bar so the same call can be used either way.
    The tick is a thin vertical rectangle in the deck's ``negative``
    palette slot (or red as a final fallback) so it stays legible
    against the fill colour.
    """
    bar = add_progress_bar(
        slide,
        left=left,
        top=top,
        width=width,
        height=height,
        fraction=fraction,
        tokens=tokens,
        fill_color=fill_color,
        track_color=track_color,
    )
    target_tick = None
    if target is not None:
        t = max(0.0, min(1.0, float(target)))
        tick_w = max(int(Inches(0.04)), 1)  # ~3px on 96dpi
        tick_x = Length(int(left) + int(round(int(width) * t)) - tick_w // 2)
        target_tick = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            tick_x,
            Length(int(top) - int(Inches(0.04))),
            Length(tick_w),
            Length(int(height) + int(Inches(0.08))),
        )
        resolved = _coerce_or_token(target_color, tokens, ("negative", "danger"))
        if resolved is None:
            resolved = _coerce_or_token("#DD2233", None, ())
        target_tick.fill.solid()
        target_tick.fill.fore_color.rgb = resolved
        target_tick.line.fill.background()
        # Tag with the same lint group so the linter doesn't warn.
        try:
            target_tick.lint_group = bar.track.lint_group
        except (AttributeError, NotImplementedError):
            pass

    return Gauge(track=bar.track, fill=bar.fill, target_tick=target_tick)


# ---------------------------------------------------------------------------
# Status pill — small coloured rounded rectangle with centred text
# ---------------------------------------------------------------------------


@dataclass
class StatusPill:
    pill: Any
    label: Any


def add_status_pill(
    slide: "Slide",
    *,
    left: Length,
    top: Length,
    width: Length,
    height: Length,
    text: str,
    accent: Any = None,
    tokens: Optional[DesignTokens] = None,
    text_color: Any = None,
) -> StatusPill:
    """Add a coloured pill-shape with centred label text.

    `accent` controls the pill fill. When ``None``, falls back to the
    token palette's ``accent`` slot, then ``primary``. ``text_color``
    falls back to ``on_primary`` (or white) for contrast.
    """
    fill_rgb = _coerce_or_token(accent, tokens, ("accent", "primary", "neutral"))
    if text_color is None:
        text_rgb = _palette(tokens, ("on_primary",))
        if text_rgb is None:
            from power_pptx.dml.color import RGBColor

            text_rgb = RGBColor(0xFF, 0xFF, 0xFF)
    else:
        from power_pptx._color import coerce_color

        text_rgb = coerce_color(text_color)

    pill = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    if fill_rgb is not None:
        pill.fill.solid()
        pill.fill.fore_color.rgb = fill_rgb
    pill.line.fill.background()
    pill.text_frame.text = ""

    label = slide.shapes.add_textbox(left, top, width, height)
    _fill_text_frame(
        label.text_frame,
        text,
        token=_typography(tokens, "body", default_size=Pt(10), default_bold=True),
        color=text_rgb,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        shrink_to_fit=True,
    )

    group_name = f"status_pill@{int(left)},{int(top)}"
    for shape in (pill, label):
        try:
            shape.lint_group = group_name
        except (AttributeError, NotImplementedError):
            pass

    return StatusPill(pill=pill, label=label)


# ---------------------------------------------------------------------------
# Stat strip — n KPI tiles laid out across a bounding box with a gutter
# ---------------------------------------------------------------------------


@dataclass
class StatStrip:
    cards: list


def add_stat_strip(
    slide: "Slide",
    *,
    left: Length,
    top: Length,
    width: Length,
    height: Length,
    items: "list[Mapping[str, Any]]",
    gutter: Length = Inches(0.25),
    tokens: Optional[DesignTokens] = None,
) -> StatStrip:
    """Add ``len(items)`` KPI tiles across a strip with the given gutter.

    Each item dict accepts the same fields as ``add_kpi_card``'s
    ``label`` / ``value`` / ``delta``. Cards are sized to the strip's
    width minus the gutters and stacked left-to-right.

    Returns a :class:`StatStrip` whose ``.cards`` is a list of
    :class:`KpiCard` bundles, in the same order as `items`.
    """
    if not items:
        return StatStrip(cards=[])

    n = len(items)
    available = int(width) - (n - 1) * int(gutter)
    card_w = Length(available // n)
    cards = []
    for i, kpi in enumerate(items):
        l = Length(int(left) + i * (int(card_w) + int(gutter)))
        delta = (
            {"delta": kpi["delta"]}
            if "delta" in kpi
            else ({"delta_text": kpi["delta_text"]} if "delta_text" in kpi else None)
        )
        cards.append(
            add_kpi_card(
                slide,
                left=l,
                top=top,
                width=card_w,
                height=height,
                label=str(kpi.get("label", "")),
                value=str(kpi.get("value", "")),
                delta=delta,
                tokens=tokens,
            )
        )
    return StatStrip(cards=cards)


# ---------------------------------------------------------------------------
# Article card — title + blurb with optional CTA pill
# ---------------------------------------------------------------------------


@dataclass
class ArticleCard:
    card: Any
    title_box: Any
    blurb_box: Any
    cta: Optional[StatusPill]


def add_article_card(
    slide: "Slide",
    *,
    left: Length,
    top: Length,
    width: Length,
    height: Length,
    title: str,
    blurb: str = "",
    cta_text: Optional[str] = None,
    tokens: Optional[DesignTokens] = None,
) -> ArticleCard:
    """Add a brand-styled article card (title + blurb + optional CTA).

    The card uses the same surface / muted / primary palette slots as
    the slide-level recipes for visual consistency. The CTA, when
    supplied, is rendered as a small :class:`StatusPill` anchored at
    the card's bottom-left.
    """
    fill_color = _palette(tokens, ("surface", "lt2"))
    border_color = _palette(tokens, ("muted", "lt1"))
    title_color = _palette(tokens, ("primary", "neutral"))
    blurb_color = _palette(tokens, ("muted", "neutral"))

    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    if fill_color is not None:
        card.fill.solid()
        card.fill.fore_color.rgb = fill_color
    else:
        card.fill.background()
    if border_color is not None:
        card.line.color.rgb = border_color
        card.line.width = Pt(0.75)
    _apply_card_styling(card, tokens)
    card.text_frame.text = ""

    pad = Inches(0.25)
    title_h = Inches(0.5)
    cta_h = Inches(0.35) if cta_text else Length(0)
    blurb_top = Length(top + pad + title_h + Inches(0.05))
    blurb_h = Length(int(height) - int(pad) * 2 - int(title_h) - int(cta_h) - Inches(0.1))

    title_box = slide.shapes.add_textbox(
        Length(left + pad), Length(top + pad), Length(width - 2 * pad), title_h
    )
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=_typography(tokens, "heading", default_size=Pt(16), default_bold=True),
        color=title_color,
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
    )

    blurb_box = slide.shapes.add_textbox(
        Length(left + pad), blurb_top, Length(width - 2 * pad), blurb_h
    )
    _fill_text_frame(
        blurb_box.text_frame,
        blurb,
        token=_typography(tokens, "body", default_size=Pt(11)),
        color=blurb_color,
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
        word_wrap=True,
    )

    cta = None
    if cta_text:
        cta_w = Inches(1.2)
        cta = add_status_pill(
            slide,
            left=Length(left + pad),
            top=Length(top + height - pad - cta_h),
            width=cta_w,
            height=cta_h,
            text=cta_text,
            tokens=tokens,
        )

    group_name = f"article_card@{int(left)},{int(top)}"
    for shape in (card, title_box, blurb_box):
        try:
            shape.lint_group = group_name
        except (AttributeError, NotImplementedError):
            pass

    return ArticleCard(card=card, title_box=title_box, blurb_box=blurb_box, cta=cta)
