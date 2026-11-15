"""Unit-test suite for `power_pptx.oxml.slide` module."""

from __future__ import annotations

import pytest
from lxml import etree

from power_pptx.oxml import parse_xml
from power_pptx.oxml.slide import (
    CT_NotesMaster,
    CT_NotesSlide,
    slide_has_p14_transition,
    unwrap_p14_transitions,
    wrap_p14_transitions,
)

from ..unitutil.file import snippet_text

_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "p14": "http://schemas.microsoft.com/office/powerpoint/2010/main",
    "p15": "http://schemas.microsoft.com/office/powerpoint/2012/main",
}

# -- what PowerPoint 2013+ writes for the Airplane transition --
_P15_WRAPPER = (
    '<mc:AlternateContent xmlns:mc="%(mc)s">'
    '<mc:Choice xmlns:p15="%(p15)s" Requires="p15">'
    '<p:transition spd="slow" p14:dur="1250"><p15:prstTrans prst="airplane"/></p:transition>'
    "</mc:Choice>"
    '<mc:Fallback><p:transition spd="slow"><p:fade/></p:transition></mc:Fallback>'
    "</mc:AlternateContent>" % _NS
)


def _sld(transition_xml: str = ""):
    """A `p:sld` element holding `transition_xml` between its `p:clrMapOvr` and `p:timing`."""
    return parse_xml(
        '<p:sld xmlns:a="%(a)s" xmlns:p="%(p)s" xmlns:p14="%(p14)s">'
        "<p:cSld><p:spTree/></p:cSld>"
        "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>" % _NS
        + transition_xml
        + "<p:timing/></p:sld>"
    )


def _saved(sld):
    """The element tree `sld` serializes to: a copy with its transition wrapped."""
    copy = etree.fromstring(etree.tostring(sld))
    wrap_p14_transitions(copy)
    return copy


def _c14n(element) -> bytes:
    return etree.tostring(element, method="c14n", exclusive=True, with_tail=False)


def _child_names(element) -> list[str]:
    return [etree.QName(child).localname for child in element]


class DescribeTransitionWrappers(object):
    """Unit-test suite for the `mc:AlternateContent` transition wrap/unwrap functions."""

    def it_gives_the_slide_a_working_copy_of_a_wrapped_transition_on_load(self):
        sld = _sld(_P15_WRAPPER)

        unwrap_p14_transitions(sld)

        # -- the accessors see a plain transition where the wrapper was, and the
        # -- wrapper itself is kept right after it for the save --
        assert _child_names(sld) == [
            "cSld",
            "clrMapOvr",
            "transition",
            "AlternateContent",
            "timing",
        ]
        assert sld.transition.get("{%(p14)s}dur" % _NS) == "1250"
        assert sld.transition.kind_element.tag == "{%(p15)s}prstTrans" % _NS

    def it_writes_an_untouched_wrapper_back_exactly_as_it_was_read(self):
        original = _sld(_P15_WRAPPER)
        sld = _sld(_P15_WRAPPER)
        unwrap_p14_transitions(sld)

        assert slide_has_p14_transition(sld) is True
        assert _c14n(_saved(sld)) == _c14n(original)

    def it_keeps_a_fallback_it_would_not_have_written_itself(self):
        # -- the fallback is the authoring application's call: here a push, not
        # -- the fade this library generates for an extension kind --
        wrapper = _P15_WRAPPER.replace("<p:fade/>", '<p:push dir="u"/>')
        original = _sld(wrapper)
        sld = _sld(wrapper)
        unwrap_p14_transitions(sld)

        assert _c14n(_saved(sld)) == _c14n(original)

    def it_derives_Requires_from_the_namespace_of_an_extension_kind(self):
        sld = _sld(
            '<p:transition><p15:prstTrans xmlns:p15="%(p15)s" prst="wind"/></p:transition>' % _NS
        )

        saved = _saved(sld)

        choice = saved.find("mc:AlternateContent/mc:Choice", _NS)
        assert choice.get("Requires") == "p15"
        assert choice.nsmap["p15"] == _NS["p15"]
        assert choice.find("p:transition/p15:prstTrans", _NS) is not None

    def it_never_puts_an_extension_kind_in_the_fallback(self):
        sld = _sld(
            '<p:transition spd="slow" p14:dur="1250">'
            '<p15:prstTrans xmlns:p15="%(p15)s" prst="airplane"/></p:transition>' % _NS
        )

        fallback = _saved(sld).find("mc:AlternateContent/mc:Fallback/p:transition", _NS)

        # -- plain timing attributes and PowerPoint's own downgrade, nothing else --
        assert dict(fallback.attrib) == {"spd": "slow"}
        assert [child.tag for child in fallback] == ["{%(p)s}fade" % _NS]

    def it_wraps_a_classic_kind_carrying_an_extension_attribute(self):
        sld = _sld('<p:transition p14:dur="700"><p:push dir="u"/></p:transition>')

        ac = _saved(sld).find("mc:AlternateContent", _NS)

        assert ac.find("mc:Choice", _NS).get("Requires") == "p14"
        # -- a classic kind is valid in the fallback, so older viewers keep it --
        assert ac.find("mc:Fallback/p:transition/p:push", _NS).get("dir") == "u"
        assert ac.find("mc:Fallback/p:transition", _NS).attrib == {}

    def it_regenerates_the_wrapper_once_the_transition_is_changed(self):
        wrapper = _P15_WRAPPER.replace("<p:fade/>", '<p:push dir="u"/>')
        sld = _sld(wrapper)
        unwrap_p14_transitions(sld)

        sld.transition.advTm = 3000
        saved = _saved(sld)

        assert _child_names(saved) == ["cSld", "clrMapOvr", "AlternateContent", "timing"]
        choice = saved.find("mc:AlternateContent/mc:Choice", _NS)
        assert choice.get("Requires") == "p15"
        assert choice.find("p:transition", _NS).get("advTm") == "3000"
        fallback = saved.find("mc:AlternateContent/mc:Fallback/p:transition", _NS)
        assert dict(fallback.attrib) == {"spd": "slow", "advTm": "3000"}
        # -- the kind did not change, so its original downgrade still applies --
        assert [child.tag for child in fallback] == ["{%(p)s}push" % _NS]

    def but_it_does_not_reuse_the_fallback_of_a_different_kind(self):
        wrapper = _P15_WRAPPER.replace("<p:fade/>", '<p:push dir="u"/>')
        sld = _sld(wrapper)
        unwrap_p14_transitions(sld)

        kind = sld.transition.kind_element
        kind.set("prst", "curtains")
        fallback = _saved(sld).find("mc:AlternateContent/mc:Fallback/p:transition", _NS)

        assert [child.tag for child in fallback] == ["{%(p)s}fade" % _NS]

    def it_drops_the_wrapper_of_a_transition_that_was_removed(self):
        sld = _sld(_P15_WRAPPER)
        unwrap_p14_transitions(sld)

        sld.remove(sld.transition)

        assert _child_names(_saved(sld)) == ["cSld", "clrMapOvr", "timing"]

    def it_repairs_a_wrapper_an_earlier_release_corrupted(self):
        # -- load → save used to turn the Airplane wrapper into this: the wrong
        # -- `Requires`, and the p15 kind copied into the fallback --
        corrupted = (
            '<mc:AlternateContent xmlns:mc="%(mc)s">'
            '<mc:Choice Requires="p14">'
            '<p:transition xmlns:p15="%(p15)s" spd="slow" p14:dur="1250">'
            '<p15:prstTrans prst="airplane"/></p:transition></mc:Choice>'
            '<mc:Fallback><p:transition spd="slow">'
            '<p15:prstTrans xmlns:p15="%(p15)s" prst="airplane"/></p:transition></mc:Fallback>'
            "</mc:AlternateContent>" % _NS
        )
        sld = _sld(corrupted)

        unwrap_p14_transitions(sld)
        ac = _saved(sld).find("mc:AlternateContent", _NS)

        assert ac.find("mc:Choice", _NS).get("Requires") == "p15"
        fallback = ac.find("mc:Fallback/p:transition", _NS)
        assert [child.tag for child in fallback] == ["{%(p)s}fade" % _NS]

    @pytest.mark.parametrize(
        "fallback",
        [
            # -- an extension attribute, which is valid only inside the choice --
            '<p:transition spd="slow" p14:dur="1250"><p:fade/></p:transition>',
            # -- an extension kind, which a viewer taking the fallback cannot read --
            '<p:transition spd="slow"><p15:prstTrans xmlns:p15="%(p15)s" prst="airplane"/>'
            "</p:transition>" % _NS,
        ],
    )
    def it_regenerates_a_wrapper_whose_fallback_holds_extension_content(self, fallback):
        wrapper = _P15_WRAPPER.replace(
            '<p:transition spd="slow"><p:fade/></p:transition></mc:Fallback>',
            fallback + "</mc:Fallback>",
        )
        assert wrapper != _P15_WRAPPER
        sld = _sld(wrapper)

        unwrap_p14_transitions(sld)
        ac = _saved(sld).find("mc:AlternateContent", _NS)

        assert ac.find("mc:Choice", _NS).get("Requires") == "p15"
        fallback = ac.find("mc:Fallback/p:transition", _NS)
        assert dict(fallback.attrib) == {"spd": "slow"}
        assert [child.tag for child in fallback] == ["{%(p)s}fade" % _NS]

    def it_writes_back_the_wrapper_of_a_transition_without_a_kind(self):
        wrapper = (
            '<mc:AlternateContent xmlns:mc="%(mc)s"><mc:Choice Requires="p14">'
            '<p:transition spd="slow" p14:dur="1250"/></mc:Choice>'
            '<mc:Fallback><p:transition spd="slow"/></mc:Fallback>'
            "</mc:AlternateContent>" % _NS
        )
        original = _sld(wrapper)
        sld = _sld(wrapper)
        unwrap_p14_transitions(sld)

        assert _c14n(_saved(sld)) == _c14n(original)

    def it_leaves_a_classic_transition_alone(self):
        sld = _sld('<p:transition spd="med"><p:fade/></p:transition>')

        assert slide_has_p14_transition(sld) is False
        assert _child_names(_saved(sld)) == ["cSld", "clrMapOvr", "transition", "timing"]


class DescribeCT_NotesMaster(object):
    """Unit-test suite for `power_pptx.oxml.slide.CT_NotesMaster` objects."""

    def it_can_create_a_default_notesMaster_element(self):
        notesMaster = CT_NotesMaster.new_default()
        assert notesMaster.xml == snippet_text("default-notesMaster")


class DescribeCT_NotesSlide(object):
    """Unit-test suite for `power_pptx.oxml.slide.CT_NotesSlide` objects."""

    def it_can_create_a_new_notes_element(self):
        notes = CT_NotesSlide.new()
        assert notes.xml == snippet_text("default-notes")
