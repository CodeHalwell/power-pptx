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

import contextlib
import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Mapping, Optional

# Re-use the private helpers from recipes rather than reimplement them.
# Same package, same module-private convention.
from power_pptx.design.recipes import (
    _DEFAULT_INSET_X,
    _DEFAULT_INSET_Y,
    _EMU_PER_PT,
    _LINE_PITCH,
    _apply_card_styling,
    _delta_color,
    _fill_text_frame,
    _fit_token,
    _palette,
    _resolve_delta,
    _typography,
    _wrapped_line_count,
)
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from power_pptx.util import Emu, Inches, Length, Pt

if TYPE_CHECKING:
    from power_pptx.design.tokens import DesignTokens, TypographyToken
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


# ---------------------------------------------------------------------------
# Sizing helpers shared by the card components
# ---------------------------------------------------------------------------


def _inches_up(emu: int) -> float:
    """*emu* in inches rounded *up* to two places, so a figure quoted in an error is enough."""
    return math.ceil(emu / 914400 * 100 - 1e-9) / 100


def _component_typography(
    tokens: Optional[DesignTokens],
    name: str,
    *,
    default_size: Length,
    default_bold: Optional[bool] = None,
) -> TypographyToken:
    """Like :func:`_typography`, but never larger than *default_size*.

    A deck's ``heading`` / ``body`` sizes are slide-scale (32 / 16 pt in every
    preset).  A component whose boxes are sized for its own default must not
    inherit them, or its title overprints what sits beneath.  A token that is
    already *smaller* than the default keeps its size.
    """
    token = _typography(tokens, name, default_size=default_size, default_bold=default_bold)
    if token.size is not None and token.size > default_size:
        token = replace(token, size=default_size)
    return token


#: Rows of a KPI card at its default 1.9 in height, top to bottom: the padding above, the
#: value, label and delta boxes, the padding below.  ``kpi_slide`` uses the same numbers.
_KPI_NATURAL = (Inches(0.25), Inches(0.85), Inches(0.40), Inches(0.35), Inches(0.05))
#: The least padding a squeezed KPI card keeps above and below its rows.
_KPI_MIN_PAD = Inches(0.05)


def _kpi_rows(
    height: int, value_pt: float, label_pt: float, delta_pt: float
) -> tuple[int, int, int, int]:
    """Split a KPI card *height* (EMU) into ``(top pad, value, label, delta)`` heights.

    At 1.9 in or more the rows are the fixed ones ``kpi_slide`` uses — a taller card
    centres them, so the extra space is shared above and below.  A shorter card squeezes
    them, padding first, in proportion, down to the height one line of each text needs;
    below that it raises :class:`ValueError`, since the rows would hang below the card.
    The delta row is always reserved, whether or not a delta is shown, so cards in one
    strip keep their values and labels aligned.
    """
    inset = 2 * int(_DEFAULT_INSET_Y)
    need = [int(pt * _LINE_PITCH * _EMU_PER_PT) + inset for pt in (value_pt, label_pt, delta_pt)]
    pad_top, *natural_rows, pad_bottom = (int(n) for n in _KPI_NATURAL)
    natural = [max(n, m) for n, m in zip(natural_rows, need)]
    natural_total = pad_top + sum(natural) + pad_bottom
    min_pad = int(_KPI_MIN_PAD)
    min_total = 2 * min_pad + sum(need)
    if height < min_total:
        raise ValueError(
            f"add_kpi_card: height={Emu(height).inches:.2f} in is too small for the value, "
            f"label and delta rows; make the card at least {_inches_up(min_total):.2f} in tall"
        )
    if height >= natural_total:
        value_h, label_h, delta_h = natural
        return pad_top + (height - natural_total) // 2, value_h, label_h, delta_h
    t = (height - min_total) / (natural_total - min_total)
    value_h, label_h, delta_h = (int(m + t * (n - m)) for m, n in zip(need, natural))
    return int(min_pad + t * (pad_top - min_pad)), value_h, label_h, delta_h


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

    The value, label and delta rows are laid out from *height*: at the
    default 1.9 in they match ``kpi_slide``, a taller card centres them and
    a shorter one squeezes them.  A card too short to hold one line of each
    (about 1.3 in with the default type, more with large token sizes)
    raises :class:`ValueError` naming the minimum height — nothing is
    added to the slide.

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

    # Work the rows out before touching the slide, so a card that cannot hold its
    # text raises without leaving a half-built one behind.
    pad_top, value_h, label_h, delta_h = _kpi_rows(
        int(height),
        value_token.size.pt if value_token.size is not None else 30.0,
        label_token.size.pt if label_token.size is not None else 12.0,
        delta_token.size.pt if delta_token.size is not None else 11.0,
    )

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

    # Vertical layout inside the card, derived from its height by _kpi_rows (which
    # mirrors kpi_slide's rows at the default height).
    inner_top = Length(top + pad_top)
    label_top = Length(inner_top + value_h)
    delta_top = Length(label_top + label_h)

    value_box = slide.shapes.add_textbox(left, inner_top, width, Length(value_h))
    _fill_text_frame(
        value_box.text_frame,
        str(value),
        token=value_token,
        color=value_color,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        shrink_to_fit=True,
    )

    label_box = slide.shapes.add_textbox(left, label_top, width, Length(label_h))
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
            delta_box = slide.shapes.add_textbox(left, delta_top, width, Length(delta_h))
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
        with contextlib.suppress(AttributeError, NotImplementedError):
            shape.lint_group = group_name

    return KpiCard(card=card, value_box=value_box, label_box=label_box, delta_box=delta_box)


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
        with contextlib.suppress(AttributeError, NotImplementedError):
            shape.lint_group = group_name

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
        with contextlib.suppress(AttributeError, NotImplementedError):
            target_tick.lint_group = bar.track.lint_group

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
        with contextlib.suppress(AttributeError, NotImplementedError):
            shape.lint_group = group_name

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
    width minus the gutters and stacked left-to-right.  *height* is each
    card's height, so a strip too short for :func:`add_kpi_card`'s rows
    raises :class:`ValueError` naming the minimum, with nothing added.

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
        card_left = Length(int(left) + i * (int(card_w) + int(gutter)))
        delta = (
            {"delta": kpi["delta"]}
            if "delta" in kpi
            else ({"delta_text": kpi["delta_text"]} if "delta_text" in kpi else None)
        )
        cards.append(
            add_kpi_card(
                slide,
                left=card_left,
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

#: Smallest the article card shrinks a long title to before letting it run to a third line.
_ARTICLE_TITLE_MIN_PT = 12.0


def _fit_title(token: TypographyToken, title: str, width: int) -> tuple[TypographyToken, int]:
    """Shrink *token* until *title* wraps to at most two lines in *width* EMU.

    Goes a whole point at a time and stops at 12 pt (or the token's own size, if
    smaller); a title that still needs more lines keeps that size and is allowed
    to run on.  Returns the resized token and the number of lines the title takes.
    """
    size = token.size.pt if token.size is not None else 16.0
    floor = min(_ARTICLE_TITLE_MIN_PT, size)
    bold = bool(token.bold)
    lines = _wrapped_line_count(title, width, size, bold=bold)
    while lines > 2 and size > floor:
        size = max(floor, float(math.ceil(size) - 1))
        lines = _wrapped_line_count(title, width, size, bold=bold)
    return replace(token, size=Pt(size)), lines


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

    The type is sized for the card, not for the deck: the title is at most
    16 pt and the blurb at most 11 pt whatever the tokens' ``heading`` /
    ``body`` sizes are (a smaller token size is kept).  A title that wraps
    to a third line first shrinks, down to 12 pt, and the box under it
    grows with it, so the blurb always starts below the title; a blurb too
    long for its space shrinks as well, down to 9 pt.  A card too short for
    its title, one line of blurb and the CTA, or too narrow to hold text,
    raises :class:`ValueError` naming the size needed — nothing is added to
    the slide.
    """
    fill_color = _palette(tokens, ("surface", "lt2"))
    border_color = _palette(tokens, ("muted", "lt1"))
    title_color = _palette(tokens, ("primary", "neutral"))
    blurb_color = _palette(tokens, ("muted", "neutral"))

    pad = Inches(0.25)
    gap = Inches(0.05)
    cta_h = Inches(0.35) if cta_text else Length(0)
    inner_w = int(width) - 2 * int(pad)
    min_width = 2 * int(pad) + int(Inches(0.5))
    if inner_w < int(Inches(0.5)):
        raise ValueError(
            f"add_article_card: width={Emu(width).inches:.2f} in is too narrow to hold "
            f"text; make the card at least {_inches_up(min_width):.2f} in wide"
        )

    # Work the inner layout out before touching the slide, so a card that cannot
    # hold its content raises without leaving a half-built one behind.
    text_w = inner_w - 2 * int(_DEFAULT_INSET_X)
    title_token, title_lines = _fit_title(
        _component_typography(tokens, "heading", default_size=Pt(16), default_bold=True),
        title,
        text_w,
    )
    title_pt = title_token.size.pt if title_token.size is not None else 16.0
    # A one-line title keeps the 0.5 in box the layout has always had; a longer one grows it.
    title_h = max(
        int(Inches(0.5)),
        int(title_lines * title_pt * _LINE_PITCH * _EMU_PER_PT) + 2 * int(_DEFAULT_INSET_Y),
    )
    blurb_token = _component_typography(tokens, "body", default_size=Pt(11))
    blurb_pt = blurb_token.size.pt if blurb_token.size is not None else 11.0
    min_blurb_h = (
        int(blurb_pt * _LINE_PITCH * _EMU_PER_PT) + 2 * int(_DEFAULT_INSET_Y)
        if blurb.strip()
        else 0
    )
    min_height = 2 * int(pad) + title_h + int(cta_h) + 2 * int(gap) + min_blurb_h
    if int(height) < min_height:
        raise ValueError(
            f"add_article_card: height={Emu(height).inches:.2f} in is too small for a "
            f"{title_lines}-line title, the blurb{' and the CTA' if cta_text else ''}; make "
            f"the card at least {_inches_up(min_height):.2f} in tall"
        )
    blurb_top = Length(top + pad + title_h + gap)
    blurb_h = Length(int(height) - min_height + min_blurb_h)
    if blurb.strip():
        blurb_token = _fit_token(
            blurb_token, [blurb], text_w, int(blurb_h) - 2 * int(_DEFAULT_INSET_Y)
        )

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

    title_box = slide.shapes.add_textbox(
        Length(left + pad), Length(top + pad), Length(width - 2 * pad), Length(title_h)
    )
    _fill_text_frame(
        title_box.text_frame,
        title,
        token=title_token,
        color=title_color,
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
        shrink_to_fit=True,
    )

    blurb_box = slide.shapes.add_textbox(
        Length(left + pad), blurb_top, Length(width - 2 * pad), blurb_h
    )
    _fill_text_frame(
        blurb_box.text_frame,
        blurb,
        token=blurb_token,
        color=blurb_color,
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.TOP,
        word_wrap=True,
        shrink_to_fit=True,
    )

    cta = None
    if cta_text:
        cta_w = Length(min(int(Inches(1.2)), inner_w))
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
        with contextlib.suppress(AttributeError, NotImplementedError):
            shape.lint_group = group_name

    return ArticleCard(card=card, title_box=title_box, blurb_box=blurb_box, cta=cta)
