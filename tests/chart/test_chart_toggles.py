"""Round-trip and schema-validity tests for the chart plot & axis toggles.

Covers the public API added for "go to Excel for this" gaps:

* ``DoughnutPlot.hole_size``
* ``LinePlot.smooth``
* ``ValueAxis.log_base``

These build real chart decks via ``slide.shapes.add_chart`` and assert both
that the deck survives a save -> open -> save cycle unchanged and that the
emitted XML validates against the bundled ISO 29500 XSDs.
"""

from __future__ import annotations

import io

import pytest

from power_pptx import Presentation
from power_pptx.chart.data import CategoryChartData
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.util import Inches

from ..integration.round_trip import assert_round_trip
from ..schema.oxml_schema_validator import (
    iter_schema_violations,
    schema_validation_available,
)


def _blank_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def _category_data(*series):
    data = CategoryChartData()
    data.categories = ["Q1", "Q2", "Q3"]
    for name, values in series:
        data.add_series(name, values)
    return data


def _doughnut_deck():
    prs = Presentation()
    s = _blank_slide(prs)
    data = _category_data(("Share", (30, 40, 30)))
    gf = s.shapes.add_chart(
        XL_CHART_TYPE.DOUGHNUT, Inches(0.5), Inches(0.5), Inches(4), Inches(3), data
    )
    gf.chart.plots[0].hole_size = 65
    return prs


def _line_smooth_deck():
    prs = Presentation()
    s = _blank_slide(prs)
    data = _category_data(("North", (1, 2, 3)), ("South", (3, 2, 1)))
    gf = s.shapes.add_chart(
        XL_CHART_TYPE.LINE, Inches(0.5), Inches(0.5), Inches(5), Inches(3), data
    )
    gf.chart.plots[0].smooth = True
    return prs


def _log_axis_deck():
    prs = Presentation()
    s = _blank_slide(prs)
    data = _category_data(("Growth", (1, 100, 10000)))
    gf = s.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(0.5),
        Inches(0.5),
        Inches(5),
        Inches(3),
        data,
    )
    gf.chart.value_axis.log_base = 10
    return prs


def _saved_bytes(prs):
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


class DescribeChartToggleRoundTrip(object):
    def it_round_trips_a_doughnut_hole_size_deck(self):
        assert_round_trip(_doughnut_deck)

    def it_round_trips_a_smoothed_line_deck(self):
        assert_round_trip(_line_smooth_deck)

    def it_round_trips_a_log_value_axis_deck(self):
        assert_round_trip(_log_axis_deck)


class DescribeChartToggleSchemaValidity(object):
    def it_reads_back_the_hole_size_it_wrote(self):
        prs = _doughnut_deck()
        assert prs.slides[0].shapes[0].chart.plots[0].hole_size == 65

    def it_reads_back_the_smooth_flag_it_wrote(self):
        prs = _line_smooth_deck()
        assert prs.slides[0].shapes[0].chart.plots[0].smooth is True

    def it_reads_back_the_log_base_it_wrote(self):
        prs = _log_axis_deck()
        assert prs.slides[0].shapes[0].chart.value_axis.log_base == 10.0

    @pytest.mark.skipif(
        not schema_validation_available(), reason="schema unavailable"
    )
    def it_emits_schema_valid_xml_for_a_doughnut_hole_size(self):
        assert list(iter_schema_violations(_saved_bytes(_doughnut_deck()))) == []

    @pytest.mark.skipif(
        not schema_validation_available(), reason="schema unavailable"
    )
    def it_emits_schema_valid_xml_for_a_smoothed_line_chart(self):
        assert list(iter_schema_violations(_saved_bytes(_line_smooth_deck()))) == []

    @pytest.mark.skipif(
        not schema_validation_available(), reason="schema unavailable"
    )
    def it_emits_schema_valid_xml_for_a_log_value_axis(self):
        assert list(iter_schema_violations(_saved_bytes(_log_axis_deck()))) == []
