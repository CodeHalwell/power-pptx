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
