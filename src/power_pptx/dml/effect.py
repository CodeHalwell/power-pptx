"""Visual effects on a shape such as shadow, glow, and soft-edges."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Callable

from power_pptx.dml.color import ColorFormat
from power_pptx.enum.dml import MSO_THEME_COLOR
from power_pptx.oxml.ns import qn

# `<a:outerShdw>`, `<a:innerShdw>`, and `<a:glow>` each require *exactly one*
# EG_ColorChoice child per the OOXML schema (minOccurs=1).  PowerPoint reports a
# deck as broken when one of these effect elements is written without a colour,
# even though lxml / python-pptx / LibreOffice accept it (the same failure mode
# as an empty `<a:scene3d>`).  Geometry-only setters such as
# ``shadow.blur_radius`` must therefore guarantee a colour child exists.
_EFFECT_COLOR_TAGS = frozenset(
    qn(t)
    for t in ("a:scrgbClr", "a:srgbClr", "a:hslClr", "a:sysClr", "a:schemeClr", "a:prstClr")
)


def _ensure_effect_color(el) -> None:
    """Add a default opaque-black colour child to *el* when it has none.

    Idempotent: a no-op when the effect element already carries a colour, so a
    caller who sets ``.color.rgb`` keeps their colour and a caller who only sets
    geometry still produces schema-valid (PowerPoint-openable) XML.
    """
    if any(child.tag in _EFFECT_COLOR_TAGS for child in el):
        return
    from power_pptx.dml.color import RGBColor

    ColorFormat.from_colorchoice_parent(el).rgb = RGBColor(0x00, 0x00, 0x00)

if TYPE_CHECKING:
    from power_pptx.dml.color import RGBColor
    from power_pptx.enum.dml import MSO_COLOR_TYPE
    from power_pptx.oxml.dml.effect import (
        CT_BlurEffect,
        CT_EffectList,
        CT_GlowEffect,
        CT_OuterShadowEffect,
        CT_ReflectionEffect,
        CT_SoftEdgesEffect,
    )
    from power_pptx.oxml.shapes.shared import CT_ShapeProperties
    from power_pptx.util import Length


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
            # No colour set yet.  Rather than force callers to set ``.rgb``
            # first, default to opaque black — shadows (and glows) are almost
            # always black, so an alpha-only assignment is the common case.
            from power_pptx.dml.color import RGBColor

            cf = self._ensure_cf()
            cf.rgb = RGBColor(0x00, 0x00, 0x00)
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

        .. deprecated:: 1.1
            Read individual properties (``shadow.blur_radius`` etc.) for
            ``None`` instead.  ``inherit`` is scheduled for removal in 2.0.
        """
        warnings.warn(
            "ShadowFormat.inherit is deprecated; read individual properties "
            "(blur_radius, distance, direction, color) for None instead. "
            "Will be removed in power-pptx 2.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._element.effectLst is None

    @inherit.setter
    def inherit(self, value: bool):
        warnings.warn(
            "ShadowFormat.inherit is deprecated; assign individual properties "
            "to None to clear them. Will be removed in power-pptx 2.0.",
            DeprecationWarning,
            stacklevel=2,
        )
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

    @color.setter
    def color(self, value: RGBColor) -> None:
        # Convenience setter so ``shape.shadow.color = RGBColor(...)`` works in
        # addition to ``shape.shadow.color.rgb = RGBColor(...)`` (parity with
        # ThreeDFormat.extrusion_color / contour_color).
        self.color.rgb = value

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
        # <a:outerShdw> requires a colour child; guarantee one so a
        # geometry-only shadow doesn't make PowerPoint flag the deck as broken.
        _ensure_effect_color(outerShdw)
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

    @color.setter
    def color(self, value: RGBColor) -> None:
        # Convenience setter so ``shape.glow.color = RGBColor(...)`` works in
        # addition to ``shape.glow.color.rgb = RGBColor(...)``.
        self.color.rgb = value

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
        # <a:glow> requires a colour child (a glow with no colour is invalid and
        # is rejected by PowerPoint); guarantee one.
        _ensure_effect_color(glow)
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


class BlurFormat(object):
    """Provides access to the Gaussian blur effect on a shape.

    All property reads are non-mutating; assigning a non-None value lazily
    creates the `<a:effectLst>`/`<a:blur>` hierarchy.  Clearing the last
    explicit attribute drops the `<a:blur>` element again so theme
    inheritance is preserved.
    """

    def __init__(self, spPr: CT_ShapeProperties):
        self._element = spPr

    @property
    def radius(self) -> Length | None:
        """Blur radius in EMU, or None when no explicit blur is set."""
        blur = self._blur
        return None if blur is None else blur.rad

    @radius.setter
    def radius(self, value: Length | None):
        if value is None:
            if self._blur is not None:
                self._blur.rad = None  # type: ignore[assignment]
                self._maybe_drop_blur()
        else:
            self._get_or_add_blur().rad = value  # type: ignore[assignment]

    @property
    def grow(self) -> bool | None:
        """True when the bounding box expands to accommodate the blur.

        Returns None when no `<a:blur>` element is present.  PowerPoint
        treats absence of the attribute as `True`, but we surface the raw
        value so a round-trip through python-pptx never silently flips a
        deck-author's choice.
        """
        blur = self._blur
        return None if blur is None else blur.grow

    @grow.setter
    def grow(self, value: bool | None):
        if value is None:
            if self._blur is not None:
                self._blur.grow = None  # type: ignore[assignment]
                self._maybe_drop_blur()
        else:
            self._get_or_add_blur().grow = bool(value)  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @property
    def _blur(self) -> CT_BlurEffect | None:
        effectLst: CT_EffectList | None = self._element.effectLst
        if effectLst is None:
            return None
        return effectLst.blur

    def _get_or_add_blur(self) -> CT_BlurEffect:
        effectLst: CT_EffectList = self._element.get_or_add_effectLst()
        blur = effectLst.blur
        if blur is None:
            blur = effectLst.get_or_add_blur()
        return blur

    def _maybe_drop_blur(self) -> None:
        """Remove `<a:blur>` when no explicit attributes remain.

        Keeps theme inheritance intact when a caller clears every property
        they previously assigned.
        """
        blur = self._blur
        if blur is None:
            return
        if not blur.attrib:
            effectLst = self._element.effectLst
            if effectLst is not None:
                effectLst._remove_blur()  # pyright: ignore[reportPrivateUsage]


class ReflectionFormat(object):
    """Provides access to the reflection effect on a shape.

    Reflection is the "mirror image fading downward" effect commonly seen on
    photo cards.  The full OOXML schema for `<a:reflection>` exposes 14
    attributes; we surface the four that control the look users typically
    care about — blur radius, offset distance, direction, and the start /
    end alpha that drive the fade — and leave the rest accessible via the
    underlying element for power users.

    All reads are non-mutating; the `<a:effectLst>`/`<a:reflection>`
    hierarchy is created lazily on first write, and clearing the last
    explicit attribute drops the element again so theme inheritance is
    preserved.
    """

    def __init__(self, spPr: CT_ShapeProperties):
        self._element = spPr

    @property
    def blur_radius(self) -> Length | None:
        """Blur radius applied to the reflection in EMU, or None."""
        reflection = self._reflection
        return None if reflection is None else reflection.blurRad

    @blur_radius.setter
    def blur_radius(self, value: Length | None):
        if value is None:
            if self._reflection is not None:
                self._reflection.blurRad = None  # type: ignore[assignment]
                self._maybe_drop_reflection()
        else:
            self._get_or_add_reflection().blurRad = value  # type: ignore[assignment]

    @property
    def distance(self) -> Length | None:
        """Distance the reflection is offset from the shape, in EMU, or None."""
        reflection = self._reflection
        return None if reflection is None else reflection.dist

    @distance.setter
    def distance(self, value: Length | None):
        if value is None:
            if self._reflection is not None:
                self._reflection.dist = None  # type: ignore[assignment]
                self._maybe_drop_reflection()
        else:
            self._get_or_add_reflection().dist = value  # type: ignore[assignment]

    @property
    def direction(self) -> float | None:
        """Direction of the reflection offset in degrees (0–360), or None."""
        reflection = self._reflection
        return None if reflection is None else reflection.dir

    @direction.setter
    def direction(self, value: float | None):
        if value is None:
            if self._reflection is not None:
                self._reflection.dir = None  # type: ignore[assignment]
                self._maybe_drop_reflection()
        else:
            self._get_or_add_reflection().dir = value  # type: ignore[assignment]

    @property
    def start_alpha(self) -> float | None:
        """Alpha at the top of the reflection in `[0.0, 1.0]`, or None."""
        reflection = self._reflection
        return None if reflection is None else reflection.stA

    @start_alpha.setter
    def start_alpha(self, value: float | None):
        if value is None:
            if self._reflection is not None:
                self._reflection.stA = None  # type: ignore[assignment]
                self._maybe_drop_reflection()
        else:
            self._get_or_add_reflection().stA = value  # type: ignore[assignment]

    @property
    def end_alpha(self) -> float | None:
        """Alpha at the bottom of the reflection in `[0.0, 1.0]`, or None."""
        reflection = self._reflection
        return None if reflection is None else reflection.endA

    @end_alpha.setter
    def end_alpha(self, value: float | None):
        if value is None:
            if self._reflection is not None:
                self._reflection.endA = None  # type: ignore[assignment]
                self._maybe_drop_reflection()
        else:
            self._get_or_add_reflection().endA = value  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @property
    def _reflection(self) -> CT_ReflectionEffect | None:
        effectLst: CT_EffectList | None = self._element.effectLst
        if effectLst is None:
            return None
        return effectLst.reflection

    def _get_or_add_reflection(self) -> CT_ReflectionEffect:
        effectLst: CT_EffectList = self._element.get_or_add_effectLst()
        reflection = effectLst.reflection
        if reflection is None:
            reflection = effectLst.get_or_add_reflection()
        return reflection

    def _maybe_drop_reflection(self) -> None:
        """Remove `<a:reflection>` when no explicit attributes remain.

        Keeps theme inheritance intact when a caller clears every property
        they previously assigned.
        """
        reflection = self._reflection
        if reflection is None:
            return
        if not reflection.attrib:
            effectLst = self._element.effectLst
            if effectLst is not None:
                effectLst._remove_reflection()  # pyright: ignore[reportPrivateUsage]
