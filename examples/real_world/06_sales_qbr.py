"""06 — Sales QBR: Q1 FY27 Quarterly Business Review.

The bread-and-butter quarterly sales review presented by a sales VP
to their CRO and senior leadership.

Slides:
    1. Cover
    2. Headline number (KPIs)
    3. Pipeline coverage (column chart)
    4. Bookings by segment (bar)
    5. Region heat map (table with conditional fill)
    6. Top 10 deals (table)
    7. Win/loss analysis (pie)
    8. Forecast next quarter (line chart)
    9. Asks (bullets)
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from power_pptx.chart.data import CategoryChartData
from power_pptx.design.recipes import kpi_slide
from power_pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from power_pptx.enum.text import MSO_VERTICAL_ANCHOR
from power_pptx.util import Inches, Pt

from _brand import SALES as TOKENS, SALES_PALETTE as PALETTE
from _common import (
    closing_slide,
    color_delta,
    cover_slide,
    divider,
    eyebrow,
    footer,
    hairline_below,
    hex_rgb,
    lint_or_die,
    new_deck,
    section_title,
    shade_cell,
    status_cell,
    styled_card,
    table_body_text,
    table_header_row,
)

FOOTER = "Q1 FY27 QBR  |  Sales Operations  |  Internal use only"


def build(out: Path) -> None:
    prs = new_deck()

    cover_slide(
        prs,
        eyebrow_text="Q1 FY27 Quarterly Business Review",
        title="Strong start.\nA few hot spots to fix.",
        subtitle="Q1 closed at 104% of plan with bookings of $612M. "
                 "Software bookings led, EMEA needs attention, and "
                 "the top of funnel is healthy heading into Q2.",
        presenter="Marcus Reed, SVP Worldwide Sales",
        date="Q1 FY27  •  CRO Staff Review  •  May 5, 2026",
        tokens=TOKENS,
    )

    kpi_slide(
        prs, title="Q1 FY27 — at a glance",
        kpis=[
            {"label": "Bookings",         "value": "$612M", "delta": +0.04},
            {"label": "Pipeline coverage","value": "3.6×",  "delta": +0.20},
            {"label": "Win rate",         "value": "31%",   "delta": +0.04},
            {"label": "Avg deal cycle",   "value": "92 d",  "delta": -0.08},
        ],
        tokens=TOKENS,
    )
    footer(prs.slides[-1], FOOTER, "2", TOKENS)

    _pipeline(prs)
    _segment_bookings(prs)
    _region_table(prs)
    _top10(prs)
    _win_loss(prs)
    _forecast(prs)
    _asks(prs)

    closing_slide(
        prs,
        headline="Q2 — pull forward, push higher.",
        sub="Plan: $674M bookings  •  4.0× pipeline coverage entering Q3",
        tokens=TOKENS,
    )

    lint_or_die(prs)
    prs.save(out)
    print(f"wrote {out}")


def _pipeline(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Top of funnel", TOKENS)
    section_title(slide, "Q2 pipeline coverage at 3.6× plan", TOKENS)
    divider(slide, TOKENS)

    data = CategoryChartData()
    data.categories = ["Stage 1", "Stage 2", "Stage 3", "Stage 4", "Closed-Won"]
    data.add_series("Q1 actual ($M)", (1820, 1240, 720, 380, 612))
    data.add_series("Q2 entering ($M)", (2210, 1480, 880, 440, 0))

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(0.6), Inches(1.7), Inches(8.5), Inches(5.0),
        data,
    ).chart
    chart.apply_palette(PALETTE)
    chart.apply_quick_layout("title_legend_bottom")
    chart.chart_title.text_frame.text = "Pipeline by stage ($M)"

    card = styled_card(slide, 9.4, 1.7, 3.4, 5.0, tokens=TOKENS,
                       fill_hex=TOKENS.palette["surface"])
    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(18)
    tf.margin_top = tf.margin_bottom = Pt(18)
    tf.text = "Pipeline takeaways"
    p = tf.paragraphs[0]
    p.font.name = TOKENS.typography["heading"].family
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = hex_rgb(TOKENS.palette["primary"])
    items = [
        ("Coverage healthy",       "3.6× entering Q2 (target 3.0×)."),
        ("Stage-2 conversion",     "Up 8 pts, driven by new MEDDPICC discipline."),
        ("Late-stage slippage",    "11% of stage-4 slipped from Q1; we expect 60% to close in Q2."),
    ]
    for h, b in items:
        p = tf.add_paragraph()
        p.text = h
        p.space_before = Pt(10)
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
        p2 = tf.add_paragraph()
        p2.text = b
        p2.font.size = Pt(11)
        p2.font.color.rgb = hex_rgb(TOKENS.palette["muted"])
    footer(slide, FOOTER, "3", TOKENS)


def _segment_bookings(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Mix", TOKENS)
    section_title(slide, "Software led; Services flat; Hardware soft", TOKENS)
    divider(slide, TOKENS)

    data = CategoryChartData()
    data.categories = ["Software", "Services", "Hardware", "Subscription"]
    data.add_series("Q1 FY27 bookings ($M)", (286, 142, 102, 82))

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_CLUSTERED,
        Inches(0.6), Inches(1.7), Inches(8.5), Inches(5.0),
        data,
    ).chart
    series = chart.series[0]
    for point, hexc in zip(series.points, PALETTE):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = hex_rgb(hexc)
    chart.apply_quick_layout("title_no_legend")
    chart.chart_title.text_frame.text = "Q1 bookings by segment ($M)"

    card = styled_card(slide, 9.4, 1.7, 3.4, 2.4, tokens=TOKENS,
                       fill_hex=TOKENS.palette["surface"])
    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(16)
    tf.margin_top = tf.margin_bottom = Pt(14)
    tf.text = "Software"
    p = tf.paragraphs[0]
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = hex_rgb(TOKENS.palette["positive"])
    p2 = tf.add_paragraph()
    p2.text = "+19% YoY. Multi-year deal mix up 12 pts."
    p2.font.size = Pt(12)
    p2.font.color.rgb = hex_rgb(TOKENS.palette["muted"])

    card2 = styled_card(slide, 9.4, 4.3, 3.4, 2.4, tokens=TOKENS,
                        fill_hex=TOKENS.palette["surface"])
    tf = card2.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(16)
    tf.margin_top = tf.margin_bottom = Pt(14)
    tf.text = "Hardware"
    p = tf.paragraphs[0]
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = hex_rgb(TOKENS.palette["negative"])
    p2 = tf.add_paragraph()
    p2.text = "−6% YoY. Two large datacenter cycles pushed to Q3."
    p2.font.size = Pt(12)
    p2.font.color.rgb = hex_rgb(TOKENS.palette["muted"])
    footer(slide, FOOTER, "4", TOKENS)


def _region_table(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Regional view", TOKENS)
    section_title(slide, "Region scorecard — green / amber / red", TOKENS)
    divider(slide, TOKENS)

    rows = [
        ("Region",        "Plan",  "Actual", "vs. Plan", "Pipeline", "Win rate", "Status"),
        ("North America", "$248M", "$268M",  "+8.1%",   "3.9×",     "33%",     "G"),
        ("EMEA",          "$162M", "$148M",  "−8.6%",   "3.1×",     "27%",     "R"),
        ("APAC",          "$108M", "$112M",  "+3.7%",   "3.5×",     "29%",     "G"),
        ("LATAM",         "$42M",  "$44M",   "+4.8%",   "3.6×",     "31%",     "G"),
        ("Public sector", "$28M",  "$22M",   "−21.4%",  "2.4×",     "22%",     "R"),
        ("Strategic / Global","$28M","$18M", "−35.7%",  "1.9×",     "18%",     "A"),
    ]
    shape = slide.shapes.add_table(
        rows=len(rows), cols=7,
        left=Inches(0.6), top=Inches(1.7),
        width=Inches(12.1), height=Inches(4.6),
    )
    table = shape.table
    table.columns[0].width = Inches(2.5)
    for c in (1, 2, 3): table.columns[c].width = Inches(1.7)
    table.columns[4].width = Inches(1.6)
    table.columns[5].width = Inches(1.5)
    table.columns[6].width = Inches(1.4)

    table_header_row(table, rows[0], TOKENS)
    for r, row in enumerate(rows[1:], start=1):
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            if c == 6:
                status_cell(cell, *REGION_STATUS[value])
            else:
                _region_metric_cell(cell, r, c, value)
            cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
            hairline_below(cell)
    footer(slide, FOOTER, "5", TOKENS)


#: Region status code -> (label, fill) for the scorecard's status column.
REGION_STATUS = {
    "G": ("ON TRACK", "#16A34A"),
    "A": ("AT RISK", "#F59E0B"),
    "R": ("OFF PLAN", "#DC2626"),
}


def _region_metric_cell(cell, r: int, c: int, value: str) -> None:
    """Bold region names, a coloured "vs. Plan" delta, zebra-striped rows."""
    p = table_body_text(cell, value, TOKENS)
    if c == 0:
        p.font.bold = True
    if c == 3:
        color_delta(p, value, TOKENS)
    if r % 2 == 0:
        shade_cell(cell, TOKENS.palette["surface"])


def _top10(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Q2 must-wins", TOKENS)
    section_title(slide, "Top 10 deals to land in Q2 — $214M total", TOKENS)
    divider(slide, TOKENS)

    rows = [
        ("Account",                "Region", "Stage",    "ACV",    "Close",  "Owner"),
        ("Polaris Capital",        "NA",     "Stage 4",  "$32M",   "May 18", "T. Singh"),
        ("Atlas Air",              "NA",     "Stage 4",  "$28M",   "May 22", "R. Kim"),
        ("ENGIE Renouvelables",    "EMEA",   "Stage 3",  "$24M",   "Jun 02", "M. Roche"),
        ("Bharti Industries",      "APAC",   "Stage 4",  "$22M",   "May 28", "P. Singh"),
        ("Aurora Mobility",        "NA",     "Stage 3",  "$21M",   "Jun 09", "R. Kim"),
        ("MunichRe Reinsurance",   "EMEA",   "Stage 3",  "$19M",   "Jun 18", "L. Weiss"),
        ("Stellar Logistics",      "EMEA",   "Stage 3",  "$18M",   "Jun 22", "L. Weiss"),
        ("Helios Power",           "LATAM",  "Stage 4",  "$17M",   "May 30", "C. Mendes"),
        ("Bay Health Network",     "NA",     "Stage 2",  "$17M",   "Jun 26", "T. Singh"),
        ("Frontier Materials",     "NA",     "Stage 3",  "$16M",   "Jun 27", "R. Kim"),
    ]
    shape = slide.shapes.add_table(
        rows=len(rows), cols=6,
        left=Inches(0.6), top=Inches(1.7),
        width=Inches(12.1), height=Inches(4.8),
    )
    table = shape.table
    table.columns[0].width = Inches(3.6)
    table.columns[1].width = Inches(1.3)
    table.columns[2].width = Inches(1.7)
    table.columns[3].width = Inches(1.6)
    table.columns[4].width = Inches(1.7)
    table.columns[5].width = Inches(2.2)

    table_header_row(table, rows[0], TOKENS)
    for r, row in enumerate(rows[1:], start=1):
        for c, value in enumerate(row):
            _deal_cell(table.cell(r, c), r, c, value)
    footer(slide, FOOTER, "6", TOKENS)


#: Deal stage -> text colour for the "Stage" column.
STAGE_COLOR = {
    "Stage 4": TOKENS.palette["positive"],
    "Stage 3": TOKENS.palette["primary"],
    "Stage 2": "#94A3B8",
}


def _deal_cell(cell, r: int, c: int, value: str) -> None:
    """Bold account, stage and ACV columns; the stage coloured by how late it is."""
    p = table_body_text(cell, value, TOKENS, size=11)
    if c == 0:
        p.font.bold = True
    if c == 2:
        p.font.bold = True
        p.font.color.rgb = hex_rgb(STAGE_COLOR.get(value, TOKENS.palette["neutral"]))
    if c == 3:
        p.font.bold = True
    cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
    if r % 2 == 0:
        shade_cell(cell, TOKENS.palette["surface"])
    hairline_below(cell)


def _win_loss(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Win/loss", TOKENS)
    section_title(slide, "Why we won — and why we lost", TOKENS)
    divider(slide, TOKENS)

    # Wins pie
    wins = CategoryChartData()
    wins.categories = ["Product capability", "Total cost", "Existing relationship",
                       "Time to value", "Other"]
    wins.add_series("Wins", (32, 24, 22, 16, 6))
    wins_chart = slide.shapes.add_chart(
        XL_CHART_TYPE.PIE,
        Inches(0.6), Inches(1.8), Inches(6.0), Inches(4.6),
        wins,
    ).chart
    series = wins_chart.series[0]
    for point, hexc in zip(series.points, PALETTE):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = hex_rgb(hexc)
    wins_chart.apply_quick_layout({
        "has_title": True, "title_text": "Why we won (%)",
        "has_legend": True, "legend_position": XL_LEGEND_POSITION.RIGHT,
    })

    # Losses pie
    losses = CategoryChartData()
    losses.categories = ["No decision", "Price", "Competitor capability",
                         "Implementation risk", "Other"]
    losses.add_series("Losses", (38, 24, 18, 12, 8))
    losses_chart = slide.shapes.add_chart(
        XL_CHART_TYPE.PIE,
        Inches(6.7), Inches(1.8), Inches(6.0), Inches(4.6),
        losses,
    ).chart
    series = losses_chart.series[0]
    for point, hexc in zip(series.points, PALETTE):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = hex_rgb(hexc)
    losses_chart.apply_quick_layout({
        "has_title": True, "title_text": "Why we lost (%)",
        "has_legend": True, "legend_position": XL_LEGEND_POSITION.RIGHT,
    })
    footer(slide, FOOTER, "7", TOKENS)


def _forecast(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Forecast", TOKENS)
    section_title(slide, "Q2 commit, best-case, and stretch", TOKENS)
    divider(slide, TOKENS)

    data = CategoryChartData()
    data.categories = ["Q1", "Q2 commit", "Q2 best", "Q2 stretch"]
    data.add_series("Bookings ($M)", (612, 632, 674, 718))
    data.add_series("Plan ($M)",     (588, 620, 620, 620))

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE,
        Inches(0.6), Inches(1.7), Inches(12.1), Inches(5.0),
        data,
    ).chart
    chart.apply_palette(PALETTE)
    chart.apply_quick_layout("title_legend_bottom")
    chart.chart_title.text_frame.text = "Q2 forecast vs. plan ($M)"
    footer(slide, FOOTER, "8", TOKENS)


def _asks(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Asks", TOKENS)
    section_title(slide, "What I need from this room", TOKENS)
    divider(slide, TOKENS)

    asks = [
        ("EMEA leadership change",
         "Decision on the EMEA AVP role by May 22 — slipping monthly."),
        ("Pricing exception authority",
         "Increase regional pricing committee threshold to $5M."),
        ("Specialist overlay for Strategic",
         "Three named overlays for Top 25 strategic accounts in Q2."),
        ("Marketing air-cover",
         "Two demand-gen waves in EMEA mid-market (€800k spend)."),
    ]
    for i, (head, body) in enumerate(asks):
        col = i % 2
        row = i // 2
        left = 0.6 + col * 6.2
        top = 1.85 + row * 2.3
        card = styled_card(slide, left, top, 6.05, 2.05,
                           tokens=TOKENS, fill_hex="#FFFFFF",
                           stroke_hex="#E5E7EB")
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Pt(18)
        tf.margin_top = tf.margin_bottom = Pt(16)
        tf.text = head
        p0 = tf.paragraphs[0]
        p0.font.name = TOKENS.typography["heading"].family
        p0.font.size = Pt(18)
        p0.font.bold = True
        p0.font.color.rgb = hex_rgb(TOKENS.palette["primary"])
        p1 = tf.add_paragraph()
        p1.text = body
        p1.space_before = Pt(8)
        p1.font.size = Pt(13)
        p1.font.color.rgb = hex_rgb(TOKENS.palette["muted"])
    footer(slide, FOOTER, "9", TOKENS)


if __name__ == "__main__":
    out = HERE / "_out" / "06_sales_qbr.pptx"
    out.parent.mkdir(exist_ok=True)
    build(out)
