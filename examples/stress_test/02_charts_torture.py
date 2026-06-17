"""Charts torture: many chart types, every built-in palette, every quick
layout, custom layout dicts, per-series gradient + pattern fills, and
chart.shape repositioning.
"""

from __future__ import annotations

from _util import blank, deck, save

from power_pptx.chart.data import CategoryChartData, XyChartData
from power_pptx.chart.palettes import palette_names
from power_pptx.chart.quick_layouts import QUICK_LAYOUTS
from power_pptx.dml.color import RGBColor
from power_pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from power_pptx.enum.dml import MSO_PATTERN_TYPE
from power_pptx.util import Inches


CATS = ["Q1", "Q2", "Q3", "Q4"]


def _cat_data():
    d = CategoryChartData()
    d.categories = CATS
    d.add_series("ARR", (100, 130, 155, 182))
    d.add_series("NDR", (115, 118, 124, 131))
    d.add_series("Pipeline", (60, 75, 90, 110))
    return d


def build():
    prs = deck()

    chart_types = [
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        XL_CHART_TYPE.COLUMN_STACKED,
        XL_CHART_TYPE.BAR_CLUSTERED,
        XL_CHART_TYPE.LINE,
        XL_CHART_TYPE.LINE_MARKERS,
        XL_CHART_TYPE.AREA,
        XL_CHART_TYPE.AREA_STACKED,
        XL_CHART_TYPE.RADAR,
        XL_CHART_TYPE.DOUGHNUT,
    ]

    # --- One slide per chart type, cycling palettes ----------------------
    palettes = list(palette_names())
    for i, ct in enumerate(chart_types):
        s = blank(prs)
        cs = s.shapes.add_chart(ct, Inches(0.7), Inches(0.7),
                                Inches(11.9), Inches(6.0), _cat_data())
        chart = cs.chart
        chart.apply_palette(palettes[i % len(palettes)])
        chart.apply_quick_layout("title_axes_legend_bottom"
                                 if ct not in (XL_CHART_TYPE.DOUGHNUT,)
                                 else "title_legend_right")
        try:
            chart.chart_title.text_frame.text = str(ct)
        except Exception:
            pass

    # --- Pie with palette + custom layout dict ---------------------------
    s = blank(prs)
    pie_data = CategoryChartData()
    pie_data.categories = ["A", "B", "C", "D", "E"]
    pie_data.add_series("Share", (30, 25, 20, 15, 10))
    cs = s.shapes.add_chart(XL_CHART_TYPE.PIE, Inches(2), Inches(1),
                            Inches(9), Inches(5.5), pie_data)
    chart = cs.chart
    chart.apply_palette(["#4F9DFF", "#7FCFA1", "#F7B500", "#EC4899", "#8B5CF6"])
    chart.apply_quick_layout({
        "has_title": True,
        "title_text": "Market share",
        "has_legend": True,
        "legend_position": "right",  # string form
    })

    # --- Every quick layout preset on the same column chart --------------
    for name in QUICK_LAYOUTS:
        s = blank(prs)
        cs = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED,
                                Inches(0.7), Inches(0.7),
                                Inches(11.9), Inches(6.0), _cat_data())
        chart = cs.chart
        chart.apply_quick_layout(name)
        tb = s.shapes.add_textbox(Inches(0.7), Inches(6.8), Inches(8), Inches(0.4))
        tb.text_frame.text = f"quick layout: {name}"

    # --- Per-series gradient + pattern fills -----------------------------
    s = blank(prs)
    cs = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED,
                            Inches(0.7), Inches(0.7),
                            Inches(11.9), Inches(6.0), _cat_data())
    chart = cs.chart
    g = chart.series[0].format.fill
    g.gradient(kind="linear")
    g.gradient_stops.replace([(0.0, "#0F2D6B"), (1.0, "#4F9DFF")])
    pat = chart.series[1].format.fill
    pat.patterned()
    pat.pattern = MSO_PATTERN_TYPE.WIDE_DOWNWARD_DIAGONAL
    pat.fore_color.rgb = (0x10, 0xB9, 0x81)
    pat.back_color.rgb = (0xFF, 0xFF, 0xFF)
    chart.series[2].format.fill.solid()
    chart.series[2].format.fill.fore_color.rgb = RGBColor(0xF5, 0x9E, 0x0B)

    # --- XY scatter + chart.shape repositioning -------------------------
    s = blank(prs)
    xy = XyChartData()
    series = xy.add_series("corr")
    for x in range(10):
        series.add_data_point(x, x * 1.7 + (x % 3))
    cs = s.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER, Inches(3), Inches(2),
                            Inches(6), Inches(4), xy)
    chart = cs.chart
    chart.shape.left = Inches(0.7)
    chart.shape.top = Inches(0.7)
    chart.shape.width = Inches(11.9)
    chart.shape.height = Inches(6.0)
    chart.apply_palette("vibrant")
    chart.apply_quick_layout({
        "has_title": True,
        "title_text": "Scatter",
        "has_legend": True,
        "legend_position": XL_LEGEND_POSITION.BOTTOM,
        "value_axis": {"has_major_gridlines": True},
    })

    return prs


if __name__ == "__main__":
    save(build(), "02_charts_torture.pptx")
