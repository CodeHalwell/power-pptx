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
    # Regression: recolor "washout" must write the required <a:biLevel thresh="…">.
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6360000002000100ffff03000006000557bfabd4000000"
        "0049454e44ae426082"
    )
    prs = Presentation()
    s = _blank_slide(prs)
    pic = s.shapes.add_picture(io.BytesIO(png), Inches(1), Inches(1), Inches(2), Inches(2))
    pic.effects.recolor = "washout"
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


_DECK_BUILDERS = {
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
}


class DescribeGeneratedDeckSchemaValidity:
    @pytest.mark.parametrize("name", sorted(_DECK_BUILDERS))
    def it_validates_against_the_ooxml_schema(self, name):
        assert_schema_valid(_DECK_BUILDERS[name]())

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
