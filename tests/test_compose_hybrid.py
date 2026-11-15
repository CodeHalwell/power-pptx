"""Unit tests for the hybrid HTML annotation contract (no browser needed).

The records below have the shape ``html_layers.js`` produces, so the native
table / chart mapping and its validation run without Chromium.
"""

from __future__ import annotations

import re

import pytest

from power_pptx import Presentation
from power_pptx.compose._hybrid import add_layers, prepare_layers
from power_pptx.design._html import HtmlCapture
from power_pptx.dml.color import RGBColor
from power_pptx.enum.dml import MSO_FILL
from power_pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from power_pptx.util import Emu

# A 1280 x 720 px canvas on a 16:9 slide: one CSS pixel is 9525 EMU.
_PX = 9525


def _style(**overrides):
    style = {
        "font": "BrandFont",
        "size": 20.0,
        "weight": "400",
        "italic": False,
        "color": "rgb(23, 35, 52)",
        "align": "left",
        "lineHeight": 24.0,
        "underline": False,
        "opacity": 1.0,
        "padding": [0.0, 0.0, 0.0, 0.0],
        "border": [0.0, 0.0, 0.0, 0.0],
        "borderColors": ["rgb(0, 0, 0)"] * 4,
        "verticalAlign": "baseline",
    }
    style.update(overrides)
    return style


def _cell(text, width, *, colspan=1, rowspan=1, fill="rgba(0, 0, 0, 0)", **style):
    return {
        "text": text,
        "colspan": colspan,
        "rowspan": rowspan,
        "style": _style(**style),
        "fill": fill,
        "bounds": [0.0, 0.0, float(width), 40.0],
        "native_font": "Mapped Sans",
    }


def _table(rows, row_heights, width=500.0):
    return {
        "kind": "table",
        "name": "table",
        "bounds": [0.0, 0.0, width, float(sum(row_heights))],
        "style": _style(),
        "native_font": "Mapped Sans",
        "rows": rows,
        "rowHeights": row_heights,
    }


def _chart(spec):
    return {
        "kind": "chart",
        "name": "chart",
        "bounds": [0.0, 0.0, 600.0, 300.0],
        "style": _style(),
        "native_font": "Mapped Sans",
        "chart": spec,
    }


def _capture(*elements, size=(1280.0, 720.0)):
    return HtmlCapture(b"", "", "", elements=tuple(elements), size=size)


def _slide_with(*elements):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(1280 * _PX), Emu(720 * _PX)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_layers(slide, _capture(*elements), slide_width=prs.slide_width,
               slide_height=prs.slide_height)
    return slide


def _prepare(*elements, size=(1280.0, 720.0)):
    prepare_layers(_capture(*elements, size=size), font_map={}, strict_fonts=False)


_SERIES = [{"name": "Revenue", "values": [1, 2]}]


class DescribePrepareLayers:
    def it_requires_canvas_dimensions(self):
        with pytest.raises(ValueError, match="^Hybrid capture has no canvas dimensions$"):
            _prepare(_chart({"categories": ["A", "B"], "series": _SERIES}), size=None)

    def it_skips_captured_regions(self):
        _prepare({"kind": "capture", "name": "art"})

    @pytest.mark.parametrize("rows", [[], [[], []]])
    def it_rejects_an_empty_table(self, rows):
        with pytest.raises(ValueError, match="^Annotated native table cannot be empty$"):
            _prepare(_table(rows, [40.0] * len(rows)))

    def it_resolves_a_native_font_for_the_region_its_runs_and_its_cells(self):
        text = {
            "kind": "text",
            "style": _style(),
            "runs": [{"text": "Hi", "line": 0, "style": _style(font="Other")}],
        }
        table = _table([[_cell("a", 100.0)]], [40.0])
        prepare_layers(
            _capture(text, table),
            font_map={"brandfont": "Mapped Sans", "other": "Mapped Serif"},
            strict_fonts=False,
        )
        assert text["native_font"] == "Mapped Sans"
        assert text["runs"][0]["native_font"] == "Mapped Serif"
        assert table["native_font"] == "Mapped Sans"
        assert table["rows"][0][0]["native_font"] == "Mapped Sans"

    def it_checks_the_colour_of_each_run_and_cell_fill(self):
        text = {
            "kind": "text",
            "style": _style(),
            "runs": [{"text": "Hi", "line": 0, "style": _style(color="hsl(0, 0%, 0%)")}],
        }
        with pytest.raises(ValueError, match="Unsupported native CSS color 'hsl"):
            _prepare(text)
        table = _table([[_cell("a", 100.0, fill="hsl(0, 0%, 0%)")]], [40.0])
        with pytest.raises(ValueError, match="Unsupported native CSS color 'hsl"):
            _prepare(table)


class DescribeChartSpecValidation:
    @pytest.mark.parametrize(
        ("spec", "message"),
        [
            (["column"], "data-pptx-chart must be a JSON object"),
            (
                {"categories": ["A"], "series": _SERIES, "stack": 1, "axis": 2},
                "Unknown chart options: axis, stack",
            ),
            (
                {"type": "radar", "categories": ["A"], "series": _SERIES},
                "Native HTML chart type must be column, bar, line, area, pie, or doughnut",
            ),
            (
                {"categories": [], "series": _SERIES},
                "Native chart requires non-empty categories and series lists",
            ),
            (
                {"categories": "AB", "series": _SERIES},
                "Native chart requires non-empty categories and series lists",
            ),
            (
                {"categories": ["A", "B"], "series": []},
                "Native chart requires non-empty categories and series lists",
            ),
            (
                {"categories": ["A", "B"], "series": {"name": "x"}},
                "Native chart requires non-empty categories and series lists",
            ),
            ({"categories": ["A", "B"], "series": [7]}, "Each chart series needs name and values"),
            (
                {"categories": ["A", "B"], "series": [{"values": [1, 2]}]},
                "Each chart series needs name and values",
            ),
            (
                {"categories": ["A", "B"], "series": [{"name": "x", "values": [1, 2], "z": 0}]},
                "Each chart series needs name and values",
            ),
            (
                {"categories": ["A", "B"], "series": [{"name": "x"}]},
                "Chart series values must match the category count",
            ),
            (
                {"categories": ["A", "B"], "series": [{"name": "x", "values": [1]}]},
                "Chart series values must match the category count",
            ),
            (
                {"categories": ["A", "B"], "series": [{"name": "x", "values": [1, True]}]},
                "Chart values must be finite numbers or null",
            ),
            (
                {"categories": ["A", "B"], "series": [{"name": "x", "values": [1, "2"]}]},
                "Chart values must be finite numbers or null",
            ),
            (
                {"categories": ["A", "B"], "series": [{"name": "x", "values": [1, float("inf")]}]},
                "Chart values must be finite numbers or null",
            ),
            (
                {"categories": ["A", "B"], "series": _SERIES, "colors": []},
                "Chart colors must be a non-empty list",
            ),
            (
                {"categories": ["A", "B"], "series": _SERIES, "colors": "#6554E8"},
                "Chart colors must be a non-empty list",
            ),
        ],
    )
    def it_rejects_a_malformed_chart_spec(self, spec, message):
        with pytest.raises(ValueError, match=f"^{re.escape(message)}$"):
            _prepare(_chart(spec))

    def it_checks_each_chart_colour(self):
        spec = {"categories": ["A", "B"], "series": _SERIES, "colors": ["#6554E8", "nope"]}
        with pytest.raises(ValueError, match="'nope'"):
            _prepare(_chart(spec))

    def it_accepts_null_values_and_defaults_to_a_column_chart(self):
        series = [{"name": "x", "values": [None, 2.5]}, {"name": "y", "values": [1, 0]}]
        _prepare(_chart({"categories": ["A", "B"], "series": series, "colors": ["#6554E8"]}))


class DescribeNativeChart:
    def it_draws_the_title_legend_and_colours_the_spec_asks_for(self):
        spec = {
            "type": "bar",
            "categories": ["A", "B"],
            "series": _SERIES,
            "title": "Revenue",
            "legend": True,
            "colors": ["#6554E8"],
        }
        slide = _slide_with(_chart(spec))
        chart = slide.shapes[0].chart
        assert chart.has_title
        assert chart.chart_title.text_frame.text == "Revenue"
        assert chart.has_legend
        assert list(chart.series[0].values) == [1, 2]


class DescribeNativeTable:
    def it_places_cells_beside_a_rowspan_from_the_row_above(self):
        rows = [
            [_cell("tall", 100.0, rowspan=2), _cell("b", 200.0), _cell("c", 200.0)],
            [_cell("d", 200.0), _cell("e", 200.0)],
        ]
        table = _slide_with(_table(rows, [40.0, 40.0])).shapes[0].table
        assert table.cell(0, 0).is_merge_origin
        assert table.cell(0, 0).span_height == 2
        assert table.cell(1, 1).text == "d"
        assert table.cell(1, 2).text == "e"

    def it_rejects_a_rowspan_beyond_the_last_row(self):
        rows = [[_cell("a", 100.0)], [_cell("b", 100.0, rowspan=2)]]
        with pytest.raises(ValueError, match="^Table rowspan extends beyond its rows$"):
            _slide_with(_table(rows, [40.0, 40.0]))

    def it_sizes_columns_and_rows_in_proportion_to_the_browser_layout(self):
        # Columns 0 and 1 hold only a two-column cell, so they share its width.
        rows = [
            [_cell("wide", 400.0, colspan=2), _cell("c", 100.0)],
            [_cell("wider", 400.0, colspan=2), _cell("d", 100.0)],
        ]
        table = _slide_with(_table(rows, [100.0, 200.0])).shapes[0].table
        assert [c.width for c in table.columns] == [200 * _PX, 200 * _PX, 100 * _PX]
        assert [r.height for r in table.rows] == [100 * _PX, 200 * _PX]

    def it_gives_a_shared_edge_the_stronger_of_the_two_borders(self):
        red, blue = "rgb(255, 0, 0)", "rgba(0, 0, 255, 0.5)"
        rows = [
            [
                _cell("left", 100.0, border=[0.0, 3.0, 0.0, 0.0], borderColors=[red] * 4),
                _cell("right", 100.0, border=[0.0, 0.0, 2.0, 1.0], borderColors=[blue] * 4),
            ]
        ]
        table = _slide_with(_table(rows, [40.0], width=200.0)).shapes[0].table
        left, right = table.cell(0, 0), table.cell(0, 1)
        for line in (left.borders.right, right.borders.left):
            assert line.width == 3 * _PX
            assert line.color.rgb == RGBColor(0xFF, 0x00, 0x00)
        assert right.borders.bottom.width == 2 * _PX
        assert right.borders.bottom.color.rgb == RGBColor(0x00, 0x00, 0xFF)
        assert right.borders.bottom.color.alpha == pytest.approx(0.5)
        assert left.borders.top.fill.type == MSO_FILL.BACKGROUND

    def it_maps_css_alignment_and_fills_onto_the_cell(self):
        rows = [
            [
                _cell("a", 100.0, align="center", verticalAlign="middle",
                      fill="rgba(255, 0, 0, 0.5)"),
                _cell("b", 100.0, align="start", verticalAlign="baseline",
                      fill="transparent", weight="700", italic=True),
            ]
        ]
        table = _slide_with(_table(rows, [40.0], width=200.0)).shapes[0].table
        filled, plain = table.cell(0, 0), table.cell(0, 1)
        assert filled.text_frame.paragraphs[0].alignment == PP_ALIGN.CENTER
        assert filled.vertical_anchor == MSO_ANCHOR.MIDDLE
        assert filled.fill.type == MSO_FILL.SOLID
        assert filled.fill.fore_color.rgb == RGBColor(0xFF, 0x00, 0x00)
        assert filled.fill.fore_color.alpha == pytest.approx(0.5)
        assert plain.text_frame.paragraphs[0].alignment == PP_ALIGN.LEFT
        assert plain.vertical_anchor == MSO_ANCHOR.TOP
        assert plain.fill.type == MSO_FILL.BACKGROUND
        run = plain.text_frame.paragraphs[0].runs[0]
        assert run.font.bold
        assert run.font.italic
        assert run.font.name == "Mapped Sans"
