# pyright: reportPrivateUsage=false

"""Unit-test suite for `power_pptx.dml.picture` module."""

from __future__ import annotations

import pytest

from power_pptx.dml.picture import PictureEffects
from power_pptx.oxml.ns import qn

from ..unitutil.cxml import element, xml


def _effects(cxml: str = "a:blip{r:embed=rId1}"):
    blip = element(cxml)
    return PictureEffects(blip), blip


def _lum_pair(blip):
    """The (bright, contrast) attribute strings of `blip`'s `a:lum`, or None."""
    lum = blip.find(qn("a:lum"))
    return None if lum is None else (lum.get("bright"), lum.get("contrast"))


class DescribePictureEffectsRecolor:
    """`PictureEffects.recolor`, including its overlap with brightness and contrast."""

    # -- washout is PowerPoint's Recolor > Washout: an `a:lum` pair, *not* a `biLevel` ------

    def it_writes_washout_as_the_brightness_contrast_pair_PowerPoint_uses(self):
        effects, blip = _effects()

        effects.recolor = "washout"

        assert blip.xml == xml("a:blip{r:embed=rId1}/a:lum{bright=70000,contrast=-70000}")
        assert blip.find(qn("a:biLevel")) is None

    def it_reads_the_washout_pair_back_as_washout(self):
        effects, _ = _effects("a:blip/a:lum{bright=70000,contrast=-70000}")

        assert effects.recolor == "washout"
        # -- washout *is* brightness +70% / contrast -70%, so the two also read back --
        assert effects.brightness == 0.7
        assert effects.contrast == -0.7

    @pytest.mark.parametrize(
        "cxml",
        [
            "a:blip",
            "a:blip/a:lum{bright=70000}",
            "a:blip/a:lum{contrast=-70000}",
            "a:blip/a:lum{bright=70000,contrast=-60000}",
            "a:blip/a:lum{bright=-70000,contrast=70000}",
            "a:blip/a:lum{bright=20000,contrast=30000}",
        ],
    )
    def but_it_does_not_read_other_brightness_and_contrast_as_washout(self, cxml):
        effects, _ = _effects(cxml)
        assert effects.recolor is None

    def it_reads_washout_whenever_brightness_and_contrast_are_the_washout_pair(self):
        # -- the pair is the only thing that identifies a washout, however it got there --
        effects, _ = _effects()
        effects.brightness = 0.7
        assert effects.recolor is None

        effects.contrast = -0.7

        assert effects.recolor == "washout"

    # -- how washout and brightness / contrast share the one `a:lum` ------------------------

    def it_replaces_any_brightness_and_contrast_when_washout_is_assigned(self):
        effects, blip = _effects()
        effects.brightness = 0.2
        effects.contrast = 0.3
        assert _lum_pair(blip) == ("20000", "30000")

        effects.recolor = "washout"

        assert _lum_pair(blip) == ("70000", "-70000")
        assert (effects.brightness, effects.contrast) == (0.7, -0.7)
        assert len(blip.findall(qn("a:lum"))) == 1

    def it_stops_reading_as_washout_once_brightness_or_contrast_is_changed(self):
        effects, blip = _effects()
        effects.recolor = "washout"
        assert _lum_pair(blip) == ("70000", "-70000")

        effects.brightness = 0.3

        assert effects.recolor is None
        assert (effects.brightness, effects.contrast) == (0.3, -0.7)

    def it_removes_a_washout_when_recolor_is_cleared(self):
        effects, blip = _effects()
        effects.recolor = "washout"
        assert _lum_pair(blip) == ("70000", "-70000")

        effects.recolor = None

        assert blip.find(qn("a:lum")) is None
        assert effects.recolor is None
        assert (effects.brightness, effects.contrast) == (0.0, 0.0)

    @pytest.mark.parametrize(
        ("other", "expected_child"),
        [
            ("grayscale", "a:grayscl"),
            ("sepia", "a:duotone"),
            ("duotone", "a:duotone"),
            ("black_and_white", "a:biLevel"),
        ],
    )
    def it_removes_a_washout_when_another_recolor_is_assigned(self, other, expected_child):
        effects, blip = _effects()
        effects.recolor = "washout"
        assert _lum_pair(blip) == ("70000", "-70000")

        effects.recolor = other

        assert blip.find(qn("a:lum")) is None
        assert blip.find(qn(expected_child)) is not None
        assert effects.recolor == other

    def it_removes_a_washout_when_a_custom_duotone_is_set(self):
        effects, blip = _effects()
        effects.recolor = "washout"
        assert _lum_pair(blip) == ("70000", "-70000")

        effects.set_duotone((0x12, 0x1E, 0x4D), (0xA8, 0xC0, 0xFF))

        assert blip.find(qn("a:lum")) is None
        assert effects.recolor == "duotone"

    @pytest.mark.parametrize("new_value", ["grayscale", "black_and_white", "sepia", None])
    def but_it_keeps_brightness_and_contrast_that_are_not_a_washout(self, new_value):
        # -- only a lum that *is* the washout pair counts as the recolor; real brightness /
        # -- contrast adjustments survive any change of recolor.
        effects, blip = _effects()
        effects.brightness = 0.2
        effects.contrast = 0.3

        effects.recolor = new_value

        assert _lum_pair(blip) == ("20000", "30000")

    def it_leaves_a_washout_untouched_when_an_invalid_recolor_is_rejected(self):
        effects, blip = _effects()
        effects.recolor = "washout"
        assert _lum_pair(blip) == ("70000", "-70000")

        with pytest.raises(ValueError, match="recolor must be"):
            effects.recolor = "bogus"

        assert effects.recolor == "washout"
        assert _lum_pair(blip) == ("70000", "-70000")

    # -- black_and_white is what "washout" used to (wrongly) write --------------------------

    def it_writes_black_and_white_as_a_50_percent_biLevel(self):
        effects, blip = _effects()

        effects.recolor = "black_and_white"

        assert blip.xml == xml("a:blip{r:embed=rId1}/a:biLevel{thresh=50000}")
        assert effects.recolor == "black_and_white"

    @pytest.mark.parametrize("thresh", [25000, 50000, 75000])
    def it_reads_any_biLevel_threshold_as_black_and_white(self, thresh):
        # -- also what a deck saved by an earlier release (washout -> biLevel) reads as --
        effects, _ = _effects("a:blip/a:biLevel{thresh=%d}" % thresh)
        assert effects.recolor == "black_and_white"

    def it_swaps_between_black_and_white_and_washout(self):
        effects, blip = _effects()

        effects.recolor = "black_and_white"
        effects.recolor = "washout"
        assert blip.find(qn("a:biLevel")) is None
        assert _lum_pair(blip) == ("70000", "-70000")

        effects.recolor = "black_and_white"
        assert blip.find(qn("a:lum")) is None
        assert blip.find(qn("a:biLevel")) is not None
        assert effects.recolor == "black_and_white"

    def it_names_black_and_white_among_the_valid_values_when_rejecting_one(self):
        effects, _ = _effects()
        with pytest.raises(ValueError, match="black_and_white"):
            effects.recolor = "washed"

    # -- the pre-existing modes, unchanged ---------------------------------------------------

    @pytest.mark.parametrize(
        ("mode", "expected_cxml"),
        [
            ("grayscale", "a:blip{r:embed=rId1}/a:grayscl"),
            (
                "sepia",
                "a:blip{r:embed=rId1}/a:duotone/(a:srgbClr{val=532400},a:srgbClr{val=FFEFCA})",
            ),
            (
                "duotone",
                "a:blip{r:embed=rId1}/a:duotone/(a:srgbClr{val=333333},a:srgbClr{val=EBEBEB})",
            ),
        ],
    )
    def it_still_writes_and_reads_back_the_other_recolor_modes(self, mode, expected_cxml):
        effects, blip = _effects()

        effects.recolor = mode

        assert blip.xml == xml(expected_cxml)
        assert effects.recolor == mode

        effects.recolor = None

        assert blip.xml == xml("a:blip{r:embed=rId1}")
        assert effects.recolor is None
