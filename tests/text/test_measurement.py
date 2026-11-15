"""Unit-test suite for `power_pptx.text.measurement`: line breaking as renderers do it."""

from __future__ import annotations

import unicodedata

import pytest

from power_pptx.text import layout, measure_text, truncate_text
from power_pptx.text.layout import TextFitter
from power_pptx.util import Pt

JAPANESE = "四半期の売上高は、すべての地域で予測を上回るペースで成長しました。"
URL = "https://example.com/reports/2026/q3/enterprise-renewals/summary-by-region.html"


def _fake_points(text: str, point_size: int) -> float:
    """Made-up advance: an East Asian character is 1 em wide, anything else half an em."""
    return sum(1.0 if unicodedata.east_asian_width(c) in "WF" else 0.5 for c in text) * point_size


@pytest.fixture(autouse=True)
def fake_metrics(monkeypatch):
    """Measure with made-up metrics so results don't depend on installed fonts."""

    def rendered_size(text, point_size, font_file):
        return int(_fake_points(text, point_size) * 12700), point_size * 12700

    monkeypatch.setattr(layout, "_rendered_size", rendered_size)
    monkeypatch.setattr(
        layout, "_advance", lambda text, size, font_file: _fake_points(text, size), raising=False
    )
    monkeypatch.setattr(layout, "_line_height_em", lambda font_file: 1.2)


class DescribeMeasureText:
    def it_wraps_East_Asian_text_between_characters(self):
        m = measure_text(JAPANESE, Pt(100), size_pt=10, font_file="fake.ttf")

        assert "".join(m.lines) == JAPANESE
        assert len(m.lines) == 4
        assert m.width <= Pt(100)

    def it_never_starts_a_line_with_closing_punctuation(self):
        m = measure_text("あいうえおかきくけ、さ", Pt(90), size_pt=10, font_file="fake.ttf")

        assert m.lines == ("あいうえおかきく", "け、さ")

    def it_wraps_a_url_after_its_slashes(self):
        m = measure_text(URL, Pt(150), size_pt=10, font_file="fake.ttf")

        assert "".join(m.lines) == URL
        assert len(m.lines) == 3

    def it_wraps_after_a_hyphen(self):
        m = measure_text("a state-of-the-art plan", Pt(60), size_pt=10, font_file="fake.ttf")

        assert m.lines == ("a state-of-", "the-art plan")

    def it_still_raises_for_a_word_wider_than_the_line(self):
        with pytest.raises(ValueError, match="does not fit"):
            measure_text("Supercalifragilistic", Pt(50), size_pt=10, font_file="fake.ttf")


class DescribeTruncateText:
    def it_uses_every_line_it_is_allowed_for_East_Asian_text(self):
        result = truncate_text(JAPANESE, Pt(100), max_lines=2, size_pt=10, font_file="fake.ttf")

        assert result.endswith("…")
        assert JAPANESE.startswith(result[:-1])
        lines = measure_text(result, Pt(100), size_pt=10, font_file="fake.ttf").lines
        assert len(lines) == 2
        assert len(result) == 20

    def it_cuts_where_a_line_could_end(self):
        result = truncate_text(
            "a state-of-the-art plan for growth", Pt(60), size_pt=10, font_file="fake.ttf"
        )

        assert result == "a state-of-…"

    def it_returns_text_that_fits_unchanged(self):
        assert truncate_text("a plan", Pt(60), size_pt=10, font_file="fake.ttf") == "a plan"

    def it_returns_nothing_when_not_even_the_ellipsis_fits(self):
        assert truncate_text("a plan", Pt(3), size_pt=10, font_file="fake.ttf") == ""

    @pytest.mark.parametrize("size_pt", [0, 1.5, True])
    def it_rejects_a_size_that_is_not_a_positive_integer(self, size_pt):
        with pytest.raises(ValueError, match="integer size_pt must be positive"):
            truncate_text("a plan", Pt(60), size_pt=size_pt, font_file="fake.ttf")


class DescribeBestFitFontSize:
    def it_fits_East_Asian_text_by_wrapping_it(self):
        # -- 33 characters: 4 lines of 9 take 139.2pt at 29pt, 144pt at 30pt --
        assert TextFitter.best_fit_font_size(JAPANESE, (Pt(280), Pt(140)), 40, None) == 29

    def it_fits_the_same_with_and_without_constraints(self):
        text = "one\ntwo\nthree"
        extents = (Pt(500), Pt(36))

        plain = TextFitter.best_fit_font_size(text, extents, 40, None)

        assert plain == 10
        assert TextFitter.best_fit_font_size(text, extents, 40, None, min_size=2) == plain
        assert TextFitter.best_fit_font_size(text, extents, 40, None, max_lines=9) == plain
        assert TextFitter.best_fit_font_size(text, extents, 40, None, min_size=plain) == plain
