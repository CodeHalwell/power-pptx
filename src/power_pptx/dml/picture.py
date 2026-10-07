"""Picture image effects: transparency, brightness, contrast, and recolor."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from power_pptx.dml.color import RGBColor
    from power_pptx.oxml.dml.fill import CT_Blip


# Sepia duotone: dark warm brown → light cream, matching PowerPoint's built-in preset.
_SEPIA_DARK = "532400"
_SEPIA_LIGHT = "FFEFCA"

# PowerPoint's Recolor > Washout preset is brightness +70% with contrast -70%, i.e. an
# `<a:lum bright="70000" contrast="-70000"/>` -- the very element that backs `brightness` and
# `contrast`. (A two-colour `<a:biLevel>` is the "Black and White" preset, not Washout.)
_WASHOUT_BRIGHTNESS = 0.7
_WASHOUT_CONTRAST = -0.7


class PictureEffects:
    """Provides access to image-level visual effects on a |Picture| shape.

    Exposes transparency (alpha), brightness, contrast, and recolor.  All reads
    are non-mutating — if no explicit effect is present the property returns a
    neutral sentinel value (``0.0`` for numeric adjustments, ``None`` for recolor).
    Writes lazily create the required ``<a:blip>`` child elements.

    Access via :attr:`power_pptx.shapes.picture.Picture.effects`.
    """

    def __init__(self, blip: CT_Blip):
        self._blip = blip

    # ------------------------------------------------------------------
    # transparency
    # ------------------------------------------------------------------

    @property
    def transparency(self) -> float:
        """Read/write float in ``[0.0, 1.0]``; ``0.0`` is fully opaque (default), ``1.0`` invisible.

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
        if value == 0.0 and self._blip.lum is None:
            return  # -- "no change" on a picture with no `a:lum`: nothing to write
        lum = self._blip.get_or_add_lum()
        lum.bright = value  # type: ignore[assignment]
        self._drop_lum_if_neutral()

    # ------------------------------------------------------------------
    # contrast
    # ------------------------------------------------------------------

    @property
    def contrast(self) -> float:
        """Read/write float in ``[-1.0, 1.0]``: ``0.0`` = no change (default).

        Maps to the ``contrast`` attribute of ``<a:lum>``.  Shares the same
        ``<a:lum>`` element as :attr:`brightness` -- and as the ``"washout"``
        :attr:`recolor`, which is brightness ``0.7`` with contrast ``-0.7``.
        """
        lum = self._blip.lum
        return 0.0 if lum is None else lum.contrast

    @contrast.setter
    def contrast(self, value: float) -> None:
        if not -1.0 <= value <= 1.0:
            raise ValueError(f"contrast must be between -1.0 and 1.0, got {value!r}")
        if value == 0.0 and self._blip.lum is None:
            return  # -- "no change" on a picture with no `a:lum`: nothing to write
        lum = self._blip.get_or_add_lum()
        lum.contrast = value  # type: ignore[assignment]
        self._drop_lum_if_neutral()

    def _drop_lum_if_neutral(self) -> None:
        """Remove `a:lum` once both adjustments are back at their defaults.

        Writing ``0.0`` drops the corresponding attribute (the schema
        default), so a lum whose adjustments are both reset would otherwise
        linger as a dead empty ``<a:lum/>``.
        """
        lum = self._blip.lum
        if lum is not None and lum.get("bright") is None and lum.get("contrast") is None:
            self._blip.remove(lum)

    # ------------------------------------------------------------------
    # recolor
    # ------------------------------------------------------------------

    @property
    def recolor(self) -> str | None:
        """Read/write recolor mode.  One of ``"grayscale"``, ``"sepia"``,
        ``"washout"``, ``"black_and_white"``, ``"duotone"``, or ``None`` (no recolor).

        * ``"grayscale"`` -- ``<a:grayscl/>``.
        * ``"sepia"`` -- a preset ``<a:duotone>`` (dark brown to cream).
        * ``"washout"`` -- PowerPoint's *Recolor > Washout*, a pale faded copy of the
          picture: brightness ``+0.7`` and contrast ``-0.7``, written as
          ``<a:lum bright="70000" contrast="-70000"/>``.
        * ``"black_and_white"`` -- ``<a:biLevel thresh="50000"/>``, PowerPoint's
          *Black and White: 50%*: every pixel becomes pure black or pure white.  Any
          ``<a:biLevel>`` reads back as this, whatever its threshold.  (Releases before
          this one wrote this element for ``"washout"``.)
        * ``"duotone"`` -- a neutral grey duotone; use :meth:`set_duotone` for your own
          two colors.

        Assigning a value removes any previously applied recolor before
        applying the new one.  Setting to ``None`` clears recolor entirely.

        ``"washout"`` is stored in the same ``<a:lum>`` element as :attr:`brightness`
        and :attr:`contrast`, so the three overlap, last write wins:

        * assigning ``"washout"`` replaces any brightness and contrast already set;
        * a picture reads back as ``"washout"`` only while brightness is exactly ``0.7``
          *and* contrast exactly ``-0.7`` -- change either afterwards and what remains
          is an ordinary brightness/contrast adjustment, so ``recolor`` reads ``None``;
        * assigning any other recolor, or ``None``, removes a washout but never touches
          a brightness/contrast pair that is not the washout one.
        """
        if self._blip.grayscl is not None:
            return "grayscale"
        biLevel = self._blip.biLevel
        if biLevel is not None:
            return "black_and_white"
        duotone = self._blip.duotone
        if duotone is not None:
            children = list(duotone)
            if len(children) == 2:
                from power_pptx.oxml.ns import qn

                vals = [c.get("val") for c in children if c.tag == qn("a:srgbClr")]
                if vals == [_SEPIA_DARK, _SEPIA_LIGHT]:
                    return "sepia"
            return "duotone"
        if self._is_washout():
            return "washout"
        return None

    @recolor.setter
    def recolor(self, value: str | None) -> None:
        # Validate before mutating so an invalid value leaves the existing effect intact.
        _VALID_RECOLOR = frozenset({"grayscale", "washout", "black_and_white", "sepia", "duotone"})
        if value is not None and value not in _VALID_RECOLOR:
            raise ValueError(
                "recolor must be 'grayscale', 'washout', 'black_and_white', 'sepia', "
                f"'duotone', or None; got {value!r}"
            )
        self._clear_recolor()
        if value is None:
            return
        if value == "grayscale":
            self._blip.get_or_add_grayscl()
        elif value == "washout":
            # -- shares `a:lum` with brightness/contrast: replaces whatever they held --
            lum = self._blip.get_or_add_lum()
            lum.bright = _WASHOUT_BRIGHTNESS  # type: ignore[assignment]
            lum.contrast = _WASHOUT_CONTRAST  # type: ignore[assignment]
        elif value == "black_and_white":
            self._blip.get_or_add_biLevel().thresh = 0.5  # type: ignore[assignment]
        elif value == "sepia":
            self.set_duotone(_SEPIA_DARK, _SEPIA_LIGHT)
        elif value == "duotone":
            # Default neutral duotone (dark grey → light grey).
            # For custom colors use set_duotone() instead.
            self.set_duotone("333333", "EBEBEB")

    def set_duotone(self, dark_color: RGBColor | tuple, light_color: RGBColor | tuple) -> None:
        """Apply a duotone recolor using custom dark and light colors.

        Each color can be an :class:`~power_pptx.dml.color.RGBColor` instance or a
        3-tuple of ``(r, g, b)`` integers.  The dark color maps to shadows, the
        light color to highlights.
        """
        self._clear_recolor()
        from lxml import etree

        from power_pptx.oxml.ns import qn

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
        # -- a washout lives in `a:lum`, shared with brightness/contrast: only a lum that is
        # -- exactly the washout pair is the recolor; any other adjustment is the user's.
        if self._is_washout():
            self._blip._remove_lum()  # pyright: ignore[reportPrivateUsage]

    def _is_washout(self) -> bool:
        """True when `a:lum` is exactly PowerPoint's Washout pair (+70% / -70%)."""
        lum = self._blip.lum
        return (
            lum is not None
            and round(lum.bright, 4) == _WASHOUT_BRIGHTNESS
            and round(lum.contrast, 4) == _WASHOUT_CONTRAST
        )


def _color_to_hex(color: RGBColor | tuple | str) -> str:
    """Return uppercase 6-char hex string for *color*.

    Accepts an :class:`~power_pptx.dml.color.RGBColor`, a hex string (with or
    without ``#``), or a 3-tuple of ``(r, g, b)`` integers.
    """
    from power_pptx.dml.color import RGBColor as _RGBColor

    if isinstance(color, _RGBColor):
        return str(color).upper()
    if isinstance(color, str):
        return color.upper().lstrip("#")
    r, g, b = color
    return f"{r:02X}{g:02X}{b:02X}"
