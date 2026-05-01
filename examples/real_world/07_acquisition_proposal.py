"""07 — M&A Acquisition Proposal: Project Blueprint.

Recommendation deck presented to the M&A committee for approval to
proceed to definitive agreement.

Slides:
    1. Cover
    2. Executive summary
    3. Strategic rationale (3 pillars)
    4. Target overview (KPIs)
    5. Financial profile (column chart)
    6. Synergy plan (table)
    7. Valuation (table)
    8. Diligence findings (table with conditional)
    9. Integration plan (timeline)
    10. Recommendation
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from power_pptx.chart.data import CategoryChartData
from power_pptx.design.recipes import kpi_slide
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import MSO_AUTO_SIZE, MSO_VERTICAL_ANCHOR, PP_ALIGN
from power_pptx.util import Inches, Pt

from _brand import MERGER as TOKENS, MERGER_PALETTE as PALETTE
from _common import (
    closing_slide,
    cover_slide,
    divider,
    eyebrow,
    footer,
    hex_rgb,
    lint_or_die,
    new_deck,
    section_title,
    styled_card,
)

FOOTER = "Project Blueprint  |  Strictly confidential — M&A Committee"


def build(out: Path) -> None:
    prs = new_deck()

    cover_slide(
        prs,
        eyebrow_text="Project Blueprint",
        title="Recommendation:\nProceed to definitive agreement.",
        subtitle="Acquisition of Meridian Composites — strategically "
                 "accretive, culturally compatible, and underwritten "
                 "to a 14% IRR base case.",
        presenter="Corporate Development & Strategy",
        date="M&A Committee  •  May 7, 2026",
        tokens=TOKENS,
    )

    _executive_summary(prs)
    _strategic_rationale(prs)

    kpi_slide(
        prs, title="Meridian Composites — at a glance",
        kpis=[
            {"label": "FY26 revenue",     "value": "$486M", "delta": +0.18},
            {"label": "EBITDA margin",    "value": "23.4%", "delta": +0.04},
            {"label": "Customer overlap", "value": "37%",   "delta": +0.10},
            {"label": "Headcount",        "value": "1,840", "delta": +0.06},
        ],
        tokens=TOKENS,
    )
    footer(prs.slides[-1], FOOTER, "4", TOKENS)

    _financial_profile(prs)
    _synergies(prs)
    _valuation(prs)
    _diligence(prs)
    _integration(prs)

    closing_slide(
        prs,
        headline="Approve to proceed.",
        sub="Definitive agreement targeted for signing on June 14, 2026.",
        tokens=TOKENS,
    )

    lint_or_die(prs)
    prs.save(out)
    print(f"wrote {out}")


def _executive_summary(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Executive summary", TOKENS)
    section_title(slide, "Why Meridian, why now, and what it costs us", TOKENS)
    divider(slide, TOKENS)

    bullets = [
        ("What",     "Acquire 100% of Meridian Composites for $1.84B in cash."),
        ("Why now",  "Founder retirement creates a window; two strategic buyers are circling."),
        ("Strategic","Closes the highest-margin gap in our materials portfolio; opens aerospace OEM channels."),
        ("Financial","23.4% EBITDA, $58M of identified run-rate synergies; accretive in year 2."),
        ("Risk",     "Two key person dependencies; 18-month carve-out from European parent."),
    ]
    for i, (head, body) in enumerate(bullets):
        top = 1.8 + i * 0.95
        # Tab marker
        tab = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(top + 0.1),
            Inches(0.08), Inches(0.65),
        )
        tab.fill.solid()
        tab.fill.fore_color.rgb = hex_rgb(TOKENS.palette["primary"])
        tab.line.fill.background()

        tb = slide.shapes.add_textbox(
            Inches(0.85), Inches(top), Inches(11.8), Inches(0.85),
        )
        tf = tb.text_frame
        tf.word_wrap = True
        tf.text = head
        p0 = tf.paragraphs[0]
        p0.font.name = TOKENS.typography["heading"].family
        p0.font.size = Pt(15)
        p0.font.bold = True
        p0.font.color.rgb = hex_rgb(TOKENS.palette["primary"])
        p1 = tf.add_paragraph()
        p1.text = body
        p1.font.name = TOKENS.typography["body"].family
        p1.font.size = Pt(13)
        p1.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
    footer(slide, FOOTER, "2", TOKENS)


def _strategic_rationale(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Strategic rationale", TOKENS)
    section_title(slide, "Three reasons this deal compounds value", TOKENS)
    divider(slide, TOKENS)

    pillars = [
        ("Portfolio",
         "Closes a $400M revenue gap in advanced composites and lifts portfolio margin by 60 bps."),
        ("Channel",
         "Tier-1 aerospace OEM relationships unlock cross-sell of our existing alloy portfolio."),
        ("Talent",
         "Inherits a 230-person R&D bench specialised in carbon-fibre process engineering."),
    ]
    for i, (head, body) in enumerate(pillars):
        left = 0.6 + i * 4.2
        card = styled_card(slide, left, 1.85, 4.05, 4.7,
                           tokens=TOKENS, fill_hex="#FFFFFF",
                           stroke_hex="#E5E7EB")
        # Top color band
        band = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(left), Inches(1.85),
            Inches(4.05), Inches(0.16),
        )
        band.fill.solid()
        band.fill.fore_color.rgb = hex_rgb(PALETTE[i])
        band.line.fill.background()

        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Pt(20)
        tf.margin_top = Pt(28)
        tf.margin_bottom = Pt(20)
        tf.text = head
        p0 = tf.paragraphs[0]
        p0.font.name = TOKENS.typography["heading"].family
        p0.font.size = Pt(24)
        p0.font.bold = True
        p0.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
        p1 = tf.add_paragraph()
        p1.text = body
        p1.space_before = Pt(10)
        p1.font.name = TOKENS.typography["body"].family
        p1.font.size = Pt(14)
        p1.font.color.rgb = hex_rgb(TOKENS.palette["muted"])
    footer(slide, FOOTER, "3", TOKENS)


def _financial_profile(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Financial profile", TOKENS)
    section_title(slide, "Five-year track record — durable growth, expanding margin", TOKENS)
    divider(slide, TOKENS)

    data = CategoryChartData()
    data.categories = ["FY22", "FY23", "FY24", "FY25", "FY26"]
    data.add_series("Revenue ($M)", (242, 286, 348, 412, 486))
    data.add_series("EBITDA ($M)",  (44,  58,  72,  92,  114))

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(0.6), Inches(1.7), Inches(8.4), Inches(5.0),
        data,
    ).chart
    chart.apply_palette([TOKENS.palette["primary"], TOKENS.palette["positive"]])
    chart.apply_quick_layout("title_legend_bottom")
    chart.chart_title.text_frame.text = "Meridian — revenue and EBITDA ($M)"

    card = styled_card(slide, 9.3, 1.7, 3.5, 5.0, tokens=TOKENS,
                       fill_hex=TOKENS.palette["surface"])
    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(18)
    tf.margin_top = tf.margin_bottom = Pt(18)
    tf.text = "Quality of earnings"
    p = tf.paragraphs[0]
    p.font.name = TOKENS.typography["heading"].family
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = hex_rgb(TOKENS.palette["primary"])
    items = [
        ("Recurring revenue", "62% under multi-year service agreements."),
        ("Customer concentration", "Top 10 = 38% of revenue (down from 51%)."),
        ("Working capital",   "DSO 47 d, DIO 71 d — best-in-class."),
        ("CapEx intensity",   "5.4% of revenue, well within our envelope."),
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
    footer(slide, FOOTER, "5", TOKENS)


def _synergies(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Value creation", TOKENS)
    section_title(slide, "$58M run-rate synergy by year 3", TOKENS)
    divider(slide, TOKENS)

    rows = [
        ("Synergy",                  "Run-rate ($M)", "Realisation",     "Confidence"),
        ("Procurement consolidation",     "$18M",     "Y1 H2",            "High"),
        ("Manufacturing footprint",       "$14M",     "Y2",               "Medium"),
        ("Cross-sell to aerospace OEMs",  "$12M",     "Y2 H2 onward",     "Medium"),
        ("Combined R&D rationalisation",  "$8M",      "Y2 H2",            "High"),
        ("G&A rationalisation",           "$6M",      "Y1",               "High"),
    ]
    shape = slide.shapes.add_table(
        rows=len(rows), cols=4,
        left=Inches(0.6), top=Inches(1.7),
        width=Inches(12.1), height=Inches(4.2),
    )
    table = shape.table
    table.columns[0].width = Inches(5.5)
    table.columns[1].width = Inches(2.0)
    table.columns[2].width = Inches(2.4)
    table.columns[3].width = Inches(2.2)

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

    confidence_color = {"High": TOKENS.palette["positive"], "Medium": "#F59E0B", "Low": TOKENS.palette["negative"]}
    for r, row in enumerate(rows[1:], start=1):
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            cell.text = value
            p = cell.text_frame.paragraphs[0]
            p.font.size = Pt(12)
            p.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
            if c == 0:
                p.font.bold = True
            if c == 1:
                p.font.bold = True
                p.alignment = PP_ALIGN.RIGHT
            if c == 3:
                p.font.bold = True
                p.font.color.rgb = hex_rgb(confidence_color.get(value, TOKENS.palette["neutral"]))
            cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
            if r % 2 == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = hex_rgb(TOKENS.palette["surface"])
            cell.borders.bottom.color.rgb = hex_rgb("#E5E7EB")
            cell.borders.bottom.width = Pt(0.5)

    note = slide.shapes.add_textbox(
        Inches(0.6), Inches(6.1), Inches(12.1), Inches(0.5),
    )
    tf = note.text_frame
    tf.text = "One-time integration costs estimated at $48M, fully expensed in years 1–2."
    p = tf.paragraphs[0]
    p.font.size = Pt(10)
    p.font.italic = True
    p.font.color.rgb = hex_rgb(TOKENS.palette["muted"])
    footer(slide, FOOTER, "6", TOKENS)


def _valuation(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Valuation", TOKENS)
    section_title(slide, "Underwritten to a 14% IRR base case", TOKENS)
    divider(slide, TOKENS)

    rows = [
        ("Metric",                     "Bear",    "Base",    "Bull"),
        ("Purchase price",             "$1.84B",  "$1.84B",  "$1.84B"),
        ("Year-3 revenue",             "$610M",   "$680M",   "$760M"),
        ("Year-3 EBITDA",              "$130M",   "$172M",   "$220M"),
        ("Synergies (run-rate)",       "$42M",    "$58M",    "$72M"),
        ("Year-5 exit multiple",       "11.0×",   "12.5×",   "14.0×"),
        ("IRR (5-year)",               "9.1%",    "14.2%",   "20.4%"),
        ("MOIC",                       "1.5×",    "1.9×",    "2.5×"),
    ]
    shape = slide.shapes.add_table(
        rows=len(rows), cols=4,
        left=Inches(0.6), top=Inches(1.7),
        width=Inches(12.1), height=Inches(4.6),
    )
    table = shape.table
    table.columns[0].width = Inches(4.6)
    for c in (1, 2, 3): table.columns[c].width = Inches(2.5)

    for c, label in enumerate(rows[0]):
        cell = table.cell(0, c)
        cell.text = label
        cell.fill.solid()
        cell.fill.fore_color.rgb = hex_rgb(TOKENS.palette["primary"])
        p = cell.text_frame.paragraphs[0]
        p.font.bold = True
        p.font.size = Pt(13)
        p.font.color.rgb = hex_rgb(TOKENS.palette["on_primary"])
        if c == 2:
            cell.fill.fore_color.rgb = hex_rgb(TOKENS.palette["accent"])
            p.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
        p.alignment = PP_ALIGN.CENTER if c > 0 else PP_ALIGN.LEFT
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
            else:
                p.alignment = PP_ALIGN.CENTER
            if c == 2:
                p.font.bold = True
                cell.fill.solid()
                cell.fill.fore_color.rgb = hex_rgb("#F9F4DC")
            cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
            if r % 2 == 0 and c != 2:
                cell.fill.solid()
                cell.fill.fore_color.rgb = hex_rgb(TOKENS.palette["surface"])
            cell.borders.bottom.color.rgb = hex_rgb("#E5E7EB")
            cell.borders.bottom.width = Pt(0.5)
    footer(slide, FOOTER, "7", TOKENS)


def _diligence(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Diligence findings", TOKENS)
    section_title(slide, "Workstream summary — green / amber, no red", TOKENS)
    divider(slide, TOKENS)

    rows = [
        ("Workstream",  "Lead",                "Status", "Headline finding"),
        ("Commercial",  "Bain",                "Green",  "Pipeline coverage validated; customer references strong."),
        ("Financial",   "PwC",                 "Green",  "Quality of earnings clean; modest working-capital adjustment."),
        ("Tax",         "EY",                  "Green",  "No material exposures; transfer-pricing position defensible."),
        ("Legal",       "Cleary",              "Amber",  "EU parent carve-out adds 6 weeks; mitigated via TSA."),
        ("Tech / Cyber","Internal + Mandiant", "Amber",  "OT estate needs $14M of remediation; included in synergies."),
        ("HR / Culture","Mercer",              "Green",  "Engagement 76 (high); attrition 9% (industry avg 14%)."),
        ("ESG",         "Internal",            "Green",  "Scope 1+2 trajectory aligned with our SBTi commitments."),
    ]
    shape = slide.shapes.add_table(
        rows=len(rows), cols=4,
        left=Inches(0.6), top=Inches(1.7),
        width=Inches(12.1), height=Inches(4.6),
    )
    table = shape.table
    table.columns[0].width = Inches(2.0)
    table.columns[1].width = Inches(2.4)
    table.columns[2].width = Inches(1.4)
    table.columns[3].width = Inches(6.3)

    for c, label in enumerate(rows[0]):
        cell = table.cell(0, c)
        cell.text = label
        cell.fill.solid()
        cell.fill.fore_color.rgb = hex_rgb(TOKENS.palette["primary"])
        p = cell.text_frame.paragraphs[0]
        p.font.bold = True
        p.font.size = Pt(12)
        p.font.color.rgb = hex_rgb(TOKENS.palette["on_primary"])
        cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE

    status_bg = {"Green": TOKENS.palette["positive"], "Amber": "#F59E0B", "Red": TOKENS.palette["negative"]}
    for r, row in enumerate(rows[1:], start=1):
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            if c == 2:
                cell.text = value.upper()
                cell.fill.solid()
                cell.fill.fore_color.rgb = hex_rgb(status_bg[value])
                p = cell.text_frame.paragraphs[0]
                p.font.size = Pt(11)
                p.font.bold = True
                p.font.color.rgb = hex_rgb("#FFFFFF")
                p.alignment = PP_ALIGN.CENTER
            else:
                cell.text = value
                p = cell.text_frame.paragraphs[0]
                p.font.size = Pt(11)
                p.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
                if c == 0:
                    p.font.bold = True
                if r % 2 == 0:
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = hex_rgb(TOKENS.palette["surface"])
            cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
            cell.borders.bottom.color.rgb = hex_rgb("#E5E7EB")
            cell.borders.bottom.width = Pt(0.5)
    footer(slide, FOOTER, "8", TOKENS)


def _integration(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Integration", TOKENS)
    section_title(slide, "100-day plan and 18-month roadmap", TOKENS)
    divider(slide, TOKENS)

    # Timeline bar
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0.7), Inches(3.7), Inches(11.9), Inches(0.06),
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = hex_rgb(TOKENS.palette["muted"])
    bar.line.fill.background()

    phases = [
        ("Day 1",     "Day-1 readiness, leadership announce, IT first connections.",   "May 2026"),
        ("Day 100",   "Synergy plan finalised, retention agreements, brand decisions.","Aug 2026"),
        ("Month 9",   "Procurement migration complete; first cross-sell wins booked.", "Feb 2027"),
        ("Month 18",  "Plant footprint moves complete; full systems migration done.",  "Nov 2027"),
    ]
    width = 2.95
    for i, (label, body, when) in enumerate(phases):
        left = 0.7 + i * 3.0
        # Marker dot on timeline
        dot = slide.shapes.add_shape(
            MSO_SHAPE.OVAL,
            Inches(left + width / 2 - 0.15), Inches(3.62),
            Inches(0.3), Inches(0.3),
        )
        dot.fill.solid()
        dot.fill.fore_color.rgb = hex_rgb(PALETTE[i])
        dot.line.color.rgb = hex_rgb("#FFFFFF")
        dot.line.width = Pt(2)

        # Label above
        upper = slide.shapes.add_textbox(
            Inches(left), Inches(2.0), Inches(width), Inches(1.5),
        )
        tf = upper.text_frame
        tf.word_wrap = True
        tf.text = label
        p0 = tf.paragraphs[0]
        p0.alignment = PP_ALIGN.CENTER
        p0.font.name = TOKENS.typography["heading"].family
        p0.font.size = Pt(20)
        p0.font.bold = True
        p0.font.color.rgb = hex_rgb(PALETTE[i])
        p1 = tf.add_paragraph()
        p1.text = when
        p1.alignment = PP_ALIGN.CENTER
        p1.font.size = Pt(11)
        p1.font.color.rgb = hex_rgb(TOKENS.palette["muted"])

        # Detail below
        lower = slide.shapes.add_textbox(
            Inches(left), Inches(4.2), Inches(width), Inches(2.4),
        )
        tf = lower.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        tf.text = body
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        p.font.size = Pt(13)
        p.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
    footer(slide, FOOTER, "9", TOKENS)


if __name__ == "__main__":
    out = HERE / "_out" / "07_acquisition_proposal.pptx"
    out.parent.mkdir(exist_ok=True)
    build(out)
