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
                "typography": {"heading": {"family": "Inter", "size": 24}},
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
# Length units, aliases and fail-closed keys
# ---------------------------------------------------------------------------


class DescribeTokenLengthUnits:
    """A bare number in a length field is points; ``Length`` objects are exact."""

    def it_reads_a_bare_integer_as_points(self):
        tokens = DesignTokens.from_dict(
            {
                "typography": {"heading": {"family": "Inter", "size": 36}},
                "radii": {"md": 8},
                "spacings": {"lg": 32},
                "shadows": {"card": {"blur_radius": 8, "distance": 2}},
            }
        )
        assert tokens.typography["heading"].size == Pt(36)
        assert tokens.radii["md"] == Pt(8)
        assert tokens.spacings["lg"] == Pt(32)
        assert tokens.shadows["card"].blur_radius == Pt(8)
        assert tokens.shadows["card"].distance == Pt(2)

    def it_reads_an_integer_and_a_float_identically(self):
        # JSON serialisers write ``36`` for ``36.0``; both must mean 36pt.
        as_int = DesignTokens.from_dict({"radii": {"md": 8}, "spacings": {"sm": 4}})
        as_float = DesignTokens.from_dict({"radii": {"md": 8.0}, "spacings": {"sm": 4.0}})
        assert as_int == as_float

    def it_keeps_Length_objects_exact(self):
        from power_pptx.util import Inches

        tokens = DesignTokens.from_dict(
            {"radii": {"a": Emu(5), "b": Pt(8), "c": Inches(0.25), "d": Emu(101600)}}
        )
        assert tokens.radii == {
            "a": Emu(5),
            "b": Emu(101600),
            "c": Emu(228600),
            "d": Emu(101600),
        }

    @pytest.mark.parametrize("emu", [12700, 101600, 457200])
    def it_still_reads_a_large_bare_integer_as_emu(self, emu):
        # Backward compatibility for callers who passed raw EMU integers.
        tokens = DesignTokens.from_dict({"radii": {"md": emu}})
        assert tokens.radii["md"] == Emu(emu)

    def it_reads_the_largest_small_integer_as_points(self):
        assert DesignTokens.from_dict({"spacings": {"x": 12699}}).spacings["x"] == Pt(12699)

    def it_reads_an_integer_override_as_points(self):
        tokens = DesignTokens.from_preset("modern_light").with_overrides(
            {"typography.heading.size": 40, "radii.md": 12, "shadows.card.distance": 3}
        )
        assert tokens.typography["heading"].size == Pt(40)
        assert tokens.radii["md"] == Pt(12)
        assert tokens.shadows["card"].distance == Pt(3)

    def it_reads_integers_in_a_yaml_brand_file_as_points(self, tmp_path):
        pytest.importorskip("yaml")
        path = tmp_path / "brand.yml"
        path.write_text(
            "typography:\n  heading: {family: Inter, size: 36}\nradii: {md: 8}\n",
            encoding="utf-8",
        )
        tokens = DesignTokens.from_yaml(path)
        assert tokens.typography["heading"].size == Pt(36)
        assert tokens.radii["md"] == Pt(8)

    def it_names_the_token_path_when_a_font_size_is_out_of_range(self):
        with pytest.raises(ValueError, match=r"typography\.heading\.size: font size must be"):
            DesignTokens.from_dict(
                {"typography": {"heading": {"family": "Inter", "size": Emu(36)}}}
            )
        with pytest.raises(ValueError, match=r"typography\.heading\.size: font size must be"):
            DesignTokens.from_preset("modern_light").with_overrides(
                {"typography.heading.size": 0.5}
            )

    @pytest.mark.parametrize("bad", [-5, -5.0, float("nan"), float("inf")])
    def it_rejects_a_negative_or_non_finite_bare_number(self, bad):
        with pytest.raises(ValueError, match=r"radii\.md: a length must be"):
            DesignTokens.from_dict({"radii": {"md": bad}})

    @pytest.mark.parametrize("bad", [True, "36", [8]])
    def it_rejects_a_value_that_is_not_a_number_or_Length(self, bad):
        with pytest.raises(TypeError, match=r"radii\.md: cannot coerce"):
            DesignTokens.from_dict({"radii": {"md": bad}})


class DescribeShadowTokenKeys:
    def it_accepts_blur_as_an_alias_for_blur_radius(self):
        token = ShadowToken.from_value({"blur": 18.0, "distance": 4.0, "alpha": 0.18})
        assert token.blur_radius == Pt(18)
        assert token == ShadowToken.from_value(
            {"blur_radius": 18.0, "distance": 4.0, "alpha": 0.18}
        )

    def it_accepts_the_blur_alias_in_overrides(self):
        tokens = DesignTokens.from_preset("modern_light")
        dotted = tokens.with_overrides({"shadows.card.blur": 20})
        nested = tokens.with_overrides({"shadows": {"card": {"blur": 22}}})
        assert dotted.shadows["card"].blur_radius == Pt(20)
        assert nested.shadows["card"].blur_radius == Pt(22)

    def it_rejects_blur_and_blur_radius_together(self):
        with pytest.raises(ValueError, match="'blur' and 'blur_radius' are the same field"):
            ShadowToken.from_value({"blur": 4, "blur_radius": 8})

    def it_rejects_an_unknown_key_with_a_hint(self):
        with pytest.raises(ValueError) as exc:
            DesignTokens.from_dict(
                {"shadows": {"card": {"blurr_radius": 9.0, "colour": "#FF0000"}}}
            )
        message = str(exc.value)
        assert message.startswith("shadows.card: unknown shadow key(s)")
        assert "'blurr_radius' (did you mean 'blur_radius'?)" in message
        assert "'colour' (did you mean 'color'?)" in message

    def it_checks_alpha_in_an_override_too(self):
        with pytest.raises(ValueError, match=r"shadows\.card\.alpha: shadow alpha"):
            DesignTokens.from_preset("modern_light").with_overrides({"shadows.card.alpha": 5})


class DescribeTypographyTokenKeys:
    def it_rejects_an_unknown_key_with_a_hint(self):
        with pytest.raises(
            ValueError,
            match=r"typography\.body: unknown typography key\(s\) 'sise' "
            r"\(did you mean 'size'\?\)",
        ):
            DesignTokens.from_dict({"typography": {"body": {"family": "Inter", "sise": 18.0}}})

    def it_rejects_a_non_boolean_bold(self):
        with pytest.raises(ValueError, match=r"typography\.body\.bold: expected true"):
            DesignTokens.from_dict({"typography": {"body": {"family": "Inter", "bold": "yes"}}})

    def it_keeps_None_fields_unset(self):
        token = TypographyToken.from_value({"family": "Inter", "size": None, "bold": None})
        assert token == TypographyToken(family="Inter")


class DescribeTokenSections:
    def it_rejects_a_misspelt_section_name(self):
        with pytest.raises(
            ValueError, match=r"unknown token section 'palete' \(did you mean 'palette'\?\)"
        ):
            DesignTokens.from_dict({"palete": {"primary": "#FF0000"}})

    def it_names_a_section_that_is_not_a_mapping(self):
        with pytest.raises(ValueError, match=r"palette: expected a mapping"):
            DesignTokens.from_dict({"palette": ["#FF0000"]})

    def it_accepts_a_json_style_rgb_list(self):
        tokens = DesignTokens.from_dict({"palette": {"primary": [255, 102, 0]}})
        assert tokens.palette["primary"] == RGBColor(0xFF, 0x66, 0x00)

    def it_names_the_palette_slot_for_a_bad_color(self):
        with pytest.raises(ValueError, match=r"palette\.primary: hex color string"):
            DesignTokens.from_dict({"palette": {"primary": "#GGGGGG"}})

    def it_suggests_the_closest_preset(self):
        with pytest.raises(ValueError, match=r"did you mean 'modern_light'\?"):
            DesignTokens.from_preset("modern-light")


class DescribeOverrideKeys:
    def it_rejects_a_path_that_is_too_deep(self):
        with pytest.raises(ValueError, match="is too deep"):
            DesignTokens.from_preset("modern_light").with_overrides(
                {"typography.heading.size.unit": Pt(10)}
            )

    def it_rejects_overrides_that_are_not_a_mapping(self):
        with pytest.raises(ValueError, match="token overrides must be a mapping"):
            DesignTokens.from_preset("modern_light").with_overrides(["palette.primary"])

    def it_checks_the_category_before_the_depth(self):
        with pytest.raises(ValueError, match="unknown override category 'nope'"):
            DesignTokens().with_overrides({"nope.a.b.c": 1})

    @pytest.mark.parametrize("key", ["palette.primary.red", "radii.md.unit", "spacings.sm.x"])
    def it_rejects_a_sub_field_outside_typography_and_shadows(self, key):
        with pytest.raises(
            ValueError,
            match=rf"sub-field override '{key}' only supported on typography and shadows",
        ):
            DesignTokens.from_preset("modern_light").with_overrides({key: 1})

    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({1: "#FF0000"}, "override keys must be non-empty strings; got 1$"),
            ({"": "#FF0000"}, "override keys must be non-empty strings; got ''$"),
            (
                {"palette": {2: "#FF0000"}},
                "override keys must be non-empty strings; got 2 under 'palette'$",
            ),
            (
                {"typography": {"heading": {"": 1}}},
                "got '' under 'typography.heading'$",
            ),
        ],
    )
    def it_rejects_keys_that_are_not_non_empty_strings(self, overrides, message):
        with pytest.raises(ValueError, match=message):
            DesignTokens().with_overrides(overrides)


class DescribeWithOverridesSlots:
    """A slot given a token replaces it; a mapping merges field by field."""

    def it_merges_a_mapping_for_a_typography_slot_into_the_existing_token(self):
        base = DesignTokens.from_preset("modern_light")

        tokens = base.with_overrides({"typography.heading": {"family": "Arial", "size": 9}})

        assert base.typography["heading"].bold is True
        assert tokens.typography["heading"] == TypographyToken(
            family="Arial", size=Pt(9), bold=True
        )

    def it_replaces_a_typography_slot_from_a_token_or_a_family_name(self):
        token = TypographyToken(family="Inter", bold=True)

        tokens = DesignTokens().with_overrides(
            {"typography": {"heading": token, "body": "Georgia"}}
        )

        assert tokens.typography["heading"] is token
        assert tokens.typography["body"] == TypographyToken(family="Georgia")

    def it_builds_a_new_shadow_slot_from_a_mapping_and_takes_a_token_whole(self):
        token = ShadowToken(distance=Pt(1))

        tokens = DesignTokens().with_overrides(
            {"shadows.card": {"blur_radius": 4}, "shadows": {"lift": token}}
        )

        assert tokens.shadows["card"] == ShadowToken(blur_radius=Pt(4))
        assert tokens.shadows["lift"] is token

    @pytest.mark.parametrize(
        ("key", "error"), [("typography.heading", TypeError), ("shadows.card", TypeError)]
    )
    def it_rejects_a_slot_value_it_cannot_build_a_token_from(self, key, error):
        with pytest.raises(error, match=rf"{key}: cannot build"):
            DesignTokens().with_overrides({key: 5})

    def it_starts_a_new_typography_slot_from_calibri_for_a_field_override(self):
        tokens = DesignTokens().with_overrides({"typography.caption.size": 9})

        assert tokens.typography["caption"] == TypographyToken(family="Calibri", size=Pt(9))

    def it_starts_a_new_shadow_slot_from_the_defaults_for_a_field_override(self):
        tokens = DesignTokens().with_overrides({"shadows.card.blur": 6})

        assert tokens.shadows["card"] == ShadowToken(blur_radius=Pt(6))

    def it_merges_a_field_into_an_existing_shadow(self):
        base = DesignTokens().with_overrides({"shadows.card": {"distance": 2}})

        tokens = base.with_overrides({"shadows.card.alpha": 0.5})

        assert tokens.shadows["card"] == ShadowToken(distance=Pt(2), alpha=0.5)
        assert base.shadows["card"] == ShadowToken(distance=Pt(2))

    def it_leaves_the_other_categories_as_they_were(self):
        base = DesignTokens.from_preset("modern_light").with_overrides(
            {"spacings.sm": 4, "radii.md": 8}
        )

        tokens = base.with_overrides({"palette.primary": "#010203"})

        assert tokens.palette["primary"] == RGBColor(1, 2, 3)
        assert tokens.typography == base.typography
        assert tokens.radii == base.radii
        assert tokens.shadows == base.shadows
        assert tokens.spacings == base.spacings


class DescribeFromPptxSources:
    def it_accepts_a_pathlib_path(self, tmp_path):
        path = tmp_path / "theme.pptx"
        Presentation().save(str(path))
        tokens = DesignTokens.from_pptx(path)
        assert "accent1" in tokens.palette
        assert "heading" in tokens.typography

    def it_accepts_a_binary_file_object(self, tmp_path):
        path = tmp_path / "theme.pptx"
        Presentation().save(str(path))
        with open(path, "rb") as stream:
            tokens = DesignTokens.from_pptx(stream)
        assert "accent1" in tokens.palette
