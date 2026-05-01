"""Shared helpers for the real-world example decks.

These wrap a few patterns we use in every script:

* lint-or-die before save (auto-fix off-slide shapes, raise on errors)
* widescreen 16:9 deck setup
* consistent section headers, footers, and KPI cards built on top of
  the base recipes for visual consistency across decks
"""

from __future__ import annotations

from typing import Iterable

from power_pptx import Presentation
from power_pptx.design.tokens import DesignTokens
from power_pptx.dml.color import RGBColor
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import MSO_AUTO_SIZE, MSO_VERTICAL_ANCHOR, PP_ALIGN
from power_pptx.exc import LintError
from power_pptx.lint import LintSeverity
from power_pptx.util import Inches, Pt

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def new_deck() -> Presentation:
    """Return an empty 16:9 widescreen presentation."""
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    return prs


def lint_or_die(prs: Presentation) -> None:
    """Auto-fix what we can, raise on remaining errors.

    ``SlideLintReport.auto_fix()`` refreshes ``report.issues`` in place,
    so a single lint pass per slide is enough — no second ``slide.lint()``
    call needed to collect the residual punch list.
    """
    errors: list[str] = []
    for i, slide in enumerate(prs.slides):
        report = slide.lint()
        report.auto_fix()
        for issue in report.issues:
            if issue.severity is LintSeverity.ERROR:
                errors.append(f"slide {i + 1}: {issue}")
    if errors:
        raise LintError("\n".join(errors))


def hex_rgb(value) -> RGBColor:
    """Accept hex strings ('#RRGGBB' / 'RRGGBB') or RGBColor instances."""
    if isinstance(value, RGBColor):
        return value
    return RGBColor.from_string(value.lstrip("#"))


def section_title(slide, text: str, tokens: DesignTokens, *, top: float = 0.55) -> None:
    """Top-of-slide bolded section heading."""
    box = slide.shapes.add_textbox(
        Inches(0.6), Inches(top), Inches(12.1), Inches(0.95),
    )
    tf = box.text_frame
    tf.word_wrap = True
    tf.text = text
    tf.fit_text(font_family=tokens.typography["heading"].family,
                max_size=32, bold=True)
    tf.paragraphs[0].font.color.rgb = hex_rgb(tokens.palette["neutral"])


def eyebrow(slide, text: str, tokens: DesignTokens, *, top: float = 0.4) -> None:
    """Small uppercase tag-line above a section title."""
    box = slide.shapes.add_textbox(
        Inches(0.6), Inches(top), Inches(12.1), Inches(0.3),
    )
    tf = box.text_frame
    tf.word_wrap = False
    tf.text = text.upper()
    p = tf.paragraphs[0]
    p.font.name = tokens.typography["body"].family
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = hex_rgb(tokens.palette["accent"])


def footer(slide, left_text: str, right_text: str, tokens: DesignTokens) -> None:
    """Small confidential / page footer at the bottom of a slide."""
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(7.32), SLIDE_W, Inches(0.18),
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = hex_rgb(tokens.palette["primary"])
    bar.line.fill.background()

    left = slide.shapes.add_textbox(
        Inches(0.4), Inches(7.0), Inches(7), Inches(0.3),
    )
    p = left.text_frame.paragraphs[0]
    p.text = left_text
    p.font.name = tokens.typography["body"].family
    p.font.size = Pt(9)
    p.font.color.rgb = hex_rgb(tokens.palette["muted"])

    right = slide.shapes.add_textbox(
        Inches(7.4), Inches(7.0), Inches(5.5), Inches(0.3),
    )
    p = right.text_frame.paragraphs[0]
    p.text = right_text
    p.alignment = PP_ALIGN.RIGHT
    p.font.name = tokens.typography["body"].family
    p.font.size = Pt(9)
    p.font.color.rgb = hex_rgb(tokens.palette["muted"])


def divider(slide, tokens: DesignTokens, *, top: float = 1.45) -> None:
    """Thin accent rule under a section heading."""
    rule = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0.62), Inches(top), Inches(0.6), Inches(0.06),
    )
    rule.fill.solid()
    rule.fill.fore_color.rgb = hex_rgb(tokens.palette["accent"])
    rule.line.fill.background()


def styled_card(
    slide,
    left: float,
    top: float,
    width: float,
    height: float,
    *,
    tokens: DesignTokens,
    fill_hex: str | None = None,
    stroke_hex: str | None = None,
):
    """Standard rounded-rectangle card with shadow + optional border."""
    card = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(left), Inches(top), Inches(width), Inches(height),
    )
    card.fill.solid()
    card.fill.fore_color.rgb = hex_rgb(fill_hex or tokens.palette["surface"])
    if stroke_hex is None:
        card.line.fill.background()
    else:
        card.line.color.rgb = hex_rgb(stroke_hex)
        card.line.width = Pt(0.75)

    card.shadow.blur_radius = Pt(18)
    card.shadow.distance = Pt(4)
    card.shadow.direction = 90.0
    card.shadow.color.rgb = hex_rgb(tokens.palette["neutral"])
    card.shadow.color.alpha = 0.10
    return card


def write_card_text(
    card,
    *,
    eyebrow_text: str | None,
    heading: str,
    body: str | None,
    tokens: DesignTokens,
    heading_color: str | None = None,
    heading_size: int = 22,
) -> None:
    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(16)
    tf.margin_top = tf.margin_bottom = Pt(14)
    tf.auto_size = MSO_AUTO_SIZE.NONE

    paragraphs: list[tuple[str, dict]] = []
    if eyebrow_text:
        paragraphs.append((eyebrow_text.upper(),
                           dict(size=Pt(10), bold=True,
                                color=tokens.palette["accent"])))
    paragraphs.append((heading,
                       dict(size=Pt(heading_size), bold=True,
                            color=heading_color or tokens.palette["neutral"])))
    if body:
        paragraphs.append((body,
                           dict(size=Pt(13),
                                color=tokens.palette["muted"])))

    tf.text = paragraphs[0][0]
    _apply_run_style(tf.paragraphs[0], paragraphs[0][1], tokens)
    for text, style in paragraphs[1:]:
        p = tf.add_paragraph()
        p.text = text
        p.space_before = Pt(6)
        _apply_run_style(p, style, tokens)


def _apply_run_style(p, style: dict, tokens: DesignTokens) -> None:
    p.font.name = tokens.typography["body"].family
    if "size" in style:
        p.font.size = style["size"]
    p.font.bold = style.get("bold", False)
    if "color" in style:
        p.font.color.rgb = hex_rgb(style["color"])


def cover_band(slide, top: float, height: float, hex_color: str) -> None:
    """A solid full-width color band — used for headers and banners."""
    band = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(top), SLIDE_W, Inches(height),
    )
    band.fill.solid()
    band.fill.fore_color.rgb = hex_rgb(hex_color)
    band.line.fill.background()


def colored_label(slide, left: float, top: float, width: float,
                  text: str, *, hex_bg: str, hex_fg: str = "#FFFFFF") -> None:
    pill = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(left), Inches(top), Inches(width), Inches(0.32),
    )
    pill.adjustments[0] = 0.5
    pill.fill.solid()
    pill.fill.fore_color.rgb = hex_rgb(hex_bg)
    pill.line.fill.background()
    tf = pill.text_frame
    tf.margin_left = tf.margin_right = Pt(8)
    tf.margin_top = tf.margin_bottom = Pt(2)
    tf.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
    tf.text = text.upper()
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.font.size = Pt(10)
    p.font.bold = True
    p.font.color.rgb = hex_rgb(hex_fg)


def bulleted_list(slide, left: float, top: float, width: float,
                  height: float, items: Iterable[str], tokens: DesignTokens,
                  *, size: int = 16) -> None:
    box = slide.shapes.add_textbox(
        Inches(left), Inches(top), Inches(width), Inches(height),
    )
    tf = box.text_frame
    tf.word_wrap = True
    items = list(items)
    if not items:
        return
    tf.text = f"•  {items[0]}"
    p0 = tf.paragraphs[0]
    p0.font.name = tokens.typography["body"].family
    p0.font.size = Pt(size)
    p0.font.color.rgb = hex_rgb(tokens.palette["neutral"])
    p0.space_after = Pt(6)
    for item in items[1:]:
        p = tf.add_paragraph()
        p.text = f"•  {item}"
        p.font.name = tokens.typography["body"].family
        p.font.size = Pt(size)
        p.font.color.rgb = hex_rgb(tokens.palette["neutral"])
        p.space_after = Pt(6)


def number_label(slide, left: float, top: float, n: int, tokens: DesignTokens) -> None:
    """Numbered circle marker in the brand primary color."""
    circle = slide.shapes.add_shape(
        MSO_SHAPE.OVAL,
        Inches(left), Inches(top), Inches(0.5), Inches(0.5),
    )
    circle.fill.solid()
    circle.fill.fore_color.rgb = hex_rgb(tokens.palette["primary"])
    circle.line.fill.background()
    tf = circle.text_frame
    tf.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
    tf.margin_left = tf.margin_right = Pt(0)
    tf.margin_top = tf.margin_bottom = Pt(0)
    tf.text = str(n)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.font.name = tokens.typography["heading"].family
    p.font.size = Pt(20)
    p.font.bold = True
    p.font.color.rgb = hex_rgb(tokens.palette["on_primary"])


def cover_slide(prs: Presentation, *, eyebrow_text: str, title: str, subtitle: str,
                presenter: str, date: str, tokens: DesignTokens):
    """Striking cover: full-bleed branded panel + side accent."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    # Left dark panel
    left_panel = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(0), Inches(5.5), SLIDE_H,
    )
    left_panel.fill.linear_gradient(
        tokens.palette["primary"], tokens.palette["neutral"], angle=90,
    )
    left_panel.line.fill.background()

    # Accent strip
    accent = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(5.5), Inches(0), Inches(0.12), SLIDE_H,
    )
    accent.fill.solid()
    accent.fill.fore_color.rgb = hex_rgb(tokens.palette["accent"])
    accent.line.fill.background()

    # Eyebrow on left panel
    eb = slide.shapes.add_textbox(Inches(0.6), Inches(0.6), Inches(4.6), Inches(0.4))
    tf = eb.text_frame
    tf.text = eyebrow_text.upper()
    p = tf.paragraphs[0]
    p.font.name = tokens.typography["body"].family
    p.font.size = Pt(12)
    p.font.bold = True
    p.font.color.rgb = hex_rgb(tokens.palette["accent"])

    # Title on left panel
    title_box = slide.shapes.add_textbox(
        Inches(0.6), Inches(2.4), Inches(4.7), Inches(3.2),
    )
    tf = title_box.text_frame
    tf.word_wrap = True
    tf.text = title
    tf.fit_text(font_family=tokens.typography["heading"].family,
                max_size=44, bold=True)
    tf.paragraphs[0].font.color.rgb = hex_rgb(tokens.palette["on_primary"])

    # Right side white panel — subtitle + meta
    sub = slide.shapes.add_textbox(
        Inches(6.0), Inches(2.6), Inches(6.8), Inches(2.4),
    )
    tf = sub.text_frame
    tf.word_wrap = True
    tf.text = subtitle
    tf.fit_text(font_family=tokens.typography["heading"].family,
                max_size=28, bold=False)
    tf.paragraphs[0].font.color.rgb = hex_rgb(tokens.palette["neutral"])

    meta = slide.shapes.add_textbox(
        Inches(6.0), Inches(5.8), Inches(6.8), Inches(0.9),
    )
    tf = meta.text_frame
    tf.word_wrap = True
    tf.text = presenter
    p0 = tf.paragraphs[0]
    p0.font.name = tokens.typography["body"].family
    p0.font.size = Pt(14)
    p0.font.bold = True
    p0.font.color.rgb = hex_rgb(tokens.palette["neutral"])
    p1 = tf.add_paragraph()
    p1.text = date
    p1.font.name = tokens.typography["body"].family
    p1.font.size = Pt(12)
    p1.font.color.rgb = hex_rgb(tokens.palette["muted"])

    return slide


def closing_slide(prs: Presentation, *, headline: str, sub: str, tokens: DesignTokens):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), SLIDE_W, SLIDE_H,
    )
    bg.fill.linear_gradient(
        tokens.palette["primary"], tokens.palette["neutral"], angle=135,
    )
    bg.line.fill.background()

    title = slide.shapes.add_textbox(
        Inches(1.0), Inches(2.7), Inches(11.3), Inches(1.8),
    )
    tf = title.text_frame
    tf.word_wrap = True
    tf.text = headline
    tf.fit_text(font_family=tokens.typography["heading"].family,
                max_size=60, bold=True)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.font.color.rgb = hex_rgb(tokens.palette["on_primary"])

    subtxt = slide.shapes.add_textbox(
        Inches(1.0), Inches(4.7), Inches(11.3), Inches(0.9),
    )
    tf = subtxt.text_frame
    tf.word_wrap = True
    tf.text = sub
    tf.fit_text(font_family=tokens.typography["body"].family,
                max_size=22, bold=False)
    tf.paragraphs[0].alignment = PP_ALIGN.CENTER
    tf.paragraphs[0].font.color.rgb = hex_rgb(tokens.palette["accent"])

    rule = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(6.17), Inches(4.5), Inches(1.0), Inches(0.06),
    )
    rule.fill.solid()
    rule.fill.fore_color.rgb = hex_rgb(tokens.palette["accent"])
    rule.line.fill.background()
    return slide
