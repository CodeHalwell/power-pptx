"""Unit-test suite for the high-level `power_pptx.theme` module."""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx.dml.color import RGBColor
from power_pptx.enum.dml import MSO_THEME_COLOR
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.theme import Theme, ThemeColors, ThemeFonts
from power_pptx.util import Inches

# The twelve slots a theme's <a:clrScheme> actually holds, in schema order (bg1/bg2/tx1/tx2
# are aliases for lt1/lt2/dk1/dk2 and never appear there).
_CANONICAL_SLOTS = (
    "dk1",
    "lt1",
    "dk2",
    "lt2",
    "accent1",
    "accent2",
    "accent3",
    "accent4",
    "accent5",
    "accent6",
    "hlink",
    "folHlink",
)


@pytest.fixture
def prs():
    return Presentation()


@pytest.fixture
def theme(prs) -> Theme:
    return prs.theme


class DescribeThemeColors:
    def it_reads_a_theme_color_slot(self, theme):
        rgb = theme.colors[MSO_THEME_COLOR.ACCENT_1]
        assert isinstance(rgb, RGBColor)

    def it_writes_a_theme_color_slot(self, theme):
        theme.colors[MSO_THEME_COLOR.ACCENT_2] = RGBColor(0x12, 0x34, 0x56)
        assert theme.colors[MSO_THEME_COLOR.ACCENT_2] == RGBColor(0x12, 0x34, 0x56)

    def it_writes_to_the_canonical_slot_for_an_alias(self, theme):
        # bg1 is an alias for lt1 — the write should land on lt1
        theme.colors[MSO_THEME_COLOR.BACKGROUND_1] = RGBColor(0xFF, 0x00, 0xFF)
        assert theme.colors[MSO_THEME_COLOR.BACKGROUND_1] == RGBColor(0xFF, 0x00, 0xFF)

    def it_raises_when_assigning_a_non_rgb_value(self, theme):
        with pytest.raises(TypeError):
            theme.colors[MSO_THEME_COLOR.ACCENT_1] = "purple"  # type: ignore[assignment]

    def it_raises_when_assigning_with_a_non_theme_color_key(self, theme):
        with pytest.raises(TypeError):
            theme.colors["accent1"] = RGBColor(0, 0, 0)  # type: ignore[index]

    def it_inserts_a_missing_slot_at_the_schema_defined_position(self, prs):
        from power_pptx.oxml.ns import qn

        clr_scheme = prs.theme._theme_elm.find(  # type: ignore[attr-defined]
            f"{qn('a:themeElements')}/{qn('a:clrScheme')}"
        )
        # Remove accent3 to force the writer's missing-slot path
        accent3 = clr_scheme.find(qn("a:accent3"))
        clr_scheme.remove(accent3)

        prs.theme.colors[MSO_THEME_COLOR.ACCENT_3] = RGBColor(0x12, 0x34, 0x56)

        order = [c.tag.rsplit("}", 1)[-1] for c in clr_scheme]
        # Schema-required ordering must be preserved
        assert order.index("accent2") + 1 == order.index("accent3")
        assert order.index("accent3") + 1 == order.index("accent4")

    def it_overwrites_a_non_srgb_color_child(self, prs):
        # Replace the existing srgbClr in the accent3 slot with sysClr,
        # then verify the writer drops the sysClr and replaces with srgbClr.
        from lxml import etree

        from power_pptx.oxml.ns import qn

        slot = prs.theme._theme_elm.find(  # type: ignore[attr-defined]
            f"{qn('a:themeElements')}/{qn('a:clrScheme')}/{qn('a:accent3')}"
        )
        for child in list(slot):
            slot.remove(child)
        sys_clr = etree.SubElement(slot, qn("a:sysClr"))
        sys_clr.set("val", "windowText")
        sys_clr.set("lastClr", "000000")

        prs.theme.colors[MSO_THEME_COLOR.ACCENT_3] = RGBColor(0xAA, 0xBB, 0xCC)
        assert slot.find(qn("a:sysClr")) is None
        assert slot.find(qn("a:srgbClr")).get("val") == "AABBCC"


class DescribeThemeFonts:
    def it_reads_major_and_minor(self, theme):
        assert isinstance(theme.fonts.major, str)
        assert isinstance(theme.fonts.minor, str)

    def it_writes_major_typeface(self, theme):
        theme.fonts.major = "Inter"
        assert theme.fonts.major == "Inter"

    def it_writes_minor_typeface(self, theme):
        theme.fonts.minor = "Source Sans Pro"
        assert theme.fonts.minor == "Source Sans Pro"

    def it_rejects_empty_typeface(self, theme):
        with pytest.raises(TypeError):
            theme.fonts.major = ""


class DescribeThemeApply:
    def it_copies_colors_and_fonts_from_another_theme(self):
        src_prs = Presentation()
        src_prs.theme.colors[MSO_THEME_COLOR.ACCENT_1] = RGBColor(0x00, 0x80, 0xC0)
        src_prs.theme.fonts.major = "Inter"
        src_prs.theme.fonts.minor = "Inter"

        dst_prs = Presentation()
        dst_prs.theme.apply(src_prs.theme)

        assert dst_prs.theme.colors[MSO_THEME_COLOR.ACCENT_1] == RGBColor(0x00, 0x80, 0xC0)
        assert dst_prs.theme.fonts.major == "Inter"
        assert dst_prs.theme.fonts.minor == "Inter"

    def it_rejects_non_theme_arguments(self, theme):
        with pytest.raises(TypeError):
            theme.apply("not a theme")  # type: ignore[arg-type]

    # -- rebind_shape_colors: which slot a literal color is rebound to -------------------

    @staticmethod
    def _rebind(palette: dict[str, RGBColor], literal: RGBColor):
        """Give a deck `palette`, fill a shape with `literal`, re-skin the deck, return the
        shape's fill element and the number of rebinds `apply()` reported."""
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        for name, rgb in palette.items():
            prs.theme.colors[MSO_THEME_COLOR.from_xml(name)] = rgb
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1)
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = literal

        other = Presentation().theme
        other.colors[MSO_THEME_COLOR.ACCENT_1] = RGBColor(0xFF, 0x00, 0x00)
        n = prs.theme.apply(other, rebind_shape_colors=True, presentation=prs)
        return shape.fill._xPr.xpath("a:solidFill/a:schemeClr/@val"), n

    @pytest.mark.parametrize("slot_name", _CANONICAL_SLOTS)
    def it_rebinds_a_literal_to_its_canonical_slot_never_to_an_alias(self, slot_name):
        # -- every slot gets its own color, so each literal matches exactly one slot. The
        # -- light slots used to come back as the bg1 / bg2 aliases while the dark ones came
        # -- back as dk1 / dk2, because MSO_THEME_COLOR lists BACKGROUND_* before LIGHT_*. --
        palette = {
            name: RGBColor(0x10 + i, 0x20 + i, 0x30 + i) for i, name in enumerate(_CANONICAL_SLOTS)
        }

        val, n = self._rebind(palette, palette[slot_name])

        assert val == [slot_name]
        assert n == 1

    @pytest.mark.parametrize(
        ("shared", "expected"),
        [
            # -- ties go to the slot that comes first in the color scheme's schema order --
            (("lt1", "lt2"), "lt1"),
            (("dk1", "accent3"), "dk1"),
            (("dk2", "accent1"), "dk2"),
            (("accent1", "accent2"), "accent1"),
            (("accent6", "hlink"), "accent6"),
        ],
    )
    def and_it_breaks_ties_between_slots_sharing_a_color_in_schema_order(self, shared, expected):
        palette = {
            name: RGBColor(0x10 + i, 0x20 + i, 0x30 + i) for i, name in enumerate(_CANONICAL_SLOTS)
        }
        twin = RGBColor(0xAB, 0xCD, 0xEF)
        for name in shared:
            palette[name] = twin

        val, n = self._rebind(palette, twin)

        assert val == [expected]
        assert n == 1


class DescribeThemeName:
    def it_reads_name(self, theme):
        # default theme has a name attribute
        assert isinstance(theme.name, str)

    def it_writes_name(self, theme):
        theme.name = "Brand"
        assert theme.name == "Brand"


class DescribeThemeAccessor:
    """`prs.theme` should be a Theme, not a transient parse."""

    def it_returns_the_same_underlying_element_on_repeated_access(self, prs):
        first = prs.theme
        second = prs.theme
        # Theme objects are recreated on each call (cheap) but they
        # should wrap the *same* underlying element so writes persist.
        assert first._theme_elm is second._theme_elm  # type: ignore[attr-defined]

    def it_exposes_colors_and_fonts(self, theme):
        assert isinstance(theme.colors, ThemeColors)
        assert isinstance(theme.fonts, ThemeFonts)


# ---------------------------------------------------------------------------
# to_dark_mode
# ---------------------------------------------------------------------------


def _relative_luminance(rgb) -> float:
    r, g, b = (int(rgb[0]) / 255.0, int(rgb[1]) / 255.0, int(rgb[2]) / 255.0)

    def _ch(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _ch(r) + 0.7152 * _ch(g) + 0.0722 * _ch(b)


def _contrast(a, b) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    light, dark = (la, lb) if la >= lb else (lb, la)
    return (light + 0.05) / (dark + 0.05)


class DescribeThemeToDarkMode:
    def it_swaps_the_dark_light_background_text_pairs(self, theme):
        before_dk1 = theme.colors[MSO_THEME_COLOR.DARK_1]
        before_lt1 = theme.colors[MSO_THEME_COLOR.LIGHT_1]
        before_dk2 = theme.colors[MSO_THEME_COLOR.DARK_2]
        before_lt2 = theme.colors[MSO_THEME_COLOR.LIGHT_2]

        theme.to_dark_mode()

        assert theme.colors[MSO_THEME_COLOR.LIGHT_1] == before_dk1
        assert theme.colors[MSO_THEME_COLOR.DARK_1] == before_lt1
        assert theme.colors[MSO_THEME_COLOR.LIGHT_2] == before_dk2
        assert theme.colors[MSO_THEME_COLOR.DARK_2] == before_lt2

    def it_returns_self_for_chaining(self, theme):
        assert theme.to_dark_mode() is theme

    def it_keeps_accents_above_aa_contrast_on_the_new_background(self, theme):
        # A deliberately low-contrast (near-black) accent must be lifted.
        theme.colors[MSO_THEME_COLOR.ACCENT_1] = RGBColor(0x0A, 0x0A, 0x0A)
        theme.to_dark_mode()
        bg = theme.colors[MSO_THEME_COLOR.LIGHT_1]
        for slot in (
            MSO_THEME_COLOR.ACCENT_1,
            MSO_THEME_COLOR.ACCENT_2,
            MSO_THEME_COLOR.ACCENT_3,
        ):
            accent = theme.colors[slot]
            assert _contrast(accent, bg) >= 4.5 - 1e-6

    def it_round_trips_after_dark_mode(self):
        from tests.integration.round_trip import assert_round_trip

        prs = Presentation()
        prs.theme.colors[MSO_THEME_COLOR.ACCENT_1] = RGBColor(0x12, 0x80, 0xC0)
        prs.theme.to_dark_mode()
        assert_round_trip(prs)

    def it_stays_schema_valid_after_dark_mode(self):
        import io

        from tests.schema.oxml_schema_validator import (
            iter_schema_violations,
            schema_validation_available,
        )

        if not schema_validation_available():
            pytest.skip("schema validation unavailable (no lxml/XSDs)")

        prs = Presentation()
        prs.theme.colors[MSO_THEME_COLOR.ACCENT_1] = RGBColor(0x0A, 0x0A, 0x0A)
        prs.theme.to_dark_mode()
        buf = io.BytesIO()
        prs.save(buf)
        violations = list(iter_schema_violations(buf.getvalue()))
        assert not violations, violations
