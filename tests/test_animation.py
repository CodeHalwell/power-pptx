"""Unit-test suite for high-level `power_pptx.animation` extensions.

Covers Phase 5 motion paths, the `sequence()` context manager, and
by-paragraph entrance animations.  The lower-level entrance/exit/
emphasis presets are exercised via the integration round-trip suite.
"""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx.animation import Emphasis, Entrance, Exit, MotionPath, Trigger
from power_pptx.oxml.ns import qn
from power_pptx.util import Inches


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


@pytest.fixture
def slide_with_shape():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    shape = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
    return slide, shape


def _ctn_node_types(slide):
    return [
        c.get("nodeType")
        for c in slide._element.iter(qn("p:cTn"))
        if c.get("nodeType") is not None
    ]


def _animMotion_paths(slide):
    return [
        m.get("path") for m in slide._element.iter(qn("p:animMotion"))
    ]


def _path_commands(path):
    """The command letters of a motion-path string, in order."""
    return [token for token in path.split() if token.isalpha()]


class DescribeSvgMotionPath:
    """`MotionPath.svg(...)` accepts SVG path syntax with a viewbox."""

    def it_converts_an_absolute_line_path(self, slide_with_shape):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        out = _svg_to_ooxml_motion_path(
            "M 0 0 L 100 0", viewbox=(0, 0, 100, 100)
        )
        assert out == "M 0 0 L 1 0 E"

    def it_converts_relative_commands(self):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        # m 5 5 → starts at (5,5); l 10 0 → moves to (15,5); l 0 10 → (15,15)
        out = _svg_to_ooxml_motion_path(
            "m 5 5 l 10 0 l 0 10", viewbox=(0, 0, 100, 100)
        )
        assert out == "M 0 0 L 0.1 0 L 0.1 0.1 E"

    def it_supports_h_v_z_shortcuts(self):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        out = _svg_to_ooxml_motion_path("M 0 0 H 100 V 100 Z")
        # Z → close back to subpath origin (the M anchor).
        assert out.startswith("M 0 0 L")
        assert out.endswith(" E")

    def it_supports_cubic_curve(self):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        out = _svg_to_ooxml_motion_path(
            "M 0 0 C 0 -10 80 -10 80 0", viewbox=(0, 0, 100, 100)
        )
        assert "C" in out
        assert out.endswith(" E")

    def it_emits_motion_path_via_class_method(self, slide_with_shape):
        from power_pptx.animation import MotionPath

        slide, shape = slide_with_shape
        MotionPath.svg(
            slide, shape, "M 0 0 L 100 0", viewbox=(0, 0, 100, 100)
        )
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

    @pytest.mark.parametrize(
        ("svg", "message"),
        [
            # -- used to spin forever: the closepath branch never moved on --
            ("M 0 0 L 1 1 Z 5", "expected a command after 'Z'"),
            ("M 0 0 L 1 1 z 0.5 0.5", "expected a command after 'z'"),
            # -- used to trip a bare `assert` --
            ("Z M 0 0", "must start with M"),
            ("1 2 M 0 0", "must start with M"),
            ("M 0 0 L 1", "'L' needs 2 coordinate"),
            ("M 0", "'M' needs 2 coordinate"),
            ("M 0 0 C 1 1 2 2 3", "'C' needs 6 coordinate"),
            ("M 0 0 Q 1 1 2", "'Q' needs 4 coordinate"),
            ("M 0 0 L 5e 1", "'L' needs 2 coordinate"),
            # -- a character the old tokenizer skipped, flipping the direction --
            ("M 0 0 L −1 0", "unexpected character"),
            ("M 0 0 L 1 0 #", "unexpected character"),
        ],
    )
    def it_raises_ValueError_on_a_malformed_path(self, svg, message):
        import signal

        from power_pptx.animation import _svg_to_ooxml_motion_path

        def give_up(*_):
            raise AssertionError("converter did not return for %r" % svg)

        signal.signal(signal.SIGALRM, give_up)
        signal.alarm(5)
        try:
            with pytest.raises(ValueError, match=message):
                _svg_to_ooxml_motion_path(svg)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, signal.SIG_DFL)

    @pytest.mark.parametrize(
        ("svg", "viewbox", "expected"),
        [
            # -- separators are optional wherever a number can only start anew --
            ("M10-5L-3-4", (0, 0, 10, 10), "M 0 0 L -1.3 0.1 E"),
            ("M.5.5L1.5.25", None, "M 0 0 L 1 -0.25 E"),
            ("M,0,0,L,1,1", None, "M 0 0 L 1 1 E"),
            ("M0 0 L+0.5 +0.25", None, "M 0 0 L 0.5 0.25 E"),
            ("M0 0 L1e-1 2E-1", None, "M 0 0 L 0.1 0.2 E"),
            # -- coordinates after the first pair of a moveto are linetos --
            ("M 0 0 10 0 10 10", (0, 0, 100, 100), "M 0 0 L 0.1 0 L 0.1 0.1 E"),
            ("m 0 0 10 0 10 10", (0, 0, 100, 100), "M 0 0 L 0.1 0 L 0.2 0.1 E"),
            # -- and a command repeats for as long as coordinates follow --
            ("M 0 0 H 1 2 3", None, "M 0 0 L 1 0 L 2 0 L 3 0 E"),
            # -- a closed subpath, then a second one --
            (
                "M 1 1 l 1 0 z m 1 1 l 1 0",
                (0, 0, 10, 10),
                "M 0 0 L 0.1 0 L 0 0 M 0.1 0.1 L 0.2 0.1 E",
            ),
        ],
    )
    def it_follows_the_svg_path_grammar(self, svg, viewbox, expected):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        assert _svg_to_ooxml_motion_path(svg, viewbox=viewbox) == expected

    def it_writes_a_quadratic_curve_as_the_cubic_tracing_it(self):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        out = _svg_to_ooxml_motion_path("M 0 0 Q 50 -60 100 0", viewbox=(0, 0, 100, 100))

        # C1 = P0 + 2/3 (Q - P0), C2 = P + 2/3 (Q - P)
        assert out == "M 0 0 C 0.333333 -0.4 0.666667 -0.4 1 0 E"

    def it_resolves_relative_quadratic_curves_against_the_current_point(self):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        out = _svg_to_ooxml_motion_path("M 10 10 q 3 3 6 0 3 -3 6 0", viewbox=(0, 0, 10, 10))

        assert out == "M 0 0 C 0.2 0.2 0.4 0.2 0.6 0 C 0.8 -0.2 1 -0.2 1.2 0 E"

    @pytest.mark.parametrize(
        "svg",
        ["M 0 0 Q 50 -60 100 0", "M 0 0 q 5 5 10 0 t 10 0", "M 0 0 L 1 0 C 1 1 2 2 3 3 z"],
    )
    def it_only_ever_writes_commands_a_motion_path_allows(self, svg):
        from power_pptx.animation import _svg_to_ooxml_motion_path

        try:
            out = _svg_to_ooxml_motion_path(svg)
        except ValueError:
            return  # -- an unsupported command is refused, not passed through --
        assert set(_path_commands(out)) <= set("MLCZE")


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

    def it_ends_a_motion_path_that_was_left_without_its_E(self, slide_with_shape):
        slide, shape = slide_with_shape
        slide.animations.add("motion", "M 0 0 L 0.5 0", shape)
        assert _animMotion_paths(slide) == ["M 0 0 L 0.5 0 E"]

    def it_rejects_a_motion_path_that_is_not_one(self, slide_with_shape):
        slide, shape = slide_with_shape
        with pytest.raises(ValueError, match="non-empty OOXML path"):
            slide.animations.add("motion", "", shape)
        with pytest.raises(ValueError, match="unsupported motion path command"):
            slide.animations.add("motion", "fade", shape)


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

    @pytest.mark.parametrize(
        ("path", "written"),
        [
            # -- the example in the shipped skill, which used to raise --
            ("M 0 0 L 0.5 0.5 L 1 0", "M 0 0 L 0.5 0.5 L 1 0 E"),
            ("M 0 0 L 0.5 0.5 L 1 0 E", "M 0 0 L 0.5 0.5 L 1 0 E"),
            ("  M 0 0 L 0.25 0  ", "M 0 0 L 0.25 0 E"),
            # -- lower case is relative, and stays so --
            ("m 0 0 l 0.1 0 c 0 0.1 0.1 0.1 0.1 0 e", "m 0 0 l 0.1 0 c 0 0.1 0.1 0.1 0.1 0 e"),
            # -- a loop closed with Z is complete without an E --
            ("M 0 0 L 0.1 0 L 0.1 0.1 Z", "M 0 0 L 0.1 0 L 0.1 0.1 Z"),
            # -- separators and number forms are tidied; `E-2` here is an exponent --
            ("M0,0L1E-2,-.5", "M 0 0 L 0.01 -0.5 E"),
            ("M 0 0 L 0.1 0 0.2 0.1", "M 0 0 L 0.1 0 L 0.2 0.1 E"),
        ],
    )
    def it_ends_and_tidies_a_custom_path(self, slide_with_shape, path, written):
        slide, shape = slide_with_shape

        MotionPath.custom(slide, shape, path)

        assert _animMotion_paths(slide) == [written]

    @pytest.mark.parametrize(
        ("path", "message"),
        [
            # -- used to be pasted into the attribute as they were: the first
            # -- smuggled a second attribute in, the second broke the parser --
            ('M 0 0 L 1 0 E" bogus="1', "unexpected character"),
            ("M 0 0 L 1 0 E <", "unexpected character"),
            ("M 0 0 L 1 0 & E", "unexpected character"),
            # -- SVG commands a motion path does not have --
            ("M 0 0 Q 0.5 -0.5 1 0 E", "unsupported motion path command 'Q'"),
            ("M 0 0 H 1 E", "unsupported motion path command 'H'"),
            ("L 1 1 E", "must start with M"),
            ("0 0 L 1 1 E", "must start with M"),
            ("M 0 0 L 1 E", "'L' needs 2 coordinate"),
            ("M 0 0 C 1 1 2 2 E", "'C' needs 6 coordinate"),
            ("M 0 0 E L 1 1", "nothing can follow the end command"),
            ("M 0 0 L 1 1 Z 5", "expected a command after 'Z'"),
            ("   ", "non-empty OOXML path"),
            (None, "non-empty OOXML path"),
        ],
    )
    def it_rejects_a_custom_path_it_cannot_write_faithfully(self, slide_with_shape, path, message):
        slide, shape = slide_with_shape

        with pytest.raises(ValueError, match=message):
            MotionPath.custom(slide, shape, path)

        assert slide._element.find(qn("p:timing")) is None

    def it_puts_a_motion_path_in_the_attribute_and_nowhere_else(self, slide_with_shape):
        slide, shape = slide_with_shape

        MotionPath.custom(slide, shape, "M 0 0 L 0.5 0")

        (motion,) = slide._element.iter(qn("p:animMotion"))
        assert dict(motion.attrib) == {
            "origin": "parent",
            "path": "M 0 0 L 0.5 0 E",
            "pathEditMode": "relative",
            "rAng": "0",
        }

    @pytest.mark.parametrize("bad", [float("nan"), float("inf")])
    def it_rejects_a_line_to_nowhere(self, slide_with_shape, bad):
        slide, shape = slide_with_shape

        with pytest.raises(ValueError, match="finite"):
            MotionPath.line(slide, shape, bad, 0)

        assert slide._element.find(qn("p:timing")) is None

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

    def it_emits_an_arc_as_a_single_cubic_curve(self, slide_with_shape):
        # A motion path has no quadratic command (ISO/IEC 29500-1 §19.5.4
        # allows M, L, C, Z, E), so the parabola is written as a cubic.
        slide, shape = slide_with_shape
        MotionPath.arc(slide, shape, Inches(3), 0, height=0.5)
        path = _animMotion_paths(slide)[0]
        assert path.startswith("M 0 0 C ")
        assert path.endswith(" E")
        assert _path_commands(path) == ["M", "C", "E"]

    def it_keeps_the_arc_the_parabola_it_was_asked_for(self, slide_with_shape):
        # The cubic has to trace the quadratic curve it stands in for: at its
        # midpoint that curve sits half-way between the chord and the peak
        # control point, which lies `height` chord lengths off the chord.
        slide, shape = slide_with_shape
        prs = slide.part.package.presentation_part.presentation
        MotionPath.arc(slide, shape, Inches(3), 0, height=0.5)

        nums = [float(n) for n in _animMotion_paths(slide)[0].split()[4:10]]
        c1x, c1y, c2x, c2y, x, y = nums
        mid_x = (3 * c1x + 3 * c2x + x) / 8
        mid_y = (3 * c1y + 3 * c2y + y) / 8

        chord = float(Inches(3)) / float(prs.slide_width)
        assert x == pytest.approx(chord, abs=1e-6)
        assert y == 0
        assert mid_x == pytest.approx(chord / 2, abs=1e-6)
        assert mid_y == pytest.approx(-0.5 * chord / 2, abs=1e-6)

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
        # Parse "M 0 0 C c1x c1y c2x c2y nx ny E" for the control points.
        c_part = path.split("C", 1)[1].rsplit("E", 1)[0].strip().split()
        c1x, c1y, c2x, c2y, nx, ny = (float(n) for n in c_part)
        # Pure-vertical chord must still bend the path off the chord —
        # otherwise the arc degenerates to a straight line, the bug Codex
        # / Copilot flagged.  With `height=0.5` and chord direction +y,
        # both control points sit at non-zero x, on the same side.
        assert c1x != 0
        assert c2x == pytest.approx(c1x)
        # They are level with one third and two thirds of the chord.
        chord = float(Inches(3)) / float(
            slide.part.package.presentation_part.presentation.slide_height
        )
        assert (nx, ny) == (0, pytest.approx(chord, abs=1e-6))
        assert c1y == pytest.approx(chord / 3, abs=1e-6)
        assert c2y == pytest.approx(2 * chord / 3, abs=1e-6)


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

        node_types = [
            nt for nt in _ctn_node_types(slide) if nt != "tmRoot"
        ]
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
        assert "50" in cond_delays   # second: 50 user, untouched
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
        indices = sorted({
            rg.get("st") for rg in slide._element.iter(qn("p:pRg"))
        })
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
# Timing trees as PowerPoint writes them
# ---------------------------------------------------------------------------


def _powerpoint_effect(spid: int, ctn_id: int, node_type: str = "clickEffect") -> str:
    """One fade-in effect on shape `spid`, as PowerPoint writes it."""
    return (
        f'<p:par><p:cTn id="{ctn_id}" presetID="10" presetClass="entr" presetSubtype="0"'
        f' fill="hold" grpId="0" nodeType="{node_type}">'
        '<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
        f'<p:set><p:cBhvr><p:cTn id="{ctn_id + 1}" dur="1" fill="hold">'
        '<p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
        f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'
        "<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr>"
        '<p:to><p:strVal val="visible"/></p:to></p:set>'
        f'<p:animEffect transition="in" filter="fade"><p:cBhvr><p:cTn id="{ctn_id + 2}" dur="500"/>'
        f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect>'
        "</p:childTnLst></p:cTn></p:par>"
    )


def _powerpoint_click_step(spid: int, ctn_id: int) -> str:
    """A click step of the main sequence holding one batch with one effect on `spid`."""
    return (
        f'<p:par><p:cTn id="{ctn_id}" fill="hold">'
        '<p:stCondLst><p:cond delay="indefinite"/></p:stCondLst><p:childTnLst>'
        f'<p:par><p:cTn id="{ctn_id + 1}" fill="hold">'
        '<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
        + _powerpoint_effect(spid, ctn_id + 2)
        + "</p:childTnLst></p:cTn></p:par>"
        "</p:childTnLst></p:cTn></p:par>"
    )


def _powerpoint_timing(*spids: int, extra: str = "") -> str:
    """A `p:timing` holding one click-triggered fade per shape id, as PowerPoint nests it.

    The effects sit three levels down in the main sequence, and each animated
    shape has its entry in the build list. `extra` is markup for further time
    nodes directly under the root, after the main sequence.
    """
    steps = "".join(_powerpoint_click_step(spid, 3 + 5 * i) for i, spid in enumerate(spids))
    main_children = "<p:childTnLst>%s</p:childTnLst>" % steps if steps else ""
    builds = "".join('<p:bldP spid="%d" grpId="0" animBg="1"/>' % spid for spid in spids)
    return (
        '<p:timing xmlns:p="%s"><p:tnLst><p:par>'
        '<p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>'
        '<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq">'
        "%s</p:cTn>"
        '<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond>'
        "</p:prevCondLst>"
        '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond>'
        "</p:nextCondLst></p:seq>%s"
        "</p:childTnLst></p:cTn></p:par></p:tnLst>%s</p:timing>"
        % (P_NS, main_children, extra, "<p:bldLst>%s</p:bldLst>" % builds if builds else "")
    )


def _slide_with_shapes(count: int):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    shapes = [
        slide.shapes.add_shape(1, Inches(1 + i), Inches(1), Inches(1), Inches(1))
        for i in range(count)
    ]
    return slide, shapes


def _animated_slide(count: int, animated: int | None = None, extra: str = ""):
    """A slide of `count` shapes, the first `animated` of which PowerPoint animated."""
    from power_pptx.oxml import parse_xml

    slide, shapes = _slide_with_shapes(count)
    spids = [shape.shape_id for shape in shapes[: count if animated is None else animated]]
    slide._element._insert_timing(parse_xml(_powerpoint_timing(*spids, extra=extra)))
    return slide, shapes


def _timing(slide):
    return slide._element.find(qn("p:timing"))


def _targeted_ids(slide) -> list[int]:
    """Shape id of every `p:spTgt` in the slide's timing tree, in document order."""
    return [int(t.get("spid")) for t in slide._element.iter(qn("p:spTgt"))]


def _build_ids(slide) -> list[int]:
    return [int(b.get("spid")) for b in slide._element.iter(qn("p:bldP"))]


def _main_sequence_steps(slide) -> list:
    """The click-step `p:par` elements of the slide's main sequence."""
    return slide._element.xpath(
        "p:timing/p:tnLst/p:par/p:cTn/p:childTnLst/p:seq"
        "/p:cTn[@nodeType='mainSeq']/p:childTnLst/p:par"
    )


def _start_delays(node) -> list[str]:
    return [cond.get("delay") for cond in node.findall("p:cTn/p:stCondLst/p:cond", {"p": P_NS})]


class DescribePowerPointAuthoredTiming:
    """Effects nested in a main sequence are read, removed and purged like any other."""

    def it_lists_the_effects_of_a_main_sequence(self):
        slide, (a, b) = _animated_slide(2)

        entries = slide.animations.list()

        assert len(slide.animations) == 2
        assert bool(slide.animations) is True
        assert [e.shape_id for e in entries] == [a.shape_id, b.shape_id]
        assert [(e.kind, e.preset, e.trigger) for e in entries] == [
            ("entrance", "fade", Trigger.ON_CLICK)
        ] * 2
        assert [(e.duration, e.delay) for e in entries] == [(500, 0), (500, 0)]
        assert entries[0].shape.shape_id == a.shape_id

    def it_purges_the_effect_and_build_entry_of_a_deleted_shape(self):
        slide, (a, b) = _animated_slide(2)

        a.delete()

        assert _targeted_ids(slide) == [b.shape_id, b.shape_id]
        assert _build_ids(slide) == [b.shape_id]
        assert [e.shape_id for e in slide.animations] == [b.shape_id]
        # -- the click step that held nothing else went with the effect --
        assert len(_main_sequence_steps(slide)) == 1

    def it_drops_the_timing_tree_when_the_last_animated_shape_is_deleted(self):
        slide, (a,) = _animated_slide(1)

        a.delete()

        assert _timing(slide) is None

    def it_reports_how_many_timing_nodes_purge_orphans_removed(self):
        slide, (a, b, c) = _animated_slide(3)
        for shape in (a, c):
            shape._element.getparent().remove(shape._element)

        assert slide.animations.purge_orphans() == 2
        assert _targeted_ids(slide) == [b.shape_id, b.shape_id]
        assert _build_ids(slide) == [b.shape_id]
        assert slide.animations.purge_orphans() == 0

    def it_leaves_the_timing_alone_when_an_unanimated_shape_is_deleted(self):
        slide, (a, b) = _animated_slide(2, animated=1)
        before = _timing(slide).xml

        b.delete()

        assert _timing(slide).xml == before

    def it_purges_only_the_effect_of_the_deleted_shape_from_a_shared_batch(self):
        from power_pptx.oxml import parse_xml

        slide, (a, b) = _animated_slide(2, animated=1)
        batch = _main_sequence_steps(slide)[0].find("p:cTn/p:childTnLst/p:par", {"p": P_NS})
        batch.find("p:cTn/p:childTnLst", {"p": P_NS}).append(
            parse_xml(
                _powerpoint_effect(b.shape_id, 20, "withEffect").replace(
                    "<p:par>", '<p:par xmlns:p="%s">' % P_NS, 1
                )
            )
        )
        assert len(slide.animations) == 2

        b.delete()

        assert [e.shape_id for e in slide.animations] == [a.shape_id]
        assert len(_main_sequence_steps(slide)) == 1

    def it_clears_every_effect_of_a_main_sequence(self):
        slide, _ = _animated_slide(3)

        assert slide.animations.clear() == 3
        assert len(slide.animations) == 0
        assert _timing(slide) is None

    def it_removes_a_single_entry_of_a_main_sequence(self):
        slide, (a, b) = _animated_slide(2)

        slide.animations.list()[0].remove()

        assert [e.shape_id for e in slide.animations] == [b.shape_id]
        assert _build_ids(slide) == [b.shape_id]
        assert len(_main_sequence_steps(slide)) == 1

    def it_exposes_the_click_step_an_effect_has_to_itself_as_its_element(self):
        slide, _ = _animated_slide(2)

        entry = slide.animations.list()[1]

        assert entry.element is _main_sequence_steps(slide)[1]

    def it_removes_a_sequence_triggered_by_clicking_a_deleted_shape(self):
        slide, (a, b) = _slide_with_shapes(2)
        interactive = (
            '<p:seq concurrent="1" nextAc="seek"><p:cTn id="30" restart="whenNotActive"'
            ' fill="hold" evtFilter="cancelBubble" nodeType="interactiveSeq">'
            '<p:stCondLst><p:cond evt="onClick" delay="0">'
            f'<p:tgtEl><p:spTgt spid="{b.shape_id}"/></p:tgtEl></p:cond></p:stCondLst>'
            "<p:childTnLst>" + _powerpoint_click_step(a.shape_id, 31) + "</p:childTnLst></p:cTn>"
            '<p:nextCondLst><p:cond evt="onClick" delay="0">'
            f'<p:tgtEl><p:spTgt spid="{b.shape_id}"/></p:tgtEl></p:cond></p:nextCondLst></p:seq>'
        )
        from power_pptx.oxml import parse_xml

        slide._element._insert_timing(
            parse_xml(_powerpoint_timing(a.shape_id, extra=interactive))
        )
        assert len(slide.animations) == 2

        # -- deleting the trigger takes the whole sequence, effect on `a` included --
        b.delete()

        assert slide._element.xpath("p:timing//p:seq/p:cTn/@nodeType") == ["mainSeq"]
        assert [e.shape_id for e in slide.animations] == [a.shape_id]
        assert b.shape_id not in _targeted_ids(slide)

    def it_purges_the_copies_of_a_timing_tree_kept_in_alternate_content(self):
        # PowerPoint wraps the timing in mc:AlternateContent when an effect uses
        # a 2010+ feature, with the plain version of the same tree as fallback.
        from lxml import etree

        mc = "http://schemas.openxmlformats.org/markup-compatibility/2006"
        slide, (a, b) = _animated_slide(2)
        timing = _timing(slide)
        wrapper = etree.Element("{%s}AlternateContent" % mc, nsmap={"mc": mc})
        timing.addprevious(wrapper)
        etree.SubElement(wrapper, "{%s}Choice" % mc, Requires="p14").append(timing)
        etree.SubElement(wrapper, "{%s}Fallback" % mc).append(
            etree.fromstring(etree.tostring(timing))
        )

        a.delete()

        assert _targeted_ids(slide) == [b.shape_id] * 4
        assert _build_ids(slide) == [b.shape_id] * 2

        b.delete()

        assert list(slide._element.iter(qn("p:timing"))) == []
        assert slide._element.find("{%s}AlternateContent" % mc) is None


class DescribeAppendingToAMainSequence:
    """A new effect on a PowerPoint-animated slide joins its main sequence."""

    def it_adds_an_on_click_effect_as_a_new_click_step(self):
        slide, (a, b) = _animated_slide(2, animated=1)

        Entrance.fade(slide, b)

        steps = _main_sequence_steps(slide)
        assert len(steps) == 2
        assert _start_delays(steps[1]) == ["indefinite"]
        batches = steps[1].findall("p:cTn/p:childTnLst/p:par", {"p": P_NS})
        assert [_start_delays(batch) for batch in batches] == [["0"]]
        # -- nothing is left outside the main sequence --
        root = slide._element.xpath("p:timing/p:tnLst/p:par/p:cTn/p:childTnLst/*")
        assert [child.tag for child in root] == [qn("p:seq")]
        assert [(e.shape_id, e.trigger) for e in slide.animations] == [
            (a.shape_id, Trigger.ON_CLICK),
            (b.shape_id, Trigger.ON_CLICK),
        ]

    def it_lets_a_with_previous_effect_join_the_last_batch(self):
        slide, (a, b) = _animated_slide(2, animated=1)

        Entrance.fade(slide, b, trigger=Trigger.WITH_PREVIOUS)

        steps = _main_sequence_steps(slide)
        assert len(steps) == 1
        batches = steps[0].findall("p:cTn/p:childTnLst/p:par", {"p": P_NS})
        assert len(batches) == 1
        effects = batches[0].findall("p:cTn/p:childTnLst/p:par/p:cTn", {"p": P_NS})
        assert [ctn.get("nodeType") for ctn in effects] == ["clickEffect", "withEffect"]

    def it_starts_an_after_previous_effect_once_the_last_batch_is_over(self):
        slide, (a, b, c) = _animated_slide(3, animated=1)

        Entrance.fade(slide, b, trigger=Trigger.AFTER_PREVIOUS, duration=700)
        Entrance.fade(slide, c, trigger=Trigger.AFTER_PREVIOUS, delay=100)

        steps = _main_sequence_steps(slide)
        assert len(steps) == 1
        batches = steps[0].findall("p:cTn/p:childTnLst/p:par", {"p": P_NS})
        # -- the existing fade runs 500 ms; the one added after it 700 ms more --
        assert [_start_delays(batch) for batch in batches] == [["0"], ["500"], ["1200"]]
        assert [e.delay for e in slide.animations] == [0, 0, 100]

    def it_sets_a_leading_effect_that_waits_for_no_click_off_with_the_sequence(self):
        slide, (a,) = _animated_slide(1, animated=0)

        Entrance.fade(slide, a, trigger=Trigger.AFTER_PREVIOUS)

        (step,) = _main_sequence_steps(slide)
        conds = step.findall("p:cTn/p:stCondLst/p:cond", {"p": P_NS})
        assert [cond.get("delay") for cond in conds] == ["indefinite", "0"]
        assert conds[1].get("evt") == "onBegin"
        # -- "2" is the id of the main sequence's own time node --
        assert conds[1].find(qn("p:tn")).get("val") == "2"

    def it_gives_every_new_time_node_an_id_of_its_own(self):
        slide, (a, b, c) = _animated_slide(3, animated=1)

        Entrance.fade(slide, b)
        Entrance.fade(slide, c, trigger=Trigger.WITH_PREVIOUS)

        ids = [ctn.get("id") for ctn in slide._element.iter(qn("p:cTn"))]
        assert len(ids) == len(set(ids))

    def it_applies_easing_to_an_effect_added_to_the_main_sequence(self):
        slide, (a, b) = _animated_slide(2, animated=1)

        slide.animations.add_entrance("fade", b, easing="ease_in_out")

        (ctn,) = [c for c in slide._element.iter(qn("p:cTn")) if c.get("accel") is not None]
        assert (ctn.get("accel"), ctn.get("decel")) == ("30000", "30000")

    def but_a_slide_without_a_main_sequence_keeps_its_effects_under_the_root(self):
        slide, (a,) = _slide_with_shapes(1)

        Entrance.fade(slide, a)

        assert _main_sequence_steps(slide) == []
        assert len(slide._element.xpath("p:timing/p:tnLst/p:par/p:cTn/p:childTnLst/p:par")) == 1


class DescribeMediaNodeCleanup:
    """The `p:video` node behind a movie's play controls goes when the movie does."""

    def _add_movie(self, slide):
        import os

        movie_path = os.path.join(os.path.dirname(__file__), "test_files", "dummy.mp4")
        return slide.shapes.add_movie(movie_path, Inches(1), Inches(3), Inches(3), Inches(2))

    def it_removes_the_video_node_of_a_deleted_movie(self):
        slide, (a,) = _slide_with_shapes(1)
        movie = self._add_movie(slide)
        Entrance.fade(slide, a)
        assert len(list(slide._element.iter(qn("p:video")))) == 1

        movie.delete()

        assert list(slide._element.iter(qn("p:video"))) == []
        assert set(_targeted_ids(slide)) == {a.shape_id}
        assert len(slide.animations) == 1

    def it_drops_the_timing_tree_a_deleted_movie_leaves_empty(self):
        slide, _ = _slide_with_shapes(0)
        movie = self._add_movie(slide)

        movie.delete()

        assert _timing(slide) is None

    def but_clear_keeps_the_video_node_of_a_movie_still_on_the_slide(self):
        slide, (a,) = _slide_with_shapes(1)
        movie = self._add_movie(slide)
        Entrance.fade(slide, a)

        assert slide.animations.clear() == 1
        assert _targeted_ids(slide) == [movie.shape_id]


# ---------------------------------------------------------------------------
# Timing values
# ---------------------------------------------------------------------------


def _time_attrs(slide) -> list[str]:
    """Every `dur` and `delay` attribute value in the slide's timing tree."""
    values = [c.get("dur") for c in slide._element.iter(qn("p:cTn")) if c.get("dur")]
    values += [c.get("delay") for c in slide._element.iter(qn("p:cond")) if c.get("delay")]
    return values


def _add_entrance(slide, shape, **kwargs):
    slide.animations.add_entrance("fade", shape, **kwargs)


def _add_exit(slide, shape, **kwargs):
    slide.animations.add_exit("fade", shape, **kwargs)


def _add_emphasis(slide, shape, **kwargs):
    slide.animations.add_emphasis("pulse", shape, **kwargs)


def _add_motion(slide, shape, **kwargs):
    slide.animations.add_motion(shape, "M 0 0 L 0.5 0 E", **kwargs)


_ADDERS = pytest.mark.parametrize(
    "add",
    [_add_entrance, _add_exit, _add_emphasis, _add_motion],
    ids=["entrance", "exit", "emphasis", "motion"],
)


class DescribeTimingValueChecks:
    """`dur` and `delay` are `ST_TLTime`: a non-negative integer or "indefinite"."""

    @_ADDERS
    def it_writes_a_float_duration_and_delay_as_whole_milliseconds(self, slide_with_shape, add):
        slide, shape = slide_with_shape

        # -- what ordinary arithmetic hands over: 500.0 and 200.00000000000003 --
        add(slide, shape, duration=1500 / 3, delay=0.2 * 1000)

        values = _time_attrs(slide)
        assert {"500", "200"} <= set(values)
        assert all(v == "indefinite" or v.isdigit() for v in values), values
        entry = slide.animations.list()[0]
        assert (entry.duration, entry.delay) == (500, 200)

    @_ADDERS
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"duration": -1},
            {"delay": -5},
            {"duration": 2**32},
            {"delay": 2**32},
            {"duration": float("nan")},
            {"delay": float("inf")},
        ],
    )
    def it_rejects_a_time_the_attribute_cannot_hold(self, slide_with_shape, add, kwargs):
        slide, shape = slide_with_shape

        with pytest.raises(ValueError, match=next(iter(kwargs))):
            add(slide, shape, **kwargs)

        # -- and nothing was written on the way to finding out --
        assert slide._element.find(qn("p:timing")) is None

    @_ADDERS
    @pytest.mark.parametrize("kwargs", [{"duration": "500"}, {"delay": None}, {"duration": True}])
    def it_rejects_a_time_that_is_not_a_number(self, slide_with_shape, add, kwargs):
        slide, shape = slide_with_shape

        with pytest.raises(TypeError, match=next(iter(kwargs))):
            add(slide, shape, **kwargs)

    def it_accepts_the_largest_time_the_attribute_holds(self, slide_with_shape):
        slide, shape = slide_with_shape

        Entrance.fade(slide, shape, duration=2**32 - 1)

        assert slide.animations.list()[0].duration == 2**32 - 1

    def it_rounds_the_delay_of_a_sequence_or_group(self, slide_with_shape):
        slide, shape = slide_with_shape

        with slide.animations.sequence(delay=0.3 * 1000):
            Entrance.fade(slide, shape)
        with slide.animations.group(delay=250.4):
            Entrance.fade(slide, shape)

        assert [e.delay for e in slide.animations] == [300, 250]
        assert all(v == "indefinite" or v.isdigit() for v in _time_attrs(slide))

    @pytest.mark.parametrize("block", ["sequence", "group"])
    def it_rejects_a_negative_block_delay(self, slide_with_shape, block):
        slide, _ = slide_with_shape

        with pytest.raises(ValueError, match="delay"):
            with getattr(slide.animations, block)(delay=-1):
                pass

    def it_rejects_a_delay_that_only_overflows_once_the_block_delay_is_added(
        self, slide_with_shape
    ):
        slide, shape = slide_with_shape

        with pytest.raises(ValueError, match="delay"):
            with slide.animations.sequence(delay=2**32 - 1):
                Entrance.fade(slide, shape, delay=1)

        assert slide._element.find(qn("p:timing")) is None

    def it_leaves_no_empty_timing_tree_behind_when_an_easing_is_refused(self, slide_with_shape):
        # The skeleton used to be created first, so a refused effect left a
        # `p:childTnLst` with nothing in it: a schema violation in the saved deck.
        slide, shape = slide_with_shape

        with pytest.raises(ValueError, match="easing"):
            slide.animations.add_entrance("fade", shape, easing="bouncy")

        assert slide._element.find(qn("p:timing")) is None

    def it_checks_the_timing_of_a_typewriter_cascade(self, slide_with_shape):
        slide, shape = slide_with_shape

        with pytest.raises(ValueError, match="delay_between_ms"):
            slide.animations.typewriter([shape, shape], delay_between_ms=-200)

        slide.animations.typewriter([shape, shape], delay_between_ms=400 / 2, duration=900 / 3)

        assert [(e.delay, e.duration) for e in slide.animations] == [(0, 300), (200, 300)]

    @pytest.mark.parametrize(
        ("degrees", "by"),
        [
            (360, "21600000"),
            (-720, "-43200000"),
            (0.5, "30000"),
            (0.00001, "1"),
            (35791, "2147460000"),
        ],
    )
    def it_writes_a_spin_angle_in_60000ths_of_a_degree(self, slide_with_shape, degrees, by):
        slide, shape = slide_with_shape

        Emphasis.spin(slide, shape, degrees=degrees)

        (rot,) = slide._element.iter(qn("p:animRot"))
        assert rot.get("by") == by

    @pytest.mark.parametrize("degrees", [1e6, -1e6, 35792, float("nan"), float("inf")])
    def it_rejects_a_spin_angle_the_attribute_cannot_hold(self, slide_with_shape, degrees):
        slide, shape = slide_with_shape

        with pytest.raises(ValueError, match="degrees"):
            Emphasis.spin(slide, shape, degrees=degrees)

        assert slide._element.find(qn("p:timing")) is None

    def it_rejects_a_spin_angle_that_is_not_a_number(self, slide_with_shape):
        slide, shape = slide_with_shape

        with pytest.raises(TypeError, match="degrees"):
            Emphasis.spin(slide, shape, degrees="360")


# ---------------------------------------------------------------------------
# Preset identity
# ---------------------------------------------------------------------------
#
# The (presetID, presetSubtype) pairs below are the ones LibreOffice's PPTX
# import and export give for each effect: a deck of every preset was converted
# with LibreOffice, and LibreOffice's own effect definitions were exported to
# PPTX by it, to read the numbers both ways.

_PRESET_IDENTITIES = [
    ("entrance", "appear", {}, ("entr", "1", "0")),
    ("entrance", "fade", {}, ("entr", "10", "0")),
    ("entrance", "fly_in", {}, ("entr", "2", "4")),
    ("entrance", "fly_in", {"direction": "bottom"}, ("entr", "2", "4")),
    ("entrance", "fly_in", {"direction": "top"}, ("entr", "2", "1")),
    ("entrance", "fly_in", {"direction": "left"}, ("entr", "2", "8")),
    ("entrance", "fly_in", {"direction": "right"}, ("entr", "2", "2")),
    ("entrance", "float_in", {}, ("entr", "42", "0")),
    ("entrance", "wipe", {}, ("entr", "22", "8")),
    ("entrance", "zoom", {}, ("entr", "23", "16")),
    ("entrance", "wheel", {}, ("entr", "21", "1")),
    ("entrance", "random_bars", {}, ("entr", "14", "5")),
    ("exit", "disappear", {}, ("exit", "1", "0")),
    ("exit", "fade", {}, ("exit", "10", "0")),
    ("exit", "fly_out", {}, ("exit", "2", "4")),
    ("exit", "fly_out", {"direction": "top"}, ("exit", "2", "1")),
    ("exit", "fly_out", {"direction": "left"}, ("exit", "2", "8")),
    ("exit", "fly_out", {"direction": "right"}, ("exit", "2", "2")),
    ("exit", "float_out", {}, ("exit", "42", "0")),
    ("exit", "wipe", {}, ("exit", "22", "8")),
    ("exit", "zoom", {}, ("exit", "23", "32")),
    ("exit", "wheel", {}, ("exit", "21", "1")),
    ("exit", "random_bars", {}, ("exit", "14", "5")),
    ("emphasis", "pulse", {}, ("emph", "26", "0")),
    ("emphasis", "spin", {}, ("emph", "8", "0")),
    ("emphasis", "teeter", {}, ("emph", "32", "0")),
]

_PRESET_IDS = [
    "%s-%s-%s" % (kind, preset, kwargs.get("direction", "default"))
    for kind, preset, kwargs, _ in _PRESET_IDENTITIES
]

# -- the filters LibreOffice recognises; any other name plays as no effect --
_RECOGNISED_FILTERS = {"fade", "wipe(left)", "wheel(1)", "randombar(vertical)"}


def _effect_ctn(slide):
    (ctn,) = [c for c in slide._element.iter(qn("p:cTn")) if c.get("presetClass")]
    return ctn


class DescribePresetIdentity:
    @pytest.mark.parametrize(
        ("kind", "preset", "kwargs", "identity"),
        _PRESET_IDENTITIES,
        ids=_PRESET_IDS,
    )
    def it_names_each_preset_by_the_number_consumers_know_it_by(
        self, slide_with_shape, kind, preset, kwargs, identity
    ):
        slide, shape = slide_with_shape

        slide.animations.add(kind, preset, shape, **kwargs)

        ctn = _effect_ctn(slide)
        assert (ctn.get("presetClass"), ctn.get("presetID"), ctn.get("presetSubtype")) == identity

    @pytest.mark.parametrize(
        ("kind", "preset", "kwargs", "identity"),
        _PRESET_IDENTITIES,
        ids=_PRESET_IDS,
    )
    def it_reads_each_preset_back_by_its_name(
        self, slide_with_shape, kind, preset, kwargs, identity
    ):
        slide, shape = slide_with_shape

        slide.animations.add(kind, preset, shape, **kwargs)

        (entry,) = slide.animations
        assert (entry.kind, entry.preset) == (kind, preset)

    @pytest.mark.parametrize(
        ("preset_class", "preset_id", "subtype", "expected"),
        [
            # -- as PowerPoint numbers them, whoever wrote the effect --
            ("entr", "22", "1", "wipe"),
            ("entr", "2", "9", "fly_in"),
            ("exit", "23", "16", "zoom"),
            ("emph", "8", "0", "spin"),
            # -- the numbers earlier releases wrote stand for other effects --
            ("entr", "8", "2", None),  # Diamond
            ("entr", "12", "1", None),  # Peek In
            ("emph", "13", "0", None),
        ],
    )
    def it_reads_a_preset_by_its_number_whatever_wrote_it(
        self, slide_with_shape, preset_class, preset_id, subtype, expected
    ):
        slide, shape = slide_with_shape
        Entrance.fade(slide, shape)
        ctn = _effect_ctn(slide)
        ctn.set("presetClass", preset_class)
        ctn.set("presetID", preset_id)
        ctn.set("presetSubtype", subtype)

        assert slide.animations.list()[0].preset == expected

    @pytest.mark.parametrize("kind", ["entrance", "exit"])
    @pytest.mark.parametrize("preset", ["fade", "wipe", "wheel", "random_bars"])
    def it_only_writes_filters_that_are_recognised(self, slide_with_shape, kind, preset):
        slide, shape = slide_with_shape

        slide.animations.add(kind, preset, shape)

        filters = {e.get("filter") for e in slide._element.iter(qn("p:animEffect"))}
        assert filters
        assert filters <= _RECOGNISED_FILTERS

    @pytest.mark.parametrize(
        ("kind", "values"),
        [
            ("entrance", [("0", "#ppt_w"), ("0", "#ppt_h")]),
            ("exit", [("#ppt_w", "0"), ("#ppt_h", "0")]),
        ],
    )
    def it_zooms_by_animating_the_width_and_height(self, slide_with_shape, kind, values):
        # There is no zoom filter: "zoom(dir=in)" played as no effect at all.
        slide, shape = slide_with_shape

        slide.animations.add(kind, "zoom", shape)

        assert list(slide._element.iter(qn("p:animEffect"))) == []
        anims = list(slide._element.iter(qn("p:anim")))
        assert [a.find("p:cBhvr/p:attrNameLst/p:attrName", {"p": P_NS}).text for a in anims] == [
            "ppt_w",
            "ppt_h",
        ]
        assert [
            tuple(v.get("val") for v in a.iter(qn("p:strVal"))) for a in anims
        ] == values
        assert {a.find("p:cBhvr/p:cTn", {"p": P_NS}).get("dur") for a in anims} == {"500"}

    def it_zooms_a_paragraph_at_a_time(self, slide_with_shape):
        slide, _ = slide_with_shape
        box = slide.shapes.add_textbox(Inches(1), Inches(3), Inches(4), Inches(1))
        box.text_frame.text = "one"
        box.text_frame.add_paragraph().text = "two"

        slide.animations.add_entrance("zoom", box, by_paragraph=True)

        targets = [
            a.find("p:cBhvr/p:tgtEl/p:spTgt/p:txEl/p:pRg", {"p": P_NS}).get("st")
            for a in slide._element.iter(qn("p:anim"))
        ]
        assert targets == ["0", "0", "1", "1"]


class DescribeExitTiming:
    """An exit hides its shape once it has played, not before."""

    def _hide_delays(self, slide):
        delays = []
        for set_ in slide._element.iter(qn("p:set")):
            if set_.find("p:to/p:strVal", {"p": P_NS}).get("val") != "hidden":
                continue
            cond = set_.find("p:cBhvr/p:cTn/p:stCondLst/p:cond", {"p": P_NS})
            delays.append(None if cond is None else cond.get("delay"))
        return delays

    @pytest.mark.parametrize(
        "preset", ["fade", "fly_out", "float_out", "wipe", "zoom", "wheel", "random_bars"]
    )
    def it_hides_the_shape_in_the_last_millisecond_of_its_exit(self, slide_with_shape, preset):
        # Hidden at the start, as it used to be, the shape vanished at once
        # and the fade, wipe or flight had nothing to show.
        slide, shape = slide_with_shape

        slide.animations.add_exit(preset, shape, duration=800)

        assert self._hide_delays(slide) == ["799"]

    def but_disappear_hides_the_shape_at_once(self, slide_with_shape):
        slide, shape = slide_with_shape

        Exit.disappear(slide, shape)

        assert self._hide_delays(slide) == [None]

    def and_an_exit_that_takes_no_time_hides_the_shape_at_once(self, slide_with_shape):
        slide, shape = slide_with_shape

        Exit.fade(slide, shape, duration=0)

        assert self._hide_delays(slide) == [None]

    def it_does_not_count_the_hiding_step_in_the_effect_duration(self, slide_with_shape):
        slide, shape = slide_with_shape

        Exit.fade(slide, shape, duration=800)

        assert slide.animations.list()[0].duration == 800
