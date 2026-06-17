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


_DECK_BUILDERS = {
    "blank": _deck_blank,
    "effects_and_3d": _deck_effects_and_3d,
    "gradient": _deck_gradient,
    "table": _deck_table,
    "chart": _deck_chart,
    "animations": _deck_animations,
    "morph_transition": _deck_morph_transition,
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
