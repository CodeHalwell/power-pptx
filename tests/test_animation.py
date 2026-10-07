"""Unit-test suite for high-level `power_pptx.animation` extensions.

Covers Phase 5 motion paths, the `sequence()` context manager, and
by-paragraph entrance animations.  The lower-level entrance/exit/
emphasis presets are exercised via the integration round-trip suite.
"""

from __future__ import annotations

import copy
import io

import pytest

from power_pptx import Presentation
from power_pptx.animation import Emphasis, Entrance, MotionPath, Trigger
from power_pptx.oxml.ns import qn
from power_pptx.util import Inches

from .unitutil.timing import (
    build_ids,
    cTn_ids,
    install_timing,
    powerpoint_timing_xml,
    target_ids,
)

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


@pytest.fixture
def slide_with_shape():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    shape = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
    return slide, shape


def _ctn_node_types(slide):
    return [
        c.get("nodeType") for c in slide._element.iter(qn("p:cTn")) if c.get("nodeType") is not None
    ]


def _animMotion_paths(slide):
    return [m.get("path") for m in slide._element.iter(qn("p:animMotion"))]


class DescribeSvgMotionPath:
    """`MotionPath.svg(...)` accepts SVG path syntax with a viewbox."""

    def it_converts_an_absolute_line_path(self, slide_with_shape):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        out = _svg_to_ooxml_motion_path("M 0 0 L 100 0", viewbox=(0, 0, 100, 100))
        assert out == "M 0 0 L 1 0 E"

    def it_converts_relative_commands(self):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        # m 5 5 → starts at (5,5); l 10 0 → moves to (15,5); l 0 10 → (15,15)
        out = _svg_to_ooxml_motion_path("m 5 5 l 10 0 l 0 10", viewbox=(0, 0, 100, 100))
        assert out == "M 0 0 L 0.1 0 L 0.1 0.1 E"

    def it_supports_h_v_z_shortcuts(self):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        out = _svg_to_ooxml_motion_path("M 0 0 H 100 V 100 Z")
        # Z → close back to subpath origin (the M anchor).
        assert out.startswith("M 0 0 L")
        assert out.endswith(" E")

    def it_supports_cubic_curve(self):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        out = _svg_to_ooxml_motion_path("M 0 0 C 0 -10 80 -10 80 0", viewbox=(0, 0, 100, 100))
        assert "C" in out
        assert out.endswith(" E")

    def it_emits_motion_path_via_class_method(self, slide_with_shape):
        from power_pptx.animation import MotionPath

        slide, shape = slide_with_shape
        MotionPath.svg(slide, shape, "M 0 0 L 100 0", viewbox=(0, 0, 100, 100))
        assert _animMotion_paths(slide) == ["M 0 0 L 1 0 E"]

    def it_rejects_an_empty_path(self):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        with pytest.raises(ValueError, match="non-empty"):
            _svg_to_ooxml_motion_path("")

    def it_rejects_a_command_before_moveto(self):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        with pytest.raises(ValueError, match="must start with M"):
            _svg_to_ooxml_motion_path("L 1 0")

    def it_rejects_unsupported_commands(self):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        with pytest.raises(ValueError, match="unsupported svg path command"):
            _svg_to_ooxml_motion_path("M 0 0 A 10 10 0 0 1 100 100")

    # -- malformed paths are rejected; none of them may loop ------------------------------

    @pytest.fixture
    def bounded(self, monkeypatch):
        """Turn a conversion that stops consuming its input into a failure, not a hang.

        Every coordinate the converter emits goes through ``_fmt``, and a loop that no longer
        advances through the tokens keeps calling it, so a call budget makes the endless loop
        fail the test promptly instead of wedging the run (and eating memory).
        """
        from power_pptx import animation

        real_fmt = animation._fmt
        calls = []

        def budgeted(value):
            calls.append(value)
            if len(calls) > 10_000:
                raise AssertionError("svg conversion loops without consuming its input")
            return real_fmt(value)

        monkeypatch.setattr(animation, "_fmt", budgeted)

    @pytest.mark.parametrize("path", ["M 0 0 L 1 1 Z 5 5", "M 0 0 L 1 1 z 5", "M 0 0 Z 1"])
    def it_rejects_a_number_after_closepath(self, bounded, path):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        with pytest.raises(ValueError, match="closepath"):
            _svg_to_ooxml_motion_path(path)

    def and_it_rejects_it_through_the_class_method_without_touching_the_slide(
        self, slide_with_shape, bounded
    ):
        slide, shape = slide_with_shape

        with pytest.raises(ValueError, match="closepath"):
            MotionPath.svg(slide, shape, "M 0 0 L 1 1 Z 5 5")

        assert slide._element.find(qn("p:timing")) is None

    @pytest.mark.parametrize("path", ["Z", "z", "Z M 0 0 L 1 1"])
    def it_rejects_a_closepath_before_moveto(self, bounded, path):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        with pytest.raises(ValueError, match="must start with M"):
            _svg_to_ooxml_motion_path(path)

    @pytest.mark.parametrize(
        "path",
        [
            "M",
            "M 1",
            "5 5",
            "M 0 0 L",
            "M 0 0 L 1",
            "M 0 0 L Z",
            "M 0 0 H",
            "M 0 0 V",
            "M 0 0 C 1 2 3 4 5",
            "M 0 0 Q 1 2 3",
            "M 0 0 L 1 1 Z 5 5 Z",
        ],
    )
    def it_rejects_truncated_or_malformed_paths(self, bounded, path):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        with pytest.raises(ValueError):
            _svg_to_ooxml_motion_path(path)

    @pytest.mark.parametrize(
        ("svg", "expected"),
        [
            # a command's coordinates may repeat without restating the command letter
            ("M 0 0 L 0.1 0.1 0.2 0.2", "M 0 0 L 0.1 0.1 L 0.2 0.2 E"),
            ("M 0 0 l 0.1 0 0 0.1", "M 0 0 L 0.1 0 L 0.1 0.1 E"),
            ("M 0 0 H 0.1 0.2", "M 0 0 L 0.1 0 L 0.2 0 E"),
            ("M 0 0 V 0.1 0.2", "M 0 0 L 0 0.1 L 0 0.2 E"),
            (
                "M 0 0 C 0 0.1 0.1 0.1 0.1 0 0.2 -0.1 0.3 -0.1 0.4 0",
                "M 0 0 C 0 0.1 0.1 0.1 0.1 0 C 0.2 -0.1 0.3 -0.1 0.4 0 E",
            ),
            ("M 0 0 Q 0.1 0.1 0.2 0 0.3 -0.1 0.4 0", "M 0 0 Q 0.1 0.1 0.2 0 Q 0.3 -0.1 0.4 0 E"),
            # extra coordinate pairs after a moveto are implicit linetos
            ("M 0 0 0.1 0.1 0.2 0", "M 0 0 L 0.1 0.1 L 0.2 0 E"),
            ("m 0 0 0.1 0.1 0.1 0", "M 0 0 L 0.1 0.1 L 0.2 0.1 E"),
            # a closepath may be followed by a new subpath
            (
                "M 0 0 L 0.1 0.1 Z M 0.5 0.5 L 0.6 0.6",
                "M 0 0 L 0.1 0.1 L 0 0 M 0.5 0.5 L 0.6 0.6 E",
            ),
        ],
    )
    def but_it_keeps_supporting_implicit_command_repetition(self, bounded, svg, expected):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        assert _svg_to_ooxml_motion_path(svg) == expected


class DescribeAnimationsAdd:
    """`SlideAnimations.add(kind, preset, shape)` polymorphic dispatcher."""

    def it_dispatches_entrance(self, slide_with_shape):
        slide, shape = slide_with_shape
        slide.animations.add("entrance", "fade", shape)
        # Entrance presets emit a presetClass="entr" cTn somewhere in the tree.
        classes = [
            c.get("presetClass")
            for c in slide._element.iter(qn("p:cTn"))
            if c.get("presetClass") is not None
        ]
        assert "entr" in classes

    def it_dispatches_exit(self, slide_with_shape):
        slide, shape = slide_with_shape
        slide.animations.add("exit", "fade", shape)
        classes = [
            c.get("presetClass")
            for c in slide._element.iter(qn("p:cTn"))
            if c.get("presetClass") is not None
        ]
        assert "exit" in classes

    def it_dispatches_emphasis(self, slide_with_shape):
        slide, shape = slide_with_shape
        slide.animations.add("emphasis", "pulse", shape)
        classes = [
            c.get("presetClass")
            for c in slide._element.iter(qn("p:cTn"))
            if c.get("presetClass") is not None
        ]
        assert "emph" in classes

    def it_dispatches_motion(self, slide_with_shape):
        slide, shape = slide_with_shape
        slide.animations.add("motion", "M 0 0 L 0.5 0 E", shape, duration=1500)
        paths = _animMotion_paths(slide)
        assert paths == ["M 0 0 L 0.5 0 E"]

    def it_writes_animRot_by_as_an_attribute_not_a_child(self, slide_with_shape):
        # CT_TLAnimateRotationBehavior allows only a <p:cBhvr> child; `by` is an
        # ST_Angle attribute.  Emitting <p:by> as a child makes PowerPoint reject
        # the deck (a <p:by> child is valid only on <p:animScale>).
        slide, shape = slide_with_shape
        slide.animations.add("emphasis", "spin", shape)
        animRots = list(slide._element.iter(qn("p:animRot")))
        assert animRots, "spin emphasis should emit a <p:animRot>"
        for animRot in animRots:
            assert animRot.get("by") is not None
            assert animRot.find(qn("p:by")) is None

    def it_writes_teeter_animRot_by_as_an_attribute(self, slide_with_shape):
        slide, shape = slide_with_shape
        slide.animations.add("emphasis", "teeter", shape)
        animRots = list(slide._element.iter(qn("p:animRot")))
        assert animRots
        for animRot in animRots:
            assert animRot.get("by") is not None
            assert animRot.find(qn("p:by")) is None

    def it_rejects_unknown_kind(self, slide_with_shape):
        slide, shape = slide_with_shape
        with pytest.raises(ValueError, match="Unknown animation kind"):
            slide.animations.add("teleport", "fade", shape)

    def it_rejects_motion_path_without_E_terminator(self, slide_with_shape):
        slide, shape = slide_with_shape
        with pytest.raises(ValueError, match="ending in 'E'"):
            slide.animations.add("motion", "M 0 0 L 0.5 0", shape)


class DescribeMotionPath:
    def it_emits_a_path_class_effect_for_a_line(self, slide_with_shape):
        slide, shape = slide_with_shape
        MotionPath.line(slide, shape, Inches(2), Inches(0))
        preset_classes = [
            c.get("presetClass")
            for c in slide._element.iter(qn("p:cTn"))
            if c.get("presetClass") is not None
        ]
        assert preset_classes == ["path"]

    def it_normalizes_the_line_path_against_slide_dimensions(self, slide_with_shape):
        slide, shape = slide_with_shape
        slide_w = slide.part.package.presentation_part.presentation.slide_width
        MotionPath.line(slide, shape, Inches(1), 0)
        path = _animMotion_paths(slide)[0]
        expected_x = float(Inches(1)) / float(slide_w)
        assert path.startswith("M 0 0 L")
        assert path.endswith(" E")
        # Parse the L coordinates: "M 0 0 L X Y E"
        l_part = path.split("L", 1)[1].rsplit("E", 1)[0].strip()
        x_str, y_str = l_part.split()
        assert float(x_str) == pytest.approx(expected_x)
        assert float(y_str) == pytest.approx(0.0)

    def it_emits_a_custom_path_unchanged(self, slide_with_shape):
        slide, shape = slide_with_shape
        MotionPath.custom(slide, shape, "M 0 0 C 0 -0.2 0.2 -0.2 0.2 0 E")
        assert _animMotion_paths(slide) == ["M 0 0 C 0 -0.2 0.2 -0.2 0.2 0 E"]

    def it_rejects_a_malformed_custom_path(self, slide_with_shape):
        slide, shape = slide_with_shape
        with pytest.raises(ValueError):
            MotionPath.custom(slide, shape, "")
        with pytest.raises(ValueError):
            MotionPath.custom(slide, shape, "no end marker")

    def it_emits_a_diagonal_path(self, slide_with_shape):
        slide, shape = slide_with_shape
        MotionPath.diagonal(slide, shape, Inches(2), Inches(1))
        path = _animMotion_paths(slide)[0]
        assert path.startswith("M 0 0 L")
        assert path.endswith(" E")

    def it_emits_a_closed_circle_path(self, slide_with_shape):
        slide, shape = slide_with_shape
        MotionPath.circle(slide, shape, Inches(1))
        paths = _animMotion_paths(slide)
        assert len(paths) == 1
        path = paths[0]
        # Four cubic-bezier segments, closing back at origin.
        assert path.count(" C ") == 4
        assert path.startswith("M 0 0")
        assert path.rstrip().endswith("0 0 E")

    def it_reverses_circle_direction_when_counterclockwise(self, slide_with_shape):
        slide, shape = slide_with_shape
        MotionPath.circle(slide, shape, Inches(1), clockwise=False)
        path = _animMotion_paths(slide)[0]
        # Counterclockwise circle's first control point sits below origin
        # (positive y in OOXML's downward y-axis is *below*).  We just
        # check the sign flipped vs. the clockwise default.
        first_c = path.split("C", 1)[1].split("C", 1)[0].strip().split()
        # First control point's y coordinate is the second token.
        y0 = float(first_c[1])
        assert y0 > 0  # below origin → counterclockwise

    def it_emits_a_quadratic_arc(self, slide_with_shape):
        slide, shape = slide_with_shape
        MotionPath.arc(slide, shape, Inches(3), 0, height=0.5)
        path = _animMotion_paths(slide)[0]
        assert path.startswith("M 0 0 Q")
        assert path.endswith(" E")

    def it_emits_a_zigzag_with_segment_count(self, slide_with_shape):
        slide, shape = slide_with_shape
        MotionPath.zigzag(slide, shape, Inches(4), 0, segments=4)
        path = _animMotion_paths(slide)[0]
        # 4 segments → 4 L commands.
        assert path.count(" L ") == 4

    def it_rejects_zero_zigzag_segments(self, slide_with_shape):
        slide, shape = slide_with_shape
        with pytest.raises(ValueError):
            MotionPath.zigzag(slide, shape, Inches(2), 0, segments=0)

    def it_emits_a_spiral_path(self, slide_with_shape):
        slide, shape = slide_with_shape
        MotionPath.spiral(slide, shape, Inches(2), turns=2)
        path = _animMotion_paths(slide)[0]
        assert path.startswith("M 0 0")
        assert path.endswith(" E")
        # 16 samples per turn × 2 turns = 32 line segments.
        assert path.count(" L ") == 32

    def it_ends_the_spiral_one_radius_from_start(self, slide_with_shape):
        slide, shape = slide_with_shape
        slide_w = slide.part.package.presentation_part.presentation.slide_width
        MotionPath.spiral(slide, shape, Inches(2), turns=2)
        path = _animMotion_paths(slide)[0]
        # Final L coordinate is the spiral endpoint.
        last_l = path.rsplit(" L ", 1)[1].rsplit(" E", 1)[0].strip().split()
        end_x, end_y = float(last_l[0]), float(last_l[1])
        expected_x = float(Inches(2)) / float(slide_w)
        # For an integer turns count the spiral lands on +x by one radius.
        assert end_x == pytest.approx(expected_x, rel=1e-6)
        assert end_y == pytest.approx(0.0, abs=1e-9)

    def it_rejects_zero_spiral_turns(self, slide_with_shape):
        slide, shape = slide_with_shape
        with pytest.raises(ValueError):
            MotionPath.spiral(slide, shape, Inches(2), turns=0)

    def it_curves_a_pure_vertical_arc(self, slide_with_shape):
        slide, shape = slide_with_shape
        MotionPath.arc(slide, shape, 0, Inches(3), height=0.5)
        path = _animMotion_paths(slide)[0]
        # Parse "M 0 0 Q cx cy nx ny E" for the control-point coordinates.
        q_part = path.split("Q", 1)[1].rsplit("E", 1)[0].strip().split()
        cx, cy = float(q_part[0]), float(q_part[1])
        # Pure-vertical chord must still bend the path off the chord —
        # otherwise the arc degenerates to a straight line, the bug Codex
        # / Copilot flagged.  With `height=0.5` and chord direction +y,
        # the perpendicular control point sits at non-zero x.
        assert cx != 0
        # cy is the chord midpoint.
        assert cy == pytest.approx(
            float(Inches(3))
            / 2
            / float(slide.part.package.presentation_part.presentation.slide_height)
        )


class DescribeAnimationSequence:
    def it_chains_subsequent_effects_after_the_first(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(1, Inches(1), Inches(2.5), Inches(2), Inches(1))
        c = slide.shapes.add_shape(1, Inches(1), Inches(4), Inches(2), Inches(1))

        with slide.animations.sequence():
            Entrance.fade(slide, a)
            Entrance.fade(slide, b)
            Emphasis.pulse(slide, c)

        node_types = [nt for nt in _ctn_node_types(slide) if nt != "tmRoot"]
        assert node_types == ["clickEffect", "afterEffect", "afterEffect"]

    def it_honours_an_explicit_start_trigger(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(1, Inches(1), Inches(2.5), Inches(2), Inches(1))

        with slide.animations.sequence(start=Trigger.WITH_PREVIOUS):
            Entrance.fade(slide, a)
            Entrance.fade(slide, b)

        node_types = [nt for nt in _ctn_node_types(slide) if nt != "tmRoot"]
        assert node_types == ["withEffect", "afterEffect"]

    def it_does_not_override_an_explicitly_supplied_trigger(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(1, Inches(1), Inches(2.5), Inches(2), Inches(1))

        with slide.animations.sequence():
            Entrance.fade(slide, a)
            # Explicit ON_CLICK must win over the sequence's AFTER_PREVIOUS default
            Entrance.fade(slide, b, trigger=Trigger.ON_CLICK)

        node_types = [nt for nt in _ctn_node_types(slide) if nt != "tmRoot"]
        assert node_types == ["clickEffect", "clickEffect"]

    def it_resets_after_the_block(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(1, Inches(1), Inches(3), Inches(2), Inches(1))

        with slide.animations.sequence():
            Entrance.fade(slide, a)
        # After exit, the next add_* should default back to ON_CLICK
        Entrance.fade(slide, b)

        node_types = [nt for nt in _ctn_node_types(slide) if nt != "tmRoot"]
        assert node_types == ["clickEffect", "clickEffect"]

    def it_rejects_nested_sequences(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        with slide.animations.sequence():
            with pytest.raises(RuntimeError):
                with slide.animations.sequence():
                    pass

    def it_shifts_the_first_effect_by_the_sequence_delay(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(1, Inches(1), Inches(3), Inches(2), Inches(1))

        with slide.animations.sequence(delay=750):
            Entrance.fade(slide, a)
            Entrance.fade(slide, b)

        cond_delays = [c.get("delay") for c in slide._element.iter(qn("p:cond"))]
        # Wrapper for first effect (clickEffect) → "indefinite";
        # inner first effect cond → "750" (the consumed sequence delay);
        # second effect wrapper → "0"; second inner cond → "0".
        assert "750" in cond_delays
        # Sequence delay must be consumed only once — no other "750" entries.
        assert cond_delays.count("750") == 1

    def it_does_not_shift_a_second_call_when_seq_delay_already_consumed(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(1, Inches(1), Inches(3), Inches(2), Inches(1))

        with slide.animations.sequence(delay=300):
            Entrance.fade(slide, a, delay=100)
            Entrance.fade(slide, b, delay=50)

        # Per-call delays should land *unchanged* on the second effect;
        # only the first effect picks up an extra +300 ms from the sequence.
        cond_delays = [c.get("delay") for c in slide._element.iter(qn("p:cond"))]
        assert "400" in cond_delays  # first: 100 user + 300 seq
        assert "50" in cond_delays  # second: 50 user, untouched
        assert "350" not in cond_delays  # second must not absorb sequence delay


class DescribeEntranceByParagraph:
    def it_emits_one_effect_per_paragraph(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(2))
        tf = tb.text_frame
        tf.text = "alpha"
        tf.add_paragraph().text = "beta"
        tf.add_paragraph().text = "gamma"

        Entrance.fade(slide, tf, by_paragraph=True)

        # Each paragraph emits a <p:set> + <p:animEffect> pair, both
        # targeting the same paragraph index.  Three paragraphs → three
        # distinct indices, two pRg occurrences per index.
        indices = sorted({rg.get("st") for rg in slide._element.iter(qn("p:pRg"))})
        assert indices == ["0", "1", "2"]

    def it_chains_paragraphs_after_the_first(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(2))
        tf = tb.text_frame
        tf.text = "one"
        tf.add_paragraph().text = "two"

        Entrance.fade(slide, tf, by_paragraph=True)

        node_types = [nt for nt in _ctn_node_types(slide) if nt != "tmRoot"]
        assert node_types == ["clickEffect", "afterEffect"]

    def it_accepts_a_shape_with_a_text_frame(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(2))
        tb.text_frame.text = "only"

        Entrance.fade(slide, tb, by_paragraph=True)

        indices = {rg.get("st") for rg in slide._element.iter(qn("p:pRg"))}
        assert indices == {"0"}

    def it_rejects_unsupported_presets(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(2))
        tb.text_frame.text = "x"

        with pytest.raises(ValueError):
            slide.animations.add_entrance("fly_in", tb.text_frame, by_paragraph=True)

    def it_rejects_a_table_cell_text_frame(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        tbl_shape = slide.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(4), Inches(2))
        cell_tf = tbl_shape.table.cell(0, 0).text_frame
        cell_tf.text = "cell content"

        with pytest.raises(TypeError, match="parent chain"):
            Entrance.fade(slide, cell_tf, by_paragraph=True)

    def it_rejects_a_text_frame_when_by_paragraph_is_false(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
        tb.text_frame.text = "x"

        with pytest.raises(TypeError, match="shape_id"):
            Entrance.fade(slide, tb.text_frame)


class DescribeAnimationGroup:
    """`group()` makes the contained effects animate as one visual cluster."""

    def it_emits_first_after_previous_then_with_previous(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(1, Inches(1), Inches(2.5), Inches(2), Inches(1))
        c = slide.shapes.add_shape(1, Inches(1), Inches(4), Inches(2), Inches(1))

        with slide.animations.group():
            Entrance.fade(slide, a)
            Entrance.fade(slide, b)
            Entrance.fade(slide, c)

        node_types = [nt for nt in _ctn_node_types(slide) if nt != "tmRoot"]
        assert node_types == ["afterEffect", "withEffect", "withEffect"]

    def it_honours_an_explicit_start_trigger(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(1, Inches(1), Inches(2.5), Inches(2), Inches(1))

        with slide.animations.group(start=Trigger.ON_CLICK):
            Entrance.fade(slide, a)
            Entrance.fade(slide, b)

        node_types = [nt for nt in _ctn_node_types(slide) if nt != "tmRoot"]
        assert node_types == ["clickEffect", "withEffect"]

    def it_shifts_only_the_first_effect_by_the_group_delay(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(1, Inches(1), Inches(3), Inches(2), Inches(1))

        with slide.animations.group(delay=200):
            Entrance.fade(slide, a)
            Entrance.fade(slide, b)

        cond_delays = [c.get("delay") for c in slide._element.iter(qn("p:cond"))]
        assert "200" in cond_delays
        assert cond_delays.count("200") == 1

    def it_resets_after_the_block(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(1, Inches(1), Inches(3), Inches(2), Inches(1))

        with slide.animations.group():
            Entrance.fade(slide, a)
        Entrance.fade(slide, b)

        node_types = [nt for nt in _ctn_node_types(slide) if nt != "tmRoot"]
        assert node_types == ["afterEffect", "clickEffect"]

    def it_rejects_nested_groups(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        with slide.animations.group():
            with pytest.raises(RuntimeError):
                with slide.animations.group():
                    pass

    def it_rejects_mixing_with_sequence(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        with slide.animations.sequence():
            with pytest.raises(RuntimeError):
                with slide.animations.group():
                    pass


class DescribeAnimationsIntrospection:
    """`SlideAnimations` is iterable, sized, and clearable."""

    def it_iterates_in_document_order(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(1, Inches(1), Inches(2.5), Inches(2), Inches(1))

        Entrance.fade(slide, a)
        Entrance.fly_in(slide, b, direction="left")

        entries = list(slide.animations)
        assert len(entries) == 2
        assert entries[0].kind == "entrance"
        assert entries[0].preset == "fade"
        assert entries[0].shape_id == a.shape_id
        # Shape proxies are created on demand, so identity is not preserved;
        # compare by shape_id which is stable.
        assert entries[0].shape is not None
        assert entries[0].shape.shape_id == a.shape_id
        assert entries[0].trigger == Trigger.ON_CLICK
        assert entries[1].preset == "fly_in"
        assert entries[1].shape_id == b.shape_id

    def it_supports_len(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        assert len(slide.animations) == 0
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        Entrance.fade(slide, a)
        assert len(slide.animations) == 1

    def it_clears_every_entry(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(1, Inches(1), Inches(2), Inches(2), Inches(1))
        Entrance.fade(slide, a)
        Entrance.fade(slide, b)

        removed = slide.animations.clear()
        assert removed == 2
        assert len(slide.animations) == 0

    def it_reports_the_inner_effect_duration(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        Entrance.fade(slide, a, duration=750)
        entry = next(iter(slide.animations))
        assert entry.duration == 750

    def it_reports_the_per_effect_delay(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        Entrance.fade(slide, a, delay=120)
        entry = next(iter(slide.animations))
        assert entry.delay == 120

    def it_remove_drops_just_that_entry(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(1, Inches(1), Inches(2), Inches(2), Inches(1))
        Entrance.fade(slide, a)
        Entrance.fade(slide, b)

        first = next(iter(slide.animations))
        first.remove()
        assert len(slide.animations) == 1
        assert next(iter(slide.animations)).shape_id == b.shape_id

    # -- timing-tree pruning: an empty <p:childTnLst> is schema-invalid
    # -- (CT_TimeNodeList requires a time-node child), so whichever removal
    # -- takes out the last entry must drop the whole p:timing subtree.

    def it_prunes_the_timing_tree_when_remove_takes_the_last_entry(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        Entrance.fade(slide, a)

        next(iter(slide.animations)).remove()
        assert slide._element.find(qn("p:timing")) is None

    def it_prunes_the_timing_tree_on_clear(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        Entrance.fade(slide, a)
        Emphasis.pulse(slide, a)

        slide.animations.clear()
        assert slide._element.find(qn("p:timing")) is None

    def it_prunes_the_timing_tree_when_purge_removes_the_last_entry(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        Entrance.fade(slide, a)
        a._element.getparent().remove(a._element)

        assert slide.animations.purge_orphans() == 1
        assert slide._element.find(qn("p:timing")) is None

    def it_never_writes_exponent_notation_into_motion_paths(self):
        # %g formatting emitted scientific notation for float noise
        # (sin/cos at multiples of pi -> 1.5e-17), which PowerPoint's path
        # parser cannot read ('e' is not a number token and 'E' is the End
        # command), so the whole animation was dropped.
        import re

        from power_pptx.animation import MotionPath

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        MotionPath.spiral(slide, a, Inches(2), turns=2)
        MotionPath.line(slide, a, Inches(0.00001), Inches(2))
        MotionPath.circle(slide, a, Inches(1))
        MotionPath.zigzag(slide, a, Inches(3), 0, segments=4)

        paths = [m.get("path") for m in slide._element.iter(qn("p:animMotion"))]
        assert paths
        offenders = [p for p in paths if re.search(r"\de[-+]", p)]
        assert offenders == [], offenders

    def but_it_keeps_a_timing_tree_that_still_holds_entries(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(1, Inches(1), Inches(2), Inches(2), Inches(1))
        Entrance.fade(slide, a)
        Entrance.fade(slide, b)

        next(iter(slide.animations)).remove()
        assert slide._element.find(qn("p:timing")) is not None

    def and_it_preserves_a_timing_extension_list_when_pruning(self):
        # CT_SlideTiming legally holds only an extLst; foreign extension data
        # must survive the prune even when the last effect is removed.
        from lxml import etree

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        Entrance.fade(slide, a)
        timing = slide._element.find(qn("p:timing"))
        etree.SubElement(timing, qn("p:extLst"))

        slide.animations.clear()

        timing = slide._element.find(qn("p:timing"))
        assert timing is not None
        assert [child.tag for child in timing] == [qn("p:extLst")]


class DescribeBlockTriggerCounting:
    """Explicit triggers inside group()/sequence() still consume a slot.

    Regression for: when the *first* effect inside a group() or sequence()
    block sets ``trigger=`` explicitly, the *next* unset-trigger effect
    must still default to WITH_PREVIOUS / AFTER_PREVIOUS — not be treated
    as if it were itself the first effect of the block.
    """

    def it_treats_subsequent_unset_trigger_as_with_previous_in_group(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(1, Inches(1), Inches(2.5), Inches(2), Inches(1))
        c = slide.shapes.add_shape(1, Inches(1), Inches(4), Inches(2), Inches(1))

        with slide.animations.group():
            Entrance.fade(slide, a, trigger=Trigger.ON_CLICK)  # explicit
            Entrance.fade(slide, b)  # must be WITH_PREVIOUS, not AFTER_PREVIOUS
            Entrance.fade(slide, c)

        node_types = [nt for nt in _ctn_node_types(slide) if nt != "tmRoot"]
        assert node_types == ["clickEffect", "withEffect", "withEffect"]

    def it_treats_subsequent_unset_trigger_as_after_previous_in_sequence(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(1, Inches(1), Inches(2.5), Inches(2), Inches(1))
        c = slide.shapes.add_shape(1, Inches(1), Inches(4), Inches(2), Inches(1))

        with slide.animations.sequence():
            Entrance.fade(slide, a, trigger=Trigger.WITH_PREVIOUS)  # explicit
            Entrance.fade(slide, b)  # must be AFTER_PREVIOUS
            Entrance.fade(slide, c)

        node_types = [nt for nt in _ctn_node_types(slide) if nt != "tmRoot"]
        assert node_types == ["withEffect", "afterEffect", "afterEffect"]


# ---------------------------------------------------------------------------
# Timing trees authored in PowerPoint: everything nested under a main sequence
# ---------------------------------------------------------------------------


@pytest.fixture
def three_shapes():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    a, b, c = (
        slide.shapes.add_shape(1, Inches(1 + 2 * i), Inches(1), Inches(1), Inches(1))
        for i in range(3)
    )
    return slide, a, b, c


def _click_groups(slide):
    """The click-group ``p:par`` elements of the main sequence."""
    return slide._element.xpath("p:timing//p:cTn[@nodeType='mainSeq']/p:childTnLst/p:par")


def _childless_lists(slide):
    """Time-node and build lists holding nothing; the schema requires at least one entry."""
    return slide._element.xpath("p:timing//p:childTnLst[not(*)] | p:timing/p:bldLst[not(*)]")


def _interactive_sequences(slide):
    return slide._element.xpath("p:timing//p:seq/p:cTn[@nodeType='interactiveSeq']")


def _share_click_group(slide, shape):
    """Graft a withEffect for *shape* into the first click group's effect list.

    The result is a click group holding two effects, which is how PowerPoint writes a
    With Previous effect.
    """
    effects = slide._element.xpath(
        "p:timing/p:tnLst/p:par/p:cTn/p:childTnLst/p:par/p:cTn/p:childTnLst"
    )[0]
    clone = copy.deepcopy(effects[0])
    for target in clone.iter(qn("p:spTgt")):
        target.set("spid", str(shape.shape_id))
    next_id = max(cTn_ids(slide)) + 1
    for ctn in clone.iter(qn("p:cTn")):
        ctn.set("id", str(next_id))
        next_id += 1
    clone.find(qn("p:cTn")).set("nodeType", "withEffect")
    effects.append(clone)


class DescribeMainSequenceIntrospection:
    """`slide.animations` sees the effects of decks authored in PowerPoint."""

    def it_reports_every_effect_in_a_main_sequence(self, three_shapes):
        slide, a, b, c = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [
                    (a.shape_id, "clickEffect"),
                    (b.shape_id, "withEffect"),
                    (c.shape_id, "afterEffect"),
                ]
            ),
        )

        entries = list(slide.animations)

        assert len(slide.animations) == 3
        assert bool(slide.animations) is True
        assert [e.shape_id for e in entries] == [a.shape_id, b.shape_id, c.shape_id]
        assert [e.shape.shape_id for e in entries] == [a.shape_id, b.shape_id, c.shape_id]
        assert [e.trigger for e in entries] == [
            Trigger.ON_CLICK,
            Trigger.WITH_PREVIOUS,
            Trigger.AFTER_PREVIOUS,
        ]
        assert [(e.kind, e.preset, e.duration) for e in entries] == [("entrance", "fade", 500)] * 3

    def it_also_reports_interactive_sequences_and_effects_the_library_appended(self, three_shapes):
        slide, a, b, c = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [(a.shape_id, "clickEffect")],
                interactive=[(a.shape_id, [(b.shape_id, "clickEffect")])],
            ),
        )

        Entrance.fade(slide, c)  # appended flat, after the structure PowerPoint wrote

        assert [e.shape_id for e in slide.animations] == [a.shape_id, b.shape_id, c.shape_id]

    def it_reports_nothing_for_a_main_sequence_without_effects(self, three_shapes):
        slide, a, _, _ = three_shapes
        install_timing(slide, powerpoint_timing_xml([], media=[("video", a.shape_id)]))

        assert len(slide.animations) == 0
        assert not slide.animations
        assert list(slide.animations) == []

    def it_clears_every_effect(self, three_shapes):
        slide, a, b, c = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [
                    (a.shape_id, "clickEffect"),
                    (b.shape_id, "withEffect"),
                    (c.shape_id, "clickEffect"),
                ],
                bld=[a.shape_id, b.shape_id, c.shape_id],
            ),
        )

        assert slide.animations.clear() == 3

        assert len(slide.animations) == 0
        # nothing meaningful is left, so the whole timing goes, build list included
        assert slide._element.find(qn("p:timing")) is None

    def and_it_clears_the_effects_of_interactive_sequences_too(self, three_shapes):
        slide, a, b, _ = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [(a.shape_id, "clickEffect")],
                interactive=[(a.shape_id, [(b.shape_id, "clickEffect")])],
            ),
        )

        assert slide.animations.clear() == 2

        assert slide._element.find(qn("p:timing")) is None

    def but_it_keeps_media_play_controls_when_clearing(self, three_shapes):
        slide, a, b, c = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [(a.shape_id, "clickEffect"), (b.shape_id, "withEffect")],
                media=[("video", c.shape_id)],
                bld=[a.shape_id],
            ),
        )

        assert slide.animations.clear() == 2

        assert target_ids(slide) == [c.shape_id]
        # the build entries described the effects just cleared
        assert slide._element.xpath("p:timing/p:bldLst") == []
        # the emptied main sequence stays, as PowerPoint writes one without effects
        assert slide._element.xpath("p:timing//p:seq/p:cTn[@nodeType='mainSeq'][not(*)]")
        assert _childless_lists(slide) == []

    def it_removes_one_entry_and_prunes_the_groups_it_empties(self, three_shapes):
        slide, a, b, c = three_shapes
        # A starts a click, B follows it, C starts the next click
        install_timing(
            slide,
            powerpoint_timing_xml(
                [
                    (a.shape_id, "clickEffect"),
                    (b.shape_id, "afterEffect"),
                    (c.shape_id, "clickEffect"),
                ]
            ),
        )
        entries = list(slide.animations)

        entries[1].remove()

        assert [e.shape_id for e in slide.animations] == [a.shape_id, c.shape_id]
        assert len(_click_groups(slide)) == 2
        assert _childless_lists(slide) == []

        entries[2].remove()

        assert [e.shape_id for e in slide.animations] == [a.shape_id]
        assert len(_click_groups(slide)) == 1
        assert _childless_lists(slide) == []


class DescribeDeletingShapesAnimatedInAMainSequence:
    """`shape.delete()` cleans the timing of decks authored in PowerPoint."""

    def it_removes_only_the_deleted_shapes_effect_from_a_shared_click_group(self, three_shapes):
        slide, a, b, c = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [
                    (a.shape_id, "clickEffect"),
                    (b.shape_id, "withEffect"),
                    (c.shape_id, "clickEffect"),
                ],
                bld=[a.shape_id, b.shape_id, c.shape_id],
            ),
        )

        a.delete()

        assert set(target_ids(slide)) == {b.shape_id, c.shape_id}
        assert build_ids(slide) == [b.shape_id, c.shape_id]
        assert [e.shape_id for e in slide.animations] == [b.shape_id, c.shape_id]
        # B keeps playing from inside the first click group
        assert len(_click_groups(slide)) == 2
        assert _childless_lists(slide) == []

    def it_prunes_the_group_pars_the_deleted_effect_leaves_empty(self, three_shapes):
        slide, a, b, c = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [
                    (a.shape_id, "clickEffect"),
                    (b.shape_id, "afterEffect"),
                    (c.shape_id, "clickEffect"),
                ]
            ),
        )
        groups = "p:timing//p:cTn[@nodeType='mainSeq']/p:childTnLst/p:par/p:cTn/p:childTnLst/p:par"
        assert len(slide._element.xpath(groups)) == 3  # A's, B's and C's with/after groups

        b.delete()

        assert [e.shape_id for e in slide.animations] == [a.shape_id, c.shape_id]
        assert len(_click_groups(slide)) == 2
        assert len(slide._element.xpath(groups)) == 2

        c.delete()

        assert len(_click_groups(slide)) == 1
        assert _childless_lists(slide) == []

    def it_drops_the_timing_once_nothing_meaningful_remains(self, three_shapes):
        slide, a, b, c = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [
                    (a.shape_id, "clickEffect"),
                    (b.shape_id, "withEffect"),
                    (c.shape_id, "clickEffect"),
                ],
                bld=[a.shape_id, b.shape_id, c.shape_id],
            ),
        )

        a.delete()
        b.delete()
        assert slide._element.find(qn("p:timing")) is not None
        c.delete()

        # the emptied main sequence alone is not worth keeping
        assert slide._element.find(qn("p:timing")) is None

    def but_it_keeps_the_main_sequence_while_media_play_controls_remain(self, three_shapes):
        slide, a, b, c = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [(a.shape_id, "clickEffect"), (b.shape_id, "withEffect")],
                media=[("video", c.shape_id)],
                bld=[a.shape_id, b.shape_id],
            ),
        )

        a.delete()
        b.delete()

        assert target_ids(slide) == [c.shape_id]
        assert slide._element.xpath("p:timing//p:seq/p:cTn[@nodeType='mainSeq'][not(*)]")
        assert slide._element.xpath("p:timing/p:bldLst") == []
        assert _childless_lists(slide) == []

    def and_it_keeps_an_interactive_sequence_that_targets_live_shapes(self, three_shapes):
        slide, a, b, c = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [(a.shape_id, "clickEffect")],
                interactive=[(b.shape_id, [(c.shape_id, "clickEffect")])],
            ),
        )

        a.delete()

        assert [e.shape_id for e in slide.animations] == [c.shape_id]
        assert len(_interactive_sequences(slide)) == 1
        assert b.shape_id in target_ids(slide)  # the trigger is still wired up
        assert _childless_lists(slide) == []

    def it_drops_an_interactive_sequence_whose_trigger_shape_is_deleted(self, three_shapes):
        slide, a, b, c = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [(a.shape_id, "clickEffect")],
                interactive=[(b.shape_id, [(c.shape_id, "clickEffect")])],
            ),
        )

        b.delete()

        assert [e.shape_id for e in slide.animations] == [a.shape_id]
        assert _interactive_sequences(slide) == []
        assert target_ids(slide) == [a.shape_id, a.shape_id]

    def and_it_drops_an_interactive_sequence_left_without_effects(self, three_shapes):
        slide, a, b, c = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [(a.shape_id, "clickEffect")],
                interactive=[(b.shape_id, [(c.shape_id, "clickEffect")])],
            ),
        )

        c.delete()

        assert [e.shape_id for e in slide.animations] == [a.shape_id]
        assert _interactive_sequences(slide) == []
        assert target_ids(slide) == [a.shape_id, a.shape_id]
        assert _childless_lists(slide) == []

    def it_drops_dead_build_entries_and_the_emptied_build_list(self, three_shapes):
        slide, a, b, c = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [(a.shape_id, "clickEffect"), (b.shape_id, "withEffect")],
                media=[("video", c.shape_id)],  # keeps the timing alive
                bld=[a.shape_id, b.shape_id],
            ),
        )

        a.delete()
        assert build_ids(slide) == [b.shape_id]

        b.delete()
        assert slide._element.xpath("p:timing/p:bldLst") == []

    def it_removes_the_effects_of_every_member_of_a_deleted_group(self, three_shapes):
        slide, a, b, c = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [
                    (a.shape_id, "clickEffect"),
                    (b.shape_id, "withEffect"),
                    (c.shape_id, "clickEffect"),
                ],
                bld=[a.shape_id, b.shape_id, c.shape_id],
            ),
        )
        group = slide.shapes.add_group_shape([a, b])

        group.delete()

        assert [e.shape_id for e in slide.animations] == [c.shape_id]
        assert set(target_ids(slide)) == {c.shape_id}
        assert build_ids(slide) == [c.shape_id]

    def it_counts_the_entries_purge_orphans_removes(self, three_shapes):
        slide, a, b, c = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [
                    (a.shape_id, "clickEffect"),
                    (b.shape_id, "withEffect"),
                    (c.shape_id, "clickEffect"),
                ]
            ),
        )
        for shape in (a, b):
            shape._element.getparent().remove(shape._element)  # bypass delete()

        assert slide.animations.purge_orphans() == 2
        assert [e.shape_id for e in slide.animations] == [c.shape_id]
        assert slide.animations.purge_orphans() == 0

    def it_keeps_cTn_ids_unique_when_effects_are_added_afterwards(self, three_shapes):
        slide, a, b, c = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [
                    (a.shape_id, "clickEffect"),
                    (b.shape_id, "withEffect"),
                    (c.shape_id, "clickEffect"),
                ]
            ),
        )

        b.delete()
        assert len(cTn_ids(slide)) == len(set(cTn_ids(slide)))

        extra = slide.shapes.add_shape(1, Inches(1), Inches(3), Inches(1), Inches(1))
        Entrance.fade(slide, extra)
        Emphasis.pulse(slide, extra)

        ids = cTn_ids(slide)
        assert len(ids) == len(set(ids))
        assert [e.shape_id for e in slide.animations] == [
            a.shape_id,
            c.shape_id,
            extra.shape_id,
            extra.shape_id,
        ]

    def it_keeps_the_cleaned_timing_through_a_save_and_reload(self, three_shapes):
        slide, a, b, c = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml(
                [(a.shape_id, "clickEffect"), (b.shape_id, "withEffect")],
                bld=[a.shape_id, b.shape_id],
            ),
        )
        a.delete()
        buf = io.BytesIO()
        slide.part.package.save(buf)
        buf.seek(0)

        reloaded = Presentation(buf).slides[0]

        assert target_ids(reloaded) == [b.shape_id, b.shape_id]
        assert build_ids(reloaded) == [b.shape_id]
        assert [e.shape_id for e in reloaded.animations] == [b.shape_id]


class DescribeDeletingShapesSharingAFlatClickGroup:
    """The library's own flat structure, with a second effect inside a click group."""

    def it_reports_each_effect_of_a_shared_click_group(self, three_shapes):
        slide, a, b, c = three_shapes
        Entrance.fade(slide, a)
        _share_click_group(slide, b)
        Entrance.fade(slide, c)

        assert len(slide.animations) == 3
        assert [e.shape_id for e in slide.animations] == [a.shape_id, b.shape_id, c.shape_id]
        assert [e.trigger for e in slide.animations] == [
            Trigger.ON_CLICK,
            Trigger.WITH_PREVIOUS,
            Trigger.ON_CLICK,
        ]

    def it_keeps_the_sibling_effect_of_a_deleted_shape(self, three_shapes):
        slide, a, b, c = three_shapes
        Entrance.fade(slide, a)
        _share_click_group(slide, b)
        Entrance.fade(slide, c)
        assert target_ids(slide) == [a.shape_id] * 2 + [b.shape_id] * 2 + [c.shape_id] * 2

        a.delete()

        assert target_ids(slide) == [b.shape_id, b.shape_id, c.shape_id, c.shape_id]
        assert [e.shape_id for e in slide.animations] == [b.shape_id, c.shape_id]
        assert len(slide._element.xpath("p:timing/p:tnLst/p:par/p:cTn/p:childTnLst/p:par")) == 2

    def and_it_still_drops_a_click_group_it_has_emptied(self, three_shapes):
        slide, a, b, c = three_shapes
        Entrance.fade(slide, a)
        _share_click_group(slide, b)
        Entrance.fade(slide, c)

        a.delete()
        b.delete()

        assert target_ids(slide) == [c.shape_id, c.shape_id]
        assert [e.shape_id for e in slide.animations] == [c.shape_id]
        assert len(slide._element.xpath("p:timing/p:tnLst/p:par/p:cTn/p:childTnLst/p:par")) == 1
        assert _childless_lists(slide) == []


class DescribeDeletingMovies:
    """A movie's play controls are timing nodes that target the movie shape."""

    @staticmethod
    def _add_movie(slide, left=1):
        return slide.shapes.add_movie(
            io.BytesIO(b"\x00" * 16),
            Inches(left),
            Inches(1),
            Inches(2),
            Inches(2),
            mime_type="video/mp4",
        )

    def it_removes_the_play_controls_of_a_deleted_movie(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        movie = self._add_movie(slide)
        assert target_ids(slide) == [movie.shape_id]

        movie.delete()

        assert slide._element.find(qn("p:timing")) is None
        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        assert Presentation(buf).slides[0]._element.find(qn("p:timing")) is None

    def but_it_keeps_the_play_controls_of_the_other_movies(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        first, second = self._add_movie(slide), self._add_movie(slide, left=4)

        first.delete()

        assert target_ids(slide) == [second.shape_id]
        assert len(slide._element.xpath("p:timing//p:video")) == 1

    def it_removes_the_play_controls_of_a_movie_inside_a_deleted_group(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        group = slide.shapes.add_group_shape()
        group.shapes.add_movie(
            io.BytesIO(b"\x00" * 16),
            Inches(1),
            Inches(1),
            Inches(2),
            Inches(2),
            mime_type="video/mp4",
        )
        assert len(target_ids(slide)) == 1

        group.delete()

        assert slide._element.find(qn("p:timing")) is None

    def it_removes_dead_audio_nodes_as_well(self, three_shapes):
        slide, a, b, _ = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml([], media=[("audio", a.shape_id), ("video", b.shape_id)]),
        )

        a.delete()
        assert target_ids(slide) == [b.shape_id]
        assert slide._element.xpath("p:timing//p:audio") == []

        b.delete()
        assert slide._element.find(qn("p:timing")) is None

    def it_removes_media_nodes_when_purged_directly(self, three_shapes):
        slide, a, b, _ = three_shapes
        install_timing(
            slide,
            powerpoint_timing_xml([], media=[("video", a.shape_id), ("video", b.shape_id)]),
        )
        a._element.getparent().remove(a._element)  # bypass delete()

        slide.animations.purge_orphans()

        assert target_ids(slide) == [b.shape_id]
