"""lxml custom element classes for DrawingML visual-effect elements."""

from __future__ import annotations

from pptx.oxml.ns import qn
from pptx.oxml.simpletypes import (
    ST_Angle,
    ST_Percentage,
    ST_PositiveCoordinate,
    ST_PositiveFixedAngle,
    ST_PositiveFixedPercentage,
    XsdBoolean,
    XsdStringEnumeration,
)
from pptx.oxml.xmlchemy import (
    BaseOxmlElement,
    Choice,
    OptionalAttribute,
    ZeroOrOne,
    ZeroOrOneChoice,
)


class ST_RectAlignment(XsdStringEnumeration):
    """Valid values for `a:reflection@algn`.

    The nine-point alignment used by the reflection effect to anchor its
    bounding box relative to the source shape.
    """

    TL = "tl"
    T = "t"
    TR = "tr"
    L = "l"
    CTR = "ctr"
    R = "r"
    BL = "bl"
    B = "b"
    BR = "br"

    _members = (TL, T, TR, L, CTR, R, BL, B, BR)

_COLOR_TAGS = frozenset(
    qn(t)
    for t in (
        "a:scrgbClr",
        "a:srgbClr",
        "a:hslClr",
        "a:sysClr",
        "a:schemeClr",
        "a:prstClr",
    )
)

_COLOR_CHOICES = (
    Choice("a:scrgbClr"),
    Choice("a:srgbClr"),
    Choice("a:hslClr"),
    Choice("a:sysClr"),
    Choice("a:schemeClr"),
    Choice("a:prstClr"),
)


class CT_EffectList(BaseOxmlElement):
    """`<a:effectLst>` custom element class — container for shape visual effects."""

    _tag_seq = (
        "a:blur",
        "a:fillOvr",
        "a:glow",
        "a:innerShdw",
        "a:outerShdw",
        "a:prstShdw",
        "a:reflection",
        "a:softEdge",
    )
    blur: CT_BlurEffect | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "a:blur", successors=_tag_seq[1:]
    )
    glow: CT_GlowEffect | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "a:glow", successors=_tag_seq[3:]
    )
    innerShdw: CT_InnerShadowEffect | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "a:innerShdw", successors=_tag_seq[4:]
    )
    outerShdw: CT_OuterShadowEffect | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "a:outerShdw", successors=_tag_seq[5:]
    )
    reflection: CT_ReflectionEffect | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "a:reflection", successors=_tag_seq[7:]
    )
    softEdge: CT_SoftEdgesEffect | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "a:softEdge", successors=_tag_seq[8:]
    )
    del _tag_seq


class CT_GlowEffect(BaseOxmlElement):
    """`<a:glow>` custom element class.

    Specifies a glow effect around the shape edges.  `rad` is the glow radius in EMU.
    """

    eg_colorChoice = ZeroOrOneChoice(_COLOR_CHOICES, successors=())
    rad = OptionalAttribute("rad", ST_PositiveCoordinate)


class CT_OuterShadowEffect(BaseOxmlElement):
    """`<a:outerShdw>` custom element class.

    Outer shadow effect. All read attributes return None when the attribute is
    absent; writes are non-mutating only when the value is explicitly None.
    """

    eg_colorChoice = ZeroOrOneChoice(_COLOR_CHOICES, successors=())
    blurRad = OptionalAttribute("blurRad", ST_PositiveCoordinate)
    dist = OptionalAttribute("dist", ST_PositiveCoordinate)
    dir = OptionalAttribute("dir", ST_Angle)
    rotWithShape = OptionalAttribute("rotWithShape", XsdBoolean)


class CT_SoftEdgesEffect(BaseOxmlElement):
    """`<a:softEdge>` custom element class.

    Specifies a soft-edge blur at the shape perimeter.  `rad` is the blur radius in EMU.
    """

    rad = OptionalAttribute("rad", ST_PositiveCoordinate)


class CT_BlurEffect(BaseOxmlElement):
    """`<a:blur>` custom element class.

    Applies a Gaussian blur to the entire shape.  `rad` is the blur radius in
    EMU; `grow` controls whether the bounding box expands to accommodate the
    blur (default True per the OOXML schema).
    """

    rad = OptionalAttribute("rad", ST_PositiveCoordinate)
    grow = OptionalAttribute("grow", XsdBoolean)


class CT_InnerShadowEffect(BaseOxmlElement):
    """`<a:innerShdw>` custom element class.

    Inner shadow effect.  Mirrors the attribute set of the outer-shadow
    element minus the outer-only `rotWithShape` flag.  All read attributes
    return None when the underlying attribute is absent.
    """

    eg_colorChoice = ZeroOrOneChoice(_COLOR_CHOICES, successors=())
    blurRad = OptionalAttribute("blurRad", ST_PositiveCoordinate)
    dist = OptionalAttribute("dist", ST_PositiveCoordinate)
    dir = OptionalAttribute("dir", ST_PositiveFixedAngle)


class CT_ReflectionEffect(BaseOxmlElement):
    """`<a:reflection>` custom element class.

    Reflection effect placed beneath the shape.  Exposes the attributes most
    users actually want — blur radius, offset distance, direction, start/end
    alpha, and alignment.  Attributes are optional; reads return None when
    absent so theme inheritance is preserved.
    """

    blurRad = OptionalAttribute("blurRad", ST_PositiveCoordinate)
    stA = OptionalAttribute("stA", ST_PositiveFixedPercentage)
    stPos = OptionalAttribute("stPos", ST_PositiveFixedPercentage)
    endA = OptionalAttribute("endA", ST_PositiveFixedPercentage)
    endPos = OptionalAttribute("endPos", ST_PositiveFixedPercentage)
    dist = OptionalAttribute("dist", ST_PositiveCoordinate)
    dir = OptionalAttribute("dir", ST_PositiveFixedAngle)
    fadeDir = OptionalAttribute("fadeDir", ST_PositiveFixedAngle)
    sx = OptionalAttribute("sx", ST_Percentage)
    sy = OptionalAttribute("sy", ST_Percentage)
    kx = OptionalAttribute("kx", ST_Angle)
    ky = OptionalAttribute("ky", ST_Angle)
    algn = OptionalAttribute("algn", ST_RectAlignment)
    rotWithShape = OptionalAttribute("rotWithShape", XsdBoolean)
