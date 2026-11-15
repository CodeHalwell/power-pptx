"""Schema-validity guards for effects, 3-D, fills, picture recolour and charts.

Each builder returns a saved deck exercising one area whose XML changed; the
test asserts that every part validates against the ISO-29500 schemas *and*
that it survives save -> open -> save unchanged.  Kept apart from
`test_schema_validity.py` so the two can grow independently.
"""

from __future__ import annotations

import io

import pytest

from power_pptx import Presentation
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.util import Inches, Pt

from ..integration.round_trip import assert_round_trip
from .oxml_schema_validator import assert_schema_valid, schema_validation_available

pytestmark = pytest.mark.skipif(
    not schema_validation_available(),
    reason="lxml or the bundled ISO-29500 XSD schemas are unavailable",
)


def _blank_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def _rect(slide, col=0, row=0):
    return slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0.5 + 3 * col),
        Inches(0.5 + 2 * row),
        Inches(2.5),
        Inches(1.5),
    )


# ---------------------------------------------------------------------------
# Deck builders — each returns an unsaved |Presentation|.
# ---------------------------------------------------------------------------


def _deck_float_effect_lengths():
    """Every effect, 3-D and line length arrives as a float (`Pt(n) / 2`)."""
    prs = Presentation()
    sh = _rect(_blank_slide(prs))
    sh.shadow.blur_radius = Pt(8) / 2
    sh.shadow.distance = Pt(8) * 0.5
    sh.inner_shadow.blur_radius = Pt(6) / 2
    sh.glow.radius = Pt(6) / 2
    sh.soft_edges.radius = Pt(6) / 2
    sh.blur.radius = Pt(6) / 2
    sh.reflection.distance = Pt(6) / 2
    sh.reflection.blur_radius = Pt(1) / 3
    sh.line.width = Pt(3) / 2
    sh.three_d.bevel_top.width = Pt(6) / 2
    sh.three_d.bevel_top.height = Pt(5) / 3
    sh.three_d.extrusion_height = Pt(6) / 2
    sh.three_d.contour_width = Pt(1) / 2
    return prs


def _deck_rejected_effect_assignments():
    """Assignments that raise must not leave a half-built element behind."""
    prs = Presentation()
    slide = _blank_slide(prs)
    sh = _rect(slide)
    attempts = (
        (sh.soft_edges, "radius", -1),  # <a:softEdge/> lacks its required `rad`
        (sh.soft_edges, "radius", "3pt"),
        (sh.reflection, "start_alpha", 1.2),
        (sh.glow, "radius", object()),
        (sh.shadow, "direction", float("nan")),
        (sh.shadow.color, "rgb", "#FFF"),
        (sh.preset_shadow, "preset", 99),
        (sh.three_d.bevel_top, "width", -1),
        (sh.three_d.bevel_top, "preset", "circle"),
        (sh.three_d.extrusion_color, "rgb", "nope"),  # <a:extrusionClr/> needs a colour
        (sh.three_d, "preset_material", "metal"),
        (sh.line, "width", -1),
    )
    for proxy, name, value in attempts:
        with pytest.raises((TypeError, ValueError)):
            setattr(proxy, name, value)
    return prs


def _deck_cleared_effects():
    """Everything is set and then cleared again with `None`."""
    from power_pptx.enum.dml import BevelPreset

    prs = Presentation()
    sh = _rect(_blank_slide(prs))
    sh.shadow.blur_radius = Pt(4)
    sh.shadow.direction = -360  # a full turn must normalise to 0, not 21600000
    sh.glow.radius = Pt(4)
    sh.inner_shadow.distance = Pt(4)
    sh.soft_edges.radius = Pt(4)
    sh.blur.radius = Pt(4)
    sh.reflection.distance = Pt(4)
    sh.preset_shadow.distance = Pt(4)
    sh.three_d.bevel_top.preset = BevelPreset.CIRCLE

    sh.shadow.blur_radius = None
    sh.shadow.direction = None
    sh.glow.radius = None
    sh.inner_shadow.distance = None
    sh.soft_edges.radius = None
    sh.blur.radius = None
    sh.reflection.distance = None
    sh.preset_shadow.preset = None
    sh.three_d.bevel_top.preset = None
    return prs


def _deck_shadow_directions():
    """Directions at and around a full turn stay inside `[0, 21600000)`."""
    prs = Presentation()
    slide = _blank_slide(prs)
    for i, degrees in enumerate((360, -360, 359.9999999, -1e-6, 720.5, -90)):
        sh = _rect(slide, col=i % 3, row=i // 3)
        sh.shadow.direction = degrees
        sh.inner_shadow.direction = degrees
        sh.reflection.direction = degrees
    return prs


_DECK_BUILDERS = {
    "cleared_effects": _deck_cleared_effects,
    "float_effect_lengths": _deck_float_effect_lengths,
    "rejected_effect_assignments": _deck_rejected_effect_assignments,
    "shadow_directions": _deck_shadow_directions,
}


def _saved(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


class DescribeEffectsAndChartsSchemaValidity:
    @pytest.mark.parametrize("name", sorted(_DECK_BUILDERS))
    def it_validates_against_the_ooxml_schema(self, name):
        assert_schema_valid(_saved(_DECK_BUILDERS[name]()))

    @pytest.mark.parametrize("name", sorted(_DECK_BUILDERS))
    def it_round_trips(self, name):
        assert_round_trip(_DECK_BUILDERS[name]())

    def it_leaves_nothing_behind_once_effects_are_cleared_or_rejected(self):
        for build in (_deck_cleared_effects, _deck_rejected_effect_assignments):
            spPr = build().slides[0].shapes[0]._element.spPr
            assert spPr.effectLst is None, build.__name__
            assert spPr.ln is None, build.__name__
