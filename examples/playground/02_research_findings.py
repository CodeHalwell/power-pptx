"""Playground 02 — Research findings deck (chart-heavy).

A seven-slide "scientific results" deck that exercises:

    cover → methods → headline scatter → stacked bar
    → donut + side legend → 2x2 small-multiples → conclusion

Demonstrates: ``XL_CHART_TYPE.XY_SCATTER`` with paired series,
``BAR_STACKED_100`` and ``BAR_STACKED``, donut chart per-slice colored
via ``Chart.recolour``, a 2x2 small-multiples grid of column charts
sharing a palette, secondary-axis line/column combo, and the post-fork
``chart.shape`` accessor for resizing.
"""

from __future__ import annotations

from pathlib import Path

from power_pptx import Presentation
from power_pptx.chart.data import CategoryChartData, XyChartData
from power_pptx.design.layout import Grid
from power_pptx.dml.color import RGBColor
from power_pptx.enum.chart import (
    XL_CHART_TYPE,
    XL_LABEL_POSITION,
    XL_LEGEND_POSITION,
)
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
from power_pptx.util import Inches, Pt

from _brand import SUNSET, SUNSET_CHART_PALETTE, MIDNIGHT_CHART_PALETTE
from _common import lint_or_die

HERE = Path(__file__).parent
P = SUNSET.palette


def build(out_path: Path) -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    _cover(prs)
    _methods(prs)
    _scatter_headline(prs)
    _stacked_progress(prs)
    _donut_with_legend(prs)
    _small_multiples(prs)
    _conclusion(prs)

    lint_or_die(prs)
    prs.save(out_path)
    return prs


# ----------------------------------------------------------------------
# slide 1 — cover with two big stat callouts
# ----------------------------------------------------------------------

def _cover(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["neutral"])

    # Big background coral disc bottom-right for visual interest.
    disc = slide.shapes.add_shape(
        MSO_SHAPE.OVAL,
        Inches(8.5), Inches(3.0), Inches(7.5), Inches(7.5),
    )
    disc.fill.solid()
    disc.fill.fore_color.rgb = P["primary"]
    disc.fill.fore_color.alpha = 0.85
    disc.line.fill.background()
    disc.blur.radius = Pt(2)

    kicker = slide.shapes.add_textbox(
        Inches(0.9), Inches(0.8), Inches(11), Inches(0.5),
    )
    kt = kicker.text_frame
    kt.word_wrap = True
    kt.text = "WORKING PAPER  •  POWER-PPTX RESEARCH  •  N°27"
    p = kt.paragraphs[0]
    p.font.name = "DejaVu Sans"
    p.font.size = Pt(13)
    p.font.bold = True
    p.font.color.rgb = P["accent"]
    p.alignment = PP_ALIGN.LEFT

    head = slide.shapes.add_textbox(
        Inches(0.9), Inches(1.6), Inches(11.5), Inches(3.5),
    )
    ht = head.text_frame
    ht.word_wrap = True
    ht.text = (
        "Surfacing Slowdowns: Latency Patterns in a 400-Service Mesh"
    )
    ht.fit_text(font_family="DejaVu Serif", max_size=60, bold=True)
    ht.paragraphs[0].font.color.rgb = P["on_primary"]
    ht.paragraphs[0].alignment = PP_ALIGN.LEFT

    auth = slide.shapes.add_textbox(
        Inches(0.9), Inches(5.4), Inches(10), Inches(0.6),
    )
    at = auth.text_frame
    at.word_wrap = True
    at.text = "Halwell · Chen · Mbeki — May 2026"
    ap = at.paragraphs[0]
    ap.font.name = "DejaVu Sans"
    ap.font.size = Pt(16)
    ap.font.italic = True
    ap.font.color.rgb = P["accent"]
    ap.alignment = PP_ALIGN.LEFT


# ----------------------------------------------------------------------
# slide 2 — methods: a sidebar of three cards + body text
# ----------------------------------------------------------------------

def _methods(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["background"])
    _title(slide, "Methods", "How we measured 1.4B request traces")

    items = [
        ("Sampling",   "Stratified-by-service, 0.5% of all upstream HTTP calls captured over a 14-day window in March 2026."),
        ("Aggregation", "Per-service P50/P95/P99 latency rolled up at 1-minute resolution and stored in a columnar warehouse."),
        ("Classification", "Each service tagged by tier (frontend / aggregator / data / async) and by call-graph depth from the edge."),
    ]
    grid = Grid(slide, cols=12, rows=6, gutter=Pt(18), margin=Pt(56))
    for i, (heading, body) in enumerate(items):
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, 0, 0, 1, 1)
        grid.place(card, col=i * 4, row=2, col_span=4, row_span=3)
        _methods_card(card, heading, body)


def _methods_card(card, heading: str, body: str) -> None:
    card.fill.solid()
    card.fill.fore_color.rgb = P["surface"]
    card.line.color.rgb = RGBColor.from_hex("#E7DED0")
    card.line.width = Pt(1)
    card.shadow.blur_radius = Pt(20)
    card.shadow.distance = Pt(6)
    card.shadow.direction = 90.0
    card.shadow.color.rgb = P["neutral"]
    card.shadow.color.alpha = 0.10

    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(20)
    tf.margin_top = tf.margin_bottom = Pt(20)
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    tf.text = heading
    p0 = tf.paragraphs[0]
    p0.font.name = "DejaVu Serif"
    p0.font.size = Pt(22)
    p0.font.bold = True
    p0.font.color.rgb = P["primary"]
    p0.alignment = PP_ALIGN.LEFT

    p1 = tf.add_paragraph()
    p1.text = body
    p1.font.name = "DejaVu Sans"
    p1.font.size = Pt(13)
    p1.font.color.rgb = P["muted"]
    p1.space_before = Pt(8)
    p1.line_spacing = 1.4
    p1.alignment = PP_ALIGN.LEFT


# ----------------------------------------------------------------------
# slide 3 — scatter (XY) of P95 latency vs call-graph depth
# ----------------------------------------------------------------------

def _scatter_headline(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["background"])
    _title(
        slide,
        "Headline: depth predicts tail latency",
        "P95 (ms) vs call-graph depth, n=412 services",
    )

    data = XyChartData()
    series_a = data.add_series("Frontend tier")
    for x, y in [(1, 22), (1, 38), (1, 28), (1, 19), (2, 41), (2, 55), (2, 32)]:
        series_a.add_data_point(x, y)
    series_b = data.add_series("Aggregator tier")
    for x, y in [(2, 71), (3, 88), (3, 102), (3, 78), (4, 121), (4, 134), (4, 96)]:
        series_b.add_data_point(x, y)
    series_c = data.add_series("Data tier")
    for x, y in [(3, 145), (4, 192), (4, 211), (5, 245), (5, 288), (5, 312), (6, 358)]:
        series_c.add_data_point(x, y)

    shape = slide.shapes.add_chart(
        XL_CHART_TYPE.XY_SCATTER,
        Inches(0.9), Inches(1.95), Inches(11.5), Inches(4.7),
        data,
    )
    chart = shape.chart

    # XL_CHART_TYPE.XY_SCATTER ships with <a:ln><a:noFill/></a:ln> on
    # each series to suppress the connecting line — DO NOT touch
    # series.format.line here, or markers-only becomes lines-with-markers.
    # The visible color on a markers-only scatter is the marker's own
    # fill, not the series fill.
    for s, color in zip(chart.series, [P["primary"], P["accent"], "#4A7C8C"]):
        rgb = color if isinstance(color, RGBColor) else RGBColor.from_hex(color)
        s.marker.size = 10
        s.marker.format.fill.solid()
        s.marker.format.fill.fore_color.rgb = rgb
        s.marker.format.line.color.rgb = rgb

    chart.apply_quick_layout({
        "has_title": False,
        "has_legend": True,
        "legend_position": XL_LEGEND_POSITION.BOTTOM,
        "value_axis":    {"has_major_gridlines": True},
        "category_axis": {"has_major_gridlines": False},
    })

    cap = slide.shapes.add_textbox(
        Inches(0.9), Inches(6.75), Inches(11.5), Inches(0.5),
    )
    cap.text_frame.word_wrap = True
    cap.text_frame.text = (
        "Tail latency rises monotonically with depth from the edge. "
        "Each unit of depth adds ~50ms at the data tier."
    )
    cp = cap.text_frame.paragraphs[0]
    cp.font.name = "DejaVu Sans"
    cp.font.size = Pt(11)
    cp.font.italic = True
    cp.font.color.rgb = P["muted"]
    cp.alignment = PP_ALIGN.LEFT


# ----------------------------------------------------------------------
# slide 4 — stacked bar: where the time goes
# ----------------------------------------------------------------------

def _stacked_progress(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["background"])
    _title(
        slide,
        "Where the time goes — per tier",
        "Median request budget breakdown (ms)",
    )

    data = CategoryChartData()
    data.categories = ["Frontend", "Aggregator", "Data", "Async worker"]
    data.add_series("Network",        (8, 12, 14, 9))
    data.add_series("Serialization", (4, 11, 17, 6))
    data.add_series("Compute",       (12, 28, 41, 33))
    data.add_series("Storage I/O",   (3, 18, 92, 47))
    data.add_series("Queue wait",    (1, 6,  22, 51))

    shape = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_STACKED,
        Inches(0.9), Inches(1.95), Inches(11.5), Inches(4.9),
        data,
    )
    chart = shape.chart
    chart.apply_palette(SUNSET_CHART_PALETTE)
    chart.apply_quick_layout({
        "has_title": False,
        "has_legend": True,
        "legend_position": XL_LEGEND_POSITION.BOTTOM,
    })

    cap = slide.shapes.add_textbox(
        Inches(0.9), Inches(6.95), Inches(11.5), Inches(0.4),
    )
    cap.text_frame.word_wrap = True
    cap.text_frame.text = "Storage I/O dominates the data tier; queue wait dominates async."
    cp = cap.text_frame.paragraphs[0]
    cp.font.name = "DejaVu Sans"
    cp.font.size = Pt(11)
    cp.font.italic = True
    cp.font.color.rgb = P["muted"]
    cp.alignment = PP_ALIGN.LEFT


# ----------------------------------------------------------------------
# slide 5 — donut with side legend + a stat block
# ----------------------------------------------------------------------

def _donut_with_legend(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["background"])
    _title(
        slide,
        "Service composition by tier",
        "n=412 services in scope; share of total request volume",
    )

    data = CategoryChartData()
    data.categories = ["Frontend", "Aggregator", "Data", "Async worker"]
    data.add_series("Volume", (38, 27, 24, 11))

    shape = slide.shapes.add_chart(
        XL_CHART_TYPE.DOUGHNUT,
        Inches(0.9), Inches(2.0), Inches(6.0), Inches(5.0),
        data,
    )
    chart = shape.chart

    # Doughnut is single-series; recolour() dispatches to color_by_category.
    chart.recolour(SUNSET_CHART_PALETTE)

    chart.apply_quick_layout({
        "has_title": False,
        "has_legend": True,
        "legend_position": XL_LEGEND_POSITION.RIGHT,
    })
    try:
        chart.legend.include_in_layout = False
    except Exception:
        pass

    # Stat block beside the donut.
    stat_box = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(7.6), Inches(2.4), Inches(5.0), Inches(4.2),
    )
    stat_box.fill.solid()
    stat_box.fill.fore_color.rgb = P["surface"]
    stat_box.line.color.rgb = RGBColor.from_hex("#E7DED0")
    stat_box.line.width = Pt(1)
    stat_box.shadow.blur_radius = Pt(18)
    stat_box.shadow.distance = Pt(6)
    stat_box.shadow.color.rgb = P["neutral"]
    stat_box.shadow.color.alpha = 0.10

    tf = stat_box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(24)
    tf.margin_top = tf.margin_bottom = Pt(24)
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    tf.text = "Headline"
    p0 = tf.paragraphs[0]
    p0.font.name = "DejaVu Sans"
    p0.font.size = Pt(12)
    p0.font.bold = True
    p0.font.color.rgb = P["primary"]
    p0.alignment = PP_ALIGN.LEFT

    p1 = tf.add_paragraph()
    p1.text = "65%"
    p1.font.name = "DejaVu Serif"
    p1.font.size = Pt(76)
    p1.font.bold = True
    p1.font.color.rgb = P["neutral"]
    p1.space_before = Pt(6)
    p1.alignment = PP_ALIGN.LEFT

    p2 = tf.add_paragraph()
    p2.text = "of request volume sits in the frontend + aggregator tiers — and accounts for only 22% of the P95 latency budget."
    p2.font.name = "DejaVu Sans"
    p2.font.size = Pt(15)
    p2.font.color.rgb = P["muted"]
    p2.line_spacing = 1.35
    p2.space_before = Pt(8)
    p2.alignment = PP_ALIGN.LEFT


# ----------------------------------------------------------------------
# slide 6 — 2x2 small multiples (one column chart per tier)
# ----------------------------------------------------------------------

def _small_multiples(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["background"])
    _title(
        slide,
        "Small multiples — P95 distribution per tier",
        "Histogram of P95 latencies (ms), bucketed",
    )

    tiers = [
        ("Frontend",     [(28, 6), (52, 14), (74, 22), (96, 18), (118, 9), (140, 3)]),
        ("Aggregator",   [(28, 1), (52, 4),  (74, 11), (96, 20), (118, 28), (140, 16)]),
        ("Data",         [(28, 0), (52, 1),  (74, 4),  (96, 9),  (118, 18), (140, 41)]),
        ("Async worker", [(28, 3), (52, 8),  (74, 14), (96, 22), (118, 11), (140, 6)]),
    ]

    grid = Grid(slide, cols=12, rows=10, gutter=Pt(18), margin=Pt(56))
    # Two rows, two cols of charts in the lower 8 grid-rows.
    positions = [(0, 2), (6, 2), (0, 6), (6, 6)]
    colors = SUNSET_CHART_PALETTE
    for (col, row), (name, buckets), color in zip(positions, tiers, colors):
        cell = grid.cell(col=col, row=row, col_span=6, row_span=4)
        data = CategoryChartData()
        data.categories = [str(b[0]) for b in buckets]
        data.add_series(name, tuple(b[1] for b in buckets))
        shape = slide.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED,
            cell.left, cell.top, cell.width, cell.height,
            data,
        )
        chart = shape.chart
        chart.series[0].format.fill.solid()
        chart.series[0].format.fill.fore_color.rgb = (
            color if isinstance(color, RGBColor) else RGBColor.from_hex(color)
        )
        chart.apply_quick_layout({
            "has_title": True,
            "title_text": name,
            "has_legend": False,
            "category_axis": {"has_major_gridlines": False},
            "value_axis":    {"has_major_gridlines": True},
        })


# ----------------------------------------------------------------------
# slide 7 — conclusion: a 3-line takeaway over a soft gradient
# ----------------------------------------------------------------------

def _conclusion(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    # Full-bleed gradient background using a shape with linear gradient.
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(0), Inches(13.333), Inches(7.5),
    )
    bg.fill.gradient(kind="linear")
    bg.fill.gradient_stops.replace([
        (0.0, P["neutral"]),
        (1.0, P["primary"]),
    ])
    bg.line.fill.background()
    sp_tree = bg._element.getparent()
    sp_tree.remove(bg._element)
    sp_tree.insert(2, bg._element)

    head = slide.shapes.add_textbox(
        Inches(0.9), Inches(0.9), Inches(11.5), Inches(1.2),
    )
    ht = head.text_frame
    ht.word_wrap = True
    ht.text = "What this tells us"
    ht.fit_text(font_family="DejaVu Serif", max_size=46, bold=True)
    ht.paragraphs[0].font.color.rgb = P["on_primary"]
    ht.paragraphs[0].alignment = PP_ALIGN.LEFT

    bullets = [
        ("Depth, not service identity, is the tail-latency driver.",
         "Targeting the deepest 10% of services would compress P95 by an estimated 40%."),
        ("Storage I/O and queue wait dominate.",
         "Together they account for 71% of the slow-path budget. Network and serialization are noise."),
        ("Async workers are an underweighted lever.",
         "Despite handling 11% of volume they contribute 23% of P95 budget — mostly queue wait."),
    ]
    body = slide.shapes.add_textbox(
        Inches(0.9), Inches(2.2), Inches(11.5), Inches(4.7),
    )
    bt = body.text_frame
    bt.word_wrap = True
    bt.text = ""
    for i, (heading, sub) in enumerate(bullets):
        para_h = bt.paragraphs[0] if i == 0 else bt.add_paragraph()
        para_h.text = f"{i + 1}.  {heading}"
        para_h.font.name = "DejaVu Sans"
        para_h.font.size = Pt(22)
        para_h.font.bold = True
        para_h.font.color.rgb = P["on_primary"]
        para_h.space_before = Pt(8 if i == 0 else 18)
        para_h.alignment = PP_ALIGN.LEFT

        para_s = bt.add_paragraph()
        para_s.text = sub
        para_s.font.name = "DejaVu Sans"
        para_s.font.size = Pt(15)
        para_s.font.italic = True
        para_s.font.color.rgb = P["accent"]
        para_s.space_before = Pt(4)
        para_s.line_spacing = 1.35
        para_s.alignment = PP_ALIGN.LEFT


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _paint_bg(slide, color) -> None:
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(0), Inches(13.333), Inches(7.5),
    )
    bg.fill.solid()
    if isinstance(color, str):
        bg.fill.fore_color.rgb = RGBColor.from_hex(color)
    else:
        bg.fill.fore_color.rgb = color
    bg.line.fill.background()
    sp_tree = bg._element.getparent()
    sp_tree.remove(bg._element)
    sp_tree.insert(2, bg._element)


def _title(slide, title: str, subtitle: str) -> None:
    tbox = slide.shapes.add_textbox(
        Inches(0.9), Inches(0.45), Inches(11.5), Inches(0.9),
    )
    tt = tbox.text_frame
    tt.word_wrap = True
    tt.text = title
    tt.fit_text(font_family="DejaVu Serif", max_size=32, bold=True)
    tt.paragraphs[0].font.color.rgb = P["neutral"]
    tt.paragraphs[0].alignment = PP_ALIGN.LEFT

    sbox = slide.shapes.add_textbox(
        Inches(0.9), Inches(1.3), Inches(11.5), Inches(0.5),
    )
    st = sbox.text_frame
    st.word_wrap = True
    st.text = subtitle
    sp = st.paragraphs[0]
    sp.font.name = "DejaVu Sans"
    sp.font.size = Pt(13)
    sp.font.italic = True
    sp.font.color.rgb = P["muted"]
    sp.alignment = PP_ALIGN.LEFT


if __name__ == "__main__":
    out = HERE / "_out" / "02_research_findings.pptx"
    out.parent.mkdir(exist_ok=True)
    build(out)
    print(f"wrote {out}")
