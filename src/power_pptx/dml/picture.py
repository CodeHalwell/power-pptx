"""Picture image effects: transparency, brightness, contrast, and recolor."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from power_pptx.dml.color import RGBColor
    from power_pptx.oxml.dml.fill import CT_Blip


# Sepia duotone: dark warm brown → light cream, matching PowerPoint's built-in preset.
_SEPIA_DARK = "532400"
_SEPIA_LIGHT = "FFEFCA"

# PowerPoint's "Washout" (Picture Format > Color > Recolor) is not a recolour
# element at all: it is a fixed brightness/contrast pair on `<a:lum>`.
_WASHOUT_BRIGHT = 0.7
_WASHOUT_CONTRAST = -0.7

# "Black and White: 50%" is `<a:biLevel>`: every pixel becomes pure black or
# pure white according to which side of the threshold its luminance falls on.
_BLACK_AND_WHITE_THRESHOLD = 0.5

_RECOLOR_MODES = ("grayscale", "washout", "sepia", "duotone", "black_and_white")


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
        ``<a:lum>`` element as :attr:`brightness`.
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
        """Read/write recolor mode.  One of ``"grayscale"``, ``"washout"``,
        ``"sepia"``, ``"duotone"``, ``"black_and_white"``, or ``None`` (no
        recolor).

        Assigning a value removes any previously applied recolor before
        applying the new one.  Setting to ``None`` clears recolor entirely.
        For custom duotone colors use :meth:`set_duotone`.

        ``"washout"`` is PowerPoint's Washout: the picture faded towards
        white, written as ``<a:lum bright="70000" contrast="-70000"/>``.
        That is the same element :attr:`brightness` and :attr:`contrast`
        use, so washout *is* that pair of values: it reads back through
        both properties, replaces whatever they held, and assigning either
        of them afterwards takes the picture out of washout.

        ``"black_and_white"`` reduces the picture to pure black and pure
        white at a 50% threshold (``<a:biLevel thresh="50000"/>``).
        """
        if self._blip.grayscl is not None:
            return "grayscale"
        if self._blip.biLevel is not None:
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
        if self._is_washed_out:
            return "washout"
        return None

    @recolor.setter
    def recolor(self, value: str | None) -> None:
        # Validate before mutating so an invalid value leaves the existing effect intact.
        if value is not None and value not in _RECOLOR_MODES:
            raise ValueError(
                "recolor must be one of %s, or None; got %r"
                % (", ".join(repr(mode) for mode in _RECOLOR_MODES), value)
            )
        self._clear_recolor()
        if value is None:
            return
        if value == "grayscale":
            self._blip.get_or_add_grayscl()
        elif value == "washout":
            lum = self._blip.get_or_add_lum()
            lum.bright = _WASHOUT_BRIGHT  # type: ignore[assignment]
            lum.contrast = _WASHOUT_CONTRAST  # type: ignore[assignment]
        elif value == "black_and_white":
            biLevel = self._blip.get_or_add_biLevel()
            biLevel.thresh = _BLACK_AND_WHITE_THRESHOLD  # type: ignore[assignment]
        elif value == "sepia":
            self.set_duotone(_SEPIA_DARK, _SEPIA_LIGHT)
        elif value == "duotone":
            # Default neutral duotone (dark grey → light grey).
            # For custom colors use set_duotone() instead.
            self.set_duotone("333333", "EBEBEB")

    def set_duotone(
        self,
        dark_color: RGBColor | str | tuple[int, int, int],
        light_color: RGBColor | str | tuple[int, int, int],
    ) -> None:
        """Apply a duotone recolor using custom dark and light colors.

        Each color can be an :class:`~power_pptx.dml.color.RGBColor` instance, a
        6-digit hex string (with or without a leading ``#``) or a 3-tuple of
        ``(r, g, b)`` integers.  The dark color maps to shadows, the light color
        to highlights.

        Both colors are checked before anything is changed: a color that is not
        one of those (``"#FFF"``, ``"red"``, ``(300, 0, 0)``, ``None``) raises
        |ValueError| or |TypeError| and leaves the picture's current recolor in
        place.
        """
        from lxml import etree

        from power_pptx._color import coerce_color
        from power_pptx.oxml.ns import qn

        # -- both, before the first mutation: `<a:duotone>` needs exactly two
        # -- colours, so failing on the second must not leave it with none
        dark, light = coerce_color(dark_color), coerce_color(light_color)

        self._clear_recolor()
        duotone = self._blip.get_or_add_duotone()
        for child in list(duotone):
            duotone.remove(child)
        for rgb in (dark, light):
            clr = etree.SubElement(duotone, qn("a:srgbClr"))
            clr.set("val", str(rgb))

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    @property
    def _is_washed_out(self) -> bool:
        """True when `<a:lum>` holds exactly the washout brightness and contrast."""
        lum = self._blip.lum
        return (
            lum is not None
            and abs(lum.bright - _WASHOUT_BRIGHT) < 1e-9
            and abs(lum.contrast - _WASHOUT_CONTRAST) < 1e-9
        )

    def _clear_recolor(self) -> None:
        """Remove any existing recolor effects from the blip."""
        self._blip._remove_grayscl()  # pyright: ignore[reportPrivateUsage]
        self._blip._remove_biLevel()  # pyright: ignore[reportPrivateUsage]
        self._blip._remove_duotone()  # pyright: ignore[reportPrivateUsage]
        # -- washout lives in `<a:lum>`; a brightness/contrast adjustment that
        # -- is not washout is the caller's own and is left alone
        if self._is_washed_out:
            self._blip._remove_lum()  # pyright: ignore[reportPrivateUsage]
