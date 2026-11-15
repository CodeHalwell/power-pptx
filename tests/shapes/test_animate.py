"""Integration tests for ``shape.animate(...)`` constrained façade."""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.util import Inches


def _shape():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    sp = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1)
    )
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

    @pytest.mark.parametrize(
        ("kind", "preset"),
        [
            ("entry", "appear"),
            ("entry", "fade"),
            ("entry", "fly_in"),
            ("entry", "float_in"),
            ("entry", "wipe"),
            ("entry", "zoom"),
            ("entry", "wheel"),
            ("entry", "random_bars"),
            ("exit", "disappear"),
            ("exit", "fade"),
            ("exit", "fly_out"),
            ("exit", "float_out"),
            ("exit", "wipe"),
            ("exit", "zoom"),
            # -- documented, but there was no Exit.wheel / Exit.random_bars --
            ("exit", "wheel"),
            ("exit", "random_bars"),
            ("emphasis", "pulse"),
            ("emphasis", "spin"),
            ("emphasis", "teeter"),
        ],
    )
    def it_supports_every_documented_preset(self, kind, preset):
        _, slide, sp = _shape()

        sp.animate(**{kind: preset})

        (entry,) = slide.animations
        expected_kind = {"entry": "entrance", "exit": "exit", "emphasis": "emphasis"}[kind]
        assert (entry.kind, entry.preset, entry.shape_id) == (expected_kind, preset, sp.shape_id)

    @pytest.mark.parametrize(
        ("kind", "preset", "direction", "subtype"),
        [
            ("entry", "fly_in", "left", "8"),
            ("entry", "wipe", "right", "2"),
            ("entry", "wipe", "top", "1"),
            ("exit", "fly_out", "top", "1"),
            ("exit", "wipe", "bottom", "4"),
        ],
    )
    def it_applies_the_direction_it_documents(self, kind, preset, direction, subtype):
        from power_pptx.oxml.ns import qn

        _, slide, sp = _shape()

        sp.animate(**{kind: preset}, direction=direction)

        (ctn,) = [c for c in slide._element.iter(qn("p:cTn")) if c.get("presetClass")]
        assert ctn.get("presetSubtype") == subtype

    def it_rejects_a_direction_a_preset_cannot_take(self):
        _, slide, sp = _shape()

        with pytest.raises(ValueError, match="direction"):
            sp.animate(entry="wipe", direction="diagonal")

        assert len(slide.animations) == 0

    @pytest.mark.parametrize("name", ["mro", "__class__", "__init__", "_milliseconds"])
    def it_rejects_names_that_are_not_presets(self, name):
        # The preset used to be looked up as an attribute of the Entrance
        # class, so these reached it and failed with an unrelated TypeError.
        _, _, sp = _shape()

        with pytest.raises(ValueError, match="unknown entry preset"):
            sp.animate(entry=name)
