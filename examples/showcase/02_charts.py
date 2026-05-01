"""Showcase 02 — Charts: palettes, quick layouts, per-series fills.

Demonstrates the chart helpers added in Phase 10:

* ``chart.apply_palette(...)`` with both built-in names and custom lists
* ``chart.apply_quick_layout(...)`` opinionated layout presets
* per-series gradient fill on a column chart

Four chart types in one deck — column, line, bar, pie — each on its
own slide with a brand-aligned palette.
"""

from __future__ import annotations

from pathlib import Path

from power_pptx import Presentation
from power_pptx.chart.data import CategoryChartData
from power_pptx.dml.color import RGBColor
from power_pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from power_pptx.util import Inches

from _lint import lint_or_die
from _tokens import CHART_PALETTE

HERE = Path(__file__).parent


def build(out_path: Path) -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    _column_with_gradient(prs)
    _line_with_modern_palette(prs)
    _bar_with_brand_palette(prs)
    _pie_minimal(prs)

    lint_or_die(prs)
    prs.save(out_path)
    return prs


def _add_title(slide, text: str) -> None:
    box = slide.shapes.add_textbox(
        Inches(0.6), Inches(0.4), Inches(12), Inches(0.9),
    )
    tf = box.text_frame
    tf.word_wrap = True
    tf.text = text
    tf.fit_text(font_family="Inter", max_size=32, bold=True)
    tf.paragraphs[0].font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)


def _column_with_gradient(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_title(slide, "ARR by quarter — column with gradient series")

    data = CategoryChartData()
    data.categories = ["Q1", "Q2", "Q3", "Q4"]
    data.add_series("FY25", (62, 71, 88, 110))
    data.add_series("FY26", (124, 145, 168, 182))

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(1), Inches(1.6), Inches(11.3), Inches(5.4),
        data,
    ).chart

    chart.apply_quick_layout("title_legend_bottom")
    chart.chart_title.text_frame.text = "ARR ($M)"

    # Gradient fill on the second (FY26) series for emphasis.
    fill = chart.series[1].format.fill
    fill.gradient(kind="linear")
    fill.gradient_stops.replace([
        (0.0, "#4F46E5"),
        (1.0, "#22D3EE"),
    ])

    # Solid brand color on the first series.
    chart.series[0].format.fill.solid()
    chart.series[0].format.fill.fore_color.rgb = RGBColor(0xCB, 0xD5, 0xE1)


def _line_with_modern_palette(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_title(slide, "NDR vs. Gross Retention — built-in 'modern' palette")

    data = CategoryChartData()
    data.categories = ["Q1", "Q2", "Q3", "Q4"]
    data.add_series("NDR (%)",  (115, 118, 124, 131))
    data.add_series("GRR (%)",  (94,  95,  96,  97))

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE,
        Inches(1), Inches(1.6), Inches(11.3), Inches(5.4),
        data,
    ).chart

    chart.apply_palette("modern")
    chart.apply_quick_layout("title_legend_bottom")
    chart.chart_title.text_frame.text = "Retention metrics (%)"


def _bar_with_brand_palette(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_title(slide, "ARR by segment — explicit brand palette")

    data = CategoryChartData()
    data.categories = ["Enterprise", "Mid-market", "SMB", "Self-serve"]
    data.add_series("FY26", (94, 55, 23, 10))

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_CLUSTERED,
        Inches(1), Inches(1.6), Inches(11.3), Inches(5.4),
        data,
    ).chart

    # Single-series bar — color each segment from the brand palette.
    series = chart.series[0]
    for point, color in zip(series.points, CHART_PALETTE):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = RGBColor.from_string(color.lstrip("#"))

    chart.apply_quick_layout("title_no_legend")
    chart.chart_title.text_frame.text = "ARR ($M) by segment"


def _pie_minimal(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_title(slide, "Revenue mix — pie with the 'minimal' quick layout")

    data = CategoryChartData()
    data.categories = ["Subscription", "Services", "Marketplace", "Other"]
    data.add_series("FY26", (148, 21, 11, 2))

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.PIE,
        Inches(2.5), Inches(1.6), Inches(8.3), Inches(5.4),
        data,
    ).chart

    # Pie charts have one series with many slices; ``apply_palette``
    # recolors series, so we color each data point individually.
    series = chart.series[0]
    for point, color in zip(series.points, CHART_PALETTE):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = RGBColor.from_string(color.lstrip("#"))

    chart.apply_quick_layout({
        "has_title":       True,
        "title_text":      "Revenue mix ($M)",
        "has_legend":      True,
        "legend_position": XL_LEGEND_POSITION.RIGHT,
    })
    chart.legend.include_in_layout = False


if __name__ == "__main__":
    out = HERE / "_out" / "02_charts.pptx"
    out.parent.mkdir(exist_ok=True)
    build(out)
    print(f"wrote {out}")
