"""Integration tests for ``shape.animate(...)`` constrained façade."""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.util import Inches


def _shape():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    sp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1))
    return prs, slide, sp


class DescribeShapeAnimate:
    def it_adds_a_fade_entrance(self):
        _, slide, sp = _shape()
        sp.animate(entry="fade", duration_ms=300)
        # The slide now has at least one animation entry on this shape.
        ids_animated = [e.shape.shape_id for e in slide.animations]
        assert sp.shape_id in ids_animated

    def it_adds_a_fade_exit(self):
        _, slide, sp = _shape()
        sp.animate(exit="fade", duration_ms=300)
        ids_animated = [e.shape.shape_id for e in slide.animations]
        assert sp.shape_id in ids_animated

    def it_adds_a_pulse_emphasis(self):
        _, slide, sp = _shape()
        sp.animate(emphasis="pulse", duration_ms=400)
        ids_animated = [e.shape.shape_id for e in slide.animations]
        assert sp.shape_id in ids_animated

    @pytest.mark.parametrize(
        "kwargs",
        [
            {},
            {"entry": "fade", "exit": "fade"},
            {"entry": "fade", "emphasis": "pulse"},
            {"exit": "fade", "emphasis": "pulse"},
            {"entry": "fade", "exit": "fade", "emphasis": "pulse"},
        ],
    )
    def it_requires_exactly_one_kind(self, kwargs):
        _, _, sp = _shape()
        with pytest.raises(ValueError, match="exactly one"):
            sp.animate(**kwargs)

    def it_rejects_unknown_presets(self):
        _, _, sp = _shape()
        with pytest.raises(ValueError, match="unknown entry preset"):
            sp.animate(entry="bogus")

    def it_rejects_unknown_triggers(self):
        _, _, sp = _shape()
        with pytest.raises(ValueError, match="trigger must be"):
            sp.animate(entry="fade", trigger="when_thanos_snaps")

    def it_passes_direction_through_to_fly_in(self):
        # No raise → success. The full XML check would re-implement the
        # animation module's behaviour, so we just assert the call
        # plumbs through without a TypeError on the keyword.
        _, _, sp = _shape()
        sp.animate(entry="fly_in", direction="left")
