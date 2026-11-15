# pyright: reportPrivateUsage=false

"""Unit-test suite for `power_pptx._slide_remover`, the machinery behind `Slides.remove()`."""

from __future__ import annotations

import io

import pytest
from lxml import etree

from power_pptx import Presentation
from power_pptx._slide_remover import (
    _iter_remaining_parts,
    _remove_references,
    _unlink,
    _xml_of,
    remove_slide,
    slide_id_entries,
)
from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT
from power_pptx.oxml import parse_xml
from power_pptx.oxml.ns import nsdecls
from power_pptx.util import Inches

from .unitutil.slide_links import (
    PNG,
    add_custom_show,
    add_layout_button,
    add_outline_view_entries,
    custom_show_rIds,
    link_on_hover,
    outline_view_slides,
    titled_deck,
    view_props_part,
)

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _deck(count: int = 3) -> Presentation:
    return titled_deck(*("slide %d" % i for i in range(count)))


class DescribeRemoveSlide:
    """`remove_slide()` takes a slide out of its presentation with every reference to it."""

    def it_takes_the_slide_out_of_the_slide_list(self):
        prs = _deck()
        a, b, c = prs.slides

        remove_slide(prs.part, b.part)

        sldIds = prs.part._element.sldIdLst.sldId_lst
        assert [prs.part.related_part(s.rId) for s in sldIds] == [a.part, c.part]

    def it_drops_the_presentations_relationship_to_the_slide(self):
        prs = _deck()
        b = prs.slides[1]

        remove_slide(prs.part, b.part)

        assert all(rel.target_part is not b.part for rel in prs.part.rels.values())

    def it_takes_the_slide_out_of_its_section(self):
        prs = _deck()
        prs.sections.add("One", start_slide_index=0)
        prs.sections.add("Two", start_slide_index=1)
        b = prs.slides[1]

        remove_slide(prs.part, b.part)

        assert [s.slide_ids for s in prs.sections] == [[256], [258]]

    def it_keeps_a_section_it_empties(self):
        prs = _deck(2)
        prs.sections.add("One", start_slide_index=0)
        prs.sections.add("Two", start_slide_index=1)

        remove_slide(prs.part, prs.slides[1].part)

        assert [(s.name, s.slide_ids) for s in prs.sections] == [("One", [256]), ("Two", [])]

    def it_takes_the_slide_out_of_the_outline_view(self):
        prs = _deck()
        a, b, c = prs.slides
        add_outline_view_entries(prs, [a, b, c])

        remove_slide(prs.part, b.part)

        assert outline_view_slides(prs) == [a, c]
        assert all(rel.target_part is not b.part for rel in view_props_part(prs).rels.values())

    def it_takes_the_slide_out_of_every_custom_show(self):
        prs = _deck()
        a, b, c = prs.slides
        add_custom_show(prs, "Short", [b, c])
        add_custom_show(prs, "Long", [a, b, c])
        rId_a = prs.part.relate_to(a.part, RT.SLIDE)
        rId_c = prs.part.relate_to(c.part, RT.SLIDE)

        remove_slide(prs.part, b.part)

        assert custom_show_rIds(prs) == [[rId_c], [rId_a, rId_c]]

    def it_removes_a_shape_click_link_to_the_slide(self):
        prs = _deck()
        a, b, _ = prs.slides
        a.shapes[0].click_action.target_slide = b

        remove_slide(prs.part, b.part)

        assert a.shapes[0].click_action.target_slide is None
        assert a.part._element.xpath("//a:hlinkClick") == []
        assert all(rel.target_part is not b.part for rel in a.part.rels.values())
        assert a.shapes[0].text_frame.text == "slide 0"

    def it_removes_a_text_run_link_to_the_slide(self):
        prs = _deck()
        a, b, _ = prs.slides
        run = a.shapes[0].text_frame.paragraphs[0].runs[0]
        run.hyperlink.target_slide = b

        remove_slide(prs.part, b.part)

        assert run.hyperlink.target_slide is None
        assert run.text == "slide 0"
        assert all(rel.target_part is not b.part for rel in a.part.rels.values())

    def it_removes_a_hover_link_to_the_slide(self):
        prs = _deck()
        a, b, _ = prs.slides
        link_on_hover(a.shapes[0], b)

        remove_slide(prs.part, b.part)

        assert a.part._element.xpath("//a:hlinkHover") == []
        assert all(rel.target_part is not b.part for rel in a.part.rels.values())

    def it_removes_links_from_notes_slides_and_layouts_too(self):
        prs = _deck()
        a, b, _ = prs.slides
        a.notes = "see the next slide"
        notes_run = a.notes_slide.notes_text_frame.paragraphs[0].runs[0]
        notes_run.hyperlink.target_slide = b
        layout = prs.slide_layouts[6]
        add_layout_button(layout, b)

        remove_slide(prs.part, b.part)

        for part in (a.notes_slide.part, layout.part):
            assert all(rel.target_part is not b.part for rel in part.rels.values())
            assert part._element.xpath("//a:hlinkClick") == []

    def but_it_keeps_links_to_other_slides(self):
        prs = _deck()
        a, b, c = prs.slides
        a.shapes[0].click_action.target_slide = c
        c.shapes[0].text_frame.paragraphs[0].runs[0].hyperlink.address = "https://example.com"

        remove_slide(prs.part, b.part)

        assert a.shapes[0].click_action.target_slide == c
        assert c.shapes[0].text_frame.paragraphs[0].runs[0].hyperlink.address == (
            "https://example.com"
        )

    def it_leaves_the_removed_slides_own_parts_alone(self):
        prs = _deck()
        b = prs.slides[1]
        b.notes = "speaker notes"
        notes_part = b.notes_slide.part

        remove_slide(prs.part, b.part)

        # -- the notes slide still relates to its slide; it is simply no longer saved --
        assert any(rel.target_part is b.part for rel in notes_part.rels.values())

    def it_raises_on_a_slide_of_another_presentation(self):
        prs, other = _deck(), _deck(1)

        with pytest.raises(ValueError, match="belongs to another presentation"):
            remove_slide(prs.part, other.slides[0].part)

        assert len(prs.slides) == 3

    def it_raises_on_a_slide_already_removed(self):
        prs = _deck()
        b = prs.slides[1]
        remove_slide(prs.part, b.part)

        with pytest.raises(ValueError, match="may already have been removed"):
            remove_slide(prs.part, b.part)

        assert len(prs.slides) == 2


class DescribeSlideIdEntries:
    def it_returns_the_entries_listing_the_slide(self):
        prs = _deck()
        b = prs.slides[1]

        entries = slide_id_entries(prs.part, b.part)

        assert [e.id for e in entries] == [b.slide_id]

    def it_raises_when_the_presentation_has_no_slide_list(self):
        prs = Presentation()
        other = _deck(1)

        with pytest.raises(ValueError):
            slide_id_entries(prs.part, other.slides[0].part)


class DescribeRemoveReferences:
    def it_removes_slide_list_entries_and_hyperlinks_naming_the_ids(self):
        element = parse_xml(
            '<p:custShowLst %s><p:custShow name="s" id="0"><p:sldLst>'
            '<p:sld r:id="rId2"/><p:sld r:id="rId3"/><p:sld r:id="rId4"/>'
            "</p:sldLst></p:custShow></p:custShowLst>" % nsdecls("p", "r")
        )

        _remove_references(element, {"rId3"})

        assert [sld.get(RID) for sld in element.iter("{%s}sld" % P)] == ["rId2", "rId4"]

    def and_hyperlinks_naming_them(self):
        element = parse_xml(
            '<p:cNvPr %s id="2" name="a"><a:hlinkClick r:id="rId3" action="x"/>'
            '<a:hlinkHover r:id="rId4" action="x"/></p:cNvPr>' % nsdecls("p", "a", "r")
        )

        _remove_references(element, {"rId3", "rId4"})

        assert len(element) == 0

    def it_leaves_everything_else_alone(self):
        element = parse_xml('<p:sldLst %s><p:sld r:id="rId2"/></p:sldLst>' % nsdecls("p", "r"))
        before = etree.tostring(element)

        _remove_references(element, {"rId9"})

        assert etree.tostring(element) == before


class DescribeXmlOf:
    def it_returns_the_element_of_an_xml_part(self):
        prs = _deck(1)
        slide_part = prs.slides[0].part

        assert _xml_of(slide_part) is slide_part._element

    def it_parses_an_xml_part_kept_as_bytes(self):
        prs = _deck(1)

        element = _xml_of(view_props_part(prs))

        assert element is not None
        assert element.tag == "{%s}viewPr" % P

    def it_returns_None_for_a_binary_part(self):
        prs = _deck(1)
        prs.slides[0].shapes.add_picture(io.BytesIO(PNG), 0, 0)
        image_part = prs.slides[0].part.related_part(prs.slides[0].shapes[1]._element.blip_rId)

        assert _xml_of(image_part) is None

    def and_for_bytes_that_are_not_well_formed_xml(self):
        prs = _deck(1)
        part = view_props_part(prs)
        part.blob = b"<p:viewPr"

        assert _xml_of(part) is None


class DescribeIterRemainingParts:
    def it_does_not_pass_through_the_removed_part(self):
        prs = _deck()
        b = prs.slides[1]
        b.notes = "notes"

        parts = list(_iter_remaining_parts(prs.part.package, b.part))

        assert b.part not in parts
        assert b.notes_slide.part not in parts
        assert prs.slides[0].part in parts
        assert prs.part in parts

    def but_it_reaches_a_part_the_removed_part_shares(self):
        prs = _deck()
        a, b, _ = prs.slides
        a.shapes.add_picture(io.BytesIO(PNG), Inches(1), Inches(3))
        b.shapes.add_picture(io.BytesIO(PNG), Inches(1), Inches(3))
        image_part = b.part.related_part(b.shapes[1]._element.blip_rId)

        parts = list(_iter_remaining_parts(prs.part.package, b.part))

        assert image_part in parts


class DescribeUnlink:
    def it_drops_the_relationships_and_the_links_using_them(self):
        prs = _deck()
        a, b, _ = prs.slides
        a.shapes[0].click_action.target_slide = b
        link_on_hover(a.shapes[0], b)

        _unlink(a.part, b.part)

        assert all(rel.target_part is not b.part for rel in a.part.rels.values())
        assert a.part._element.xpath("//a:hlinkClick | //a:hlinkHover") == []

    def it_does_nothing_to_a_part_without_a_link(self):
        prs = _deck()
        a, b, _ = prs.slides
        before = (a.part._element.xml, dict(a.part.rels))

        _unlink(a.part, b.part)

        assert (a.part._element.xml, dict(a.part.rels)) == before
