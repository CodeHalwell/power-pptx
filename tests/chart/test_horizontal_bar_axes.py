"""Where the value axis of a horizontal bar chart sits once its categories are reversed.

`add_chart` reverses the category axis of horizontal bar charts so that the first category is
at the top. A reversed category axis moves the value axis to the other end of it, which is the
top, unless the value axis crosses it at the *maximum* category. Without that, the value-axis
labels were drawn along the top of the plot (checked by rendering a default BAR_CLUSTERED chart
in LibreOffice).

`c:crosses` inside an axis element says where *that* axis crosses the other one. So it is the
`c:valAx` that must carry ``max``, whereas ``chart.value_axis.crosses`` (the python-pptx style
property) writes to the *other* axis' element, the `c:catAx`.
"""

from __future__ import annotations

import io

import pytest
from lxml import etree

from power_pptx import Presentation
from power_pptx.chart.data import CategoryChartData
from power_pptx.enum.chart import XL_AXIS_CROSSES, XL_CHART_TYPE
from power_pptx.util import Inches

from ..schema.oxml_schema_validator import assert_schema_valid, schema_validation_available

HORIZONTAL_BAR_TYPES = [
    XL_CHART_TYPE.BAR_CLUSTERED,
    XL_CHART_TYPE.BAR_STACKED,
    XL_CHART_TYPE.BAR_STACKED_100,
]


def _chart(chart_type, categories=("A", "B", "C")):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    data = CategoryChartData()
    data.categories = list(categories)
    data.add_series("S", [3, 2, 1][: len(categories)])
    return slide.shapes.add_chart(chart_type, Inches(1), Inches(1), Inches(6), Inches(4), data), prs


def _crosses(chart, axis_tag):
    """The ``val`` of the `c:crosses` child of the first `c:<axis_tag>`, or |None|."""
    values = chart._chartSpace.xpath(f"//c:{axis_tag}/c:crosses/@val")
    return values[0] if values else None


def _orientation(chart, axis_tag):
    values = chart._chartSpace.xpath(f"//c:{axis_tag}/c:scaling/c:orientation/@val")
    return values[0] if values else None


class DescribeHorizontalBarChartAxes:
    @pytest.mark.parametrize("chart_type", HORIZONTAL_BAR_TYPES)
    def it_reads_top_to_bottom_with_the_value_axis_along_the_bottom(self, chart_type):
        chart = _chart(chart_type)[0].chart

        # -- first category on top ... --
        assert chart.category_axis.reverse_order is True
        # -- ... and the value axis crossing at the maximum category, i.e. at the bottom --
        assert _crosses(chart, "valAx") == "max"

    @pytest.mark.parametrize("chart_type", HORIZONTAL_BAR_TYPES)
    def it_leaves_the_category_axis_crossing_the_value_axis_where_it_was(self, chart_type):
        # -- `c:catAx/c:crosses` places the category axis along the value axis; reaching for
        # -- `chart.value_axis.crosses` would move it to the far end of the value axis instead
        chart = _chart(chart_type)[0].chart

        assert _crosses(chart, "catAx") == "autoZero"

    def it_exposes_the_crossing_through_the_category_axis(self):
        chart = _chart(XL_CHART_TYPE.BAR_CLUSTERED)[0].chart

        assert chart.category_axis.crosses == XL_AXIS_CROSSES.MAXIMUM
        assert chart.value_axis.crosses == XL_AXIS_CROSSES.AUTOMATIC

    @pytest.mark.parametrize(
        "chart_type",
        [
            XL_CHART_TYPE.COLUMN_CLUSTERED,
            XL_CHART_TYPE.COLUMN_STACKED,
            XL_CHART_TYPE.LINE,
            XL_CHART_TYPE.AREA,
        ],
    )
    def it_does_not_touch_the_axes_of_charts_that_are_not_horizontal_bars(self, chart_type):
        chart = _chart(chart_type)[0].chart

        assert chart.category_axis.reverse_order is False
        assert _crosses(chart, "valAx") == "autoZero"
        assert _crosses(chart, "catAx") == "autoZero"

    def it_restores_the_legacy_layout_when_the_reversal_is_turned_off(self):
        # -- the documented way back to the old bottom-up order must still put the value axis
        # -- along the bottom, which for an un-reversed axis means crossing at the origin
        chart = _chart(XL_CHART_TYPE.BAR_CLUSTERED)[0].chart

        chart.category_axis.reverse_order = False

        assert _orientation(chart, "catAx") in (None, "minMax")
        assert _crosses(chart, "valAx") == "autoZero"
        assert _crosses(chart, "catAx") == "autoZero"

    def it_can_be_reversed_again_and_keeps_the_value_axis_at_the_bottom_when_asked(self):
        chart = _chart(XL_CHART_TYPE.BAR_CLUSTERED)[0].chart
        chart.category_axis.reverse_order = False

        chart.category_axis.reverse_order = True
        chart.category_axis.crosses = XL_AXIS_CROSSES.MAXIMUM

        assert _orientation(chart, "catAx") == "maxMin"
        assert _crosses(chart, "valAx") == "max"

    def it_does_not_undo_a_crossing_the_caller_chose_other_than_the_maximum(self):
        chart = _chart(XL_CHART_TYPE.BAR_CLUSTERED)[0].chart
        chart.category_axis.crosses = XL_AXIS_CROSSES.MINIMUM

        chart.category_axis.reverse_order = False

        assert _crosses(chart, "valAx") == "min"

    def it_survives_a_save_and_reopen(self):
        _, prs = _chart(XL_CHART_TYPE.BAR_CLUSTERED)
        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)

        chart = Presentation(buf).slides[0].shapes[0].chart

        assert chart.category_axis.reverse_order is True
        assert chart.category_axis.crosses == XL_AXIS_CROSSES.MAXIMUM

    def it_works_for_a_bar_chart_with_date_categories(self):
        import datetime

        categories = [datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)]
        chart = _chart(XL_CHART_TYPE.BAR_CLUSTERED, categories=categories)[0].chart

        assert chart._chartSpace.xpath("//c:dateAx")
        assert chart.category_axis.reverse_order is True
        assert _crosses(chart, "valAx") == "max"

    @pytest.mark.skipif(not schema_validation_available(), reason="XSD schemas unavailable")
    @pytest.mark.parametrize("chart_type", HORIZONTAL_BAR_TYPES)
    def it_validates_against_the_chart_schema(self, chart_type):
        prs = _chart(chart_type)[1]
        buf = io.BytesIO()
        prs.save(buf)

        assert_schema_valid(buf.getvalue())

    def it_orders_the_crosses_element_where_the_schema_wants_it(self):
        chart = _chart(XL_CHART_TYPE.BAR_CLUSTERED)[0].chart

        (valAx,) = chart._chartSpace.xpath("//c:valAx")
        tags = [etree.QName(child).localname for child in valAx]

        assert tags.count("crosses") == 1
        assert "crossesAt" not in tags
        assert tags.index("crosses") == tags.index("crossAx") + 1
