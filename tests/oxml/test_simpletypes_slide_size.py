"""Unit-test suite for `power_pptx.oxml.simpletypes.ST_SlideSizeCoordinate`."""

from __future__ import annotations

import pytest

from power_pptx.oxml.simpletypes import ST_SlideSizeCoordinate
from power_pptx.util import MAX_SLIDE_SIZE, MIN_SLIDE_SIZE, Emu, Inches, Length


class DescribeST_SlideSizeCoordinate(object):
    """Unit-test suite for `power_pptx.oxml.simpletypes.ST_SlideSizeCoordinate`."""

    def it_converts_an_XML_value_to_a_Length(self):
        value = ST_SlideSizeCoordinate.from_xml("12192000")

        assert isinstance(value, Length)
        assert value == Inches(13.333333333333334) == 12192000

    @pytest.mark.parametrize(
        "value", [MIN_SLIDE_SIZE, MAX_SLIDE_SIZE, Inches(13.333), Emu(914401), Emu(51206399)]
    )
    def it_accepts_a_value_from_the_minimum_to_the_maximum_inclusive(self, value):
        assert ST_SlideSizeCoordinate.to_xml(value) == str(int(value))

    @pytest.mark.parametrize(
        ("value", "got"),
        [
            (MIN_SLIDE_SIZE - 1, "got 0.999999 inches (914399 EMU)"),
            (MAX_SLIDE_SIZE + 1, "got 56 inches (51206401 EMU)"),
            (Inches(80), "got 80 inches (73152000 EMU)"),
            (Inches(0.5), "got 0.5 inches (457200 EMU)"),
            (0, "got 0 inches (0 EMU)"),
            (-914400, "got -1 inches (-914400 EMU)"),
        ],
    )
    def it_rejects_a_value_outside_the_public_limits(self, value, got):
        with pytest.raises(ValueError) as excinfo:
            ST_SlideSizeCoordinate.to_xml(value)

        # -- the limits are stated in inches, with the EMU values alongside --
        assert str(excinfo.value) == (
            "slide width and height must be between 1 and 56 inches "
            "(914400 to 51206400 EMU), " + got
        )

    def it_states_the_limits_from_the_public_constants(self):
        with pytest.raises(ValueError) as excinfo:
            ST_SlideSizeCoordinate.validate(MAX_SLIDE_SIZE * 2)

        message = str(excinfo.value)
        limits_in_inches = (MIN_SLIDE_SIZE.inches, MAX_SLIDE_SIZE.inches)
        assert "between %g and %g inches" % limits_in_inches in message
        assert "(%d to %d EMU)" % (MIN_SLIDE_SIZE, MAX_SLIDE_SIZE) in message

    @pytest.mark.parametrize("value", [9144000.0, "9144000", None])
    def it_still_requires_an_integer(self, value):
        with pytest.raises(TypeError):
            ST_SlideSizeCoordinate.to_xml(value)
