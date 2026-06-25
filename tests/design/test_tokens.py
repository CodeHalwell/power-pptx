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


class DescribeNestedDictOverrides:
    """`with_overrides` accepts nested dicts in addition to dotted keys."""

    def it_accepts_a_nested_dict(self):
        from power_pptx.design.tokens import DesignTokens
        from power_pptx.util import Pt

        tokens = DesignTokens.from_dict({
            "palette": {"primary": "#000000"},
            "typography": {"heading": {"family": "Inter", "size": 24}},
        })
        result = tokens.with_overrides({
            "palette": {"primary": "#FF6600"},
            "typography": {"heading": {"size": Pt(40)}},
        })
        assert str(result.palette["primary"]) == "FF6600"
        assert result.typography["heading"].size == Pt(40)

    def it_accepts_dotted_keys(self):
        from power_pptx.design.tokens import DesignTokens
        from power_pptx.util import Pt

        tokens = DesignTokens.from_dict({"palette": {"primary": "#000000"}})
        result = tokens.with_overrides({
            "palette.primary": "#11AA22",
            "typography.heading.size": Pt(20),
        })
        assert str(result.palette["primary"]) == "11AA22"
        assert result.typography["heading"].size == Pt(20)

    def it_accepts_mixed_styles(self):
        from power_pptx.design.tokens import DesignTokens
        from power_pptx.util import Pt

        tokens = DesignTokens.from_dict({"palette": {"primary": "#000000"}})
        result = tokens.with_overrides({
            "palette.primary": "#AA00BB",
            "typography": {"heading": {"size": Pt(28)}},
        })
        assert str(result.palette["primary"]) == "AA00BB"
        assert result.typography["heading"].size == Pt(28)


# ---------------------------------------------------------------------------
# DesignTokens.from_seed
# ---------------------------------------------------------------------------

_FROM_SEED_KEYS = {
    "primary", "secondary", "accent", "neutral", "muted", "surface",
    "background", "text", "on_primary", "lt1", "lt2",
    "positive", "negative", "success", "danger",
}


class DescribeDesignTokensFromSeed:
    @pytest.mark.parametrize(
        "harmony",
        ["complementary", "analogous", "triadic", "monochromatic"],
    )
    def it_returns_all_expected_palette_keys(self, harmony):
        tokens = DesignTokens.from_seed("#3B5BDB", harmony=harmony)
        assert set(tokens.palette) == _FROM_SEED_KEYS
        for value in tokens.palette.values():
            assert isinstance(value, RGBColor)

    @pytest.mark.parametrize(
        "harmony",
        ["complementary", "analogous", "triadic", "monochromatic"],
    )
    def it_is_deterministic(self, harmony):
        a = DesignTokens.from_seed("#3B5BDB", harmony=harmony)
        b = DesignTokens.from_seed("#3B5BDB", harmony=harmony)
        assert a.palette == b.palette

    def it_accepts_rgbcolor_and_tuple_and_hex_alike(self):
        ref = DesignTokens.from_seed("#3B5BDB").palette
        assert DesignTokens.from_seed(RGBColor(0x3B, 0x5B, 0xDB)).palette == ref
        assert DesignTokens.from_seed((0x3B, 0x5B, 0xDB)).palette == ref

    def it_keeps_primary_equal_to_the_seed(self):
        tokens = DesignTokens.from_seed("#3B5BDB")
        assert tokens.palette["primary"] == RGBColor(0x3B, 0x5B, 0xDB)

    def it_rejects_an_unknown_harmony(self):
        with pytest.raises(ValueError):
            DesignTokens.from_seed("#3B5BDB", harmony="bogus")

    def it_differs_between_harmonies(self):
        comp = DesignTokens.from_seed("#3B5BDB", harmony="complementary")
        tri = DesignTokens.from_seed("#3B5BDB", harmony="triadic")
        assert comp.palette["secondary"] != tri.palette["secondary"]


class DescribeValidateColorBlindness:
    @pytest.mark.parametrize(
        "kind", ["deuteranopia", "protanopia", "tritanopia"]
    )
    def it_returns_a_list_of_pairs(self, kind):
        tokens = DesignTokens.from_seed("#3B5BDB")
        result = tokens.validate_color_blindness(kind)
        assert isinstance(result, list)
        for pair in result:
            assert isinstance(pair, tuple)
            assert len(pair) == 2
            assert pair[0] < pair[1]  # alphabetically ordered, distinct

    def it_flags_a_known_red_green_confusion(self):
        # A saturated red and a saturated green — distinct to typical
        # vision, classically confusable under deuteranopia.
        tokens = DesignTokens.from_dict(
            {"palette": {"go": "#22AA22", "stop": "#CC2222"}}
        )
        pairs = tokens.validate_color_blindness("deuteranopia")
        assert ("go", "stop") in pairs

    def it_rejects_an_unknown_kind(self):
        with pytest.raises(ValueError):
            DesignTokens.from_seed("#3B5BDB").validate_color_blindness("x")
