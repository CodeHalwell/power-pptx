# pyright: reportPrivateUsage=false

"""Validate decks after `Slides.remove()` / `Slides.duplicate()` against the ISO-29500 schema.

Removal rewrites `ppt/presentation.xml` (the slide list, sections and custom
shows) and every part that linked to the slide; duplication adds a slide with
its own notes and chart. Each must leave XML the schema accepts and no
dangling relationship or orphan slide, which PowerPoint would repair.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from lxml import etree

from ..unitutil.slide_links import add_chart, linked_deck, titled_deck
from .oxml_schema_validator import (
    assert_schema_valid,
    iter_schema_violations,
    schema_validation_available,
)

_NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}

pytestmark = pytest.mark.skipif(
    not schema_validation_available(),
    reason="lxml or the bundled ISO-29500 XSD schemas are unavailable",
)


def _saved(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


class DescribeRemovedSlideSchemaValidity:
    @pytest.mark.parametrize("index", [0, 1, 2, 3], ids=["a", "b", "c", "d"])
    def it_validates_after_removing_any_slide_of_a_linked_deck(self, index):
        prs = linked_deck()

        prs.slides.remove(prs.slides[index])

        assert_schema_valid(_saved(prs))

    def it_validates_after_removing_every_slide(self):
        prs = linked_deck()

        for slide in list(prs.slides):
            prs.slides.remove(slide)

        assert_schema_valid(_saved(prs))

    def it_validates_a_custom_show_left_without_slides(self):
        prs = linked_deck()
        b, c = prs.slides[1], prs.slides[2]

        prs.slides.remove(b)
        prs.slides.remove(c)
        blob = _saved(prs)

        assert_schema_valid(blob)
        # -- guard against passing vacuously: the show is there, and empty --
        shows = _presentation(blob).findall(".//p:custShowLst/p:custShow", _NS)
        assert [show.get("name") for show in shows] == ["Short"]
        assert shows[0].findall("p:sldLst/p:sld", _NS) == []

    def it_would_report_the_links_left_by_dropping_the_slide_by_hand(self):
        # -- self-test: what callers used to do leaves an orphan slide behind --
        prs = linked_deck()
        sldIdLst = prs.slides._sldIdLst
        sldId = sldIdLst.sldId_lst[1]
        prs.part.drop_rel(sldId.rId)
        sldIdLst.remove(sldId)

        violations = list(iter_schema_violations(_saved(prs)))

        assert any("orphan slide" in message for _, message in violations), violations


class DescribeDuplicatedSlideSchemaValidity:
    def it_validates_a_copy_with_notes_a_chart_and_links(self):
        prs = titled_deck("a", "b")
        a, b = prs.slides
        a.notes = "notes"
        add_chart(a)
        a.shapes[0].click_action.target_slide = b
        prs.sections.add("Only", start_slide_index=0)

        prs.slides.duplicate(a)
        prs.slides.duplicate(b, index=0)

        assert_schema_valid(_saved(prs))

    def it_validates_a_copy_of_a_slide_of_the_linked_deck(self):
        prs = linked_deck()

        prs.slides.duplicate(prs.slides[1])

        assert_schema_valid(_saved(prs))


def _presentation(blob: bytes):
    """The parsed `ppt/presentation.xml` of the package *blob*."""
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        return etree.fromstring(zf.read("ppt/presentation.xml"))
