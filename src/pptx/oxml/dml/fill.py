"""lxml custom element classes for DrawingML-related XML elements."""

from __future__ import annotations

from pptx.enum.dml import MSO_PATTERN_TYPE
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls
from pptx.oxml.simpletypes import (
    ST_Percentage,
    ST_PositiveFixedAngle,
    ST_PositiveFixedPercentage,
    ST_RelationshipId,
)
from pptx.oxml.xmlchemy import (
    BaseOxmlElement,
    Choice,
    OneOrMore,
    OptionalAttribute,
    RequiredAttribute,
    ZeroOrOne,
    ZeroOrOneChoice,
)


class CT_Blip(BaseOxmlElement):
    """`<a:blip>` element — image reference plus optional per-image effects."""

    # Child tag order follows the OOXML CT_Blip content model.
    _tag_seq = (
        "a:alphaBiLevel",
        "a:alphaCeiling",
        "a:alphaFloor",
        "a:alphaInv",
        "a:alphaMod",
        "a:alphaModFix",
        "a:alphaRepl",
        "a:biLevel",
        "a:blur",
        "a:clrChange",
        "a:clrRepl",
        "a:duotone",
        "a:fillOverlay",
        "a:grayscl",
        "a:hsl",
        "a:lum",
        "a:tint",
        "a:extLst",
    )
    alphaModFix: CT_AlphaModFixEffect | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "a:alphaModFix", successors=_tag_seq[6:]
    )
    biLevel: CT_BiLevelEffect | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "a:biLevel", successors=_tag_seq[8:]
    )
    duotone: CT_DuotoneEffect | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "a:duotone", successors=_tag_seq[12:]
    )
    grayscl: CT_GrayscaleEffect | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "a:grayscl", successors=_tag_seq[14:]
    )
    lum: CT_LuminanceEffect | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "a:lum", successors=_tag_seq[16:]
    )
    del _tag_seq

    rEmbed = OptionalAttribute("r:embed", ST_RelationshipId)


class CT_BlipFillProperties(BaseOxmlElement):
    """
    Custom element class for <a:blipFill> element.
    """

    _tag_seq = ("a:blip", "a:srcRect", "a:tile", "a:stretch")
    blip = ZeroOrOne("a:blip", successors=_tag_seq[1:])
    srcRect = ZeroOrOne("a:srcRect", successors=_tag_seq[2:])
    del _tag_seq

    def crop(self, cropping):
        """
        Set `a:srcRect` child to crop according to *cropping* values.
        """
        srcRect = self._add_srcRect()
        srcRect.l, srcRect.t, srcRect.r, srcRect.b = cropping


class CT_GradientFillProperties(BaseOxmlElement):
    """`a:gradFill` custom element class."""

    _tag_seq = ("a:gsLst", "a:lin", "a:path", "a:tileRect")
    gsLst = ZeroOrOne("a:gsLst", successors=_tag_seq[1:])
    lin = ZeroOrOne("a:lin", successors=_tag_seq[2:])
    path = ZeroOrOne("a:path", successors=_tag_seq[3:])
    del _tag_seq

    @classmethod
    def new_gradFill(cls):
        """Return newly-created "loose" default gradient subtree."""
        return parse_xml(
            '<a:gradFill %s rotWithShape="1">\n'
            "  <a:gsLst>\n"
            '    <a:gs pos="0">\n'
            '      <a:schemeClr val="accent1">\n'
            '        <a:tint val="100000"/>\n'
            '        <a:shade val="100000"/>\n'
            '        <a:satMod val="130000"/>\n'
            "      </a:schemeClr>\n"
            "    </a:gs>\n"
            '    <a:gs pos="100000">\n'
            '      <a:schemeClr val="accent1">\n'
            '        <a:tint val="50000"/>\n'
            '        <a:shade val="100000"/>\n'
            '        <a:satMod val="350000"/>\n'
            "      </a:schemeClr>\n"
            "    </a:gs>\n"
            "  </a:gsLst>\n"
            '  <a:lin scaled="0"/>\n'
            "</a:gradFill>\n" % nsdecls("a")
        )

    def _new_gsLst(self):
        """Override default to add minimum subtree."""
        return CT_GradientStopList.new_gsLst()


class CT_GradientStop(BaseOxmlElement):
    """`a:gs` custom element class."""

    eg_colorChoice = ZeroOrOneChoice(
        (
            Choice("a:scrgbClr"),
            Choice("a:srgbClr"),
            Choice("a:hslClr"),
            Choice("a:sysClr"),
            Choice("a:schemeClr"),
            Choice("a:prstClr"),
        ),
        successors=(),
    )
    pos = RequiredAttribute("pos", ST_PositiveFixedPercentage)


class CT_GradientStopList(BaseOxmlElement):
    """`a:gsLst` custom element class."""

    gs = OneOrMore("a:gs")

    @classmethod
    def new_gsLst(cls):
        """Return newly-created "loose" default stop-list subtree.

        An `a:gsLst` element must have at least two `a:gs` children. These
        are the default from the PowerPoint built-in "White" template.
        """
        return parse_xml(
            "<a:gsLst %s>\n"
            '  <a:gs pos="0">\n'
            '    <a:schemeClr val="accent1">\n'
            '      <a:tint val="100000"/>\n'
            '      <a:shade val="100000"/>\n'
            '      <a:satMod val="130000"/>\n'
            "    </a:schemeClr>\n"
            "  </a:gs>\n"
            '  <a:gs pos="100000">\n'
            '    <a:schemeClr val="accent1">\n'
            '      <a:tint val="50000"/>\n'
            '      <a:shade val="100000"/>\n'
            '      <a:satMod val="350000"/>\n'
            "    </a:schemeClr>\n"
            "  </a:gs>\n"
            "</a:gsLst>\n" % nsdecls("a")
        )


class CT_GroupFillProperties(BaseOxmlElement):
    """`a:grpFill` custom element class"""


class CT_LinearShadeProperties(BaseOxmlElement):
    """`a:lin` custom element class"""

    ang = OptionalAttribute("ang", ST_PositiveFixedAngle)


class CT_NoFillProperties(BaseOxmlElement):
    """`a:noFill` custom element class"""


class CT_PatternFillProperties(BaseOxmlElement):
    """`a:pattFill` custom element class"""

    _tag_seq = ("a:fgClr", "a:bgClr")
    fgClr = ZeroOrOne("a:fgClr", successors=_tag_seq[1:])
    bgClr = ZeroOrOne("a:bgClr", successors=_tag_seq[2:])
    del _tag_seq
    prst = OptionalAttribute("prst", MSO_PATTERN_TYPE)

    def _new_bgClr(self):
        """Override default to add minimum subtree."""
        xml = ("<a:bgClr %s>\n" ' <a:srgbClr val="FFFFFF"/>\n' "</a:bgClr>\n") % nsdecls("a")
        bgClr = parse_xml(xml)
        return bgClr

    def _new_fgClr(self):
        """Override default to add minimum subtree."""
        xml = ("<a:fgClr %s>\n" ' <a:srgbClr val="000000"/>\n' "</a:fgClr>\n") % nsdecls("a")
        fgClr = parse_xml(xml)
        return fgClr


class CT_RelativeRect(BaseOxmlElement):
    """`a:srcRect` element and perhaps others."""

    l = OptionalAttribute("l", ST_Percentage, default=0.0)  # noqa
    t = OptionalAttribute("t", ST_Percentage, default=0.0)
    r = OptionalAttribute("r", ST_Percentage, default=0.0)
    b = OptionalAttribute("b", ST_Percentage, default=0.0)


class CT_AlphaModFixEffect(BaseOxmlElement):
    """`<a:alphaModFix>` element — scales the alpha (opacity) of an image.

    `amt` is a `ST_PositiveFixedPercentage` where ``1.0`` (100%) means fully
    opaque and ``0.0`` means fully transparent.  When absent, the element is
    treated as 100% opaque by PowerPoint.
    """

    amt = OptionalAttribute("amt", ST_PositiveFixedPercentage, default=1.0)


class CT_BiLevelEffect(BaseOxmlElement):
    """`<a:biLevel>` element — converts the image to a two-color (black/white) palette.

    `thresh` is the luminance threshold: pixels darker than this become black,
    brighter ones become white.  ``0.5`` (50%) approximates PowerPoint's "Washout" preset.
    """

    thresh = OptionalAttribute("thresh", ST_PositiveFixedPercentage, default=0.5)


_DUOTONE_COLOR_CHOICES = (
    Choice("a:scrgbClr"),
    Choice("a:srgbClr"),
    Choice("a:hslClr"),
    Choice("a:sysClr"),
    Choice("a:schemeClr"),
    Choice("a:prstClr"),
)


class CT_DuotoneEffect(BaseOxmlElement):
    """`<a:duotone>` element — maps the image to two-color tone.

    Contains exactly two color-choice child elements (dark tone and light tone).
    """


class CT_GrayscaleEffect(BaseOxmlElement):
    """`<a:grayscl>` element — converts the image to grayscale.  No attributes."""


class CT_LuminanceEffect(BaseOxmlElement):
    """`<a:lum>` element — adjusts the brightness and contrast of an image.

    Both `bright` and `contrast` are `ST_Percentage` floats in the range
    ``[-1.0, 1.0]`` where ``0.0`` means no change.
    """

    bright = OptionalAttribute("bright", ST_Percentage, default=0.0)
    contrast = OptionalAttribute("contrast", ST_Percentage, default=0.0)


class CT_SolidColorFillProperties(BaseOxmlElement):
    """`a:solidFill` custom element class."""

    eg_colorChoice = ZeroOrOneChoice(
        (
            Choice("a:scrgbClr"),
            Choice("a:srgbClr"),
            Choice("a:hslClr"),
            Choice("a:sysClr"),
            Choice("a:schemeClr"),
            Choice("a:prstClr"),
        ),
        successors=(),
    )
