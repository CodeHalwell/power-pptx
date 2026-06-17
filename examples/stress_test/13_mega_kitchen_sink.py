"""Mega kitchen-sink: a single large deck (30+ slides) that interleaves every
feature area — cover, gradients, effects, 3D, charts, tables, diagrams,
pictures, recipes, transitions deck-wide — to surface cross-feature interaction
bugs that the focused scripts miss.
"""

from __future__ import annotations

from pathlib import Path

from _util import SLIDE_H, SLIDE_W, blank, deck, save

from power_pptx import BBox
from power_pptx.chart.data import CategoryChartData
from power_pptx.design.recipes import bullet_slide, kpi_slide, quote_slide, title_slide
from power_pptx.design.tokens import DesignTokens
from power_pptx.diagrams import (
    comparison_columns,
    cycle,
    decision_tree,
    horizontal_pipeline,
    hub_and_spoke,
)
from power_pptx.dml.color import RGBColor
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.enum.dml import BevelPreset, MSO_PATTERN_TYPE, PresetMaterial
from power_pptx.enum.presentation import MSO_TRANSITION_TYPE
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import MSO_AUTO_SIZE
from power_pptx.util import Inches, Pt

ASSETS = Path(__file__).parent / "_assets"

TOKENS = DesignTokens.from_dict({
    "palette": {
        "primary": "#0B2447", "accent": "#C9A227", "neutral": "#0F172A",
        "muted": "#475569", "surface": "#F4F5F7", "background": "#FFFFFF",
        "on_primary": "#FFFFFF", "positive": "#1B7F3F", "negative": "#B91C1C",
    },
    "typography": {
        "heading": {"family": "Inter", "size": 40.0, "bold": True},
        "body": {"family": "Inter", "size": 18.0},
    },
    "shadows": {"card": {"blur": 18.0, "distance": 4.0, "alpha": 0.16}},
})
PALETTE = ["#0B2447", "#C9A227", "#1B7F3F", "#3B82F6", "#94A3B8", "#B91C1C"]


def _heading(s, text):
    box = s.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(12.1), Inches(0.9))
    tf = box.text_frame
    tf.word_wrap = True
    tf.text = text
    tf.fit_text(font_family="Inter", max_size=32, bold=True)
    tf.paragraphs[0].font.color.rgb = RGBColor.from_hex("#0F172A")


def _ensure_assets():
    ASSETS.mkdir(exist_ok=True)
    if not (ASSETS / "hero.jpg").exists():
        from PIL import Image
        Image.new("RGB", (800, 500), (11, 36, 71)).save(ASSETS / "hero.jpg")


def _cover(prs):
    s = blank(prs)
    panel = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    panel.fill.linear_gradient("#0B2447", "#0F172A", angle=120)
    panel.line.fill.background()
    rule = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(3.6),
                              Inches(1.2), Inches(0.08))
    rule.fill.solid()
    rule.fill.fore_color.rgb = RGBColor.from_hex("#C9A227")
    rule.line.fill.background()
    box = s.shapes.add_textbox(Inches(0.8), Inches(2.2), Inches(11), Inches(1.3))
    tf = box.text_frame
    tf.word_wrap = True
    tf.text = "Mega Kitchen Sink"
    tf.fit_text(font_family="Inter", max_size=54, bold=True)
    tf.paragraphs[0].font.color.rgb = RGBColor.from_hex("#FFFFFF")
    sub = s.shapes.add_textbox(Inches(0.8), Inches(4.0), Inches(11), Inches(0.8))
    sub.text_frame.text = "Every feature area, one deck"
    sub.text_frame.paragraphs[0].font.color.rgb = RGBColor.from_hex("#C9A227")
    sub.text_frame.paragraphs[0].font.size = Pt(22)


def _effects_slide(prs):
    s = blank(prs)
    _heading(s, "Effects + gradients")
    for i, kind in enumerate(["linear", "radial", "rectangular", "shape"]):
        card = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                  Inches(0.6 + (i % 4) * 3.1), Inches(2.0),
                                  Inches(2.8), Inches(2.4))
        card.fill.gradient(kind=kind)
        card.fill.gradient_stops.replace([(0.0, "#0B2447"), (1.0, "#C9A227")])
        card.line.fill.background()
        card.shadow.blur_radius = Pt(14)
        card.shadow.distance = Pt(4)
        card.shadow.color.alpha = 0.25
        card.glow.radius = Pt(6)
        card.glow.color = RGBColor.from_hex("#C9A227")
        card.text_frame.text = kind


def _three_d_slide(prs):
    s = blank(prs)
    _heading(s, "3D badges")
    for i, (bev, mat) in enumerate([
        (BevelPreset.SOFT_ROUND, PresetMaterial.METAL),
        (BevelPreset.CIRCLE, PresetMaterial.PLASTIC),
        (BevelPreset.CONVEX, PresetMaterial.WARM_MATTE),
        (BevelPreset.ART_DECO, PresetMaterial.MATTE),
    ]):
        b = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.8 + i * 3.0), Inches(2.4),
                               Inches(2.4), Inches(2.4))
        b.fill.solid()
        b.fill.fore_color.rgb = RGBColor.from_hex(PALETTE[i])
        b.line.fill.background()
        td = b.three_d
        td.bevel_top.preset = bev
        td.bevel_top.width = Pt(8)
        td.bevel_top.height = Pt(4)
        td.extrusion_height = Pt(14)
        td.extrusion_color = RGBColor.from_hex("#0F172A")
        td.preset_material = mat


def _chart_slide(prs):
    s = blank(prs)
    _heading(s, "Charts")
    d = CategoryChartData()
    d.categories = ["Q1", "Q2", "Q3", "Q4"]
    d.add_series("ARR", (100, 130, 155, 182))
    d.add_series("NDR", (115, 118, 124, 131))
    cs = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.7),
                            Inches(1.5), Inches(11.9), Inches(5.4), d)
    chart = cs.chart
    chart.apply_palette(PALETTE)
    chart.apply_quick_layout("title_axes_legend_bottom")
    g = chart.series[0].format.fill
    g.gradient(kind="linear")
    g.gradient_stops.replace([(0.0, "#0B2447"), (1.0, "#3B82F6")])
    pat = chart.series[1].format.fill
    pat.patterned()
    pat.pattern = MSO_PATTERN_TYPE.WIDE_DOWNWARD_DIAGONAL
    pat.fore_color.rgb = (0xC9, 0xA2, 0x27)
    pat.back_color.rgb = (0xFF, 0xFF, 0xFF)


def _table_slide(prs):
    s = blank(prs)
    _heading(s, "Table")
    shape = s.shapes.add_table(6, 4, Inches(0.7), Inches(1.6),
                               Inches(11.9), Inches(4.5))
    table = shape.table
    headers = ["Metric", "Q3", "Q4", "Δ"]
    for c, h in enumerate(headers):
        cell = table.cell(0, c)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor.from_hex("#0B2447")
        p = cell.text_frame.paragraphs[0]
        p.font.bold = True
        p.font.color.rgb = RGBColor.from_hex("#FFFFFF")
    rows = [
        ("ARR", "$155M", "$182M", "+17%"),
        ("NDR", "124%", "131%", "+7pt"),
        ("Customers", "1,204", "1,389", "+15%"),
        ("Gross margin", "80%", "82%", "+2pt"),
        ("Churn", "1.8%", "1.4%", "-0.4pt"),
    ]
    for r, row in enumerate(rows, start=1):
        for c, v in enumerate(row):
            cell = table.cell(r, c)
            cell.text = v
            cell.borders.bottom.color.rgb = RGBColor.from_hex("#E5E7EB")
            cell.borders.bottom.width = Pt(0.5)


def _diagram_slides(prs):
    s = blank(prs)
    _heading(s, "Pipeline")
    horizontal_pipeline(s, BBox.from_inches(0.6, 3.0, 12.1, 1.6),
                        steps=["Plan", "Build", "Ship", "Measure"],
                        accent="#C9A227")
    s = blank(prs)
    _heading(s, "Hub & spoke")
    hub_and_spoke(s, BBox.from_inches(3, 1.4, 7.3, 5.6), centre="Core",
                  spokes=["Sales", "Eng", "Ops", "Finance", "People"],
                  accent="#0B2447", hub_fill="#0B2447", hub_text_color="#FFFFFF")
    s = blank(prs)
    _heading(s, "Cycle")
    cycle(s, BBox.from_inches(3, 1.6, 7.3, 5.4),
          steps=["Discover", "Define", "Design", "Deliver"])
    s = blank(prs)
    _heading(s, "Decision tree")
    decision_tree(s, BBox.from_inches(0.7, 1.5, 11.9, 5.6), root="Deal?",
                  branches=[{"label": "Qualified", "children": ["Propose", "Close"]},
                            {"label": "Unqualified", "children": ["Nurture"]}],
                  fill="#141A23", text_color="#E6EDF3",
                  root_fill="#C9A227", root_text_color="#0B0E14")
    s = blank(prs)
    _heading(s, "Comparison")
    comparison_columns(s, BBox.from_inches(0.6, 1.6, 12.1, 5.2),
                       columns=[{"title": "Now", "body": ["Manual", "Slow"]},
                                {"title": "Next", "body": ["Automated", "Fast"]}],
                       header_fill="#0B2447", header_text_color="#FFFFFF")


def _picture_slide(prs):
    s = blank(prs)
    pic = s.shapes.add_picture(str(ASSETS / "hero.jpg"), 0, 0,
                               width=SLIDE_W, height=SLIDE_H)
    pic.effects.set_duotone(RGBColor.from_hex("#0B2447"), "#C9A227")
    band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, SLIDE_H - Inches(1.6),
                              SLIDE_W, Inches(1.6))
    band.fill.solid()
    band.fill.fore_color.rgb = RGBColor.from_hex("#0B2447")
    band.fill.fore_color.alpha = 0.6
    band.line.fill.background()
    tb = s.shapes.add_textbox(Inches(0.6), SLIDE_H - Inches(1.3),
                              Inches(12), Inches(0.9))
    tf = tb.text_frame
    tf.text = "Duotoned hero with overlay"
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    tf.paragraphs[0].font.size = Pt(30)
    tf.paragraphs[0].font.bold = True
    tf.paragraphs[0].font.color.rgb = RGBColor.from_hex("#FFFFFF")


def build():
    _ensure_assets()
    prs = deck()

    _cover(prs)
    # recipe slides (build their own slides)
    title_slide(prs, title="Section: Foundations", subtitle="Tokens & recipes",
                tokens=TOKENS, transition="morph")
    kpi_slide(prs, title="Headline KPIs", kpis=[
        {"label": "ARR", "value": "$182M", "delta": +0.27},
        {"label": "NDR", "value": "131%", "delta": +0.07},
        {"label": "Customers", "value": "1,389", "delta": +0.15},
    ], tokens=TOKENS)
    bullet_slide(prs, title="Why this matters", bullets=[
        "Every feature exercised in one place.",
        "Cross-feature interactions surface here.",
        "Lint + round-trip gate the whole deck.",
    ], tokens=TOKENS)

    _effects_slide(prs)
    _three_d_slide(prs)
    _chart_slide(prs)
    _table_slide(prs)
    _diagram_slides(prs)
    _picture_slide(prs)

    quote_slide(prs, quote="One deck to find every bug.",
                attribution="The harness", tokens=TOKENS)

    # deck-wide transition, preserving the morph on the section divider
    prs.set_transition(kind=MSO_TRANSITION_TYPE.FADE, duration=500)

    return prs


if __name__ == "__main__":
    save(build(), "13_mega_kitchen_sink.pptx")
