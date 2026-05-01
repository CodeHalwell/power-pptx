"""03 — Product Launch: Atlas Cloud Console 4.0.

A go-to-market launch deck — the kind a product VP presents to the
field, partners, and analysts to introduce a flagship release.

Slides:
    1. Cover
    2. The problem (eyebrow + bullets)
    3. Introducing the product (hero with feature pills)
    4. What's new (3-up feature grid)
    5. Customer impact (KPIs)
    6. Performance benchmarks (column chart)
    7. Competitive positioning (table)
    8. Pricing & packaging (3-tier)
    9. Customer voice (quote)
    10. Closing / call to action
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from power_pptx.chart.data import CategoryChartData
from power_pptx.design.recipes import kpi_slide, quote_slide
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.enum.presentation import MSO_TRANSITION_TYPE
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import MSO_AUTO_SIZE, MSO_VERTICAL_ANCHOR, PP_ALIGN
from power_pptx.util import Inches, Pt

from _brand import PRODUCT as TOKENS, PRODUCT_PALETTE as PALETTE
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

FOOTER = "Atlas Cloud Console 4.0  |  Launch Day Briefing  |  May 2026"


def build(out: Path) -> None:
    prs = new_deck()

    cover_slide(
        prs,
        eyebrow_text="Atlas Cloud Console 4.0",
        title="One console.\nEvery cloud.\nAny scale.",
        subtitle="The unified operations plane for multi-cloud "
                 "infrastructure — now with autonomous remediation, "
                 "FinOps, and policy-as-code built in.",
        presenter="Priya Ramachandran, SVP Product",
        date="Worldwide Launch  •  May 14, 2026",
        tokens=TOKENS,
    )

    _the_problem(prs)
    intro_slide = _introducing(prs)
    _whats_new(prs)

    kpi_slide(
        prs, title="What customers achieve in 90 days",
        kpis=[
            {"label": "Mean time to remediate", "value": "−74%", "delta": -0.74},
            {"label": "Cloud spend optimised", "value": "−22%", "delta": -0.22},
            {"label": "Policy violations",     "value": "−91%", "delta": -0.91},
            {"label": "Engineer hours saved",  "value": "+18 wk/yr", "delta": +0.32},
        ],
        tokens=TOKENS,
    )
    footer(prs.slides[-1], FOOTER, "5", TOKENS)

    _benchmarks(prs)
    _competitive(prs)
    _pricing(prs)

    quote_slide(
        prs,
        quote="Atlas 4.0 is the first product that gave my SRE team back "
              "their weekends. We turned three pager-driven processes "
              "into one console-driven workflow.",
        attribution="Director of Platform Engineering, Global Top-10 Bank",
        tokens=TOKENS,
    )
    footer(prs.slides[-1], FOOTER, "9", TOKENS)

    closing_slide(
        prs,
        headline="Generally available May 14.",
        sub="atlas.cloud/launch  |  partner-portal.atlas.cloud  |  #atlas-launch",
        tokens=TOKENS,
    )

    # Apply the deck-wide fade FIRST, then override the introducing slide
    # with Morph — set_transition iterates every slide and would otherwise
    # clobber the per-slide override.
    prs.set_transition(kind=MSO_TRANSITION_TYPE.FADE, duration=400)
    intro_slide.transition.kind = MSO_TRANSITION_TYPE.MORPH
    intro_slide.transition.duration = 1200

    lint_or_die(prs)
    prs.save(out)
    print(f"wrote {out}")


def _the_problem(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Why this matters", TOKENS)
    section_title(slide, "Operations teams are drowning in tools", TOKENS)
    divider(slide, TOKENS)

    problems = [
        ("47", "average tools per platform team"),
        ("31%", "of incident time spent context-switching"),
        ("$84B", "wasted cloud spend industry-wide in 2025"),
        ("4 of 5", "engineers report alert fatigue weekly"),
    ]
    width = 2.95
    gap = 0.18
    left0 = 0.6
    for i, (num, body) in enumerate(problems):
        left = left0 + i * (width + gap)
        card = styled_card(slide, left, 1.95, width, 2.6, tokens=TOKENS,
                           fill_hex="#FFFFFF", stroke_hex="#E5E7EB")
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Pt(16)
        tf.margin_top = Pt(18)
        tf.margin_bottom = Pt(16)
        tf.text = num
        p0 = tf.paragraphs[0]
        p0.font.name = TOKENS.typography["heading"].family
        p0.font.size = Pt(40)
        p0.font.bold = True
        p0.font.color.rgb = hex_rgb(PALETTE[i])
        p1 = tf.add_paragraph()
        p1.text = body
        p1.space_before = Pt(6)
        p1.font.name = TOKENS.typography["body"].family
        p1.font.size = Pt(13)
        p1.font.color.rgb = hex_rgb(TOKENS.palette["muted"])

    summary = slide.shapes.add_textbox(
        Inches(0.6), Inches(4.95), Inches(12.1), Inches(1.4),
    )
    tf = summary.text_frame
    tf.word_wrap = True
    tf.text = ("The result: outages get longer, budgets get cut, and "
               "best engineers leave. Teams need a single plane that "
               "consolidates the noise — without forcing a forklift.")
    tf.fit_text(font_family=TOKENS.typography["body"].family,
                max_size=18, bold=False)
    tf.paragraphs[0].font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
    footer(slide, FOOTER, "2", TOKENS)


def _introducing(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    # Full-bleed gradient backdrop
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0),
        Inches(13.333), Inches(7.5),
    )
    bg.fill.linear_gradient(
        TOKENS.palette["primary"], TOKENS.palette["accent"], angle=135,
    )
    bg.line.fill.background()

    eb = slide.shapes.add_textbox(
        Inches(0.8), Inches(0.7), Inches(11.7), Inches(0.4),
    )
    tf = eb.text_frame
    tf.text = "INTRODUCING ATLAS 4.0"
    p = tf.paragraphs[0]
    p.font.size = Pt(13)
    p.font.bold = True
    p.font.color.rgb = hex_rgb(TOKENS.palette["on_primary"])

    title = slide.shapes.add_textbox(
        Inches(0.8), Inches(1.4), Inches(11.7), Inches(2.4),
    )
    tf = title.text_frame
    tf.word_wrap = True
    tf.text = "Multi-cloud operations.\nNow autonomous."
    tf.fit_text(font_family=TOKENS.typography["heading"].family,
                max_size=66, bold=True)
    tf.paragraphs[0].font.color.rgb = hex_rgb(TOKENS.palette["on_primary"])

    sub = slide.shapes.add_textbox(
        Inches(0.8), Inches(4.0), Inches(11.7), Inches(1.0),
    )
    tf = sub.text_frame
    tf.word_wrap = True
    tf.text = ("A unified plane for AWS, Azure, GCP, and on-prem. "
               "Built on an open agent runtime and a policy graph "
               "your platform team already knows.")
    tf.fit_text(font_family=TOKENS.typography["body"].family,
                max_size=20, bold=False)
    tf.paragraphs[0].font.color.rgb = hex_rgb("#F8FAFC")
    tf.paragraphs[0].font.color.alpha = 0.92

    # Feature pills
    pills = ["Autonomous remediation", "FinOps insights",
             "Policy-as-code", "Open agent runtime"]
    px = 0.8
    py = 5.6
    for label in pills:
        pill = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(px), Inches(py), Inches(2.85), Inches(0.6),
        )
        pill.adjustments[0] = 0.5
        pill.fill.solid()
        pill.fill.fore_color.rgb = hex_rgb("#FFFFFF")
        pill.fill.fore_color.alpha = 0.14
        pill.line.color.rgb = hex_rgb("#FFFFFF")
        pill.line.color.alpha = 0.45
        pill.line.width = Pt(0.75)
        tf = pill.text_frame
        tf.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
        tf.text = label
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        p.font.name = TOKENS.typography["body"].family
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = hex_rgb(TOKENS.palette["on_primary"])
        px += 3.0

    # Caller applies the Morph override AFTER the deck-wide set_transition.
    return slide


def _whats_new(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "What's new in 4.0", TOKENS)
    section_title(slide, "Six capabilities your platform team will love", TOKENS)
    divider(slide, TOKENS)

    features = [
        ("⚡", "Autonomous remediation",
         "Closed-loop incident response. Detects, decides, and fixes — humans approve, never type."),
        ("📊", "FinOps insights",
         "Per-team, per-service spend with budget guardrails. Cuts cloud bills by 22% on average."),
        ("📜", "Policy-as-code",
         "Declarative guardrails authored in Rego or CUE. Continuously enforced across every cloud."),
        ("🔌", "Open agent runtime",
         "Bring-your-own runners on Kubernetes, ECS, or bare-metal. No SDK lock-in. Apache 2.0."),
        ("🔒", "Sovereign deployments",
         "FedRAMP High, EU sovereign, and dedicated tenant tiers — same console, isolated control plane."),
        ("🔭", "Unified observability",
         "OpenTelemetry-native. Native ingest from Datadog, New Relic, and Prometheus — no re-instrumentation."),
    ]
    cols = 3
    card_w = 4.05
    card_h = 2.45
    gap_x = 0.15
    gap_y = 0.2
    left0 = 0.6
    top0 = 1.8
    for i, (icon, head, body) in enumerate(features):
        col = i % cols
        row = i // cols
        left = left0 + col * (card_w + gap_x)
        top = top0 + row * (card_h + gap_y)
        card = styled_card(slide, left, top, card_w, card_h,
                           tokens=TOKENS, fill_hex="#FFFFFF",
                           stroke_hex="#E5E7EB")
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Pt(16)
        tf.margin_top = tf.margin_bottom = Pt(14)
        tf.text = icon
        p0 = tf.paragraphs[0]
        p0.font.size = Pt(28)
        p0.font.color.rgb = hex_rgb(TOKENS.palette["primary"])
        p1 = tf.add_paragraph()
        p1.text = head
        p1.space_before = Pt(4)
        p1.font.name = TOKENS.typography["heading"].family
        p1.font.size = Pt(16)
        p1.font.bold = True
        p1.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
        p2 = tf.add_paragraph()
        p2.text = body
        p2.space_before = Pt(4)
        p2.font.name = TOKENS.typography["body"].family
        p2.font.size = Pt(11)
        p2.font.color.rgb = hex_rgb(TOKENS.palette["muted"])
    footer(slide, FOOTER, "4", TOKENS)


def _benchmarks(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Performance", TOKENS)
    section_title(slide, "Atlas 4.0 benchmarks vs. 3.x and the field", TOKENS)
    divider(slide, TOKENS)

    data = CategoryChartData()
    data.categories = [
        "MTTR (min)", "Policy eval p95 (ms)",
        "API throughput (req/s)", "Cloud spend savings (%)",
    ]
    data.add_series("Atlas 3.6", (38, 420, 9000, 12))
    data.add_series("Atlas 4.0", (10, 90, 24000, 22))
    data.add_series("Industry median", (52, 510, 7800, 8))

    chart_shape = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(0.6), Inches(1.7), Inches(12.1), Inches(5.0),
        data,
    )
    chart = chart_shape.chart
    chart.apply_palette(PALETTE)
    chart.apply_quick_layout("title_legend_bottom")
    chart.chart_title.text_frame.text = "Atlas 4.0 — measured improvements"

    footer(slide, FOOTER, "6", TOKENS)


def _competitive(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Competitive landscape", TOKENS)
    section_title(slide, "How we compare on what matters", TOKENS)
    divider(slide, TOKENS)

    rows = [
        ("Capability",            "Atlas 4.0", "Vendor A", "Vendor B", "Vendor C"),
        ("Multi-cloud parity",    "✓ Native",  "Partial",  "AWS-first","Partial"),
        ("Autonomous remediation","✓ Closed-loop","Manual","Suggest-only","Suggest-only"),
        ("Policy-as-code",        "✓ Rego + CUE","Proprietary","Proprietary","✓ Rego"),
        ("FedRAMP High",          "✓",          "✗",        "In progress","✓"),
        ("Open agent runtime",    "✓ Apache 2.0","Closed",  "Closed",   "Closed"),
        ("Pricing model",         "Per-asset",  "Per-seat", "Per-host", "Per-seat"),
    ]
    shape = slide.shapes.add_table(
        rows=len(rows), cols=5,
        left=Inches(0.6), top=Inches(1.7),
        width=Inches(12.1), height=Inches(4.6),
    )
    table = shape.table
    table.columns[0].width = Inches(3.4)
    for c in range(1, 5):
        table.columns[c].width = Inches(2.175)

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
            if c == 1:
                p.font.bold = True
                p.font.color.rgb = hex_rgb(TOKENS.palette["positive"])
            cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
            if r % 2 == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = hex_rgb(TOKENS.palette["surface"])
            cell.borders.bottom.color.rgb = hex_rgb("#E5E7EB")
            cell.borders.bottom.width = Pt(0.5)
    footer(slide, FOOTER, "7", TOKENS)


def _pricing(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    eyebrow(slide, "Packaging", TOKENS)
    section_title(slide, "Three editions. Pay for assets, not seats.", TOKENS)
    divider(slide, TOKENS)

    tiers = [
        ("Team",       "Free",      "Up to 50 assets",
         ["Single cloud", "Community policies",
          "Slack alerts", "Email support"], "#94A3B8", False),
        ("Business",   "$1.20",     "per asset / month",
         ["Multi-cloud", "FinOps dashboards",
          "Policy library + custom",
          "Autonomous remediation",
          "24×7 support"], TOKENS.palette["primary"], True),
        ("Enterprise", "Custom",    "annual commitment",
         ["Sovereign deploys", "FedRAMP High",
          "Dedicated SRE pod",
          "Audit logging + SOC integration",
          "99.99% SLA"], TOKENS.palette["accent"], False),
    ]
    width = 4.05
    gap = 0.15
    left0 = 0.6
    for i, (name, price, sub, bullets, color, featured) in enumerate(tiers):
        left = left0 + i * (width + gap)
        card = styled_card(slide, left, 1.7, width, 5.2,
                           tokens=TOKENS, fill_hex="#FFFFFF",
                           stroke_hex=color if featured else "#E5E7EB")
        if featured:
            badge = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(left + width - 1.4), Inches(1.55),
                Inches(1.3), Inches(0.32),
            )
            badge.adjustments[0] = 0.5
            badge.fill.solid()
            badge.fill.fore_color.rgb = hex_rgb(color)
            badge.line.fill.background()
            tf = badge.text_frame
            tf.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
            tf.margin_top = tf.margin_bottom = Pt(2)
            tf.margin_left = tf.margin_right = Pt(4)
            tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
            tf.text = "MOST POPULAR"
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            p.font.size = Pt(9)
            p.font.bold = True
            p.font.color.rgb = hex_rgb("#FFFFFF")

        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Pt(18)
        tf.margin_top = tf.margin_bottom = Pt(16)
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        tf.text = name
        p0 = tf.paragraphs[0]
        p0.font.name = TOKENS.typography["heading"].family
        p0.font.size = Pt(18)
        p0.font.bold = True
        p0.font.color.rgb = hex_rgb(color)
        p1 = tf.add_paragraph()
        p1.text = price
        p1.space_before = Pt(4)
        p1.font.name = TOKENS.typography["heading"].family
        p1.font.size = Pt(28)
        p1.font.bold = True
        p1.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
        p2 = tf.add_paragraph()
        p2.text = sub
        p2.font.name = TOKENS.typography["body"].family
        p2.font.size = Pt(11)
        p2.font.color.rgb = hex_rgb(TOKENS.palette["muted"])
        for b in bullets:
            pb = tf.add_paragraph()
            pb.text = f"✓  {b}"
            pb.space_before = Pt(5)
            pb.font.name = TOKENS.typography["body"].family
            pb.font.size = Pt(11)
            pb.font.color.rgb = hex_rgb(TOKENS.palette["neutral"])
    footer(slide, FOOTER, "8", TOKENS)


if __name__ == "__main__":
    out = HERE / "_out" / "03_product_launch.pptx"
    out.parent.mkdir(exist_ok=True)
    build(out)
