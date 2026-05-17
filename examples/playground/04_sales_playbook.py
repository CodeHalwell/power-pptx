"""Playground 04 — Sales-ops playbook (mixed layouts + transitions).

Eight slides walking through a quarterly sales playbook:

    cover → agenda → two-column "do / don't" → 5-step process flow
    → segmented bar chart → objection handling deck
    → KPI dashboard → call-to-action close

Demonstrates: ``Stack`` for vertical lists, two-column comparison,
horizontal arrow flow built from connectors + shapes, ``apply_palette``
on a 100%-stacked bar, deck-wide PUSH transition with Morph overrides
for the agenda → first-section pair.
"""

from __future__ import annotations

from pathlib import Path

from power_pptx import Presentation
from power_pptx.chart.data import CategoryChartData
from power_pptx.design.layout import Grid, Stack
from power_pptx.dml.color import RGBColor
from power_pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from power_pptx.enum.presentation import MSO_TRANSITION_TYPE
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
from power_pptx.util import Inches, Pt

from _brand import SUNSET, SUNSET_CHART_PALETTE
from _common import lint_or_die

HERE = Path(__file__).parent
P = SUNSET.palette


def build(out_path: Path) -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    _cover(prs)
    _agenda(prs)
    _do_dont(prs)
    _process_flow(prs)
    _segment_bar(prs)
    _objection_handling(prs)
    _kpi_dashboard(prs)
    _close(prs)

    # Deck-wide push for forward movement.
    prs.set_transition(kind=MSO_TRANSITION_TYPE.PUSH, duration=500)
    # Morph between the cover and agenda.
    prs.slides[0].transition.kind = MSO_TRANSITION_TYPE.MORPH
    prs.slides[0].transition.duration = 1200
    # A subtle fade on the close.
    prs.slides[-1].transition.kind = MSO_TRANSITION_TYPE.FADE
    prs.slides[-1].transition.duration = 800

    lint_or_die(prs)
    prs.save(out_path)
    return prs


# ----------------------------------------------------------------------
# slide 1 — cover
# ----------------------------------------------------------------------

def _cover(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["surface"])

    # Coral block top-left.
    block = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(0), Inches(6.6), Inches(7.5),
    )
    block.fill.solid()
    block.fill.fore_color.rgb = P["primary"]
    block.line.fill.background()

    label = slide.shapes.add_textbox(
        Inches(0.7), Inches(1.0), Inches(5.6), Inches(0.5),
    )
    lt = label.text_frame
    lt.word_wrap = True
    lt.text = "Q2 2026 — SALES PLAYBOOK"
    lp = lt.paragraphs[0]
    lp.font.name = "DejaVu Sans"
    lp.font.size = Pt(13)
    lp.font.bold = True
    lp.font.color.rgb = P["accent"]
    lp.alignment = PP_ALIGN.LEFT

    head = slide.shapes.add_textbox(
        Inches(0.7), Inches(1.7), Inches(5.6), Inches(4.5),
    )
    ht = head.text_frame
    ht.word_wrap = True
    ht.text = "Sell the value, not the seat."
    ht.fit_text(font_family="DejaVu Serif", max_size=58, bold=True)
    ht.paragraphs[0].font.color.rgb = P["on_primary"]
    ht.paragraphs[0].alignment = PP_ALIGN.LEFT

    foot = slide.shapes.add_textbox(
        Inches(0.7), Inches(6.6), Inches(5.6), Inches(0.5),
    )
    ft = foot.text_frame
    ft.word_wrap = True
    ft.text = "Internal · Field Sales · Updated 17 May 2026"
    fp = ft.paragraphs[0]
    fp.font.name = "DejaVu Sans"
    fp.font.size = Pt(11)
    fp.font.italic = True
    fp.font.color.rgb = P["accent"]
    fp.alignment = PP_ALIGN.LEFT

    # Right-side: large quotation
    quote = slide.shapes.add_textbox(
        Inches(7.0), Inches(2.5), Inches(6.0), Inches(3.5),
    )
    qt = quote.text_frame
    qt.word_wrap = True
    qt.text = (
        "“The best reps don't pitch features — they reframe budget, "
        "risk, and time-to-value until the deal closes itself.”"
    )
    qp = qt.paragraphs[0]
    qp.font.name = "DejaVu Serif"
    qp.font.size = Pt(22)
    qp.font.italic = True
    qp.font.color.rgb = P["neutral"]
    qp.line_spacing = 1.4
    qp.alignment = PP_ALIGN.LEFT


# ----------------------------------------------------------------------
# slide 2 — agenda using Stack
# ----------------------------------------------------------------------

def _agenda(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["background"])
    _title(slide, "Agenda", "Six sections, twenty minutes — questions at the end")

    items = [
        ("01", "The new positioning",     "Where we sit in the FY26 buyer's mental map."),
        ("02", "Do / Don't",              "Six habits to adopt this quarter; six to drop."),
        ("03", "The five-call process",   "How we move a qualified opp from intro to signed MSA."),
        ("04", "Pipeline mix targets",    "Segment split that hits the FY26 number."),
        ("05", "Top objection cheatsheet", "The four objections that lose 80% of the closed-lost."),
        ("06", "Q2 KPIs and accountability", "What good looks like — and who owns each metric."),
    ]

    stack = Stack(direction="vertical", gap=Pt(8),
                  left=Inches(0.9), top=Inches(2.0), width=Inches(11.5))
    for num, title_, body in items:
        row = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, 1, 1)
        stack.place(row, height=Inches(0.65))
        _agenda_row(row, num, title_, body)


def _agenda_row(row, num: str, title_: str, body: str) -> None:
    row.fill.solid()
    row.fill.fore_color.rgb = P["surface"]
    row.line.color.rgb = RGBColor.from_hex("#E7DED0")
    row.line.width = Pt(0.5)

    tf = row.text_frame
    tf.word_wrap = True
    tf.margin_left = Pt(20)
    tf.margin_right = Pt(20)
    tf.margin_top = Pt(8)
    tf.margin_bottom = Pt(8)

    tf.text = ""
    # Single-line "NN.  Title — sub-body"
    p = tf.paragraphs[0]
    r1 = p.add_run()
    r1.text = f"{num}   "
    r1.font.name = "DejaVu Sans Mono"
    r1.font.size = Pt(16)
    r1.font.bold = True
    r1.font.color.rgb = P["primary"]

    r2 = p.add_run()
    r2.text = title_
    r2.font.name = "DejaVu Serif"
    r2.font.size = Pt(18)
    r2.font.bold = True
    r2.font.color.rgb = P["neutral"]

    r3 = p.add_run()
    r3.text = f"   —   {body}"
    r3.font.name = "DejaVu Sans"
    r3.font.size = Pt(14)
    r3.font.italic = True
    r3.font.color.rgb = P["muted"]

    p.alignment = PP_ALIGN.LEFT


# ----------------------------------------------------------------------
# slide 3 — Do / Don't two-column comparison
# ----------------------------------------------------------------------

def _do_dont(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["background"])
    _title(slide, "Do / Don't — this quarter's habits", "Six adds; six removes")

    do = [
        "Lead with the customer's number, not ours.",
        "Send a recap in the same 90-minute window.",
        "Bring a peer reference to call #2.",
        "Quote in the customer's currency.",
        "Mirror exec language verbatim in proposals.",
        "Always include a 12-week success plan.",
    ]
    dont = [
        "Open with the feature deck.",
        "Wait 48 hours to send the recap.",
        "Save the reference for legal.",
        "Quote in USD when buyer pays in EUR.",
        "Rewrite their objection in our jargon.",
        "Skip the success plan to close faster.",
    ]

    _column_card(slide,
                 left=Inches(0.9), top=Inches(2.0),
                 width=Inches(5.85), height=Inches(4.7),
                 header="DO",      header_color=P["positive"],
                 items=do, bullet="✓ ")
    _column_card(slide,
                 left=Inches(6.85), top=Inches(2.0),
                 width=Inches(5.85), height=Inches(4.7),
                 header="DON'T",   header_color=P["negative"],
                 items=dont, bullet="✗ ")


def _column_card(slide, *, left, top, width, height, header, header_color,
                 items, bullet):
    card = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height,
    )
    card.fill.solid()
    card.fill.fore_color.rgb = P["surface"]
    card.line.color.rgb = RGBColor.from_hex("#E7DED0")
    card.line.width = Pt(1)
    card.shadow.blur_radius = Pt(20)
    card.shadow.distance = Pt(6)
    card.shadow.color.rgb = P["neutral"]
    card.shadow.color.alpha = 0.10

    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(28)
    tf.margin_top = tf.margin_bottom = Pt(24)
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    tf.text = header
    h = tf.paragraphs[0]
    h.font.name = "DejaVu Sans"
    h.font.size = Pt(16)
    h.font.bold = True
    h.font.color.rgb = header_color
    h.alignment = PP_ALIGN.LEFT

    for item in items:
        ip = tf.add_paragraph()
        ip.text = f"{bullet}{item}"
        ip.font.name = "DejaVu Sans"
        ip.font.size = Pt(15)
        ip.font.color.rgb = P["neutral"]
        ip.line_spacing = 1.45
        ip.space_before = Pt(8)
        ip.alignment = PP_ALIGN.LEFT


# ----------------------------------------------------------------------
# slide 4 — five-step process flow (chevrons)
# ----------------------------------------------------------------------

def _process_flow(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["background"])
    _title(slide, "The five-call process", "From intro to signed MSA in eight weeks")

    steps = [
        ("Intro",       "Discovery + qualify",         P["accent"]),
        ("Demo",        "Tailored, w/ peer ref",       P["primary"]),
        ("Champion",    "Value hypothesis + budget",   RGBColor.from_hex("#2E8B57")),
        ("Proposal",    "12-week success plan",        RGBColor.from_hex("#4A7C8C")),
        ("Close",       "Legal + procurement",         P["neutral"]),
    ]

    n = len(steps)
    margin_l = 0.7
    margin_r = 0.7
    total_w = 13.333 - margin_l - margin_r
    # Each step is a wide rounded rectangle with a small chevron arrow
    # between steps. This avoids the chevron-wedge text-wrapping problem
    # (see IMPROVEMENTS.md) — keeps text in rectangles, motion in arrows.
    arrow_w = 0.5
    step_w = (total_w - arrow_w * (n - 1)) / n
    step_h = 1.4
    top = 2.6

    for i, (head, body, color) in enumerate(steps):
        left = Inches(margin_l + (step_w + arrow_w) * i)
        box = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            left, Inches(top), Inches(step_w), Inches(step_h),
        )
        box.fill.solid()
        box.fill.fore_color.rgb = color
        box.line.fill.background()
        box.shadow.blur_radius = Pt(8)
        box.shadow.distance = Pt(3)
        box.shadow.color.rgb = P["neutral"]
        box.shadow.color.alpha = 0.20

        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Pt(10)
        tf.margin_top = Pt(14)
        tf.margin_bottom = Pt(10)

        tf.text = head
        h = tf.paragraphs[0]
        h.font.name = "DejaVu Serif"
        h.font.size = Pt(20)
        h.font.bold = True
        h.font.color.rgb = P["on_primary"]
        h.alignment = PP_ALIGN.CENTER

        bp = tf.add_paragraph()
        bp.text = body
        bp.font.name = "DejaVu Sans"
        bp.font.size = Pt(11)
        bp.font.color.rgb = P["on_primary"]
        bp.alignment = PP_ALIGN.CENTER
        bp.space_before = Pt(4)

        # Add a small chevron in the gap to the right of all but the last
        if i < n - 1:
            arrow_left = Inches(margin_l + (step_w + arrow_w) * i + step_w)
            arrow = slide.shapes.add_shape(
                MSO_SHAPE.RIGHT_TRIANGLE,
                arrow_left, Inches(top + step_h / 2 - 0.18),
                Inches(arrow_w * 0.7), Inches(0.36),
            )
            # Rotate the right-triangle 90° clockwise via the rotation property
            # so the tip points right (the default has the right angle in the
            # bottom-left). Even better: use a CHEVRON-like ISOSCELES_TRIANGLE.
            arrow.rotation = 90
            arrow.fill.solid()
            arrow.fill.fore_color.rgb = RGBColor.from_hex("#D9CFC0")
            arrow.line.fill.background()

    # Annotation below each step.
    annotations = [
        "Goal: confirm pain + power.",
        "Goal: customer pictures the win.",
        "Goal: champion sells internally.",
        "Goal: agreement on price + plan.",
        "Goal: signature within 14 days.",
    ]
    for i, note in enumerate(annotations):
        left = Inches(margin_l + (step_w + arrow_w) * i)
        nbox = slide.shapes.add_textbox(
            left, Inches(top + step_h + 0.25),
            Inches(step_w), Inches(0.7),
        )
        nt = nbox.text_frame
        nt.word_wrap = True
        nt.text = note
        np = nt.paragraphs[0]
        np.font.name = "DejaVu Sans"
        np.font.size = Pt(12)
        np.font.italic = True
        np.font.color.rgb = P["muted"]
        np.alignment = PP_ALIGN.CENTER


# ----------------------------------------------------------------------
# slide 5 — 100% stacked bar — pipeline mix by segment
# ----------------------------------------------------------------------

def _segment_bar(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["background"])
    _title(slide, "Pipeline mix targets — Q2 vs Q1",
           "Share of weighted pipeline by segment (%)")

    data = CategoryChartData()
    data.categories = ["Q1 '26 actual", "Q2 '26 target"]
    data.add_series("Enterprise",  (38, 50))
    data.add_series("Mid-market",  (32, 30))
    data.add_series("SMB",         (18, 14))
    data.add_series("Self-serve",  (12, 6))

    shape = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_STACKED_100,
        Inches(0.9), Inches(2.0), Inches(11.5), Inches(4.3),
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
        Inches(0.9), Inches(6.4), Inches(11.5), Inches(0.6),
    )
    ct = cap.text_frame
    ct.word_wrap = True
    ct.text = (
        "Target shifts weight to Enterprise by 12 points — funded by "
        "halving Self-serve and modest SMB compression."
    )
    cp = ct.paragraphs[0]
    cp.font.name = "DejaVu Sans"
    cp.font.size = Pt(12)
    cp.font.italic = True
    cp.font.color.rgb = P["muted"]
    cp.alignment = PP_ALIGN.LEFT


# ----------------------------------------------------------------------
# slide 6 — objection handling deck (4 cards in a 2x2 grid)
# ----------------------------------------------------------------------

def _objection_handling(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["background"])
    _title(slide, "Top objection cheatsheet",
           "Four scripts that recover 80% of the closed-lost")

    objections = [
        ("It's too expensive.",
         "Reframe: cost per active user vs three alternatives we already know they evaluated.",
         "→ Walk through the 12-week success plan ROI; ask what number they need to hit."),
        ("We don't have bandwidth.",
         "Reframe: bandwidth is bigger if you DON'T do this — they keep paying the manual cost.",
         "→ Offer to staff the first sprint with our solutions architect."),
        ("We're going to build it.",
         "Reframe: maintenance cost over 24 months vs subscription, plus opportunity cost of eng time.",
         "→ Co-author a build-vs-buy memo for their CTO."),
        ("Let's revisit next quarter.",
         "Reframe: what would have to be true for this to not slip again? Usually a missing piece of data.",
         "→ Ask which decision-maker would unblock it; offer to brief them directly."),
    ]
    grid = Grid(slide, cols=12, rows=8, gutter=Pt(20), margin=Pt(56))
    for i, (q, reframe, action) in enumerate(objections):
        col = (i % 2) * 6
        row = 2 + (i // 2) * 3
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, 0, 0, 1, 1)
        grid.place(card, col=col, row=row, col_span=6, row_span=3)
        _objection_card(card, q, reframe, action)


def _objection_card(card, q, reframe, action):
    card.fill.solid()
    card.fill.fore_color.rgb = P["surface"]
    card.line.color.rgb = RGBColor.from_hex("#E7DED0")
    card.line.width = Pt(1)
    card.shadow.blur_radius = Pt(18)
    card.shadow.distance = Pt(4)
    card.shadow.color.rgb = P["neutral"]
    card.shadow.color.alpha = 0.10

    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(22)
    tf.margin_top = tf.margin_bottom = Pt(20)
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    tf.text = f"“{q}”"
    qp = tf.paragraphs[0]
    qp.font.name = "DejaVu Serif"
    qp.font.size = Pt(18)
    qp.font.italic = True
    qp.font.color.rgb = P["primary"]
    qp.alignment = PP_ALIGN.LEFT

    rp = tf.add_paragraph()
    rp.text = reframe
    rp.font.name = "DejaVu Sans"
    rp.font.size = Pt(13)
    rp.font.color.rgb = P["neutral"]
    rp.line_spacing = 1.4
    rp.space_before = Pt(10)
    rp.alignment = PP_ALIGN.LEFT

    ap = tf.add_paragraph()
    ap.text = action
    ap.font.name = "DejaVu Sans"
    ap.font.size = Pt(12)
    ap.font.bold = True
    ap.font.color.rgb = P["positive"]
    ap.line_spacing = 1.4
    ap.space_before = Pt(8)
    ap.alignment = PP_ALIGN.LEFT


# ----------------------------------------------------------------------
# slide 7 — KPI dashboard (4 KPI cards + one supporting bar chart)
# ----------------------------------------------------------------------

def _kpi_dashboard(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["background"])
    _title(slide, "Q2 KPIs and accountability",
           "What good looks like, and who owns each metric")

    kpis = [
        ("Pipeline coverage",   "3.6×",   "RVP",         "positive"),
        ("Avg deal size",       "$82K",   "AE Manager",  "positive"),
        ("Time to close",       "47 days","SE Lead",     "negative"),
        ("Win rate (Ent.)",     "34%",    "RVP",         "positive"),
    ]
    grid = Grid(slide, cols=12, rows=10, gutter=Pt(16), margin=Pt(56))
    for i, (label, value, owner, color_key) in enumerate(kpis):
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, 0, 0, 1, 1)
        grid.place(card, col=i * 3, row=2, col_span=3, row_span=3)
        _mini_kpi(card, label, value, owner, color_key)

    # Supporting bar chart underneath
    data = CategoryChartData()
    data.categories = ["Pipeline cov.", "Deal size", "Time to close", "Win rate"]
    data.add_series("Q1 actual",  (3.1, 71, 54, 28))
    data.add_series("Q2 target",  (3.6, 82, 47, 34))

    shape = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_CLUSTERED,
        Inches(0.9), Inches(5.0), Inches(11.5), Inches(2.2),
        data,
    )
    chart = shape.chart
    chart.apply_palette([P["muted"], P["primary"]])
    chart.apply_quick_layout({
        "has_title": False,
        "has_legend": True,
        "legend_position": XL_LEGEND_POSITION.BOTTOM,
        "category_axis": {"has_major_gridlines": False},
        "value_axis":    {"has_major_gridlines": False},
    })


def _mini_kpi(card, label, value, owner, color_key):
    card.fill.solid()
    card.fill.fore_color.rgb = P["surface"]
    card.line.color.rgb = RGBColor.from_hex("#E7DED0")
    card.line.width = Pt(1)

    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(14)
    tf.margin_top = tf.margin_bottom = Pt(12)
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    tf.text = label
    lp = tf.paragraphs[0]
    lp.font.name = "DejaVu Sans"
    lp.font.size = Pt(11)
    lp.font.color.rgb = P["muted"]
    lp.alignment = PP_ALIGN.LEFT

    vp = tf.add_paragraph()
    vp.text = value
    vp.font.name = "DejaVu Serif"
    vp.font.size = Pt(36)
    vp.font.bold = True
    vp.font.color.rgb = P["neutral"]
    vp.space_before = Pt(4)
    vp.alignment = PP_ALIGN.LEFT

    op = tf.add_paragraph()
    op.text = f"Owner: {owner}"
    op.font.name = "DejaVu Sans Mono"
    op.font.size = Pt(10)
    op.font.color.rgb = P[color_key]
    op.space_before = Pt(6)
    op.alignment = PP_ALIGN.LEFT


# ----------------------------------------------------------------------
# slide 8 — close
# ----------------------------------------------------------------------

def _close(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["primary"])

    head = slide.shapes.add_textbox(
        Inches(0.9), Inches(2.6), Inches(11.5), Inches(2.0),
    )
    ht = head.text_frame
    ht.word_wrap = True
    ht.text = "Bring one new champion to next week's office hours."
    ht.fit_text(font_family="DejaVu Serif", max_size=44, bold=True)
    ht.paragraphs[0].font.color.rgb = P["on_primary"]
    ht.paragraphs[0].alignment = PP_ALIGN.CENTER

    sub = slide.shapes.add_textbox(
        Inches(0.9), Inches(5.0), Inches(11.5), Inches(0.7),
    )
    st = sub.text_frame
    st.word_wrap = True
    st.text = "Same room, every Tuesday, 10:30 PT. Bring questions."
    sp = st.paragraphs[0]
    sp.font.name = "DejaVu Sans"
    sp.font.size = Pt(18)
    sp.font.italic = True
    sp.font.color.rgb = P["accent"]
    sp.alignment = PP_ALIGN.CENTER


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
    out = HERE / "_out" / "04_sales_playbook.pptx"
    out.parent.mkdir(exist_ok=True)
    build(out)
    print(f"wrote {out}")
