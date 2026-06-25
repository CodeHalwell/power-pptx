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

    def it_moves_a_series_via_axis_group(self):
        prs, chart = _column_chart()
        chart.series[0].axis_group = "secondary"
        assert chart.series[0].axis_group == "secondary"
        assert len(chart._chartSpace.plotArea.xpath("c:valAx")) == 2

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
