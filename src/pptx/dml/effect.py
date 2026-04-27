"""Visual effects on a shape such as shadow, glow, and soft-edges."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from pptx.dml.color import ColorFormat
from pptx.enum.dml import MSO_THEME_COLOR

if TYPE_CHECKING:
    from pptx.dml.color import RGBColor
    from pptx.enum.dml import MSO_COLOR_TYPE
    from pptx.oxml.dml.effect import (
        CT_EffectList,
        CT_GlowEffect,
        CT_OuterShadowEffect,
        CT_SoftEdgesEffect,
    )
    from pptx.oxml.shapes.shared import CT_ShapeProperties
    from pptx.util import Length


class _LazyEffectColorFormat:
    """Non-mutating ColorFormat proxy for visual-effect elements (shadow, glow).

    Reads (`type`, `rgb`, `theme_color`, `brightness`, `alpha`) peek at the
    existing effect element without touching the XML.  When the element doesn't
    exist yet, reads return the appropriate "no color" sentinel values.

    Writes (`rgb=`, `theme_color=`) lazily create the effectLst + effect element
    hierarchy on first assignment, then delegate to a real `ColorFormat`.

    `peek()` must return the existing effect element or None without any side
    effects; `ensure()` must return the element (creating it if absent).
    """

    def __init__(
        self,
        peek: Callable[[], CT_OuterShadowEffect | CT_GlowEffect | None],
        ensure: Callable[[], CT_OuterShadowEffect | CT_GlowEffect],
    ):
        self._peek = peek
        self._ensure = ensure

    @property
    def type(self) -> MSO_COLOR_TYPE | None:
        cf = self._existing_cf()
        return cf.type if cf is not None else None

    @property
    def rgb(self) -> RGBColor | None:
        cf = self._existing_cf()
        return cf.rgb if cf is not None else None

    @rgb.setter
    def rgb(self, value: RGBColor):
        self._ensure_cf().rgb = value

    @property
    def theme_color(self) -> MSO_THEME_COLOR:
        cf = self._existing_cf()
        return cf.theme_color if cf is not None else MSO_THEME_COLOR.NOT_THEME_COLOR

    @theme_color.setter
    def theme_color(self, value: MSO_THEME_COLOR):
        self._ensure_cf().theme_color = value

    @property
    def brightness(self) -> float:
        cf = self._existing_cf()
        return cf.brightness if cf is not None else 0.0

    @brightness.setter
    def brightness(self, value: float):
        cf = self._existing_cf()
        if cf is None:
            raise ValueError(
                "can't set brightness when color.type is None."
                " Set color.rgb or .theme_color first."
            )
        cf.brightness = value

    @property
    def alpha(self) -> float:
        cf = self._existing_cf()
        return cf.alpha if cf is not None else 1.0

    @alpha.setter
    def alpha(self, value: float | None):
        cf = self._existing_cf()
        if cf is None:
            raise ValueError(
                "can't set alpha when color.type is None."
                " Set color.rgb or .theme_color first."
            )
        cf.alpha = value

    def _existing_cf(self) -> ColorFormat | None:
        """ColorFormat for the effect element if it exists, else None."""
        el = self._peek()
        return None if el is None else ColorFormat.from_colorchoice_parent(el)

    def _ensure_cf(self) -> ColorFormat:
        """ColorFormat for the effect element, creating the element if needed."""
        return ColorFormat.from_colorchoice_parent(self._ensure())


class ShadowFormat(object):
    """Provides access to outer-shadow effect on a shape.

    All property reads are non-mutating: if no explicit shadow is set, None is
    returned rather than writing a default into the XML.  Assigning to a
    property creates the `<a:effectLst>`/`<a:outerShdw>` hierarchy on demand.

    The legacy `inherit` read/write property is retained for backward
    compatibility but is deprecated; prefer reading individual properties for
    None.
    """

    def __init__(self, spPr: CT_ShapeProperties):
        self._element = spPr

    # ------------------------------------------------------------------
    # Legacy back-compat property
    # ------------------------------------------------------------------

    @property
    def inherit(self) -> bool:
        """True if shape inherits shadow settings (no explicit effectLst).

        Assigning True removes any explicit `<a:effectLst>` (restoring
        inheritance for *all* effects).  Assigning False ensures the element
        is present but leaves it empty (no visible effect).
        """
        return self._element.effectLst is None

    @inherit.setter
    def inherit(self, value: bool):
        if bool(value):
            self._element._remove_effectLst()  # pyright: ignore[reportPrivateUsage]
        else:
            self._element.get_or_add_effectLst()

    # ------------------------------------------------------------------
    # New Phase-3 properties — all non-mutating on read
    # ------------------------------------------------------------------

    @property
    def blur_radius(self) -> Length | None:
        """Blur radius of the shadow in EMU, or None if not explicitly set."""
        outerShdw = self._outerShdw
        return None if outerShdw is None else outerShdw.blurRad

    @blur_radius.setter
    def blur_radius(self, value: Length | None):
        if value is None:
            if self._outerShdw is not None:
                self._outerShdw.blurRad = None  # type: ignore[assignment]
        else:
            self._get_or_add_outerShdw().blurRad = value  # type: ignore[assignment]

    @property
    def distance(self) -> Length | None:
        """Shadow offset distance in EMU, or None if not explicitly set."""
        outerShdw = self._outerShdw
        return None if outerShdw is None else outerShdw.dist

    @distance.setter
    def distance(self, value: Length | None):
        if value is None:
            if self._outerShdw is not None:
                self._outerShdw.dist = None  # type: ignore[assignment]
        else:
            self._get_or_add_outerShdw().dist = value  # type: ignore[assignment]

    @property
    def direction(self) -> float | None:
        """Shadow direction in degrees (0–360), or None if not explicitly set."""
        outerShdw = self._outerShdw
        return None if outerShdw is None else outerShdw.dir

    @direction.setter
    def direction(self, value: float | None):
        if value is None:
            if self._outerShdw is not None:
                self._outerShdw.dir = None  # type: ignore[assignment]
        else:
            self._get_or_add_outerShdw().dir = value  # type: ignore[assignment]

    @property
    def color(self) -> _LazyEffectColorFormat:
        """Non-mutating color accessor for the shadow color.

        Reading any sub-property (``type``, ``rgb``, ``theme_color``) on a
        shape with no explicit shadow returns the appropriate "no color"
        sentinel without touching the XML.  Writing to ``color.rgb`` or
        ``color.theme_color`` lazily creates the ``<a:outerShdw>`` hierarchy.
        """
        return _LazyEffectColorFormat(lambda: self._outerShdw, self._get_or_add_outerShdw)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @property
    def _outerShdw(self) -> CT_OuterShadowEffect | None:
        effectLst: CT_EffectList | None = self._element.effectLst
        if effectLst is None:
            return None
        return effectLst.outerShdw

    def _get_or_add_outerShdw(self) -> CT_OuterShadowEffect:
        effectLst: CT_EffectList = self._element.get_or_add_effectLst()
        outerShdw = effectLst.outerShdw
        if outerShdw is None:
            outerShdw = effectLst.get_or_add_outerShdw()
        return outerShdw


class GlowFormat(object):
    """Provides access to the glow effect on a shape.

    All property reads are non-mutating; assigning a non-None value lazily
    creates the `<a:effectLst>`/`<a:glow>` hierarchy.
    """

    def __init__(self, spPr: CT_ShapeProperties):
        self._element = spPr

    @property
    def radius(self) -> Length | None:
        """Glow radius in EMU, or None when no explicit glow is set."""
        glow = self._glow
        return None if glow is None else glow.rad

    @radius.setter
    def radius(self, value: Length | None):
        if value is None:
            # Only remove the attribute — preserves any explicitly set color.
            if self._glow is not None:
                self._glow.rad = None  # type: ignore[assignment]
        else:
            self._get_or_add_glow().rad = value  # type: ignore[assignment]

    @property
    def color(self) -> _LazyEffectColorFormat:
        """Non-mutating color accessor for the glow color.

        Reading any sub-property on a shape with no explicit glow returns the
        appropriate "no color" sentinel without touching the XML.  Writing to
        ``color.rgb`` or ``color.theme_color`` lazily creates the
        ``<a:glow>`` hierarchy.
        """
        return _LazyEffectColorFormat(lambda: self._glow, self._get_or_add_glow)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @property
    def _glow(self) -> CT_GlowEffect | None:
        effectLst: CT_EffectList | None = self._element.effectLst
        if effectLst is None:
            return None
        return effectLst.glow

    def _get_or_add_glow(self) -> CT_GlowEffect:
        effectLst: CT_EffectList = self._element.get_or_add_effectLst()
        glow = effectLst.glow
        if glow is None:
            glow = effectLst.get_or_add_glow()
        return glow


class SoftEdgeFormat(object):
    """Provides access to the soft-edge effect on a shape.

    All property reads are non-mutating.  Assigning a non-None radius lazily
    creates the `<a:effectLst>`/`<a:softEdge>` hierarchy.
    """

    def __init__(self, spPr: CT_ShapeProperties):
        self._element = spPr

    @property
    def radius(self) -> Length | None:
        """Soft-edge blur radius in EMU, or None when no explicit soft-edge is set."""
        softEdge = self._softEdge
        return None if softEdge is None else softEdge.rad

    @radius.setter
    def radius(self, value: Length | None):
        if value is None:
            if self._softEdge is not None:
                effectLst: CT_EffectList | None = self._element.effectLst
                if effectLst is not None:
                    effectLst._remove_softEdge()  # pyright: ignore[reportPrivateUsage]
        else:
            self._get_or_add_softEdge().rad = value  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @property
    def _softEdge(self) -> CT_SoftEdgesEffect | None:
        effectLst: CT_EffectList | None = self._element.effectLst
        if effectLst is None:
            return None
        return effectLst.softEdge

    def _get_or_add_softEdge(self) -> CT_SoftEdgesEffect:
        effectLst: CT_EffectList = self._element.get_or_add_effectLst()
        softEdge = effectLst.softEdge
        if softEdge is None:
            softEdge = effectLst.get_or_add_softEdge()
        return softEdge
