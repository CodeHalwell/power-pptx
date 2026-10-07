"""Unit-test suite for power_pptx.oxml.graphfrm module."""

from __future__ import annotations

import pytest

from power_pptx.oxml.shapes.graphfrm import CT_GraphicalObjectFrame

from ...unitutil.cxml import xml

CHART_URI = "http://schemas.openxmlformats.org/drawingml/2006/chart"
TABLE_URI = "http://schemas.openxmlformats.org/drawingml/2006/table"

# -- names that are legal shape names but break naive XML templating --
AWKWARD_NAMES = [
    'Hero "banner"',
    "Hero & Logo",
    "Q<4> results",
    'it\'s 100% & "done"',
    "tabbed\tname",
    "two\nlines",
]


class DescribeCT_GraphicalObjectFrame(object):
    """Unit-test suite for `power_pptx.oxml.shapes.graphfrm.CT_GraphicalObjectFrame."""

    def it_can_construct_a_new_graphicFrame(self, new_graphicFrame_fixture):
        id_, name, x, y, cx, cy, expected_xml = new_graphicFrame_fixture
        graphicFrame = CT_GraphicalObjectFrame.new_graphicFrame(id_, name, x, y, cx, cy)
        assert graphicFrame.xml == expected_xml

    def it_can_construct_a_new_chart_graphicFrame(self, new_chart_graphicFrame_fixture):
        id_, name, rId, x, y, cx, cy, expected_xml = new_chart_graphicFrame_fixture
        graphicFrame = CT_GraphicalObjectFrame.new_chart_graphicFrame(id_, name, rId, x, y, cx, cy)
        assert graphicFrame.xml == expected_xml

    def it_can_construct_a_new_table_graphicFrame(self, new_table_graphicFrame_fixture):
        (
            id_,
            name,
            rows,
            cols,
            x,
            y,
            cx,
            cy,
            expected_xml,
        ) = new_table_graphicFrame_fixture
        graphicFrame = CT_GraphicalObjectFrame.new_table_graphicFrame(
            id_, name, rows, cols, x, y, cx, cy
        )
        assert graphicFrame.xml == expected_xml

    @pytest.mark.parametrize("name", AWKWARD_NAMES)
    def it_escapes_the_name_of_a_new_graphicFrame(self, name):
        graphicFrame = CT_GraphicalObjectFrame.new_graphicFrame(42, name, 1, 2, 3, 4)
        assert graphicFrame.xpath("p:nvGraphicFramePr/p:cNvPr")[0].get("name") == name

    @pytest.mark.parametrize("name", AWKWARD_NAMES)
    def it_escapes_the_name_of_a_new_chart_graphicFrame(self, name):
        graphicFrame = CT_GraphicalObjectFrame.new_chart_graphicFrame(42, name, "rId6", 1, 2, 3, 4)
        assert graphicFrame.xpath("p:nvGraphicFramePr/p:cNvPr")[0].get("name") == name

    @pytest.mark.parametrize("name", AWKWARD_NAMES)
    def it_escapes_the_name_of_a_new_table_graphicFrame(self, name):
        graphicFrame = CT_GraphicalObjectFrame.new_table_graphicFrame(42, name, 1, 1, 1, 2, 3, 4)
        assert graphicFrame.xpath("p:nvGraphicFramePr/p:cNvPr")[0].get("name") == name

    @pytest.mark.parametrize("text", AWKWARD_NAMES)
    def it_escapes_the_name_and_progId_of_a_new_ole_object_graphicFrame(self, text):
        graphicFrame = CT_GraphicalObjectFrame.new_ole_object_graphicFrame(
            id_=42,
            name=text,
            ole_object_rId="rId6",
            progId=text,
            icon_rId="rId7",
            x=1,
            y=2,
            cx=3,
            cy=4,
            imgW=5,
            imgH=6,
            pic_id=43,
        )
        assert graphicFrame.xpath("p:nvGraphicFramePr/p:cNvPr")[0].get("name") == text
        assert graphicFrame.xpath(".//p:oleObj")[0].get("progId") == text

    # fixtures -------------------------------------------------------

    @pytest.fixture
    def new_chart_graphicFrame_fixture(self):
        id_, name, rId, x, y, cx, cy = 42, "foobar", "rId6", 1, 2, 3, 4
        xml_tmpl = xml(
            "p:graphicFrame/(p:nvGraphicFramePr/(p:cNvPr{id=42,name=foobar},"
            "p:cNvGraphicFramePr/a:graphicFrameLocks{noGrp=1},p:nvPr),p:xfrm"
            "/(a:off{x=1,y=2},a:ext{cx=3,cy=4}),a:graphic/a:graphicData{uri="
            '%s}"%%s")' % CHART_URI
        )
        expected_xml = xml_tmpl % ("\n      " + xml("c:chart{r:id=rId6}") + "    ")
        return id_, name, rId, x, y, cx, cy, expected_xml

    @pytest.fixture
    def new_graphicFrame_fixture(self):
        id_, name, x, y, cx, cy = 42, "foobar", 1, 2, 3, 4
        expected_xml = xml(
            "p:graphicFrame/(p:nvGraphicFramePr/(p:cNvPr{id=42,name=foobar},"
            "p:cNvGraphicFramePr/a:graphicFrameLocks{noGrp=1},p:nvPr),p:xfrm"
            "/(a:off{x=1,y=2},a:ext{cx=3,cy=4}),a:graphic/a:graphicData)"
        )
        return id_, name, x, y, cx, cy, expected_xml

    @pytest.fixture
    def new_table_graphicFrame_fixture(self):
        id_, name, rows, cols, x, y, cx, cy = 42, "foobar", 1, 1, 1, 2, 3, 4
        expected_xml = xml(
            "p:graphicFrame/(p:nvGraphicFramePr/(p:cNvPr{id=42,name=foobar},"
            "p:cNvGraphicFramePr/a:graphicFrameLocks{noGrp=1},p:nvPr),p:xfrm"
            "/(a:off{x=1,y=2},a:ext{cx=3,cy=4}),a:graphic/a:graphicData{uri="
            '%s}/a:tbl/(a:tblPr{firstRow=1,bandRow=1}/a:tableStyleId"{5C2254'
            '4A-7EE6-4342-B048-85BDC9FD1C3A}",a:tblGrid/a:gridCol{w=3},a:tr{'
            "h=4}/a:tc/(a:txBody/(a:bodyPr,a:lstStyle,a:p),a:tcPr)))" % TABLE_URI
        )
        return id_, name, rows, cols, x, y, cx, cy, expected_xml
