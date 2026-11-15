"""09 — Talent & Workforce Strategy.

CHRO presents the annual people strategy to the executive committee.

Slides:
    1. Cover
    2. The state of the workforce (KPIs)
    3. Engagement & retention (line chart)
    4. Diversity representation (bar chart)
    5. Pay equity & compensation (table)
    6. Skills of the future (bullets)
    7. Leadership pipeline (table)
    8. Wellbeing & belonging (KPIs)
    9. Three asks of the executive
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from power_pptx.chart.data import CategoryChartData
from power_pptx.design.recipes import kpi_slide, quote_slide
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import MSO_VERTICAL_ANCHOR
from power_pptx.util import Inches, Pt

from _brand import PEOPLE as TOKENS, PEOPLE_PALETTE as PALETTE
from _common import (
    closing_slide,
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
    styled_card,
    table_body_text,
    table_header_row,
)

FOOTER = "FY27 Talent & Workforce Strategy  |  Executive Committee"


def build(out: Path) -> None:
    prs = new_deck()

    cover_slide(
        prs,
        eyebrow_text="Talent & Workforce Strategy",
        title="Our people are the\ncompounding asset.",
        subtitle="An honest read on engagement, representation, and "
                 "leadership — and the seven moves that earn us the "
                 "right to call ourselves a destination employer.",
        presenter="Lina Okafor, Chief Human Resources Officer",
        date="Executive Committee  •  FY27 Strategy Review",
        tokens=TOKENS,
    )

    kpi_slide(
        prs, title="Where we are today",
        kpis=[
            {"label": "Total employees",     "value": "62,400", "delta": +0.04},
            {"label": "Engagement (eNPS)",   "value": "+38",    "delta": +0.21},
            {"label": "Voluntary attrition", "value": "8.6%",   "delta": -0.27},
            {"label": "Internal mobility",   "value": "23%",    "delta": +0.31},
        ],
        tokens=TOKENS,
    )
    footer(prs.slides[-1], FOOTER, "2", TOKENS)

    _engagement(prs)
    _representation(prs)
    _pay_equity(prs)
    _skills(prs)
    _pipeline(prs)
    _wellbeing(prs)

    quote_slide(
        prs,
        quote="People don't leave companies, they leave bosses. "
              "Our number-one investment in FY27 is in the manager "
              "tier — because that's where engagement is made or lost.",
        attribution="Lina Okafor, CHRO",
        tokens=TOKENS,
    )
    footer(prs.slides[-1], FOOTER, "9", TOKENS)

    closing_slide(
        prs,
        headline="Be the place careers are made.",
        sub="Three asks. Three commitments. Three years.",
        tokens=TOKENS,
    )

    lint_or_die(prs)
    prs.save(out)
    print(f"wrote {out}")


def _engagement(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Engagement", TOKENS)
    section_title(slide, "eNPS up 21 points; attrition down to 8.6%", TOKENS)
    divider(slide, TOKENS)

    data = CategoryChartData()
    data.categories = ["Q1 FY25", "Q2", "Q3", "Q4",
                       "Q1 FY26", "Q2", "Q3", "Q4"]
    data.add_series("eNPS",                (12, 16, 20, 24, 28, 32, 35, 38))
    data.add_series("Voluntary attrition % (×4 scale)",
                                            (44, 42, 40, 38, 36, 35, 34, 34))

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE,
        Inches(0.6), Inches(1.7), Inches(12.1), Inches(5.0),
        data,
    ).chart
    chart.apply_palette([TOKENS.palette["primary"], TOKENS.palette["accent"]])
    chart.apply_quick_layout("title_legend_bottom")
    chart.chart_title.text_frame.text = "Engagement & retention trajectory"
    footer(slide, FOOTER, "3", TOKENS)


def _representation(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Representation", TOKENS)
    section_title(slide, "Movement at every level — and our gaps", TOKENS)
    divider(slide, TOKENS)

    data = CategoryChartData()
    data.categories = ["Frontline", "Manager", "Director", "VP+", "Officers"]
    data.add_series("FY24", (44, 38, 31, 24, 18))
    data.add_series("FY26", (47, 43, 37, 31, 27))
    data.add_series("FY29 target", (50, 50, 45, 40, 35))

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_CLUSTERED,
        Inches(0.6), Inches(1.7), Inches(8.5), Inches(5.0),
        data,
    ).chart
    chart.apply_palette([TOKENS.palette["muted"], TOKENS.palette["primary"], TOKENS.palette["accent"]])
    chart.apply_quick_layout("title_legend_bottom")
    chart.chart_title.text_frame.text = "Women in leadership (% of role)"

    card = styled_card(slide, 9.4, 1.7, 3.4, 5.0, tokens=TOKENS,
                       fill_hex=TOKENS.palette["surface"])
    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(18)
    tf.margin_top = tf.margin_bottom = Pt(18)
    tf.text = "Where we still need work"
    p = tf.paragraphs[0]
    p.font.name = TOKENS.typography["heading"].family
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = hex_rgb(TOKENS.palette["primary"])
    items = [
        ("VP+ pipeline", "8 pp gap to FY29 target — sponsor program needed."),
        ("Geographic",   "EMEA leadership representation lags US by 9 pp."),
        ("STEM technical","23% women in engineering — apprenticeship pilot to scale."),
        ("Disability",   "Self-ID at 4.1%; investing in psychological safety."),
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
    footer(slide, FOOTER, "4", TOKENS)


def _pay_equity(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Pay equity", TOKENS)
    section_title(slide, "Adjusted gender pay gap below 1% across all geos", TOKENS)
    divider(slide, TOKENS)

    rows = [
        ("Region",         "Unadjusted gap", "Adjusted gap", "Audit firm",  "Status"),
        ("North America",  "8.2%",           "0.6%",         "Mercer",      "Compliant"),
        ("EMEA",           "11.4%",          "0.9%",         "Mercer",      "Compliant"),
        ("APAC",           "9.8%",           "0.4%",         "Aon",         "Compliant"),
        ("LATAM",          "12.1%",          "1.2%",         "Aon",         "Action plan"),
        ("Network-wide",   "9.6%",           "0.7%",         "Independent", "Compliant"),
    ]
    shape = slide.shapes.add_table(
        rows=len(rows), cols=5,
        left=Inches(0.6), top=Inches(1.7),
        width=Inches(12.1), height=Inches(4.0),
    )
    table = shape.table
    table.columns[0].width = Inches(2.8)
    table.columns[1].width = Inches(2.7)
    table.columns[2].width = Inches(2.7)
    table.columns[3].width = Inches(2.0)
    table.columns[4].width = Inches(1.9)

    table_header_row(table, rows[0], TOKENS, size=13)
    for r, row in enumerate(rows[1:], start=1):
        for c, value in enumerate(row):
            _pay_gap_cell(table.cell(r, c), r, c, value)

    note = slide.shapes.add_textbox(
        Inches(0.6), Inches(5.85), Inches(12.1), Inches(0.6),
    )
    tf = note.text_frame
    tf.word_wrap = True
    tf.text = ("Adjusted gap controls for role, level, tenure, location, and performance. "
               "Independently audited annually; results published in our ESG report.")
    p = tf.paragraphs[0]
    p.font.size = Pt(10)
    p.font.italic = True
    p.font.color.rgb = hex_rgb(TOKENS.palette["muted"])
    footer(slide, FOOTER, "5", TOKENS)


NETWORK_WIDE_ROW = 5


def _pay_gap_cell(cell, r: int, c: int, value: str) -> None:
    """Bold regions and status; the network-wide total row highlighted."""
    p = table_body_text(cell, value, TOKENS)
    if c == 0 or r == NETWORK_WIDE_ROW:
        p.font.bold = True
    if c == 4:
        p.font.bold = True
        p.font.color.rgb = hex_rgb(
            TOKENS.palette["positive"] if value == "Compliant"
            else "#F59E0B"
        )
    cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
    if r % 2 == 0:
        shade_cell(cell, TOKENS.palette["surface"])
    if r == NETWORK_WIDE_ROW:
        shade_cell(cell, "#FCE7F3")
    hairline_below(cell)


def _skills(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Skills of the future", TOKENS)
    section_title(slide, "Six capabilities every team will need by FY29", TOKENS)
    divider(slide, TOKENS)

    skills = [
        ("AI fluency",     "Every employee uses AI safely in their daily work; technical builds on top of it."),
        ("Data literacy",  "Decision-making rooted in evidence — every manager passes our data baseline."),
        ("Customer-craft", "We hire and promote on demonstrated empathy and craftsmanship, not credentials."),
        ("Systems thinking","Engineers and operators trained to see — and improve — entire flows, not steps."),
        ("Sustainability", "Embedded in every product and process decision, not a side-bar function."),
        ("Inclusive leadership","Every people-leader certified in inclusive practices by FY28 H1."),
    ]
    cols = 3
    card_w = 4.05
    card_h = 2.45
    gap_x = 0.15
    gap_y = 0.2
    for i, (head, body) in enumerate(skills):
        col = i % cols
        row = i // cols
        left = 0.6 + col * (card_w + gap_x)
        top = 1.8 + row * (card_h + gap_y)
        card = styled_card(slide, left, top, card_w, card_h,
                           tokens=TOKENS, fill_hex="#FFFFFF",
                           stroke_hex="#E5E7EB")
        # Color band (shape gradient)
        band = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(left), Inches(top),
            Inches(card_w), Inches(0.12),
        )
        band.fill.solid()
        band.fill.fore_color.rgb = hex_rgb(PALETTE[i])
        band.line.fill.background()

        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Pt(16)
        tf.margin_top = Pt(20)
        tf.margin_bottom = Pt(14)
        tf.text = head
        p0 = tf.paragraphs[0]
        p0.font.name = TOKENS.typography["heading"].family
        p0.font.size = Pt(17)
        p0.font.bold = True
        p0.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
        p1 = tf.add_paragraph()
        p1.text = body
        p1.space_before = Pt(6)
        p1.font.size = Pt(11)
        p1.font.color.rgb = hex_rgb(TOKENS.palette["muted"])
    footer(slide, FOOTER, "6", TOKENS)


def _pipeline(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Leadership pipeline", TOKENS)
    section_title(slide, "Bench depth — ready-now and ready-soon", TOKENS)
    divider(slide, TOKENS)

    rows = [
        ("Tier",                "Ready-now", "Ready-soon", "Risk roles", "Bench ratio"),
        ("CEO direct reports",  "2 of 12",   "5 of 12",    "1",          "0.58"),
        ("VP / SVP",            "32 of 88",  "61 of 88",   "8",          "1.06"),
        ("Director",            "94 of 312", "188 of 312", "11",         "0.90"),
        ("Senior Manager",      "210 of 740","380 of 740", "19",         "0.80"),
    ]
    shape = slide.shapes.add_table(
        rows=len(rows), cols=5,
        left=Inches(0.6), top=Inches(1.7),
        width=Inches(12.1), height=Inches(3.6),
    )
    table = shape.table
    table.columns[0].width = Inches(3.4)
    for c in (1, 2, 3, 4): table.columns[c].width = Inches(2.175)

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
            cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
            if r % 2 == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = hex_rgb(TOKENS.palette["surface"])
            cell.borders.bottom.color.rgb = hex_rgb("#E5E7EB")
            cell.borders.bottom.width = Pt(0.5)

    box = slide.shapes.add_textbox(
        Inches(0.6), Inches(5.5), Inches(12.1), Inches(1.4),
    )
    tf = box.text_frame
    tf.word_wrap = True
    tf.text = ("CEO direct-report bench remains the fragile tier. We are running an "
               "external slate alongside three internal candidates for two roles, "
               "and have committed sponsors for the eight high-potential VPs.")
    tf.fit_text(font_family=TOKENS.typography["body"].family,
                max_size=15, bold=False)
    tf.paragraphs[0].font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
    footer(slide, FOOTER, "7", TOKENS)


def _wellbeing(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Wellbeing & belonging", TOKENS)
    section_title(slide, "Where the work-experience numbers stand", TOKENS)
    divider(slide, TOKENS)

    kpis = [
        ("87%",  "agree manager cares about wellbeing"),
        ("82%",  "agree they belong"),
        ("4.6", "Glassdoor (out of 5)"),
        ("63%",  "use mental-health benefits annually"),
        ("$48M", "annual wellbeing investment"),
        ("12 wk", "fully paid family leave (all geos)"),
    ]
    cols = 3
    card_w = 4.05
    card_h = 2.45
    gap_x = 0.15
    gap_y = 0.2
    for i, (num, label) in enumerate(kpis):
        col = i % cols
        row = i // cols
        left = 0.6 + col * (card_w + gap_x)
        top = 1.8 + row * (card_h + gap_y)
        card = styled_card(slide, left, top, card_w, card_h,
                           tokens=TOKENS, fill_hex="#FFFFFF",
                           stroke_hex="#E5E7EB")
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Pt(18)
        tf.margin_top = Pt(20)
        tf.text = num
        p0 = tf.paragraphs[0]
        p0.font.name = TOKENS.typography["heading"].family
        p0.font.size = Pt(40)
        p0.font.bold = True
        p0.font.color.rgb = hex_rgb(PALETTE[i % len(PALETTE)])
        p1 = tf.add_paragraph()
        p1.text = label
        p1.space_before = Pt(6)
        p1.font.size = Pt(13)
        p1.font.color.rgb = hex_rgb(TOKENS.palette["muted"])
    footer(slide, FOOTER, "8", TOKENS)


if __name__ == "__main__":
    out = HERE / "_out" / "09_talent_strategy.pptx"
    out.parent.mkdir(exist_ok=True)
    build(out)
