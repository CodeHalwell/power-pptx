"""Series-related oxml objects."""

from __future__ import annotations

from power_pptx.enum.chart import (
    XL_ERROR_BAR_DIRECTION,
    XL_ERROR_BAR_INCLUDE,
    XL_ERROR_BAR_TYPE,
    XL_TRENDLINE_TYPE,
)
from power_pptx.oxml import parse_xml
from power_pptx.oxml.chart.datalabel import CT_DLbls
from power_pptx.oxml.ns import nsdecls
from power_pptx.oxml.simpletypes import XsdUnsignedInt
from power_pptx.oxml.xmlchemy import (
    BaseOxmlElement,
    OneAndOnlyOne,
    OptionalAttribute,
    OxmlElement,
    RequiredAttribute,
    ZeroOrMore,
    ZeroOrOne,
)


class CT_AxDataSource(BaseOxmlElement):
    """
    ``<c:cat>`` custom element class used in category charts to specify
    category labels and hierarchy.
    """

    multiLvlStrRef = ZeroOrOne("c:multiLvlStrRef", successors=())

    @property
    def lvls(self):
        """
        Return a list containing the `c:lvl` descendent elements in document
        order. These will only be present when the required single child
        is a `c:multiLvlStrRef` element. Returns an empty list when no
        `c:lvl` descendent elements are present.
        """
        return self.xpath(".//c:lvl")


class CT_DPt(BaseOxmlElement):
    """
    ``<c:dPt>`` custom element class, containing visual properties for a data
    point.
    """

    _tag_seq = (
        "c:idx",
        "c:invertIfNegative",
        "c:marker",
        "c:bubble3D",
        "c:explosion",
        "c:spPr",
        "c:pictureOptions",
        "c:extLst",
    )
    idx = OneAndOnlyOne("c:idx")
    marker = ZeroOrOne("c:marker", successors=_tag_seq[3:])
    spPr = ZeroOrOne("c:spPr", successors=_tag_seq[6:])
    del _tag_seq

    @classmethod
    def new_dPt(cls):
        """
        Return a newly created "loose" `c:dPt` element containing its default
        subtree.
        """
        dPt = OxmlElement("c:dPt")
        dPt.append(OxmlElement("c:idx"))
        return dPt


class CT_Lvl(BaseOxmlElement):
    """
    ``<c:lvl>`` custom element class used in multi-level categories to
    specify a level of hierarchy.
    """

    pt = ZeroOrMore("c:pt", successors=())


class CT_NumDataSource(BaseOxmlElement):
    """
    ``<c:yVal>`` custom element class used in XY and bubble charts, and
    perhaps others.
    """

    numRef = OneAndOnlyOne("c:numRef")

    @property
    def ptCount_val(self):
        """
        Return the value of `./c:numRef/c:numCache/c:ptCount/@val`,
        specifying how many `c:pt` elements are in this numeric data cache.
        Returns 0 if no `c:ptCount` element is present, as this is the least
        disruptive way to degrade when no cached point data is available.
        This situation is not expected, but is valid according to the schema.
        """
        results = self.xpath(".//c:ptCount/@val")
        return int(results[0]) if results else 0

    def pt_v(self, idx):
        """
        Return the Y value for data point *idx* in this cache, or None if no
        value is present for that data point.
        """
        results = self.xpath(".//c:pt[@idx=%d]" % idx)
        return results[0].value if results else None


class CT_SeriesComposite(BaseOxmlElement):
    """
    ``<c:ser>`` custom element class. Note there are several different series
    element types in the schema, such as ``CT_LineSer`` and ``CT_BarSer``,
    but they all share the same tag name. This class acts as a composite and
    depends on the caller not to do anything invalid for a series belonging
    to a particular plot type.
    """

    _tag_seq = (
        "c:idx",
        "c:order",
        "c:tx",
        "c:spPr",
        "c:invertIfNegative",
        "c:pictureOptions",
        "c:marker",
        "c:explosion",
        "c:dPt",
        "c:dLbls",
        "c:trendline",
        "c:errBars",
        "c:cat",
        "c:val",
        "c:xVal",
        "c:yVal",
        "c:shape",
        "c:smooth",
        "c:bubbleSize",
        "c:bubble3D",
        "c:extLst",
    )
    idx = OneAndOnlyOne("c:idx")
    order = OneAndOnlyOne("c:order")
    tx = ZeroOrOne("c:tx", successors=_tag_seq[3:])
    spPr = ZeroOrOne("c:spPr", successors=_tag_seq[4:])
    invertIfNegative = ZeroOrOne("c:invertIfNegative", successors=_tag_seq[5:])
    marker = ZeroOrOne("c:marker", successors=_tag_seq[7:])
    dPt = ZeroOrMore("c:dPt", successors=_tag_seq[9:])
    dLbls = ZeroOrOne("c:dLbls", successors=_tag_seq[10:])
    trendline = ZeroOrMore("c:trendline", successors=_tag_seq[11:])
    errBars = ZeroOrOne("c:errBars", successors=_tag_seq[12:])
    cat = ZeroOrOne("c:cat", successors=_tag_seq[13:])
    val = ZeroOrOne("c:val", successors=_tag_seq[14:])
    xVal = ZeroOrOne("c:xVal", successors=_tag_seq[15:])
    yVal = ZeroOrOne("c:yVal", successors=_tag_seq[16:])
    smooth = ZeroOrOne("c:smooth", successors=_tag_seq[18:])
    bubbleSize = ZeroOrOne("c:bubbleSize", successors=_tag_seq[19:])
    del _tag_seq

    @property
    def bubbleSize_ptCount_val(self):
        """
        Return the number of bubble size values as reflected in the `val`
        attribute of `./c:bubbleSize//c:ptCount`, or 0 if not present.
        """
        vals = self.xpath("./c:bubbleSize//c:ptCount/@val")
        if not vals:
            return 0
        return int(vals[0])

    @property
    def cat_ptCount_val(self):
        """
        Return the number of categories as reflected in the `val` attribute
        of `./c:cat//c:ptCount`, or 0 if not present.
        """
        vals = self.xpath("./c:cat//c:ptCount/@val")
        if not vals:
            return 0
        return int(vals[0])

    def get_dLbl(self, idx):
        """
        Return the `c:dLbl` element representing the label for the data point
        at offset *idx* in this series, or |None| if not present.
        """
        dLbls = self.dLbls
        if dLbls is None:
            return None
        return dLbls.get_dLbl_for_point(idx)

    def get_or_add_dLbl(self, idx):
        """
        Return the `c:dLbl` element representing the label of the point at
        offset *idx* in this series, newly created if not yet present.
        """
        dLbls = self.get_or_add_dLbls()
        return dLbls.get_or_add_dLbl_for_point(idx)

    def get_or_add_dPt_for_point(self, idx):
        """
        Return the `c:dPt` child representing the visual properties of the
        data point at index *idx*.
        """
        matches = self.xpath('c:dPt[c:idx[@val="%d"]]' % idx)
        if matches:
            return matches[0]
        dPt = self._add_dPt()
        dPt.idx.val = idx
        return dPt

    @property
    def xVal_ptCount_val(self):
        """
        Return the number of X values as reflected in the `val` attribute of
        `./c:xVal//c:ptCount`, or 0 if not present.
        """
        vals = self.xpath("./c:xVal//c:ptCount/@val")
        if not vals:
            return 0
        return int(vals[0])

    @property
    def yVal_ptCount_val(self):
        """
        Return the number of Y values as reflected in the `val` attribute of
        `./c:yVal//c:ptCount`, or 0 if not present.
        """
        vals = self.xpath("./c:yVal//c:ptCount/@val")
        if not vals:
            return 0
        return int(vals[0])

    def _new_dLbls(self):
        """Override metaclass method that creates `c:dLbls` element."""
        return CT_DLbls.new_dLbls()

    def _new_dPt(self):
        """
        Overrides the metaclass generated method to get `c:dPt` with minimal
        subtree.
        """
        return CT_DPt.new_dPt()

    def _new_errBars(self):
        """Override metaclass method to create a schema-valid `c:errBars`.

        A bare ``<c:errBars/>`` is invalid (the `errBarType` and `errValType`
        children are schema-required); seed those defaults so the element is
        valid the moment it is materialised.
        """
        return CT_ErrBars.new_errBars()

    def _new_trendline(self):
        """Override metaclass method to create a schema-valid `c:trendline`.

        Seeds the required ``<c:trendlineType>`` child (defaulting to
        ``linear``) so the element is schema-valid on creation.
        """
        return CT_Trendline.new_trendline()


class CT_StrVal_NumVal_Composite(BaseOxmlElement):
    """
    ``<c:pt>`` element, can be either CT_StrVal or CT_NumVal complex type.
    Using this class for both, differentiating as needed.
    """

    v = OneAndOnlyOne("c:v")
    idx = RequiredAttribute("idx", XsdUnsignedInt)

    @property
    def value(self):
        """
        The float value of the text in the required ``<c:v>`` child.
        """
        return float(self.v.text)


class CT_TrendlineType(BaseOxmlElement):
    """``<c:trendlineType>`` element, the kind of trendline curve to fit."""

    val = OptionalAttribute("val", XL_TRENDLINE_TYPE, default=XL_TRENDLINE_TYPE.LINEAR)


class CT_Trendline(BaseOxmlElement):
    """``<c:trendline>`` element, an analytical trend curve fitted to a series."""

    _tag_seq = (
        "c:name",
        "c:spPr",
        "c:trendlineType",
        "c:order",
        "c:period",
        "c:forward",
        "c:backward",
        "c:intercept",
        "c:dispRSqr",
        "c:dispEq",
        "c:trendlineLbl",
        "c:extLst",
    )
    name = ZeroOrOne("c:name", successors=_tag_seq[1:])
    spPr = ZeroOrOne("c:spPr", successors=_tag_seq[2:])
    trendlineType = OneAndOnlyOne("c:trendlineType")
    order = ZeroOrOne("c:order", successors=_tag_seq[4:])
    period = ZeroOrOne("c:period", successors=_tag_seq[5:])
    forward = ZeroOrOne("c:forward", successors=_tag_seq[6:])
    backward = ZeroOrOne("c:backward", successors=_tag_seq[7:])
    intercept = ZeroOrOne("c:intercept", successors=_tag_seq[8:])
    dispRSqr = ZeroOrOne("c:dispRSqr", successors=_tag_seq[9:])
    dispEq = ZeroOrOne("c:dispEq", successors=_tag_seq[10:])
    del _tag_seq

    @classmethod
    def new_trendline(cls):
        """Return a newly created "loose" `c:trendline` element.

        Contains the single required `c:trendlineType` child, defaulting to
        ``linear``, so the element is schema-valid the moment it is created.
        """
        return parse_xml(
            '<c:trendline %s><c:trendlineType val="linear"/></c:trendline>' % nsdecls("c")
        )


class CT_TrendlineName(BaseOxmlElement):
    """``<c:name>`` child of `c:trendline`, a plain-string legend label."""


class CT_ErrBars(BaseOxmlElement):
    """``<c:errBars>`` element, error bars drawn from each data point."""

    _tag_seq = (
        "c:errDir",
        "c:errBarType",
        "c:errValType",
        "c:noEndCap",
        "c:plus",
        "c:minus",
        "c:val",
        "c:spPr",
        "c:extLst",
    )
    errDir = ZeroOrOne("c:errDir", successors=_tag_seq[1:])
    errBarType = ZeroOrOne("c:errBarType", successors=_tag_seq[2:])
    errValType = ZeroOrOne("c:errValType", successors=_tag_seq[3:])
    noEndCap = ZeroOrOne("c:noEndCap", successors=_tag_seq[4:])
    plus = ZeroOrOne("c:plus", successors=_tag_seq[5:])
    minus = ZeroOrOne("c:minus", successors=_tag_seq[6:])
    val = ZeroOrOne("c:val", successors=_tag_seq[7:])
    spPr = ZeroOrOne("c:spPr", successors=_tag_seq[8:])
    del _tag_seq

    @classmethod
    def new_errBars(cls):
        """Return a newly created "loose" `c:errBars` element.

        The element contains the two schema-required children
        (`c:errBarType` and `c:errValType`) so it is schema-valid the moment
        it is created.
        """
        return parse_xml(
            "<c:errBars %s>\n"
            '  <c:errBarType val="both"/>\n'
            '  <c:errValType val="fixedVal"/>\n'
            "</c:errBars>\n" % nsdecls("c")
        )


class CT_ErrDir(BaseOxmlElement):
    """``<c:errDir>`` element, the axis along which error bars are drawn."""

    val = RequiredAttribute("val", XL_ERROR_BAR_DIRECTION)


class CT_ErrBarType(BaseOxmlElement):
    """``<c:errBarType>`` element, the direction error bars extend."""

    val = OptionalAttribute("val", XL_ERROR_BAR_TYPE, default=XL_ERROR_BAR_TYPE.BOTH)


class CT_ErrValType(BaseOxmlElement):
    """``<c:errValType>`` element, how the error amount is calculated."""

    val = OptionalAttribute("val", XL_ERROR_BAR_INCLUDE, default=XL_ERROR_BAR_INCLUDE.FIXED_VALUE)


# -- element-class registration for the trendline / errBars subtree. These are
# -- registered here (rather than from `power_pptx.oxml.__init__`) so the whole
# -- analytics feature is self-contained within the chart oxml package. The
# -- import is local to avoid a circular import at package-initialization time.
from power_pptx.oxml import register_element_cls  # noqa: E402
from power_pptx.oxml.chart.shared import (  # noqa: E402
    CT_Boolean,
    CT_Boolean_Explicit,
    CT_Double,
    CT_UnsignedInt,
)

# -- trendline + errBars container elements --
register_element_cls("c:trendline", CT_Trendline)
register_element_cls("c:trendlineType", CT_TrendlineType)
register_element_cls("c:errBars", CT_ErrBars)
register_element_cls("c:errDir", CT_ErrDir)
register_element_cls("c:errBarType", CT_ErrBarType)
register_element_cls("c:errValType", CT_ErrValType)
register_element_cls("c:name", CT_TrendlineName)
# -- custom error-bar plus/minus numeric data sources --
register_element_cls("c:plus", CT_NumDataSource)
register_element_cls("c:minus", CT_NumDataSource)
# -- scalar trendline children (c:order is already registered globally as
# -- CT_UnsignedInt for the series order element, which serves here too) --
register_element_cls("c:period", CT_UnsignedInt)
register_element_cls("c:forward", CT_Double)
register_element_cls("c:backward", CT_Double)
register_element_cls("c:intercept", CT_Double)
register_element_cls("c:dispEq", CT_Boolean_Explicit)
register_element_cls("c:dispRSqr", CT_Boolean_Explicit)
register_element_cls("c:noEndCap", CT_Boolean)
