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
        t = TypographyToken.from_value({"family": "Inter", "size": Pt(14), "bold": True})
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
        tokens = DesignTokens.from_dict({"palette": {"primary": "#3C2F80", "secondary": "FF6600"}})
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
        base = DesignTokens.from_dict({"palette": {"primary": "#000000", "secondary": "#FFFFFF"}})
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

        tokens = DesignTokens.from_dict(
            {
                "palette": {"primary": "#000000"},
                "typography": {"heading": {"family": "Inter", "size": 24.0}},
            }
        )
        result = tokens.with_overrides(
            {
                "palette": {"primary": "#FF6600"},
                "typography": {"heading": {"size": Pt(40)}},
            }
        )
        assert str(result.palette["primary"]) == "FF6600"
        assert result.typography["heading"].size == Pt(40)

    def it_accepts_dotted_keys(self):
        from power_pptx.design.tokens import DesignTokens
        from power_pptx.util import Pt

        tokens = DesignTokens.from_dict({"palette": {"primary": "#000000"}})
        result = tokens.with_overrides(
            {
                "palette.primary": "#11AA22",
                "typography.heading.size": Pt(20),
            }
        )
        assert str(result.palette["primary"]) == "11AA22"
        assert result.typography["heading"].size == Pt(20)

    def it_accepts_mixed_styles(self):
        from power_pptx.design.tokens import DesignTokens
        from power_pptx.util import Pt

        tokens = DesignTokens.from_dict({"palette": {"primary": "#000000"}})
        result = tokens.with_overrides(
            {
                "palette.primary": "#AA00BB",
                "typography": {"heading": {"size": Pt(28)}},
            }
        )
        assert str(result.palette["primary"]) == "AA00BB"
        assert result.typography["heading"].size == Pt(28)


# ---------------------------------------------------------------------------
# DesignTokens.from_seed
# ---------------------------------------------------------------------------

_FROM_SEED_KEYS = {
    "primary",
    "secondary",
    "accent",
    "neutral",
    "muted",
    "surface",
    "background",
    "text",
    "on_primary",
    "lt1",
    "lt2",
    "positive",
    "negative",
    "success",
    "danger",
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
    @pytest.mark.parametrize("kind", ["deuteranopia", "protanopia", "tritanopia"])
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
        tokens = DesignTokens.from_dict({"palette": {"go": "#22AA22", "stop": "#CC2222"}})
        pairs = tokens.validate_color_blindness("deuteranopia")
        assert ("go", "stop") in pairs

    def it_rejects_an_unknown_kind(self):
        with pytest.raises(ValueError):
            DesignTokens.from_seed("#3B5BDB").validate_color_blindness("x")


# ---------------------------------------------------------------------------
# Coercion: colours from JSON/YAML lists, unit-less lengths, shadow alpha
# ---------------------------------------------------------------------------

_UNIT_HINT = r"use a float for points, or Pt\(\.\.\.\)"


class DescribeColorCoercionFromJsonShapes:
    """JSON / YAML have no tuples; a 3-item list must work as an RGB triple."""

    def it_coerces_a_list_of_three_ints(self):
        tokens = DesignTokens.from_dict({"palette": {"primary": [51, 51, 51]}})
        assert tokens.palette["primary"] == RGBColor(51, 51, 51)

    def it_coerces_a_list_in_an_override(self):
        tokens = DesignTokens.from_preset("modern_light")
        assert tokens.with_overrides({"palette.primary": [1, 2, 3]}).palette["primary"] == RGBColor(
            1, 2, 3
        )

    def it_coerces_a_list_in_a_typography_color(self):
        tokens = DesignTokens.from_dict(
            {"typography": {"body": {"family": "Inter", "color": [10, 20, 30]}}}
        )
        assert tokens.typography["body"].color == RGBColor(10, 20, 30)

    @pytest.mark.parametrize("bad", [[], [1, 2], [1, 2, 3, 4]])
    def it_rejects_a_list_of_the_wrong_length(self, bad):
        with pytest.raises(TypeError, match="cannot coerce"):
            DesignTokens.from_dict({"palette": {"primary": bad}})

    def it_rejects_a_channel_outside_0_to_255(self):
        with pytest.raises(ValueError):
            DesignTokens.from_dict({"palette": {"primary": [0, 0, 300]}})


class DescribeFontSizeUnits:
    """A bare int is EMU; a size that small is a unit slip, so it fails loudly."""

    def it_rejects_a_bare_int_size_and_names_the_token(self):
        with pytest.raises(ValueError, match=rf"tokens\.typography\.heading\.size.*{_UNIT_HINT}"):
            DesignTokens.from_dict({"typography": {"heading": {"family": "Inter", "size": 36}}})

    def it_says_what_the_int_was_read_as(self):
        with pytest.raises(ValueError, match=r"36 EMU"):
            DesignTokens.from_dict({"typography": {"heading": {"family": "Inter", "size": 36}}})

    def it_reads_a_float_size_as_points(self):
        tokens = DesignTokens.from_dict(
            {"typography": {"heading": {"family": "Inter", "size": 36.0}}}
        )
        assert tokens.typography["heading"].size == Pt(36)

    def it_accepts_a_Pt_size(self):
        tokens = DesignTokens.from_dict(
            {"typography": {"heading": {"family": "Inter", "size": Pt(36)}}}
        )
        assert tokens.typography["heading"].size == Pt(36)

    def it_still_accepts_an_int_that_really_is_a_font_sized_emu_count(self):
        t = TypographyToken.from_value({"family": "Inter", "size": 457200})
        assert t.size == Pt(36)

    @pytest.mark.parametrize("size", [0.0, 0.5, Pt(0.5), Emu(24), -12.0])
    def it_rejects_any_size_below_one_point(self, size):
        with pytest.raises(ValueError, match=rf"tokens\.typography\.body\.size.*{_UNIT_HINT}"):
            DesignTokens.from_dict({"typography": {"body": {"family": "Inter", "size": size}}})

    def it_accepts_exactly_one_point(self):
        tokens = DesignTokens.from_dict({"typography": {"body": {"family": "Inter", "size": 1.0}}})
        assert tokens.typography["body"].size == Pt(1)

    @pytest.mark.parametrize("size", [4001.0, 457200.0, 5_000_000_000])
    def it_rejects_a_size_above_the_ooxml_maximum(self, size):
        with pytest.raises(ValueError, match=r"tokens\.typography\.body\.size"):
            DesignTokens.from_dict({"typography": {"body": {"family": "Inter", "size": size}}})

    def it_names_the_token_when_called_directly(self):
        with pytest.raises(ValueError, match=r"size.*EMU"):
            TypographyToken.from_value({"family": "Inter", "size": 36})

    def it_validates_a_size_override_on_a_sub_field(self):
        tokens = DesignTokens.from_preset("modern_light")
        with pytest.raises(ValueError, match=rf"tokens\.typography\.heading\.size.*{_UNIT_HINT}"):
            tokens.with_overrides({"typography.heading.size": 40})

    def it_validates_a_size_override_in_a_nested_dict(self):
        tokens = DesignTokens.from_preset("modern_light")
        with pytest.raises(ValueError, match=r"tokens\.typography\.heading\.size"):
            tokens.with_overrides({"typography": {"heading": {"size": 40}}})

    def it_validates_a_size_inside_a_whole_token_override(self):
        tokens = DesignTokens.from_preset("modern_light")
        with pytest.raises(ValueError, match=r"tokens\.typography\.heading\.size"):
            tokens.with_overrides({"typography.heading": {"family": "Inter", "size": 40}})

    def it_accepts_a_float_size_override(self):
        tokens = DesignTokens.from_preset("modern_light").with_overrides(
            {"typography.heading.size": 40.0}
        )
        assert tokens.typography["heading"].size == Pt(40)


class DescribeRadiusAndSpacingUnits:
    """A radius / spacing given as a tiny bare int would silently be ~0 pt."""

    @pytest.mark.parametrize("category", ["radii", "spacings"])
    def it_rejects_a_tiny_bare_int_and_names_the_token(self, category):
        with pytest.raises(ValueError, match=rf"tokens\.{category}\.md.*{_UNIT_HINT}"):
            DesignTokens.from_dict({category: {"md": 8}})

    @pytest.mark.parametrize("value", [1, 8, 99, -8])
    def it_rejects_any_nonzero_int_below_100_emu(self, value):
        with pytest.raises(ValueError, match=r"tokens\.radii\.md"):
            DesignTokens.from_dict({"radii": {"md": value}})

    @pytest.mark.parametrize("category", ["radii", "spacings"])
    def it_accepts_zero_which_has_no_unit_to_get_wrong(self, category):
        tokens = DesignTokens.from_dict({category: {"none": 0}})
        assert getattr(tokens, category)["none"] == Emu(0)

    @pytest.mark.parametrize("category", ["radii", "spacings"])
    def it_accepts_floats_as_points(self, category):
        tokens = DesignTokens.from_dict({category: {"md": 8.0}})
        assert getattr(tokens, category)["md"] == Pt(8)

    def it_accepts_a_Length_of_any_size(self):
        tokens = DesignTokens.from_dict({"radii": {"hairline": Emu(8), "lg": Pt(16)}})
        assert tokens.radii["hairline"] == Emu(8)
        assert tokens.radii["lg"] == Pt(16)

    def it_accepts_an_int_of_at_least_100_emu(self):
        tokens = DesignTokens.from_dict({"spacings": {"md": 100, "lg": 203200}})
        assert tokens.spacings["md"] == Emu(100)
        assert tokens.spacings["lg"] == Pt(16)

    def it_does_not_read_a_bool_as_a_one_emu_length(self):
        with pytest.raises(TypeError, match="cannot coerce"):
            DesignTokens.from_dict({"radii": {"md": True}})

    @pytest.mark.parametrize(
        ("key", "path"),
        [("radii.md", r"tokens\.radii\.md"), ("spacings.md", r"tokens\.spacings\.md")],
    )
    def it_validates_dotted_overrides(self, key, path):
        tokens = DesignTokens.from_preset("modern_light")
        with pytest.raises(ValueError, match=rf"{path}.*{_UNIT_HINT}"):
            tokens.with_overrides({key: 8})

    def it_validates_nested_overrides(self):
        tokens = DesignTokens.from_preset("modern_light")
        with pytest.raises(ValueError, match=r"tokens\.radii\.lg"):
            tokens.with_overrides({"radii": {"lg": 16}})

    def it_accepts_float_overrides(self):
        tokens = DesignTokens.from_preset("modern_light").with_overrides({"radii.md": 12.0})
        assert tokens.radii["md"] == Pt(12)


class DescribeShadowExtentUnits:
    @pytest.mark.parametrize("field", ["blur_radius", "distance"])
    def it_rejects_a_tiny_bare_int_and_names_the_token(self, field):
        with pytest.raises(ValueError, match=rf"tokens\.shadows\.card\.{field}.*{_UNIT_HINT}"):
            DesignTokens.from_dict({"shadows": {"card": {field: 8}}})

    def it_accepts_floats_as_points_and_zero(self):
        tokens = DesignTokens.from_dict({"shadows": {"card": {"blur_radius": 8.0, "distance": 0}}})
        assert tokens.shadows["card"].blur_radius == Pt(8)
        assert tokens.shadows["card"].distance == Emu(0)

    def it_validates_sub_field_overrides(self):
        tokens = DesignTokens.from_preset("modern_light")
        with pytest.raises(ValueError, match=r"tokens\.shadows\.card\.blur_radius"):
            tokens.with_overrides({"shadows.card.blur_radius": 8})


class DescribeShadowAlphaOverrides:
    """``with_overrides`` must apply the same [0, 1] rule as ``from_value``."""

    @pytest.mark.parametrize("alpha", [2.0, 1.01, -0.1, float("nan")])
    def it_rejects_an_out_of_range_alpha_override(self, alpha):
        tokens = DesignTokens.from_preset("modern_light")
        with pytest.raises(ValueError, match=r"tokens\.shadows\.card\.alpha.*\[0\.0, 1\.0\]"):
            tokens.with_overrides({"shadows.card.alpha": alpha})

    def it_rejects_an_out_of_range_alpha_in_a_nested_override(self):
        tokens = DesignTokens.from_preset("modern_light")
        with pytest.raises(ValueError, match=r"tokens\.shadows\.card\.alpha"):
            tokens.with_overrides({"shadows": {"card": {"alpha": 5}}})

    @pytest.mark.parametrize("alpha", [0, 0.5, 1, 1.0])
    def it_accepts_alpha_within_the_range(self, alpha):
        tokens = DesignTokens.from_preset("modern_light")
        result = tokens.with_overrides({"shadows.card.alpha": alpha})
        assert result.shadows["card"].alpha == float(alpha)

    def it_keeps_the_base_untouched_when_the_override_is_rejected(self):
        tokens = DesignTokens.from_preset("modern_light")
        before = tokens.shadows["card"].alpha
        with pytest.raises(ValueError):
            tokens.with_overrides({"shadows.card.alpha": 2.0})
        assert tokens.shadows["card"].alpha == before


class DescribeSectionShapes:
    """Each token category is a mapping; anything else is a clear ValueError."""

    @pytest.mark.parametrize("section", ["palette", "typography", "radii", "spacings", "shadows"])
    @pytest.mark.parametrize("bad", ["modern_blue", ["#FF0000"], 12])
    def it_rejects_a_non_mapping_category(self, section, bad):
        with pytest.raises(ValueError, match=rf"tokens\.{section} must be a mapping"):
            DesignTokens.from_dict({section: bad})

    def it_names_the_offending_value(self):
        with pytest.raises(ValueError, match=r"'str'.*modern_blue"):
            DesignTokens.from_dict({"palette": "modern_blue"})

    @pytest.mark.parametrize("section", ["palette", "typography", "radii", "spacings", "shadows"])
    def it_treats_a_null_category_as_empty(self, section):
        tokens = DesignTokens.from_dict({section: None})
        assert getattr(tokens, section) == {}

    def it_rejects_a_spec_that_is_not_a_mapping(self):
        with pytest.raises(ValueError, match="mapping"):
            DesignTokens.from_dict(None)  # pyright: ignore[reportArgumentType]


class DescribeOverrideKeyShapes:
    def it_rejects_a_key_with_too_many_segments(self):
        tokens = DesignTokens.from_preset("modern_light")
        with pytest.raises(ValueError, match="too many segments"):
            tokens.with_overrides({"typography.heading.size.bogus": Pt(99)})

    def it_still_rejects_a_sub_field_on_a_palette_entry(self):
        tokens = DesignTokens.from_preset("modern_light")
        with pytest.raises(ValueError, match="only supported on typography and shadows"):
            tokens.with_overrides({"palette.primary.x": "#000000"})


class DescribePresetNames:
    @pytest.mark.parametrize("name", [["modern_light"], None, 3])
    def it_rejects_a_non_string_preset_name_as_unknown(self, name):
        with pytest.raises(ValueError, match="Unknown preset"):
            DesignTokens.from_preset(name)  # pyright: ignore[reportArgumentType]


class DescribeNonNumericLengthsAndAlpha:
    """A value that is no number at all names its token too, not just a bad unit."""

    def it_names_the_token_when_a_font_size_is_text(self):
        # ``"36pt"`` is what a YAML author writes; it is not a unit this takes.
        with pytest.raises(TypeError, match=r"tokens\.typography\.heading\.size: cannot coerce"):
            DesignTokens.from_dict({"typography": {"heading": {"family": "Inter", "size": "36pt"}}})

    @pytest.mark.parametrize("category", ["radii", "spacings"])
    def it_names_the_token_when_a_radius_or_spacing_is_text(self, category):
        with pytest.raises(TypeError, match=rf"tokens\.{category}\.md: cannot coerce '8pt'"):
            DesignTokens.from_dict({category: {"md": "8pt"}})

    def it_names_the_token_when_a_shadow_extent_is_text(self):
        with pytest.raises(TypeError, match=r"tokens\.shadows\.card\.distance: cannot coerce"):
            DesignTokens.from_dict({"shadows": {"card": {"distance": "4pt"}}})

    @pytest.mark.parametrize("alpha", ["opaque", [0.5], {}])
    def it_names_the_token_when_alpha_is_not_a_number(self, alpha):
        with pytest.raises(ValueError, match=r"tokens\.shadows\.card\.alpha: .*must be a number"):
            DesignTokens.from_dict({"shadows": {"card": {"alpha": alpha}}})
