"""Validate slide sizes written by `Presentation.set_slide_size` against the ISO-29500 schema.

`p:sldSz/@cx` and `@cy` are `ST_SlideSizeCoordinate`, which the schema bounds
at 914400 and 51206400 EMU. The public `MIN_SLIDE_SIZE` / `MAX_SLIDE_SIZE`
constants have to agree with those bounds, and every size the fit helper
produces has to land inside them.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from lxml import etree

import power_pptx
from power_pptx import Presentation
from power_pptx.util import MAX_SLIDE_SIZE, MIN_SLIDE_SIZE, Emu, Inches

from .oxml_schema_validator import (
    assert_schema_valid,
    iter_schema_violations,
    schema_validation_available,
)

pytestmark = pytest.mark.skipif(
    not schema_validation_available(),
    reason="lxml or the bundled ISO-29500 XSD schemas are unavailable",
)

_XSD = "http://www.w3.org/2001/XMLSchema"


def _saved(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _deck(width, height, fit: bool) -> bytes:
    prs = Presentation()
    prs.set_slide_size(width, height, fit=fit)
    prs.slides.add_slide(prs.slide_layouts[6])
    return _saved(prs)


_DECK_BUILDERS = {
    "widescreen": lambda: _deck(Inches(13.333), Inches(7.5), False),
    "smallest": lambda: _deck(MIN_SLIDE_SIZE, MIN_SLIDE_SIZE, False),
    "largest": lambda: _deck(MAX_SLIDE_SIZE, MAX_SLIDE_SIZE, False),
    "float_arithmetic": lambda: _deck(Inches(40) / 3, Inches(15) / 2, False),
    "fit_video_wall": lambda: _deck(Inches(7680 / 96), Inches(1080 / 96), True),
    "fit_portrait_wall": lambda: _deck(Inches(1080 / 96), Inches(7680 / 96), True),
    "fit_too_small": lambda: _deck(Inches(0.25), Inches(3), True),
    "fit_most_elongated": lambda: _deck(Inches(5600), Inches(100), True),
    "fit_awkward_ratio": lambda: _deck(Emu(987654321), Emu(123456789), True),
    "fit_already_fits": lambda: _deck(Inches(10), Inches(5.625), True),
}


class DescribeSlideSizeSchemaValidity:
    def it_takes_its_limits_from_the_same_place_the_schema_does(self):
        xsd = Path(power_pptx.__file__).parent / "schemas" / "pml.xsd"
        simple_type = etree.parse(str(xsd)).find(
            ".//{%s}simpleType[@name='ST_SlideSizeCoordinate']" % _XSD
        )
        assert simple_type is not None

        def bound(name: str) -> int:
            return int(simple_type.find(".//{%s}%s" % (_XSD, name)).get("value"))

        assert bound("minInclusive") == MIN_SLIDE_SIZE
        assert bound("maxInclusive") == MAX_SLIDE_SIZE

    @pytest.mark.parametrize("name", sorted(_DECK_BUILDERS))
    def it_validates_against_the_ooxml_schema(self, name):
        assert_schema_valid(_DECK_BUILDERS[name]())

    @pytest.mark.parametrize(("cx", "cy"), [("51206401", "6858000"), ("9144000", "914399")])
    def it_detects_a_slide_size_outside_the_limits(self, cx: str, cy: str):
        # -- self-test: bypass the API to write a size one EMU outside the
        # -- limits and confirm the validator would have caught it --
        prs = Presentation()
        sldSz = prs._element.sldSz
        sldSz.set("cx", cx)
        sldSz.set("cy", cy)

        violations = list(iter_schema_violations(_saved(prs)))

        assert any(
            part == "ppt/presentation.xml" and "sldSz" in message for part, message in violations
        ), violations
