# pyright: reportPrivateUsage=false

"""Unit-test suite for `power_pptx.text.layout` module."""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from power_pptx.text import layout
from power_pptx.text.layout import (
    ParagraphFormat,
    TextFitter,
    _BinarySearchTree,
    _Fonts,
    _Layout,
    _LineSource,
)
from power_pptx.util import Pt

from ..unitutil.mock import (
    ANY,
    call,
    class_mock,
    function_mock,
    initializer_mock,
    instance_mock,
    method_mock,
    property_mock,
)


class DescribeTextFitter(object):
    """Unit-test suite for `power_pptx.text.layout.TextFitter` object."""

    def it_can_determine_the_best_fit_font_size(self, request, line_source_):
        _LineSource_ = class_mock(
            request, "power_pptx.text.layout._LineSource", return_value=line_source_
        )
        _init_ = initializer_mock(request, TextFitter)
        _best_fit_font_size_ = method_mock(
            request, TextFitter, "_best_fit_font_size", return_value=36
        )
        extents, max_size = (19, 20), 42

        font_size = TextFitter.best_fit_font_size("Foobar", extents, max_size, "foobar.ttf")

        _LineSource_.assert_called_once_with("Foobar")
        _init_.assert_called_once_with(line_source_, extents, "foobar.ttf", 0, _Layout())
        _best_fit_font_size_.assert_called_once_with(ANY, max_size, 1)
        assert font_size == 36

    def it_finds_best_fit_font_size_to_help_best_fit(self, _best_fit_fixture):
        text_fitter, max_size, _BinarySearchTree_ = _best_fit_fixture[:3]
        sizes_, predicate_, font_size_ = _best_fit_fixture[3:]

        font_size = text_fitter._best_fit_font_size(max_size)

        _BinarySearchTree_.from_ordered_sequence.assert_called_once_with(range(1, max_size + 1))
        sizes_.find_max.assert_called_once_with(predicate_)
        assert font_size is font_size_

    @pytest.mark.parametrize(
        # ``cy`` used by the predicate is now ``max(ink_cy, leading_cy)``
        # where ``leading_cy = int(point_size * 1.2 * 914400 / 72.0)``.
        # For the mocked ink_cy=50 and point_size=6, leading_cy=91439
        # (floating-point truncation of 91439.999...) dominates, so the
        # 2-line height bound is 182878 EMU. Boundary cases exercised
        # here.  See IMPROVEMENTS item 7.
        ("extents", "point_size", "text_lines", "expected_value"),
        [
            ((66, 182877), 6, ("foo", "bar"), False),
            ((66, 182878), 6, ("foo", "bar"), True),
            ((66, 182879), 6, ("foo", "bar"), True),
        ],
    )
    def it_provides_a_fits_inside_predicate_fn(
        self,
        request,
        line_source_,
        _rendered_size_,
        extents,
        point_size,
        text_lines,
        expected_value,
    ):
        _wrap_lines_ = method_mock(request, TextFitter, "_wrap_lines", return_value=text_lines)
        _rendered_size_.return_value = (None, 50)
        text_fitter = TextFitter(line_source_, extents, "foobar.ttf")

        predicate = text_fitter._fits_inside_predicate
        result = predicate(point_size)

        _wrap_lines_.assert_called_once_with(text_fitter, line_source_, point_size, fitting=True)
        _rendered_size_.assert_called_once_with("Ty", point_size, text_fitter._font_file)
        assert result is expected_value

    @pytest.mark.parametrize(
        ("rendered_width", "expected_value"), [(49, True), (50, True), (51, False)]
    )
    def it_compares_a_line_with_its_width(self, _rendered_size_, rendered_width, expected_value):
        text_fitter = TextFitter(None, (50, None), "foobar.ttf")
        _rendered_size_.return_value = (rendered_width, None)

        width = text_fitter._line_width("foobar", 12)

        _rendered_size_.assert_called_once_with("foobar", 12, "foobar.ttf")
        assert (width <= text_fitter._width) is expected_value

    def it_adds_letter_spacing_after_every_character(self, _rendered_size_):
        _rendered_size_.return_value = (100, None)

        assert TextFitter(None, (50, None), None, 7)._line_width("abc", 12) == 121

    # fixtures ---------------------------------------------

    @pytest.fixture
    def _best_fit_fixture(self, _BinarySearchTree_, _fits_inside_predicate_):
        text_fitter = TextFitter(None, (None, None), None)
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

    # fixture components -----------------------------------

    @pytest.fixture
    def _BinarySearchTree_(self, request):
        return class_mock(request, "power_pptx.text.layout._BinarySearchTree")

    @pytest.fixture
    def _fits_inside_predicate_(self, request):
        return property_mock(request, TextFitter, "_fits_inside_predicate")

    @pytest.fixture
    def line_source_(self, request):
        return instance_mock(request, _LineSource)

    @pytest.fixture
    def _rendered_size_(self, request):
        return function_mock(request, "power_pptx.text.layout._rendered_size")


# -- Wrapping and fitting are checked with made-up metrics so the results don't
# -- depend on installed fonts: an East Asian character is 1 em wide, anything
# -- else half an em, and every line is 1 em tall.


def _fake_points(text: str, point_size: int) -> float:
    return sum(1.0 if unicodedata.east_asian_width(c) in "WF" else 0.5 for c in text) * point_size


@pytest.fixture
def fake_metrics(monkeypatch):
    calls = []

    def rendered_size(text, point_size, font_file):
        calls.append(text)
        return int(_fake_points(text, point_size) * 12700), point_size * 12700

    monkeypatch.setattr(layout, "_rendered_size", rendered_size)
    monkeypatch.setattr(layout, "_advance", lambda text, size, font_file: _fake_points(text, size))
    return calls


def _wrap(text, width_pt, size=10, **layout_options):
    fitter = TextFitter(_LineSource(text), (Pt(width_pt), Pt(1000)), None, 0)
    if layout_options:
        fitter = TextFitter(
            _LineSource(text), (Pt(width_pt), Pt(1000)), None, 0, _Layout(**layout_options)
        )
    return fitter._wrap_lines(_LineSource(text), size)


JAPANESE = "四半期の売上高は、すべての地域で予測を上回るペースで成長しました。"


@pytest.mark.usefixtures("fake_metrics")
class DescribeTextFitterWrapping(object):
    """`TextFitter` breaks lines where PowerPoint and LibreOffice break them."""

    def it_breaks_at_spaces(self):
        assert _wrap("one two three four", 50) == ["one two", "three four"]

    def it_collapses_runs_of_spaces_and_keeps_explicit_lines(self):
        assert _wrap("  one   two \v\nthree\n", 100) == ["one two", "", "three", ""]

    def it_breaks_between_East_Asian_characters(self):
        lines = _wrap(JAPANESE, 100)

        assert "".join(lines) == JAPANESE
        assert all(_fake_points(line, 10) <= 100 for line in lines)
        assert len(lines) == 4

    @pytest.mark.parametrize(
        ("text", "width", "expected"),
        [
            # -- 、 cannot start a line, so は moves down with it --
            ("あいうえおかきくけ、さ", 90, ["あいうえおかきく", "け、さ"]),
            # -- 「 cannot end a line --
            ("あいうえおかき「くけこ」", 80, ["あいうえおかき", "「くけこ」"]),
            # -- nor can a small kana or the prolonged-sound mark start one --
            ("あいうえおかきくっこ", 80, ["あいうえおかき", "くっこ"]),
            ("あいうえおかきカーこ", 80, ["あいうえおかき", "カーこ"]),
        ],
    )
    def it_respects_the_East_Asian_line_breaking_rules(self, text, width, expected):
        assert _wrap(text, width) == expected

    def it_breaks_after_a_hyphen(self):
        assert _wrap("a state-of-the-art plan", 60) == ["a state-of-", "the-art plan"]

    def it_breaks_a_long_path_after_a_slash(self):
        # -- 24 half-em characters per line at 10pt in a 120pt box --
        lines = _wrap("https://example.com/reports/2026/q3/summary.html", 120)

        assert lines == ["https://example.com/", "reports/2026/q3/", "summary.html"]

    def but_it_keeps_a_short_slash_word_whole(self):
        # -- "Revenues and/" would fit the 14-character line --
        assert _wrap("Revenues and/or margin", 70) == ["Revenues", "and/or margin"]

    def it_reports_a_word_wider_than_the_line(self):
        assert _wrap("a Supercalifragilistic word", 50) is None

    def but_it_can_split_the_word_at_the_edge_of_the_line(self):
        lines = _wrap("a Supercalifragilistic word", 50, break_long_words=True)

        assert lines == ["a", "Supercalif", "ragilistic", "word"]

    def it_keeps_a_combining_mark_with_its_letter(self):
        lines = _wrap("é" * 12, 25, break_long_words=True)

        assert all(not line.startswith("́") for line in lines)

    def and_it_lets_a_letter_and_its_mark_overflow_a_line_too_narrow_for_both(self):
        assert _wrap("éé", 5, break_long_words=True) == ["é", "é"]

    @pytest.mark.parametrize(
        ("text", "width", "break_long_words", "expected"),
        [
            # -- a slash that exactly fills the line ends it only when nothing before can --
            ("abcdefghi/jklmn", 50, False, ["abcdefghi/", "jklmn"]),
            ("ab/cdefgh/ijklmn", 50, False, ["ab/", "cdefgh/", "ijklmn"]),
            ("a-bcdefgh/ijklmn", 50, False, ["a-", "bcdefgh/", "ijklmn"]),
            # -- a short path after a space is cut at the edge of the box, not at a slash --
            ("ab abcdef/ghijklmnop", 50, True, ["ab", "abcdef/ghi", "jklmnop"]),
            ("ab abcdef/ghijklmnop", 60, False, None),
            # -- a soft line break counts as that space; the start of a paragraph doesn't --
            ("x\vabcdefg/hijklmn", 50, True, ["x", "abcdefg/hi", "jklmn"]),
            ("abcdefg/hijklmn", 50, True, ["abcdefg/", "hijklmn"]),
        ],
    )
    def it_breaks_after_a_slash_only_where_LibreOffice_does(
        self, text, width, break_long_words, expected
    ):
        assert _wrap(text, width, break_long_words=break_long_words) == expected

    @pytest.mark.parametrize("estimate_scale", [0.5, 2.0])
    def it_wraps_by_measured_width_however_far_off_the_estimate_is(
        self, monkeypatch, estimate_scale
    ):
        def advance(text, size, font_file):
            return _fake_points(text, size) * estimate_scale

        monkeypatch.setattr(layout, "_advance", advance)

        lines = _wrap("one two three four five six seven eight nine ten", 50)

        # -- ten half-em characters to a 50pt line at 10pt --
        assert lines == ["one two", "three four", "five six", "seven", "eight nine", "ten"]

    def it_measures_each_line_only_a_few_times(self, fake_metrics):
        text = " ".join(["revenue growth margin enterprise customers forecast"] * 150)

        lines = _wrap(text, 400)

        assert len(fake_metrics) < 4 * len(lines)


@pytest.mark.usefixtures("fake_metrics")
class DescribeTextFitterFitting(object):
    """`TextFitter.best_fit_font_size` measures what will be rendered."""

    def it_fits_East_Asian_text_by_wrapping_it(self):
        size = TextFitter.best_fit_font_size(JAPANESE, (Pt(280), Pt(140)), 40, None)

        # -- 33 characters: 4 lines of 9 take 139.2pt at 29pt, 144pt at 30pt --
        assert size == 29

    def it_keeps_words_whole_when_a_smaller_size_allows_it(self):
        size = TextFitter.best_fit_font_size("Supercalifragilistic", (Pt(100), Pt(200)), 40, None)

        assert size == 10

    def but_it_breaks_a_word_when_no_size_from_the_minimum_keeps_it_whole(self):
        size = TextFitter.best_fit_font_size(
            "Supercalifragilistic", (Pt(100), Pt(200)), 40, None, min_size=14
        )

        # -- four lines of five characters at 40pt take 192pt of the 200pt --
        assert size == 40

    def and_it_breaks_a_word_only_at_a_size_where_each_character_fits(self):
        # -- a character is half an em: "W" is 5pt wide at 10pt, so 10pt is the largest --
        size = TextFitter.best_fit_font_size("WW", (Pt(5), Pt(100)), 18, None, min_size=6)

        assert size == 10

    def but_it_finds_no_fit_when_not_even_one_character_fits_the_width(self):
        size = TextFitter.best_fit_font_size("WW", (Pt(5), Pt(100)), 18, None, min_size=12)

        assert size is None

    def and_it_never_breaks_a_word_when_told_to_keep_words_whole(self):
        size = TextFitter.best_fit_font_size(
            "Supercalifragilistic",
            (Pt(100), Pt(200)),
            40,
            None,
            min_size=14,
            break_long_words=False,
        )

        assert size is None

    def it_measures_single_spacing_by_default(self):
        text = "one\ntwo\nthree"

        assert TextFitter.best_fit_font_size(text, (Pt(500), Pt(36)), 40, None) == 10
        assert TextFitter.best_fit_font_size(text, (Pt(500), Pt(36)), 40, None, min_size=2) == 10

    def it_measures_the_line_spacing_it_is_given(self):
        text = "one\ntwo\nthree"

        assert TextFitter.best_fit_font_size(text, (Pt(500), Pt(36)), 40, None, line_spacing=2) == 5
        assert (
            TextFitter.best_fit_font_size(text, (Pt(500), Pt(36)), 40, None, line_spacing=Pt(12))
            == 12
        )

    def it_adds_the_space_between_paragraphs(self):
        formats = [ParagraphFormat(space_after=Pt(6)), ParagraphFormat(space_before=Pt(6))]
        # -- 2 lines of 1.2em plus 12pt between them in 36pt: 1.2 * 2 * 10 + 12 = 36 --
        size = TextFitter.best_fit_font_size(
            "one\ntwo", (Pt(500), Pt(36)), 40, None, paragraph_formats=formats
        )

        assert size == 10

    def but_not_above_the_first_paragraph_or_below_the_last(self):
        formats = [ParagraphFormat(space_before=Pt(50)), ParagraphFormat(space_after=Pt(50))]
        size = TextFitter.best_fit_font_size(
            "one\ntwo", (Pt(500), Pt(36)), 40, None, paragraph_formats=formats
        )

        assert size == 15

    def it_measures_spacing_given_as_a_fraction_of_the_font_size(self):
        formats = [ParagraphFormat(), ParagraphFormat(space_before=0.6)]

        size = TextFitter.best_fit_font_size(
            "one\ntwo", (Pt(500), Pt(36)), 40, None, paragraph_formats=formats
        )

        assert size == 12

    def it_wants_a_format_for_every_paragraph(self):
        with pytest.raises(ValueError, match="paragraph_formats"):
            TextFitter.best_fit_font_size(
                "one\ntwo", (Pt(500), Pt(36)), 40, None, paragraph_formats=[ParagraphFormat()]
            )


class DescribeFullWidthCharacters(object):
    """Wide and fullwidth East Asian characters measure one em in any font.

    A renderer draws them in an East Asian font even when the run names a
    Latin face without the glyphs, so measuring them in that face (its
    "missing glyph" box, 0.69 em in Outfit) under-counted their width.
    """

    OUTFIT = str(Path(__file__).parents[1] / "fonts" / "Outfit-Regular.ttf")

    def it_advances_one_em_per_character_in_a_face_without_the_glyphs(self):
        assert layout._advance("四半期の売上", 100, self.OUTFIT) == pytest.approx(600)

    def and_it_measures_the_ink_of_a_line_the_same_way(self):
        width, _ = layout._rendered_size("四半期の売上", 100, self.OUTFIT)

        assert width == 600 * 12700

    def and_it_still_measures_the_Latin_text_beside_them_in_the_face(self):
        latin = layout._advance("Q3", 100, self.OUTFIT)

        assert layout._advance("売上Q3", 100, self.OUTFIT) == pytest.approx(200 + latin)


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


class Describe_LineSource(object):
    """Unit-test suite for `power_pptx.text.layout._LineSource` object."""

    def it_generates_text_remainder_pairs(self):
        line_source = _LineSource("foo bar baz")
        expected = (
            ("foo", _LineSource("bar baz")),
            ("foo bar", _LineSource("baz")),
            ("foo bar baz", _LineSource("")),
        )
        assert all((a == b) for a, b in zip(expected, line_source))


class Describe_Fonts(object):
    """Unit-test suite for `power_pptx.text.layout._Fonts` object."""

    def it_names_a_font_file_it_cannot_open(self, tmp_path):
        missing = str(tmp_path / "no-such-font.ttf")

        with pytest.raises(OSError, match="no-such-font.ttf"):
            layout._Fonts._load(missing, 12)

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
