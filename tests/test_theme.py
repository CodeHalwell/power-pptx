"""Unit-test suite for the high-level `power_pptx.theme` module."""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx.dml.color import RGBColor
from power_pptx.enum.dml import MSO_THEME_COLOR
from power_pptx.theme import Theme, ThemeColors, ThemeFonts

from .unitutil.cxml import xml


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

    def it_keeps_its_own_font_where_the_other_theme_names_none(self):
        src_prs = Presentation()
        src_theme_elm = src_prs.theme._theme_elm  # type: ignore[attr-defined]
        for latin in src_theme_elm.xpath("a:themeElements/a:fontScheme/a:majorFont/a:latin"):
            del latin.attrib["typeface"]
        src_prs.theme.fonts.minor = "Inter"
        dst_prs = Presentation()
        major = dst_prs.theme.fonts.major

        rebound = dst_prs.theme.apply(src_prs.theme)

        assert rebound == 0
        assert dst_prs.theme.fonts.major == major
        assert dst_prs.theme.fonts.minor == "Inter"

    def it_rebinds_literal_colors_of_the_old_palette_on_every_slide(self, prs):
        from power_pptx.oxml.ns import qn
        from power_pptx.oxml.xmlchemy import OxmlElement
        from power_pptx.util import Inches

        old_accent = prs.theme.colors[MSO_THEME_COLOR.ACCENT_1]
        fills = []
        for color in (old_accent, RGBColor(0x12, 0x34, 0x56), old_accent):
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            shape = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
            shape.fill.solid()
            shape.fill.fore_color.rgb = color
            fills.append(shape._element.spPr.find(qn("a:solidFill")))
        srgbClr = fills[0][0]
        srgbClr.set("val", srgbClr.get("val").lower())
        for tag, val in (("a:alpha", "50000"), ("a:lumMod", "75000")):
            srgbClr.append(OxmlElement(tag))
            srgbClr[-1].set("val", val)
        new_prs = Presentation()
        new_prs.theme.colors[MSO_THEME_COLOR.ACCENT_1] = RGBColor(0xFF, 0x00, 0x00)

        rebound = prs.theme.apply(new_prs.theme, rebind_shape_colors=True, presentation=prs)

        assert rebound == 2
        assert [_without_nsdecls(fill.xml) for fill in fills] == [
            _without_nsdecls(xml(cxml))
            for cxml in (
                "a:solidFill/a:schemeClr{val=accent1}/(a:alpha{val=50000},a:lumMod{val=75000})",
                "a:solidFill/a:srgbClr{val=123456}",
                "a:solidFill/a:schemeClr{val=accent1}",
            )
        ]

    def it_rebinds_nothing_for_an_empty_palette(self, prs):
        from power_pptx.theme import _rebind_shape_colors

        assert _rebind_shape_colors(prs, {}) == 0


def _without_nsdecls(xml_str: str) -> str:
    import re

    return re.sub(r' xmlns:\w+="[^"]*"', "", xml_str)


class DescribeEmbeddedFontEntry:
    """`_add_embedded_font_entry()` keeps one `p:embeddedFont` per typeface."""

    def it_points_an_existing_weight_slot_at_the_new_font_part(self):
        from power_pptx.oxml import parse_xml
        from power_pptx.theme import _add_embedded_font_entry

        pres = parse_xml(
            b'<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/'
            b'main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships'
            b'"/>'
        )

        class _Presentation:
            _element = pres

        for typeface, weight, rId in (
            ("Inter", "bold", "rId1"),
            ("Inter", "regular", "rId2"),
            ("Lora", "italic", "rId3"),
            ("Inter", "bold", "rId4"),
        ):
            _add_embedded_font_entry(_Presentation, typeface, weight, rId)

        assert pres.get("embedTrueTypeFonts") == "1"
        assert pres.xml == xml(
            "p:presentation{embedTrueTypeFonts=1}/p:embeddedFontLst/("
            "p:embeddedFont/(p:font{typeface=Inter},p:regular{r:id=rId2},p:bold{r:id=rId4}),"
            "p:embeddedFont/(p:font{typeface=Lora},p:italic{r:id=rId3}))"
        )


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


_PALETTE_SLOTS = tuple(slot for slot in MSO_THEME_COLOR if slot.xml_value)


class DescribeRaiseContrast:
    """`_raise_contrast()` moves a color away from its background."""

    @pytest.mark.parametrize(
        ("rgb", "background"),
        [
            (RGBColor(0x0A, 0x0A, 0x0A), RGBColor(0x00, 0x00, 0x00)),
            (RGBColor(0x40, 0x20, 0x80), RGBColor(0x12, 0x12, 0x12)),
            (RGBColor(0xF0, 0xF0, 0x60), RGBColor(0xFF, 0xFF, 0xFF)),
            (RGBColor(0x80, 0xC0, 0xFF), RGBColor(0xF4, 0xF4, 0xF4)),
        ],
    )
    def it_reaches_the_contrast_target_on_either_kind_of_background(self, rgb, background):
        from power_pptx.theme import _raise_contrast

        fixed = _raise_contrast(rgb, background, 4.5)

        assert _contrast(fixed, background) >= 4.5 - 1e-6
        moved_lighter = _relative_luminance(fixed) > _relative_luminance(rgb)
        assert moved_lighter is (_relative_luminance(background) < 0.18)

    def it_leaves_a_color_that_already_contrasts_alone(self):
        from power_pptx.theme import _raise_contrast

        rgb = RGBColor(0x12, 0x34, 0x56)
        assert _raise_contrast(rgb, RGBColor(0xFF, 0xFF, 0xFF), 4.5) is rgb


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

    def it_is_idempotent(self, theme):
        # Regression: a second call swapped the pairs back to light and then
        # "raised" every accent's contrast by lightening it, on a white canvas,
        # turning most of them white.
        theme.colors[MSO_THEME_COLOR.ACCENT_1] = RGBColor(0x0A, 0x0A, 0x0A)
        theme.to_dark_mode()
        once = {slot: theme.colors.get(slot) for slot in _PALETTE_SLOTS}

        theme.to_dark_mode()

        assert {slot: theme.colors.get(slot) for slot in _PALETTE_SLOTS} == once

    def it_leaves_a_theme_that_is_already_dark_dark(self, theme):
        colors = theme.colors
        colors[MSO_THEME_COLOR.DARK_1] = RGBColor(0xF5, 0xF5, 0xF5)
        colors[MSO_THEME_COLOR.LIGHT_1] = RGBColor(0x10, 0x14, 0x1C)
        colors[MSO_THEME_COLOR.DARK_2] = RGBColor(0xC0, 0xC8, 0xD0)
        colors[MSO_THEME_COLOR.LIGHT_2] = RGBColor(0x22, 0x28, 0x33)
        accent = RGBColor(0x5B, 0xC0, 0xEB)
        colors[MSO_THEME_COLOR.ACCENT_1] = accent

        theme.to_dark_mode()

        assert colors[MSO_THEME_COLOR.LIGHT_1] == RGBColor(0x10, 0x14, 0x1C)
        assert colors[MSO_THEME_COLOR.LIGHT_2] == RGBColor(0x22, 0x28, 0x33)
        assert colors[MSO_THEME_COLOR.ACCENT_1] == accent

    def it_darkens_accents_that_are_too_light_for_a_light_canvas(self, theme):
        # A canvas that is still light after the swap (light-grey "text" over
        # white): an accent can only gain contrast by getting darker.
        colors = theme.colors
        colors[MSO_THEME_COLOR.DARK_1] = RGBColor(0xEE, 0xEE, 0xEE)
        colors[MSO_THEME_COLOR.LIGHT_1] = RGBColor(0xFF, 0xFF, 0xFF)
        colors[MSO_THEME_COLOR.ACCENT_1] = RGBColor(0xFF, 0xE0, 0x80)

        theme.to_dark_mode()

        bg = colors[MSO_THEME_COLOR.LIGHT_1]
        accent = colors[MSO_THEME_COLOR.ACCENT_1]
        assert bg == RGBColor(0xEE, 0xEE, 0xEE)
        assert _contrast(accent, bg) >= 4.5 - 1e-6
        assert _relative_luminance(accent) < _relative_luminance(RGBColor(0xFF, 0xE0, 0x80))

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
