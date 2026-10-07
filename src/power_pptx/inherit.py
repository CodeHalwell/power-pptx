"""Theme-aware inheritance helpers for color/effect getters.

Phase 1 made every color getter non-mutating: reading a property that
isn't explicitly set returns ``None`` and leaves the XML untouched.
That preserves theme inheritance — but it also means callers who want
the *effective* color (the one PowerPoint will actually render) have to
walk the style hierarchy themselves.

This module provides the read-only resolver that closes that gap.  The
public surface is a single function::

    from power_pptx.inherit import resolve_color
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
``[-1.0, 1.0]`` where negative numbers darken the resolved color and
positive numbers lighten it.  It is applied the way PowerPoint applies the
``lumMod`` / ``lumOff`` transforms that ``brightness`` writes -- to the HSL
*luminance*, leaving hue and saturation alone -- and not by blending the RGB
channels toward black or white, which gives visibly duller results for
saturated colors.  That is close enough to what PowerPoint renders to be
useful for design-system code that needs to render mock-ups outside
PowerPoint.
"""

from __future__ import annotations

import colorsys
from typing import TYPE_CHECKING, Optional

from power_pptx.dml.color import ColorFormat, RGBColor
from power_pptx.enum.dml import MSO_COLOR_TYPE

if TYPE_CHECKING:
    from power_pptx.theme import Theme


def resolve_color(color_format: ColorFormat, *, theme: "Theme | None" = None) -> Optional[RGBColor]:
    """Return the effective `RGBColor` for `color_format`, or ``None``.

    `color_format` is any :class:`~power_pptx.dml.color.ColorFormat` (including
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
    """Lighten/darken `rgb` the way PowerPoint applies ``lumMod`` / ``lumOff``.

    A `brightness` of 0 (or `None`) is a no-op.  Otherwise the HSL
    *luminance* `l` is adjusted and hue and saturation are kept (PowerPoint
    does not blend the RGB channels toward black or white).  `brightness` is
    capped to ``[-1.0, 1.0]``; negative values shade, positive values tint:

    * shade: ``lumMod = 1 - |brightness|``, so ``l' = l * (1 - |brightness|)``
    * tint: ``lumMod = 1 - brightness`` and ``lumOff = brightness``, so
      ``l' = l * (1 - brightness) + brightness``
    """
    if not brightness:
        return rgb
    delta = max(-1.0, min(1.0, brightness))
    lum_mod = 1.0 - abs(delta)  # a shade and a tint both scale the luminance down ...
    lum_off = max(delta, 0.0)  # ... but only a tint then adds the offset back
    hue, lum, sat = colorsys.rgb_to_hls(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
    r, g, b = colorsys.hls_to_rgb(hue, max(0.0, min(1.0, lum * lum_mod + lum_off)), sat)
    return RGBColor(_u8(r * 255.0), _u8(g * 255.0), _u8(b * 255.0))


def _u8(value: float) -> int:
    return max(0, min(255, int(round(value))))
