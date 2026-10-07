"""Integration tests for ``Presentation.apply_template()``."""

from __future__ import annotations

import io
import zipfile

import pytest

from power_pptx import Presentation
from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT
from power_pptx.util import Inches

from ..schema.hierarchy_decks import (
    BLUE,
    RED,
    add_logo,
    add_theme_image_fill,
    embedded_images,
    needs_schema_validator,
    saved_bytes,
    solid_png,
    zip_names,
)
from ..schema.hierarchy_validator import iter_hierarchy_violations
from ..schema.oxml_schema_validator import iter_schema_violations

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_deck(*titles: str) -> Presentation:
    """Return a presentation where each title maps to one slide."""
    prs = Presentation()
    for i, title in enumerate(titles):
        layout_idx = i % len(prs.slide_layouts)
        slide = prs.slides.add_slide(prs.slide_layouts[layout_idx])
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        tb.text_frame.text = title
    return prs


def _as_stream(prs: Presentation) -> io.BytesIO:
    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf


def _round_trip(prs: Presentation) -> Presentation:
    return Presentation(_as_stream(prs))


def _all_text(prs: Presentation) -> list[str]:
    texts: list[str] = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    t = para.text
                    if t:
                        texts.append(t)
    return texts


# ---------------------------------------------------------------------------
# Happy path: name-matched layouts
# ---------------------------------------------------------------------------


class Describe_apply_template_happy_path:
    def it_preserves_all_slides(self):
        deck = _make_deck("Slide A", "Slide B", "Slide C")
        template = _make_deck("template")

        deck.apply_template(_as_stream(template))

        assert len(deck.slides) == 3

    def it_preserves_slide_text_content(self):
        deck = _make_deck("Important Content", "Critical Data")
        template = _make_deck("template slide")

        deck.apply_template(_as_stream(template))

        texts = _all_text(deck)
        assert "Important Content" in texts
        assert "Critical Data" in texts

    def it_round_trips_after_apply_template(self):
        deck = _make_deck("Hello", "World")
        template = _make_deck("t")
        deck.apply_template(_as_stream(template))

        deck2 = _round_trip(deck)
        assert len(deck2.slides) == 2
        texts = _all_text(deck2)
        assert "Hello" in texts
        assert "World" in texts

    def it_replaces_all_masters_with_template_masters(self):
        deck = _make_deck("slide")
        template = Presentation()
        template.slides.add_slide(template.slide_layouts[0])

        len(deck.slide_masters)
        deck.apply_template(_as_stream(template))
        after_master_count = len(deck.slide_masters)

        # Master count in the result equals the template's master count
        assert after_master_count == len(template.slide_masters)

    def it_produces_no_duplicate_partnames_in_saved_package(self):
        deck = _make_deck("A", "B", "C")
        template = _make_deck("t")
        deck.apply_template(_as_stream(template))

        buf = io.BytesIO()
        deck.save(buf)
        buf.seek(0)
        with zipfile.ZipFile(buf) as z:
            names = [i.filename for i in z.infolist()]
        assert len(names) == len(set(names)), (
            f"Duplicate partnames: {[n for n in names if names.count(n) > 1]}"
        )


# ---------------------------------------------------------------------------
# Fallback: template has fewer layouts
# ---------------------------------------------------------------------------


class Describe_apply_template_fallback:
    def it_falls_back_to_first_layout_when_no_name_match(self):
        """All slides should be remapped even when the template has no name match."""
        deck = _make_deck("Slide 1", "Slide 2")
        # Build a template where none of the layout names will match 'Blank'
        template = Presentation()
        template.slides.add_slide(template.slide_layouts[0])

        # Should not raise
        deck.apply_template(_as_stream(template))

        deck2 = _round_trip(deck)
        assert len(deck2.slides) == 2


# ---------------------------------------------------------------------------
# Old masters removed
# ---------------------------------------------------------------------------


class Describe_apply_template_old_masters:
    def it_removes_old_master_parts_from_the_saved_package(self):
        """After apply_template the old master/layout/theme XML should not appear."""
        # Give the original deck a uniquely identifiable theme
        import io as _io
        import zipfile as _zf

        deck = _make_deck("slide")
        buf = _io.BytesIO()
        deck.save(buf)
        buf.seek(0)
        raw = buf.getvalue()

        # Inject an easily-searchable marker into the original theme
        out = _io.BytesIO()
        with _zf.ZipFile(_io.BytesIO(raw)) as zin, _zf.ZipFile(out, "w", _zf.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.startswith("ppt/theme/"):
                    data = data.replace(b"Office Theme", b"ORIGINAL_MARKER_THEME")
                zout.writestr(item, data)
        out.seek(0)
        deck2 = Presentation(out)

        template = _make_deck("t")
        deck2.apply_template(_as_stream(template))

        saved = _io.BytesIO()
        deck2.save(saved)
        saved.seek(0)

        with _zf.ZipFile(saved) as z:
            all_xml = b"".join(z.read(n) for n in z.namelist() if n.endswith(".xml"))

        assert b"ORIGINAL_MARKER_THEME" not in all_xml, (
            "Old theme XML was retained in saved package after apply_template."
        )


# ---------------------------------------------------------------------------
# Helpers for the hierarchy / dependency / in-memory-state tests below
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# The cloned master must list its own cloned layouts
# ---------------------------------------------------------------------------


class Describe_apply_template_layout_lists:
    def it_lists_every_cloned_layout_so_the_saved_deck_can_be_iterated(self):
        # Regression: the cloned master kept the TEMPLATE master's `p:sldLayoutIdLst`, whose
        # r:ids index the template's relationships; in the clone the theme sits on rId1, so the
        # first entry resolved to the theme part ('ThemePart' has no attribute 'slide_layout')
        # and the last layout was not listed at all.
        template = Presentation()
        deck = _make_deck("A", "B")

        deck.apply_template(_as_stream(template))

        reopened = _round_trip(deck)
        names = [lo.name for master in reopened.slide_masters for lo in master.slide_layouts]
        assert names == [lo.name for lo in template.slide_layouts]

    def it_writes_master_and_layout_lists_that_resolve_to_the_right_parts(self):
        deck = _make_deck("A", "B")

        deck.apply_template(_as_stream(Presentation()))

        assert list(iter_hierarchy_violations(saved_bytes(deck))) == []

    def it_gives_every_master_and_layout_of_a_multi_master_template_a_unique_id(self):
        template = Presentation()
        donor = Presentation()
        donor.slides.add_slide(donor.slide_layouts[0])
        template.import_slide(donor.slides[0], merge_master="clone")
        assert len(template.slide_masters) == 2
        n_layouts = len(Presentation().slide_layouts)
        deck = _make_deck("A")

        deck.apply_template(_as_stream(template))

        blob = saved_bytes(deck)
        assert list(iter_hierarchy_violations(blob)) == []
        reopened = Presentation(io.BytesIO(blob))
        assert [len(m.slide_layouts) for m in reopened.slide_masters] == [n_layouts, n_layouts]
        assert [len(m.slide_layouts) for m in deck.slide_masters] == [n_layouts, n_layouts]


# ---------------------------------------------------------------------------
# Pictures and other dependencies of the template master / layouts / theme
# ---------------------------------------------------------------------------


class Describe_apply_template_dependencies:
    def it_copies_the_pictures_of_the_template_master_and_layout(self):
        # Regression: dependencies of the cloned master and layouts were never copied and their
        # r:ids never remapped, so every logo was lost (dangling r:embed, empty ppt/media).
        template = Presentation()
        add_logo(template, template.slide_master.part, solid_png(RED), shape_id=900)
        add_logo(template, template.slide_layouts[0].part, solid_png(BLUE), shape_id=901)
        deck = _make_deck("A")

        deck.apply_template(_as_stream(template))

        blob = saved_bytes(deck)
        [master] = zip_names(blob, r"ppt/slideMasters/slideMaster\d+\.xml")
        assert embedded_images(blob, master) == [solid_png(RED)]
        layout_images = [
            images
            for name in zip_names(blob, r"ppt/slideLayouts/slideLayout\d+\.xml")
            if (images := embedded_images(blob, name))
        ]
        assert layout_images == [[solid_png(BLUE)]]
        assert len(zip_names(blob, r"ppt/media/.*")) == 2

    @needs_schema_validator
    def it_produces_a_schema_valid_package_for_a_template_with_pictures(self):
        template = Presentation()
        add_logo(template, template.slide_master.part, solid_png(RED), shape_id=900)
        add_logo(template, template.slide_layouts[0].part, solid_png(BLUE), shape_id=901)
        assert list(iter_schema_violations(saved_bytes(template))) == []
        deck = _make_deck("A", "B")

        deck.apply_template(_as_stream(template))

        blob = saved_bytes(deck)
        assert list(iter_schema_violations(blob)) == []
        assert list(iter_hierarchy_violations(blob)) == []

    def it_stores_a_picture_shared_by_master_and_layout_once(self):
        template = Presentation()
        add_logo(template, template.slide_master.part, solid_png(RED), shape_id=900)
        add_logo(template, template.slide_layouts[0].part, solid_png(RED), shape_id=901)
        deck = _make_deck("A")

        deck.apply_template(_as_stream(template))

        blob = saved_bytes(deck)
        assert len(zip_names(blob, r"ppt/media/.*")) == 1
        [master] = zip_names(blob, r"ppt/slideMasters/slideMaster\d+\.xml")
        assert embedded_images(blob, master) == [solid_png(RED)]
        layout_images = [
            images
            for name in zip_names(blob, r"ppt/slideLayouts/slideLayout\d+\.xml")
            if (images := embedded_images(blob, name))
        ]
        assert layout_images == [[solid_png(RED)]]

    @needs_schema_validator
    def it_copies_images_referenced_by_the_template_theme(self):
        template = Presentation()
        add_theme_image_fill(template, solid_png(RED))
        assert list(iter_schema_violations(saved_bytes(template))) == []
        deck = _make_deck("A")

        deck.apply_template(_as_stream(template))

        blob = saved_bytes(deck)
        [theme] = zip_names(blob, r"ppt/theme/theme\d+\.xml")
        assert embedded_images(blob, theme) == [solid_png(RED)]
        assert list(iter_schema_violations(blob)) == []

    def it_keeps_slide_content_and_pictures_on_the_slides_themselves(self):
        template = Presentation()
        add_logo(template, template.slide_master.part, solid_png(RED), shape_id=900)
        deck = _make_deck("Keep me")
        deck.slides[0].shapes.add_picture(
            io.BytesIO(solid_png(BLUE)), Inches(1), Inches(3), Inches(1), Inches(1)
        )

        deck.apply_template(_as_stream(template))

        reopened = _round_trip(deck)
        assert "Keep me" in _all_text(reopened)
        blob = saved_bytes(deck)
        [slide] = zip_names(blob, r"ppt/slides/slide\d+\.xml")
        assert embedded_images(blob, slide) == [solid_png(BLUE)]


# ---------------------------------------------------------------------------
# The in-memory deck must work right after the call, not only after save + reopen
# ---------------------------------------------------------------------------


class Describe_apply_template_in_memory_state:
    def it_leaves_the_presentation_usable_without_a_save_and_reopen(self):
        # Regression: the old `p:sldMasterIdLst` was removed and a new one created, but
        # `Presentation.slide_masters` (a lazyproperty) stayed bound to the detached old element
        # whose entry still said rId1, so layouts / the master / add_slide all raised
        # KeyError("no relationship with key 'rId1'").
        template = Presentation()
        template.slide_master._element.cSld.set("name", "BrandMaster")
        deck = _make_deck("A", "B")

        deck.apply_template(_as_stream(template))

        assert deck.slide_master._element.cSld.get("name") == "BrandMaster"
        layout = deck.slide_layouts[0]
        new_slide = deck.slides.add_slide(layout)
        assert new_slide.slide_layout.part is layout.part
        assert len(deck.slides) == 3

    def it_keeps_a_previously_obtained_masters_collection_pointing_at_the_new_masters(self):
        deck = _make_deck("A")
        masters = deck.slide_masters
        old_master_part = masters[0].part

        deck.apply_template(_as_stream(Presentation()))

        assert len(masters) == 1
        assert masters[0].part is deck.slide_master.part
        assert masters[0].part is not old_master_part

    def it_points_every_slide_at_a_layout_of_the_new_master(self):
        deck = _make_deck("A", "B", "C")

        deck.apply_template(_as_stream(Presentation()))

        new_master_part = deck.slide_master.part
        for slide in deck.slides:
            assert slide.slide_layout.slide_master.part is new_master_part

    def it_lets_later_imports_dedupe_onto_the_applied_masters(self):
        template = Presentation()
        add_logo(template, template.slide_master.part, solid_png(RED), shape_id=900)
        template.slides.add_slide(template.slide_layouts[0])
        deck = _make_deck("A")
        deck.apply_template(_as_stream(template))

        imported = deck.import_slide(Presentation(_as_stream(template)).slides[0])

        assert len(deck.slide_masters) == 1
        assert len(deck.slides) == 2
        assert imported.slide_layout.slide_master.part is deck.slide_master.part
        assert deck.slides[0].slide_layout.slide_master.part is deck.slide_master.part

    def it_lets_an_applied_deck_be_saved_edited_and_saved_again(self):
        template = Presentation()
        add_logo(template, template.slide_master.part, solid_png(RED), shape_id=900)
        deck = _make_deck("A")
        deck.apply_template(_as_stream(template))
        deck.slides.add_slide(deck.slide_layouts[1]).shapes.title.text = "Added afterwards"

        reopened = _round_trip(deck)

        assert len(reopened.slides) == 2
        assert "Added afterwards" in [
            sh.text_frame.text for sh in reopened.slides[1].shapes if sh.has_text_frame
        ]


# ---------------------------------------------------------------------------
# Old masters really go away; the presentation's theme relationship follows the new master
# ---------------------------------------------------------------------------


class Describe_apply_template_old_parts:
    def it_leaves_exactly_the_template_masters_layouts_and_themes_in_the_package(self):
        template = Presentation()
        deck = _make_deck("A", "B")

        deck.apply_template(_as_stream(template))

        blob = saved_bytes(deck)
        assert len(zip_names(blob, r"ppt/slideMasters/slideMaster\d+\.xml")) == 1
        assert len(zip_names(blob, r"ppt/slideLayouts/slideLayout\d+\.xml")) == len(
            template.slide_layouts
        )
        assert len(zip_names(blob, r"ppt/theme/theme\d+\.xml")) == 1

    def it_leaves_no_old_media_behind_when_the_old_master_carried_a_picture(self):
        deck = _make_deck("A")
        add_logo(deck, deck.slide_master.part, solid_png(RED), shape_id=900)
        assert len(zip_names(saved_bytes(deck), r"ppt/media/.*")) == 1

        deck.apply_template(_as_stream(Presentation()))

        assert zip_names(saved_bytes(deck), r"ppt/media/.*") == []

    def it_points_the_presentation_theme_relationship_at_the_new_master_theme(self):
        deck = _make_deck("A")
        deck.apply_template(_as_stream(Presentation()))

        reopened = _round_trip(deck)

        new_theme_part = reopened.slide_master.part.part_related_by(RT.THEME)
        assert reopened.part.part_related_by(RT.THEME) is new_theme_part
        assert deck.part.part_related_by(RT.THEME) is deck.slide_master.part.part_related_by(
            RT.THEME
        )

    def it_keeps_speaker_notes_and_gives_the_new_theme_a_partname_of_its_own(self):
        deck = _make_deck("A")
        deck.slides[0].notes_slide.notes_text_frame.text = "speaker notes"

        deck.apply_template(_as_stream(Presentation()))

        blob = saved_bytes(deck)
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            members = z.namelist()
        assert len(members) == len(set(members))
        # -- the new master's theme and the notes master's own theme --
        assert len(zip_names(blob, r"ppt/theme/theme\d+\.xml")) == 2
        reopened = _round_trip(deck)
        assert reopened.slides[0].notes_slide.notes_text_frame.text == "speaker notes"

    def it_copes_with_a_template_master_that_has_no_theme(self):
        template = Presentation()
        master_part = template.slide_master.part
        [theme_rId] = [rId for rId, rel in master_part.rels.items() if rel.reltype == RT.THEME]
        master_part.rels.pop(theme_rId)
        deck = _make_deck("A")

        deck.apply_template(_as_stream(template))

        assert deck.theme is None
        assert [r for r in deck.part.rels.values() if r.reltype == RT.THEME] == []
        assert list(iter_hierarchy_violations(saved_bytes(deck))) == []
        assert len(_round_trip(deck).slides) == 1

    def it_can_be_applied_more_than_once(self):
        deck = _make_deck("A", "B")

        deck.apply_template(_as_stream(Presentation()))
        deck.apply_template(_as_stream(Presentation()))

        assert len(deck.slide_masters) == 1
        blob = saved_bytes(deck)
        assert list(iter_hierarchy_violations(blob)) == []
        assert len(zip_names(blob, r"ppt/slideMasters/slideMaster\d+\.xml")) == 1
        assert len(_round_trip(deck).slides) == 2

    def it_leaves_the_deck_unchanged_and_warns_when_the_template_has_no_layouts(self):
        template = Presentation()
        for layout in list(template.slide_layouts):
            template.slide_layouts.remove(layout)
        deck = _make_deck("A")
        master_part = deck.slide_master.part
        layout_part = deck.slides[0].slide_layout.part

        with pytest.warns(UserWarning, match="no layouts") as record:
            deck.apply_template(_as_stream(template))

        assert record[0].filename == __file__
        assert deck.slide_master.part is master_part
        assert deck.slides[0].slide_layout.part is layout_part
        assert list(iter_hierarchy_violations(saved_bytes(deck))) == []


# ---------------------------------------------------------------------------
# Layout matching (name, then type, then the template's first layout)
# ---------------------------------------------------------------------------


class Describe_apply_template_layout_matching:
    def it_matches_slides_to_template_layouts_by_name(self):
        deck = _make_deck("A", "B", "C")
        original_names = [s.slide_layout.name for s in deck.slides]

        deck.apply_template(_as_stream(Presentation()))

        assert [s.slide_layout.name for s in deck.slides] == original_names

    def it_falls_back_to_the_layout_type_when_no_name_matches(self):
        template = Presentation()
        template.slide_layouts[1]._element.cSld.set("name", "Renamed Content")
        deck = Presentation()
        deck.slides.add_slide(deck.slide_layouts[1])

        deck.apply_template(_as_stream(template))

        assert deck.slides[0].slide_layout.name == "Renamed Content"

    def it_falls_back_to_the_templates_first_layout_when_nothing_matches(self):
        template = Presentation()
        template.slide_layouts[0]._element.cSld.set("name", "Brand Opener")
        deck = Presentation()
        orphan_layout = deck.slide_layouts[0]
        orphan_layout._element.cSld.set("name", "Orphan")
        orphan_layout._element.attrib.pop("type", None)
        deck.slides.add_slide(orphan_layout)

        deck.apply_template(_as_stream(template))

        assert deck.slides[0].slide_layout.name == "Brand Opener"
