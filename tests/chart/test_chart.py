# pyright: reportPrivateUsage=false

"""Unit-test suite for `power_pptx.chart.chart` module."""

from __future__ import annotations

import pytest

from power_pptx.chart.axis import CategoryAxis, DateAxis, ValueAxis
from power_pptx.chart.chart import Chart, ChartTitle, Legend, _Plots
from power_pptx.chart.data import ChartData
from power_pptx.chart.plot import _BasePlot
from power_pptx.chart.series import SeriesCollection
from power_pptx.chart.xmlwriter import _BaseSeriesXmlRewriter
from power_pptx.dml.chtfmt import ChartFormat
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.parts.chart import ChartWorkbook
from power_pptx.text.text import Font

from ..unitutil.cxml import element, xml
from ..unitutil.mock import (
    call,
    class_mock,
    function_mock,
    instance_mock,
    property_mock,
)


def _make_chart_with_series(series_names):
    """Build a real `Chart` with N series for palette/integration tests."""
    from power_pptx import Presentation
    from power_pptx.chart.data import CategoryChartData
    from power_pptx.util import Inches

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    data = CategoryChartData()
    data.categories = ["A", "B", "C"]
    for name in series_names:
        data.add_series(name, (1, 2, 3))
    gframe = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(1),
        Inches(1),
        Inches(6),
        Inches(4),
        data,
    )
    return gframe.chart


class DescribeChart(object):
    """Unit-test suite for `power_pptx.chart.chart.Chart` objects."""

    def it_provides_access_to_its_font(self, font_fixture, Font_, font_):
        chartSpace, expected_xml = font_fixture
        Font_.return_value = font_
        chart = Chart(chartSpace, None)

        font = chart.font

        assert chartSpace.xml == expected_xml
        Font_.assert_called_once_with(chartSpace.xpath("./c:txPr/a:p/a:pPr/a:defRPr")[0])
        assert font is font_

    def it_knows_whether_it_has_a_title(self, has_title_get_fixture):
        chart, expected_value = has_title_get_fixture
        assert chart.has_title is expected_value

    def it_can_change_whether_it_has_a_title(self, has_title_set_fixture):
        chart, new_value, expected_xml = has_title_set_fixture
        chart.has_title = new_value
        assert chart._chartSpace.chart.xml == expected_xml

    def it_provides_access_to_the_chart_title(self, title_fixture):
        chart, expected_xml, ChartTitle_, chart_title_ = title_fixture

        chart_title = chart.chart_title

        assert chart.element.xpath("c:chart/c:title")[0].xml == expected_xml
        ChartTitle_.assert_called_once_with(chart.element.chart.title)
        assert chart_title is chart_title_

    def it_provides_access_to_the_category_axis(self, category_axis_fixture):
        chart, category_axis_, AxisCls_, xAx = category_axis_fixture
        category_axis = chart.category_axis
        AxisCls_.assert_called_once_with(xAx)
        assert category_axis is category_axis_

    def it_raises_when_no_category_axis(self, cat_ax_raise_fixture):
        chart = cat_ax_raise_fixture
        with pytest.raises(ValueError):
            chart.category_axis

    def it_provides_access_to_the_value_axis(self, val_ax_fixture):
        chart, ValueAxis_, valAx, value_axis_ = val_ax_fixture
        value_axis = chart.value_axis
        ValueAxis_.assert_called_once_with(valAx)
        assert value_axis is value_axis_

    def it_raises_when_no_value_axis(self, val_ax_raise_fixture):
        chart = val_ax_raise_fixture
        with pytest.raises(ValueError):
            chart.value_axis

    def it_provides_access_to_its_series(self, series_fixture):
        chart, SeriesCollection_, plotArea, series_ = series_fixture
        series = chart.series
        SeriesCollection_.assert_called_once_with(plotArea)
        assert series is series_

    def it_provides_access_to_its_plots(self, plots_fixture):
        chart, plots_, _Plots_, plotArea = plots_fixture
        plots = chart.plots
        _Plots_.assert_called_once_with(plotArea, chart)
        assert plots is plots_

    def it_knows_whether_it_has_a_legend(self, has_legend_get_fixture):
        chart, expected_value = has_legend_get_fixture
        assert chart.has_legend == expected_value

    def it_can_change_whether_it_has_a_legend(self, has_legend_set_fixture):
        chart, new_value, expected_xml = has_legend_set_fixture
        chart.has_legend = new_value
        assert chart._chartSpace.xml == expected_xml

    def it_provides_access_to_its_legend(self, legend_fixture):
        chart, Legend_, expected_calls, expected_value = legend_fixture
        legend = chart.legend
        assert Legend_.call_args_list == expected_calls
        assert legend is expected_value

    def it_knows_its_chart_type(self, request, PlotTypeInspector_, plot_):
        property_mock(request, Chart, "plots", return_value=[plot_])
        PlotTypeInspector_.chart_type.return_value = XL_CHART_TYPE.PIE
        chart = Chart(None, None)

        chart_type = chart.chart_type

        PlotTypeInspector_.chart_type.assert_called_once_with(plot_)
        assert chart_type == XL_CHART_TYPE.PIE

    def it_knows_its_style(self, style_get_fixture):
        chart, expected_value = style_get_fixture
        assert chart.chart_style == expected_value

    def it_can_change_its_style(self, style_set_fixture):
        chart, new_value, expected_xml = style_set_fixture
        chart.chart_style = new_value
        assert chart._chartSpace.xml == expected_xml

    def it_can_apply_a_named_palette(self):
        chart = _make_chart_with_series(("S1", "S2", "S3"))

        chart.apply_palette("modern")

        # First three colors of the "modern" palette
        from power_pptx.chart.palettes import CHART_PALETTES

        expected = CHART_PALETTES["modern"][:3]
        actual = [str(s.format.fill.fore_color.rgb) for s in chart.series]
        assert actual == [c.lstrip("#").upper() for c in expected]

    def it_wraps_palette_when_more_series_than_colors(self):
        chart = _make_chart_with_series(("S1", "S2", "S3"))

        chart.apply_palette(["#FF0000", "#00FF00"])

        actual = [str(s.format.fill.fore_color.rgb) for s in chart.series]
        assert actual == ["FF0000", "00FF00", "FF0000"]

    def it_accepts_mixed_color_likes_in_a_palette(self):
        from power_pptx.dml.color import RGBColor

        chart = _make_chart_with_series(("S1", "S2", "S3"))

        chart.apply_palette([RGBColor(0xAB, 0xCD, 0xEF), "BADA55", (0, 0, 255)])

        actual = [str(s.format.fill.fore_color.rgb) for s in chart.series]
        assert actual == ["ABCDEF", "BADA55", "0000FF"]

    def it_raises_for_unknown_palette_name(self):
        chart = _make_chart_with_series(("S1",))

        with pytest.raises(ValueError, match="unknown palette"):
            chart.apply_palette("not_a_real_palette")

    def it_raises_for_empty_palette(self):
        chart = _make_chart_with_series(("S1",))

        with pytest.raises(ValueError, match="at least one color"):
            chart.apply_palette([])

    def it_leaves_chart_style_untouched_when_applying_a_palette(self):
        chart = _make_chart_with_series(("S1", "S2"))
        chart.chart_style = 13

        chart.apply_palette("classic")

        assert chart.chart_style == 13

    def it_pins_chart_text_color_across_chart_legend_title_and_data_labels(self):
        # `text_color` is a write-only facade that walks every text-bearing
        # location on the chart so a dark deck doesn't have to thread the
        # same colour through chart.font, legend.font, title runs, and each
        # plot's data_labels.font by hand.
        from power_pptx.dml.color import RGBColor

        chart = _make_chart_with_series(("S1",))
        chart.has_title = True
        chart.chart_title.text_frame.text = "Q4"
        chart.has_legend = True
        chart.plots[0].has_data_labels = True

        chart.text_color = "#FFAA00"

        assert chart.font.color.rgb == RGBColor(0xFF, 0xAA, 0x00)
        assert chart.legend.font.color.rgb == RGBColor(0xFF, 0xAA, 0x00)
        assert chart.plots[0].data_labels.font.color.rgb == RGBColor(0xFF, 0xAA, 0x00)
        title_run_rgbs = [
            run.font.color.rgb
            for p in chart.chart_title.text_frame.paragraphs
            for run in p.runs
        ]
        assert all(rgb == RGBColor(0xFF, 0xAA, 0x00) for rgb in title_run_rgbs)

    def it_accepts_text_color_as_rgb_tuple_or_RGBColor(self):
        from power_pptx.dml.color import RGBColor

        chart = _make_chart_with_series(("S1",))
        chart.text_color = (10, 20, 30)
        assert chart.font.color.rgb == RGBColor(10, 20, 30)

        chart.text_color = RGBColor(0, 128, 255)
        assert chart.font.color.rgb == RGBColor(0, 128, 255)

    def it_rejects_invalid_text_color_types(self):
        chart = _make_chart_with_series(("S1",))
        with pytest.raises(TypeError):
            chart.text_color = 123  # type: ignore[assignment]

    def it_raises_on_text_color_read(self):
        chart = _make_chart_with_series(("S1",))
        with pytest.raises(AttributeError):
            chart.text_color  # noqa: B018

    def it_supports_gradient_fills_per_series_via_ChartFormat(self):
        """Per-series gradient fills are exposed through `ChartFormat.fill`,
        which is a regular `FillFormat` and so honors all gradient kinds."""
        from power_pptx.enum.dml import MSO_FILL_TYPE

        chart = _make_chart_with_series(("S1",))
        fill = chart.series[0].format.fill

        fill.gradient(kind="radial")

        assert fill.type == MSO_FILL_TYPE.GRADIENT
        assert fill.gradient_kind == "radial"
        assert len(fill.gradient_stops) == 2

    def it_supports_pattern_fills_per_series_via_ChartFormat(self):
        from power_pptx.enum.dml import MSO_FILL_TYPE, MSO_PATTERN_TYPE

        chart = _make_chart_with_series(("S1",))
        fill = chart.series[0].format.fill

        fill.patterned()
        fill.pattern = MSO_PATTERN_TYPE.WIDE_DOWNWARD_DIAGONAL

        assert fill.type == MSO_FILL_TYPE.PATTERNED
        assert fill.pattern == MSO_PATTERN_TYPE.WIDE_DOWNWARD_DIAGONAL

    def it_can_replace_the_chart_data(self, replace_fixture):
        (
            chart,
            chart_data_,
            SeriesXmlRewriterFactory_,
            chart_type,
            rewriter_,
            chartSpace,
            workbook_,
            xlsx_blob,
        ) = replace_fixture

        chart.replace_data(chart_data_)

        SeriesXmlRewriterFactory_.assert_called_once_with(chart_type, chart_data_)
        rewriter_.replace_series_data.assert_called_once_with(chartSpace)
        workbook_.update_from_xlsx_blob.assert_called_once_with(xlsx_blob)

    # fixtures -------------------------------------------------------

    @pytest.fixture(params=["c:catAx", "c:dateAx", "c:valAx"])
    def category_axis_fixture(self, request, CategoryAxis_, DateAxis_, ValueAxis_):
        ax_tag = request.param
        chartSpace_cxml = "c:chartSpace/c:chart/c:plotArea/%s" % ax_tag
        chartSpace = element(chartSpace_cxml)
        chart = Chart(chartSpace, None)
        AxisCls_ = {
            "c:catAx": CategoryAxis_,
            "c:dateAx": DateAxis_,
            "c:valAx": ValueAxis_,
        }[ax_tag]
        axis_ = AxisCls_.return_value
        xAx = chartSpace.xpath(".//%s" % ax_tag)[0]
        return chart, axis_, AxisCls_, xAx

    @pytest.fixture
    def cat_ax_raise_fixture(self):
        chart = Chart(element("c:chartSpace/c:chart/c:plotArea"), None)
        return chart

    @pytest.fixture(
        params=[
            (
                "c:chartSpace{a:b=c}",
                "c:chartSpace{a:b=c}/c:txPr/(a:bodyPr,a:lstStyle,a:p/a:pPr/a:defRPr" ")",
            ),
            ("c:chartSpace/c:txPr/a:p", "c:chartSpace/c:txPr/a:p/a:pPr/a:defRPr"),
            (
                "c:chartSpace/c:txPr/(a:bodyPr,a:lstStyle,a:p/a:pPr/a:defRPr)",
                "c:chartSpace/c:txPr/(a:bodyPr,a:lstStyle,a:p/a:pPr/a:defRPr)",
            ),
        ]
    )
    def font_fixture(self, request):
        chartSpace_cxml, expected_cxml = request.param
        chartSpace = element(chartSpace_cxml)
        expected_xml = xml(expected_cxml)
        return chartSpace, expected_xml

    @pytest.fixture(
        params=[
            ("c:chartSpace/c:chart", False),
            ("c:chartSpace/c:chart/c:legend", True),
        ]
    )
    def has_legend_get_fixture(self, request):
        chartSpace_cxml, expected_value = request.param
        chart = Chart(element(chartSpace_cxml), None)
        return chart, expected_value

    @pytest.fixture(params=[("c:chartSpace/c:chart", True, "c:chartSpace/c:chart/c:legend")])
    def has_legend_set_fixture(self, request):
        chartSpace_cxml, new_value, expected_chartSpace_cxml = request.param
        chart = Chart(element(chartSpace_cxml), None)
        expected_xml = xml(expected_chartSpace_cxml)
        return chart, new_value, expected_xml

    @pytest.fixture(
        params=[("c:chartSpace/c:chart", False), ("c:chartSpace/c:chart/c:title", True)]
    )
    def has_title_get_fixture(self, request):
        chartSpace_cxml, expected_value = request.param
        chart = Chart(element(chartSpace_cxml), None)
        return chart, expected_value

    @pytest.fixture(
        params=[
            ("c:chart", True, "c:chart/c:title/(c:layout,c:overlay{val=0})"),
            ("c:chart/c:title", True, "c:chart/c:title"),
            ("c:chart/c:title", False, "c:chart/c:autoTitleDeleted{val=1}"),
            ("c:chart", False, "c:chart/c:autoTitleDeleted{val=1}"),
        ]
    )
    def has_title_set_fixture(self, request):
        chart_cxml, new_value, expected_cxml = request.param
        chart = Chart(element("c:chartSpace/%s" % chart_cxml), None)
        expected_xml = xml(expected_cxml)
        return chart, new_value, expected_xml

    @pytest.fixture(
        params=[
            ("c:chartSpace/c:chart", False),
            ("c:chartSpace/c:chart/c:legend", True),
        ]
    )
    def legend_fixture(self, request, Legend_, legend_):
        chartSpace_cxml, has_legend = request.param
        chartSpace = element(chartSpace_cxml)
        chart = Chart(chartSpace, None)
        expected_value, expected_calls = None, []
        if has_legend:
            expected_value = legend_
            legend_elm = chartSpace.chart.legend
            expected_calls.append(call(legend_elm))
        return chart, Legend_, expected_calls, expected_value

    @pytest.fixture
    def plots_fixture(self, _Plots_, plots_):
        chartSpace = element("c:chartSpace/c:chart/c:plotArea")
        plotArea = chartSpace.xpath("./c:chart/c:plotArea")[0]
        chart = Chart(chartSpace, None)
        return chart, plots_, _Plots_, plotArea

    @pytest.fixture
    def replace_fixture(
        self,
        chart_data_,
        SeriesXmlRewriterFactory_,
        series_rewriter_,
        workbook_,
        workbook_prop_,
    ):
        chartSpace = element("c:chartSpace/c:chart/c:plotArea/c:pieChart")
        chart = Chart(chartSpace, None)
        chart_type = XL_CHART_TYPE.PIE
        xlsx_blob = "fooblob"
        chart_data_.xlsx_blob = xlsx_blob
        return (
            chart,
            chart_data_,
            SeriesXmlRewriterFactory_,
            chart_type,
            series_rewriter_,
            chartSpace,
            workbook_,
            xlsx_blob,
        )

    @pytest.fixture
    def series_fixture(self, SeriesCollection_, series_collection_):
        chartSpace = element("c:chartSpace/c:chart/c:plotArea")
        plotArea = chartSpace.xpath(".//c:plotArea")[0]
        chart = Chart(chartSpace, None)
        return chart, SeriesCollection_, plotArea, series_collection_

    @pytest.fixture(params=[("c:chartSpace/c:style{val=42}", 42), ("c:chartSpace", None)])
    def style_get_fixture(self, request):
        chartSpace_cxml, expected_value = request.param
        chart = Chart(element(chartSpace_cxml), None)
        return chart, expected_value

    @pytest.fixture(
        params=[
            ("c:chartSpace", 4, "c:chartSpace/c:style{val=4}"),
            ("c:chartSpace", None, "c:chartSpace"),
            ("c:chartSpace/c:style{val=4}", 2, "c:chartSpace/c:style{val=2}"),
            ("c:chartSpace/c:style{val=4}", None, "c:chartSpace"),
        ]
    )
    def style_set_fixture(self, request):
        chartSpace_cxml, new_value, expected_chartSpace_cxml = request.param
        chart = Chart(element(chartSpace_cxml), None)
        expected_xml = xml(expected_chartSpace_cxml)
        return chart, new_value, expected_xml

    @pytest.fixture(
        params=[
            ("c:chartSpace/c:chart", "c:title/(c:layout,c:overlay{val=0})"),
            ("c:chartSpace/c:chart/c:title/c:layout", "c:title/c:layout"),
        ]
    )
    def title_fixture(self, request, ChartTitle_, chart_title_):
        chartSpace_cxml, expected_cxml = request.param
        chart = Chart(element(chartSpace_cxml), None)
        expected_xml = xml(expected_cxml)
        return chart, expected_xml, ChartTitle_, chart_title_

    @pytest.fixture(
        params=[
            ("c:chartSpace/c:chart/c:plotArea/(c:catAx,c:valAx)", 0),
            ("c:chartSpace/c:chart/c:plotArea/(c:valAx,c:valAx)", 1),
        ]
    )
    def val_ax_fixture(self, request, ValueAxis_, value_axis_):
        chartSpace_xml, idx = request.param
        chartSpace = element(chartSpace_xml)
        chart = Chart(chartSpace, None)
        valAx = chartSpace.xpath(".//c:valAx")[idx]
        return chart, ValueAxis_, valAx, value_axis_

    @pytest.fixture
    def val_ax_raise_fixture(self):
        chart = Chart(element("c:chartSpace/c:chart/c:plotArea"), None)
        return chart

    # fixture components ---------------------------------------------

    @pytest.fixture
    def CategoryAxis_(self, request, category_axis_):
        return class_mock(request, "power_pptx.chart.chart.CategoryAxis", return_value=category_axis_)

    @pytest.fixture
    def category_axis_(self, request):
        return instance_mock(request, CategoryAxis)

    @pytest.fixture
    def chart_data_(self, request):
        return instance_mock(request, ChartData)

    @pytest.fixture
    def ChartTitle_(self, request, chart_title_):
        return class_mock(request, "power_pptx.chart.chart.ChartTitle", return_value=chart_title_)

    @pytest.fixture
    def chart_title_(self, request):
        return instance_mock(request, ChartTitle)

    @pytest.fixture
    def DateAxis_(self, request, date_axis_):
        return class_mock(request, "power_pptx.chart.chart.DateAxis", return_value=date_axis_)

    @pytest.fixture
    def date_axis_(self, request):
        return instance_mock(request, DateAxis)

    @pytest.fixture
    def Font_(self, request):
        return class_mock(request, "power_pptx.chart.chart.Font")

    @pytest.fixture
    def font_(self, request):
        return instance_mock(request, Font)

    @pytest.fixture
    def Legend_(self, request, legend_):
        return class_mock(request, "power_pptx.chart.chart.Legend", return_value=legend_)

    @pytest.fixture
    def legend_(self, request):
        return instance_mock(request, Legend)

    @pytest.fixture
    def PlotTypeInspector_(self, request):
        return class_mock(request, "power_pptx.chart.chart.PlotTypeInspector")

    @pytest.fixture
    def _Plots_(self, request, plots_):
        return class_mock(request, "power_pptx.chart.chart._Plots", return_value=plots_)

    @pytest.fixture
    def plot_(self, request):
        return instance_mock(request, _BasePlot)

    @pytest.fixture
    def plots_(self, request):
        return instance_mock(request, _Plots)

    @pytest.fixture
    def SeriesCollection_(self, request, series_collection_):
        return class_mock(
            request,
            "power_pptx.chart.chart.SeriesCollection",
            return_value=series_collection_,
        )

    @pytest.fixture
    def SeriesXmlRewriterFactory_(self, request, series_rewriter_):
        return function_mock(
            request,
            "power_pptx.chart.chart.SeriesXmlRewriterFactory",
            return_value=series_rewriter_,
            autospec=True,
        )

    @pytest.fixture
    def series_collection_(self, request):
        return instance_mock(request, SeriesCollection)

    @pytest.fixture
    def series_rewriter_(self, request):
        return instance_mock(request, _BaseSeriesXmlRewriter)

    @pytest.fixture
    def ValueAxis_(self, request, value_axis_):
        return class_mock(request, "power_pptx.chart.chart.ValueAxis", return_value=value_axis_)

    @pytest.fixture
    def value_axis_(self, request):
        return instance_mock(request, ValueAxis)

    @pytest.fixture
    def workbook_(self, request):
        return instance_mock(request, ChartWorkbook)

    @pytest.fixture
    def workbook_prop_(self, request, workbook_):
        return property_mock(request, Chart, "_workbook", return_value=workbook_)


class DescribeChartTitle(object):
    """Unit-test suite for `power_pptx.chart.chart.ChartTitle` objects."""

    def it_provides_access_to_its_format(self, format_fixture):
        chart_title, ChartFormat_, format_ = format_fixture
        format = chart_title.format
        ChartFormat_.assert_called_once_with(chart_title.element)
        assert format is format_

    def it_knows_whether_it_has_a_text_frame(self, has_tf_get_fixture):
        chart_title, expected_value = has_tf_get_fixture
        value = chart_title.has_text_frame
        assert value is expected_value

    def it_can_change_whether_it_has_a_text_frame(self, has_tf_set_fixture):
        chart_title, value, expected_xml = has_tf_set_fixture
        chart_title.has_text_frame = value
        assert chart_title._element.xml == expected_xml

    def it_provides_access_to_its_text_frame(self, text_frame_fixture):
        chart_title, TextFrame_, text_frame_ = text_frame_fixture
        text_frame = chart_title.text_frame
        TextFrame_.assert_called_once_with(chart_title._element.tx.rich, chart_title)
        assert text_frame is text_frame_

    # fixtures -------------------------------------------------------

    @pytest.fixture
    def format_fixture(self, request, ChartFormat_, format_):
        chart_title = ChartTitle(element("c:title"))
        return chart_title, ChartFormat_, format_

    @pytest.fixture(
        params=[
            ("c:title", False),
            ("c:title/c:tx", False),
            ("c:title/c:tx/c:strRef", False),
            ("c:title/c:tx/c:rich", True),
        ]
    )
    def has_tf_get_fixture(self, request):
        title_cxml, expected_value = request.param
        chart_title = ChartTitle(element(title_cxml))
        return chart_title, expected_value

    @pytest.fixture(
        params=[
            (
                "c:title{a:b=c}",
                True,
                "c:title{a:b=c}/c:tx/c:rich/(a:bodyPr,a:lstStyle,a:p/a:pPr/a:defRPr" ")",
            ),
            (
                "c:title{a:b=c}/c:tx",
                True,
                "c:title{a:b=c}/c:tx/c:rich/(a:bodyPr,a:lstStyle,a:p/a:pPr/a:defRPr" ")",
            ),
            (
                "c:title{a:b=c}/c:tx/c:strRef",
                True,
                "c:title{a:b=c}/c:tx/c:rich/(a:bodyPr,a:lstStyle,a:p/a:pPr/a:defRPr" ")",
            ),
            ("c:title/c:tx/c:rich", True, "c:title/c:tx/c:rich"),
            ("c:title", False, "c:title"),
            ("c:title/c:tx", False, "c:title"),
            ("c:title/c:tx/c:rich", False, "c:title"),
            ("c:title/c:tx/c:strRef", False, "c:title"),
        ]
    )
    def has_tf_set_fixture(self, request):
        title_cxml, value, expected_cxml = request.param
        chart_title = ChartTitle(element(title_cxml))
        expected_xml = xml(expected_cxml)
        return chart_title, value, expected_xml

    @pytest.fixture
    def text_frame_fixture(self, request, TextFrame_):
        chart_title = ChartTitle(element("c:title"))
        text_frame_ = TextFrame_.return_value
        return chart_title, TextFrame_, text_frame_

    # fixture components ---------------------------------------------

    @pytest.fixture
    def ChartFormat_(self, request, format_):
        return class_mock(request, "power_pptx.chart.chart.ChartFormat", return_value=format_)

    @pytest.fixture
    def format_(self, request):
        return instance_mock(request, ChartFormat)

    @pytest.fixture
    def TextFrame_(self, request):
        return class_mock(request, "power_pptx.chart.chart.TextFrame")


class Describe_Plots(object):
    """Unit-test suite for `power_pptx.chart.chart._Plots` objects."""

    def it_supports_indexed_access(self, getitem_fixture):
        plots, idx, PlotFactory_, plot_elm, chart_, plot_ = getitem_fixture
        plot = plots[idx]
        PlotFactory_.assert_called_once_with(plot_elm, chart_)
        assert plot is plot_

    def it_supports_len(self, len_fixture):
        plots, expected_len = len_fixture
        assert len(plots) == expected_len

    # fixtures -------------------------------------------------------

    @pytest.fixture(
        params=[
            ("c:plotArea/c:barChart", 0),
            ("c:plotArea/(c:radarChart,c:barChart)", 1),
        ]
    )
    def getitem_fixture(self, request, PlotFactory_, chart_, plot_):
        plotArea_cxml, idx = request.param
        plotArea = element(plotArea_cxml)
        plot_elm = plotArea[idx]
        plots = _Plots(plotArea, chart_)
        return plots, idx, PlotFactory_, plot_elm, chart_, plot_

    @pytest.fixture(
        params=[
            ("c:plotArea", 0),
            ("c:plotArea/c:barChart", 1),
            ("c:plotArea/(c:barChart,c:lineChart)", 2),
        ]
    )
    def len_fixture(self, request):
        plotArea_cxml, expected_len = request.param
        plots = _Plots(element(plotArea_cxml), None)
        return plots, expected_len

    # fixture components ---------------------------------------------

    @pytest.fixture
    def chart_(self, request):
        return instance_mock(request, Chart)

    @pytest.fixture
    def PlotFactory_(self, request, plot_):
        return function_mock(request, "power_pptx.chart.chart.PlotFactory", return_value=plot_)

    @pytest.fixture
    def plot_(self, request):
        return instance_mock(request, _BasePlot)
