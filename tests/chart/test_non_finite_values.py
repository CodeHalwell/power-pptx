"""Chart data holding NaN (a gap, like `None`) or +/-infinity (an error), end to end.

`None` has always meant "no value for this point". NaN, which is what pandas and numpy use for
a missing value, used to be written as ``<c:v>nan</c:v>`` and then crash deep inside
XlsxWriter; it must produce exactly what `None` produces, for every kind of chart data.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from lxml import etree

from power_pptx import Presentation
from power_pptx.chart.data import BubbleChartData, CategoryChartData, XyChartData
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.util import Inches

from ..schema.oxml_schema_validator import assert_schema_valid, schema_validation_available

NAN = float("nan")
INF = float("inf")

_C = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _category_data(values):
    data = CategoryChartData()
    data.categories = ["A", "B", "C"]
    data.add_series("S", values)
    return data


def _xy_data(points):
    data = XyChartData()
    series = data.add_series("S")
    for x, y in points:
        series.add_data_point(x, y)
    return data


def _bubble_data(points):
    data = BubbleChartData()
    series = data.add_series("S")
    for x, y, size in points:
        series.add_data_point(x, y, size)
    return data


def _worksheet(xlsx_blob):
    """The `xl/worksheets/sheet1.xml` of an embedded workbook, as text."""
    with zipfile.ZipFile(io.BytesIO(xlsx_blob)) as zf:
        return zf.read("xl/worksheets/sheet1.xml").decode("utf-8")


def _point_indexes(chart_xml, container):
    """The `idx` of each `c:pt` under the `c:<container>` element(s) of the chart XML."""
    root = etree.fromstring(chart_xml)
    return [pt.get("idx") for el in root.iter(_C + container) for pt in el.iter(_C + "pt")]


class DescribeANaNInCategoryChartData:
    @pytest.mark.parametrize(
        "chart_type",
        [
            XL_CHART_TYPE.COLUMN_CLUSTERED,
            XL_CHART_TYPE.BAR_CLUSTERED,
            XL_CHART_TYPE.LINE_MARKERS,
            XL_CHART_TYPE.AREA,
            XL_CHART_TYPE.PIE,
            XL_CHART_TYPE.RADAR,
        ],
    )
    def it_is_written_exactly_like_None(self, chart_type):
        with_nan = _category_data([1.0, NAN, 3.0])
        with_none = _category_data([1.0, None, 3.0])

        assert with_nan.xml_bytes(chart_type) == with_none.xml_bytes(chart_type)

    def it_leaves_no_point_for_the_gap_but_keeps_the_point_count(self):
        xml = _category_data([1.0, NAN, 3.0]).xml_bytes(XL_CHART_TYPE.COLUMN_CLUSTERED)

        root = etree.fromstring(xml)
        (val,) = root.iter(_C + "val")
        assert val.find(f"{_C}numRef/{_C}numCache/{_C}ptCount").get("val") == "3"
        assert [pt.get("idx") for pt in val.iter(_C + "pt")] == ["0", "2"]
        assert b"nan" not in xml.lower()

    def it_is_written_to_the_workbook_as_a_blank_cell(self):
        with_nan = _category_data([1.0, NAN, 3.0]).xlsx_blob
        with_none = _category_data([1.0, None, 3.0]).xlsx_blob

        sheet = _worksheet(with_nan)
        assert sheet == _worksheet(with_none)
        cell = etree.fromstring(sheet.encode("utf-8")).find(f".//{_S}c[@r='B3']")
        assert cell is not None
        assert cell.find(_S + "v") is None

    def it_can_be_an_every_value_of_a_series(self):
        data = _category_data([NAN, NAN, NAN])

        assert _point_indexes(data.xml_bytes(XL_CHART_TYPE.COLUMN_CLUSTERED), "val") == []
        assert _worksheet(data.xlsx_blob) == _worksheet(_category_data([None] * 3).xlsx_blob)

    def it_builds_a_chart_on_a_slide(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        chart = slide.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED,
            Inches(1),
            Inches(1),
            Inches(6),
            Inches(4),
            _category_data([1.0, NAN, 3.0]),
        ).chart

        assert list(chart.plots[0].series[0].values) == [1.0, None, 3.0]

    def it_replaces_the_data_of_an_existing_chart(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        chart = slide.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED,
            Inches(1),
            Inches(1),
            Inches(6),
            Inches(4),
            _category_data([1.0, 2.0, 3.0]),
        ).chart

        chart.replace_data(_category_data([NAN, 2.0, NAN]))

        assert list(chart.plots[0].series[0].values) == [None, 2.0, None]

    @pytest.mark.skipif(not schema_validation_available(), reason="XSD schemas unavailable")
    def it_leaves_a_deck_that_validates_against_the_schema(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.shapes.add_chart(
            XL_CHART_TYPE.LINE_MARKERS,
            Inches(1),
            Inches(1),
            Inches(6),
            Inches(4),
            _category_data([1.0, NAN, 3.0]),
        )
        buf = io.BytesIO()
        prs.save(buf)

        assert_schema_valid(buf.getvalue())

    def it_accepts_the_missing_values_of_a_pandas_series(self):
        np = pytest.importorskip("numpy")
        pd = pytest.importorskip("pandas")
        data = CategoryChartData()
        data.categories = ["A", "B", "C"]

        data.add_series("S", pd.Series([1.0, np.nan, 3.0]))

        xml = data.xml_bytes(XL_CHART_TYPE.COLUMN_CLUSTERED)
        assert _point_indexes(xml, "val") == ["0", "2"]
        assert _worksheet(data.xlsx_blob) == _worksheet(_category_data([1.0, None, 3.0]).xlsx_blob)


class DescribeANaNInXyChartData:
    def it_is_written_exactly_like_None_for_a_missing_y(self):
        with_nan = _xy_data([(1, 10), (2, NAN), (3, 30)])
        with_none = _xy_data([(1, 10), (2, None), (3, 30)])

        xml = with_nan.xml_bytes(XL_CHART_TYPE.XY_SCATTER)

        assert xml == with_none.xml_bytes(XL_CHART_TYPE.XY_SCATTER)
        assert _point_indexes(xml, "xVal") == ["0", "1", "2"]
        assert _point_indexes(xml, "yVal") == ["0", "2"]

    def it_is_written_exactly_like_None_for_a_missing_x(self):
        with_nan = _xy_data([(1, 10), (NAN, 20), (3, 30)])
        with_none = _xy_data([(1, 10), (None, 20), (3, 30)])

        xml = with_nan.xml_bytes(XL_CHART_TYPE.XY_SCATTER)

        assert xml == with_none.xml_bytes(XL_CHART_TYPE.XY_SCATTER)
        assert _point_indexes(xml, "xVal") == ["0", "2"]

    def it_is_written_to_the_workbook_as_blank_cells(self):
        with_nan = _xy_data([(1, 10), (NAN, NAN), (3, 30)]).xlsx_blob
        with_none = _xy_data([(1, 10), (None, None), (3, 30)]).xlsx_blob

        assert _worksheet(with_nan) == _worksheet(with_none)


class DescribeANaNInBubbleChartData:
    def it_is_written_exactly_like_None_in_every_dimension(self):
        with_nan = _bubble_data([(1, 10, 5), (NAN, NAN, NAN), (3, 30, 7)])
        with_none = _bubble_data([(1, 10, 5), (None, None, None), (3, 30, 7)])

        xml = with_nan.xml_bytes(XL_CHART_TYPE.BUBBLE)

        assert xml == with_none.xml_bytes(XL_CHART_TYPE.BUBBLE)
        assert _point_indexes(xml, "bubbleSize") == ["0", "2"]

    def it_is_written_to_the_workbook_as_blank_cells(self):
        with_nan = _bubble_data([(1, 10, 5), (NAN, 20, NAN)]).xlsx_blob
        with_none = _bubble_data([(1, 10, 5), (None, 20, None)]).xlsx_blob

        assert _worksheet(with_nan) == _worksheet(with_none)


class DescribeInfinityInChartData:
    """Infinity cannot be plotted and is not a gap, so it is an error that says where."""

    @pytest.mark.parametrize("bad", [INF, -INF])
    def it_is_refused_for_category_data_naming_series_and_point(self, bad):
        data = _category_data([1.0, 2.0, bad])

        with pytest.raises(ValueError, match=r"series 'S'.*point index 2.*value"):
            data.xml_bytes(XL_CHART_TYPE.COLUMN_CLUSTERED)
        with pytest.raises(ValueError, match=r"series 'S'.*point index 2.*value"):
            _ = data.xlsx_blob

    def it_is_refused_when_adding_the_chart(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        with pytest.raises(ValueError, match=r"series 'S'.*point index 1"):
            slide.shapes.add_chart(
                XL_CHART_TYPE.LINE,
                Inches(1),
                Inches(1),
                Inches(6),
                Inches(4),
                _category_data([1.0, INF, 3.0]),
            )

    def it_is_refused_when_replacing_chart_data(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        chart = slide.shapes.add_chart(
            XL_CHART_TYPE.LINE,
            Inches(1),
            Inches(1),
            Inches(6),
            Inches(4),
            _category_data([1.0, 2.0, 3.0]),
        ).chart

        with pytest.raises(ValueError, match=r"series 'S'.*point index 0"):
            chart.replace_data(_category_data([INF, 2.0, 3.0]))

    @pytest.mark.parametrize(
        ("points", "kind"),
        [
            ([(1, 10), (INF, 20)], "X value"),
            ([(1, 10), (2, -INF)], "Y value"),
        ],
    )
    def it_is_refused_for_xy_data_naming_which_value(self, points, kind):
        data = _xy_data(points)

        with pytest.raises(ValueError, match=rf"series 'S'.*point index 1.*{kind}"):
            data.xml_bytes(XL_CHART_TYPE.XY_SCATTER)
        with pytest.raises(ValueError, match=rf"series 'S'.*point index 1.*{kind}"):
            _ = data.xlsx_blob

    @pytest.mark.parametrize(
        ("points", "kind"),
        [
            ([(1, 10, 5), (INF, 20, 5)], "X value"),
            ([(1, 10, 5), (2, INF, 5)], "Y value"),
            ([(1, 10, 5), (2, 20, INF)], "bubble size"),
        ],
    )
    def it_is_refused_for_bubble_data_naming_which_value(self, points, kind):
        data = _bubble_data(points)

        with pytest.raises(ValueError, match=rf"series 'S'.*point index 1.*{kind}"):
            data.xml_bytes(XL_CHART_TYPE.BUBBLE)
        with pytest.raises(ValueError, match=rf"series 'S'.*point index 1.*{kind}"):
            _ = data.xlsx_blob

    def it_names_the_right_series_of_several(self):
        data = CategoryChartData()
        data.categories = ["A", "B"]
        data.add_series("Fine", [1.0, 2.0])
        data.add_series("Broken", [1.0, INF])

        with pytest.raises(ValueError, match=r"series 'Broken'.*point index 1"):
            data.xml_bytes(XL_CHART_TYPE.COLUMN_CLUSTERED)
