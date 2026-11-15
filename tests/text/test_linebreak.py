"""Unit-test suite for `power_pptx.text._linebreak`: where a line may break inside text."""

from __future__ import annotations

import pytest

from power_pptx.text._linebreak import (
    asian_latin_gaps,
    break_offsets,
    has_east_asian,
    is_character_start,
    line_start_offsets,
    split_words,
)


def _pieces(word: str) -> list[str]:
    offsets = (0, *break_offsets(word), len(word))
    return [word[a:b] for a, b in zip(offsets, offsets[1:])]


class DescribeBreakOffsets:
    # -- Each case was checked against LibreOffice 24.2's line breaks. --

    @pytest.mark.parametrize(
        ("word", "expected"),
        [
            ("revenue", ["revenue"]),
            ("state-of-the-art", ["state-", "of-", "the-", "art"]),
            ("covid-19", ["covid-", "19"]),
            ("2024\u20132026", ["2024\u2013", "2026"]),
            ("example.com/reports/q3", ["example.com/", "reports/", "q3"]),
            ("C:\\Users\\x", ["C:\\", "Users\\", "x"]),
            ("what?really!yes", ["what?", "really!", "yes"]),
            ("alpha|beta", ["alpha|", "beta"]),
            # -- an em dash may also start a line --
            ("Revenue\u2014margin", ["Revenue", "\u2014", "margin"]),
        ],
    )
    def it_breaks_after_hyphens_dashes_slashes_and_question_marks(self, word, expected):
        assert _pieces(word) == expected

    @pytest.mark.parametrize(
        "word",
        ["1,234,567.89", "12/31/2026", "$1,000.00", "12.5%", "(555)123", "x86_64", "v2.0.1"],
    )
    def it_keeps_numbers_together(self, word):
        assert _pieces(word)[0].rstrip("/") in word
        assert len(_pieces(word)) == 1

    def it_breaks_between_East_Asian_characters(self):
        assert _pieces("売上高") == ["売", "上", "高"]

    @pytest.mark.parametrize(
        ("word", "expected"),
        [
            ("あ、い", ["あ、", "い"]),
            ("あ。」い", ["あ。」", "い"]),
            ("あ「い」う", ["あ", "「い」", "う"]),
            ("あ（い）う", ["あ", "（い）", "う"]),
            ("かっこ", ["かっ", "こ"]),
            ("カーブ", ["カー", "ブ"]),
            ("あ々い", ["あ々", "い"]),
            ("あ・い", ["あ・", "い"]),
        ],
    )
    def it_follows_the_kinsoku_rules(self, word, expected):
        assert _pieces(word) == expected

    def it_keeps_a_Korean_word_together(self):
        assert _pieces("분기별") == ["분기별"]

    def it_keeps_latin_letters_and_digits_next_to_East_Asian_text_apart(self):
        assert _pieces("売上Q3で") == ["売", "上", "Q3", "で"]

    def it_holds_a_combining_mark_to_its_letter(self):
        assert _pieces("売\u3099上") == ["売\u3099", "上"]

    def it_breaks_after_a_zero_width_space_but_not_at_a_word_joiner(self):
        assert _pieces("ab\u200bcd") == ["ab\u200b", "cd"]
        assert _pieces("ab\u2060cd") == ["ab\u2060cd"]


class DescribeSplitWords:
    def it_splits_at_any_breaking_space(self):
        assert split_words(" one\ttwo\u2009three  ") == ["one", "two", "three"]

    def but_not_at_a_no_break_space(self):
        assert split_words("12\u00a0000 USD") == ["12\u00a0000", "USD"]


def it_lists_every_place_a_new_line_may_start():
    assert line_start_offsets("  one two-three") == [6, 10]


@pytest.mark.parametrize(
    ("text", "expected"),
    [("売上高はQ3 2026で", 2), ("12.5%増の", 1), ("plain text", 0), ("売上高（速報）", 0)],
)
def it_counts_where_East_Asian_and_Latin_text_meet(text, expected):
    assert asian_latin_gaps(text) == expected


def it_recognises_East_Asian_text():
    assert has_east_asian("Revenue 売上")
    assert not has_east_asian("Revenue café")


def it_never_cuts_before_a_combining_mark():
    assert not is_character_start("e\u0301x", 1)
    assert is_character_start("e\u0301x", 2)
