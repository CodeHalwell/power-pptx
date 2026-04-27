"""Picture image effects: transparency, brightness, contrast, and recolor."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pptx.dml.color import RGBColor
    from pptx.oxml.dml.fill import CT_Blip


# Sepia duotone: dark warm brown → light cream, matching PowerPoint's built-in preset.
_SEPIA_DARK = "532400"
_SEPIA_LIGHT = "FFEFCA"


class PictureEffects:
    """Provides access to image-level visual effects on a |Picture| shape.

    Exposes transparency (alpha), brightness, contrast, and recolor.  All reads
    are non-mutating — if no explicit effect is present the property returns a
    neutral sentinel value (``0.0`` for numeric adjustments, ``None`` for recolor).
    Writes lazily create the required ``<a:blip>`` child elements.

    Access via :attr:`pptx.shapes.picture.Picture.effects`.
    """

    def __init__(self, blip: CT_Blip):
        self._blip = blip

    # ------------------------------------------------------------------
    # transparency
    # ------------------------------------------------------------------

    @property
    def transparency(self) -> float:
        """Read/write float in ``[0.0, 1.0]``: ``0.0`` = fully opaque (default), ``1.0`` = invisible.

        Maps to ``<a:alphaModFix amt="N"/>`` where ``amt`` is the *remaining* opacity
        (``100000`` = fully opaque).  Setting to ``0.0`` removes the element entirely,
        restoring full opacity.
        """
        alphaModFix = self._blip.alphaModFix
        if alphaModFix is None:
            return 0.0
        amt = alphaModFix.amt
        return round(1.0 - amt, 10)

    @transparency.setter
    def transparency(self, value: float) -> None:
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"transparency must be between 0.0 and 1.0, got {value!r}")
        if value == 0.0:
            self._blip._remove_alphaModFix()  # pyright: ignore[reportPrivateUsage]
        else:
            self._blip.get_or_add_alphaModFix().amt = 1.0 - value  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # brightness
    # ------------------------------------------------------------------

    @property
    def brightness(self) -> float:
        """Read/write float in ``[-1.0, 1.0]``: ``0.0`` = no change (default).

        Maps to the ``bright`` attribute of ``<a:lum>``.  A value of ``0.4``
        means +40% brightness; ``-0.25`` means 25% darker.
        """
        lum = self._blip.lum
        return 0.0 if lum is None else lum.bright

    @brightness.setter
    def brightness(self, value: float) -> None:
        if not -1.0 <= value <= 1.0:
            raise ValueError(f"brightness must be between -1.0 and 1.0, got {value!r}")
        lum = self._blip.get_or_add_lum()
        lum.bright = value  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # contrast
    # ------------------------------------------------------------------

    @property
    def contrast(self) -> float:
        """Read/write float in ``[-1.0, 1.0]``: ``0.0`` = no change (default).

        Maps to the ``contrast`` attribute of ``<a:lum>``.  Shares the same
        ``<a:lum>`` element as :attr:`brightness`.
        """
        lum = self._blip.lum
        return 0.0 if lum is None else lum.contrast

    @contrast.setter
    def contrast(self, value: float) -> None:
        if not -1.0 <= value <= 1.0:
            raise ValueError(f"contrast must be between -1.0 and 1.0, got {value!r}")
        lum = self._blip.get_or_add_lum()
        lum.contrast = value  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # recolor
    # ------------------------------------------------------------------

    @property
    def recolor(self) -> str | None:
        """Read/write recolor mode.  One of ``"grayscale"``, ``"washout"``,
        ``"sepia"``, ``"duotone"``, or ``None`` (no recolor).

        Assigning a value removes any previously applied recolor before
        applying the new one.  Setting to ``None`` clears recolor entirely.
        For custom duotone colors use :meth:`set_duotone`.
        """
        if self._blip.grayscl is not None:
            return "grayscale"
        biLevel = self._blip.biLevel
        if biLevel is not None:
            return "washout"
        duotone = self._blip.duotone
        if duotone is not None:
            children = list(duotone)
            if len(children) == 2:
                from pptx.oxml.ns import qn

                vals = [c.get("val") for c in children if c.tag == qn("a:srgbClr")]
                if vals == [_SEPIA_DARK, _SEPIA_LIGHT]:
                    return "sepia"
            return "duotone"
        return None

    @recolor.setter
    def recolor(self, value: str | None) -> None:
        self._clear_recolor()
        if value is None:
            return
        if value == "grayscale":
            self._blip.get_or_add_grayscl()
        elif value == "washout":
            self._blip.get_or_add_biLevel().thresh = 0.5  # type: ignore[assignment]
        elif value == "sepia":
            self.set_duotone(_SEPIA_DARK, _SEPIA_LIGHT)
        else:
            raise ValueError(
                f"recolor must be 'grayscale', 'washout', 'sepia', 'duotone', or None; got {value!r}"
            )

    def set_duotone(self, dark_color: RGBColor | tuple, light_color: RGBColor | tuple) -> None:
        """Apply a duotone recolor using custom dark and light colors.

        Each color can be an :class:`~pptx.dml.color.RGBColor` instance or a
        3-tuple of ``(r, g, b)`` integers.  The dark color maps to shadows, the
        light color to highlights.
        """
        self._clear_recolor()
        from lxml import etree

        from pptx.oxml.ns import qn

        duotone = self._blip.get_or_add_duotone()
        for child in list(duotone):
            duotone.remove(child)
        for hex_val in (_color_to_hex(dark_color), _color_to_hex(light_color)):
            clr = etree.SubElement(duotone, qn("a:srgbClr"))
            clr.set("val", hex_val)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _clear_recolor(self) -> None:
        """Remove any existing recolor effects from the blip."""
        self._blip._remove_grayscl()  # pyright: ignore[reportPrivateUsage]
        self._blip._remove_biLevel()  # pyright: ignore[reportPrivateUsage]
        self._blip._remove_duotone()  # pyright: ignore[reportPrivateUsage]


def _color_to_hex(color: RGBColor | tuple | str) -> str:
    """Return uppercase 6-char hex string for *color*.

    Accepts an :class:`~pptx.dml.color.RGBColor`, a hex string (with or
    without ``#``), or a 3-tuple of ``(r, g, b)`` integers.
    """
    from pptx.dml.color import RGBColor as _RGBColor

    if isinstance(color, _RGBColor):
        return str(color).upper()
    if isinstance(color, str):
        return color.upper().lstrip("#")
    r, g, b = color
    return f"{r:02X}{g:02X}{b:02X}"
