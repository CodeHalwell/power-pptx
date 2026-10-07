# pyright: reportPrivateUsage=false

"""Unit-test suite for `power_pptx.text.layout` module."""

from __future__ import annotations

import os
import re
import time

import pytest
from PIL import ImageFont

from power_pptx.text.layout import (
    TextFitter,
    _BinarySearchTree,
    _Fonts,
    _line_height,
    _split_into_segments,
)
from power_pptx.util import Inches

from ..unitutil.file import testfile
from ..unitutil.mock import (
    ANY,
    call,
    class_mock,
    function_mock,
    initializer_mock,
    method_mock,
    property_mock,
)


class DescribeTextFitter(object):
    """Unit-test suite for `power_pptx.text.layout.TextFitter` object."""

    def it_can_determine_the_best_fit_font_size(self, request):
        _init_ = initializer_mock(request, TextFitter)
        _best_fit_font_size_ = method_mock(
            request, TextFitter, "_best_fit_font_size", return_value=36
        )
        extents, max_size = (19, 20), 42

        font_size = TextFitter.best_fit_font_size("Foobar", extents, max_size, "foobar.ttf")

        _init_.assert_called_once_with("Foobar", extents, "foobar.ttf")
        _best_fit_font_size_.assert_called_once_with(ANY, max_size)
        assert font_size == 36

    def it_splits_its_text_into_segments_at_each_forced_line_break(self):
        text_fitter = TextFitter("foo bar\nbaz\v\nquux", (None, None), None)

        assert text_fitter._segments == (("foo", "bar"), ("baz",), (), ("quux",))

    def it_finds_best_fit_font_size_to_help_best_fit(self, _best_fit_fixture):
        text_fitter, max_size, _BinarySearchTree_ = _best_fit_fixture[:3]
        sizes_, predicate_, font_size_ = _best_fit_fixture[3:]

        font_size = text_fitter._best_fit_font_size(max_size)

        _BinarySearchTree_.from_ordered_sequence.assert_called_once_with(range(1, max_size + 1))
        sizes_.find_max.assert_called_once_with(predicate_)
        assert font_size is font_size_

    @pytest.mark.parametrize("max_size", [0, -3, 0.9])
    def but_it_refuses_a_max_size_below_one_point(self, max_size, _BinarySearchTree_):
        text_fitter = TextFitter("", (None, None), None)

        with pytest.raises(ValueError, match="max_size must be at least 1 point"):
            text_fitter._best_fit_font_size(max_size)

        _BinarySearchTree_.from_ordered_sequence.assert_not_called()

    @pytest.mark.parametrize(
        # ``cy`` used by the predicate is the number of lines times the height of one line.
        # Boundary cases exercised here, for a line height of 91439 EMU.
        ("extents", "line_count", "expected_value"),
        [
            ((66, 182877), 2, False),
            ((66, 182878), 2, True),
            ((66, 182879), 2, True),
            ((66, 91439), 1, True),
            ((66, 91438), 1, False),
        ],
    )
    def it_provides_a_fits_inside_predicate_fn(
        self, request, _line_height_, extents, line_count, expected_value
    ):
        _line_count_ = method_mock(request, TextFitter, "_line_count", return_value=line_count)
        _line_height_.return_value = 91439
        text_fitter = TextFitter("foo bar", extents, "foobar.ttf")

        predicate = text_fitter._fits_inside_predicate
        result = predicate(6)

        _line_count_.assert_called_once_with(text_fitter, 6)
        _line_height_.assert_called_once_with(6, "foobar.ttf")
        assert result is expected_value

    def but_it_does_not_fit_when_a_word_is_wider_than_the_width(self, request, _line_height_):
        _line_count_ = method_mock(request, TextFitter, "_line_count", return_value=None)
        text_fitter = TextFitter("foo bar", (66, 10**9), "foobar.ttf")

        predicate = text_fitter._fits_inside_predicate
        result = predicate(6)

        _line_count_.assert_called_once_with(text_fitter, 6)
        _line_height_.assert_not_called()
        assert result is False

    def it_provides_a_fits_in_width_predicate_fn(self, fits_cx_pred_fixture):
        text_fitter, point_size, text = fits_cx_pred_fixture[:3]
        _rendered_size_, expected_value = fits_cx_pred_fixture[3:]

        predicate = text_fitter._fits_in_width_predicate(point_size)
        result = predicate(text)

        _rendered_size_.assert_called_once_with(text, point_size, text_fitter._font_file)
        assert result is expected_value

    @pytest.mark.parametrize(
        ("words", "expected_lines"),
        [
            # ---an empty paragraph is a line of its own---
            ((), [""]),
            (("foo",), ["foo"]),
            # ---a line takes as many words as fit; with 10 characters to a line---
            (("foo", "bar", "baz", "quux"), ["foo bar", "baz quux"]),
            (("0123456789",), ["0123456789"]),
            (("01234", "56789"), ["01234", "56789"]),
            (("0123", "5678", "ab"), ["0123 5678", "ab"]),
            (("a", "b", "c", "d", "e"), ["a b c d e"]),
            # ---a word wider than a line cannot be wrapped---
            (("01234567890",), None),
            (("foo", "01234567890"), None),
            (("foo", "bar", "baz", "01234567890", "quux"), None),
        ],
    )
    def it_wraps_words_into_lines_to_help_best_fit(self, _rendered_size_, words, expected_lines):
        # ---a stand-in font in which every character is 10 EMU wide, in a width of 100 EMU---
        _rendered_size_.side_effect = lambda text, point_size, font_file: (len(text) * 10, 0)
        text_fitter = TextFitter("", (100, 100), "foobar.ttf")

        assert text_fitter._wrap_lines(words, 12) == expected_lines

    @pytest.mark.parametrize(
        ("text", "width", "expected_count"),
        [
            ("foo bar", 100, 1),
            # ---a paragraph boundary and a soft line break each start a line---
            ("foo\nbar", 100, 2),
            ("foo\vbar", 100, 2),
            ("foo\nbar\vbaz", 100, 3),
            # ---an empty paragraph takes a line, and so does a trailing one---
            ("foo\n\nbar", 100, 3),
            ("foo\n", 100, 2),
            ("", 100, 1),
            # ---each paragraph wraps on its own---
            ("foo bar\nbaz", 50, 3),
            ("foo bar baz\nquux bar", 80, 3),
            # ---a word wider than the width cannot be wrapped---
            ("foo\nquux", 30, None),
        ],
    )
    def it_counts_the_lines_the_text_occupies_to_help_best_fit(
        self, _rendered_size_, text, width, expected_count
    ):
        # ---a stand-in font in which every character is 10 EMU wide---
        _rendered_size_.side_effect = lambda text, point_size, font_file: (len(text) * 10, 0)
        text_fitter = TextFitter(text, (width, 1000), "foobar.ttf")

        assert text_fitter._line_count(12) == expected_count

    # fixtures ---------------------------------------------

    @pytest.fixture
    def _best_fit_fixture(self, _BinarySearchTree_, _fits_inside_predicate_):
        text_fitter = TextFitter("", (None, None), None)
        max_size = 42
        sizes_ = _BinarySearchTree_.from_ordered_sequence.return_value
        predicate_ = _fits_inside_predicate_.return_value
        font_size_ = sizes_.find_max.return_value
        return (
            text_fitter,
            max_size,
            _BinarySearchTree_,
            sizes_,
            predicate_,
            font_size_,
        )

    @pytest.fixture(params=[(49, True), (50, True), (51, False)])
    def fits_cx_pred_fixture(self, request, _rendered_size_):
        rendered_width, expected_value = request.param
        text_fitter = TextFitter("", (50, None), "foobar.ttf")
        point_size, text = 12, "foobar"
        _rendered_size_.return_value = (rendered_width, None)
        return (text_fitter, point_size, text, _rendered_size_, expected_value)

    # fixture components -----------------------------------

    @pytest.fixture
    def _BinarySearchTree_(self, request):
        return class_mock(request, "power_pptx.text.layout._BinarySearchTree")

    @pytest.fixture
    def _fits_inside_predicate_(self, request):
        return property_mock(request, TextFitter, "_fits_inside_predicate")

    @pytest.fixture
    def _line_height_(self, request):
        return function_mock(request, "power_pptx.text.layout._line_height")

    @pytest.fixture
    def _rendered_size_(self, request):
        return function_mock(request, "power_pptx.text.layout._rendered_size")


class Describe_BinarySearchTree(object):
    """Unit-test suite for `power_pptx.text.layout._BinarySearchTree` object."""

    def it_can_construct_from_an_ordered_sequence(self):
        bst = _BinarySearchTree.from_ordered_sequence(range(10))

        def in_order(node):
            """
            Traverse the tree depth first to produce a list of its values,
            in order.
            """
            result = []
            if node is None:
                return result
            result.extend(in_order(node._lesser))
            result.append(node.value)
            result.extend(in_order(node._greater))
            return result

        assert bst.value == 9
        assert bst._lesser.value == 4
        assert bst._greater is None
        assert in_order(bst) == list(range(10))

    def it_can_find_the_max_value_satisfying_a_predicate(self, max_fixture):
        bst, predicate, expected_value = max_fixture
        assert bst.find_max(predicate) == expected_value

    # fixtures ---------------------------------------------

    @pytest.fixture(
        params=[
            (range(10), lambda n: n < 6.5, 6),
            (range(10), lambda n: n > 9.9, None),
            (range(10), lambda n: n < 0.0, None),
        ]
    )
    def max_fixture(self, request):
        seq, predicate, expected_value = request.param
        bst = _BinarySearchTree.from_ordered_sequence(seq)
        return bst, predicate, expected_value


class Describe_split_into_segments(object):
    """Unit-test suite for `power_pptx.text.layout._split_into_segments()` function."""

    @pytest.mark.parametrize(
        ("text", "expected_value"),
        [
            ("", ((),)),
            ("foo", (("foo",),)),
            ("foo  bar\tbaz ", (("foo", "bar", "baz"),)),
            ("foo\nbar", (("foo",), ("bar",))),
            ("foo\vbar", (("foo",), ("bar",))),
            ("foo\n\nbar", (("foo",), (), ("bar",))),
            ("foo\n", (("foo",), ())),
            ("\n", ((), ())),
            ("foo\r\nbar", (("foo",), ("bar",))),
            ("  \xa0 ", ((),)),
        ],
    )
    def it_splits_text_into_the_words_between_forced_line_breaks(self, text, expected_value):
        assert _split_into_segments(text) == expected_value


class Describe_line_height(object):
    """Unit-test suite for `power_pptx.text.layout._line_height()` function."""

    def it_allows_1_2_ems_for_a_font_that_needs_no_more(self, request):
        _Fonts_ = class_mock(request, "power_pptx.text.layout._Fonts")
        _Fonts_.font.return_value.getmetrics.return_value = (8, 2)

        line_height = _line_height(10, "foobar.ttf")

        _Fonts_.font.assert_called_once_with("foobar.ttf", 10)
        assert line_height == round(1.2 * 10 * 12700)

    def but_it_allows_the_ascent_and_descent_of_a_font_that_needs_more(self, request):
        _Fonts_ = class_mock(request, "power_pptx.text.layout._Fonts")
        _Fonts_.font.return_value.getmetrics.return_value = (10, 3)

        assert _line_height(10, "foobar.ttf") == 13 * 12700

    def and_it_falls_back_on_1_2_ems_for_a_font_that_reports_no_metrics(self, request):
        _Fonts_ = class_mock(request, "power_pptx.text.layout._Fonts")
        # ---an object without `getmetrics()`, like Pillow's old bitmap default font---
        _Fonts_.font.return_value = object()

        assert _line_height(10, None) == round(1.2 * 10 * 12700)

    def it_is_the_greater_of_the_two_for_a_real_font(self, font_file):
        for point_size in (8, 14, 24, 44):
            ascent, descent = ImageFont.truetype(font_file, point_size).getmetrics()

            line_height = _line_height(point_size, font_file)

            assert line_height >= round(1.2 * point_size * 12700)
            assert line_height >= (ascent + descent) * 12700
            assert line_height in (round(1.2 * point_size * 12700), (ascent + descent) * 12700)


class Describe_Fonts(object):
    """Unit-test suite for `power_pptx.text.layout._Fonts` object."""

    def it_uses_pillows_default_font_when_no_path_is_given(self, request):
        """Pillow's bundled default lets `fit_text` work on platforms without
        the requested family installed (notably most Linux runtimes)."""
        # Reset memo so this test is independent of others
        _Fonts.fonts = {}
        from PIL import ImageFont

        load_default_ = function_mock(
            request, "power_pptx.text.layout.ImageFont.load_default", autospec=False
        )
        truetype_ = function_mock(
            request, "power_pptx.text.layout.ImageFont.truetype", autospec=False
        )
        load_default_.return_value = "default-font"

        font = _Fonts.font(None, 12)

        load_default_.assert_called_once_with(size=12)
        truetype_.assert_not_called()
        assert font == "default-font"
        # Cleanup memo to avoid leaking the mock into other tests
        _Fonts.fonts = {}
        # Reference ImageFont so `from PIL import` is not flagged unused
        assert ImageFont is not None

    def it_falls_back_to_unsized_default_on_old_pillow(self, request):
        _Fonts.fonts = {}
        load_default_ = function_mock(
            request, "power_pptx.text.layout.ImageFont.load_default", autospec=False
        )
        load_default_.side_effect = [TypeError("no size kwarg"), "old-default"]

        font = _Fonts.font(None, 12)

        assert load_default_.call_args_list == [call(size=12), call()]
        assert font == "old-default"
        _Fonts.fonts = {}

    def it_raises_a_ValueError_naming_a_font_file_it_cannot_load(self):
        _Fonts.fonts = {}

        with pytest.raises(ValueError, match="no-such-font.ttf"):
            _Fonts.font("/nonexistent/dir/no-such-font.ttf", 12)

        assert _Fonts.fonts == {}


# ---- behavior against a real font file ------------------------------------------------------

EMU_PER_PT = 12700

#: Font files the behavioral tests measure with.  `calibriz.ttf` ships with the test suite so the
#: results are the same everywhere; DejaVu Sans is added where installed because its line height
#: (ascent + descent) is *below* 1.2 em, whereas Calibri's is above it.
_TEST_FONTS = [testfile("calibriz.ttf")]
_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
if os.path.isfile(_DEJAVU):
    _TEST_FONTS.append(_DEJAVU)

_BULLETS = (
    "Revenue up 12%",
    "Churn down 3%",
    "NPS at 61",
    "Hiring on track",
    "Runway 28 months",
    "Series B in Q3",
)


def _needed_height(text: str, size: int, font_file: str, width: int) -> float | None:
    """EMU of height `text` needs at `size` points, or None when one word is wider than `width`.

    Derived from the documented rules rather than from the fitter's own helpers: every paragraph
    ("\\n") and soft line break ("\\v") starts a new line, an empty one still takes a line, words
    wrap greedily on spaces, and each rendered line costs max(1.2 em, ascent + descent).
    """
    font = ImageFont.truetype(font_file, size)

    def too_wide(candidate: str) -> bool:
        return font.getlength(candidate) * EMU_PER_PT > width

    line_count = 0
    for segment in re.split("[\n\v]", text):
        line_count += 1
        current = ""
        for word in segment.split():
            if too_wide(word):
                return None
            if current and too_wide(f"{current} {word}"):
                line_count += 1
                current = word
            else:
                current = f"{current} {word}" if current else word
    ascent, descent = font.getmetrics()
    return line_count * max(1.2 * size, ascent + descent) * EMU_PER_PT


@pytest.fixture(params=_TEST_FONTS, ids=os.path.basename)
def font_file(request: pytest.FixtureRequest) -> str:
    return request.param


class DescribeBestFitFontSize(object):
    """`TextFitter.best_fit_font_size()` measured against real font metrics."""

    def it_stacks_paragraphs_instead_of_flowing_them_together(self, font_file):
        text = "\n".join(_BULLETS)
        width, height = Inches(3.8), Inches(1.4)

        size = TextFitter.best_fit_font_size(text, (width, height), 60, font_file)

        assert size is not None
        # ---six short lines: they fit at `size` but not one point larger---
        assert _needed_height(text, size, font_file, width) <= height
        assert _needed_height(text, size + 1, font_file, width) > height

    def and_it_picks_a_smaller_size_than_for_the_same_words_run_together(self, font_file):
        extents = (Inches(3.8), Inches(1.4))

        stacked = TextFitter.best_fit_font_size("\n".join(_BULLETS), extents, 60, font_file)
        flowing = TextFitter.best_fit_font_size(" ".join(_BULLETS), extents, 60, font_file)

        assert flowing is not None
        assert stacked is not None
        assert _needed_height(" ".join(_BULLETS), flowing, font_file, extents[0]) <= extents[1]
        assert stacked < flowing

    def it_treats_a_soft_line_break_like_a_paragraph_boundary(self, font_file):
        extents = (Inches(3.8), Inches(1.4))

        by_paragraph = TextFitter.best_fit_font_size("\n".join(_BULLETS), extents, 60, font_file)
        by_line_break = TextFitter.best_fit_font_size("\v".join(_BULLETS), extents, 60, font_file)
        flowing = TextFitter.best_fit_font_size(" ".join(_BULLETS), extents, 60, font_file)

        assert by_line_break == by_paragraph
        assert flowing is not None
        assert by_line_break is not None
        assert by_line_break < flowing

    def it_gives_an_empty_paragraph_a_line_of_its_own(self, font_file):
        extents = (Inches(6), Inches(1))

        with_gap = TextFitter.best_fit_font_size("first\n\nthird", extents, 60, font_file)
        three_lines = TextFitter.best_fit_font_size("first\nsecond\nthird", extents, 60, font_file)
        two_lines = TextFitter.best_fit_font_size("first\nthird", extents, 60, font_file)

        assert with_gap == three_lines
        assert two_lines is not None
        assert with_gap is not None
        assert with_gap < two_lines

    def it_wraps_each_paragraph_on_its_own(self, font_file):
        text = (
            "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod\n"
            "tempor incididunt ut labore et dolore magna aliqua ut enim ad minim veniam"
        )
        width, height = Inches(3), Inches(2.5)

        size = TextFitter.best_fit_font_size(text, (width, height), 60, font_file)

        assert size is not None
        assert _needed_height(text, size, font_file, width) <= height
        # ---and the size is close to the biggest one that fits---
        assert _needed_height(text, size + 2, font_file, width) > height

    def it_returns_None_when_a_single_word_is_wider_than_the_box(self, font_file):
        assert (
            TextFitter.best_fit_font_size(
                "antidisestablishmentarianism", (Inches(0.05), Inches(2)), 18, font_file
            )
            is None
        )

    @pytest.mark.parametrize("max_size", [0, -3, 0.9])
    def it_rejects_a_max_size_below_one_point(self, max_size, font_file):
        with pytest.raises(ValueError, match="max_size"):
            TextFitter.best_fit_font_size("Hello", (Inches(4), Inches(1)), max_size, font_file)

    def it_names_a_font_file_it_cannot_load(self):
        with pytest.raises(ValueError, match="no-such-font.ttf"):
            TextFitter.best_fit_font_size(
                "Hello", (Inches(4), Inches(1)), 18, "/nonexistent/dir/no-such-font.ttf"
            )

    def it_fits_a_long_text_in_reasonable_time(self):
        # ---wrapping used to be worse than quadratic in the number of words: 400 of them took
        # ---about 9 seconds, where it now takes well under one
        font_file = testfile("calibriz.ttf")
        words = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu " * 50).split()
        text = " ".join(words[:400])
        width, height = Inches(6), Inches(40)

        started = time.perf_counter()
        size = TextFitter.best_fit_font_size(text, (width, height), 40, font_file)
        elapsed = time.perf_counter() - started

        assert size is not None
        assert _needed_height(text, size, font_file, width) <= height
        assert elapsed < 4.0


# produces different results on Linux, fails Travis-CI

# from power_pptx.text.layout import _rendered_size
# from ..unitutil.file import testfile
# class Describe_rendered_size(object):

#     def it_calculates_the_rendered_size_of_text_at_point_size(self, fixture):
#         text, point_size, font_file, expected_value = fixture
#         extents = _rendered_size(text, point_size, font_file)
#         assert extents == expected_value

#     # fixtures ---------------------------------------------

#     @pytest.fixture(params=[
#         ('Typical',     18, (673100, 254000)),
#         ('foo bar baz', 12, (698500, 165100)),
#     ])
#     def fixture(self, request):
#         text, point_size, expected_value = request.param
#         font_file = testfile('calibriz.ttf')
#         return text, point_size, font_file, expected_value
