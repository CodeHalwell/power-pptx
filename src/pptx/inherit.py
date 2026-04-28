"""Theme-aware inheritance helpers for color/effect getters.

Phase 1 made every color getter non-mutating: reading a property that
isn't explicitly set returns ``None`` and leaves the XML untouched.
That preserves theme inheritance — but it also means callers who want
the *effective* color (the one PowerPoint will actually render) have to
walk the style hierarchy themselves.

This module provides the read-only resolver that closes that gap.  The
public surface is a single function::

    from pptx.inherit import resolve_color
    rgb = resolve_color(font.color, theme=prs.theme)   # RGBColor or None

Scope (intentionally focused):

* ``MSO_COLOR_TYPE.RGB`` — returns the explicit ``RGBColor``, applying
  the ``brightness`` adjustment if any.
* ``MSO_COLOR_TYPE.SCHEME`` — looks the theme color up via
  ``theme.colors[theme_color]`` and applies the brightness adjustment.
* ``None`` (no explicit color) — returns ``None`` without trying to
  walk slide → layout → master placeholder inheritance.  Implementing
  the full placeholder walk is a substantial follow-up; this resolver
  intentionally stops short of it so callers get a deterministic,
  side-effect-free answer.

Brightness handling matches ``ColorFormat.brightness``: a value in
``[-1.0, 1.0]`` where negative numbers darken the resolved RGB
proportionally and positive numbers lighten it.  The math mirrors
PowerPoint's ``lumMod``/``lumOff`` / ``tint``/``shade`` model closely
enough to be useful for design-system code that needs to render
mock-ups outside PowerPoint (e.g. the lint contrast check planned in
Phase 2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from pptx.dml.color import ColorFormat, RGBColor
from pptx.enum.dml import MSO_COLOR_TYPE

if TYPE_CHECKING:
    from pptx.theme import Theme


def resolve_color(color_format: ColorFormat, *, theme: "Theme | None" = None) -> Optional[RGBColor]:
    """Return the effective `RGBColor` for `color_format`, or ``None``.

    `color_format` is any :class:`~pptx.dml.color.ColorFormat` (including
    the lazy proxy returned by ``Font.color`` / ``LineFormat.color``).

    `theme` is required to resolve theme colors; pass
    ``presentation.theme``.  When a scheme color cannot be resolved
    (e.g. ``theme=None`` or the slot is unmapped) this function returns
    ``None`` rather than raising, so it composes safely with downstream
    callers that fall back to a hard-coded default.
    """
    color_type = color_format.type
    if color_type == MSO_COLOR_TYPE.RGB:
        rgb = color_format.rgb
        if rgb is None:
            return None
        return _apply_brightness(rgb, color_format.brightness)
    if color_type == MSO_COLOR_TYPE.SCHEME:
        if theme is None:
            return None
        try:
            theme_color = color_format.theme_color
        except AttributeError:
            return None
        try:
            base = theme.colors[theme_color]
        except (KeyError, TypeError):
            return None
        return _apply_brightness(base, color_format.brightness)
    return None


def _apply_brightness(rgb: RGBColor, brightness: float | None) -> RGBColor:
    """Lighten/darken `rgb` toward white/black per PowerPoint's brightness model.

    A `brightness` of 0 (or `None`) is a no-op.  Positive values tint
    toward white; negative values shade toward black.  The blend ratio
    is the absolute value of `brightness`, capped at 1.0.
    """
    if not brightness:
        return rgb
    delta = max(-1.0, min(1.0, brightness))
    if delta > 0:
        return _blend(rgb, _WHITE, delta)
    return _blend(rgb, _BLACK, -delta)


def _blend(a: RGBColor, b: RGBColor, t: float) -> RGBColor:
    """Linear blend from `a` toward `b` by ratio `t` in ``[0, 1]``."""
    return RGBColor(
        _u8(a[0] + (b[0] - a[0]) * t),
        _u8(a[1] + (b[1] - a[1]) * t),
        _u8(a[2] + (b[2] - a[2]) * t),
    )


def _u8(value: float) -> int:
    return max(0, min(255, int(round(value))))


_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
_BLACK = RGBColor(0x00, 0x00, 0x00)
