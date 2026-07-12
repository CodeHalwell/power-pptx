"""Integration tests for ``data_labels.collision_strategy``.

The feature ties three things together — font size, gap width, and
chart-shape introspection — so the cleanest test path is to build a
real chart, set the strategy, and inspect the resulting plot
element. Heavy mocking would mean re-implementing the heuristic in
test code.
"""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx.chart.data import CategoryChartData
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.oxml.ns import qn
from power_pptx.util import Inches, Pt


def _make_chart(*, categories, series_count, chart_type=XL_CHART_TYPE.COLUMN_CLUSTERED):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    data = CategoryChartData()
    data.categories = list(categories)
    for i in range(series_count):
        data.add_series(
            f"S{i + 1}", tuple(float(j + 1) for j in range(len(categories)))
        )
    gframe = slide.shapes.add_chart(
        chart_type,
        Inches(1), Inches(1), Inches(6), Inches(4),
        data,
    )
    return gframe.chart


def _gap_width(plot_elm) -> int | None:
    gw = plot_elm.find(qn("c:gapWidth"))
    return None if gw is None else int(gw.get("val"))


class DescribeAuto:
    def it_shrinks_font_and_drops_gap_width_on_dense_multi_series(self):
        # 5 cats × 2 series → heuristic fires.
        chart = _make_chart(
            categories=["A", "B", "C", "D", "E"], series_count=2
        )
        chart.plots[0].has_data_labels = True
        chart.plots[0].data_labels.collision_strategy = "auto"

        assert chart.plots[0].data_labels.font.size == Pt(8)
        plot_elm = chart.plots[0]._element
        assert _gap_width(plot_elm) == 60

    def it_only_shrinks_font_when_few_categories(self):
        # 3 cats — heuristic doesn't fire; font shrinks but gap_width
        # stays at PowerPoint's default (None / unset).
        chart = _make_chart(categories=["A", "B", "C"], series_count=2)
        chart.plots[0].has_data_labels = True
        chart.plots[0].data_labels.collision_strategy = "auto"

        assert chart.plots[0].data_labels.font.size == Pt(8)
        # gap_width left unset for the chart engine to resolve.
        plot_elm = chart.plots[0]._element
        assert _gap_width(plot_elm) is None

    def it_only_shrinks_font_when_single_series(self):
        chart = _make_chart(
            categories=["A", "B", "C", "D", "E"], series_count=1
        )
        chart.plots[0].has_data_labels = True
        chart.plots[0].data_labels.collision_strategy = "auto"

        plot_elm = chart.plots[0]._element
        assert _gap_width(plot_elm) is None


class DescribeCompact:
    def it_always_shrinks_and_thickens(self):
        # ``compact`` skips the heuristic and applies regardless of
        # category / series count.
        chart = _make_chart(categories=["A", "B"], series_count=1)
        chart.plots[0].has_data_labels = True
        chart.plots[0].data_labels.collision_strategy = "compact"

        assert chart.plots[0].data_labels.font.size == Pt(8)
        plot_elm = chart.plots[0]._element
        assert _gap_width(plot_elm) == 60

    def it_inserts_gap_width_in_schema_order(self):
        # A freshly written barChart has no c:gapWidth, so the strategy
        # creates one; it must land *before* c:axId in the CT_BarChart
        # sequence — appended after axId, PowerPoint repairs the deck.
        chart = _make_chart(categories=["A", "B"], series_count=1)
        chart.plots[0].has_data_labels = True
        chart.plots[0].data_labels.collision_strategy = "compact"

        plot_elm = chart.plots[0]._element
        tags = [child.tag for child in plot_elm]
        assert tags.index(qn("c:gapWidth")) < tags.index(qn("c:axId"))


class DescribeShrink:
    def it_only_touches_font(self):
        chart = _make_chart(
            categories=["A", "B", "C", "D", "E"], series_count=2
        )
        chart.plots[0].has_data_labels = True
        chart.plots[0].data_labels.collision_strategy = "shrink"

        assert chart.plots[0].data_labels.font.size == Pt(8)
        plot_elm = chart.plots[0]._element
        assert _gap_width(plot_elm) is None


class DescribeRejectsBadInputs:
    def it_rejects_unknown_strategies(self):
        chart = _make_chart(categories=["A", "B"], series_count=1)
        chart.plots[0].has_data_labels = True
        with pytest.raises(ValueError, match="collision_strategy"):
            chart.plots[0].data_labels.collision_strategy = "bogus"

    def it_raises_on_read(self):
        chart = _make_chart(categories=["A", "B"], series_count=1)
        chart.plots[0].has_data_labels = True
        with pytest.raises(AttributeError):
            chart.plots[0].data_labels.collision_strategy  # noqa: B018
