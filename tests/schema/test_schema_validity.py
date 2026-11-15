"""Validate decks built through the public API against the ISO-29500 schemas.

These are regression guards for the "generates fine but PowerPoint reports it
as broken / repairs it" class of bug.  Each test builds a deck exercising a
feature area and asserts that every part with a known schema validates — the
check that ordinary "does it reopen" tests miss.
"""

from __future__ import annotations

import io

import pytest

from power_pptx import Presentation
from power_pptx.util import Inches, Pt

from .oxml_schema_validator import (
    assert_schema_valid,
    iter_schema_violations,
    schema_validation_available,
)

pytestmark = pytest.mark.skipif(
    not schema_validation_available(),
    reason="lxml or the bundled ISO-29500 XSD schemas are unavailable",
)


def _saved(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _blank_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


# ---------------------------------------------------------------------------
# Deck builders — each returns a saved .pptx as bytes.
# ---------------------------------------------------------------------------


def _deck_blank() -> bytes:
    prs = Presentation()
    _blank_slide(prs)
    return _saved(prs)


def _deck_effects_and_3d() -> bytes:
    from power_pptx.dml.color import RGBColor
    from power_pptx.enum.dml import BevelPreset, PresetMaterial
    from power_pptx.enum.shapes import MSO_SHAPE

    prs = Presentation()
    s = _blank_slide(prs)
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1), Inches(1), Inches(3), Inches(1.5))
    sh.fill.solid()
    sh.fill.fore_color.rgb = RGBColor(0x33, 0xA7, 0xFF)
    # geometry-only shadow + glow (must still carry a colour child)
    sh.shadow.blur_radius = Pt(8)
    sh.shadow.distance = Pt(3)
    sh.glow.radius = Pt(6)
    # 3-D (scene3d must be populated)
    sh.three_d.bevel_top.preset = BevelPreset.SOFT_ROUND
    sh.three_d.preset_material = PresetMaterial.METAL
    sh.three_d.extrusion_color = RGBColor(0x12, 0x1E, 0x4D)
    return _saved(prs)


def _deck_gradient() -> bytes:
    from power_pptx.enum.shapes import MSO_SHAPE

    prs = Presentation()
    s = _blank_slide(prs)
    sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(4), Inches(2))
    sh.fill.gradient()
    return _saved(prs)


def _deck_table() -> bytes:
    prs = Presentation()
    s = _blank_slide(prs)
    table = s.shapes.add_table(3, 3, Inches(1), Inches(1), Inches(6), Inches(3)).table
    for r in range(3):
        for c in range(3):
            table.cell(r, c).text = "r%dc%d" % (r, c)
    table.cell(0, 0).merge(table.cell(0, 1))
    return _saved(prs)


def _deck_chart() -> bytes:
    from power_pptx.chart.data import CategoryChartData
    from power_pptx.enum.chart import XL_CHART_TYPE

    prs = Presentation()
    s = _blank_slide(prs)
    data = CategoryChartData()
    data.categories = ["A", "B", "C"]
    data.add_series("S1", [1, 2, 3])
    data.add_series("S2", [3, 2, 1])
    chart = s.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1), Inches(8), Inches(5), data
    ).chart
    chart.has_legend = True
    chart.plots[0].has_data_labels = True
    chart.value_axis.tick_labels.number_format_is_linked = True
    return _saved(prs)


def _deck_animations() -> bytes:
    from power_pptx.enum.shapes import MSO_SHAPE

    prs = Presentation()
    s = _blank_slide(prs)
    shape = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(2), Inches(2), Inches(2), Inches(2))
    s.animations.add("entrance", "fade", shape)
    s.animations.add("emphasis", "spin", shape)
    s.animations.add("emphasis", "teeter", shape)
    return _saved(prs)


def _deck_morph_transition() -> bytes:
    from power_pptx.enum.presentation import MSO_TRANSITION_TYPE
    from power_pptx.enum.shapes import MSO_SHAPE

    prs = Presentation()
    s = _blank_slide(prs)
    s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(2), Inches(2), Inches(2), Inches(2))
    s.transition.kind = MSO_TRANSITION_TYPE.MORPH
    s.transition.duration = 600
    s2 = _blank_slide(prs)
    s2.transition.kind = MSO_TRANSITION_TYPE.FADE
    return _saved(prs)


def _deck_recipes() -> bytes:
    from power_pptx.design.recipes import bullet_slide, kpi_slide, title_slide

    prs = Presentation()
    title_slide(prs, title="Q4 Review", subtitle="April 2026")
    bullet_slide(prs, title="Highlights", bullets=["One.", "Two.", "Three."])
    kpi_slide(
        prs,
        title="Metrics",
        kpis=[{"label": "ARR", "value": "$182M", "delta": 0.27}],
    )
    return _saved(prs)


def _deck_chart_types() -> bytes:
    # Regression: every chart type must emit axis ids in PowerPoint's signed
    # int32 range (1..2**31-1). The hardcoded template ids previously exceeded
    # 2**31, which passes XSD (unsignedInt) but makes PowerPoint repair the file.
    from power_pptx.chart.data import BubbleChartData, CategoryChartData, XyChartData
    from power_pptx.enum.chart import XL_CHART_TYPE

    prs = Presentation()
    s = _blank_slide(prs)
    cat = CategoryChartData()
    cat.categories = ["A", "B", "C"]
    cat.add_series("S1", (1, 2, 3))
    cat.add_series("S2", (3, 2, 1))
    for ct in (
        XL_CHART_TYPE.COLUMN_CLUSTERED, XL_CHART_TYPE.COLUMN_STACKED,
        XL_CHART_TYPE.BAR_CLUSTERED, XL_CHART_TYPE.LINE, XL_CHART_TYPE.LINE_MARKERS,
        XL_CHART_TYPE.AREA, XL_CHART_TYPE.AREA_STACKED, XL_CHART_TYPE.RADAR,
        XL_CHART_TYPE.RADAR_MARKERS,
    ):
        s.shapes.add_chart(ct, Inches(0.5), Inches(0.5), Inches(3), Inches(2), cat)
    xy = XyChartData()
    xs = xy.add_series("xy")
    for n in range(4):
        xs.add_data_point(n, n * 2)
    s.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER, Inches(0.5), Inches(3), Inches(3), Inches(2), xy)
    bub = BubbleChartData()
    bs = bub.add_series("b")
    for n in range(4):
        bs.add_data_point(n, n, n + 1)
    s.shapes.add_chart(XL_CHART_TYPE.BUBBLE, Inches(4), Inches(3), Inches(3), Inches(2), bub)
    return _saved(prs)


def _deck_radar_chart() -> bytes:
    # Regression: radar series must not emit <c:smooth> (invalid in CT_RadarSer).
    from power_pptx.chart.data import CategoryChartData
    from power_pptx.enum.chart import XL_CHART_TYPE

    prs = Presentation()
    s = _blank_slide(prs)
    data = CategoryChartData()
    data.categories = ["A", "B", "C"]
    data.add_series("S1", [1, 2, 3])
    data.add_series("S2", [3, 2, 1])
    for ct in (XL_CHART_TYPE.RADAR, XL_CHART_TYPE.RADAR_MARKERS, XL_CHART_TYPE.RADAR_FILLED):
        s.shapes.add_chart(ct, Inches(1), Inches(1), Inches(4), Inches(3), data)
    return _saved(prs)


def _deck_soft_metal_material() -> bytes:
    # Regression: PresetMaterial.SOFT_METAL must emit the schema's "softmetal".
    from power_pptx.dml.color import RGBColor
    from power_pptx.enum.dml import PresetMaterial
    from power_pptx.enum.shapes import MSO_SHAPE

    prs = Presentation()
    s = _blank_slide(prs)
    sh = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(2), Inches(2), Inches(2), Inches(2))
    sh.fill.solid()
    sh.fill.fore_color.rgb = RGBColor(0x4F, 0x9D, 0xFF)
    sh.three_d.extrusion_height = Pt(12)
    sh.three_d.preset_material = PresetMaterial.SOFT_METAL
    return _saved(prs)


def _deck_3d_none_presets() -> bytes:
    # Regression: BevelPreset.NONE / PresetMaterial.NONE must not emit the token
    # "none" (invalid per ST_BevelPresetType / ST_PresetMaterialType, which makes
    # PowerPoint repair the file). NONE removes the bevel / clears the material.
    from power_pptx.dml.color import RGBColor
    from power_pptx.enum.dml import BevelPreset, PresetMaterial
    from power_pptx.enum.shapes import MSO_SHAPE

    prs = Presentation()
    s = _blank_slide(prs)

    # A shape that sets a real preset then turns it off via NONE.
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1), Inches(1), Inches(3), Inches(2))
    sh.fill.solid()
    sh.fill.fore_color.rgb = RGBColor(0x33, 0xA7, 0xFF)
    sh.three_d.bevel_top.preset = BevelPreset.CIRCLE
    sh.three_d.bevel_top.width = Pt(6)
    sh.three_d.bevel_top.preset = BevelPreset.NONE  # -> removes <a:bevelT>
    sh.three_d.preset_material = PresetMaterial.METAL
    sh.three_d.preset_material = PresetMaterial.NONE  # -> clears prstMaterial
    sh.three_d.extrusion_height = Pt(8)  # keep a populated sp3d so the part is real

    # A second shape that only ever assigns NONE (must not fabricate junk).
    sh2 = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(5), Inches(1), Inches(2), Inches(2))
    sh2.three_d.bevel_bottom.preset = BevelPreset.NONE
    sh2.three_d.preset_material = PresetMaterial.NONE

    # A third shape that turns things off via the enum's raw *value* (an int,
    # e.g. deserialized from JSON/config) rather than the singleton — this must
    # also route to remove/clear, not coerce the int back into "none".
    sh3 = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(8), Inches(1), Inches(2), Inches(2))
    sh3.three_d.bevel_top.preset = BevelPreset.SLOPE
    sh3.three_d.bevel_top.preset = BevelPreset.NONE.value  # int -> removes bevelT
    sh3.three_d.preset_material = PresetMaterial.NONE.value  # int -> clears attr
    sh3.three_d.extrusion_height = Pt(4)
    return _saved(prs)


def _deck_embedded_font() -> bytes:
    # Regression: embed_font wrote <p:embeddedFontLst> at the end of
    # presentation.xml, after the defaultTextStyle every template carries.
    # CT_Presentation requires it *before* defaultTextStyle, so the out-of-order
    # append made PowerPoint report the deck as needing repair.
    import os

    from power_pptx.theme import embed_font

    ttf = os.path.join(
        os.path.dirname(__file__), "..", "test_files", "calibriz.ttf"
    )
    if not os.path.isfile(ttf):
        pytest.skip("calibriz.ttf fixture is unavailable")

    prs = Presentation()
    _blank_slide(prs)
    embed_font(prs, ttf, typeface="Calibri", weight="regular")
    embed_font(prs, ttf, typeface="Calibri", weight="boldItalic")
    return _saved(prs)


def _deck_ole_objects() -> bytes:
    # Regression: two OLE objects on one slide previously both emitted the
    # inner show-as-icon <p:pic> with the hardcoded id="0", a duplicate shape
    # id that makes PowerPoint report the deck as needing repair. Each inner
    # pic must now get its own unique shape id.
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6360000002000100ffff03000006000557bfabd4000000"
        "0049454e44ae426082"
    )
    prs = Presentation()
    s = _blank_slide(prs)
    for i in range(2):
        s.shapes.add_ole_object(
            io.BytesIO(b"embedded-object-payload-%d" % i),
            prog_id="Package",
            left=Inches(1 + i * 3),
            top=Inches(1),
            width=Inches(2),
            height=Inches(2),
            icon_file=io.BytesIO(png),
        )
    return _saved(prs)


def _deck_picture_washout() -> bytes:
    # Regression: <a:biLevel> must carry its required thresh="…". That element
    # is the "black_and_white" recolor; "washout", which used to write it, is
    # now PowerPoint's <a:lum bright="70000" contrast="-70000"/>.
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6360000002000100ffff03000006000557bfabd4000000"
        "0049454e44ae426082"
    )
    prs = Presentation()
    s = _blank_slide(prs)
    pic = s.shapes.add_picture(io.BytesIO(png), Inches(1), Inches(1), Inches(2), Inches(2))
    pic.effects.recolor = "washout"
    pic2 = s.shapes.add_picture(io.BytesIO(png), Inches(4), Inches(1), Inches(2), Inches(2))
    pic2.effects.recolor = "black_and_white"
    return _saved(prs)


def _deck_transition_duration() -> bytes:
    # Regression: a duration writes p14:dur, which is only schema-valid inside an
    # mc:AlternateContent wrapper — even for a classic (non-p14) transition kind.
    from power_pptx.enum.presentation import MSO_TRANSITION_TYPE

    prs = Presentation()
    s = _blank_slide(prs)
    s.transition.kind = MSO_TRANSITION_TYPE.FADE
    s.transition.duration = 800
    s2 = _blank_slide(prs)
    s2.transition.kind = MSO_TRANSITION_TYPE.MORPH  # p14 kind + duration
    s2.transition.duration = 1200
    return _saved(prs)


def _deck_sections() -> bytes:
    # Regression: an empty section must still emit its required
    # <p14:sldIdLst/> child, and a slide added to a sectioned deck must join
    # the final section so the section list stays a complete partition.
    prs = Presentation()
    for _ in range(3):
        _blank_slide(prs)
    prs.sections.add("Intro", 0)
    prs.sections.add("Body", 2)
    prs.sections.add("Empty tail")
    _blank_slide(prs)  # joins "Empty tail"
    return _saved(prs)


def _deck_animation_removal() -> bytes:
    # Regression: removing the last animation entry (remove()/clear()/
    # purge_orphans()) left an empty <p:childTnLst>, which is schema-invalid
    # and a repair trigger. Slide 1 ends with zero animations; slide 2 keeps
    # one after a partial removal.
    from power_pptx.enum.shapes import MSO_SHAPE

    prs = Presentation()
    s1 = _blank_slide(prs)
    sh1 = s1.shapes.add_shape(MSO_SHAPE.OVAL, Inches(1), Inches(1), Inches(1), Inches(1))
    s1.animations.add("entrance", "fade", sh1)
    s1.animations.clear()

    s2 = _blank_slide(prs)
    sh2 = s2.shapes.add_shape(MSO_SHAPE.OVAL, Inches(1), Inches(1), Inches(1), Inches(1))
    s2.animations.add("entrance", "fade", sh2)
    s2.animations.add("emphasis", "pulse", sh2)
    next(iter(s2.animations)).remove()
    return _saved(prs)


def _deck_label_collision_strategy() -> bytes:
    # Regression: collision_strategy created <c:gapWidth> by bare append,
    # landing it after <c:axId> — out of sequence in CT_BarChart.
    from power_pptx.chart.data import CategoryChartData
    from power_pptx.enum.chart import XL_CHART_TYPE

    prs = Presentation()
    s = _blank_slide(prs)
    data = CategoryChartData()
    data.categories = ["A", "B", "C", "D", "E"]
    data.add_series("S1", (1, 2, 3, 4, 5))
    data.add_series("S2", (5, 4, 3, 2, 1))
    chart = s.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1), Inches(8), Inches(5), data
    ).chart
    chart.plots[0].has_data_labels = True
    chart.plots[0].data_labels.collision_strategy = "compact"
    return _saved(prs)


def _deck_diagrams() -> bytes:
    from power_pptx.diagrams import cycle, decision_tree, horizontal_pipeline
    from power_pptx.geometry import BBox

    prs = Presentation()
    s = _blank_slide(prs)
    horizontal_pipeline(s, BBox.from_inches(0.5, 0.5, 9, 1.5), steps=["A", "B", "C"])
    cycle(s, BBox.from_inches(3, 2.5, 4, 4), steps=["Ingest", "Model", "Serve"])
    decision_tree(
        s,
        BBox.from_inches(0.5, 5.2, 9, 2),
        root="Q?",
        branches=[{"label": "Yes", "children": ["Go"]}, "No"],
    )
    return _saved(prs)


def _deck_group_fill() -> bytes:
    # A group with a solid fill exercises EG_FillProperties on `p:grpSpPr`,
    # which the schema permits but `a:ln` (line) on a group does not.
    from power_pptx.dml.color import RGBColor
    from power_pptx.enum.shapes import MSO_SHAPE

    prs = Presentation()
    s = _blank_slide(prs)
    group = s.shapes.add_group_shape()
    group.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1))
    group.shapes.add_shape(MSO_SHAPE.OVAL, Inches(4), Inches(2), Inches(1), Inches(1))
    group.fill.solid()
    group.fill.fore_color.rgb = RGBColor(0x1F, 0x4E, 0x79)
    return _saved(prs)


def _deck_run_properties() -> bytes:
    # Exercises the cap / spc / strike / baseline attributes on a:rPr.
    prs = Presentation()
    s = _blank_slide(prs)
    tb = s.shapes.add_textbox(Inches(1), Inches(1), Inches(7), Inches(1))
    p = tb.text_frame.paragraphs[0]
    eyebrow = p.add_run()
    eyebrow.text = "SECTION"
    eyebrow.font.all_caps = True
    eyebrow.font.letter_spacing = Pt(2)
    struck = p.add_run()
    struck.text = "was-99"
    struck.font.strikethrough = True
    sup = p.add_run()
    sup.text = "2"
    sup.font.superscript = True
    sub = p.add_run()
    sub.text = "x"
    sub.font.subscript = True
    small = p.add_run()
    small.text = "Small Caps"
    small.font.small_caps = True
    return _saved(prs)


def _deck_ergonomics() -> bytes:
    """Shadow suppression, point-valued corner radius, and cell formatting."""
    from power_pptx.enum.shapes import MSO_SHAPE

    prs = Presentation()
    s = _blank_slide(prs)

    card = s.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1), Inches(1), Inches(4), Inches(2)
    )
    card.corner_radius = Pt(6)
    card.shadow.clear()  # empty <a:effectLst/> + <a:effectRef idx="0"/>

    glowing = s.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6), Inches(1), Inches(3), Inches(2)
    )
    glowing.glow.radius = Pt(6)
    glowing.shadow.clear()  # a surviving sibling effect must stay schema-valid

    # A shape whose effects are an <a:effectDag>: clearing must prune the
    # shadow nodes rather than add a sibling <a:effectLst>, which would put two
    # arms of the EG_EffectProperties choice in one <a:spPr>.
    from power_pptx.oxml import parse_xml
    from power_pptx.oxml.ns import nsdecls

    dagged = s.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1), Inches(3.4), Inches(3), Inches(1.2)
    )
    dagged._element.spPr.append(
        parse_xml(
            '<a:effectDag %s name="dag"><a:cont>'
            '<a:outerShdw blurRad="50800"><a:srgbClr val="000000"/></a:outerShdw>'
            '<a:glow rad="50800"><a:srgbClr val="4F9DFF"/></a:glow>'
            "</a:cont></a:effectDag>" % nsdecls("a")
        )
    )
    dagged.shadow.clear()

    table = s.shapes.add_table(3, 3, Inches(1), Inches(4), Inches(8), Inches(2)).table
    for r in range(3):
        for c in range(3):
            table.cell(r, c).text = "r%dc%d" % (r, c)
    table.format_cells(rows=0, fill="#1F2937", color="#FFFFFF", bold=True, anchor="middle")
    # style-then-populate: writes <a:lstStyle>/<a:lvl1pPr> text-body defaults
    empty = s.shapes.add_table(1, 2, Inches(1), Inches(6.2), Inches(4), Inches(0.6)).table
    empty.format_cells(color="#111111", bold=True, size_pt=11, align="center")
    empty.cell(0, 0).text = "styled first"
    table.format_cells(rows=slice(1, None), size_pt=11, align="right", margin=(2, 8, 2, 8))
    table.cell(2, 0).format(fill="none")
    return _saved(prs)


def _deck_lint_relationship_model() -> bytes:
    """Lint intent markers: group, skip, pairwise allowance, and layer hints.

    All of it lives in a ``cNvPr/extLst/ext`` extension rather than as custom
    attributes on ``cNvPr`` precisely so the deck stays schema-valid — a
    custom-namespaced attribute there is what triggers PowerPoint's
    "repaired and removed" prompt.
    """
    from power_pptx.enum.shapes import MSO_SHAPE

    prs = Presentation()
    s = _blank_slide(prs)

    card = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(4), Inches(2))
    badge = s.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(4), Inches(0.6), Inches(1.5), Inches(0.8)
    )
    # <pp:lintLayer name=.../> and <pp:lintLayer above=.../>
    card.layer = "card"
    badge.layer_above = "card"
    # <pp:lintAllow ids="..."/>, incl. the multi-id comma-joined form
    accent = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(2.8), Inches(4), Inches(0.3))
    badge.allow_overlap_with(card, accent)
    # ...alongside the pre-existing markers, in one shared <a:ext>
    card.lint_group = "kpi-card-1"
    card.lint_skip = {"MinFontSize"}
    card.allow_overlap_with(badge)

    # A shape carrying only a layer declaration, and one whose markers were
    # set and then cleared (the <a:extLst> must be pruned, not left empty).
    lone = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6), Inches(4), Inches(2), Inches(1))
    lone.layer = "panel"
    cleared = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6), Inches(5.2), Inches(2), Inches(1))
    cleared.layer = "panel"
    cleared.allow_overlap_with(lone)
    cleared.layer = None
    cleared.overlap_allowances = ()

    # A textbox and a table cell body carry cNvPr too — exercise a non-autoshape.
    box = s.shapes.add_textbox(Inches(0.5), Inches(4.5), Inches(3), Inches(1))
    box.text_frame.text = "declared"
    box.layer_above = "panel"
    box.allow_overlap_with(card)

    return _saved(prs)


def _deck_svg_embedding() -> bytes:
    from PIL import Image

    prs = Presentation()
    fallback = io.BytesIO()
    Image.new("RGB", (200, 100), "#214b44").save(fallback, format="PNG")
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">'
           '<rect width="200" height="100" fill="#214b44"/></svg>')
    for _ in range(2):
        slide = _blank_slide(prs)
        slide.shapes.add_svg_picture(svg, Inches(1), Inches(1), Inches(4), Inches(2),
                                     png_fallback=fallback.getvalue())
    return _saved(prs)


def _deck_native_typography() -> bytes:
    from pathlib import Path

    from power_pptx import BBox
    from power_pptx.design import Column, DataTable, TextBlock

    font = str(Path(__file__).parents[1] / "fonts" / "Tektur-Medium.ttf")
    prs = Presentation()
    s = _blank_slide(prs)
    Column(
        [
            TextBlock(
                "Active customers",
                font="Tektur",
                font_file=font,
                weight="medium",
                letter_spacing=Pt(1.4),
                case="upper",
                size_pt=9,
                min_size_pt=9,
            ),
            DataTable(
                [["Region", "Revenue"], ["EMEA", "A long note that will be cut"]],
                max_lines=1,
                truncate=True,
            ),
        ],
        fill_last=True,
    ).render(s, BBox(Inches(0.5), Inches(0.5), Inches(5), Inches(3)))
    return _saved(prs)


_DECK_BUILDERS = {
    "native_typography": _deck_native_typography,
    "svg_embedding": _deck_svg_embedding,
    "blank": _deck_blank,
    "group_fill": _deck_group_fill,
    "run_properties": _deck_run_properties,
    "effects_and_3d": _deck_effects_and_3d,
    "3d_none_presets": _deck_3d_none_presets,
    "ole_objects": _deck_ole_objects,
    "embedded_font": _deck_embedded_font,
    "gradient": _deck_gradient,
    "table": _deck_table,
    "chart": _deck_chart,
    "label_collision_strategy": _deck_label_collision_strategy,
    "animations": _deck_animations,
    "animation_removal": _deck_animation_removal,
    "sections": _deck_sections,
    "morph_transition": _deck_morph_transition,
    "transition_duration": _deck_transition_duration,
    "chart_types": _deck_chart_types,
    "radar_chart": _deck_radar_chart,
    "soft_metal_material": _deck_soft_metal_material,
    "picture_washout": _deck_picture_washout,
    "recipes": _deck_recipes,
    "diagrams": _deck_diagrams,
    "ergonomics": _deck_ergonomics,
    "lint_relationship_model": _deck_lint_relationship_model,
}


class DescribeGeneratedDeckSchemaValidity:
    @pytest.mark.parametrize("name", sorted(_DECK_BUILDERS))
    def it_validates_against_the_ooxml_schema(self, name):
        assert_schema_valid(_DECK_BUILDERS[name]())

    def it_keeps_lint_extension_markers_in_the_validated_deck(self):
        # Guard against the schema test passing vacuously: the deck it
        # validates must actually carry the new <pp:lintAllow>/<pp:lintLayer>
        # elements (and their siblings) in the slide XML.
        import zipfile

        blob = _deck_lint_relationship_model()
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            xml = zf.read("ppt/slides/slide1.xml").decode("utf-8")
        for tag in ("lintAllow", "lintLayer", "lintGroup", "lintSkip"):
            assert tag in xml, tag
        assert 'ids="' in xml
        assert 'above="card"' in xml
        # ...and no custom-namespaced attribute snuck onto <p:cNvPr> itself.
        assert "lintGroup=" not in xml

    def it_validates_a_slide_imported_with_an_image(self):
        # import_slide must keep r:embed references pointing at the image, and
        # the copied parts must stay schema-valid.
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000d49444154789c6360000002000100ffff03000006000557bfabd4000000"
            "0049454e44ae426082"
        )
        src = Presentation()
        ss = src.slides.add_slide(src.slide_layouts[6])
        ss.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
        ss.shapes.add_picture(io.BytesIO(png), Inches(3), Inches(3), Inches(1), Inches(1))

        dst = Presentation()
        dst.import_slide(src.slides[0])
        assert_schema_valid(_saved(dst))

    def it_validates_an_imported_slide_that_linked_to_another_slide(self):
        # A slide-jump link is re-pointed when its target is in the
        # destination and removed otherwise; neither outcome may leave a
        # dangling r:id or an unregistered (orphan) slide part behind.
        src = Presentation()
        a = _blank_slide(src)
        b = _blank_slide(src)
        button = a.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
        button.text_frame.text = "next"
        button.click_action.target_slide = b

        link_dropped = Presentation()
        link_dropped.import_slide(a)
        assert_schema_valid(_saved(link_dropped))

        link_kept = Presentation()
        link_kept.import_slide(b)
        link_kept.import_slide(a)
        assert_schema_valid(_saved(link_kept))

        same_deck = Presentation(io.BytesIO(_saved(src)))
        same_deck.import_slide(same_deck.slides[0])
        assert_schema_valid(_saved(same_deck))

    def it_validates_a_deck_after_apply_template(self):
        # apply_template must leave every p:sldLayoutId pointing at a layout
        # (not the theme) and every master/layout picture reference resolved.
        from copy import deepcopy

        from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT

        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000d49444154789c6360000002000100ffff03000006000557bfabd4000000"
            "0049454e44ae426082"
        )

        def add_picture_to(owner, prs):
            scratch = prs.slides.add_slide(prs.slide_layouts[6])
            pic = scratch.shapes.add_picture(io.BytesIO(png), 0, 0, Inches(1), Inches(1))
            image_part = scratch.part.related_part(pic._element.blip_rId)
            pic_el = deepcopy(pic._element)
            pic_el.blipFill.blip.rEmbed = owner.part.relate_to(image_part, RT.IMAGE)
            pic_el.nvPicPr.cNvPr.id = 1 + max(
                int(v) for v in owner._element.xpath("//p:cNvPr/@id")
            )
            owner.shapes._spTree.append(pic_el)
            sldIdLst = prs.slides._sldIdLst
            prs.part.drop_rel(sldIdLst[-1].rId)
            sldIdLst.remove(sldIdLst[-1])

        plain_template = io.BytesIO(_saved(Presentation()))
        branded = Presentation()
        add_picture_to(branded.slide_master, branded)
        add_picture_to(branded.slide_layouts[1], branded)
        branded_template = io.BytesIO(_saved(branded))
        assert_schema_valid(branded_template.getvalue())

        for template in (plain_template, branded_template):
            deck = Presentation()
            deck.slides.add_slide(deck.slide_layouts[1]).shapes.title.text = "hello"
            deck.apply_template(template)
            assert_schema_valid(_saved(deck))
            # ...and still valid after carrying on authoring, and a reopen.
            deck.slides.add_slide(deck.slide_layouts[5])
            reopened = Presentation(io.BytesIO(_saved(deck)))
            reopened.slides.add_slide(reopened.slide_layouts[0])
            assert_schema_valid(_saved(reopened))

    def it_reports_violations_as_part_message_pairs(self):
        # The validator's own contract: a clean deck yields no violations.
        assert list(iter_schema_violations(_deck_blank())) == []

    def it_actually_detects_an_invalid_part(self):
        # Self-test: inject a known-bad element (an empty <a:scene3d/>, which
        # is exactly the bug class this harness guards) bypassing the API, and
        # confirm the validator flags it — so the harness can't silently
        # regress into always-passing.
        from lxml import etree

        from power_pptx.enum.shapes import MSO_SHAPE
        from power_pptx.oxml.ns import qn

        prs = Presentation()
        s = _blank_slide(prs)
        sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(2))
        etree.SubElement(sh._element.spPr, qn("a:scene3d"))  # empty -> invalid

        violations = list(iter_schema_violations(_saved(prs)))
        assert any("scene3d" in msg for _, msg in violations), violations

    def it_detects_an_out_of_range_axis_id(self):
        # Self-test for the PowerPoint signed-int32 axis-id rule: inject an axId
        # above 2**31 (valid per XSD unsignedInt, but PowerPoint repairs it) and
        # confirm the validator flags it.
        import io as _io

        from power_pptx.chart.data import CategoryChartData
        from power_pptx.enum.chart import XL_CHART_TYPE

        prs = Presentation()
        s = _blank_slide(prs)
        data = CategoryChartData()
        data.categories = ["A", "B"]
        data.add_series("S", (1, 2))
        chart = s.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1), Inches(6), Inches(4), data
        ).chart
        # Corrupt one axis id into the >2**31 range, bypassing the writer.
        ax = chart._chartSpace.xpath(".//c:axId")[0]
        ax.set("val", str(2**31 + 5))

        buf = _io.BytesIO()
        prs.save(buf)
        violations = list(iter_schema_violations(buf.getvalue()))
        assert any("axis-id range" in msg for _, msg in violations), violations

    def it_gives_each_ole_object_a_unique_icon_pic_id(self):
        # The inner show-as-icon <p:pic> of each OLE object must carry a unique,
        # non-zero shape id — two objects sharing id="0" is a repair trigger.
        import zipfile

        from lxml import etree

        data = _deck_ole_objects()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            doc = etree.fromstring(zf.read("ppt/slides/slide1.xml"))
        ids = [
            el.get("id")
            for el in doc.iter()
            if etree.QName(el).localname == "cNvPr"
        ]
        assert "0" not in ids, ids
        assert len(ids) == len(set(ids)), "duplicate shape ids: %s" % ids

    def it_detects_a_duplicate_shape_id(self):
        # Self-test for the duplicate-shape-id rule: force two shapes on one
        # slide to share a cNvPr id (valid per XSD unsignedInt, but a PowerPoint
        # repair trigger) and confirm the validator flags it.
        from power_pptx.enum.shapes import MSO_SHAPE

        prs = Presentation()
        s = _blank_slide(prs)
        a = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1))
        b = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(4), Inches(1), Inches(2), Inches(1))
        # Collide b's id onto a's, bypassing the id allocator.
        b._element.nvSpPr.cNvPr.set("id", str(a.shape_id))

        violations = list(iter_schema_violations(_saved(prs)))
        assert any("duplicate shape id" in msg for _, msg in violations), violations

    def it_detects_a_dangling_relationship_reference(self):
        # Self-test for the relationship rule: point a picture's r:embed at a
        # relationship id that does not exist and confirm the validator flags it.
        import io as _io
        import zipfile

        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000d49444154789c6360000002000100ffff03000006000557bfabd4000000"
            "0049454e44ae426082"
        )
        prs = Presentation()
        s = _blank_slide(prs)
        s.shapes.add_picture(_io.BytesIO(png), Inches(1), Inches(1), Inches(2), Inches(2))
        original = _saved(prs)

        # Rewrite slide1.xml so the blip r:embed references a bogus rId.
        buf = _io.BytesIO()
        with zipfile.ZipFile(_io.BytesIO(original)) as zin:
            slide_xml = zin.read("ppt/slides/slide1.xml").replace(b'r:embed="rId', b'r:embed="rIdX')
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    is_slide = item.filename == "ppt/slides/slide1.xml"
                    zout.writestr(item, slide_xml if is_slide else zin.read(item.filename))

        violations = list(iter_schema_violations(buf.getvalue()))
        assert any("dangling" in msg for _, msg in violations), violations

    def it_detects_a_missing_target_in_the_package_root_rels(self):
        # Self-test for the package-root ``_rels/.rels`` case: drop the
        # ``docProps/core.xml`` part its core-properties relationship points at
        # (nothing else references it), so the root rels now targets a missing
        # part. A part-driven scan would skip the package root because the root
        # is not itself an XML part; the rels-driven pass must catch it.
        import io as _io
        import zipfile

        original = _deck_blank()
        buf = _io.BytesIO()
        with zipfile.ZipFile(_io.BytesIO(original)) as zin:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename == "docProps/core.xml":
                        continue  # drop the part the root rels points at
                    zout.writestr(item, zin.read(item.filename))

        violations = list(iter_schema_violations(buf.getvalue()))
        assert any(
            part == "_rels/.rels" and "docProps/core.xml" in msg
            for part, msg in violations
        ), violations

    def it_detects_a_duplicate_zip_member_name(self):
        # Self-test for the OPC unique-partname rule: write two different
        # payloads under one member name (zipfile permits it silently; the
        # PowerPoint package reader does not) and confirm the validator
        # flags it.
        import io as _io
        import warnings
        import zipfile

        original = _deck_blank()
        buf = _io.BytesIO()
        with zipfile.ZipFile(_io.BytesIO(original)) as zin:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    zout.writestr(item, zin.read(item.filename))
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)  # zipfile dup warning
                    zout.writestr("ppt/slides/slide1.xml", b"<not-the-real-slide/>")

        violations = list(iter_schema_violations(buf.getvalue()))
        assert any(
            part == "ppt/slides/slide1.xml" and "more than once" in msg
            for part, msg in violations
        ), violations

    def it_detects_an_orphan_slide_part(self):
        # Self-test for the sldIdLst-coverage rule: add a slide part (with
        # valid rels and a content-type override) that no p:sldId references
        # and confirm the validator flags it.
        import io as _io
        import zipfile

        original = _deck_blank()
        buf = _io.BytesIO()
        with zipfile.ZipFile(_io.BytesIO(original)) as zin:
            ct = zin.read("[Content_Types].xml").replace(
                b"</Types>",
                b'<Override PartName="/ppt/slides/slide9.xml" ContentType='
                b'"application/vnd.openxmlformats-officedocument.presentationml.'
                b'slide+xml"/></Types>',
            )
            # Read up front: writestr(zinfo, ...) mutates the shared ZipInfo,
            # so members can't be re-read after they've been written out.
            slide_xml = zin.read("ppt/slides/slide1.xml")
            slide_rels = zin.read("ppt/slides/_rels/slide1.xml.rels")
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = ct if item.filename == "[Content_Types].xml" else zin.read(item.filename)
                    zout.writestr(item, data)
                zout.writestr("ppt/slides/slide9.xml", slide_xml)
                zout.writestr("ppt/slides/_rels/slide9.xml.rels", slide_rels)

        violations = list(iter_schema_violations(buf.getvalue()))
        assert any(
            part == "ppt/slides/slide9.xml" and "not referenced by any p:sldId" in msg
            for part, msg in violations
        ), violations

    def it_detects_a_part_missing_from_content_types(self):
        # Self-test for the content-types rule: add a part whose extension has
        # neither a Default nor an Override (the exact "PowerPoint can't type
        # this part" repair trigger) and confirm the validator flags it.
        import io as _io
        import zipfile

        original = _deck_blank()
        buf = _io.BytesIO()
        with zipfile.ZipFile(_io.BytesIO(original)) as zin:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    zout.writestr(item, zin.read(item.filename))
                # A part with a novel extension the content-types stream never declares.
                zout.writestr("ppt/media/orphan.xyz", b"not declared anywhere")

        violations = list(iter_schema_violations(buf.getvalue()))
        assert any(
            part == "ppt/media/orphan.xyz" and "not declared in [Content_Types].xml" in msg
            for part, msg in violations
        ), violations


def _rewritten(blob: bytes, edits) -> bytes:
    """Return package *blob* with ``edits[name](data)`` applied to the named members."""
    import zipfile

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(blob)) as zin, zipfile.ZipFile(
        out, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for name in zin.namelist():
            data = zin.read(name)
            zout.writestr(name, edits[name](data) if name in edits else data)
    return out.getvalue()


def _with_doctype(doctype: bytes):
    """Return an edit that puts *doctype* between a part's XML declaration and its root."""

    def edit(data: bytes) -> bytes:
        declaration, root = data.split(b"?>", 1)
        return declaration + b"?>" + doctype + root

    return edit


_REL_TYPES = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"


def _rel_ids(blob: bytes, rels_name: str, rel_type: str) -> "list[str]":
    """Return the ids of the *rel_type* relationships (``"theme"``, …) in *rels_name*."""
    import zipfile

    from lxml import etree

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        rels = etree.fromstring(zf.read(rels_name))
    return [rel.get("Id") for rel in rels if rel.get("Type") == _REL_TYPES + rel_type]


class DescribeIdListReferences:
    """An id-list entry must name a relationship of its own kind.

    The XML here is edited by hand: the checks must hold whatever produced
    the package, and must not depend on the code that used to produce it.
    """

    MASTER = "ppt/slideMasters/slideMaster1.xml"
    MASTER_RELS = "ppt/slideMasters/_rels/slideMaster1.xml.rels"
    PRESENTATION_RELS = "ppt/_rels/presentation.xml.rels"

    def it_detects_a_layout_id_that_resolves_to_the_theme(self):
        # -- what a master is left with when its relationship ids shift by one --
        original = _deck_blank()
        (theme_rid,) = _rel_ids(original, self.MASTER_RELS, "theme")
        layout_rid = _rel_ids(original, self.MASTER_RELS, "slideLayout")[0]

        def edit(data: bytes) -> bytes:
            old = b'r:id="%s"/>' % layout_rid.encode()
            assert data.count(old) == 1
            return data.replace(old, b'r:id="%s"/>' % theme_rid.encode())

        violations = list(iter_schema_violations(_rewritten(original, {self.MASTER: edit})))

        assert violations == [
            (
                self.MASTER,
                "<sldLayoutId> r:id=%r resolves to a relationship of type 'theme', not "
                "'slideLayout' — PowerPoint repairs an id list that points at the wrong "
                "kind of part" % theme_rid,
            )
        ]

    def it_detects_a_slide_id_that_resolves_to_a_master(self):
        original = _deck_blank()
        (slide_rid,) = _rel_ids(original, self.PRESENTATION_RELS, "slide")
        (master_rid,) = _rel_ids(original, self.PRESENTATION_RELS, "slideMaster")

        def edit(data: bytes) -> bytes:
            old = b'<p:sldId id="256" r:id="%s"/>' % slide_rid.encode()
            assert data.count(old) == 1
            return data.replace(old, b'<p:sldId id="256" r:id="%s"/>' % master_rid.encode())

        violations = list(
            iter_schema_violations(_rewritten(original, {"ppt/presentation.xml": edit}))
        )

        assert (
            "ppt/presentation.xml",
            "<sldId> r:id=%r resolves to a relationship of type 'slideMaster', not 'slide' — "
            "PowerPoint repairs an id list that points at the wrong kind of part" % master_rid,
        ) in violations

    def it_leaves_a_missing_relationship_to_the_dangling_reference_check(self):
        original = _deck_blank()
        layout_rid = _rel_ids(original, self.MASTER_RELS, "slideLayout")[0]

        def edit(data: bytes) -> bytes:
            old = b'r:id="%s"/>' % layout_rid.encode()
            assert data.count(old) == 1
            return data.replace(old, b'r:id="rId999"/>')

        violations = list(iter_schema_violations(_rewritten(original, {self.MASTER: edit})))

        # -- one finding for one defect: there is no relationship to have a type --
        assert len(violations) == 1
        assert "dangling id='rId999' on <sldLayoutId>" in violations[0][1]

    def but_it_accepts_the_strict_relationship_namespace(self):
        # -- ISO "strict" packages spell relationship types under purl.oclc.org --
        strict = b"http://purl.oclc.org/ooxml/officeDocument/relationships/"

        def edit(data: bytes) -> bytes:
            assert _REL_TYPES.encode() in data
            return data.replace(_REL_TYPES.encode(), strict)

        blob = _rewritten(
            _deck_blank(), {self.MASTER_RELS: edit, self.PRESENTATION_RELS: edit}
        )

        assert list(iter_schema_violations(blob)) == []


#: A hand-written "Appear" entrance, as PowerPoint writes it, for the shape
#: ``{target}``, with a paragraph build for the shape ``{build}``.
_TIMING = """\
<p:timing><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">\
<p:childTnLst><p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" \
nodeType="mainSeq"><p:childTnLst><p:par><p:cTn id="3" fill="hold"><p:stCondLst>\
<p:cond delay="indefinite"/></p:stCondLst><p:childTnLst><p:par><p:cTn id="4" fill="hold">\
<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst><p:par><p:cTn id="5" presetID="1" \
presetClass="entr" presetSubtype="0" fill="hold" grpId="0" nodeType="clickEffect"><p:stCondLst>\
<p:cond delay="0"/></p:stCondLst><p:childTnLst><p:set><p:cBhvr><p:cTn id="6" dur="1" fill="hold">\
<p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn><p:tgtEl><p:spTgt spid="{target}"/>\
</p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr>\
<p:to><p:strVal val="visible"/></p:to></p:set><p:animEffect transition="in" filter="fade">\
<p:cBhvr><p:cTn id="7" dur="500"/><p:tgtEl><p:spTgt spid="{target}"/></p:tgtEl></p:cBhvr>\
</p:animEffect></p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par></p:childTnLst>\
</p:cTn></p:par></p:childTnLst></p:cTn><p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl>\
<p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst><p:nextCondLst><p:cond evt="onNext" delay="0">\
<p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst></p:seq></p:childTnLst></p:cTn></p:par>\
</p:tnLst><p:bldLst><p:bldP spid="{build}" grpId="0"/></p:bldLst></p:timing>"""


class DescribeAnimationTargets:
    """An animation must target a shape that is on its slide.

    The timing XML is written by hand rather than through the animation API,
    so these hold whatever produced the package.
    """

    SLIDE = "ppt/slides/slide1.xml"

    def _deck(self, target, build):
        """Return a saved deck whose slide animates shape *target* and builds *build*.

        The slide holds a rectangle and, nested two groups deep, a diamond.
        Either argument is ``"rectangle"`` or ``"nested"``, standing for that
        shape's id, or else the id to write, as a string.
        """
        from power_pptx.enum.shapes import MSO_SHAPE

        prs = Presentation()
        slide = _blank_slide(prs)
        self.rectangle = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1)
        )
        outer = slide.shapes.add_group_shape()
        inner = outer.shapes.add_group_shape()
        self.nested = inner.shapes.add_shape(
            MSO_SHAPE.DIAMOND, Inches(4), Inches(1), Inches(1), Inches(1)
        )

        ids = {
            "rectangle": str(self.rectangle.shape_id),
            "nested": str(self.nested.shape_id),
        }
        timing = _TIMING.format(
            target=ids.get(target, target), build=ids.get(build, build)
        ).encode()

        def edit(data: bytes) -> bytes:
            assert data.count(b"</p:sld>") == 1
            assert b"<p:timing" not in data
            return data.replace(b"</p:sld>", timing + b"</p:sld>")

        return _rewritten(_saved(prs), {self.SLIDE: edit})

    def it_accepts_targets_that_are_on_the_slide(self):
        assert list(iter_schema_violations(self._deck("rectangle", "rectangle"))) == []

    def it_counts_shapes_nested_in_groups(self):
        assert list(iter_schema_violations(self._deck("nested", "nested"))) == []

    def it_compares_ids_as_numbers(self):
        blob = self._deck("rectangle", "rectangle")
        rectangle_id = str(self.rectangle.shape_id).encode()

        def edit(data: bytes) -> bytes:
            old = b'<p:spTgt spid="%s"/>' % rectangle_id
            assert old in data
            return data.replace(old, b'<p:spTgt spid="0%s"/>' % rectangle_id)

        assert list(iter_schema_violations(_rewritten(blob, {self.SLIDE: edit}))) == []

    def it_detects_an_animation_target_that_is_not_on_the_slide(self):
        violations = list(iter_schema_violations(self._deck("999", "rectangle")))

        # -- reported once, though two behaviours of the effect name the shape --
        assert violations == [
            (
                self.SLIDE,
                "p:spTgt spid=999 names no shape on this slide — PowerPoint repairs an "
                "animation whose target shape is missing",
            )
        ]

    def it_detects_a_build_entry_whose_shape_is_not_on_the_slide(self):
        violations = list(iter_schema_violations(self._deck("nested", "4242")))

        assert violations == [
            (
                self.SLIDE,
                "p:bldP spid=4242 names no shape on this slide — PowerPoint repairs an "
                "animation whose target shape is missing",
            )
        ]

    def it_checks_only_slides_that_have_a_timeline(self):
        # -- no p:timing, nothing to resolve: the common case costs nothing --
        assert list(iter_schema_violations(_deck_blank())) == []


class DescribeUntrustedPackages:
    """The validator reads a package from anywhere without resolving entities."""

    def it_reports_a_part_that_declares_a_dtd(self):
        blob = _rewritten(
            _deck_blank(),
            {
                "ppt/slides/slide1.xml": _with_doctype(b"<!DOCTYPE sld>"),
                "ppt/slides/_rels/slide1.xml.rels": _with_doctype(b"<!DOCTYPE Relationships>"),
            },
        )

        violations = list(iter_schema_violations(blob))

        assert sorted(part for part, msg in violations if "declares a DTD" in msg) == [
            "ppt/slides/_rels/slide1.xml.rels",
            "ppt/slides/slide1.xml",
        ]

    def it_does_not_expand_an_entity_into_the_part_it_validates(self, tmp_path):
        secret = tmp_path / "secret.txt"
        secret.write_text("TOP-SECRET-MARKER")
        doctype = (
            b'<!DOCTYPE sld [<!ENTITY file SYSTEM "' + secret.as_uri().encode() + b'">'
            b'<!ENTITY text "INTERNAL-ENTITY-TEXT">]>'
        )

        def edit(data: bytes) -> bytes:
            # -- character content is not allowed in p:spTree, so an expanded
            # -- entity would surface in a schema error --
            assert b"<p:spTree>" in data
            return _with_doctype(doctype)(data).replace(b"<p:spTree>", b"<p:spTree>&text;&file;")

        blob = _rewritten(_deck_blank(), {"ppt/slides/slide1.xml": edit})

        violations = list(iter_schema_violations(blob))

        messages = [msg for part, msg in violations if part == "ppt/slides/slide1.xml"]
        assert any("declares a DTD" in msg for msg in messages), violations
        # -- the entities stayed references: the part could not be validated,
        # -- rather than being validated with their text in place --
        assert any("could not be validated" in msg for msg in messages), violations
        assert not any("TOP-SECRET-MARKER" in msg for _, msg in violations)
        assert not any("Character content" in msg for _, msg in violations)

    def it_does_not_mistake_quoted_doctype_text_for_a_dtd(self):
        def edit(data: bytes) -> bytes:
            return data.replace(b"<p:spTree>", b"<p:spTree><!-- <!DOCTYPE x> -->")

        blob = _rewritten(_deck_blank(), {"ppt/slides/slide1.xml": edit})

        assert list(iter_schema_violations(blob)) == []

    def it_accepts_comments_and_processing_instructions_in_a_part(self):
        # -- valid XML that other producers write; these nodes have no QName,
        # -- which used to stop the validator with a ValueError --
        def edit(data: bytes) -> bytes:
            return data.replace(b"<p:spTree>", b"<p:spTree><!-- a comment --><?producer note?>")

        blob = _rewritten(
            _deck_blank(),
            {"ppt/slides/slide1.xml": edit, "ppt/slideMasters/slideMaster1.xml": edit},
        )

        assert list(iter_schema_violations(blob)) == []

    def it_reads_every_part_with_the_one_hardened_parser(self):
        from unittest.mock import patch

        from lxml import etree

        from power_pptx import _schema

        blob = _deck_chart()
        parsers = []
        real_fromstring = etree.fromstring

        def recording_fromstring(text, parser=None, **kwargs):
            parsers.append(parser)
            return real_fromstring(text, parser, **kwargs)

        with patch.object(_schema.etree, "fromstring", recording_fromstring):
            assert list(iter_schema_violations(blob)) == []

        assert parsers, "expected the validator to parse parts"
        assert all(parser is _schema._PARSER for parser in parsers)
