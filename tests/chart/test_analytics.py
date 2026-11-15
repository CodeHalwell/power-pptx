# pyright: reportPrivateUsage=false

"""Unit-test suite for `power_pptx.chart.analytics` and the series analytics API.

Covers trendlines, error bars, and the secondary value axis, including a
round-trip and a schema-validity check for a deck that exercises all three.
"""

from __future__ import annotations

import io

import pytest

from power_pptx import Presentation
from power_pptx.chart.analytics import ErrorBars, Trendline, Trendlines
from power_pptx.chart.data import CategoryChartData, XyChartData
from power_pptx.chart.series import BarSeries
from power_pptx.enum.chart import (
    XL_CHART_TYPE,
    XL_ERROR_BAR_INCLUDE,
    XL_ERROR_BAR_TYPE,
    XL_TRENDLINE_TYPE,
)
from power_pptx.util import Inches

from ..unitutil.cxml import element

# -- real-chart builders ----------------------------------------------------


def _column_chart(series=("Rev", "Growth")):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    data = CategoryChartData()
    data.categories = ["A", "B", "C"]
    for name in series:
        data.add_series(name, (1.0, 2.0, 3.0))
    gframe = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1), Inches(6), Inches(4), data
    )
    return prs, gframe.chart


def _scatter_chart():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    data = XyChartData()
    s = data.add_series("S")
    for x, y in [(1, 2), (2, 3), (3, 4)]:
        s.add_data_point(x, y)
    gframe = slide.shapes.add_chart(
        XL_CHART_TYPE.XY_SCATTER, Inches(1), Inches(1), Inches(6), Inches(4), data
    )
    return prs, gframe.chart


def _saved_bytes(prs):
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# -- Trendlines -------------------------------------------------------------


class DescribeTrendlines(object):
    def it_starts_empty(self):
        ser = element("c:ser/(c:idx{val=0},c:order{val=0})")
        trendlines = Trendlines(ser)
        assert len(trendlines) == 0

    def it_adds_a_linear_trendline_with_equation_and_r_squared(self):
        ser = element("c:ser/(c:idx{val=0},c:order{val=0})")
        trendlines = Trendlines(ser)

        tl = trendlines.add("linear", show_equation=True, show_r_squared=True)

        assert isinstance(tl, Trendline)
        assert len(trendlines) == 1
        assert tl.trendline_type == XL_TRENDLINE_TYPE.LINEAR
        assert tl.show_equation is True
        assert tl.show_r_squared is True
        # -- the trendlineType val is written explicitly
        assert ser.xpath("c:trendline/c:trendlineType/@val") == ["linear"]
        assert ser.xpath("c:trendline/c:dispEq/@val") == ["1"]
        assert ser.xpath("c:trendline/c:dispRSqr/@val") == ["1"]

    @pytest.mark.parametrize(
        ("kind", "expected_xml_val"),
        [
            ("linear", "linear"),
            ("exp", "exp"),
            ("exponential", "exp"),
            ("log", "log"),
            ("movingAvg", "movingAvg"),
            ("poly", "poly"),
            ("power", "power"),
            (XL_TRENDLINE_TYPE.LOGARITHMIC, "log"),
        ],
    )
    def it_accepts_kind_names_and_enum_members(self, kind, expected_xml_val):
        ser = element("c:ser/(c:idx{val=0},c:order{val=0})")
        Trendlines(ser).add(kind)
        assert ser.xpath("c:trendline/c:trendlineType/@val") == [expected_xml_val]

    def it_writes_order_period_and_projection(self):
        ser = element("c:ser/(c:idx{val=0},c:order{val=0})")
        trendlines = Trendlines(ser)

        trendlines.add("poly", order=3, name="Fit")
        trendlines.add("movingAvg", period=4, forward=2.0, backward=1.0)

        assert ser.xpath("c:trendline[1]/c:order/@val") == ["3"]
        assert ser.xpath("c:trendline[1]/c:name/text()") == ["Fit"]
        assert ser.xpath("c:trendline[2]/c:period/@val") == ["4"]
        assert ser.xpath("c:trendline[2]/c:forward/@val") == ["2.0"]
        assert ser.xpath("c:trendline[2]/c:backward/@val") == ["1.0"]
        assert len(trendlines) == 2

    def it_rejects_an_unknown_kind(self):
        ser = element("c:ser/(c:idx{val=0},c:order{val=0})")
        with pytest.raises(ValueError):
            Trendlines(ser).add("bogus")

    @pytest.mark.parametrize("order", [0, 1, 7, 10])
    def it_rejects_a_polynomial_order_outside_2_to_6(self, order):
        # ST_Order is 2..6; an out-of-range c:order makes PowerPoint
        # report the deck as needing repair.
        ser = element("c:ser/(c:idx{val=0},c:order{val=0})")
        with pytest.raises(ValueError):
            Trendlines(ser).add("poly", order=order)

    @pytest.mark.parametrize("period", [0, 1])
    def it_rejects_a_moving_average_period_below_2(self, period):
        # ST_Period requires >= 2.
        ser = element("c:ser/(c:idx{val=0},c:order{val=0})")
        with pytest.raises(ValueError):
            Trendlines(ser).add("movingAvg", period=period)

    def it_supports_indexing_and_iteration(self):
        ser = element("c:ser/(c:idx{val=0},c:order{val=0})")
        trendlines = Trendlines(ser)
        trendlines.add("linear")
        trendlines.add("poly", order=2)
        assert [t.trendline_type for t in trendlines] == [
            XL_TRENDLINE_TYPE.LINEAR,
            XL_TRENDLINE_TYPE.POLYNOMIAL,
        ]
        assert trendlines[1].trendline_type == XL_TRENDLINE_TYPE.POLYNOMIAL


# -- ErrorBars --------------------------------------------------------------


class DescribeErrorBars(object):
    def it_is_absent_until_configured(self):
        ser = element("c:ser/(c:idx{val=0},c:order{val=0})")
        bars = ErrorBars(ser)
        assert bars.exists is False
        assert bars.include_type is None

    @pytest.mark.parametrize(
        ("method", "args", "expected_val_type"),
        [
            ("fixed", (1.5,), XL_ERROR_BAR_INCLUDE.FIXED_VALUE),
            ("percentage", (5,), XL_ERROR_BAR_INCLUDE.PERCENTAGE),
            ("standard_deviation", (2,), XL_ERROR_BAR_INCLUDE.STANDARD_DEVIATION),
        ],
    )
    def it_builds_value_based_error_bars(self, method, args, expected_val_type):
        ser = element("c:ser/(c:idx{val=0},c:order{val=0})")
        bars = ErrorBars(ser)

        getattr(bars, method)(*args)

        assert bars.exists is True
        assert bars.error_bar_type == XL_ERROR_BAR_TYPE.BOTH
        assert bars.include_type == expected_val_type
        assert ser.xpath("c:errBars/c:errBarType/@val") == ["both"]
        assert ser.xpath("c:errBars/c:val/@val") == [str(float(args[0]))]

    def it_builds_standard_error_bars_without_a_value(self):
        ser = element("c:ser/(c:idx{val=0},c:order{val=0})")
        bars = ErrorBars(ser)
        bars.standard_error()
        assert ser.xpath("c:errBars/c:errValType/@val") == ["stdErr"]
        assert ser.xpath("c:errBars/c:val") == []

    def it_honors_the_direction_argument(self):
        ser = element("c:ser/(c:idx{val=0},c:order{val=0})")
        ErrorBars(ser).fixed(2.0, direction="minus")
        assert ser.xpath("c:errBars/c:errBarType/@val") == ["minus"]

    def it_builds_custom_error_bars_with_plus_and_minus(self):
        ser = element("c:ser/(c:idx{val=0},c:order{val=0})")
        bars = ErrorBars(ser)

        bars.custom([0.1, 0.2, 0.3], [0.4, 0.5, 0.6])

        assert ser.xpath("c:errBars/c:errValType/@val") == ["cust"]
        assert ser.xpath("c:errBars/c:plus/c:numLit/c:pt/c:v/text()") == ["0.1", "0.2", "0.3"]
        assert ser.xpath("c:errBars/c:minus/c:numLit/c:pt/c:v/text()") == ["0.4", "0.5", "0.6"]

    def it_replaces_prior_settings_on_reconfigure(self):
        ser = element("c:ser/(c:idx{val=0},c:order{val=0})")
        bars = ErrorBars(ser)
        bars.custom([1.0], [1.0])
        bars.fixed(3.0)
        # -- only one errBars, and the stale plus/minus are gone
        assert len(ser.xpath("c:errBars")) == 1
        assert ser.xpath("c:errBars/c:plus") == []
        assert ser.xpath("c:errBars/c:val/@val") == ["3.0"]


# -- series wiring ----------------------------------------------------------


class DescribeSeriesAnalyticsWiring(object):
    def it_exposes_trendlines_and_error_bars_on_a_bar_series(self):
        ser = element("c:ser/(c:idx{val=0},c:order{val=0})")
        series = BarSeries(ser)
        assert isinstance(series.trendlines, Trendlines)
        assert isinstance(series.error_bars, ErrorBars)

    def it_omits_analytics_on_pie_and_radar_series(self):
        from power_pptx.chart.series import PieSeries, RadarSeries

        for cls in (PieSeries, RadarSeries):
            series = cls(element("c:ser/(c:idx{val=0},c:order{val=0})"))
            assert not hasattr(series, "trendlines")
            assert not hasattr(series, "error_bars")


# -- secondary value axis ---------------------------------------------------


class DescribeSecondaryValueAxis(object):
    def it_adds_a_second_value_axis_with_in_range_ids(self):
        prs, chart = _column_chart()
        plotArea = chart._chartSpace.plotArea
        assert len(plotArea.xpath("c:valAx")) == 1

        chart.secondary_value_axis

        assert len(plotArea.xpath("c:valAx")) == 2
        ax_ids = [int(v) for v in plotArea.xpath(".//c:axId/@val")]
        assert all(1 <= i <= 2**31 - 1 for i in ax_ids)
        # -- no id collisions among the four distinct axis-pair ids
        assert len(set(ax_ids)) == 4

    def it_is_idempotent(self):
        prs, chart = _column_chart()
        first_id = chart.secondary_value_axis._element.xpath("c:axId/@val")
        chart.secondary_value_axis
        second_id = chart.secondary_value_axis._element.xpath("c:axId/@val")
        assert first_id == second_id
        assert len(chart._chartSpace.plotArea.xpath("c:valAx")) == 2

    def and_it_stays_idempotent_after_the_secondary_axis_is_hidden(self):
        # Hiding writes a bare `<c:delete/>` (val attribute stripped as the
        # schema default); detection must still match so a later access
        # doesn't pile a third axis pair onto the plot area.
        prs, chart = _column_chart()
        chart.secondary_value_axis.visible = False
        chart.secondary_value_axis
        plotArea = chart._chartSpace.plotArea
        assert len(plotArea.xpath("c:valAx")) == 2

    def it_moves_a_series_via_axis_group(self):
        prs, chart = _column_chart()
        # -- hold the series: `chart.series` lists series plot by plot, so the
        # -- one that moves into a plot of its own is no longer at index 0
        rev = chart.series[0]
        rev.axis_group = "secondary"
        assert rev.axis_group == "secondary"
        assert len(chart._chartSpace.plotArea.xpath("c:valAx")) == 2

    def it_moves_only_the_series_it_is_asked_to_move(self):
        # Regression: the axes belong to the plot, so re-pointing the plot the
        # series shared put *every* series on the secondary axis and left the
        # primary axes unreferenced.
        prs, chart = _column_chart()
        rev, growth = chart.series
        plotArea = chart._chartSpace.plotArea

        growth.axis_group = "secondary"

        assert (rev.axis_group, growth.axis_group) == ("primary", "secondary")
        assert [s.name for s in chart.series] == ["Rev", "Growth"]
        assert len(chart.plots) == 2
        # -- every axis is used by a plot, and every plot's axes exist
        axis_ids = set(plotArea.xpath("c:catAx/c:axId/@val | c:valAx/c:axId/@val"))
        plot_ids = set(plotArea.xpath("c:barChart/c:axId/@val"))
        assert plot_ids == axis_ids
        assert len(axis_ids) == 4

    def it_splits_the_series_off_into_a_plot_of_the_same_kind(self):
        prs, chart = _column_chart(("A", "B", "C"))
        plotArea = chart._chartSpace.plotArea
        original = plotArea.xpath("c:barChart")[0]
        original.get_or_add_gapWidth().val = 80

        chart.series[1].axis_group = "secondary"

        first, second = plotArea.xpath("c:barChart")
        assert first is original
        assert [s.name for s in chart.series] == ["A", "C", "B"]
        # -- the new plot follows the old one and precedes every axis
        assert [c.tag.rpartition("}")[2] for c in plotArea] == [
            "barChart",
            "barChart",
            "catAx",
            "valAx",
            "valAx",
            "catAx",
        ]
        # -- same kind of plot, same settings, different axes
        assert second.xpath("c:barDir/@val") == first.xpath("c:barDir/@val")
        assert second.xpath("c:grouping/@val") == first.xpath("c:grouping/@val")
        assert second.xpath("c:gapWidth/@val") == ["80"]
        assert not set(second.xpath("c:axId/@val")) & set(first.xpath("c:axId/@val"))
        # -- series identity is preserved: idx/order are chart-wide and unique
        assert sorted(plotArea.xpath(".//c:ser/c:idx/@val")) == ["0", "1", "2"]
        assert sorted(plotArea.xpath(".//c:ser/c:order/@val")) == ["0", "1", "2"]

    def it_gathers_like_series_on_the_secondary_axis_into_one_plot(self):
        # Two column series on the secondary axis must cluster side by side,
        # which they only do as members of the same plot.
        prs, chart = _column_chart(("A", "B", "C"))
        a, b, c = chart.series

        c.axis_group = "secondary"
        b.axis_group = "secondary"

        assert [s.axis_group for s in (a, b, c)] == ["primary", "secondary", "secondary"]
        assert [len(p.series) for p in chart.plots] == [1, 2]
        assert len(chart._chartSpace.plotArea.xpath("c:valAx")) == 2

    def it_moves_the_whole_plot_when_the_series_is_alone_in_it(self):
        prs, chart = _column_chart(("Only",))
        chart.series[0].axis_group = "secondary"
        assert chart.series[0].axis_group == "secondary"
        assert len(chart.plots) == 1

    def it_keeps_a_proxy_obtained_before_the_move_usable(self):
        prs, chart = _column_chart()
        growth = chart.series[1]
        growth.axis_group = "secondary"
        growth.format.fill.solid()
        growth.format.fill.fore_color.rgb = "112233"
        assert chart.series[1].format.fill.fore_color.rgb == growth.format.fill.fore_color.rgb

    def it_is_a_no_op_for_a_series_already_on_the_secondary_axis(self):
        prs, chart = _column_chart()
        growth = chart.series[1]
        growth.axis_group = "secondary"
        before = chart._chartSpace.xml

        growth.axis_group = "secondary"

        assert chart._chartSpace.xml == before

    def it_splits_a_scatter_series_too(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        data = XyChartData()
        for name in ("S1", "S2"):
            s = data.add_series(name)
            for x, y in [(1, 2), (2, 3), (3, 4)]:
                s.add_data_point(x, y)
        chart = slide.shapes.add_chart(
            XL_CHART_TYPE.XY_SCATTER, Inches(1), Inches(1), Inches(6), Inches(4), data
        ).chart
        s1, s2 = chart.series
        y_axis = chart.value_axis._element

        s2.axis_group = "secondary"

        assert (s1.axis_group, s2.axis_group) == ("primary", "secondary")
        assert chart.value_axis._element is y_axis
        assert chart.category_axis._element.xpath("c:axPos/@val") == ["b"]


class DescribePrimaryValueAxis(object):
    """`chart.value_axis` is the primary axis whatever else the chart holds."""

    def it_stays_the_primary_axis_once_a_secondary_one_exists(self):
        # Regression: with two `c:valAx` in the plot area the second one was
        # returned, the XY-chart rule, which here is the secondary axis.
        prs, chart = _column_chart()
        primary = chart.value_axis._element

        chart.series[1].axis_group = "secondary"

        assert chart.value_axis._element is primary
        assert chart.value_axis._element is not chart.secondary_value_axis._element

    def it_scales_the_primary_axis_not_the_secondary(self):
        prs, chart = _column_chart()
        primary = chart.value_axis._element
        chart.series[1].axis_group = "secondary"

        chart.value_axis.maximum_scale = 1000

        assert primary.xpath("c:scaling/c:max/@val") == ["1000.0"]
        assert chart.secondary_value_axis._element.xpath("c:scaling/c:max") == []

    def it_is_still_the_y_axis_of_a_scatter_chart(self):
        prs, chart = _scatter_chart()
        x_axis, y_axis = chart._chartSpace.valAx_lst
        assert chart.value_axis._element is y_axis
        assert chart.category_axis._element is x_axis

        chart.secondary_value_axis

        assert chart.value_axis._element is y_axis

    def it_is_the_lone_value_axis_even_when_that_is_drawn_on_the_right(self):
        # `axPos="r"` is how the secondary axis is recognised; a chart whose
        # only value axis sits there must still report it.
        prs, chart = _column_chart()
        valAx = chart._chartSpace.valAx_lst[0]
        valAx.xpath("c:axPos")[0].set("val", "r")

        assert chart.value_axis._element is valAx


class DescribeSecondaryValueAxisAccess(object):
    """What `chart.secondary_value_axis` re-points when it creates the axis."""

    def it_leaves_a_plot_of_several_series_on_the_primary_axis(self):
        # Regression: this is the first line of the documented pattern
        #     chart.secondary_value_axis
        #     chart.series[1].axis_group = "secondary"
        # and it used to move the one plot, i.e. both series, by itself.
        prs, chart = _column_chart()
        rev, growth = chart.series

        chart.secondary_value_axis

        assert (rev.axis_group, growth.axis_group) == ("primary", "primary")

        growth.axis_group = "secondary"

        assert (rev.axis_group, growth.axis_group) == ("primary", "secondary")
        assert len(chart._chartSpace.plotArea.xpath("c:valAx")) == 2

    def it_still_repoints_a_plot_holding_a_single_series(self):
        prs, chart = _column_chart(("Only",))
        chart.secondary_value_axis
        assert chart.series[0].axis_group == "secondary"

    def it_still_repoints_the_front_plot_of_a_combo_chart(self):
        import copy

        prs, chart = _column_chart(("A", "B", "C"))
        # -- make a combo: a second plot on the same axes, holding series C
        back = chart._chartSpace.plotArea.xpath("c:barChart")[0]
        front = copy.deepcopy(back)
        for ser in front.xpath("c:ser")[:2]:
            front.remove(ser)
        back.remove(back.xpath("c:ser")[2])
        back.addnext(front)
        assert [len(p.series) for p in chart.plots] == [2, 1]

        chart.secondary_value_axis

        assert [s.axis_group for s in chart.series] == ["primary", "primary", "secondary"]

    def it_repoints_the_targeted_plot_not_just_the_last(self):
        # Combo chart: two plots sharing the primary axes. Moving the FIRST
        # plot to secondary must repoint that plot, not the front-most one
        # (PR #39 review).
        from power_pptx.oxml import parse_xml
        from power_pptx.oxml.ns import nsdecls

        xml = (
            f"<c:plotArea {nsdecls('c')}>"
            '<c:barChart><c:ser/><c:axId val="111"/><c:axId val="222"/></c:barChart>'
            '<c:lineChart><c:ser/><c:axId val="111"/><c:axId val="222"/></c:lineChart>'
            '<c:catAx><c:axId val="111"/></c:catAx>'
            '<c:valAx><c:axId val="222"/></c:valAx>'
            "</c:plotArea>"
        )
        plotArea = parse_xml(xml)
        bar = plotArea.xpath("c:barChart")[0]

        plotArea.add_secondary_value_axis(bar)

        bar_ids = [a.get("val") for a in bar.xpath("c:axId")]
        line_ids = [a.get("val") for a in plotArea.xpath("c:lineChart")[0].xpath("c:axId")]
        assert bar_ids != ["111", "222"]  # the targeted plot was repointed
        assert line_ids == ["111", "222"]  # the other plot was left alone

    def it_raises_for_a_chart_without_a_value_axis(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        data = CategoryChartData()
        data.categories = ["A", "B"]
        data.add_series("S", (1.0, 2.0))
        gframe = slide.shapes.add_chart(
            XL_CHART_TYPE.PIE, Inches(1), Inches(1), Inches(4), Inches(4), data
        )
        with pytest.raises(ValueError):
            gframe.chart.secondary_value_axis

    def it_works_for_a_scatter_chart_two_value_axes(self):
        prs, chart = _scatter_chart()
        chart.secondary_value_axis
        # -- scatter uses valAx for both axes; the hidden cross axis is a valAx
        plotArea = chart._chartSpace.plotArea
        assert len(plotArea.xpath("c:valAx")) == 4
        assert plotArea.xpath("c:catAx") == []


# -- round-trip + schema-validity (all three features at once) --------------


def _build_full_deck():
    prs, chart = _column_chart()
    s0 = chart.series[0]
    s0.trendlines.add("linear", show_equation=True, show_r_squared=True, forward=1.0)
    s0.trendlines.add("poly", order=3)
    s0.error_bars.percentage(5)
    chart.series[1].error_bars.custom([0.1, 0.2, 0.3], [0.1, 0.2, 0.3])
    chart.secondary_value_axis
    return prs


class DescribeAnalyticsRoundTripAndSchema(object):
    def it_round_trips_clean(self):
        from tests.integration.round_trip import assert_round_trip

        assert_round_trip(_build_full_deck())

    def it_emits_schema_valid_xml(self):
        from tests.schema.oxml_schema_validator import (
            iter_schema_violations,
            schema_validation_available,
        )

        if not schema_validation_available():
            pytest.skip("schema validation unavailable (lxml/XSD missing)")

        saved = _saved_bytes(_build_full_deck())
        assert list(iter_schema_violations(saved)) == []
