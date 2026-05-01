"""10 — Integrated Marketing Campaign Strategy.

CMO presents the integrated annual brand and demand campaign to the
executive committee for approval and budget commit.

Slides:
    1. Cover
    2. The brief (KPIs)
    3. Audience segmentation (pie)
    4. The big idea (large quote slide)
    5. Channel mix (bar chart)
    6. Always-on funnel (3-stage)
    7. Phased calendar (gantt-style)
    8. Forecast & ROI (line chart)
    9. Investment by quarter (column)
    10. Asks
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from power_pptx.chart.data import CategoryChartData
from power_pptx.design.recipes import kpi_slide
from power_pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from power_pptx.enum.presentation import MSO_TRANSITION_TYPE
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import MSO_AUTO_SIZE, MSO_VERTICAL_ANCHOR, PP_ALIGN
from power_pptx.util import Inches, Pt

from _brand import MARKETING as TOKENS, MARKETING_PALETTE as PALETTE
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

FOOTER = "FY27 Integrated Campaign  |  Confidential"


def build(out: Path) -> None:
    prs = new_deck()

    cover_slide(
        prs,
        eyebrow_text="FY27 Integrated Campaign",
        title="Made for the\nmovers.",
        subtitle="A year-long brand-and-demand campaign designed to "
                 "shift consideration with operators and CFOs in our "
                 "five highest-priority verticals.",
        presenter="Marielle Nguyen, Chief Marketing Officer",
        date="Executive Committee  •  Budget Approval  •  May 2026",
        tokens=TOKENS,
    )

    kpi_slide(
        prs, title="The brief — what we're investing for",
        kpis=[
            {"label": "Aided brand awareness", "value": "+8 pts", "delta": +0.20},
            {"label": "Pipeline contribution", "value": "$640M",  "delta": +0.32},
            {"label": "Marketing ROI",         "value": "5.4×",   "delta": +0.18},
            {"label": "CAC payback",           "value": "11 mo",  "delta": -0.12},
        ],
        tokens=TOKENS,
    )
    footer(prs.slides[-1], FOOTER, "2", TOKENS)

    _segmentation(prs)
    big_idea_slide = _big_idea(prs)
    _channel_mix(prs)
    _funnel(prs)
    _calendar(prs)
    _forecast(prs)
    _asks(prs)

    closing_slide(
        prs,
        headline="Movers, this is for you.",
        sub="Approve the $84M investment for FY27. Let's go win the consideration set.",
        tokens=TOKENS,
    )

    # Apply the deck-wide fade FIRST, then override the big-idea slide
    # with Morph — set_transition iterates every slide and would otherwise
    # clobber the per-slide override.
    prs.set_transition(kind=MSO_TRANSITION_TYPE.FADE, duration=400)
    big_idea_slide.transition.kind = MSO_TRANSITION_TYPE.MORPH
    big_idea_slide.transition.duration = 1200

    lint_or_die(prs)
    prs.save(out)
    print(f"wrote {out}")


def _segmentation(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Audience", TOKENS)
    section_title(slide, "Who we're talking to — and in what proportion", TOKENS)
    divider(slide, TOKENS)

    data = CategoryChartData()
    data.categories = [
        "Enterprise CIO/CTO",
        "Enterprise CFO",
        "Mid-market COO",
        "VP Engineering",
        "VP Operations",
        "Practitioner / dev",
    ]
    data.add_series("Spend share", (28, 22, 16, 14, 12, 8))
    chart_shape = slide.shapes.add_chart(
        XL_CHART_TYPE.PIE,
        Inches(0.6), Inches(1.7), Inches(7.2), Inches(5.0),
        data,
    )
    chart = chart_shape.chart
    series = chart.series[0]
    for point, hexc in zip(series.points, PALETTE):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = hex_rgb(hexc)
    chart.apply_quick_layout({
        "has_title": True, "title_text": "FY27 spend share by audience (%)",
        "has_legend": True, "legend_position": XL_LEGEND_POSITION.RIGHT,
    })

    card = styled_card(slide, 8.0, 1.7, 4.7, 5.0, tokens=TOKENS,
                       fill_hex=TOKENS.palette["surface"])
    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(20)
    tf.margin_top = tf.margin_bottom = Pt(20)
    tf.text = "Segmentation logic"
    p = tf.paragraphs[0]
    p.font.name = TOKENS.typography["heading"].family
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = hex_rgb(TOKENS.palette["primary"])
    items = [
        ("Investment follows revenue", "73% of FY27 pipeline sits in the top three personas."),
        ("Frequency over reach",       "Mid-market COO is highest-LTV but smallest universe — go heavy."),
        ("Always-on practitioner",     "Developer audience runs continuously to fuel bottoms-up motion."),
        ("Buying group, not buyer",    "Activate three roles per account in parallel — no single-threaded plays."),
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


def _big_idea(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5),
    )
    bg.fill.linear_gradient(
        TOKENS.palette["primary"], TOKENS.palette["accent"], angle=135,
    )
    bg.line.fill.background()

    eb = slide.shapes.add_textbox(
        Inches(0.8), Inches(0.9), Inches(11.7), Inches(0.5),
    )
    tf = eb.text_frame
    tf.text = "THE BIG IDEA"
    p = tf.paragraphs[0]
    p.font.size = Pt(13)
    p.font.bold = True
    p.font.color.rgb = hex_rgb("#FFFFFF")
    p.font.color.alpha = 0.85

    head = slide.shapes.add_textbox(
        Inches(0.8), Inches(1.7), Inches(11.7), Inches(3.5),
    )
    tf = head.text_frame
    tf.word_wrap = True
    tf.text = "We don't sell software.\nWe back the people who move things."
    tf.fit_text(font_family=TOKENS.typography["heading"].family,
                max_size=58, bold=True)
    tf.paragraphs[0].font.color.rgb = hex_rgb("#FFFFFF")

    sub = slide.shapes.add_textbox(
        Inches(0.8), Inches(5.4), Inches(11.7), Inches(1.5),
    )
    tf = sub.text_frame
    tf.word_wrap = True
    tf.text = ("Our customers move shipments, decisions, money, and people. "
               "Our brand promise: every product we ship saves them an hour, "
               "a dollar, or a difficult conversation.")
    tf.fit_text(font_family=TOKENS.typography["body"].family,
                max_size=20, bold=False)
    tf.paragraphs[0].font.color.rgb = hex_rgb("#FFFFFF")
    tf.paragraphs[0].font.color.alpha = 0.92

    # Caller applies the Morph override AFTER the deck-wide set_transition.
    return slide


def _channel_mix(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Channel mix", TOKENS)
    section_title(slide, "Where the $84M goes", TOKENS)
    divider(slide, TOKENS)

    data = CategoryChartData()
    data.categories = [
        "Connected TV / video", "Search & social",
        "Field & events", "Content & PR",
        "Influencer / community", "Partner co-marketing",
        "Out-of-home & print",
    ]
    data.add_series("FY27 budget ($M)", (18, 16, 14, 12, 10, 8, 6))

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_CLUSTERED,
        Inches(0.6), Inches(1.7), Inches(8.5), Inches(5.0),
        data,
    ).chart
    series = chart.series[0]
    for i, point in enumerate(series.points):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = hex_rgb(PALETTE[i % len(PALETTE)])
    chart.apply_quick_layout("title_no_legend")
    chart.chart_title.text_frame.text = "FY27 spend by channel ($M)"

    card = styled_card(slide, 9.4, 1.7, 3.4, 5.0, tokens=TOKENS,
                       fill_hex=TOKENS.palette["surface"])
    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(18)
    tf.margin_top = tf.margin_bottom = Pt(18)
    tf.text = "What's different"
    p = tf.paragraphs[0]
    p.font.name = TOKENS.typography["heading"].family
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = hex_rgb(TOKENS.palette["primary"])
    items = [
        ("CTV up 80%",     "Reach our CFO + COO targets where they are."),
        ("Field rebalanced","Two flagship events; tighter, more sponsored."),
        ("Influencer 2×",  "Practitioner trust > banner ads. Always-on creator network."),
        ("OOH targeted",   "Five business-district takeovers around fly-in events."),
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


def _funnel(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Funnel architecture", TOKENS)
    section_title(slide, "Three stages, always on, measured weekly", TOKENS)
    divider(slide, TOKENS)

    stages = [
        ("Awareness",
         "CTV, OOH, audio, sponsored content. Brand-led storytelling.",
         "Aided awareness +8 pts; share-of-voice 24%",
         PALETTE[0]),
        ("Consideration",
         "Webinars, analyst-led research, customer panels. Mid-funnel POV.",
         "Engaged accounts 8,400/qtr; MQL→SQL 32%",
         PALETTE[1]),
        ("Conversion",
         "ABM plays, demos, partner co-marketing. Sales activation.",
         "Pipeline $640M; close-won 31%",
         PALETTE[2]),
    ]
    width = 4.05
    gap = 0.15
    for i, (head, body, kpi, color) in enumerate(stages):
        left = 0.6 + i * (width + gap)
        card = styled_card(slide, left, 1.85, width, 4.7,
                           tokens=TOKENS, fill_hex="#FFFFFF",
                           stroke_hex="#E5E7EB")
        # Top color band
        band = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(left), Inches(1.85),
            Inches(width), Inches(0.16),
        )
        band.fill.solid()
        band.fill.fore_color.rgb = hex_rgb(color)
        band.line.fill.background()

        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Pt(18)
        tf.margin_top = Pt(28)
        tf.margin_bottom = Pt(18)
        tf.text = head
        p0 = tf.paragraphs[0]
        p0.font.name = TOKENS.typography["heading"].family
        p0.font.size = Pt(22)
        p0.font.bold = True
        p0.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
        p1 = tf.add_paragraph()
        p1.text = body
        p1.space_before = Pt(8)
        p1.font.size = Pt(13)
        p1.font.color.rgb = hex_rgb(TOKENS.palette["muted"])
        p2 = tf.add_paragraph()
        p2.text = "KPIs"
        p2.space_before = Pt(14)
        p2.font.size = Pt(10)
        p2.font.bold = True
        p2.font.color.rgb = hex_rgb(color)
        p3 = tf.add_paragraph()
        p3.text = kpi
        p3.font.size = Pt(12)
        p3.font.bold = True
        p3.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
    footer(slide, FOOTER, "6", TOKENS)


def _calendar(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Calendar", TOKENS)
    section_title(slide, "Five tentpoles, four always-on tracks", TOKENS)
    divider(slide, TOKENS)

    # Header row
    quarters = ["Q1", "Q2", "Q3", "Q4"]
    track_left = 0.6
    track_top = 1.8
    label_w = 2.6
    bar_total_w = 9.5
    qw = bar_total_w / 4

    for i, q in enumerate(quarters):
        tb = slide.shapes.add_textbox(
            Inches(track_left + label_w + i * qw), Inches(track_top),
            Inches(qw), Inches(0.4),
        )
        tf = tb.text_frame
        tf.text = q
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.color.rgb = hex_rgb(TOKENS.palette["muted"])

    rows = [
        ("Tentpole — Brand launch",  0,   1, PALETTE[0]),
        ("Tentpole — Atlas event",   1.8, 0.6, PALETTE[1]),
        ("Tentpole — Holiday demand",3.0, 0.9, PALETTE[2]),
        ("Always-on — Search/social",0,   4,   PALETTE[3]),
        ("Always-on — Practitioner", 0,   4,   PALETTE[4]),
        ("Always-on — ABM",          0,   4,   PALETTE[5]),
    ]
    for r, (label, start_q, dur, color) in enumerate(rows):
        top = track_top + 0.6 + r * 0.7
        # Label
        tb = slide.shapes.add_textbox(
            Inches(track_left), Inches(top),
            Inches(label_w - 0.1), Inches(0.55),
        )
        tf = tb.text_frame
        tf.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
        tf.text = label
        p = tf.paragraphs[0]
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])

        # Bar
        bar = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(track_left + label_w + start_q * qw), Inches(top + 0.05),
            Inches(dur * qw - 0.1), Inches(0.45),
        )
        bar.adjustments[0] = 0.5
        bar.fill.solid()
        bar.fill.fore_color.rgb = hex_rgb(color)
        bar.line.fill.background()

    note = slide.shapes.add_textbox(
        Inches(0.6), Inches(6.55), Inches(12.1), Inches(0.5),
    )
    tf = note.text_frame
    tf.text = "Tentpoles are 6-week windows of concentrated spend. Always-on tracks deliver baseline reach and frequency through the year."
    p = tf.paragraphs[0]
    p.font.size = Pt(10)
    p.font.italic = True
    p.font.color.rgb = hex_rgb(TOKENS.palette["muted"])
    footer(slide, FOOTER, "7", TOKENS)


def _forecast(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Forecast", TOKENS)
    section_title(slide, "Pipeline contribution and ROI by quarter", TOKENS)
    divider(slide, TOKENS)

    data = CategoryChartData()
    data.categories = ["Q1", "Q2", "Q3", "Q4"]
    data.add_series("Pipeline ($M)",       (120, 152, 168, 200))
    data.add_series("Marketing-sourced revenue ($M)", (52, 68, 76, 92))
    data.add_series("ROI multiple (×10)",  (38,  46,  56,  60))

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE,
        Inches(0.6), Inches(1.7), Inches(12.1), Inches(5.0),
        data,
    ).chart
    chart.apply_palette(PALETTE)
    chart.apply_quick_layout("title_legend_bottom")
    chart.chart_title.text_frame.text = "FY27 quarterly forecast"
    footer(slide, FOOTER, "8", TOKENS)


def _asks(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Asks", TOKENS)
    section_title(slide, "What I need from this committee", TOKENS)
    divider(slide, TOKENS)

    asks = [
        ("Approve $84M FY27 budget",
         "+9% YoY. Largest reallocation is from print to CTV and creator network."),
        ("Endorse the brand platform",
         "'Made for the movers' — public launch May 22 at Atlas conference."),
        ("Co-anchor the launch",
         "CEO keynote at Atlas; CFO interview in Forbes Q3."),
        ("Vertical SVPs partner on tentpoles",
         "Joint plans for Q2 Atlas, Q3 Industrial summit, Q4 demand wave."),
    ]
    for i, (head, body) in enumerate(asks):
        col = i % 2
        row = i // 2
        left = 0.6 + col * 6.2
        top = 1.85 + row * 2.3
        card = styled_card(slide, left, top, 6.05, 2.05,
                           tokens=TOKENS, fill_hex="#FFFFFF",
                           stroke_hex="#E5E7EB")
        # Number
        num = slide.shapes.add_shape(
            MSO_SHAPE.OVAL,
            Inches(left + 0.25), Inches(top + 0.25),
            Inches(0.5), Inches(0.5),
        )
        num.fill.solid()
        num.fill.fore_color.rgb = hex_rgb(TOKENS.palette["primary"])
        num.line.fill.background()
        ntf = num.text_frame
        ntf.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
        ntf.margin_left = ntf.margin_right = Pt(0)
        ntf.text = str(i + 1)
        np = ntf.paragraphs[0]
        np.alignment = PP_ALIGN.CENTER
        np.font.size = Pt(16)
        np.font.bold = True
        np.font.color.rgb = hex_rgb("#FFFFFF")

        tf = card.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        tf.margin_left = Pt(72)
        tf.margin_right = Pt(18)
        tf.margin_top = tf.margin_bottom = Pt(18)
        tf.text = head
        p0 = tf.paragraphs[0]
        p0.font.name = TOKENS.typography["heading"].family
        p0.font.size = Pt(17)
        p0.font.bold = True
        p0.font.color.rgb = hex_rgb(TOKENS.palette["primary"])
        p1 = tf.add_paragraph()
        p1.text = body
        p1.space_before = Pt(6)
        p1.font.size = Pt(12)
        p1.font.color.rgb = hex_rgb(TOKENS.palette["muted"])
    footer(slide, FOOTER, "9", TOKENS)


if __name__ == "__main__":
    out = HERE / "_out" / "10_marketing_campaign.pptx"
    out.parent.mkdir(exist_ok=True)
    build(out)
