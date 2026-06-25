"""Unit, round-trip, and schema-validity tests for the Sections API."""

from __future__ import annotations

import io

import pytest

import power_pptx
from power_pptx.section import Section, Sections

# -- deterministic GUIDs so emitted XML is stable across runs --
GUID_A = "{11111111-1111-1111-1111-111111111111}"
GUID_B = "{22222222-2222-2222-2222-222222222222}"


def _deck(n_slides: int = 4):
    """Return a fresh blank presentation with `n_slides` blank slides."""
    prs = power_pptx.Presentation()
    layout = prs.slide_layouts[6]  # blank
    for _ in range(n_slides):
        prs.slides.add_slide(layout)
    return prs


def _save_bytes(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


class DescribeSections:
    """Behaviour of the `prs.sections` collection."""

    def it_starts_empty(self):
        prs = _deck()
        assert isinstance(prs.sections, Sections)
        assert len(prs.sections) == 0
        assert list(prs.sections) == []

    def it_can_add_a_section_spanning_slides_from_an_index(self):
        prs = _deck(4)
        section = prs.sections.add("Intro", start_slide_index=0, id=GUID_A)

        assert isinstance(section, Section)
        assert len(prs.sections) == 1
        assert section.name == "Intro"
        assert section.id == GUID_A
        # -- four blank slides have ids 256..259 --
        assert section.slide_ids == [256, 257, 258, 259]

    def it_keeps_sections_contiguous_and_non_overlapping(self):
        # Adding a section that starts at slide 2 must take slides 2+ away from
        # the earlier section (PowerPoint sections don't overlap) — PR #39.
        prs = _deck(4)
        intro = prs.sections.add("Intro", start_slide_index=0, id=GUID_A)
        body = prs.sections.add("Body", start_slide_index=2, id=GUID_B)

        assert intro.slide_ids == [256, 257]
        assert body.slide_ids == [258, 259]
        # no slide id appears in two sections
        assert set(intro.slide_ids).isdisjoint(body.slide_ids)

    def it_can_add_an_empty_section(self):
        prs = _deck(2)
        section = prs.sections.add("Empty", id=GUID_A)
        assert section.slide_ids == []
        assert section.slides == ()

    def it_supports_indexing_and_iteration(self):
        prs = _deck(4)
        prs.sections.add("Intro", start_slide_index=0, id=GUID_A)
        prs.sections.add("Body", start_slide_index=2, id=GUID_B)

        assert len(prs.sections) == 2
        assert prs.sections[0].name == "Intro"
        assert prs.sections[1].name == "Body"
        assert [s.name for s in prs.sections] == ["Intro", "Body"]

    def it_raises_on_out_of_range_index(self):
        prs = _deck(1)
        prs.sections.add("Only", id=GUID_A)
        with pytest.raises(IndexError):
            prs.sections[5]

    def it_can_list_member_slides(self):
        prs = _deck(4)
        section = prs.sections.add("Body", start_slide_index=2, id=GUID_A)
        member_ids = [s.slide_id for s in section.slides]
        assert member_ids == [258, 259]

    def it_can_rename_a_section(self):
        prs = _deck(2)
        section = prs.sections.add("Old", start_slide_index=0, id=GUID_A)
        section.name = "New"
        assert section.name == "New"
        assert prs.sections[0].name == "New"

    def it_can_remove_a_section_via_the_collection(self):
        prs = _deck(2)
        a = prs.sections.add("A", start_slide_index=0, id=GUID_A)
        prs.sections.add("B", id=GUID_B)
        prs.sections.remove(a)

        assert len(prs.sections) == 1
        assert prs.sections[0].name == "B"

    def it_can_remove_a_section_via_delete(self):
        prs = _deck(2)
        a = prs.sections.add("A", start_slide_index=0, id=GUID_A)
        a.delete()
        assert len(prs.sections) == 0

    def it_emits_the_expected_section_list_xml(self):
        prs = _deck(2)
        prs.sections.add("Intro", start_slide_index=0, id=GUID_A)

        xml = prs._element.sectionLst.xml
        assert 'name="Intro"' in xml
        assert 'id="%s"' % GUID_A in xml
        assert "<p14:sldId" in xml
        assert 'id="256"' in xml
        assert 'id="257"' in xml

    def it_generates_a_stable_guid_when_none_given(self):
        prs = _deck(1)
        section = prs.sections.add("Auto", start_slide_index=0)
        assert section.id.startswith("{")
        assert section.id.endswith("}")


class DescribeSectionsPersistence:
    """The section extension survives save/reopen and validates clean."""

    def it_round_trips_byte_clean(self):
        from tests.integration.round_trip import assert_round_trip

        def factory():
            prs = _deck(4)
            prs.sections.add("Intro", start_slide_index=0, id=GUID_A)
            prs.sections.add("Body", start_slide_index=2, id=GUID_B)
            return prs

        assert_round_trip(factory)

    def it_survives_save_and_reopen(self):
        prs = _deck(4)
        prs.sections.add("Intro", start_slide_index=0, id=GUID_A)
        prs.sections.add("Body", start_slide_index=2, id=GUID_B)

        reopened = power_pptx.Presentation(io.BytesIO(_save_bytes(prs)))
        assert len(reopened.sections) == 2
        assert [s.name for s in reopened.sections] == ["Intro", "Body"]
        assert reopened.sections[0].id == GUID_A
        assert reopened.sections[1].slide_ids == [258, 259]

    def it_validates_against_the_ooxml_schema(self):
        try:
            from tests.schema.oxml_schema_validator import (
                iter_schema_violations,
                schema_validation_available,
            )
        except ImportError:  # pragma: no cover
            pytest.skip("schema validator unavailable")

        if not schema_validation_available():  # pragma: no cover
            pytest.skip("schema validation unavailable (lxml or XSDs missing)")

        prs = _deck(4)
        prs.sections.add("Intro", start_slide_index=0, id=GUID_A)
        prs.sections.add("Body", start_slide_index=2, id=GUID_B)

        violations = list(iter_schema_violations(_save_bytes(prs)))
        assert violations == []
