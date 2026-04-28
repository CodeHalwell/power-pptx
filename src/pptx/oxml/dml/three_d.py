"""lxml custom element classes for DrawingML 3-D shape elements."""

from __future__ import annotations

from pptx.enum.dml import BevelPreset, PresetMaterial
from pptx.oxml.simpletypes import ST_PositiveCoordinate
from pptx.oxml.xmlchemy import (
    BaseOxmlElement,
    Choice,
    OptionalAttribute,
    ZeroOrOne,
    ZeroOrOneChoice,
)

_COLOR_CHOICES = (
    Choice("a:scrgbClr"),
    Choice("a:srgbClr"),
    Choice("a:hslClr"),
    Choice("a:sysClr"),
    Choice("a:schemeClr"),
    Choice("a:prstClr"),
)


class CT_Bevel(BaseOxmlElement):
    """`<a:bevelT>` / `<a:bevelB>` element — describes a top or bottom bevel on a 3-D shape.

    The ``prst`` attribute selects from a set of preset bevel profiles.  ``w`` and ``h`` control
    the bevel width and height in EMU.
    """

    w = OptionalAttribute("w", ST_PositiveCoordinate)
    h = OptionalAttribute("h", ST_PositiveCoordinate)
    prst = OptionalAttribute("prst", BevelPreset)


class CT_Shape3D(BaseOxmlElement):
    """`<a:sp3d>` element — describes 3-D properties for a single shape.

    Contains optional top and bottom bevel elements, extrusion and contour colour children,
    and several sizing / material attributes.
    """

    _tag_seq = (
        "a:bevelT",
        "a:bevelB",
        "a:extrusionClr",
        "a:contourClr",
        "a:extLst",
    )
    bevelT = ZeroOrOne("a:bevelT", successors=_tag_seq[1:])
    bevelB = ZeroOrOne("a:bevelB", successors=_tag_seq[2:])
    extrusionClr = ZeroOrOne("a:extrusionClr", successors=_tag_seq[3:])
    contourClr = ZeroOrOne("a:contourClr", successors=_tag_seq[4:])
    del _tag_seq

    extrusionH = OptionalAttribute("extrusionH", ST_PositiveCoordinate)
    contourW = OptionalAttribute("contourW", ST_PositiveCoordinate)
    prstMaterial = OptionalAttribute("prstMaterial", PresetMaterial)


class CT_ExtrusionColor(BaseOxmlElement):
    """`<a:extrusionClr>` element — colour of the 3-D extrusion."""

    eg_colorChoice = ZeroOrOneChoice(_COLOR_CHOICES, successors=())


class CT_ContourColor(BaseOxmlElement):
    """`<a:contourClr>` element — colour of the 3-D contour (edge)."""

    eg_colorChoice = ZeroOrOneChoice(_COLOR_CHOICES, successors=())


class CT_Scene3D(BaseOxmlElement):
    """`<a:scene3d>` element — scene-level 3-D rendering settings.

    Contains camera and light-rig children.  For typical bevel/extrusion use the element only
    needs to exist; individual sub-element access is not yet implemented.
    """
