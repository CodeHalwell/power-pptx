"""Visual effects on a shape such as shadow, glow, and soft-edges."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pptx.dml.color import ColorFormat
from pptx.oxml.xmlchemy import OxmlElement

if TYPE_CHECKING:
    from pptx.oxml.dml.effect import CT_EffectList, CT_GlowEffect, CT_OuterShadowEffect
    from pptx.oxml.shapes.shared import CT_ShapeProperties
    from pptx.util import Length


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
    def color(self) -> ColorFormat:
        """ColorFormat for shadow color.

        Returns a ColorFormat whose type is None when no explicit shadow color
        is set.  Assigning to `color.rgb` or `color.theme_color` lazily
        creates the shadow element hierarchy.
        """
        outerShdw = self._outerShdw
        if outerShdw is None:
            outerShdw = self._get_or_add_outerShdw()
        return ColorFormat.from_colorchoice_parent(outerShdw)

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
            if self._glow is not None:
                effectLst: CT_EffectList | None = self._element.effectLst
                if effectLst is not None:
                    effectLst._remove_glow()  # pyright: ignore[reportPrivateUsage]
        else:
            self._get_or_add_glow().rad = value  # type: ignore[assignment]

    @property
    def color(self) -> ColorFormat:
        """ColorFormat for the glow color.

        Returns a ColorFormat whose type is None when no explicit glow color
        is set.  Assigning to color.rgb lazily creates the glow hierarchy.
        """
        glow = self._glow
        if glow is None:
            glow = self._get_or_add_glow()
        return ColorFormat.from_colorchoice_parent(glow)

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
    def _softEdge(self):
        effectLst: CT_EffectList | None = self._element.effectLst
        if effectLst is None:
            return None
        return effectLst.softEdge

    def _get_or_add_softEdge(self):
        effectLst: CT_EffectList = self._element.get_or_add_effectLst()
        softEdge = effectLst.softEdge
        if softEdge is None:
            softEdge = effectLst.get_or_add_softEdge()
        return softEdge
