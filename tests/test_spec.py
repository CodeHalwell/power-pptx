"""Unit-test suite for :mod:`power_pptx.spec`."""

from __future__ import annotations

from power_pptx import Presentation
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.spec import autoshape_types
from power_pptx.util import Inches


class DescribeAutoshapeTypes:
    def it_names_each_adjustment_of_a_shape_once(self):
        # A repeated guide name makes `shape.adjustments[i] = x` write two
        # `<a:gd>` elements with the same name into the preset's avLst.
        duplicated = {
            str(shape): [name for name, _ in spec["avLst"]]
            for shape, spec in autoshape_types.items()
            if len({name for name, _ in spec["avLst"]}) != len(spec["avLst"])
        }
        assert duplicated == {}

    def it_gives_the_up_down_arrow_its_two_guides(self):
        # presetShapeDefinitions.xml: upDownArrow has adj1 and adj2 only.
        assert autoshape_types[MSO_SHAPE.UP_DOWN_ARROW]["avLst"] == (
            ("adj1", 50000),
            ("adj2", 50000),
        )

    def it_writes_one_guide_per_adjustment_on_an_up_down_arrow(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        arrow = slide.shapes.add_shape(
            MSO_SHAPE.UP_DOWN_ARROW, Inches(1), Inches(1), Inches(1), Inches(3)
        )

        arrow.adjustments[0] = 0.3

        guides = arrow._element.spPr.prstGeom.avLst.findall(
            "{http://schemas.openxmlformats.org/drawingml/2006/main}gd"
        )
        assert [gd.get("name") for gd in guides] == ["adj1", "adj2"]
        assert len(arrow.adjustments) == 2
        assert arrow.adjustments[0] == 0.3
