"""Unit-test suite for the slide-size limits, `fit_slide_size` and `Presentation.set_slide_size`."""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx.util import (
    MAX_SLIDE_SIZE,
    MIN_SLIDE_SIZE,
    Cm,
    Emu,
    Inches,
    Length,
    Mm,
    Pt,
    SlideSize,
    fit_slide_size,
)


class DescribeSlideSizeLimits(object):
    """`MIN_SLIDE_SIZE` and `MAX_SLIDE_SIZE` are the public form of PowerPoint's limits."""

    def it_exposes_the_limits_as_lengths(self):
        assert isinstance(MIN_SLIDE_SIZE, Length)
        assert isinstance(MAX_SLIDE_SIZE, Length)
        assert MIN_SLIDE_SIZE == Inches(1) == 914400
        assert MAX_SLIDE_SIZE == Inches(56) == 51206400
        assert (MIN_SLIDE_SIZE.inches, MAX_SLIDE_SIZE.inches) == (1.0, 56.0)

    def it_matches_the_limits_the_setters_enforce(self):
        prs = Presentation()

        prs.slide_width, prs.slide_height = MIN_SLIDE_SIZE, MAX_SLIDE_SIZE
        assert (prs.slide_width, prs.slide_height) == (MIN_SLIDE_SIZE, MAX_SLIDE_SIZE)

        with pytest.raises(ValueError):
            prs.slide_width = MIN_SLIDE_SIZE - 1
        with pytest.raises(ValueError):
            prs.slide_height = MAX_SLIDE_SIZE + 1


class Describe_fit_slide_size(object):
    """`fit_slide_size` brings a size inside the limits without changing its shape."""

    def it_returns_a_SlideSize_that_unpacks_as_width_height_scale(self):
        size = fit_slide_size(Inches(80), Inches(11.25))

        assert isinstance(size, SlideSize)
        width, height, scale = size
        assert (width, height, scale) == (size.width, size.height, size.scale)
        assert isinstance(width, Length)
        assert isinstance(height, Length)
        assert isinstance(scale, float)

    def it_scales_a_video_wall_down_to_the_largest_slide_of_the_same_shape(self):
        # -- 7680 x 1080 px at 96 px per inch, the case in issue #56 --
        size = fit_slide_size(Inches(7680 / 96), Inches(1080 / 96))

        assert size.width == MAX_SLIDE_SIZE
        assert size.height == Inches(7.875)
        assert size.scale == pytest.approx(0.7)

    @pytest.mark.parametrize(
        ("width", "height"),
        [
            (Inches(10), Inches(7.5)),
            (Inches(13.333), Inches(7.5)),
            (Inches(1), Inches(1)),
            (Inches(56), Inches(56)),
            (Inches(56), Inches(1)),
            (Inches(1), Inches(56)),
            (Cm(33.867), Cm(19.05)),
        ],
    )
    def it_leaves_a_size_that_already_fits_alone(self, width, height):
        size = fit_slide_size(width, height)

        assert (size.width, size.height) == (width, height)
        assert size.scale == 1.0

    def and_it_does_not_enlarge_one_just_because_there_is_room(self):
        assert fit_slide_size(Inches(2), Inches(1.5)) == (Inches(2), Inches(1.5), 1.0)

    @pytest.mark.parametrize(
        ("width", "height", "expected_width", "expected_height", "expected_scale"),
        [
            # -- wide: the width lands on the maximum --
            (Inches(80), Inches(11.25), Inches(56), Inches(7.875), 0.7),
            (Inches(112), Inches(63), Inches(56), Inches(31.5), 0.5),
            (Inches(57), Inches(28.5), Inches(56), Inches(28), 56 / 57),
            # -- tall: the height does --
            (Inches(11.25), Inches(80), Inches(7.875), Inches(56), 0.7),
            (Inches(40), Inches(70), Inches(32), Inches(56), 0.8),
            # -- only one side over --
            (Inches(60), Inches(30), Inches(56), Inches(28), 56 / 60),
            # -- square --
            (Inches(100), Inches(100), Inches(56), Inches(56), 0.56),
            # -- other units --
            (Mm(2844.8), Mm(1422.4), Inches(56), Inches(28), 0.5),
        ],
    )
    def it_scales_a_size_that_is_too_large_down_to_the_maximum(
        self, width, height, expected_width, expected_height, expected_scale
    ):
        size = fit_slide_size(width, height)

        assert (size.width, size.height) == (expected_width, expected_height)
        assert size.scale == pytest.approx(expected_scale)
        assert max(size.width, size.height) == MAX_SLIDE_SIZE

    @pytest.mark.parametrize(
        ("width", "height", "expected_width", "expected_height", "expected_scale"),
        [
            (Inches(0.5), Inches(20), Inches(1), Inches(40), 2.0),
            (Inches(20), Inches(0.5), Inches(40), Inches(1), 2.0),
            (Inches(0.25), Inches(0.25), Inches(1), Inches(1), 4.0),
            (Pt(36), Pt(72), Inches(1), Inches(2), 2.0),
        ],
    )
    def it_scales_a_size_that_is_too_small_up_to_the_minimum(
        self, width, height, expected_width, expected_height, expected_scale
    ):
        size = fit_slide_size(width, height)

        assert (size.width, size.height) == (expected_width, expected_height)
        assert size.scale == pytest.approx(expected_scale)
        assert min(size.width, size.height) == MIN_SLIDE_SIZE

    @pytest.mark.parametrize(
        ("width", "height"),
        [
            (Inches(80), Inches(11.25)),
            (Inches(11.25), Inches(80)),
            (Inches(123.4), Inches(45.6)),
            (Emu(987654321), Emu(123456789)),
            (Inches(0.3), Inches(7.77)),
            (Inches(1000), Inches(18)),
            (Emu(51206401), Emu(914401)),
        ],
    )
    def it_keeps_the_aspect_ratio_and_stays_inside_the_limits(self, width, height):
        size = fit_slide_size(width, height)

        assert MIN_SLIDE_SIZE <= size.width <= MAX_SLIDE_SIZE
        assert MIN_SLIDE_SIZE <= size.height <= MAX_SLIDE_SIZE
        # -- each side is the requested one times `scale`, to within the half
        # -- EMU that rounding to a whole number can cost --
        assert abs(size.width - width * size.scale) <= 0.5
        assert abs(size.height - height * size.scale) <= 0.5
        assert size.width / size.height == pytest.approx(width / height, rel=1e-6)

    def it_accepts_the_float_result_of_arithmetic_on_lengths(self):
        size = fit_slide_size(Inches(400) / 3, Inches(100) * 0.75)

        assert size == (Inches(56), Inches(31.5), pytest.approx(0.42))
        assert type(size.width) is not float
        assert type(size.height) is not float

    def it_fits_a_shape_of_exactly_56_to_1_without_losing_it_to_rounding(self):
        assert fit_slide_size(Inches(56), Inches(1)).scale == 1.0
        assert fit_slide_size(Inches(560), Inches(10)) == (
            MAX_SLIDE_SIZE,
            MIN_SLIDE_SIZE,
            pytest.approx(0.1),
        )
        assert fit_slide_size(Emu(56 * 7), Emu(7)) == (
            MAX_SLIDE_SIZE,
            MIN_SLIDE_SIZE,
            pytest.approx(914400 / 7),
        )

    @pytest.mark.parametrize(
        ("width", "height"),
        [
            (Inches(80), Inches(1)),
            (Inches(1), Inches(80)),
            (Inches(57), Inches(1)),
            (Emu(51206401), Emu(914400)),
            (Inches(7680 / 96), Inches(100 / 96)),
        ],
    )
    def but_it_raises_when_no_slide_has_those_proportions(self, width, height):
        with pytest.raises(ValueError, match="most elongated one is 56:1") as excinfo:
            fit_slide_size(width, height)
        # -- the message states the limits in inches --
        assert "between 1 and 56 inches" in str(excinfo.value)

    @pytest.mark.parametrize(
        ("width", "height"), [(0, Inches(1)), (Inches(1), 0), (-Inches(10), Inches(5)), (0, 0)]
    )
    def it_rejects_a_size_that_is_not_positive(self, width, height):
        with pytest.raises(ValueError, match="must be positive"):
            fit_slide_size(width, height)

    @pytest.mark.parametrize(
        ("width", "height"),
        [("10", Inches(1)), (Inches(1), None), (None, None), (True, Inches(1)), (float("nan"), 1)],
    )
    def it_rejects_a_size_that_is_not_a_length(self, width, height):
        with pytest.raises(TypeError):
            fit_slide_size(width, height)


class DescribePresentation_set_slide_size(object):
    """`Presentation.set_slide_size` sets both dimensions, optionally fitting them."""

    def it_sets_the_width_and_height_in_one_call(self):
        prs = Presentation()

        size = prs.set_slide_size(Inches(13.333), Inches(7.5))

        assert (prs.slide_width, prs.slide_height) == (Inches(13.333), Inches(7.5))
        assert isinstance(size, SlideSize)
        assert size == (Inches(13.333), Inches(7.5), 1.0)
        sldSz = prs._element.sldSz
        assert (sldSz.get("cx"), sldSz.get("cy")) == ("12191695", "6858000")

    def it_accepts_the_limits_themselves(self):
        prs = Presentation()
        assert prs.set_slide_size(MAX_SLIDE_SIZE, MIN_SLIDE_SIZE) == (
            MAX_SLIDE_SIZE,
            MIN_SLIDE_SIZE,
            1.0,
        )
        assert (prs.slide_width, prs.slide_height) == (MAX_SLIDE_SIZE, MIN_SLIDE_SIZE)

    def it_accepts_the_float_result_of_arithmetic_on_lengths(self):
        prs = Presentation()

        prs.set_slide_size(Inches(40) / 3, Inches(15) / 2)

        assert (prs.slide_width, prs.slide_height) == (12192000, 6858000)
        sldSz = prs._element.sldSz
        assert (sldSz.get("cx"), sldSz.get("cy")) == ("12192000", "6858000")

    @pytest.mark.parametrize(
        ("width", "height", "culprit", "got"),
        [
            (Inches(80), Inches(11.25), "slide width", "got 80 inches (73152000 EMU)"),
            (Inches(13.333), Inches(80), "slide height", "got 80 inches (73152000 EMU)"),
            (Inches(0.5), Inches(7.5), "slide width", "got 0.5 inches (457200 EMU)"),
            (Inches(10), Emu(100), "slide height", "(100 EMU)"),
        ],
    )
    def it_refuses_a_size_outside_the_limits_and_says_what_they_are(
        self, width, height, culprit, got
    ):
        prs = Presentation()
        before = (prs.slide_width, prs.slide_height)

        with pytest.raises(ValueError) as excinfo:
            prs.set_slide_size(width, height)

        message = str(excinfo.value)
        assert message.startswith(
            culprit + " must be between 1 and 56 inches (914400 to 51206400 EMU)"
        )
        assert got in message
        assert "fit=True" in message
        # -- and neither dimension was changed, even when only the second was at fault --
        assert (prs.slide_width, prs.slide_height) == before

    def it_can_fit_a_size_outside_the_limits_and_reports_the_scale(self):
        prs = Presentation()

        size = prs.set_slide_size(Inches(7680 / 96), Inches(1080 / 96), fit=True)

        assert size == (Inches(56), Inches(7.875), pytest.approx(0.7))
        assert (prs.slide_width, prs.slide_height) == (Inches(56), Inches(7.875))
        # -- the scale puts content laid out in wall pixels in the right place --
        px = size.scale * Inches(1) / 96
        assert 7680 * px == pytest.approx(prs.slide_width)
        assert 1080 * px == pytest.approx(prs.slide_height)

    def it_reports_a_scale_of_one_when_fitting_changes_nothing(self):
        prs = Presentation()
        assert prs.set_slide_size(Inches(13.333), Inches(7.5), fit=True) == (
            Inches(13.333),
            Inches(7.5),
            1.0,
        )

    def it_can_fit_a_size_that_is_too_small(self):
        prs = Presentation()

        size = prs.set_slide_size(Inches(0.5), Inches(2), fit=True)

        assert size == (Inches(1), Inches(4), pytest.approx(2.0))
        assert (prs.slide_width, prs.slide_height) == (Inches(1), Inches(4))

    def it_leaves_the_size_alone_when_fitting_is_impossible(self):
        prs = Presentation()
        before = (prs.slide_width, prs.slide_height)

        with pytest.raises(ValueError, match="most elongated one is 56:1"):
            prs.set_slide_size(Inches(100), Inches(1), fit=True)

        assert (prs.slide_width, prs.slide_height) == before

    def it_takes_fit_as_a_keyword_only(self):
        prs = Presentation()
        with pytest.raises(TypeError):
            prs.set_slide_size(Inches(80), Inches(11.25), True)  # pyright: ignore[reportCallIssue]

    @pytest.mark.parametrize(
        ("width", "height"), [(None, Inches(5)), (Inches(5), None), ("10in", Inches(5))]
    )
    def it_rejects_a_size_that_is_not_a_length(self, width, height):
        prs = Presentation()
        before = (prs.slide_width, prs.slide_height)

        with pytest.raises(TypeError):
            prs.set_slide_size(width, height)

        assert (prs.slide_width, prs.slide_height) == before

    def it_adds_the_sldSz_element_to_a_presentation_that_has_none(self):
        prs = Presentation()
        prs._element.remove(prs._element.sldSz)
        assert prs.slide_width is None

        prs.set_slide_size(Inches(16), Inches(9))

        assert (prs.slide_width, prs.slide_height) == (Inches(16), Inches(9))
        # -- p:sldSz belongs between p:sldIdLst and p:notesSz --
        tags = [child.tag.rpartition("}")[2] for child in prs._element]
        assert tags.index("sldSz") == tags.index("notesSz") - 1
