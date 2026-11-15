# pyright: reportPrivateUsage=false

"""Unit-test suite for `power_pptx.oxml.presprops` module."""

from __future__ import annotations

from typing import cast

import pytest

from power_pptx.oxml.presprops import CT_PresentationProperties, CT_ShowProperties

from ..unitutil.cxml import element, xml


class DescribeCT_PresentationProperties(object):
    """Unit-test suite for `power_pptx.oxml.presprops.CT_PresentationProperties`."""

    def it_is_the_class_of_the_presentationPr_element(self):
        assert isinstance(element("p:presentationPr"), CT_PresentationProperties)

    def it_can_construct_an_empty_root_declaring_the_namespaces_PowerPoint_does(self):
        presentationPr = CT_PresentationProperties.new()

        assert isinstance(presentationPr, CT_PresentationProperties)
        assert len(presentationPr) == 0
        assert presentationPr.nsmap == {
            "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        }

    def it_knows_when_it_has_no_showPr(self):
        presentationPr = cast(CT_PresentationProperties, element("p:presentationPr/p:extLst"))
        assert presentationPr.showPr is None

    @pytest.mark.parametrize(
        ("cxml", "expected_cxml"),
        [
            # -- the sequence is htmlPubPr, webPr, prnPr, showPr, clrMru, extLst --
            ("p:presentationPr", "p:presentationPr/p:showPr"),
            ("p:presentationPr/p:extLst", "p:presentationPr/(p:showPr,p:extLst)"),
            ("p:presentationPr/p:clrMru", "p:presentationPr/(p:showPr,p:clrMru)"),
            (
                "p:presentationPr/(p:clrMru,p:extLst)",
                "p:presentationPr/(p:showPr,p:clrMru,p:extLst)",
            ),
            ("p:presentationPr/p:prnPr", "p:presentationPr/(p:prnPr,p:showPr)"),
            (
                "p:presentationPr/(p:htmlPubPr,p:webPr,p:prnPr,p:clrMru,p:extLst)",
                "p:presentationPr/(p:htmlPubPr,p:webPr,p:prnPr,p:showPr,p:clrMru,p:extLst)",
            ),
        ],
    )
    def it_adds_showPr_in_schema_order(self, cxml: str, expected_cxml: str):
        presentationPr = cast(CT_PresentationProperties, element(cxml))

        showPr = presentationPr.get_or_add_showPr()

        assert isinstance(showPr, CT_ShowProperties)
        assert presentationPr.xml == xml(expected_cxml)

    def it_returns_the_existing_showPr_rather_than_adding_a_second(self):
        presentationPr = cast(
            CT_PresentationProperties, element("p:presentationPr/(p:showPr{loop=1},p:extLst)")
        )

        showPr = presentationPr.get_or_add_showPr()

        assert showPr is presentationPr.showPr
        assert presentationPr.xml == xml("p:presentationPr/(p:showPr{loop=1},p:extLst)")

    def it_can_remove_its_showPr(self):
        presentationPr = cast(
            CT_PresentationProperties, element("p:presentationPr/(p:showPr,p:extLst)")
        )
        presentationPr._remove_showPr()
        assert presentationPr.xml == xml("p:presentationPr/p:extLst")


class DescribeCT_ShowProperties(object):
    """Unit-test suite for `power_pptx.oxml.presprops.CT_ShowProperties`."""

    @pytest.mark.parametrize(
        ("cxml", "loop", "animation", "timings", "narration"),
        [
            # -- absent attributes read as the schema defaults, except narration,
            # -- whose absence is reported rather than interpreted --
            ("p:showPr", False, True, True, None),
            ("p:showPr{loop=1}", True, True, True, None),
            ("p:showPr{loop=true}", True, True, True, None),
            ("p:showPr{loop=0}", False, True, True, None),
            ("p:showPr{showAnimation=0}", False, False, True, None),
            ("p:showPr{useTimings=false}", False, True, False, None),
            ("p:showPr{showNarration=1}", False, True, True, True),
            ("p:showPr{showNarration=0}", False, True, True, False),
            (
                "p:showPr{loop=1,showNarration=1,showAnimation=0,useTimings=0}",
                True,
                False,
                False,
                True,
            ),
        ],
    )
    def it_knows_its_attribute_values(
        self, cxml: str, loop: bool, animation: bool, timings: bool, narration: bool | None
    ):
        showPr = cast(CT_ShowProperties, element(cxml))

        assert showPr.loop is loop
        assert showPr.showAnimation is animation
        assert showPr.useTimings is timings
        assert showPr.showNarration is narration

    @pytest.mark.parametrize(
        ("cxml", "attr", "value", "expected_cxml"),
        [
            ("p:showPr", "loop", True, "p:showPr{loop=1}"),
            ("p:showPr{loop=1}", "loop", False, "p:showPr"),
            ("p:showPr", "useTimings", False, "p:showPr{useTimings=0}"),
            ("p:showPr{useTimings=0}", "useTimings", True, "p:showPr"),
            ("p:showPr", "showAnimation", False, "p:showPr{showAnimation=0}"),
            ("p:showPr{showAnimation=0}", "showAnimation", True, "p:showPr"),
            # -- narration is always written out, never left to the schema default --
            ("p:showPr", "showNarration", True, "p:showPr{showNarration=1}"),
            ("p:showPr{showNarration=1}", "showNarration", False, "p:showPr{showNarration=0}"),
            ("p:showPr{showNarration=0}", "showNarration", None, "p:showPr"),
        ],
    )
    def it_can_change_its_attribute_values(
        self, cxml: str, attr: str, value: bool | None, expected_cxml: str
    ):
        showPr = cast(CT_ShowProperties, element(cxml))
        setattr(showPr, attr, value)
        assert showPr.xml == xml(expected_cxml)

    @pytest.mark.parametrize(
        ("cxml", "expected_tag"),
        [
            ("p:showPr", None),
            ("p:showPr/p:sldAll", None),
            ("p:showPr/p:present", "present"),
            ("p:showPr/(p:browse,p:sldAll)", "browse"),
            ("p:showPr/(p:kiosk{restart=60000},p:sldAll,p:penClr)", "kiosk"),
        ],
    )
    def it_knows_its_show_type_child(self, cxml: str, expected_tag: str | None):
        showPr = cast(CT_ShowProperties, element(cxml))

        child = showPr.eg_showType

        assert (None if child is None else child.tag.rpartition("}")[2]) == expected_tag

    @pytest.mark.parametrize(
        ("cxml", "method", "expected_cxml"),
        [
            # -- the show type comes first: before the slide list, pen colour and extLst --
            ("p:showPr", "get_or_change_to_kiosk", "p:showPr/p:kiosk"),
            ("p:showPr/p:sldAll", "get_or_change_to_kiosk", "p:showPr/(p:kiosk,p:sldAll)"),
            (
                "p:showPr/p:sldRg{st=1,end=3}",
                "get_or_change_to_browse",
                "p:showPr/(p:browse,p:sldRg{st=1,end=3})",
            ),
            (
                "p:showPr/p:custShow{id=0}",
                "get_or_change_to_browse",
                "p:showPr/(p:browse,p:custShow{id=0})",
            ),
            ("p:showPr/p:penClr", "get_or_change_to_kiosk", "p:showPr/(p:kiosk,p:penClr)"),
            ("p:showPr/p:extLst", "get_or_change_to_kiosk", "p:showPr/(p:kiosk,p:extLst)"),
            # -- and replaces whichever show type was there --
            (
                "p:showPr/(p:present,p:sldAll,p:penClr,p:extLst)",
                "get_or_change_to_kiosk",
                "p:showPr/(p:kiosk,p:sldAll,p:penClr,p:extLst)",
            ),
            (
                "p:showPr/(p:kiosk,p:sldAll)",
                "get_or_change_to_browse",
                "p:showPr/(p:browse,p:sldAll)",
            ),
            (
                "p:showPr/(p:browse,p:sldAll)",
                "get_or_change_to_present",
                "p:showPr/(p:present,p:sldAll)",
            ),
        ],
    )
    def it_puts_the_show_type_child_in_schema_order(
        self, cxml: str, method: str, expected_cxml: str
    ):
        showPr = cast(CT_ShowProperties, element(cxml))
        getattr(showPr, method)()
        assert showPr.xml == xml(expected_cxml)

    def it_keeps_the_attributes_of_a_show_type_child_that_is_already_there(self):
        showPr = cast(CT_ShowProperties, element("p:showPr/p:kiosk{restart=60000}"))
        showPr.get_or_change_to_kiosk()
        assert showPr.xml == xml("p:showPr/p:kiosk{restart=60000}")

    def it_can_remove_its_show_type_child(self):
        showPr = cast(CT_ShowProperties, element("p:showPr/(p:kiosk,p:sldAll)"))
        showPr._remove_eg_showType()
        assert showPr.xml == xml("p:showPr/p:sldAll")

    @pytest.mark.parametrize(
        ("cxml", "expected_value"),
        [
            # -- only "narration on, everything else default, no children" is the
            # -- same show as having no element at all --
            ("p:showPr{showNarration=1}", True),
            ("p:showPr{showNarration=true,loop=0,useTimings=1,showAnimation=true}", True),
            ("p:showPr", False),
            ("p:showPr{showNarration=0}", False),
            ("p:showPr{showNarration=1,loop=1}", False),
            ("p:showPr{showNarration=1,useTimings=0}", False),
            ("p:showPr{showNarration=1,showAnimation=0}", False),
            ("p:showPr{showNarration=1}/p:present", False),
            ("p:showPr{showNarration=1}/p:sldAll", False),
            ("p:showPr{showNarration=1}/p:penClr", False),
            ("p:showPr{showNarration=1}/p:extLst", False),
            ("p:showPr{showNarration=1,r:id=rId9}", False),
        ],
    )
    def it_knows_whether_it_says_anything(self, cxml: str, expected_value: bool):
        showPr = cast(CT_ShowProperties, element(cxml))
        assert showPr.says_nothing is expected_value
