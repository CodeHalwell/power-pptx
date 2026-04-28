"""Unit-test suite for `pptx.chart.palettes`."""

from __future__ import annotations

import pytest

from pptx.chart.palettes import (
    CHART_PALETTES,
    _to_rgb,
    palette_names,
    resolve_palette,
)
from pptx.dml.color import RGBColor


class DescribeResolvePalette:
    def it_resolves_a_named_palette_to_RGBColors(self):
        colors = resolve_palette("modern")

        assert len(colors) == len(CHART_PALETTES["modern"])
        assert all(isinstance(c, RGBColor) for c in colors)
        assert str(colors[0]) == CHART_PALETTES["modern"][0].lstrip("#").upper()

    def it_resolves_every_built_in_palette(self):
        for name in palette_names():
            colors = resolve_palette(name)
            assert colors and all(isinstance(c, RGBColor) for c in colors)

    def it_resolves_a_sequence_of_color_likes(self):
        colors = resolve_palette(["#FF0000", "00FF00", (0, 0, 255), RGBColor(1, 2, 3)])
        assert [str(c) for c in colors] == ["FF0000", "00FF00", "0000FF", "010203"]

    def it_raises_for_unknown_palette_name(self):
        with pytest.raises(ValueError, match="unknown palette"):
            resolve_palette("not_real")

    def it_raises_for_empty_palette(self):
        with pytest.raises(ValueError, match="at least one color"):
            resolve_palette([])


class DescribeToRgb:
    def it_returns_RGBColor_unchanged(self):
        c = RGBColor(1, 2, 3)
        assert _to_rgb(c) is c

    def it_parses_a_hex_string_with_or_without_hash(self):
        assert _to_rgb("#3C2F80") == RGBColor(0x3C, 0x2F, 0x80)
        assert _to_rgb("3C2F80") == RGBColor(0x3C, 0x2F, 0x80)

    def it_parses_an_rgb_triple(self):
        assert _to_rgb((10, 20, 30)) == RGBColor(10, 20, 30)
        assert _to_rgb([10, 20, 30]) == RGBColor(10, 20, 30)


class DescribePaletteNames:
    def it_returns_all_built_in_palette_names(self):
        names = palette_names()
        assert isinstance(names, tuple)
        assert set(names) == set(CHART_PALETTES.keys())
