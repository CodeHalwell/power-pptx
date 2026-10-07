"""Unit-test suite for `power_pptx.inherit`."""

from __future__ import annotations

import colorsys

import pytest

from power_pptx import Presentation
from power_pptx.dml.color import RGBColor
from power_pptx.enum.dml import MSO_THEME_COLOR
from power_pptx.inherit import _apply_brightness, resolve_color
from power_pptx.util import Inches


def _make_run():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(2))
    tf = tb.text_frame
    tf.text = "Hello"
    return prs, tf.paragraphs[0].runs[0]


def _hsl_lum_adjust(rgb, brightness):
    """Independent model of PowerPoint's ``lumMod`` / ``lumOff`` on an RGB color.

    PowerPoint converts to HSL, scales/offsets the luminance and keeps hue and saturation:
    a shade (``brightness < 0``) is ``lumMod = 1 - |b|``; a tint is ``lumMod = 1 - b`` with
    ``lumOff = b``.
    """
    h, lum, s = colorsys.rgb_to_hls(*(c / 255.0 for c in rgb))
    lum_mod = 1.0 - abs(brightness)
    lum_off = brightness if brightness > 0 else 0.0
    return tuple(round(c * 255.0) for c in colorsys.hls_to_rgb(h, lum * lum_mod + lum_off, s))


class DescribeResolveColor:
    def it_returns_None_for_an_unset_color(self):
        prs, run = _make_run()
        assert resolve_color(run.font.color, theme=prs.theme) is None

    def it_resolves_an_explicit_RGBColor(self):
        prs, run = _make_run()
        run.font.color.rgb = RGBColor(0x12, 0x34, 0x56)

        assert resolve_color(run.font.color, theme=prs.theme) == RGBColor(0x12, 0x34, 0x56)

    def it_resolves_an_RGBColor_without_a_theme(self):
        prs, run = _make_run()
        run.font.color.rgb = RGBColor(0xFE, 0xDC, 0xBA)

        # `theme` is only required for SCHEME colors.
        assert resolve_color(run.font.color) == RGBColor(0xFE, 0xDC, 0xBA)

    def it_resolves_a_theme_color_via_the_theme(self):
        prs, run = _make_run()
        run.font.color.theme_color = MSO_THEME_COLOR.ACCENT_2
        expected = prs.theme.colors[MSO_THEME_COLOR.ACCENT_2]

        assert resolve_color(run.font.color, theme=prs.theme) == expected

    def it_returns_None_for_a_theme_color_when_theme_is_omitted(self):
        prs, run = _make_run()
        run.font.color.theme_color = MSO_THEME_COLOR.ACCENT_2

        assert resolve_color(run.font.color) is None

    def it_applies_positive_brightness_lightening_toward_white(self):
        prs, run = _make_run()
        run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)
        run.font.color.brightness = 0.5  # halfway to white

        # -- a gray has no hue or saturation, so its HSL luminance (128/255) is all there is:
        # -- 0.502 * 0.5 + 0.5 = 0.751 -> 191.5, which rounds to 0xC0 --
        assert resolve_color(run.font.color, theme=prs.theme) == RGBColor(0xC0, 0xC0, 0xC0)

    def it_applies_negative_brightness_darkening_toward_black(self):
        prs, run = _make_run()
        run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)
        run.font.color.brightness = -0.5  # halfway to black

        assert resolve_color(run.font.color, theme=prs.theme) == RGBColor(0x40, 0x40, 0x40)

    def it_applies_brightness_to_HSL_luminance_not_to_the_RGB_channels(self):
        prs, run = _make_run()
        run.font.color.rgb = RGBColor(0xFF, 0xCC, 0xCC)
        run.font.color.brightness = -0.5  # "Darker 50%": lumMod 50%

        # -- FFCCCC is hue 0, saturation 100%, luminance 90%. PowerPoint halves the luminance
        # -- to 45% and keeps hue and saturation: E60000. Scaling the channels toward black
        # -- instead would give a dull, desaturated 806666. --
        assert resolve_color(run.font.color, theme=prs.theme) == RGBColor(0xE6, 0x00, 0x00)

    def it_applies_brightness_to_a_theme_color_the_same_way(self):
        prs, run = _make_run()
        prs.theme.colors[MSO_THEME_COLOR.ACCENT_1] = RGBColor(0x4F, 0x81, 0xBD)
        run.font.color.theme_color = MSO_THEME_COLOR.ACCENT_1

        # -- "Darker 50%" (lumMod 50%): luminance 0.526 -> 0.263, hue/saturation kept.
        # -- Cf. the Office 2007 colour-picker swatch 244062 for this slot: within one per
        # -- channel; an RGB blend toward black (28405E) is four off. --
        run.font.color.brightness = -0.5
        assert resolve_color(run.font.color, theme=prs.theme) == RGBColor(0x25, 0x40, 0x61)

        # -- "Lighter 60%" (lumMod 40% + lumOff 60%); cf. the Office swatch B8CCE4 --
        run.font.color.brightness = 0.6
        assert resolve_color(run.font.color, theme=prs.theme) == RGBColor(0xB9, 0xCD, 0xE5)

    def it_returns_None_when_theme_lookup_misses(self):
        """If the theme palette doesn't define a slot the resolver doesn't raise."""
        prs, run = _make_run()
        run.font.color.theme_color = MSO_THEME_COLOR.ACCENT_3

        class _StubTheme:
            class colors:
                @staticmethod
                def __getitem__(key):
                    raise KeyError(key)

        # bind unbound classmethod-style lookup
        stub = _StubTheme()
        stub.colors = type(
            "C", (), {"__getitem__": lambda s, k: (_ for _ in ()).throw(KeyError(k))}
        )()
        assert resolve_color(run.font.color, theme=stub) is None


class DescribeApplyBrightness:
    @pytest.mark.parametrize(
        ("brightness", "expected"),
        [
            (0, RGBColor(0x80, 0x80, 0x80)),
            (None, RGBColor(0x80, 0x80, 0x80)),
            (1.0, RGBColor(0xFF, 0xFF, 0xFF)),
            (-1.0, RGBColor(0x00, 0x00, 0x00)),
            # -- a gray has only luminance (128/255 = 0.502): 0.502 * 0.75 + 0.25 = 0.6275
            # -- -> 159.75 -> 160 (0xA0) --
            (0.25, RGBColor(0xA0, 0xA0, 0xA0)),
            # -- 0.502 * 0.75 = 0.3765 -> 96 (0x60) --
            (-0.25, RGBColor(0x60, 0x60, 0x60)),
        ],
    )
    def it_lightens_or_darkens_a_gray(self, brightness, expected):
        assert _apply_brightness(RGBColor(0x80, 0x80, 0x80), brightness) == expected

    @pytest.mark.parametrize(
        ("hex_color", "brightness", "expected_hex"),
        [
            # -- shades: lumMod = 1 - |b| scales the HSL luminance; hue and saturation stay.
            # -- Expected values worked out with colorsys; an RGB blend gives the one noted. --
            ("FFCCCC", -0.5, "E60000"),  # l 0.90 -> 0.45 (blend: 806666)
            ("DDEBF7", -0.5, "2D7BBD"),  # l 0.92 -> 0.46 (blend: 6E767C)
            ("4F81BD", -0.5, "254061"),  # (blend: 28405E)
            ("C0504D", -0.25, "953735"),  # (blend: 903C3A)
            ("9BBB59", -0.5, "4F6228"),  # (blend: 4E5E2C)
            # -- tints: lumMod = 1 - b and lumOff = b give l' = l * (1 - b) + b. For a dark,
            # -- saturated color that is far from blending the channels toward white. --
            ("800000", 0.5, "FF4040"),  # l 0.25 -> 0.63 (blend: C08080)
            ("1F3864", 0.4, "517DC9"),  # (blend: 7988A2)
            ("7030A0", 0.4, "AB74D5"),  # (blend: A983C6)
            ("4F81BD", 0.4, "95B3D7"),  # a light-ish color: both models agree here
        ],
    )
    def it_applies_brightness_to_HSL_luminance_like_lumMod_and_lumOff(
        self, hex_color, brightness, expected_hex
    ):
        rgb = RGBColor.from_hex(hex_color)

        assert _apply_brightness(rgb, brightness) == RGBColor.from_hex(expected_hex)

    @pytest.mark.parametrize("brightness", [-1.0, -0.75, -0.5, -0.25, 0.25, 0.5, 0.75, 1.0])
    @pytest.mark.parametrize(
        "hex_color",
        [
            "000000",
            "FFFFFF",
            "808080",
            "FF0000",
            "00FF00",
            "0000FF",
            "FFC000",
            "4F81BD",
            "C0504D",
            "9BBB59",
            "7030A0",
            "1F3864",
            "FFCCCC",
        ],
    )
    def it_agrees_with_an_independent_HSL_model(self, hex_color, brightness):
        rgb = RGBColor.from_hex(hex_color)

        result = _apply_brightness(rgb, brightness)

        # -- within one per channel: 8-bit rounding can differ at an exact .5 --
        expected = _hsl_lum_adjust(rgb, brightness)
        assert all(abs(got - want) <= 1 for got, want in zip(result, expected)), (result, expected)

    @pytest.mark.parametrize("brightness", [-0.3, 0.3])
    @pytest.mark.parametrize("hex_color", ["4F81BD", "9BBB59", "C0504D", "FFC000", "7030A0"])
    def it_keeps_hue_and_saturation(self, hex_color, brightness):
        rgb = RGBColor.from_hex(hex_color)

        result = _apply_brightness(rgb, brightness)

        h0, _, s0 = colorsys.rgb_to_hls(*(c / 255.0 for c in rgb))
        h1, _, s1 = colorsys.rgb_to_hls(*(c / 255.0 for c in result))
        assert h1 == pytest.approx(h0, abs=0.01)
        assert s1 == pytest.approx(s0, abs=0.03)

    def it_clamps_out_of_range_values(self):
        # Values outside [-1, 1] saturate at the endpoints.
        assert _apply_brightness(RGBColor(0x80, 0x80, 0x80), 5.0) == RGBColor(0xFF, 0xFF, 0xFF)
        assert _apply_brightness(RGBColor(0x80, 0x80, 0x80), -3.0) == RGBColor(0x00, 0x00, 0x00)
        assert _apply_brightness(RGBColor(0xFF, 0xCC, 0xCC), 5.0) == RGBColor(0xFF, 0xFF, 0xFF)
        assert _apply_brightness(RGBColor(0xFF, 0xCC, 0xCC), -3.0) == RGBColor(0x00, 0x00, 0x00)

    @pytest.mark.parametrize("brightness", [0, 0.0, None])
    def it_returns_the_color_untouched_when_there_is_no_adjustment(self, brightness):
        # -- no HSL round trip, so no rounding drift on an unadjusted color --
        rgb = RGBColor(0x4F, 0x81, 0xBD)
        assert _apply_brightness(rgb, brightness) == rgb
