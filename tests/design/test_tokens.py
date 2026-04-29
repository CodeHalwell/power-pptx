"""Unit-test suite for :mod:`power_pptx.design.tokens`."""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx.design.tokens import DesignTokens, ShadowToken, TypographyToken
from power_pptx.dml.color import RGBColor
from power_pptx.util import Emu, Pt


class DescribeTypographyToken:
    def it_builds_from_a_string_family(self):
        t = TypographyToken.from_value("Inter")
        assert t.family == "Inter"
        assert t.size is None
        assert t.bold is None

    def it_builds_from_a_dict(self):
        t = TypographyToken.from_value(
            {"family": "Inter", "size": Pt(14), "bold": True}
        )
        assert t.family == "Inter"
        assert t.size == Pt(14)
        assert t.bold is True

    def it_coerces_an_int_size_to_emu(self):
        t = TypographyToken.from_value({"family": "Inter", "size": 100000})
        assert t.size == Emu(100000)

    def it_rejects_a_missing_family(self):
        with pytest.raises(ValueError):
            TypographyToken.from_value({"size": Pt(12)})

    def it_returns_the_existing_token_unchanged(self):
        t = TypographyToken(family="Inter")
        assert TypographyToken.from_value(t) is t


class DescribeShadowToken:
    def it_builds_from_a_dict(self):
        s = ShadowToken.from_value(
            {
                "blur_radius": Pt(8),
                "distance": Pt(2),
                "direction": 90,
                "color": "#000000",
                "alpha": 0.25,
            }
        )
        assert s.blur_radius == Pt(8)
        assert s.distance == Pt(2)
        assert s.direction == 90.0
        assert s.color == RGBColor(0, 0, 0)
        assert s.alpha == 0.25

    def it_rejects_alpha_out_of_range(self):
        with pytest.raises(ValueError):
            ShadowToken.from_value({"alpha": 1.5})


class DescribeDesignTokensFromDict:
    def it_coerces_palette_entries_from_hex_strings(self):
        tokens = DesignTokens.from_dict(
            {"palette": {"primary": "#3C2F80", "secondary": "FF6600"}}
        )
        assert tokens.palette["primary"] == RGBColor(0x3C, 0x2F, 0x80)
        assert tokens.palette["secondary"] == RGBColor(0xFF, 0x66, 0x00)

    def it_coerces_palette_entries_from_tuples(self):
        tokens = DesignTokens.from_dict({"palette": {"x": (10, 20, 30)}})
        assert tokens.palette["x"] == RGBColor(10, 20, 30)

    def it_rejects_bad_hex_strings(self):
        with pytest.raises(ValueError):
            DesignTokens.from_dict({"palette": {"x": "#abc"}})

    def it_builds_typography_radii_spacings_shadows(self):
        tokens = DesignTokens.from_dict(
            {
                "typography": {"heading": "Inter"},
                "radii": {"sm": Pt(4)},
                "spacings": {"md": Pt(16)},
                "shadows": {"card": {"blur_radius": Pt(8), "alpha": 0.3}},
            }
        )
        assert tokens.typography["heading"].family == "Inter"
        assert tokens.radii["sm"] == Pt(4)
        assert tokens.spacings["md"] == Pt(16)
        assert tokens.shadows["card"].blur_radius == Pt(8)
        assert tokens.shadows["card"].alpha == 0.3

    def it_ignores_unknown_top_level_keys(self):
        tokens = DesignTokens.from_dict({"palette": {}, "extras": "ignored"})
        assert tokens.palette == {}


class DescribeDesignTokensMerge:
    def it_overlays_other_on_self(self):
        base = DesignTokens.from_dict(
            {"palette": {"primary": "#000000", "secondary": "#FFFFFF"}}
        )
        override = DesignTokens.from_dict({"palette": {"primary": "#FF0000"}})
        merged = base.merge(override)
        assert merged.palette["primary"] == RGBColor(0xFF, 0, 0)
        assert merged.palette["secondary"] == RGBColor(0xFF, 0xFF, 0xFF)


class DescribeDesignTokensFromPptx:
    def it_extracts_palette_and_fonts_from_an_open_presentation(self):
        prs = Presentation()
        tokens = DesignTokens.from_pptx(prs)
        # Default theme has all six accent slots populated and major/minor fonts.
        for slot in ("accent1", "accent2", "accent3", "accent4", "accent5", "accent6"):
            assert slot in tokens.palette
            assert isinstance(tokens.palette[slot], RGBColor)
        assert "heading" in tokens.typography
        assert "body" in tokens.typography


class DescribeFromPreset:
    """Built-in named token presets save callers from inventing a brand."""

    def it_loads_the_modern_light_preset(self):
        t = DesignTokens.from_preset("modern_light")
        # Sanity: the preset populates every category so recipes don't
        # have to fall back to defaults.
        assert "primary" in t.palette
        assert "neutral" in t.palette
        assert "heading" in t.typography
        assert "md" in t.radii
        assert "card" in t.shadows
        assert "md" in t.spacings

    def it_loads_each_named_preset(self):
        for name in ("modern_light", "modern_dark", "corporate_navy", "vibrant"):
            t = DesignTokens.from_preset(name)
            assert "primary" in t.palette

    def it_rejects_unknown_presets(self):
        with pytest.raises(ValueError, match="Unknown preset"):
            DesignTokens.from_preset("not-a-thing")


class DescribeWithOverrides:
    """`tokens.with_overrides({'palette.primary': ...})` for per-call tweaks."""

    def it_overrides_a_palette_color(self):
        t = DesignTokens.from_preset("modern_light")
        t2 = t.with_overrides({"palette.primary": "#FF6600"})
        assert t2.palette["primary"] == RGBColor(0xFF, 0x66, 0x00)
        # The base is untouched.
        assert t.palette["primary"] != RGBColor(0xFF, 0x66, 0x00)

    def it_overrides_a_radius(self):
        t = DesignTokens.from_preset("modern_light")
        t2 = t.with_overrides({"radii.lg": Pt(24)})
        assert t2.radii["lg"] == Pt(24)

    def it_overrides_a_typography_subfield(self):
        t = DesignTokens.from_preset("modern_light")
        t2 = t.with_overrides({"typography.heading.size": Pt(48)})
        assert t2.typography["heading"].size == Pt(48)
        # The other heading fields survive.
        assert t2.typography["heading"].family == t.typography["heading"].family

    def it_rejects_a_non_dotted_key(self):
        t = DesignTokens.from_preset("modern_light")
        with pytest.raises(ValueError, match="must be dotted"):
            t.with_overrides({"primary": "#FF0000"})

    def it_rejects_an_unknown_category(self):
        t = DesignTokens.from_preset("modern_light")
        with pytest.raises(ValueError, match="unknown override category"):
            t.with_overrides({"nonsense.foo": "bar"})
