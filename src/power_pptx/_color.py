"""Internal canonical colour-coercion helper.

Most public colour-accepting setters in power-pptx historically accepted
exactly one shape (``RGBColor`` for ``shape.fill.fore_color.rgb``, hex
strings for ``linear_gradient``, mixed for ``chart.apply_palette``).  The
asymmetry was a category-of-bug for both human and LLM authoring.

:func:`coerce_color` accepts every shape any documented surface in the
library has accepted historically, so a public setter that routes a
caller-supplied colour through this helper "just works" with hex
strings, ``RGBColor`` instances, and 3-tuples.

Supported inputs
~~~~~~~~~~~~~~~~

* :class:`~power_pptx.dml.color.RGBColor` — returned as-is.
* ``str`` — 6-digit hex, with or without leading ``"#"``.  3-digit
  shorthand (``"#FFF"``) is **not** accepted; write the full form.
* 3-tuple / 3-list of ``int`` in ``[0, 255]`` — positional R, G, B.

Anything else raises :class:`TypeError` with a message that points to
this helper, so callers see one consistent error regardless of which
public setter they hit.
"""

from __future__ import annotations

from typing import Any

from power_pptx.dml.color import RGBColor

ColorLike = "RGBColor | str | tuple[int, int, int] | list[int]"


def coerce_color(value: Any) -> RGBColor:
    """Coerce *value* to an :class:`RGBColor`.

    See module docstring for the accepted shapes.
    """
    if isinstance(value, RGBColor):
        return value
    if isinstance(value, str):
        s = value.lstrip("#")
        if len(s) != 6:
            raise ValueError(
                "color hex string must be 6 digits "
                "(e.g. '#3C2F80' or '3C2F80'); got %r" % value
            )
        try:
            return RGBColor.from_hex(s)
        except ValueError as exc:
            raise ValueError("invalid color hex string %r: %s" % (value, exc)) from exc
    if isinstance(value, (tuple, list)) and len(value) == 3:
        try:
            r, g, b = (int(c) for c in value)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "color 3-tuple must contain integers in [0, 255]; got %r" % (value,)
            ) from exc
        return RGBColor(r, g, b)
    raise TypeError(
        "expected a color-like value (RGBColor, '#RRGGBB' hex string, "
        "or 3-tuple of ints); got %r" % (value,)
    )


# Re-export under the historical underscore name as well so
# ``from power_pptx._color import _coerce`` works.
_coerce = coerce_color
