"""Token-resolving style facade for shapes.

:class:`ShapeStyle` is the high-level "design system" view of a shape:
callers assign whole tokens to ``shape.style.fill`` / ``shape.style.shadow``
/ etc., and the facade fans the assignment out into the underlying
:class:`~pptx.dml.fill.FillFormat`, :class:`~pptx.dml.line.LineFormat`,
and :class:`~pptx.dml.effect.ShadowFormat` calls.

This is purely additive — the low-level fill/line/shadow APIs continue to
work and are the right tool when a caller needs fine-grained control.
``shape.style`` exists so recipe code stays declarative::

    shape.style.fill = tokens.palette["primary"]
    shape.style.line = tokens.palette["primary"]
    shape.style.shadow = tokens.shadows["card"]
    shape.style.text_color = tokens.palette["neutral"]
    shape.style.font = tokens.typography["body"]
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from pptx.design.tokens import ShadowToken, TypographyToken
from pptx.dml.color import RGBColor

if TYPE_CHECKING:
    from pptx.shapes.base import BaseShape


class ShapeStyle:
    """Style facade that resolves design tokens onto the shape's low-level proxies.

    Attribute *getters* are deliberately not implemented for token-shaped
    properties: the underlying fill/line/shadow APIs are the source of
    truth for what's actually set, and a getter that round-trips a token
    through the shape's XML can't faithfully reconstruct the token's
    name.  Use ``shape.fill`` / ``shape.line`` / ``shape.shadow`` for
    reads.
    """

    def __init__(self, shape: "BaseShape"):
        self._shape = shape

    # ------------------------------------------------------------------
    # Fill
    # ------------------------------------------------------------------

    @property
    def fill(self) -> None:
        raise AttributeError(
            "ShapeStyle.fill is write-only; read shape.fill for the underlying proxy"
        )

    @fill.setter
    def fill(self, value: Optional[RGBColor]) -> None:
        """Apply a solid fill in *value* to the shape.

        Accepts an :class:`RGBColor` (hex string / 3-tuple are coerced
        the same way as :class:`pptx.design.tokens.DesignTokens`).  Pass
        ``None`` to clear the fill (transparent).
        """
        from pptx.design.tokens import _coerce_color  # noqa: PLC0415

        fill = self._shape.fill  # type: ignore[attr-defined]
        if value is None:
            fill.background()
            return
        rgb = _coerce_color(value)
        fill.solid()
        fill.fore_color.rgb = rgb

    # ------------------------------------------------------------------
    # Line
    # ------------------------------------------------------------------

    @property
    def line(self) -> None:
        raise AttributeError(
            "ShapeStyle.line is write-only; read shape.line for the underlying proxy"
        )

    @line.setter
    def line(self, value: Optional[RGBColor]) -> None:
        """Apply a solid line color.  ``None`` clears the line."""
        from pptx.design.tokens import _coerce_color  # noqa: PLC0415

        line = self._shape.line  # type: ignore[attr-defined]
        if value is None:
            line.fill.background()
            return
        rgb = _coerce_color(value)
        line.color.rgb = rgb

    # ------------------------------------------------------------------
    # Shadow
    # ------------------------------------------------------------------

    @property
    def shadow(self) -> None:
        raise AttributeError(
            "ShapeStyle.shadow is write-only; read shape.shadow for the underlying proxy"
        )

    @shadow.setter
    def shadow(self, value: Optional[ShadowToken]) -> None:
        """Apply a :class:`ShadowToken` to the shape's outer shadow.

        Each unset token attribute is left untouched on the shape, so a
        token that only specifies ``blur_radius`` won't blow away an
        existing distance/direction.  ``None`` clears the shadow entirely.
        """
        shadow = self._shape.shadow
        if value is None:
            shadow.blur_radius = None
            shadow.distance = None
            shadow.direction = None
            return
        if not isinstance(value, ShadowToken):
            value = ShadowToken.from_value(value)
        if value.blur_radius is not None:
            shadow.blur_radius = value.blur_radius
        if value.distance is not None:
            shadow.distance = value.distance
        if value.direction is not None:
            shadow.direction = value.direction
        if value.color is not None:
            shadow.color.rgb = value.color
        if value.alpha is not None:
            # alpha requires color to exist first; if the token didn't
            # set an explicit color and none is present, leave alpha
            # alone (PowerPoint inherits a black shadow color).
            try:
                shadow.color.alpha = value.alpha
            except ValueError:
                shadow.color.rgb = RGBColor(0, 0, 0)
                shadow.color.alpha = value.alpha

    # ------------------------------------------------------------------
    # Text color / font (for shapes with text frames)
    # ------------------------------------------------------------------

    @property
    def text_color(self) -> None:
        raise AttributeError(
            "ShapeStyle.text_color is write-only; iterate runs for reads"
        )

    @text_color.setter
    def text_color(self, value: Optional[RGBColor]) -> None:
        """Set every run's font color in this shape's text frame.

        Silently no-ops on shapes that don't have a text frame.
        """
        from pptx.design.tokens import _coerce_color  # noqa: PLC0415

        text_frame = _text_frame(self._shape)
        if text_frame is None:
            return
        rgb = None if value is None else _coerce_color(value)
        for paragraph in text_frame.paragraphs:
            for run in paragraph.runs:
                if rgb is None:
                    # Best-effort clear: assigning None to font.color.rgb
                    # is a no-op upstream, so leave it untouched.
                    continue
                run.font.color.rgb = rgb

    @property
    def font(self) -> None:
        raise AttributeError(
            "ShapeStyle.font is write-only; iterate runs for reads"
        )

    @font.setter
    def font(self, value: TypographyToken) -> None:
        """Apply a :class:`TypographyToken` to every run in the text frame.

        Unset token attributes (``size`` / ``bold`` / ``italic`` /
        ``color``) leave the run's existing values alone.
        """
        if not isinstance(value, TypographyToken):
            value = TypographyToken.from_value(value)
        text_frame = _text_frame(self._shape)
        if text_frame is None:
            return
        for paragraph in text_frame.paragraphs:
            for run in paragraph.runs:
                font = run.font
                font.name = value.family
                if value.size is not None:
                    font.size = value.size
                if value.bold is not None:
                    font.bold = value.bold
                if value.italic is not None:
                    font.italic = value.italic
                if value.color is not None:
                    font.color.rgb = value.color


def _text_frame(shape: "BaseShape"):
    if getattr(shape, "has_text_frame", False):
        return shape.text_frame  # type: ignore[attr-defined]
    return None
