"""Unit, round-trip, and schema-validity tests for the Sections API."""

from __future__ import annotations

import io

import pytest

import power_pptx
from power_pptx.section import Section, Sections

# -- deterministic GUIDs so emitted XML is stable across runs --
GUID_A = "{11111111-1111-1111-1111-111111111111}"
GUID_B = "{22222222-2222-2222-2222-222222222222}"

_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_P14_NS = "http://schemas.microsoft.com/office/powerpoint/2010/main"


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

    def it_emits_the_required_sldIdLst_child_for_an_empty_section(self):
        # MS-PPTX 2.5.17 (CT_Section) makes `p14:sldIdLst` a required child
        # (minOccurs=1); PowerPoint writes it even for an empty section.
        prs = _deck(1)
        prs.sections.add("Empty", id=GUID_A)
        assert "<p14:sldIdLst" in prs._element.sectionLst.xml

    def it_adds_new_slides_to_the_final_section(self):
        # PowerPoint keeps the section list a complete partition of the deck;
        # a slide appended to a sectioned deck must join the last section
        # rather than belong to no section at all.
        prs = _deck(2)
        prs.sections.add("A", start_slide_index=0, id=GUID_A)
        prs.sections.add("B", start_slide_index=1, id=GUID_B)

        slide = prs.slides.add_slide(prs.slide_layouts[6])
        assert prs.sections[1].slide_ids[-1] == slide.slide_id
        # complete partition: every slide in exactly one section
        all_ids = [sid for section in prs.sections for sid in section.slide_ids]
        assert sorted(all_ids) == sorted(s.slide_id for s in prs.slides)
        assert len(all_ids) == len(set(all_ids))

    def but_adding_a_slide_to_an_unsectioned_deck_stays_a_no_op(self):
        prs = _deck(1)
        prs.slides.add_slide(prs.slide_layouts[6])
        assert prs._element.sectionLst is None

    def it_does_not_mutate_the_deck_when_sections_is_only_read(self):
        # Reading a property must not inject the PowerPoint-2010 extension
        # block (an empty <p14:sectionLst/> is itself invalid — CT_SectionList
        # requires at least one section).
        prs = _deck(1)
        assert len(prs.sections) == 0
        assert list(prs.sections) == []
        assert prs._element.sectionLst is None

    def it_merges_removed_section_slides_into_the_previous_section(self):
        prs = _deck(4)
        prs.sections.add("A", start_slide_index=0, id=GUID_A)
        b = prs.sections.add("B", start_slide_index=2, id=GUID_B)

        prs.sections.remove(b)

        assert len(prs.sections) == 1
        assert prs.sections[0].slide_ids == [256, 257, 258, 259]

    def it_merges_first_section_slides_into_the_next_section_in_order(self):
        prs = _deck(4)
        a = prs.sections.add("A", start_slide_index=0, id=GUID_A)
        prs.sections.add("B", start_slide_index=2, id=GUID_B)

        a.delete()

        assert len(prs.sections) == 1
        assert prs.sections[0].name == "B"
        assert prs.sections[0].slide_ids == [256, 257, 258, 259]

    def it_drops_the_section_extension_when_the_only_section_is_removed(self):
        prs = _deck(2)
        only = prs.sections.add("Only", start_slide_index=0, id=GUID_A)
        only.delete()
        assert len(prs.sections) == 0
        # No empty <p14:sectionLst/> (CT_SectionList minOccurs=1) may remain.
        assert prs._element.sectionLst is None

    def but_it_keeps_the_other_extensions_of_the_presentation(self):
        from power_pptx.oxml import parse_xml

        prs = _deck(2)
        only = prs.sections.add("Only", start_slide_index=0, id=GUID_A)
        extLst = prs._element.find("{%s}extLst" % _P_NS)
        extLst.append(parse_xml('<p:ext xmlns:p="%s" uri="{OTHER}"/>' % _P_NS))

        only.delete()

        assert prs._element.sectionLst is None
        assert [ext.get("uri") for ext in prs._element.find("{%s}extLst" % _P_NS)] == ["{OTHER}"]

    def it_does_nothing_when_a_section_is_deleted_twice(self):
        prs = _deck(4)
        prs.sections.add("A", start_slide_index=0, id=GUID_A)
        b = prs.sections.add("B", start_slide_index=2, id=GUID_B)
        b.delete()

        b.delete()

        assert [(s.name, s.slide_ids) for s in prs.sections] == [("A", [256, 257, 258, 259])]

    def it_removes_the_only_section_of_a_list_that_is_in_no_presentation(self):
        from power_pptx.oxml import parse_xml
        from power_pptx.section import _remove_section_element

        section_xml = (
            '<p14:sectionLst xmlns:p14="%s"><p14:section name="A" id="%s"><p14:sldIdLst>'
            '<p14:sldId id="256"/></p14:sldIdLst></p14:section></p14:sectionLst>'
            % (_P14_NS, GUID_A)
        )
        # -- a bare section list: nothing above it to remove --
        sectionLst = parse_xml(section_xml)
        _remove_section_element(sectionLst[0])
        assert len(sectionLst) == 1
        # -- an extension list with no presentation: its extension goes, it stays --
        extLst = parse_xml(
            '<p:extLst xmlns:p="%s"><p:ext uri="{521415D9-36F7-43E2-AB2F-B90AF26B5E84}">'
            "%s</p:ext></p:extLst>" % (_P_NS, section_xml)
        )
        _remove_section_element(extLst[0][0][0])
        assert len(extLst) == 0

    def it_moves_a_slide_between_sections_rather_than_duplicating_it(self):
        prs = _deck(2)
        a = prs.sections.add("A", start_slide_index=0, id=GUID_A)
        b = prs.sections.add("B", id=GUID_B)

        slide = prs.slides[0]
        b.add_slide(slide)

        assert slide.slide_id not in a.slide_ids
        assert slide.slide_id in b.slide_ids

    def it_covers_leading_slides_when_the_first_section_starts_past_zero(self):
        # PowerPoint never leaves a slide outside every section; a first
        # section starting at slide 2 gets an auto-created "Default Section"
        # covering slides 0-1.
        prs = _deck(4)
        prs.sections.add("Body", start_slide_index=2, id=GUID_A)

        assert len(prs.sections) == 2
        assert prs.sections[0].name == "Default Section"
        assert prs.sections[0].slide_ids == [256, 257]
        assert prs.sections[1].name == "Body"
        assert prs.sections[1].slide_ids == [258, 259]

    def it_rejects_a_malformed_section_id(self):
        prs = _deck(1)
        with pytest.raises(ValueError):
            prs.sections.add("Bad", id="not-a-guid")

    def it_rejects_a_duplicate_section_id(self):
        prs = _deck(2)
        prs.sections.add("A", start_slide_index=0, id=GUID_A)
        with pytest.raises(ValueError):
            prs.sections.add("B", id=GUID_A)

    def it_adds_an_imported_slide_to_the_final_section(self):
        src = _deck(1)
        prs = _deck(2)
        prs.sections.add("A", start_slide_index=0, id=GUID_A)
        prs.sections.add("B", start_slide_index=1, id=GUID_B)

        imported = prs.import_slide(src.slides[0])

        assert imported.slide_id in prs.sections[1].slide_ids
        all_ids = [sid for section in prs.sections for sid in section.slide_ids]
        assert sorted(all_ids) == sorted(s.slide_id for s in prs.slides)
        assert len(all_ids) == len(set(all_ids))


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


GUID_C = "{33333333-3333-3333-3333-333333333333}"
GUID_D = "{44444444-4444-4444-4444-444444444444}"


def _sectioned_deck(*starts, n_slides=6):
    """A deck of `n_slides` slides with sections A, B, ... starting at `starts`."""
    prs = _deck(n_slides)
    for name, start, guid in zip("ABCD", starts, (GUID_A, GUID_B, GUID_C, GUID_D)):
        prs.sections.add(name, start_slide_index=start, id=guid)
    return prs


def _layout(prs):
    """Each section as (name, [original slide numbers]), slide n having id 256 + n."""
    return [(s.name, [i - 256 for i in s.slide_ids]) for s in prs.sections]


def _assert_partition(prs):
    """Every slide is in exactly one section, and sections are contiguous runs."""
    deck = [s.slide_id for s in prs.slides]
    members = [i for section in prs.sections for i in section.slide_ids]
    assert members == deck


class DescribeSectionsFollowSlideOrder:
    """`Slides.move()` / `reorder()` keep the section list consistent."""

    def it_moves_a_slide_into_the_section_it_lands_in(self):
        # Regression: after move(5, 0) the slide sat at the front of the deck
        # but was still listed in the last section.
        prs = _sectioned_deck(0, 2, 4)

        prs.slides.move(5, 0)

        assert _layout(prs) == [("A", [5, 0, 1]), ("B", [2, 3]), ("C", [4])]
        _assert_partition(prs)

    def it_joins_the_section_of_the_slide_before_it(self):
        prs = _sectioned_deck(0, 2, 4)

        prs.slides.move(0, 3)  # -- lands after slide 3, in B

        assert _layout(prs) == [("A", [1]), ("B", [2, 3, 0]), ("C", [4, 5])]
        _assert_partition(prs)

    def but_it_stays_in_its_own_section_when_it_lands_next_to_it(self):
        prs = _sectioned_deck(0, 3)

        prs.slides.move(5, 3)  # -- between 2 (A) and 3 (B): next to its own B

        assert _layout(prs) == [("A", [0, 1, 2]), ("B", [5, 3, 4])]
        _assert_partition(prs)

    def and_it_can_leave_a_section_empty(self):
        prs = _sectioned_deck(0, 3, 4)  # -- B holds slide 3 alone

        prs.slides.move(3, 1)

        assert _layout(prs) == [("A", [0, 3, 1, 2]), ("B", []), ("C", [4, 5])]
        _assert_partition(prs)

    def it_moves_sections_with_their_slides_when_the_deck_is_reversed(self):
        prs = _sectioned_deck(0, 3)

        prs.slides.reorder([5, 4, 3, 2, 1, 0])

        assert _layout(prs) == [("B", [5, 4, 3]), ("A", [2, 1, 0])]
        _assert_partition(prs)

    def it_can_swap_whole_sections(self):
        prs = _sectioned_deck(0, 2, 4)

        prs.slides.reorder([4, 5, 0, 1, 2, 3])

        assert _layout(prs) == [("C", [4, 5]), ("A", [0, 1]), ("B", [2, 3])]
        _assert_partition(prs)

    def it_keeps_an_empty_section_after_the_one_it_followed(self):
        prs = _sectioned_deck(0, 3)
        prs.sections.add("Empty", id=GUID_C)  # -- last, after B
        empty = prs.sections[2]
        prs.sections[1]._element.addnext(empty._element)  # -- A, B, Empty
        prs.sections[0]._element.addnext(empty._element)  # -- A, Empty, B

        prs.slides.reorder([3, 4, 5, 0, 1, 2])

        assert _layout(prs) == [("B", [3, 4, 5]), ("A", [0, 1, 2]), ("Empty", [])]

    def it_treats_a_reorder_that_moves_one_slide_like_that_move(self):
        by_move, by_reorder = _sectioned_deck(0, 2, 4), _sectioned_deck(0, 2, 4)

        by_move.slides.move(5, 0)
        by_reorder.slides.reorder([5, 0, 1, 2, 3, 4])

        assert _layout(by_reorder) == _layout(by_move)

    def it_keeps_sections_contiguous_after_an_interleaving_reorder(self):
        prs = _sectioned_deck(0, 3)

        prs.slides.reorder([0, 3, 1, 4, 2, 5])

        _assert_partition(prs)
        assert [s.name for s in prs.sections] == ["A", "B"]

    def it_reorders_within_a_section_without_changing_membership(self):
        prs = _sectioned_deck(0, 3)

        prs.slides.reorder([2, 0, 1, 5, 3, 4])

        assert _layout(prs) == [("A", [2, 0, 1]), ("B", [5, 3, 4])]

    def it_drops_a_member_reference_to_a_slide_no_longer_in_the_deck(self):
        prs = _sectioned_deck(0, 3)
        prs.sections[0]._element.add_sldId(999)

        prs.slides.move(1, 0)

        assert _layout(prs) == [("A", [1, 0, 2]), ("B", [3, 4, 5])]

    def it_keeps_a_moved_slide_in_its_section_when_no_neighbour_has_one(self):
        prs = _deck(2)
        a = prs.sections.add("A", id=GUID_A)
        a.add_slide(prs.slides[1])  # -- slide 0 is in no section

        prs.slides.move(1, 0)

        assert _layout(prs) == [("A", [1])]

    def it_leaves_an_unsectioned_deck_unsectioned(self):
        prs = _deck(4)

        prs.slides.move(3, 0)
        prs.slides.reorder([1, 0, 3, 2])

        assert len(prs.sections) == 0
        assert prs.part._element.sectionLst is None

    @pytest.mark.parametrize(
        "operation",
        [
            lambda slides: slides.move(5, 0),
            lambda slides: slides.move(0, 5),
            lambda slides: slides.reorder([5, 4, 3, 2, 1, 0]),
            lambda slides: slides.reorder([0, 3, 1, 4, 2, 5]),
        ],
    )
    def it_saves_a_valid_deck_that_round_trips(self, operation):
        from tests.integration.round_trip import assert_round_trip
        from tests.schema.oxml_schema_validator import (
            iter_schema_violations,
            schema_validation_available,
        )

        prs = _sectioned_deck(0, 2, 4)
        operation(prs.slides)

        _assert_partition(prs)
        if schema_validation_available():
            assert list(iter_schema_violations(_save_bytes(prs))) == []
        assert_round_trip(prs)
