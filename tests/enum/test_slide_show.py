"""Unit-test suite for `power_pptx.enum.slide_show` module."""

from __future__ import annotations

import pytest

from power_pptx.enum.slide_show import PP_SLIDE_SHOW, PP_SLIDE_SHOW_TYPE


class DescribePP_SLIDE_SHOW_TYPE(object):
    """Unit-test suite for `power_pptx.enum.slide_show.PP_SLIDE_SHOW_TYPE`."""

    @pytest.mark.parametrize(
        ("member", "ms_api_value", "xml_value"),
        [
            # -- values are those of `PpSlideShowType` in the PowerPoint object model;
            # -- the XML value is the local name of the `p:showPr` child element --
            (PP_SLIDE_SHOW_TYPE.SPEAKER, 1, "present"),
            (PP_SLIDE_SHOW_TYPE.WINDOW, 2, "browse"),
            (PP_SLIDE_SHOW_TYPE.KIOSK, 3, "kiosk"),
        ],
    )
    def it_maps_each_member_to_its_MS_API_value_and_element_name(
        self, member: PP_SLIDE_SHOW_TYPE, ms_api_value: int, xml_value: str
    ):
        assert member == ms_api_value
        assert member.xml_value == xml_value
        assert PP_SLIDE_SHOW_TYPE.from_xml(xml_value) is member
        assert PP_SLIDE_SHOW_TYPE.to_xml(member) == xml_value

    def it_has_exactly_the_three_show_types_of_the_dialog(self):
        assert [m.name for m in PP_SLIDE_SHOW_TYPE] == ["SPEAKER", "WINDOW", "KIOSK"]

    def it_documents_every_member(self):
        assert all(member.__doc__ for member in PP_SLIDE_SHOW_TYPE)

    def it_has_a_short_alias(self):
        assert PP_SLIDE_SHOW is PP_SLIDE_SHOW_TYPE
