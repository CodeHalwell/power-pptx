"""lxml custom element classes for DrawingML 3-D shape elements."""

from __future__ import annotations

from power_pptx.enum.dml import BevelPreset, PresetMaterial
from power_pptx.oxml.simpletypes import ST_PositiveCoordinate, XsdString
from power_pptx.oxml.xmlchemy import (
    BaseOxmlElement,
    Choice,
    OptionalAttribute,
    RequiredAttribute,
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


class CT_Camera(BaseOxmlElement):
    """`<a:camera>` element — the scene camera within `<a:scene3d>`.

    The ``prst`` attribute (preset camera type, e.g. ``orthographicFront``) is ``use="required"``
    in the OOXML schema (``CT_Camera``), so it is modelled as a ``RequiredAttribute`` — a plain
    string so callers / defaults can write any preset name without an exhaustive enum.
    """

    prst = RequiredAttribute("prst", XsdString)


class CT_LightRig(BaseOxmlElement):
    """`<a:lightRig>` element — the scene light rig within `<a:scene3d>`.

    Both ``rig`` (e.g. ``threePt``) and ``dir`` (e.g. ``t``) are ``use="required"`` in the OOXML
    schema (``CT_LightRig``), so they are modelled as ``RequiredAttribute`` for the same reason as
    :class:`CT_Camera`.
    """

    rig = RequiredAttribute("rig", XsdString)
    dir = RequiredAttribute("dir", XsdString)


class CT_Scene3D(BaseOxmlElement):
    """`<a:scene3d>` element — scene-level 3-D rendering settings.

    Contains a required ``<a:camera>`` and ``<a:lightRig>`` child (in that order).  PowerPoint
    rejects a deck whose ``<a:scene3d>`` is empty while a sibling ``<a:sp3d>`` is present, so the
    creating path (:meth:`power_pptx.dml.three_d.ThreeDFormat._get_or_add_sp3d`) always populates
    both children with safe defaults.
    """

    _tag_seq = ("a:camera", "a:lightRig", "a:extLst")
    camera = ZeroOrOne("a:camera", successors=_tag_seq[1:])
    lightRig = ZeroOrOne("a:lightRig", successors=_tag_seq[2:])
    del _tag_seq
