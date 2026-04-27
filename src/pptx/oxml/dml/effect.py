"""lxml custom element classes for DrawingML visual-effect elements."""

from __future__ import annotations

from pptx.oxml.ns import qn
from pptx.oxml.simpletypes import ST_Angle, ST_PositiveCoordinate, XsdBoolean
from pptx.oxml.xmlchemy import (
    BaseOxmlElement,
    Choice,
    OptionalAttribute,
    ZeroOrOne,
    ZeroOrOneChoice,
)

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
    glow: CT_GlowEffect | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "a:glow", successors=_tag_seq[3:]
    )
    outerShdw: CT_OuterShadowEffect | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "a:outerShdw", successors=_tag_seq[5:]
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
