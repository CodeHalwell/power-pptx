"""Unit-test suite for `power_pptx.dml.picture` module."""

from __future__ import annotations

import pytest

from power_pptx.dml.color import RGBColor
from power_pptx.dml.picture import PictureEffects

from ..unitutil.cxml import element, xml

_BLIP = "a:blip{r:embed=rId1}"


def _effects(cxml: str = _BLIP):
    """Return `(blip, effects)` for a blip described by `cxml`."""
    blip = element(cxml)
    return blip, PictureEffects(blip)


class DescribePictureEffectsDuotone:
    """`set_duotone()` coerces its colours the way every other colour setter does."""

    @pytest.mark.parametrize(
        ("dark", "light", "expected"),
        [
            (RGBColor(0x12, 0x1E, 0x4D), "#A8C0FF", ("121E4D", "A8C0FF")),
            ("a8c0ff", "0b2447", ("A8C0FF", "0B2447")),
            ((18, 30, 77), (168, 192, 255), ("121E4D", "A8C0FF")),
            ([1, 2, 3], RGBColor(4, 5, 6), ("010203", "040506")),
        ],
    )
    def it_writes_two_six_digit_colours(self, dark, light, expected):
        blip, effects = _effects()

        effects.set_duotone(dark, light)

        assert blip.xml == xml(
            _BLIP + "/a:duotone/(a:srgbClr{val=%s},a:srgbClr{val=%s})" % expected
        )
        assert effects.recolor == "duotone"

    @pytest.mark.parametrize(
        ("dark", "light", "exc"),
        [
            # -- each of these used to be written out as-is: val="FFF",
            # -- val="RED", val="12C0000"
            ("#FFF", "#000", ValueError),
            ("red", "blue", ValueError),
            ((300, 0, 0), (0, 0, 0), ValueError),
            ("", "", ValueError),
            ("#0B2447", "#12345", ValueError),
            ((1.5, 2, 3), (0, 0, 0), TypeError),
            # -- and this one raised only after the old recolour was cleared
            ((1, 2, 3), None, TypeError),
            (None, (1, 2, 3), TypeError),
        ],
    )
    def it_rejects_a_bad_colour_and_keeps_the_current_recolour(self, dark, light, exc):
        blip, effects = _effects(_BLIP + "/a:grayscl")
        before = blip.xml

        with pytest.raises(exc):
            effects.set_duotone(dark, light)

        assert blip.xml == before
        assert effects.recolor == "grayscale"

    def it_replaces_an_existing_duotone_when_the_colours_are_good(self):
        blip, effects = _effects()
        effects.set_duotone("111111", "EEEEEE")

        effects.set_duotone("222222", "DDDDDD")

        assert blip.xml == xml(
            _BLIP + "/a:duotone/(a:srgbClr{val=222222},a:srgbClr{val=DDDDDD})"
        )

    def but_it_keeps_the_existing_duotone_when_the_new_one_is_rejected(self):
        blip, effects = _effects()
        effects.set_duotone("111111", "EEEEEE")
        before = blip.xml

        with pytest.raises(ValueError):
            effects.set_duotone("222222", "#DDD")

        assert blip.xml == before


class DescribePictureEffectsRecolor:
    def it_writes_washout_as_brightness_and_contrast(self):
        # Regression: washout used to be `<a:biLevel thresh="50000"/>`, a hard
        # black/white split. PowerPoint's Washout is +70% brightness, -70%
        # contrast on `<a:lum>`.
        blip, effects = _effects()

        effects.recolor = "washout"

        assert blip.xml == xml(_BLIP + "/a:lum{bright=70000,contrast=-70000}")
        assert effects.recolor == "washout"
        assert effects.brightness == 0.7
        assert effects.contrast == -0.7

    def it_reads_a_powerpoint_washout_back_as_washout(self):
        _, effects = _effects(_BLIP + "/a:lum{bright=70000,contrast=-70000}")
        assert effects.recolor == "washout"

    def it_writes_black_and_white_as_a_bilevel_threshold(self):
        blip, effects = _effects()

        effects.recolor = "black_and_white"

        assert blip.xml == xml(_BLIP + "/a:biLevel{thresh=50000}")
        assert effects.recolor == "black_and_white"

    def it_no_longer_calls_a_bilevel_picture_washout(self):
        _, effects = _effects(_BLIP + "/a:biLevel{thresh=50000}")
        assert effects.recolor == "black_and_white"

    @pytest.mark.parametrize(
        "mode", ["grayscale", "washout", "sepia", "duotone", "black_and_white"]
    )
    def it_round_trips_every_mode_and_clears_it_again(self, mode):
        blip, effects = _effects()

        effects.recolor = mode
        assert effects.recolor == mode

        effects.recolor = None
        assert effects.recolor is None
        assert blip.xml == xml(_BLIP)

    @pytest.mark.parametrize("first", ["grayscale", "washout", "sepia", "black_and_white"])
    @pytest.mark.parametrize("second", ["grayscale", "washout", "duotone", "black_and_white"])
    def it_replaces_one_mode_with_another(self, first, second):
        blip, effects = _effects()
        effects.recolor = first

        effects.recolor = second

        assert effects.recolor == second
        assert len(blip) == 1

    def it_keeps_a_brightness_adjustment_that_is_not_washout(self):
        blip, effects = _effects()
        effects.brightness = 0.2
        effects.recolor = "grayscale"

        effects.recolor = None

        assert blip.xml == xml(_BLIP + "/a:lum{bright=20000}")

    def it_leaves_washout_when_brightness_is_changed_afterwards(self):
        _, effects = _effects()
        effects.recolor = "washout"

        effects.brightness = 0.2

        assert effects.recolor is None
        assert effects.contrast == -0.7

    def it_rejects_an_unknown_mode_and_keeps_the_current_one(self):
        blip, effects = _effects(_BLIP + "/a:grayscl")
        before = blip.xml

        with pytest.raises(ValueError, match="black_and_white"):
            effects.recolor = "negative"

        assert blip.xml == before


def _png():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (40, 120, 200)).save(buf, format="PNG")
    buf.seek(0)
    return buf


def _deck_with_recoloured_pictures():
    from power_pptx import Presentation
    from power_pptx.util import Inches

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    modes = ("grayscale", "washout", "sepia", "duotone", "black_and_white")
    for i, mode in enumerate(modes):
        pic = slide.shapes.add_picture(_png(), Inches(0.3 + 1.9 * i), Inches(1), Inches(1.7))
        pic.effects.recolor = mode
    custom = slide.shapes.add_picture(_png(), Inches(0.3), Inches(4), Inches(1.7))
    custom.effects.set_duotone("#0b2447", (201, 162, 39))
    rejected = slide.shapes.add_picture(_png(), Inches(2.2), Inches(4), Inches(1.7))
    rejected.effects.recolor = "sepia"
    for bad in (("#FFF", "#000"), ("red", "blue"), ((300, 0, 0), (0, 0, 0)), ((1, 2, 3), None)):
        with pytest.raises((TypeError, ValueError)):
            rejected.effects.set_duotone(*bad)
    return prs


class DescribeRecolouredPicturesInASavedDeck:
    def it_keeps_each_mode_through_save_and_reopen(self):
        import io

        from power_pptx import Presentation

        buf = io.BytesIO()
        _deck_with_recoloured_pictures().save(buf)
        pics = list(Presentation(io.BytesIO(buf.getvalue())).slides[0].shapes)

        assert [p.effects.recolor for p in pics] == [
            "grayscale",
            "washout",
            "sepia",
            "duotone",
            "black_and_white",
            "duotone",
            "sepia",
        ]

    def it_is_schema_valid(self):
        import io

        from tests.schema.oxml_schema_validator import (
            iter_schema_violations,
            schema_validation_available,
        )

        if not schema_validation_available():
            pytest.skip("schema validation unavailable")

        buf = io.BytesIO()
        _deck_with_recoloured_pictures().save(buf)
        assert list(iter_schema_violations(buf.getvalue())) == []

    def it_round_trips(self):
        from tests.integration.round_trip import assert_round_trip

        assert_round_trip(_deck_with_recoloured_pictures())
