"""Custom element classes for top-level chart-related XML elements."""

from __future__ import annotations

from typing import cast

from power_pptx.oxml import parse_xml
from power_pptx.oxml.chart.shared import CT_Title
from power_pptx.oxml.ns import nsdecls, qn
from power_pptx.oxml.simpletypes import ST_Style, XsdString
from power_pptx.oxml.text import CT_TextBody
from power_pptx.oxml.xmlchemy import (
    BaseOxmlElement,
    OneAndOnlyOne,
    RequiredAttribute,
    ZeroOrMore,
    ZeroOrOne,
)


class CT_Chart(BaseOxmlElement):
    """`c:chart` custom element class."""

    _tag_seq = (
        "c:title",
        "c:autoTitleDeleted",
        "c:pivotFmts",
        "c:view3D",
        "c:floor",
        "c:sideWall",
        "c:backWall",
        "c:plotArea",
        "c:legend",
        "c:plotVisOnly",
        "c:dispBlanksAs",
        "c:showDLblsOverMax",
        "c:extLst",
    )
    title = ZeroOrOne("c:title", successors=_tag_seq[1:])
    autoTitleDeleted = ZeroOrOne("c:autoTitleDeleted", successors=_tag_seq[2:])
    plotArea = OneAndOnlyOne("c:plotArea")
    legend = ZeroOrOne("c:legend", successors=_tag_seq[9:])
    rId: str = RequiredAttribute("r:id", XsdString)  # pyright: ignore[reportAssignmentType]

    @property
    def has_legend(self):
        """
        True if this chart has a legend defined, False otherwise.
        """
        legend = self.legend
        if legend is None:
            return False
        return True

    @has_legend.setter
    def has_legend(self, bool_value):
        """
        Add, remove, or leave alone the ``<c:legend>`` child element depending
        on current state and *bool_value*. If *bool_value* is |True| and no
        ``<c:legend>`` element is present, a new default element is added.
        When |False|, any existing legend element is removed.
        """
        if bool(bool_value) is False:
            self._remove_legend()
        else:
            if self.legend is None:
                self._add_legend()

    @staticmethod
    def new_chart(rId: str) -> CT_Chart:
        """Return a new `c:chart` element."""
        return cast(CT_Chart, parse_xml(f'<c:chart {nsdecls("c")} {nsdecls("r")} r:id="{rId}"/>'))

    def _new_title(self):
        return CT_Title.new_title()


class CT_ChartSpace(BaseOxmlElement):
    """`c:chartSpace` root element of a chart part."""

    _tag_seq = (
        "c:date1904",
        "c:lang",
        "c:roundedCorners",
        "c:style",
        "c:clrMapOvr",
        "c:pivotSource",
        "c:protection",
        "c:chart",
        "c:spPr",
        "c:txPr",
        "c:externalData",
        "c:printSettings",
        "c:userShapes",
        "c:extLst",
    )
    date1904 = ZeroOrOne("c:date1904", successors=_tag_seq[1:])
    style = ZeroOrOne("c:style", successors=_tag_seq[4:])
    chart = OneAndOnlyOne("c:chart")
    txPr = ZeroOrOne("c:txPr", successors=_tag_seq[10:])
    externalData = ZeroOrOne("c:externalData", successors=_tag_seq[11:])
    del _tag_seq

    @property
    def catAx_lst(self):
        return self.chart.plotArea.catAx_lst

    @property
    def date_1904(self):
        """
        Return |True| if the `c:date1904` child element resolves truthy,
        |False| otherwise. This value indicates whether date number values
        are based on the 1900 or 1904 epoch.
        """
        date1904 = self.date1904
        if date1904 is None:
            return False
        return date1904.val

    @property
    def dateAx_lst(self):
        return self.xpath("c:chart/c:plotArea/c:dateAx")

    def get_or_add_title(self):
        """Return the `c:title` grandchild, newly created if not present."""
        return self.chart.get_or_add_title()

    @property
    def plotArea(self):
        """
        Return the required `c:chartSpace/c:chart/c:plotArea` grandchild
        element.
        """
        return self.chart.plotArea

    @property
    def valAx_lst(self):
        return self.chart.plotArea.valAx_lst

    @property
    def xlsx_part_rId(self):
        """
        The string in the required ``r:id`` attribute of the
        `<c:externalData>` child, or |None| if no externalData element is
        present.
        """
        externalData = self.externalData
        if externalData is None:
            return None
        return externalData.rId

    def _add_externalData(self):
        """
        Always add a ``<c:autoUpdate val="0"/>`` child so auto-updating
        behavior is off by default.
        """
        externalData = self._new_externalData()
        externalData._add_autoUpdate(val=False)
        self._insert_externalData(externalData)
        return externalData

    def _new_txPr(self):
        return CT_TextBody.new_txPr()


class CT_ExternalData(BaseOxmlElement):
    """
    `<c:externalData>` element, defining link to embedded Excel package part
    containing the chart data.
    """

    autoUpdate = ZeroOrOne("c:autoUpdate")
    rId = RequiredAttribute("r:id", XsdString)


class CT_PlotArea(BaseOxmlElement):
    """
    ``<c:plotArea>`` element.
    """

    catAx = ZeroOrMore("c:catAx")
    valAx = ZeroOrMore("c:valAx")

    def iter_sers(self):
        """
        Generate each of the `c:ser` elements in this chart, ordered first by
        the document order of the containing xChart element, then by their
        ordering within the xChart element (not necessarily document order).
        """
        for xChart in self.iter_xCharts():
            for ser in xChart.iter_sers():
                yield ser

    def iter_xCharts(self):
        """
        Generate each xChart child element in document.
        """
        plot_tags = (
            qn("c:area3DChart"),
            qn("c:areaChart"),
            qn("c:bar3DChart"),
            qn("c:barChart"),
            qn("c:bubbleChart"),
            qn("c:doughnutChart"),
            qn("c:line3DChart"),
            qn("c:lineChart"),
            qn("c:ofPieChart"),
            qn("c:pie3DChart"),
            qn("c:pieChart"),
            qn("c:radarChart"),
            qn("c:scatterChart"),
            qn("c:stockChart"),
            qn("c:surface3DChart"),
            qn("c:surfaceChart"),
        )

        for child in self.iterchildren():
            if child.tag not in plot_tags:
                continue
            yield child

    @property
    def last_ser(self):
        """
        Return the last `<c:ser>` element in the last xChart element, based
        on series order (not necessarily the same element as document order).
        """
        last_xChart = self.xCharts[-1]
        sers = last_xChart.sers
        if not sers:
            return None
        return sers[-1]

    @property
    def next_idx(self):
        """
        Return the next available `c:ser/c:idx` value within the scope of
        this chart, the maximum idx value found on existing series,
        incremented by one.
        """
        idx_vals = [s.idx.val for s in self.sers]
        if not idx_vals:
            return 0
        return max(idx_vals) + 1

    @property
    def next_order(self):
        """
        Return the next available `c:ser/c:order` value within the scope of
        this chart, the maximum order value found on existing series,
        incremented by one.
        """
        order_vals = [s.order.val for s in self.sers]
        if not order_vals:
            return 0
        return max(order_vals) + 1

    @property
    def sers(self):
        """
        Return a sequence containing all the `c:ser` elements in this chart,
        ordered first by the document order of the containing xChart element,
        then by their ordering within the xChart element (not necessarily
        document order).
        """
        return tuple(self.iter_sers())

    @property
    def xCharts(self):
        """
        Return a sequence containing all the `c:{x}Chart` elements in this
        chart, in document order.
        """
        return tuple(self.iter_xCharts())

    # -- secondary-axis support -----------------------------------------

    def iter_axIds(self):
        """Generate every ``c:axId`` value defined anywhere in the plot area.

        Includes both the axId references inside each xChart and the axId of
        each axis element, so a freshly-allocated id can be checked against
        the complete set already in use.
        """
        for axId in self.xpath(".//c:axId"):
            yield int(axId.get("val"))

    def _next_axId(self, used):
        """Return a fresh ``c:axId`` value not present in *used*.

        Stays within the signed-int32 range ``1..2**31-1`` — ids at or above
        ``2**31`` make PowerPoint flag the file for repair, a release-blocking
        bug this allocator deliberately avoids.
        """
        # -- start just past the current max so the new ids read as "later"
        # -- axes in document order, but cap into signed-int32 range and fall
        # -- back to a linear scan if we'd overflow.
        _INT32_MAX = 2**31 - 1
        candidate = (max(used) + 1) if used else 1
        if candidate > _INT32_MAX:
            candidate = 1
        while candidate in used or candidate < 1:
            candidate += 1
            if candidate > _INT32_MAX:
                # -- wrap and scan from the bottom; the used-set is tiny so a
                # -- free slot is guaranteed to exist far below the cap.
                candidate = 1
        return candidate

    @property
    def _last_xChart(self):
        xCharts = self.xCharts
        return xCharts[-1] if xCharts else None

    @property
    def secondary_value_axis(self):
        """The secondary ``c:valAx`` element, or |None| if none has been added.

        The secondary value axis is the (single) visible value axis drawn on
        the right (``axPos="r"``) — the orientation :meth:`add_secondary_value_axis`
        always gives it. Detecting by ``axPos`` is robust for scatter / bubble
        charts, which natively carry two value axes on a single plot, so a mere
        count of ``c:valAx`` elements is not a reliable signal there. (Primary
        value axes are emitted with ``axPos="l"``.)
        """
        matches = self.xpath('c:valAx[c:axPos/@val="r"][c:delete/@val="0"]')
        return matches[0] if matches else None

    def add_secondary_value_axis(self):
        """Create a secondary value axis and return its ``c:valAx`` element.

        Allocates two fresh signed-int32 axId values, builds a secondary value
        axis (drawn on the right) plus a hidden secondary cross axis that it
        crosses, and re-points the front-most plot's two ``c:axId`` children to
        the new ids so that plot is rendered against the secondary axes.

        Returns the existing secondary ``c:valAx`` if one is already present,
        making this method idempotent.
        """
        existing_secondary = self.secondary_value_axis
        if existing_secondary is not None:
            return existing_secondary

        used = set(self.iter_axIds())
        val2_id = self._next_axId(used)
        used.add(val2_id)
        cross2_id = self._next_axId(used)
        used.add(cross2_id)

        # -- determine whether the existing "category" axis is a real catAx
        # -- (bar/line/area) or a valAx (scatter/bubble), and mirror it.
        cross_is_val = not bool(self.xpath("c:catAx"))

        c = nsdecls("c")
        valAx_xml = (
            f"<c:valAx {c}>\n"
            f'  <c:axId val="{val2_id}"/>\n'
            '  <c:scaling><c:orientation val="minMax"/></c:scaling>\n'
            '  <c:delete val="0"/>\n'
            '  <c:axPos val="r"/>\n'
            '  <c:numFmt formatCode="General" sourceLinked="1"/>\n'
            '  <c:majorTickMark val="out"/>\n'
            '  <c:minorTickMark val="none"/>\n'
            '  <c:tickLblPos val="nextTo"/>\n'
            f'  <c:crossAx val="{cross2_id}"/>\n'
            '  <c:crosses val="max"/>\n'
            '  <c:crossBetween val="between"/>\n'
            "</c:valAx>\n"
        )
        if cross_is_val:
            cross_xml = (
                f"<c:valAx {c}>\n"
                f'  <c:axId val="{cross2_id}"/>\n'
                '  <c:scaling><c:orientation val="minMax"/></c:scaling>\n'
                '  <c:delete val="1"/>\n'
                '  <c:axPos val="b"/>\n'
                '  <c:numFmt formatCode="General" sourceLinked="1"/>\n'
                '  <c:majorTickMark val="out"/>\n'
                '  <c:minorTickMark val="none"/>\n'
                '  <c:tickLblPos val="nextTo"/>\n'
                f'  <c:crossAx val="{val2_id}"/>\n'
                '  <c:crosses val="autoZero"/>\n'
                '  <c:crossBetween val="midCat"/>\n'
                "</c:valAx>\n"
            )
        else:
            cross_xml = (
                f"<c:catAx {c}>\n"
                f'  <c:axId val="{cross2_id}"/>\n'
                '  <c:scaling><c:orientation val="minMax"/></c:scaling>\n'
                '  <c:delete val="1"/>\n'
                '  <c:axPos val="b"/>\n'
                '  <c:numFmt formatCode="General" sourceLinked="1"/>\n'
                '  <c:majorTickMark val="out"/>\n'
                '  <c:minorTickMark val="none"/>\n'
                '  <c:tickLblPos val="nextTo"/>\n'
                f'  <c:crossAx val="{val2_id}"/>\n'
                '  <c:crosses val="autoZero"/>\n'
                '  <c:auto val="1"/>\n'
                '  <c:lblAlgn val="ctr"/>\n'
                '  <c:lblOffset val="100"/>\n'
                '  <c:noMultiLvlLbl val="0"/>\n'
                "</c:catAx>\n"
            )

        valAx = parse_xml(valAx_xml)
        cross_ax = parse_xml(cross_xml)

        # -- insert the new axes after the last existing axis (or after the
        # -- last xChart when no axes exist), preserving plotArea child order:
        # -- ...xCharts, axes..., (dTable?, spPr?, extLst?).
        axes = self.xpath("c:valAx | c:catAx | c:dateAx | c:serAx")
        anchor = axes[-1] if axes else self._last_xChart
        # -- valAx first then the (hidden) cross axis, matching PowerPoint's
        # -- own ordering for a secondary axis.
        anchor.addnext(cross_ax)
        anchor.addnext(valAx)

        # -- re-point the front-most plot onto the new axis ids.
        self._repoint_front_plot_axes(val2_id, cross2_id)
        return valAx

    def _repoint_front_plot_axes(self, val2_id, cross2_id):
        """Re-point the last xChart's two ``c:axId`` children to the new ids.

        The category-side id is set to *cross2_id* and the value-side id to
        *val2_id*, matching how the new secondary axes cross-reference each
        other.
        """
        xChart = self._last_xChart
        if xChart is None:
            return
        axIds = xChart.xpath("c:axId")
        if len(axIds) < 2:
            return
        # -- by convention the first axId is the category axis, the second the
        # -- value axis (the writers emit them in that order).
        axIds[0].set("val", str(cross2_id))
        axIds[1].set("val", str(val2_id))


class CT_Style(BaseOxmlElement):
    """
    ``<c:style>`` element; defines the chart style.
    """

    val = RequiredAttribute("val", ST_Style)
