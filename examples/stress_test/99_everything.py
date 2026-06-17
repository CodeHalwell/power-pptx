"""THE EVERYTHING DECK — one presentation that touches every capability and
method I can reach, with the interaction-heavy combinations the focused decks
keep apart (effects + 3D + animation + transition on the same shapes; charts,
tables, diagrams, pictures, OLE, movies, freeform, groups; recipes; theme
read/write/apply; import_slide; apply_template).

A final ``_introspect`` pass *reads* a huge number of properties off every
shape on every slide — reads must never mutate the XML, so any read-mutation
bug shows up as a round-trip diff in the harness.

This is a deliberate bug probe. It is NOT a recommended authoring pattern —
in particular it generates ``power_pptx.animation`` calls, which the skill's
house rules tell normal decks to avoid (playback is broken in PowerPoint).
"""

from __future__ import annotations

import io
from pathlib import Path

from _util import SLIDE_H, SLIDE_W, blank, deck

from power_pptx import BBox
from power_pptx.animation import MotionPath, PP_ANIM_TRIGGER as TR
from power_pptx.chart.data import BubbleChartData, CategoryChartData, XyChartData
from power_pptx.compose import from_spec
from power_pptx.design.layout import Grid, Stack
from power_pptx.design.recipes import (
    bullet_slide,
    image_hero_slide,
    kpi_slide,
    quote_slide,
    title_slide,
)
from power_pptx.design.tokens import DesignTokens
from power_pptx.diagrams import (
    comparison_columns,
    cycle,
    decision_tree,
    horizontal_pipeline,
    hub_and_spoke,
    vertical_pipeline,
)
from power_pptx.dml.color import RGBColor
from power_pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from power_pptx.enum.dml import (
    BevelPreset,
    MSO_LINE_CAP_STYLE,
    MSO_LINE_COMPOUND_STYLE,
    MSO_LINE_DASH_STYLE,
    MSO_LINE_END_TYPE,
    MSO_LINE_JOIN_STYLE,
    MSO_PATTERN_TYPE,
    MSO_THEME_COLOR,
    PresetMaterial,
)
from power_pptx.enum.presentation import MSO_TRANSITION_TYPE
from power_pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from power_pptx.enum.text import (
    MSO_TEXT_UNDERLINE_TYPE,
    MSO_VERTICAL_ANCHOR,
    PP_ALIGN,
)
from power_pptx.util import Inches, Pt

ASSETS = Path(__file__).parent / "_assets"

TOKENS = DesignTokens.from_dict({
    "palette": {
        "primary": "#4F46E5", "accent": "#06B6D4", "neutral": "#0F172A",
        "muted": "#64748B", "surface": "#F1F5F9", "background": "#FFFFFF",
        "on_primary": "#FFFFFF", "positive": "#16A34A", "negative": "#DC2626",
    },
    "typography": {
        "heading": {"family": "Inter", "size": 40.0, "bold": True},
        "body": {"family": "Inter", "size": 18.0},
        "caption": {"family": "Inter", "size": 12.0, "italic": True},
    },
    "shadows": {"card": {"blur": 18.0, "distance": 4.0, "alpha": 0.18}},
    "radii": {"card": 12.0}, "spacings": {"sm": 8.0, "md": 16.0, "lg": 32.0},
})
PALETTE = ["#4F46E5", "#06B6D4", "#16A34A", "#F59E0B", "#EC4899", "#8B5CF6"]


def _assets():
    ASSETS.mkdir(exist_ok=True)
    from PIL import Image, ImageDraw
    jpg = ASSETS / "ev_hero.jpg"
    img = Image.new("RGB", (800, 500))
    d = ImageDraw.Draw(img)
    for y in range(0, 500, 5):
        d.line([(0, y), (800, y)], fill=(y % 256, (2 * y) % 256, (3 * y) % 256), width=5)
    img.save(jpg, "JPEG", quality=80)
    png = ASSETS / "ev_logo.png"
    p = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    dd = ImageDraw.Draw(p)
    dd.ellipse([10, 10, 290, 290], fill=(79, 70, 229, 255))
    p.save(png, "PNG")
    svg = ASSETS / "ev_mark.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
        '<rect width="200" height="200" fill="#0F172A"/>'
        '<circle cx="100" cy="100" r="70" fill="#06B6D4"/></svg>'
    )
    fb = ASSETS / "ev_mark.png"
    fimg = Image.new("RGB", (200, 200), (15, 23, 42))
    ImageDraw.Draw(fimg).ellipse([30, 30, 170, 170], fill=(6, 182, 212))
    fimg.save(fb, "PNG")
    return jpg, png, svg, fb


def _hx(s):
    return RGBColor.from_hex(s)


def _heading(s, text):
    box = s.shapes.add_textbox(Inches(0.5), Inches(0.25), Inches(12.3), Inches(0.8))
    tf = box.text_frame
    tf.word_wrap = True
    tf.text = text
    tf.fit_text(font_family="Inter", max_size=30, bold=True)
    tf.paragraphs[0].font.color.rgb = _hx("#0F172A")


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
def sec_cover(prs):
    s = blank(prs)
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.gradient(kind="rectangular")
    bg.fill.gradient_stops.replace([(0.0, "#4F46E5"), (0.5, "#06B6D4"), (1.0, "#0F172A")])
    bg.line.fill.background()
    title = s.shapes.add_textbox(Inches(0.8), Inches(2.4), Inches(11.7), Inches(1.6))
    tf = title.text_frame
    tf.word_wrap = True
    tf.text = "The Everything Deck"
    tf.fit_text(font_family="Inter", max_size=60, bold=True)
    tf.paragraphs[0].font.color.rgb = _hx("#FFFFFF")
    s.shapes.add_text(
        BBox.from_inches(0.8, 4.1, 11.7, 0.8),
        text="Every capability, one file — and a read-everything pass",
        font="Inter", size_pt=22, color="#E0F2FE", align="left", anchor="top",
    )
    s.transition.kind = MSO_TRANSITION_TYPE.MORPH
    s.transition.duration = 1200
    badge = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(11.0), Inches(0.6), Inches(1.6), Inches(1.6))
    badge.fill.solid()
    badge.fill.fore_color.rgb = _hx("#F59E0B")
    badge.line.fill.background()
    td = badge.three_d
    td.bevel_top.preset = BevelPreset.SOFT_ROUND
    td.bevel_top.width = Pt(8)
    td.bevel_top.height = Pt(4)
    td.preset_material = PresetMaterial.METAL
    badge.shadow.blur_radius = Pt(12)
    badge.shadow.color.alpha = 0.3


def sec_autoshapes(prs):
    s = blank(prs)
    _heading(s, "Autoshapes · fills · lines · effects")
    shapes = [MSO_SHAPE.ROUNDED_RECTANGLE, MSO_SHAPE.OVAL, MSO_SHAPE.DIAMOND,
              MSO_SHAPE.HEXAGON, MSO_SHAPE.CHEVRON, MSO_SHAPE.PENTAGON,
              MSO_SHAPE.STAR_5_POINT, MSO_SHAPE.CLOUD, MSO_SHAPE.HEART,
              MSO_SHAPE.LIGHTNING_BOLT, MSO_SHAPE.SMILEY_FACE, MSO_SHAPE.SUN]
    for i, shp in enumerate(shapes):
        col, row = i % 6, i // 6
        sh = s.shapes.add_shape(shp, Inches(0.4 + col * 2.15), Inches(1.4 + row * 2.6),
                                Inches(1.9), Inches(2.2))
        sh.fill.solid()
        sh.fill.fore_color.rgb = _hx(PALETTE[i % len(PALETTE)])
        sh.fill.fore_color.alpha = 0.85
        sh.line.color.rgb = _hx("#0F172A")
        sh.line.width = Pt(1.5)
        if i % 2:
            sh.shadow.blur_radius = Pt(10)
            sh.shadow.distance = Pt(3)
            sh.shadow.color.alpha = 0.3
        else:
            sh.glow.radius = Pt(6)
            sh.glow.color = _hx(PALETTE[i % len(PALETTE)])
        try:
            sh.rotation = i * 7
        except Exception:
            pass
    # adjustments on a chevron
    chev = s.shapes.add_shape(MSO_SHAPE.CHEVRON, Inches(10), Inches(0.3), Inches(2.8), Inches(0.9))
    if chev.adjustments:
        chev.adjustments[0] = 0.6
    chev.fill.solid()
    chev.fill.fore_color.rgb = _hx("#8B5CF6")


def sec_lines_gradients(prs):
    s = blank(prs)
    _heading(s, "Gradients · patterns · line styles · arrowheads")
    for i, kind in enumerate(["linear", "radial", "rectangular", "shape"]):
        sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.4 + i * 3.2), Inches(1.3),
                                Inches(2.9), Inches(1.8))
        sh.fill.gradient(kind=kind)
        stops = sh.fill.gradient_stops
        stops.replace([(0.0, "#4F46E5"), (1.0, "#06B6D4")])
        stops.append(0.5, "#EC4899")
        del stops[1]
        sh.line.fill.background()
    # pattern fills
    pats = [MSO_PATTERN_TYPE.WAVE, MSO_PATTERN_TYPE.WIDE_DOWNWARD_DIAGONAL,
            MSO_PATTERN_TYPE.PERCENT_40, MSO_PATTERN_TYPE.DOTTED_GRID]
    for i, pat in enumerate(pats):
        sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.4 + i * 3.2), Inches(3.3),
                                Inches(2.9), Inches(1.3))
        sh.fill.patterned()
        sh.fill.pattern = pat
        sh.fill.fore_color.rgb = _hx(PALETTE[i])
        sh.fill.back_color.rgb = _hx("#FFFFFF")
        sh.line.fill.background()
    # connectors with every arrowhead + dash + cap/join/compound
    ends = [MSO_LINE_END_TYPE.TRIANGLE, MSO_LINE_END_TYPE.STEALTH,
            MSO_LINE_END_TYPE.OVAL, MSO_LINE_END_TYPE.DIAMOND, MSO_LINE_END_TYPE.ARROW]
    dashes = [MSO_LINE_DASH_STYLE.SOLID, MSO_LINE_DASH_STYLE.DASH,
              MSO_LINE_DASH_STYLE.DASH_DOT, MSO_LINE_DASH_STYLE.ROUND_DOT,
              MSO_LINE_DASH_STYLE.LONG_DASH]
    for i, (end, dash) in enumerate(zip(ends, dashes)):
        c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(0.6),
                                   Inches(5.0 + i * 0.45), Inches(12.7), Inches(5.0 + i * 0.45))
        ln = c.line
        ln.width = Pt(2.5)
        ln.color.rgb = _hx("#0F172A")
        ln.color.alpha = 0.8
        ln.dash_style = dash
        ln.cap = MSO_LINE_CAP_STYLE.ROUND
        ln.join = MSO_LINE_JOIN_STYLE.BEVEL
        ln.compound = MSO_LINE_COMPOUND_STYLE.SINGLE
        ln.head_end.type = end
        ln.tail_end.type = MSO_LINE_END_TYPE.OVAL


def sec_3d(prs):
    s = blank(prs)
    _heading(s, "3-D · bevels · extrusion · contour · materials")
    bevels = [BevelPreset.RELAXED_INSET, BevelPreset.CIRCLE, BevelPreset.SLOPE,
              BevelPreset.CONVEX, BevelPreset.SOFT_ROUND, BevelPreset.ART_DECO]
    mats = [PresetMaterial.MATTE, PresetMaterial.PLASTIC, PresetMaterial.METAL,
            PresetMaterial.WARM_MATTE, PresetMaterial.SOFT_METAL, PresetMaterial.POWDER]
    for i, (bev, mat) in enumerate(zip(bevels, mats)):
        sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                Inches(0.4 + (i % 3) * 4.3), Inches(1.4 + (i // 3) * 2.8),
                                Inches(3.9), Inches(2.4))
        sh.fill.solid()
        sh.fill.fore_color.rgb = _hx(PALETTE[i])
        sh.line.fill.background()
        td = sh.three_d
        td.bevel_top.preset = bev
        td.bevel_top.width = Pt(8)
        td.bevel_top.height = Pt(4)
        td.bevel_bottom.preset = BevelPreset.ANGLE
        td.bevel_bottom.width = Pt(3)
        td.extrusion_height = Pt(18)
        td.extrusion_color = _hx("#0F172A")
        td.contour_width = Pt(1)
        td.contour_color = _hx("#FFFFFF")
        td.preset_material = mat
        sh.text_frame.text = f"{bev.name}\n{mat.name}"


def sec_charts(prs):
    cats = ["Q1", "Q2", "Q3", "Q4"]

    def cat():
        d = CategoryChartData()
        d.categories = cats
        d.add_series("ARR", (100, 130, 155, 182))
        d.add_series("NDR", (115, 118, 124, 131))
        d.add_series("Pipe", (60, 75, 90, 110))
        return d

    for ct, ql in [
        (XL_CHART_TYPE.COLUMN_CLUSTERED, "title_axes_legend_bottom"),
        (XL_CHART_TYPE.LINE_MARKERS, "title_legend_right"),
        (XL_CHART_TYPE.AREA_STACKED, "minimal"),
        (XL_CHART_TYPE.RADAR_MARKERS, "title_legend_top"),
    ]:
        s = blank(prs)
        _heading(s, f"Chart · {ct}")
        chart = s.shapes.add_chart(ct, Inches(0.7), Inches(1.3), Inches(11.9),
                                   Inches(5.7), cat()).chart
        chart.apply_palette(PALETTE)
        chart.apply_quick_layout(ql)
        g = chart.series[0].format.fill
        g.gradient(kind="linear")
        g.gradient_stops.replace([(0.0, "#4F46E5"), (1.0, "#06B6D4")])
        pat = chart.series[1].format.fill
        pat.patterned()
        pat.pattern = MSO_PATTERN_TYPE.WIDE_UPWARD_DIAGONAL
        pat.fore_color.rgb = _hx("#16A34A")
        pat.back_color.rgb = _hx("#FFFFFF")

    # pie via color_by_category + custom layout dict + data labels
    s = blank(prs)
    _heading(s, "Chart · PIE (color_by_category, data labels)")
    pd = CategoryChartData()
    pd.categories = ["A", "B", "C", "D", "E"]
    pd.add_series("Share", (30, 25, 20, 15, 10))
    chart = s.shapes.add_chart(XL_CHART_TYPE.PIE, Inches(2.5), Inches(1.4),
                               Inches(8.3), Inches(5.4), pd).chart
    chart.color_by_category(PALETTE)
    chart.apply_quick_layout({"has_title": True, "title_text": "Share",
                              "has_legend": True, "legend_position": "right"})
    chart.plots[0].has_data_labels = True
    dl = chart.plots[0].data_labels
    dl.number_format = "0%"
    dl.number_format_is_linked = False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END

    # bubble + scatter + axis scaling
    s = blank(prs)
    _heading(s, "Chart · bubble + scatter")
    bub = BubbleChartData()
    bs = bub.add_series("b")
    for i in range(6):
        bs.add_data_point(i, i * 1.5, (i + 1) * 2)
    chart = s.shapes.add_chart(XL_CHART_TYPE.BUBBLE, Inches(0.7), Inches(1.3),
                               Inches(6.0), Inches(5.5), bub).chart
    chart.apply_palette("vibrant")
    xy = XyChartData()
    xs = xy.add_series("xy")
    for i in range(8):
        xs.add_data_point(i, i * i)
    chart2 = s.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER_LINES, Inches(7.0),
                                Inches(1.3), Inches(5.9), Inches(5.5), xy).chart
    chart2.value_axis.minimum_scale = 0
    chart2.value_axis.maximum_scale = 64
    chart2.value_axis.has_major_gridlines = True
    chart2.apply_quick_layout({"has_legend": True,
                               "legend_position": XL_LEGEND_POSITION.BOTTOM})


def sec_tables(prs):
    s = blank(prs)
    _heading(s, "Table · merges · all border helpers · fills")
    t = s.shapes.add_table(7, 5, Inches(0.6), Inches(1.3), Inches(12.1), Inches(5.4)).table
    headers = ["Segment", "Q3", "Q4", "Δ", "Status"]
    for c, h in enumerate(headers):
        cell = t.cell(0, c)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = _hx("#0F172A")
        p = cell.text_frame.paragraphs[0]
        p.font.bold = True
        p.font.color.rgb = _hx("#FFFFFF")
        cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
        cell.borders.bottom.color.rgb = _hx("#06B6D4")
        cell.borders.bottom.width = Pt(2)
    rows = [
        ("Enterprise", "$60M", "$72M", "+20%", "On track"),
        ("Mid-market", "$40M", "$48M", "+20%", "On track"),
        ("SMB", "$30M", "$33M", "+10%", "Watch"),
        ("Partner", "$15M", "$19M", "+27%", "Ahead"),
        ("Other", "$10M", "$10M", "0%", "Flat"),
    ]
    for r, row in enumerate(rows, start=1):
        for c, v in enumerate(row):
            cell = t.cell(r, c)
            cell.text = v
            cell.margin_left = cell.margin_right = Pt(10)
            cell.margin_top = cell.margin_bottom = Pt(6)
            if r % 2 == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = _hx("#F1F5F9")
            cell.borders.bottom.color.rgb = _hx("#E5E7EB")
            cell.borders.bottom.width = Pt(0.5)
    # total row merged across first two cols + diagonal accent
    t.cell(6, 0).merge(t.cell(6, 1))
    t.cell(6, 0).text = "Total"
    t.cell(6, 0).borders.all(width=Pt(1), color=_hx("#0F172A"))
    t.cell(6, 4).borders.diagonal_down.color.rgb = _hx("#DC2626")
    t.cell(6, 4).borders.diagonal_down.width = Pt(1.5)
    t.columns[0].width = Inches(3.5)


def sec_diagrams(prs):
    s = blank(prs)
    _heading(s, "Diagram · horizontal pipeline")
    horizontal_pipeline(s, BBox.from_inches(0.5, 3.0, 12.3, 1.7),
                        steps=["Plan", "Build", "Ship", "Learn"], accent="#4F46E5")
    s = blank(prs)
    _heading(s, "Diagram · vertical pipeline + hub & spoke")
    vertical_pipeline(s, BBox.from_inches(0.6, 1.3, 3.6, 5.6),
                      steps=["Intake", "Triage", "Resolve", "Verify"], accent="#06B6D4")
    hub_and_spoke(s, BBox.from_inches(4.6, 1.3, 8.2, 5.6), centre="Core",
                  spokes=["A", "B", "C", "D", "E", "F"], accent="#8B5CF6",
                  hub_fill="#8B5CF6", hub_text_color="#FFFFFF")
    s = blank(prs)
    _heading(s, "Diagram · cycle + decision tree + comparison")
    cycle(s, BBox.from_inches(0.4, 1.3, 4.0, 5.5), steps=["Plan", "Do", "Check", "Act"])
    decision_tree(s, BBox.from_inches(4.6, 1.3, 4.0, 5.5), root="Q?",
                  branches=[{"label": "Yes", "children": ["Go"]}, "No"],
                  fill="#0F172A", text_color="#E2E8F0",
                  root_fill="#06B6D4", root_text_color="#0F172A")
    comparison_columns(s, BBox.from_inches(8.9, 1.3, 4.0, 5.5),
                       columns=[{"title": "Now", "body": ["Manual"]},
                                {"title": "Next", "body": ["Auto"]}],
                       header_fill="#4F46E5", header_text_color="#FFFFFF")


def sec_pictures(prs, jpg, png, svg, fb):
    s = blank(prs)
    pic = s.shapes.add_picture(str(jpg), 0, 0, width=SLIDE_W, height=SLIDE_H)
    pic.effects.set_duotone(_hx("#0F172A"), "#06B6D4")
    band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, SLIDE_H - Inches(1.5),
                              SLIDE_W, Inches(1.5))
    band.fill.solid()
    band.fill.fore_color.rgb = _hx("#0F172A")
    band.fill.fore_color.alpha = 0.6
    band.line.fill.background()
    s.shapes.add_text(BBox.from_inches(0.6, SLIDE_H.inches - 1.25, 12, 0.9),
                      text="Duotoned hero + overlay", font="Inter", size_pt=30,
                      bold=True, color="#FFFFFF")
    s = blank(prs)
    _heading(s, "Picture filters · recolor · transparency · SVG")
    for i, preset in enumerate(["grayscale", "sepia", "washout"]):
        p = s.shapes.add_picture(str(jpg), Inches(0.4 + i * 4.3), Inches(1.4),
                                 Inches(4.0), Inches(2.5))
        p.effects.recolor = preset
        s.shapes.add_text(BBox.from_inches(0.4 + i * 4.3, 4.0, 4.0, 0.4),
                          text=preset, font="Inter", size_pt=14, color="#0F172A")
    p2 = s.shapes.add_picture(str(jpg), Inches(0.4), Inches(4.6), Inches(4.0), Inches(2.4))
    p2.effects.brightness = 0.2
    p2.effects.contrast = 0.15
    p2.effects.transparency = 0.25
    p2.crop_left = 0.1
    p2.crop_right = 0.1
    p2.crop_top = 0.05
    p2.crop_bottom = 0.05
    p2.line.color.rgb = _hx("#0F172A")
    p2.line.width = Pt(2)
    p2.shadow.blur_radius = Pt(10)
    p2.shadow.color.alpha = 0.4
    s.shapes.add_picture(str(png), Inches(5.0), Inches(4.6), Inches(2.2), Inches(2.2))
    s.shapes.add_svg_picture(str(svg), Inches(7.6), Inches(4.6),
                             width=Inches(2.2), height=Inches(2.2), png_fallback=str(fb))


def sec_text(prs):
    s = blank(prs)
    _heading(s, "Text · levels · runs · underline · hyperlink · defaults")
    box = s.shapes.add_textbox(Inches(0.6), Inches(1.3), Inches(7.5), Inches(5.6))
    tf = box.text_frame
    tf.word_wrap = True
    tf.set_paragraph_defaults(font_name="Inter", size=Pt(16), color="#0F172A")
    tf.text = "Level 0 — outline root"
    for lvl in range(1, 5):
        p = tf.add_paragraph()
        p.text = f"Level {lvl} nested bullet"
        p.level = lvl
        p.space_before = Pt(4)
        p.space_after = Pt(2)
        p.line_spacing = 1.1
    # rich runs
    box2 = s.shapes.add_textbox(Inches(8.3), Inches(1.3), Inches(4.5), Inches(5.6))
    tf2 = box2.text_frame
    tf2.word_wrap = True
    para = tf2.paragraphs[0]
    para.alignment = PP_ALIGN.LEFT
    r1 = para.add_run(); r1.text = "Bold "; r1.font.bold = True; r1.font.size = Pt(18)
    r2 = para.add_run(); r2.text = "italic "; r2.font.italic = True
    r3 = para.add_run(); r3.text = "underlined "
    r3.font.underline = MSO_TEXT_UNDERLINE_TYPE.WAVY_LINE
    r4 = para.add_run(); r4.text = "colored\n"
    r4.font.color.rgb = _hx("#DC2626")
    r4.font.color.alpha = 0.85
    p2 = tf2.add_paragraph()
    link = p2.add_run()
    link.text = "Visit example.com"
    link.hyperlink.address = "https://example.com"
    # theme-colored run + brightness
    p3 = tf2.add_paragraph()
    rt = p3.add_run()
    rt.text = "theme accent text"
    rt.font.color.theme_color = MSO_THEME_COLOR.ACCENT_1
    rt.font.color.brightness = 0.2


def sec_freeform_groups(prs):
    s = blank(prs)
    _heading(s, "Freeform · groups (nested) · connected connectors · arrows")
    fb = s.shapes.build_freeform(Inches(1.0), Inches(2.0), scale=1.0)
    fb.add_line_segments([(Inches(3.0), Inches(1.5)), (Inches(4.0), Inches(3.5)),
                          (Inches(2.0), Inches(4.5)), (Inches(1.0), Inches(2.0))])
    free = fb.convert_to_shape()
    free.fill.solid()
    free.fill.fore_color.rgb = _hx("#06B6D4")
    free.line.color.rgb = _hx("#0F172A")
    # nested group
    g = s.shapes.add_group_shape()
    a = g.shapes.add_shape(MSO_SHAPE.OVAL, Inches(5.5), Inches(1.5), Inches(1.5), Inches(1.5))
    a.fill.solid(); a.fill.fore_color.rgb = _hx("#4F46E5")
    inner = g.shapes.add_group_shape()
    b = inner.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(7.5), Inches(2.0),
                               Inches(1.5), Inches(1.0))
    b.fill.solid(); b.fill.fore_color.rgb = _hx("#EC4899")
    c = inner.shapes.add_shape(MSO_SHAPE.STAR_5_POINT, Inches(7.5), Inches(3.3),
                               Inches(1.5), Inches(1.5))
    c.fill.solid(); c.fill.fore_color.rgb = _hx("#F59E0B")
    # connected connector between two top-level shapes
    s1 = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(5.5),
                            Inches(2.5), Inches(1.2))
    s1.fill.solid(); s1.fill.fore_color.rgb = _hx("#16A34A")
    s2 = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(9.5), Inches(5.5),
                            Inches(2.5), Inches(1.2))
    s2.fill.solid(); s2.fill.fore_color.rgb = _hx("#8B5CF6")
    conn = s.shapes.add_connector(MSO_CONNECTOR.ELBOW, Inches(3.5), Inches(6.1),
                                  Inches(9.5), Inches(6.1))
    conn.begin_connect(s1, 3)
    conn.end_connect(s2, 1)
    conn.line.width = Pt(2)
    conn.line.color.rgb = _hx("#0F172A")
    # high-level arrow helper
    s.shapes.add_arrow(s1, s2, head="stealth", color="#DC2626", weight_pt=2.0,
                       route="straight", inset_pt=6.0)


def sec_media(prs):
    s = blank(prs)
    _heading(s, "Media · movie · OLE object")
    s.shapes.add_movie(io.BytesIO(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64),
                       Inches(0.8), Inches(1.5), Inches(5.5), Inches(4.0),
                       mime_type="video/mp4")
    s.shapes.add_ole_object(io.BytesIO(b"PK\x03\x04fake-embedded-workbook"),
                            prog_id="Excel.Sheet.12", left=Inches(7.0),
                            top=Inches(1.5), width=Inches(5.0), height=Inches(4.0))


def sec_animations(prs):
    # Deliberate animation bug-probe (see module docstring).
    s = blank(prs)
    _heading(s, "Animations (bug probe) · entrance/emphasis/exit/motion")
    shapes = []
    for i in range(4):
        sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.6 + i * 3.1),
                                Inches(2.0), Inches(2.6), Inches(1.6))
        sh.fill.solid()
        sh.fill.fore_color.rgb = _hx(PALETTE[i])
        sh.text_frame.text = f"shape {i}"
        shapes.append(sh)
    s.animations.add("entrance", "fly_in", shapes[0], trigger=TR.ON_CLICK)
    s.animations.add("emphasis", "spin", shapes[1], trigger=TR.WITH_PREVIOUS)
    s.animations.add("exit", "fade", shapes[2], trigger=TR.AFTER_PREVIOUS)
    MotionPath.line(s, shapes[3], Inches(2), Inches(0))
    MotionPath.arc(s, shapes[3], Inches(1), Inches(1), height=0.5)
    MotionPath.circle(s, shapes[3], Inches(1))
    # by-paragraph reveal + typewriter cascade + sequence
    tb = s.shapes.add_textbox(Inches(0.6), Inches(4.2), Inches(8), Inches(2.5))
    tf = tb.text_frame
    tf.text = "first"
    tf.add_paragraph().text = "second"
    tf.add_paragraph().text = "third"
    s.animations.add("entrance", "fade", tb, by_paragraph=True)
    cascade = [s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(9 + i * 1.2), Inches(4.4),
                                  Inches(1.0), Inches(1.0)) for i in range(3)]
    for sh in cascade:
        sh.fill.solid(); sh.fill.fore_color.rgb = _hx("#06B6D4")
    s.animations.typewriter(cascade)
    with s.animations.sequence() as seq:
        for sh in cascade:
            seq.add("emphasis", "pulse", sh)


def sec_notes_bg_links(prs):
    s = blank(prs)
    bg = s.background
    bg.fill.solid()
    bg.fill.fore_color.rgb = _hx("#0F172A")
    s.shapes.add_text(BBox.from_inches(0.8, 2.8, 11.7, 1.5),
                      text="Slide background + notes + navigation links",
                      font="Inter", size_pt=34, bold=True, color="#FFFFFF", align="center")
    ns = s.notes_slide
    ns.notes_text_frame.text = "These are speaker notes.\nThey have two lines."
    nav = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(5.4), Inches(5.0),
                             Inches(2.5), Inches(0.9))
    nav.fill.solid()
    nav.fill.fore_color.rgb = _hx("#06B6D4")
    nav.text_frame.text = "Jump to cover"
    nav.click_action.target_slide = prs.slides[0]


def sec_design_system(prs):
    # Grid + Stack + style facade
    s = blank(prs)
    _heading(s, "Design system · Grid · Stack · style facade")
    grid = Grid(s, cols=12, rows=6, gutter=Pt(10), margin=Pt(40))
    for i, (c, r, cs, rs) in enumerate([(0, 1, 4, 2), (4, 1, 4, 2), (8, 1, 4, 2),
                                        (0, 3, 6, 2), (6, 3, 6, 2)]):
        card = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, 0, 0, Pt(10), Pt(10))
        grid.place(card, col=c, row=r, col_span=cs, row_span=rs)
        card.style.fill = TOKENS.palette["primary"] if i % 2 else TOKENS.palette["surface"]
        card.style.shadow = TOKENS.shadows["card"]
        card.style.text_color = TOKENS.palette["on_primary"] if i % 2 else TOKENS.palette["neutral"]
        card.style.font = TOKENS.typography["body"]
        card.text_frame.text = f"card {i}"
    # The two wide cards (row 3, span 2) bottom out near y=421pt; place the chip
    # row safely below that so the Stack doesn't overlap the Grid cards.
    stack = Stack(direction="horizontal", gap=Pt(12), left=Pt(40), top=Pt(440), width=Pt(840))
    for label in ["one", "two", "three", "four"]:
        chip = s.shapes.add_shape(MSO_SHAPE.OVAL, 0, 0, Pt(10), Pt(10))
        stack.place(chip, width=Pt(120), height=Pt(85))
        chip.style.fill = TOKENS.palette["accent"]
        chip.text_frame.text = label

    # recipes (each adds its own slide)
    title_slide(prs, title="Recipes", subtitle="title/bullet/kpi/quote/image_hero",
                tokens=TOKENS, transition="fade")
    bullet_slide(prs, title="Bullets", bullets=["Alpha", "Beta", "Gamma", "Delta"],
                 tokens=TOKENS)
    kpi_slide(prs, title="KPIs", kpis=[
        {"label": "ARR", "value": "$182M", "delta": +0.27},
        {"label": "NDR", "value": "131%", "delta": +0.03},
        {"label": "CAC", "value": "8 mo", "delta": -0.10},
    ], tokens=TOKENS)
    quote_slide(prs, quote="Everything in one deck.", attribution="The harness",
                tokens=TOKENS)
    image_hero_slide(prs, title="Image hero", image=str(ASSETS / "ev_hero.jpg"),
                     tokens=TOKENS)


def sec_import(prs):
    # Build a small from_spec deck and import its slides into the mega deck.
    sub = from_spec({
        "slide_size": "16:9",
        "tokens": {"preset": "modern_light"},
        "slides": [
            {"layout": "title", "title": "Imported via from_spec",
             "subtitle": "import_slide across decks"},
            {"layout": "bullets", "title": "Imported bullets",
             "bullets": ["one", "two", "three"]},
        ],
    })
    for sl in sub.slides:
        prs.import_slide(sl, merge_master="dedupe")


def _introspect(prs):
    """Read a large number of properties off every shape. Reads must not mutate
    (the harness round-trip will catch it if they do)."""
    sink = []
    for slide in prs.slides:
        sink.append(slide.slide_id)
        sink.append(slide.transition.kind)
        sink.append(slide.transition.duration)
        sink.append(slide.has_notes_slide)
        for shape in slide.shapes:
            sink.append((shape.shape_type, shape.name, shape.shape_id))
            for attr in ("left", "top", "width", "height", "rotation"):
                sink.append(getattr(shape, attr, None))
            try:
                sink.append(shape.bbox)
            except Exception:
                pass
            if shape.has_text_frame:
                tf = shape.text_frame
                sink.append((tf.auto_size, tf.word_wrap, tf.text))
                for p in tf.paragraphs:
                    sink.append((p.level, p.alignment))
                    for r in p.runs:
                        sink.append((r.text, r.font.bold, r.font.italic, r.font.size))
                        sink.append(r.font.color.type)
            for eff in ("shadow", "glow", "soft_edges", "reflection", "blur"):
                try:
                    proxy = getattr(shape, eff, None)
                except NotImplementedError:
                    # Effect proxies aren't supported on GraphicFrame — explicit
                    # NotImplementedError on read; skip rather than crash.
                    continue
                if proxy is not None:
                    sink.append(getattr(proxy, "radius", None) if eff in ("glow", "soft_edges")
                                else getattr(proxy, "blur_radius", None))
            try:
                sink.append(shape.fill.type)
            except Exception:
                pass
            try:
                sink.append(shape.line.width)
                sink.append(shape.line.dash_style)
            except Exception:
                pass
            try:
                td = getattr(shape, "three_d", None)
            except NotImplementedError:
                td = None
            if td is not None:
                sink.append(td.extrusion_height)
                sink.append(td.bevel_top.preset)
            if shape.has_chart:
                sink.append(shape.chart.chart_type)
                for ser in shape.chart.series:
                    sink.append(ser.name)
            if shape.has_table:
                tbl = shape.table
                for row in tbl.rows:
                    for cell in row.cells:
                        sink.append(cell.text)
                        sink.append(cell.borders.bottom.width)
    return len(sink)


def build():
    jpg, png, svg, fb = _assets()
    prs = deck()

    sec_cover(prs)
    sec_autoshapes(prs)
    sec_lines_gradients(prs)
    sec_3d(prs)
    sec_charts(prs)
    sec_tables(prs)
    sec_diagrams(prs)
    sec_pictures(prs, jpg, png, svg, fb)
    sec_text(prs)
    sec_freeform_groups(prs)
    sec_media(prs)
    sec_animations(prs)
    sec_notes_bg_links(prs)
    sec_design_system(prs)
    sec_import(prs)

    # core properties
    import datetime
    cp = prs.core_properties
    cp.author = "power-pptx stress harness"
    cp.title = "The Everything Deck"
    cp.subject = "bug surfacing"
    cp.keywords = "stress, schema, everything"
    cp.comments = "Generated to exercise every capability in one file."
    cp.category = "test"
    cp.created = datetime.datetime(2026, 6, 17)
    cp.last_modified_by = "harness"

    # theme write + apply from a second deck
    for slot, rgb in [(MSO_THEME_COLOR.ACCENT_1, _hx("#4F46E5")),
                      (MSO_THEME_COLOR.ACCENT_2, _hx("#06B6D4")),
                      (MSO_THEME_COLOR.HYPERLINK, _hx("#4F46E5"))]:
        prs.theme.colors[slot] = rgb
    prs.theme.fonts.major = "Inter"
    prs.theme.fonts.minor = "Inter"

    # deck-wide transition (preserves the per-slide MORPH on the cover)
    prs.set_transition(kind=MSO_TRANSITION_TYPE.FADE, duration=500)

    # read-everything pass — reads must not mutate
    _introspect(prs)

    return prs


if __name__ == "__main__":
    build().save("_out/99_everything.pptx")
