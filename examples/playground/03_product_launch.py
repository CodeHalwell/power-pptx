"""Playground 03 — Product launch (effects + transitions heavy).

A six-slide product-launch deck that exercises every Phase-3/6 visual
effect:

    teaser → hero (radial gradient bg) → feature grid (glow + shadow)
    → pricing tier cards (alpha glass) → roadmap timeline → sign-off

Demonstrates: linear / radial / shape gradient fills, alpha-tinted
glass cards on a saturated background, glow + shadow stacks, soft
edges, reflection on a hero card, and a deck-wide MORPH/FADE
transition palette. A subtle Morph between consecutive hero/cards
slides lets the audience see the cards rearrange.
"""

from __future__ import annotations

from pathlib import Path

from power_pptx import Presentation
from power_pptx.design.layout import Grid
from power_pptx.dml.color import RGBColor
from power_pptx.enum.presentation import MSO_TRANSITION_TYPE
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

    _teaser(prs)
    _hero(prs)
    _features(prs)
    _pricing(prs)
    _roadmap(prs)
    _signoff(prs)

    # Deck-wide gentle fade; override the teaser → hero pair with Morph
    # so the headline grows in place.
    prs.set_transition(kind=MSO_TRANSITION_TYPE.FADE, duration=500)
    prs.slides[0].transition.kind = MSO_TRANSITION_TYPE.MORPH
    prs.slides[0].transition.duration = 1500
    prs.slides[1].transition.kind = MSO_TRANSITION_TYPE.MORPH
    prs.slides[1].transition.duration = 1500
    # Push for the roadmap to suggest forward motion.
    prs.slides[4].transition.kind = MSO_TRANSITION_TYPE.PUSH
    prs.slides[4].transition.duration = 700

    lint_or_die(prs)
    prs.save(out_path)
    return prs


# ----------------------------------------------------------------------
# slide 1 — teaser (single big word, tight)
# ----------------------------------------------------------------------

def _teaser(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["neutral"])

    # Single oversized word with a tight tracking-equivalent (we can't
    # set letter-spacing in OOXML easily, so use bold + large size).
    box = slide.shapes.add_textbox(
        Inches(0.5), Inches(2.4), Inches(12.5), Inches(3.2),
    )
    tf = box.text_frame
    tf.word_wrap = True
    tf.text = "Espresso"
    tf.fit_text(font_family="DejaVu Serif", max_size=240, bold=True)
    p = tf.paragraphs[0]
    p.font.color.rgb = P["on_primary"]
    p.alignment = PP_ALIGN.CENTER

    # Hairline below the word
    rule = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(5.4), Inches(5.6), Inches(2.5), Inches(0.02),
    )
    rule.fill.solid()
    rule.fill.fore_color.rgb = P["primary"]
    rule.line.fill.background()

    # Sub-caption
    cap = slide.shapes.add_textbox(
        Inches(0.5), Inches(5.9), Inches(12.5), Inches(0.8),
    )
    ct = cap.text_frame
    ct.word_wrap = True
    ct.text = "A faster brew, in five minutes flat."
    cp = ct.paragraphs[0]
    cp.font.name = "DejaVu Sans"
    cp.font.size = Pt(20)
    cp.font.italic = True
    cp.font.color.rgb = P["accent"]
    cp.alignment = PP_ALIGN.CENTER


# ----------------------------------------------------------------------
# slide 2 — hero (radial gradient background, big card with reflection)
# ----------------------------------------------------------------------

def _hero(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    # Radial-gradient backdrop, neutral edge → primary center.
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(0), Inches(13.333), Inches(7.5),
    )
    bg.fill.gradient(kind="radial")
    bg.fill.gradient_stops.replace([
        (0.0, P["primary"]),
        (0.7, RGBColor.from_hex("#7B1F12")),
        (1.0, P["neutral"]),
    ])
    bg.line.fill.background()
    _send_to_back(bg)

    # Big floating card with reflection.
    card = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(1.5), Inches(1.2), Inches(10.3), Inches(4.4),
    )
    card.fill.solid()
    card.fill.fore_color.rgb = P["surface"]
    card.line.fill.background()
    card.shadow.blur_radius = Pt(28)
    card.shadow.distance = Pt(10)
    card.shadow.direction = 90.0
    card.shadow.color.rgb = RGBColor.from_hex("#000000")
    card.shadow.color.alpha = 0.45
    card.reflection.blur_radius = Pt(2)
    card.reflection.distance = Pt(1)
    card.reflection.start_alpha = 0.45
    card.reflection.end_alpha = 0.0

    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(48)
    tf.margin_top = tf.margin_bottom = Pt(36)
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    tf.text = "Introducing Espresso"
    h = tf.paragraphs[0]
    h.font.name = "DejaVu Serif"
    h.font.size = Pt(52)
    h.font.bold = True
    h.font.color.rgb = P["neutral"]
    h.alignment = PP_ALIGN.LEFT

    body = tf.add_paragraph()
    body.text = (
        "An end-to-end deck generator that goes from a JSON spec to a "
        "lint-clean, brand-aligned PowerPoint in under five seconds — "
        "with the same space-aware guarantees you'd expect from a "
        "designer touching every slide."
    )
    body.font.name = "DejaVu Sans"
    body.font.size = Pt(19)
    body.font.color.rgb = P["muted"]
    body.line_spacing = 1.4
    body.space_before = Pt(16)
    body.alignment = PP_ALIGN.LEFT

    # Two pill buttons under the card.
    _add_pill(slide, "Read the docs",   Inches(1.5), Inches(6.2), P["primary"], P["on_primary"])
    _add_pill(slide, "Try the API",     Inches(4.5), Inches(6.2), P["surface"], P["primary"], outline=P["primary"])


def _add_pill(slide, text: str, left, top, fill_color, text_color, *, outline=None):
    pill = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        left, top, Inches(2.6), Inches(0.6),
    )
    pill.adjustments[0] = 0.5  # extreme rounding -> pill
    pill.fill.solid()
    pill.fill.fore_color.rgb = fill_color
    if outline is not None:
        pill.line.color.rgb = outline
        pill.line.width = Pt(1.5)
    else:
        pill.line.fill.background()
    tf = pill.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(6)
    tf.margin_top = tf.margin_bottom = Pt(6)
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    tf.text = text
    p = tf.paragraphs[0]
    p.font.name = "DejaVu Sans"
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = text_color
    p.alignment = PP_ALIGN.CENTER


# ----------------------------------------------------------------------
# slide 3 — feature grid (3x2 cards with shadow + glow)
# ----------------------------------------------------------------------

def _features(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["background"])
    _title(slide, "What it ships with", "Six things that make generated decks survive review")

    # Use big ASCII numerals for the visual hierarchy. (Emoji glyphs
    # don't render reliably in headless LibreOffice — see IMPROVEMENTS.md.)
    features = [
        ("01", "Five-second build", "JSON spec → linted .pptx in under five seconds for a typical 12-slide deck."),
        ("02", "Space-aware text",  "Headlines fit their box by font metric, then auto-shrink if a human edits."),
        ("03", "Design tokens",      "One palette and typography spec drives every recipe and chart palette."),
        ("04", "Branded charts",     "Apply a named palette + opinionated layout in two lines per chart."),
        ("05", "Lint-on-save",       "Off-slide shapes are nudged back in; text overflow is flagged before save."),
        ("06", "API ergonomics",     "Reads never mutate XML. Effects clear cleanly. Everything round-trips."),
    ]

    grid = Grid(slide, cols=12, rows=8, gutter=Pt(16), margin=Pt(48))
    for i, (emoji, heading, body) in enumerate(features):
        col = (i % 3) * 4
        row = 2 + (i // 3) * 3
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, 0, 0, 1, 1)
        grid.place(card, col=col, row=row, col_span=4, row_span=3)
        _feature_card(card, emoji, heading, body, accent=(i % 3 == 1))


def _feature_card(card, emoji, heading, body, *, accent=False):
    card.fill.solid()
    card.fill.fore_color.rgb = P["surface"] if not accent else RGBColor.from_hex("#FFF1E7")
    card.line.color.rgb = RGBColor.from_hex("#E7DED0")
    card.line.width = Pt(1)
    card.shadow.blur_radius = Pt(18)
    card.shadow.distance = Pt(6)
    card.shadow.direction = 90.0
    card.shadow.color.rgb = P["neutral"]
    card.shadow.color.alpha = 0.12
    if accent:
        # Subtle glow on the middle card per row
        card.glow.radius = Pt(8)
        card.glow.color.rgb = P["primary"]
        card.glow.color.alpha = 0.30  # type: ignore[attr-defined]
    card.soft_edges.radius = Pt(1)

    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(20)
    tf.margin_top = tf.margin_bottom = Pt(18)
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    tf.text = emoji
    e = tf.paragraphs[0]
    e.font.size = Pt(28)
    e.font.name = "DejaVu Sans Mono"
    e.font.bold = True
    e.font.color.rgb = P["primary"]
    e.alignment = PP_ALIGN.LEFT

    h = tf.add_paragraph()
    h.text = heading
    h.font.name = "DejaVu Serif"
    h.font.size = Pt(20)
    h.font.bold = True
    h.font.color.rgb = P["neutral"]
    h.space_before = Pt(4)
    h.alignment = PP_ALIGN.LEFT

    b = tf.add_paragraph()
    b.text = body
    b.font.name = "DejaVu Sans"
    b.font.size = Pt(12)
    b.font.color.rgb = P["muted"]
    b.line_spacing = 1.35
    b.space_before = Pt(6)
    b.alignment = PP_ALIGN.LEFT


# ----------------------------------------------------------------------
# slide 4 — pricing (three alpha-glass cards on a saturated background)
# ----------------------------------------------------------------------

def _pricing(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    # Diagonal linear-gradient background, primary → near-black.
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(0), Inches(13.333), Inches(7.5),
    )
    bg.fill.gradient(kind="linear")
    bg.fill.gradient_stops.replace([
        (0.0, P["primary"]),
        (1.0, P["neutral"]),
    ])
    bg.line.fill.background()
    _send_to_back(bg)

    # Title in white.
    th = slide.shapes.add_textbox(
        Inches(0.9), Inches(0.6), Inches(11.5), Inches(1.0),
    )
    tt = th.text_frame
    tt.word_wrap = True
    tt.text = "Pricing built for teams that ship"
    tt.fit_text(font_family="DejaVu Serif", max_size=38, bold=True)
    tt.paragraphs[0].font.color.rgb = P["on_primary"]
    tt.paragraphs[0].alignment = PP_ALIGN.LEFT

    # Three glass cards via alpha-tinted white fills.
    tiers = [
        ("Starter",    "Free",       ["10 decks / month", "Lint + auto-fix", "Community support"], False),
        ("Studio",     "$49 / mo",   ["Unlimited decks", "Brand tokens", "Email support"],         True),
        ("Enterprise", "Custom",     ["SSO + audit log", "On-prem render", "Dedicated success"],    False),
    ]
    grid = Grid(slide, cols=12, rows=8, gutter=Pt(20), margin=Pt(64))
    for i, (name, price, feats, featured) in enumerate(tiers):
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, 0, 0, 1, 1)
        grid.place(card, col=i * 4, row=2, col_span=4, row_span=6)
        _glass_pricing_card(card, name, price, feats, featured)


def _glass_pricing_card(card, name, price, feats, featured):
    # Alpha-tinted white for the glass effect on a saturated background.
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor.from_hex("#FFFFFF")
    card.fill.fore_color.alpha = 0.94 if featured else 0.18
    card.line.color.rgb = RGBColor.from_hex("#FFFFFF")
    card.line.color.alpha = 0.30
    card.line.width = Pt(1)
    if featured:
        card.shadow.blur_radius = Pt(32)
        card.shadow.distance = Pt(12)
        card.shadow.direction = 90.0
        card.shadow.color.rgb = RGBColor.from_hex("#000000")
        card.shadow.color.alpha = 0.40
        card.glow.radius = Pt(12)
        card.glow.color.rgb = P["accent"]
        card.glow.color.alpha = 0.40  # type: ignore[attr-defined]

    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(26)
    tf.margin_top = tf.margin_bottom = Pt(24)
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    name_color = P["primary"] if featured else P["on_primary"]
    price_color = P["neutral"] if featured else P["on_primary"]
    body_color = P["muted"] if featured else P["on_primary"]

    tf.text = name
    n = tf.paragraphs[0]
    n.font.name = "DejaVu Sans"
    n.font.size = Pt(14)
    n.font.bold = True
    n.font.color.rgb = name_color
    n.alignment = PP_ALIGN.LEFT

    pr = tf.add_paragraph()
    pr.text = price
    pr.font.name = "DejaVu Serif"
    pr.font.size = Pt(40)
    pr.font.bold = True
    pr.font.color.rgb = price_color
    pr.space_before = Pt(6)
    pr.alignment = PP_ALIGN.LEFT

    # Separator
    sep = tf.add_paragraph()
    sep.text = ""
    sep.space_before = Pt(8)

    for feat in feats:
        f = tf.add_paragraph()
        f.text = f"•  {feat}"
        f.font.name = "DejaVu Sans"
        f.font.size = Pt(14)
        f.font.color.rgb = body_color
        f.line_spacing = 1.45
        f.alignment = PP_ALIGN.LEFT


# ----------------------------------------------------------------------
# slide 5 — roadmap timeline (five connected milestones)
# ----------------------------------------------------------------------

def _roadmap(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["background"])
    _title(slide, "What's next on the roadmap", "Q2 → Q4 2026 — milestones, not promises")

    milestones = [
        ("Q2 '26", "Public beta",   P["accent"]),
        ("Q3 '26", "Brand template marketplace", P["primary"]),
        ("Q4 '26", "Real-time collaboration",    RGBColor.from_hex("#2E8B57")),
        ("Q1 '27", "On-prem render farm",        RGBColor.from_hex("#4A7C8C")),
        ("Q2 '27", "1.0 release",                P["neutral"]),
    ]

    # Horizontal rule connecting the milestones.
    track_y = Inches(4.4)
    rule = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(1.2), track_y, Inches(10.9), Inches(0.03),
    )
    rule.fill.solid()
    rule.fill.fore_color.rgb = RGBColor.from_hex("#E7DED0")
    rule.line.fill.background()

    # Five dots and labels.
    n = len(milestones)
    track_w = 10.9
    step = track_w / (n - 1)
    for i, (when, what, color) in enumerate(milestones):
        cx = 1.2 + step * i

        dot = slide.shapes.add_shape(
            MSO_SHAPE.OVAL,
            Inches(cx - 0.18), Inches(4.27), Inches(0.36), Inches(0.36),
        )
        dot.fill.solid()
        dot.fill.fore_color.rgb = color
        dot.line.color.rgb = RGBColor.from_hex("#FFFFFF")
        dot.line.width = Pt(2.5)
        dot.shadow.blur_radius = Pt(8)
        dot.shadow.distance = Pt(2)
        dot.shadow.color.rgb = P["neutral"]
        dot.shadow.color.alpha = 0.25

        # Quarter label above the dot
        qbox = slide.shapes.add_textbox(
            Inches(cx - 1.0), Inches(3.4), Inches(2.0), Inches(0.5),
        )
        qt = qbox.text_frame
        qt.word_wrap = True
        qt.text = when
        qp = qt.paragraphs[0]
        qp.font.name = "DejaVu Sans Mono"
        qp.font.size = Pt(14)
        qp.font.bold = True
        qp.font.color.rgb = color
        qp.alignment = PP_ALIGN.CENTER

        # Description below the dot
        wbox = slide.shapes.add_textbox(
            Inches(cx - 1.25), Inches(4.85), Inches(2.5), Inches(1.4),
        )
        wt = wbox.text_frame
        wt.word_wrap = True
        wt.text = what
        wp = wt.paragraphs[0]
        wp.font.name = "DejaVu Serif"
        wp.font.size = Pt(15)
        wp.font.bold = True
        wp.font.color.rgb = P["neutral"]
        wp.alignment = PP_ALIGN.CENTER


# ----------------------------------------------------------------------
# slide 6 — sign-off
# ----------------------------------------------------------------------

def _signoff(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_bg(slide, P["neutral"])

    head = slide.shapes.add_textbox(
        Inches(0.9), Inches(2.4), Inches(11.5), Inches(2.4),
    )
    ht = head.text_frame
    ht.word_wrap = True
    ht.text = "Ship the next deck before lunch."
    ht.fit_text(font_family="DejaVu Serif", max_size=56, bold=True)
    ht.paragraphs[0].font.color.rgb = P["on_primary"]
    ht.paragraphs[0].alignment = PP_ALIGN.CENTER

    sub = slide.shapes.add_textbox(
        Inches(0.9), Inches(5.4), Inches(11.5), Inches(0.8),
    )
    st = sub.text_frame
    st.word_wrap = True
    st.text = "espresso.dev   ·   thanks@espresso.dev   ·   @espresso_dev"
    sp = st.paragraphs[0]
    sp.font.name = "DejaVu Sans Mono"
    sp.font.size = Pt(18)
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
    _send_to_back(bg)


def _send_to_back(shape) -> None:
    sp_tree = shape._element.getparent()
    sp_tree.remove(shape._element)
    sp_tree.insert(2, shape._element)


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
    out = HERE / "_out" / "03_product_launch.pptx"
    out.parent.mkdir(exist_ok=True)
    build(out)
    print(f"wrote {out}")
