"""08 — Operational Excellence Program Update.

Annual update on the company-wide ops transformation program. The
audience is the COO's staff plus business-unit GMs.

Slides:
    1. Cover
    2. Where we started, where we are (KPIs)
    3. Cost-out actions delivered (waterfall-style bar chart)
    4. OEE by site (table with conditional)
    5. Quality progress (line chart)
    6. Safety record (KPIs + bullets)
    7. Supply chain & inventory (column chart)
    8. People — black belts, green belts (bullets)
    9. FY27 commitments (table)
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from power_pptx.chart.data import CategoryChartData
from power_pptx.design.recipes import kpi_slide
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.enum.text import MSO_AUTO_SIZE, MSO_VERTICAL_ANCHOR
from power_pptx.util import Inches, Pt

from _brand import OPS as TOKENS, OPS_PALETTE as PALETTE
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

FOOTER = "Operational Excellence  |  FY26 Annual Update  |  Internal"


def build(out: Path) -> None:
    prs = new_deck()

    cover_slide(
        prs,
        eyebrow_text="Operational Excellence",
        title="From cost-out to capability.",
        subtitle="Year three of our enterprise operating system. "
                 "$314M of cumulative savings, 4.6 sigma quality, "
                 "and the industry's safest plant network.",
        presenter="Sandra Okolie, Chief Operating Officer",
        date="FY26 Annual Update  •  COO Staff",
        tokens=TOKENS,
    )

    kpi_slide(
        prs, title="Three years of compounding gains",
        kpis=[
            {"label": "Cumulative savings",    "value": "$314M", "delta": +0.34},
            {"label": "OEE (network-wide)",    "value": "82%",   "delta": +0.10},
            {"label": "DPMO (defects)",        "value": "1,820", "delta": -0.41},
            {"label": "TRIR (safety)",         "value": "0.42",  "delta": -0.36},
        ],
        tokens=TOKENS,
    )
    footer(prs.slides[-1], FOOTER, "2", TOKENS)

    _cost_out(prs)
    _oee_by_site(prs)
    _quality_progress(prs)
    _safety(prs)
    _supply_chain(prs)
    _people(prs)
    _commitments(prs)

    closing_slide(
        prs,
        headline="Operating systems compound.",
        sub="FY27 target: $390M cumulative savings  •  85% OEE  •  TRIR < 0.35",
        tokens=TOKENS,
    )

    lint_or_die(prs)
    prs.save(out)
    print(f"wrote {out}")


def _cost_out(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Cost-out", TOKENS)
    section_title(slide, "How we got from $148M to $314M cumulative", TOKENS)
    divider(slide, TOKENS)

    data = CategoryChartData()
    data.categories = ["FY24 base", "Procurement", "Lean / yield",
                       "Logistics", "Energy", "Automation", "FY26 total"]
    data.add_series("Cumulative savings ($M)",
                    (148, 184, 224, 248, 268, 298, 314))

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(0.6), Inches(1.7), Inches(8.5), Inches(5.0),
        data,
    ).chart
    series = chart.series[0]
    for point, hexc in zip(series.points, [
        TOKENS.palette["muted"], *PALETTE[:5], TOKENS.palette["primary"]
    ]):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = hex_rgb(hexc)
    chart.apply_quick_layout("title_no_legend")
    chart.chart_title.text_frame.text = "Cumulative savings build, FY24 → FY26 ($M)"

    card = styled_card(slide, 9.4, 1.7, 3.4, 5.0, tokens=TOKENS,
                       fill_hex=TOKENS.palette["surface"])
    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(18)
    tf.margin_top = tf.margin_bottom = Pt(18)
    tf.text = "Standout drivers"
    p = tf.paragraphs[0]
    p.font.name = TOKENS.typography["heading"].family
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = hex_rgb(TOKENS.palette["primary"])
    items = [
        ("Procurement",  "Strategic sourcing wave 3 — 6.4% unit-cost reduction."),
        ("Yield",        "Plant-7 first-pass yield from 88% to 94%."),
        ("Energy",       "Site-level PPAs cut energy spend 11% YoY."),
        ("Automation",   "13 robotic cells deployed; payback < 14 months."),
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


def _oee_by_site(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Plant performance", TOKENS)
    section_title(slide, "OEE by site — five hit target, two need attention", TOKENS)
    divider(slide, TOKENS)

    rows = [
        ("Site",            "Avail.", "Perf.", "Quality", "OEE",  "vs. Target", "Status"),
        ("Plant 1 — Pune",  "94%",    "92%",   "99.1%",   "85.7%","+0.7 pp",    "G"),
        ("Plant 2 — Monterrey","91%", "89%",   "98.7%",   "79.9%","−5.1 pp",    "R"),
        ("Plant 3 — Cleveland","95%", "93%",   "99.4%",   "87.7%","+2.7 pp",    "G"),
        ("Plant 4 — Lyon",  "92%",    "90%",   "99.0%",   "82.0%","−3.0 pp",    "A"),
        ("Plant 5 — Ulsan", "96%",    "94%",   "99.6%",   "89.8%","+4.8 pp",    "G"),
        ("Plant 6 — Riyadh","93%",    "91%",   "98.9%",   "83.6%","−1.4 pp",    "A"),
        ("Plant 7 — Greenville","94%","92%",   "99.2%",   "85.8%","+0.8 pp",    "G"),
    ]
    shape = slide.shapes.add_table(
        rows=len(rows), cols=7,
        left=Inches(0.6), top=Inches(1.7),
        width=Inches(12.1), height=Inches(4.7),
    )
    table = shape.table
    table.columns[0].width = Inches(3.0)
    for c in (1, 2, 3, 4): table.columns[c].width = Inches(1.4)
    table.columns[5].width = Inches(1.7)
    table.columns[6].width = Inches(1.6)

    table_header_row(table, rows[0], TOKENS)
    for r, row in enumerate(rows[1:], start=1):
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            if c == 6:
                status_cell(cell, *SITE_STATUS[value])
            else:
                _site_metric_cell(cell, r, c, value)
            cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
            hairline_below(cell)
    footer(slide, FOOTER, "4", TOKENS)


#: Site status code -> (label, fill) for the OEE table's status column.
SITE_STATUS = {
    "G": ("ON TARGET", TOKENS.palette["positive"]),
    "A": ("WATCH", "#F59E0B"),
    "R": ("BEHIND", TOKENS.palette["negative"]),
}


def _site_metric_cell(cell, r: int, c: int, value: str) -> None:
    """Bold site names, a coloured "vs. Target" delta, zebra-striped rows."""
    p = table_body_text(cell, value, TOKENS, size=11)
    if c == 0:
        p.font.bold = True
    if c == 5:
        color_delta(p, value, TOKENS)
    if r % 2 == 0:
        shade_cell(cell, TOKENS.palette["surface"])


def _quality_progress(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Quality", TOKENS)
    section_title(slide, "Defects-per-million down 41% over three years", TOKENS)
    divider(slide, TOKENS)

    data = CategoryChartData()
    data.categories = ["FY23 Q1", "Q2", "Q3", "Q4",
                       "FY24 Q1", "Q2", "Q3", "Q4",
                       "FY25 Q1", "Q2", "Q3", "Q4",
                       "FY26 Q1", "Q2", "Q3", "Q4"]
    data.add_series("DPMO",
                    (3120, 3050, 2940, 2880, 2780, 2620, 2510, 2440,
                     2350, 2280, 2150, 2080, 2010, 1940, 1890, 1820))

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE,
        Inches(0.6), Inches(1.7), Inches(12.1), Inches(5.0),
        data,
    ).chart
    chart.apply_palette([TOKENS.palette["primary"]])
    chart.apply_quick_layout("title_no_legend")
    chart.chart_title.text_frame.text = "Defects per million opportunities (DPMO)"
    footer(slide, FOOTER, "5", TOKENS)


def _safety(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Safety", TOKENS)
    section_title(slide, "Lowest TRIR in our industry — but not yet zero", TOKENS)
    divider(slide, TOKENS)

    kpis = [
        ("0.42", "Total Recordable Injury Rate"),
        ("0.08", "Lost-time injury rate"),
        ("0",    "Fatalities (3 yrs running)"),
        ("412",  "Days since last lost-time event (Plant 5)"),
    ]
    for i, (num, label) in enumerate(kpis):
        col = i % 2
        row = i // 2
        left = 0.6 + col * 3.05
        top = 1.85 + row * 1.7
        card = styled_card(slide, left, top, 2.95, 1.55,
                           tokens=TOKENS, fill_hex="#FFFFFF",
                           stroke_hex="#E5E7EB")
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Pt(14)
        tf.margin_top = Pt(12)
        tf.text = num
        p0 = tf.paragraphs[0]
        p0.font.name = TOKENS.typography["heading"].family
        p0.font.size = Pt(28)
        p0.font.bold = True
        p0.font.color.rgb = hex_rgb(TOKENS.palette["primary"])
        p1 = tf.add_paragraph()
        p1.text = label
        p1.space_before = Pt(2)
        p1.font.size = Pt(11)
        p1.font.color.rgb = hex_rgb(TOKENS.palette["muted"])

    box = slide.shapes.add_textbox(
        Inches(7.0), Inches(1.85), Inches(5.7), Inches(4.6),
    )
    tf = box.text_frame
    tf.word_wrap = True
    items = [
        ("Behaviour-based safety",  "Daily 5-minute pre-shift safety conversation rolled out at all 7 plants."),
        ("Critical-risk audits",    "Energy-isolation procedures audited 4× per shift; failures down 84%."),
        ("Visible felt leadership", "Plant managers walk the line minimum 2 hours per day; logged weekly."),
        ("Near-miss reporting",     "Up 220% — engaged workforce surfaces issues before they become events."),
    ]
    tf.text = items[0][0]
    p0 = tf.paragraphs[0]
    p0.font.name = TOKENS.typography["heading"].family
    p0.font.size = Pt(14)
    p0.font.bold = True
    p0.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
    p1 = tf.add_paragraph()
    p1.text = items[0][1]
    p1.font.size = Pt(11)
    p1.font.color.rgb = hex_rgb(TOKENS.palette["muted"])
    for h, b in items[1:]:
        p = tf.add_paragraph()
        p.text = h
        p.space_before = Pt(8)
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
        p2 = tf.add_paragraph()
        p2.text = b
        p2.font.size = Pt(11)
        p2.font.color.rgb = hex_rgb(TOKENS.palette["muted"])
    footer(slide, FOOTER, "6", TOKENS)


def _supply_chain(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Supply chain", TOKENS)
    section_title(slide, "Inventory turns up; on-time delivery up 6 pts", TOKENS)
    divider(slide, TOKENS)

    data = CategoryChartData()
    data.categories = ["FY23", "FY24", "FY25", "FY26"]
    data.add_series("Inventory turns",   (4.2, 4.5, 4.9, 5.4))
    data.add_series("On-time-in-full %", (88,  90,  93,  94))

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(0.6), Inches(1.7), Inches(12.1), Inches(5.0),
        data,
    ).chart
    chart.apply_palette([TOKENS.palette["primary"], TOKENS.palette["accent"]])
    chart.apply_quick_layout("title_legend_bottom")
    chart.chart_title.text_frame.text = "Supply-chain performance"
    footer(slide, FOOTER, "7", TOKENS)


def _people(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Capability", TOKENS)
    section_title(slide, "We're building operating-system fluency, not slogans", TOKENS)
    divider(slide, TOKENS)

    items = [
        ("412 Green Belts certified",
         "Active project portfolio worth $84M of run-rate savings."),
        ("38 Black Belts active",
         "Each leads multi-site initiatives ranging from $4M to $20M."),
        ("Daily management at every level",
         "Tier-1 huddle on the floor → Tier-4 review with the CEO every Friday."),
        ("Operating-system playbook",
         "Standardised across all 7 plants; transferred to Meridian post-close."),
        ("Frontline training",
         "120 hours / operator / year — up from 40 hours three years ago."),
    ]
    for i, (head, body) in enumerate(items):
        col = i % 2
        row = i // 2
        left = 0.6 + col * 6.2
        top = 1.85 + row * 1.55
        if i == 4:
            left = 0.6
            top = 4.95
        card = styled_card(slide, left, top, 6.05 if i < 4 else 12.1, 1.4,
                           tokens=TOKENS, fill_hex="#FFFFFF",
                           stroke_hex="#E5E7EB")
        tf = card.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        tf.margin_left = tf.margin_right = Pt(16)
        tf.margin_top = tf.margin_bottom = Pt(12)
        tf.text = head
        p0 = tf.paragraphs[0]
        p0.font.name = TOKENS.typography["heading"].family
        p0.font.size = Pt(16)
        p0.font.bold = True
        p0.font.color.rgb = hex_rgb(TOKENS.palette["primary"])
        p1 = tf.add_paragraph()
        p1.text = body
        p1.space_before = Pt(4)
        p1.font.size = Pt(12)
        p1.font.color.rgb = hex_rgb(TOKENS.palette["muted"])
    footer(slide, FOOTER, "8", TOKENS)


def _commitments(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "FY27", TOKENS)
    section_title(slide, "What we're signing up for next year", TOKENS)
    divider(slide, TOKENS)

    rows = [
        ("Metric",                "FY26 actual", "FY27 commit", "Owner"),
        ("Cumulative savings",    "$314M",       "$390M",        "Site GMs"),
        ("OEE network-wide",      "82%",         "85%",          "Plant Directors"),
        ("DPMO",                  "1,820",       "< 1,500",      "VP Quality"),
        ("TRIR",                  "0.42",        "< 0.35",       "VP EHS"),
        ("Inventory turns",       "5.4×",        "6.0×",         "VP Supply Chain"),
        ("On-time-in-full",       "94%",         "96%",          "VP Customer Ops"),
        ("Energy intensity",      "−11% YoY",    "−7% YoY",      "VP Sustainability"),
    ]
    shape = slide.shapes.add_table(
        rows=len(rows), cols=4,
        left=Inches(0.6), top=Inches(1.7),
        width=Inches(12.1), height=Inches(4.6),
    )
    table = shape.table
    table.columns[0].width = Inches(4.0)
    table.columns[1].width = Inches(2.7)
    table.columns[2].width = Inches(2.7)
    table.columns[3].width = Inches(2.7)

    for c, label in enumerate(rows[0]):
        cell = table.cell(0, c)
        cell.text = label
        cell.fill.solid()
        cell.fill.fore_color.rgb = hex_rgb(TOKENS.palette["primary"])
        p = cell.text_frame.paragraphs[0]
        p.font.bold = True
        p.font.size = Pt(13)
        p.font.color.rgb = hex_rgb(TOKENS.palette["on_primary"])
        cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
    for r, row in enumerate(rows[1:], start=1):
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            cell.text = value
            p = cell.text_frame.paragraphs[0]
            p.font.size = Pt(12)
            p.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
            if c == 0:
                p.font.bold = True
            if c == 2:
                p.font.bold = True
                p.font.color.rgb = hex_rgb(TOKENS.palette["primary"])
            cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
            if r % 2 == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = hex_rgb(TOKENS.palette["surface"])
            cell.borders.bottom.color.rgb = hex_rgb("#E5E7EB")
            cell.borders.bottom.width = Pt(0.5)
    footer(slide, FOOTER, "9", TOKENS)


if __name__ == "__main__":
    out = HERE / "_out" / "08_operational_excellence.pptx"
    out.parent.mkdir(exist_ok=True)
    build(out)
