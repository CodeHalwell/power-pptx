"""Test suite for `pptx.dml.line` module."""

from __future__ import annotations

import pytest

from pptx.dml.color import ColorFormat
from pptx.dml.fill import FillFormat
from pptx.dml.line import LineFormat
from pptx.enum.dml import MSO_FILL, MSO_LINE
from pptx.oxml.shapes.shared import CT_LineProperties
from pptx.shapes.autoshape import Shape

from ..oxml.unitdata.dml import an_ln
from ..unitutil.cxml import element, xml
from ..unitutil.mock import call, class_mock, instance_mock, property_mock


class DescribeLineFormat(object):
    def it_knows_its_dash_style(self, dash_style_get_fixture):
        line, expected_value = dash_style_get_fixture
        assert line.dash_style == expected_value

    @pytest.mark.parametrize(
        ("spPr_cxml", "dash_style", "expected_cxml"),
        [
            ("p:spPr{a:b=c}", MSO_LINE.DASH, "p:spPr{a:b=c}/a:ln/a:prstDash{val=dash}"),
            ("p:spPr/a:ln", MSO_LINE.ROUND_DOT, "p:spPr/a:ln/a:prstDash{val=sysDot}"),
            (
                "p:spPr/a:ln/a:prstDash",
                MSO_LINE.SOLID,
                "p:spPr/a:ln/a:prstDash{val=solid}",
            ),
            (
                "p:spPr/a:ln/a:custDash",
                MSO_LINE.DASH_DOT,
                "p:spPr/a:ln/a:prstDash{val=dashDot}",
            ),
            (
                "p:spPr/a:ln/a:prstDash{val=dash}",
                MSO_LINE.LONG_DASH,
                "p:spPr/a:ln/a:prstDash{val=lgDash}",
            ),
            ("p:spPr/a:ln/a:prstDash{val=dash}", None, "p:spPr/a:ln"),
            ("p:spPr/a:ln/a:custDash", None, "p:spPr/a:ln"),
        ],
    )
    def it_can_change_its_dash_style(
        self, spPr_cxml: str, dash_style: MSO_LINE, expected_cxml: str
    ):
        spPr = element(spPr_cxml)
        line = LineFormat(spPr)

        line.dash_style = dash_style

        assert spPr.xml == xml(expected_cxml)

    def it_knows_its_width(self, width_get_fixture):
        line, expected_line_width = width_get_fixture
        assert line.width == expected_line_width

    def it_can_change_its_width(self, width_set_fixture):
        line, width, expected_xml = width_set_fixture
        line.width = width
        assert line._ln.xml == expected_xml

    def it_has_a_fill(self, fill_fixture):
        line, FillFormat_, ln_, fill_ = fill_fixture
        fill = line.fill
        FillFormat_.from_fill_parent.assert_called_once_with(ln_)
        assert fill is fill_

    def it_reads_color_without_calling_solid(self, line, fill_, fill_prop_, FillFormat_):
        # -- reads through `line.color` must not switch the fill to solid; the
        # -- proxy resolves the underlying ColorFormat lazily on write only.
        for fill_type in (MSO_FILL.SOLID, MSO_FILL.BACKGROUND, None):
            fill_.reset_mock()
            fill_.type = fill_type
            color = line.color
            _ = color.type
            _ = color.rgb
            _ = color.theme_color
            _ = color.brightness
            assert fill_.solid.mock_calls == []

    def it_delegates_color_writes_through_to_a_solid_fill(
        self, line, fill_, fill_prop_, FillFormat_, color_
    ):
        from pptx.dml.color import RGBColor

        fill_.type = MSO_FILL.BACKGROUND
        line.color.rgb = RGBColor(0xFF, 0x00, 0x00)
        assert fill_.solid.mock_calls == [call()]
        assert color_.rgb == RGBColor(0xFF, 0x00, 0x00)

    # fixtures -------------------------------------------------------

    @pytest.fixture
    def color_setup(self, line, fill_prop_, fill_, color_):
        # -- ensures the LineFormat.fill property is mocked to return `fill_` --
        return line, fill_, color_

    @pytest.fixture(
        params=[
            ("p:spPr", None),
            ("p:spPr/a:ln", None),
            ("p:spPr/a:ln/a:prstDash", None),
            ("p:spPr/a:ln/a:prstDash{val=dash}", MSO_LINE.DASH),
            ("p:spPr/a:ln/a:prstDash{val=solid}", MSO_LINE.SOLID),
        ]
    )
    def dash_style_get_fixture(self, request):
        spPr_cxml, expected_value = request.param
        spPr = element(spPr_cxml)
        line = LineFormat(spPr)
        return line, expected_value

    @pytest.fixture
    def fill_fixture(self, line, FillFormat_, ln_, fill_):
        return line, FillFormat_, ln_, fill_

    @pytest.fixture(params=[(None, 0), (12700, 12700)])
    def width_get_fixture(self, request, shape_):
        w, expected_line_width = request.param
        shape_.ln = self.ln_bldr(w).element
        line = LineFormat(shape_)
        return line, expected_line_width

    @pytest.fixture(
        params=[
            (None, None),
            (None, 12700),
            (12700, 12700),
            (12700, 25400),
            (25400, None),
        ]
    )
    def width_set_fixture(self, request, shape_):
        initial_width, width = request.param
        shape_.ln = shape_.get_or_add_ln.return_value = self.ln_bldr(initial_width).element
        line = LineFormat(shape_)
        expected_xml = self.ln_bldr(width).xml()
        return line, width, expected_xml

    # fixture components ---------------------------------------------

    @pytest.fixture
    def color_(self, request):
        return instance_mock(request, ColorFormat)

    @pytest.fixture
    def fill_(self, request, color_):
        return instance_mock(request, FillFormat, fore_color=color_)

    @pytest.fixture
    def fill_prop_(self, request, fill_):
        return property_mock(request, LineFormat, "fill", return_value=fill_)

    @pytest.fixture
    def FillFormat_(self, request, fill_):
        FillFormat_ = class_mock(request, "pptx.dml.line.FillFormat")
        FillFormat_.from_fill_parent.return_value = fill_
        return FillFormat_

    @pytest.fixture
    def line(self, shape_):
        return LineFormat(shape_)

    @pytest.fixture
    def ln_(self, request):
        return instance_mock(request, CT_LineProperties)

    def ln_bldr(self, w):
        ln_bldr = an_ln().with_nsdecls()
        if w is not None:
            ln_bldr.with_w(w)
        return ln_bldr

    @pytest.fixture
    def shape_(self, request, ln_):
        shape_ = instance_mock(request, Shape)
        shape_.get_or_add_ln.return_value = ln_
        return shape_
