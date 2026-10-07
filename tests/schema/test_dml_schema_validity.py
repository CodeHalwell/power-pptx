"""Schema validation for DrawingML output: gradient shading, picture recolor.

These decks exercise paths of ``power_pptx.dml`` that emit (or reorder) XML, and
assert the generated parts still validate against the ISO/IEC 29500 schemas -- the
"reopens fine but PowerPoint offers to repair it" class of bug.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from lxml import etree

from power_pptx import Presentation
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.oxml.ns import qn
from power_pptx.util import Inches

from .oxml_schema_validator import assert_schema_valid, schema_validation_available

pytestmark = pytest.mark.skipif(
    not schema_validation_available(),
    reason="lxml or the bundled ISO-29500 XSD schemas are unavailable",
)


def _saved(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _slide_xml(blob: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        return zf.read("ppt/slides/slide1.xml").decode("utf-8")


# A 1x1 transparent PNG, enough for a `p:pic` to carry blip effects.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360000002000100ffff03000006000557bfabd4000000"
    "0049454e44ae426082"
)


def _washout_then_brightness(effects):
    effects.recolor = "washout"
    effects.brightness = 0.3  # no longer the washout pair: an ordinary adjustment


def _adjustments_then_washout(effects):
    effects.brightness = 0.2
    effects.contrast = 0.3
    effects.recolor = "washout"  # replaces them


def _washout_then_sepia(effects):
    effects.recolor = "washout"
    effects.recolor = "sepia"  # drops the washout `a:lum`


def _grayscale_with_adjustments(effects):
    effects.brightness = 0.1
    effects.recolor = "grayscale"  # leaves the (non-washout) `a:lum` alone


class DescribePictureRecolorSchemaValidity:
    def it_validates_each_recolor_and_the_washout_brightness_contrast_overlap(self):
        # "washout" is PowerPoint's <a:lum bright="70000" contrast="-70000"/> (it shares the
        # element with brightness/contrast); "black_and_white" is the <a:biLevel thresh="50000"/>
        # that "washout" used to write, whose required `thresh` was once left out.
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        scenarios = (
            lambda effects: setattr(effects, "recolor", "washout"),
            lambda effects: setattr(effects, "recolor", "black_and_white"),
            _washout_then_brightness,
            _adjustments_then_washout,
            _washout_then_sepia,
            _grayscale_with_adjustments,
        )
        for i, scenario in enumerate(scenarios):
            picture = slide.shapes.add_picture(
                io.BytesIO(_PNG), Inches(0.5 + i * 1.5), Inches(1), Inches(1), Inches(1)
            )
            scenario(picture.effects)

        blob = _saved(prs)
        slide_xml = _slide_xml(blob)

        # guard against passing vacuously: both element shapes really are in the deck
        assert '<a:lum bright="70000" contrast="-70000"/>' in slide_xml
        assert '<a:biLevel thresh="50000"/>' in slide_xml
        assert '<a:lum bright="30000" contrast="-70000"/>' in slide_xml
        assert '<a:lum bright="10000"/>' in slide_xml
        assert_schema_valid(blob)


class DescribeGradientShadingSchemaValidity:
    def it_validates_a_shading_less_gradient_once_it_is_given_an_angle(self):
        # A `gradFill` with neither `a:lin` nor `a:path` is legal; giving it an angle adds
        # `a:lin`, which must land after `a:gsLst` and before `a:tileRect` (schema sequence
        # gsLst, lin|path, tileRect) or PowerPoint reports the deck as needing repair.
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        entry_points = (
            lambda fill: fill.gradient("linear", angle=45),
            lambda fill: fill.linear_gradient("#FF0000", "#0000FF", angle=45),
            lambda fill: setattr(fill, "gradient_angle", 45),
            lambda fill: setattr(fill, "gradient_angle", 270),  # top to bottom
        )
        for i, apply_angle in enumerate(entry_points):
            shape = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Inches(1), Inches(0.5 + i * 1.2), Inches(4), Inches(1)
            )
            shape.fill.gradient()
            gradFill = shape.fill._xPr.find(qn("a:gradFill"))
            gradFill.remove(gradFill.find(qn("a:lin")))
            if i == len(entry_points) - 1:
                etree.SubElement(gradFill, qn("a:tileRect"))  # lin must go *before* this
            apply_angle(shape.fill)

        blob = _saved(prs)

        # guard against passing vacuously: every shape really did gain its `a:lin`
        assert _slide_xml(blob).count("<a:lin ") == len(entry_points)
        assert_schema_valid(blob)
