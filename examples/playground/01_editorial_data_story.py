"""Playground 01 — Editorial data story.

A six-slide "magazine-style" deck about the global coffee market:

    cover → KPI strip → headline chart → comparison table
    → quote pull → callout pillars

Demonstrates: SUNSET design tokens, ``Grid``-driven layout, ``fit_text``
on headlines, two chart styles, alternating-row table with conditional
delta coloring, and quote/pillar recipes built from primitives.
"""

from __future__ import annotations

from pathlib import Path

from power_pptx import Presentation
from power_pptx.chart.data import CategoryChartData
from power_pptx.design.layout import Grid
from power_pptx.dml.color import RGBColor
from power_pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
from power_pptx.util import Inches, Pt

from _brand import SUNSET
from _common import lint_or_die

HERE = Path(__file__).parent
P = SUNSET.palette


def build(out_path: Path) -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    _cover(prs)
    _kpi_strip(prs)
    _headline_chart(prs)
    _comparison_table(prs)
    _pull_quote(prs)
    _pillars(prs)

    lint_or_die(prs)
    prs.save(out_path)
    return prs


# ----------------------------------------------------------------------
# slide 1 — cover
# ----------------------------------------------------------------------

def _cover(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_background(slide, P["surface"])

    # Big coral accent stripe on the left margin.
    stripe = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(0), Inches(0.45), Inches(7.5),
    )
    stripe.fill.solid()
    stripe.fill.fore_color.rgb = P["primary"]
    stripe.line.fill.background()

    # Eyebrow kicker — small caps.
    kicker = slide.shapes.add_textbox(
        Inches(1.1), Inches(1.0), Inches(11.0), Inches(0.4),
    )
    ktf = kicker.text_frame
    ktf.word_wrap = True  # disable spAutoFit which mis-renders in LibreOffice
    ktf.text = "ISSUE 04  •  MAY 2026  •  GLOBAL MARKETS"
    p = ktf.paragraphs[0]
    p.font.name = "DejaVu Sans"
    p.font.size = Pt(13)
    p.font.bold = True
    p.font.color.rgb = P["primary"]
    _left_align(ktf)

    # Headline.
    head = slide.shapes.add_textbox(
        Inches(1.1), Inches(1.7), Inches(11.0), Inches(3.2),
    )
    htf = head.text_frame
    htf.word_wrap = True
    htf.text = "The Quiet Reordering of the Global Coffee Trade"
    htf.fit_text(font_family="DejaVu Serif", max_size=72, bold=True)
    htf.paragraphs[0].font.color.rgb = P["neutral"]
    _left_align(htf)

    # Standfirst (short summary paragraph under the headline).
    stand = slide.shapes.add_textbox(
        Inches(1.1), Inches(5.1), Inches(10.0), Inches(1.4),
    )
    stf = stand.text_frame
    stf.word_wrap = True
    stf.text = (
        "Brazilian frost, container-rate volatility, and a fast-growing "
        "specialty segment have rewritten who buys what from whom — "
        "and whose margin is at risk through the rest of FY26."
    )
    sp = stf.paragraphs[0]
    sp.font.name = "DejaVu Sans"
    sp.font.size = Pt(18)
    sp.font.color.rgb = P["muted"]
    sp.line_spacing = 1.35
    _left_align(stf)

    # Byline footer.
    foot = slide.shapes.add_textbox(
        Inches(1.1), Inches(6.7), Inches(11.0), Inches(0.4),
    )
    ftf = foot.text_frame
    ftf.word_wrap = True
    ftf.text = "By the power-pptx Editorial Desk"
    fp = ftf.paragraphs[0]
    fp.font.name = "DejaVu Sans"
    fp.font.size = Pt(12)
    fp.font.italic = True
    fp.font.color.rgb = P["muted"]
    _left_align(ftf)


# ----------------------------------------------------------------------
# slide 2 — KPI strip across the top, callout body below
# ----------------------------------------------------------------------

def _kpi_strip(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_background(slide, P["background"])
    _section_title(slide, "By the numbers", subtitle="FY26 YTD vs FY25 YTD")

    kpis = [
        {"label": "Global green-bean trade",      "value": "$31.4B", "delta": "+8.1%", "delta_color": "positive"},
        {"label": "Average Arabica spot price",   "value": "$3.92/lb", "delta": "+24.6%", "delta_color": "negative"},
        {"label": "Specialty share of imports",   "value": "27.3%", "delta": "+3.1 pp", "delta_color": "positive"},
        {"label": "Container-rate Asia → US East","value": "$4,180", "delta": "−12.4%", "delta_color": "positive"},
    ]

    grid = Grid(slide, cols=12, rows=6, gutter=Pt(18), margin=Pt(64))
    for i, kpi in enumerate(kpis):
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, 0, 0, 1, 1)
        grid.place(card, col=i * 3, row=2, col_span=3, row_span=2)
        _style_kpi_card(card, kpi)

    # Caption row underneath the KPIs explaining what to look at.
    caption = slide.shapes.add_textbox(
        Inches(0.9), Inches(5.6), Inches(11.5), Inches(1.4),
    )
    ctf = caption.text_frame
    ctf.word_wrap = True
    ctf.text = (
        "Spot prices spiked alongside the July frost in Minas Gerais, "
        "but the *positive* signal here is the freight reversal: trans-"
        "Pacific container rates are finally normalising after twenty "
        "months of post-pandemic stickiness."
    )
    cp = ctf.paragraphs[0]
    cp.font.name = "DejaVu Sans"
    cp.font.size = Pt(14)
    cp.font.color.rgb = P["muted"]
    cp.line_spacing = 1.4
    _left_align(ctf)


def _style_kpi_card(card, kpi: dict) -> None:
    card.fill.solid()
    card.fill.fore_color.rgb = P["surface"]
    card.line.color.rgb = RGBColor.from_hex("#E7DED0")
    card.line.width = Pt(1)
    card.shadow.blur_radius = Pt(16)
    card.shadow.distance = Pt(4)
    card.shadow.direction = 90.0
    card.shadow.color.rgb = P["neutral"]
    card.shadow.color.alpha = 0.10

    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(18)
    tf.margin_top = tf.margin_bottom = Pt(16)
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    tf.text = kpi["value"]
    v = tf.paragraphs[0]
    v.font.name = "DejaVu Serif"
    v.font.size = Pt(34)
    v.font.bold = True
    v.font.color.rgb = P["neutral"]

    label = tf.add_paragraph()
    label.text = kpi["label"]
    label.font.name = "DejaVu Sans"
    label.font.size = Pt(12)
    label.font.color.rgb = P["muted"]
    label.space_before = Pt(4)

    delta = tf.add_paragraph()
    delta.text = kpi["delta"]
    delta.font.name = "DejaVu Sans Mono"
    delta.font.size = Pt(13)
    delta.font.bold = True
    color_key = kpi.get("delta_color", "positive")
    delta.font.color.rgb = P[color_key]
    delta.space_before = Pt(8)

    _left_align(tf)


# ----------------------------------------------------------------------
# slide 3 — headline chart
# ----------------------------------------------------------------------

def _headline_chart(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_background(slide, P["background"])
    _section_title(
        slide,
        "Arabica vs Robusta spot price",
        subtitle="USD per pound, monthly close, Jan-2024 → Apr-2026",
    )

    data = CategoryChartData()
    data.categories = [
        "Jan-24", "Apr-24", "Jul-24", "Oct-24",
        "Jan-25", "Apr-25", "Jul-25", "Oct-25",
        "Jan-26", "Apr-26",
    ]
    data.add_series("Arabica", (
        1.85, 1.92, 2.05, 2.30, 2.65, 2.98, 3.42, 3.71, 3.84, 3.92,
    ))
    data.add_series("Robusta", (
        1.10, 1.18, 1.32, 1.58, 1.86, 2.11, 2.34, 2.42, 2.48, 2.55,
    ))

    chart_shape = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE,
        Inches(0.9), Inches(1.9), Inches(11.5), Inches(4.6),
        data,
    )
    chart = chart_shape.chart
    chart.apply_palette([P["primary"], P["muted"]])
    # apply_palette only sets the fill solid color, which is invisible on
    # line charts — set the line stroke explicitly. See IMPROVEMENTS.md #2.
    for s, c in zip(chart.series, [P["primary"], P["muted"]]):
        s.format.line.color.rgb = c
        s.format.line.width = Pt(2.5)
    chart.apply_quick_layout({
        "has_title": False,
        "has_legend": True,
        "legend_position": XL_LEGEND_POSITION.BOTTOM,
        "category_axis": {"has_major_gridlines": False},
        "value_axis":    {"has_major_gridlines": True},
    })

    # Editorial caption tying chart back to the headline metric.
    cap = slide.shapes.add_textbox(
        Inches(0.9), Inches(6.6), Inches(11.5), Inches(0.6),
    )
    ctf = cap.text_frame
    ctf.word_wrap = True
    ctf.text = "Source: ICO monthly composite. Both grades doubled inside 24 months."
    cp = ctf.paragraphs[0]
    cp.font.name = "DejaVu Sans"
    cp.font.size = Pt(11)
    cp.font.italic = True
    cp.font.color.rgb = P["muted"]
    _left_align(ctf)


# ----------------------------------------------------------------------
# slide 4 — comparison table
# ----------------------------------------------------------------------

def _comparison_table(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_background(slide, P["background"])
    _section_title(
        slide,
        "Top importers — volume and YoY change",
        subtitle="Green-bean equivalent, '000 metric tons",
    )

    headers = ["Country", "Volume FY25", "Volume FY26", "Δ YoY", "Specialty share"]
    rows = [
        ("United States", "1,572",  "1,610",  "+2.4%",   "31%"),
        ("Germany",         "986",   "1,021",  "+3.5%",   "29%"),
        ("Italy",           "612",     "598",   "−2.3%",  "18%"),
        ("Japan",           "418",     "445",   "+6.4%",  "34%"),
        ("Belgium",         "402",     "451",  "+12.2%",  "22%"),
        ("Spain",           "318",     "311",   "−2.2%",  "17%"),
    ]

    table_shape = slide.shapes.add_table(
        rows=len(rows) + 1,
        cols=len(headers),
        left=Inches(0.9), top=Inches(2.0),
        width=Inches(11.5), height=Inches(4.4),
    )
    table = table_shape.table
    # The default table style overlays alternating rows and a header band;
    # we're styling everything ourselves so turn the built-ins off.
    table.first_row = False
    table.horz_banding = False

    # Column widths — name column wider than the numeric ones.
    widths = [Inches(2.6), Inches(2.1), Inches(2.1), Inches(2.0), Inches(2.7)]
    for i, w in enumerate(widths):
        table.columns[i].width = w

    table.rows[0].height = Inches(0.55)
    for r in range(1, len(rows) + 1):
        table.rows[r].height = Inches(0.55)

    # Header band.
    for c, label in enumerate(headers):
        cell = table.cell(0, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = P["neutral"]
        cell.text = label
        p = cell.text_frame.paragraphs[0]
        p.font.name = "DejaVu Sans"
        p.font.bold = True
        p.font.size = Pt(13)
        p.font.color.rgb = P["on_primary"]
        p.alignment = PP_ALIGN.LEFT if c == 0 else PP_ALIGN.RIGHT
        cell.borders.bottom.color.rgb = P["primary"]
        cell.borders.bottom.width = Pt(2.5)

    # Body rows — zebra fill + conditional delta color.
    # Fill *every* cell explicitly so the inherited default-table-style
    # banding doesn't show through on the rows we'd otherwise leave bare.
    stripe = RGBColor.from_hex("#FAF4EA")
    white = RGBColor.from_hex("#FFFFFF")
    for r, row in enumerate(rows, start=1):
        zebra = r % 2 == 1
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = stripe if zebra else white
            cell.text = value
            p = cell.text_frame.paragraphs[0]
            p.font.name = "DejaVu Sans" if c == 0 else "DejaVu Sans Mono"
            p.font.size = Pt(13)
            p.font.color.rgb = P["neutral"]
            p.alignment = PP_ALIGN.LEFT if c == 0 else PP_ALIGN.RIGHT
            cell.borders.bottom.color.rgb = RGBColor.from_hex("#E7DED0")
            cell.borders.bottom.width = Pt(0.5)

        # Conditional delta coloring on column 3.
        delta_cell = table.cell(r, 3)
        delta_text = row[3]
        dp = delta_cell.text_frame.paragraphs[0]
        dp.font.bold = True
        if delta_text.startswith("−") or delta_text.startswith("-"):
            dp.font.color.rgb = P["negative"]
        else:
            dp.font.color.rgb = P["positive"]


# ----------------------------------------------------------------------
# slide 5 — pull quote
# ----------------------------------------------------------------------

def _pull_quote(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_background(slide, P["primary"])

    # Oversized opening quote mark.
    mark = slide.shapes.add_textbox(
        Inches(0.6), Inches(0.3), Inches(2.0), Inches(2.0),
    )
    mtf = mark.text_frame
    mtf.word_wrap = True
    mtf.text = "“"
    mp = mtf.paragraphs[0]
    mp.font.name = "DejaVu Serif"
    mp.font.size = Pt(220)
    mp.font.bold = True
    mp.font.color.rgb = P["on_primary"]
    mp.font.color.alpha = 0.35

    quote = slide.shapes.add_textbox(
        Inches(1.6), Inches(2.0), Inches(10.4), Inches(3.4),
    )
    qtf = quote.text_frame
    qtf.word_wrap = True
    qtf.text = (
        "We used to budget twelve months ahead. Now we budget twelve "
        "weeks ahead, hedge the rest, and pray for an ordinary harvest."
    )
    qp = qtf.paragraphs[0]
    qp.font.name = "DejaVu Serif"
    qp.font.size = Pt(36)
    qp.font.italic = True
    qp.font.color.rgb = P["on_primary"]
    qp.line_spacing = 1.3
    _left_align(qtf)

    # Attribution + role on two lines.
    attr = slide.shapes.add_textbox(
        Inches(1.6), Inches(5.6), Inches(10.4), Inches(1.0),
    )
    atf = attr.text_frame
    atf.word_wrap = True
    atf.text = "— Marta Quesada"
    a0 = atf.paragraphs[0]
    a0.font.name = "DejaVu Sans"
    a0.font.size = Pt(20)
    a0.font.bold = True
    a0.font.color.rgb = P["on_primary"]

    role = atf.add_paragraph()
    role.text = "Head of Procurement, top-3 European roaster"
    role.font.name = "DejaVu Sans"
    role.font.size = Pt(14)
    role.font.italic = True
    role.font.color.rgb = P["accent"]
    role.space_before = Pt(2)
    _left_align(atf)


# ----------------------------------------------------------------------
# slide 6 — three callout pillars
# ----------------------------------------------------------------------

def _pillars(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_background(slide, P["background"])
    _section_title(
        slide,
        "What to watch through 2026",
        subtitle="Three signals worth the price of a Bloomberg seat",
    )

    pillars = [
        ("Brazilian harvest",
         "September forecasts will tell us whether the 2026 crop "
         "rebuilds inventory or extends the squeeze into FY27."),
        ("Specialty premium",
         "If the spread over commodity Arabica narrows below 60c, "
         "expect specialty roasters to renegotiate forward contracts."),
        ("Container shipping",
         "A second consecutive quarter of trans-Pacific rate easing "
         "would unlock margin recovery for North American importers."),
    ]

    grid = Grid(slide, cols=12, rows=6, gutter=Pt(20), margin=Pt(64))
    for i, (heading, body) in enumerate(pillars):
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, 0, 0, 1, 1)
        grid.place(card, col=i * 4, row=2, col_span=4, row_span=3)
        _style_pillar(card, str(i + 1), heading, body)


def _style_pillar(card, number: str, heading: str, body: str) -> None:
    card.fill.solid()
    card.fill.fore_color.rgb = P["surface"]
    card.line.fill.background()
    card.shadow.blur_radius = Pt(22)
    card.shadow.distance = Pt(6)
    card.shadow.direction = 90.0
    card.shadow.color.rgb = P["neutral"]
    card.shadow.color.alpha = 0.12

    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(22)
    tf.margin_top = tf.margin_bottom = Pt(22)

    # Big number kicker.
    tf.text = number
    n = tf.paragraphs[0]
    n.font.name = "DejaVu Serif"
    n.font.size = Pt(48)
    n.font.bold = True
    n.font.color.rgb = P["primary"]

    h = tf.add_paragraph()
    h.text = heading
    h.font.name = "DejaVu Serif"
    h.font.size = Pt(22)
    h.font.bold = True
    h.font.color.rgb = P["neutral"]
    h.space_before = Pt(4)

    b = tf.add_paragraph()
    b.text = body
    b.font.name = "DejaVu Sans"
    b.font.size = Pt(13)
    b.font.color.rgb = P["muted"]
    b.space_before = Pt(8)
    b.line_spacing = 1.35

    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    _left_align(tf)


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _left_align(text_frame) -> None:
    """Force every paragraph to left alignment.

    Works around LibreOffice rendering un-aligned paragraphs as centered;
    PowerPoint defaults to left.  See ``IMPROVEMENTS.md`` #3.
    """
    for p in text_frame.paragraphs:
        p.alignment = PP_ALIGN.LEFT


def _paint_background(slide, color) -> None:
    """``color`` may be a hex string or an ``RGBColor`` from the palette."""
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
    # Send to back by moving the spTree child to the front of the list.
    sp_tree = bg._element.getparent()
    sp_tree.remove(bg._element)
    sp_tree.insert(2, bg._element)  # after nvGrpSpPr and grpSpPr


def _section_title(slide, title: str, subtitle: str | None = None) -> None:
    title_box = slide.shapes.add_textbox(
        Inches(0.9), Inches(0.5), Inches(11.5), Inches(0.9),
    )
    tt = title_box.text_frame
    tt.word_wrap = True
    tt.text = title
    tt.fit_text(font_family="DejaVu Serif", max_size=34, bold=True)
    tt.paragraphs[0].font.color.rgb = P["neutral"]
    _left_align(tt)

    if subtitle:
        sub_box = slide.shapes.add_textbox(
            Inches(0.9), Inches(1.35), Inches(11.5), Inches(0.5),
        )
        st = sub_box.text_frame
        st.word_wrap = True
        st.text = subtitle
        sp = st.paragraphs[0]
        sp.font.name = "DejaVu Sans"
        sp.font.size = Pt(13)
        sp.font.italic = True
        sp.font.color.rgb = P["muted"]
        _left_align(st)


if __name__ == "__main__":
    out = HERE / "_out" / "01_editorial_data_story.pptx"
    out.parent.mkdir(exist_ok=True)
    build(out)
    print(f"wrote {out}")
