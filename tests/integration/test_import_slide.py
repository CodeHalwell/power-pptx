"""Integration tests for ``Presentation.import_slide()``."""

from __future__ import annotations

import io

import pytest

from power_pptx import Presentation
from power_pptx.util import Inches


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prs_with_text(*titles: str) -> Presentation:
    """Return a Presentation where each title becomes a slide with a text box."""
    prs = Presentation()
    for title in titles:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        tb.text_frame.text = title
    return prs


def _round_trip(prs: Presentation) -> Presentation:
    """Save *prs* to a BytesIO buffer and reopen it."""
    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    return Presentation(buf)


def _first_textbox_text(slide) -> str:
    for shape in slide.shapes:
        if shape.has_text_frame:
            return shape.text_frame.text
    return ""


# ---------------------------------------------------------------------------
# Basic slide import
# ---------------------------------------------------------------------------


class Describe_import_slide_basic:
    def it_appends_the_imported_slide(self):
        src = _make_prs_with_text("Hello")
        dst = Presentation()
        dst.slides.add_slide(dst.slide_layouts[6])
        assert len(dst.slides) == 1

        dst.import_slide(src.slides[0])

        assert len(dst.slides) == 2

    def it_preserves_slide_content(self):
        src = _make_prs_with_text("Unique Content XYZ")
        dst = Presentation()
        dst.import_slide(src.slides[0])

        assert _first_textbox_text(dst.slides[0]) == "Unique Content XYZ"

    def it_round_trips_successfully(self):
        src = _make_prs_with_text("Slide1", "Slide2")
        dst = Presentation()
        dst.import_slide(src.slides[0])
        dst.import_slide(src.slides[1])

        dst2 = _round_trip(dst)
        assert len(dst2.slides) == 2
        assert _first_textbox_text(dst2.slides[0]) == "Slide1"
        assert _first_textbox_text(dst2.slides[1]) == "Slide2"


# ---------------------------------------------------------------------------
# Master deduplication
# ---------------------------------------------------------------------------


class Describe_import_slide_dedupe:
    def it_reuses_identical_master_on_dedupe(self):
        """Importing from a matching master should not add a new master."""
        src = Presentation()
        src.slides.add_slide(src.slide_layouts[0])

        dst = Presentation()
        dst.slides.add_slide(dst.slide_layouts[0])
        master_count_before = len(dst.slide_masters)

        dst.import_slide(src.slides[0], merge_master="dedupe")

        assert len(dst.slide_masters) == master_count_before

    def it_adds_a_new_master_on_dedupe_miss(self):
        """Importing from a different-looking master should add a new master."""
        import zipfile, io as _io

        # Build a source pptx whose master has a subtly different theme XML
        src = Presentation()
        src.slides.add_slide(src.slide_layouts[6])

        # Patch the theme XML to make it different
        buf = _io.BytesIO()
        src.save(buf)
        buf.seek(0)

        # Modify the theme inside the zip to produce a 'different' package
        import zipfile as zf

        raw = buf.getvalue()
        out = _io.BytesIO()
        with zf.ZipFile(_io.BytesIO(raw)) as zin, zf.ZipFile(out, "w", zf.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.startswith("ppt/theme/"):
                    data = data.replace(b"Office Theme", b"Custom Theme XYZ")
                zout.writestr(item, data)

        out.seek(0)
        src2 = Presentation(out)

        dst = Presentation()
        dst.slides.add_slide(dst.slide_layouts[0])
        master_count_before = len(dst.slide_masters)

        dst.import_slide(src2.slides[0], merge_master="dedupe")

        assert len(dst.slide_masters) == master_count_before + 1

    def it_always_adds_a_master_on_clone_mode(self):
        """merge_master='clone' must always add a new master."""
        src = Presentation()
        src.slides.add_slide(src.slide_layouts[0])

        dst = Presentation()
        dst.slides.add_slide(dst.slide_layouts[0])
        before = len(dst.slide_masters)

        dst.import_slide(src.slides[0], merge_master="clone")

        assert len(dst.slide_masters) == before + 1

    def it_rebuilds_the_cloned_masters_layout_id_list(self):
        # Regression: the deep-copied master kept the SOURCE's
        # p:sldLayoutIdLst rIds while its new rels put the theme on rId1 —
        # so the first "layout" entry resolved to the theme part, every
        # other one was off by one, and the last layout was unlisted.
        from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT

        src = Presentation()
        src.slides.add_slide(src.slide_layouts[0])

        dst = Presentation()
        dst.import_slide(src.slides[0], merge_master="clone")

        cloned_master = list(dst.slide_masters)[-1]
        master_part = cloned_master.part
        entries = cloned_master._element.sldLayoutIdLst.sldLayoutId_lst
        n_layout_rels = sum(
            1
            for rel in master_part.rels.values()
            if not rel.is_external and rel.reltype == RT.SLIDE_LAYOUT
        )
        assert len(entries) == n_layout_rels
        for entry in entries:
            target = master_part.related_part(entry.rId)
            assert "slideLayout" in str(target.partname), (
                "sldLayoutId %s resolves to %s" % (entry.rId, target.partname)
            )

        # ids stay unique across every master's layout list + master ids
        ids = [e.get("id") for e in entries]
        for master in list(dst.slide_masters)[:-1]:
            lst = master._element.sldLayoutIdLst
            if lst is not None:
                ids += [e.get("id") for e in lst.sldLayoutId_lst]
        prs_elm = dst.part._element
        ids += list(prs_elm.xpath("p:sldMasterIdLst/p:sldMasterId/@id"))
        ids = [i for i in ids if i is not None]
        assert len(ids) == len(set(ids)), "duplicate hierarchy ids: %s" % ids

    def it_copies_a_cloned_layouts_own_dependencies(self):
        # Regression: cloned layouts lost their image dependencies, leaving
        # dangling r:embed references — a documented repair trigger for any
        # branded template with a logo on a layout.
        import re
        import zipfile

        from copy import deepcopy

        from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT

        # Build a source deck whose layout carries a picture.
        src = Presentation()
        slide = src.slides.add_slide(src.slide_layouts[6])
        pic = slide.shapes.add_picture(
            io.BytesIO(_PNG), Inches(8), Inches(6), Inches(1), Inches(1)
        )
        layout = src.slide_layouts[6]
        image_part = slide.part.related_part(pic._element.blip_rId)
        rId = layout.part.relate_to(image_part, RT.IMAGE)
        pic_el = deepcopy(pic._element)
        for el in pic_el.iter():
            for attr_name in list(el.attrib):
                if attr_name.endswith("}embed"):
                    el.set(attr_name, rId)
        for el in pic_el.iter():
            if el.tag.endswith("}cNvPr"):
                el.set("id", "999")  # clear of the layout's placeholder ids
                break
        layout.shapes._spTree.append(pic_el)
        pic._element.getparent().remove(pic._element)

        dst = Presentation()
        dst.import_slide(src.slides[0], merge_master="clone")

        buf = io.BytesIO()
        dst.save(buf)
        with zipfile.ZipFile(buf) as z:
            layout_names = [
                n for n in z.namelist()
                if re.match(r"ppt/slideLayouts/slideLayout\d+\.xml$", n)
            ]
            dangling = []
            for name in layout_names:
                xml_text = z.read(name).decode()
                embeds = re.findall(r'r:embed="([^"]+)"', xml_text)
                if not embeds:
                    continue
                rels_name = name.replace("slideLayouts/", "slideLayouts/_rels/") + ".rels"
                rels_text = z.read(rels_name).decode() if rels_name in z.namelist() else ""
                for embed_rId in embeds:
                    if 'Id="%s"' % embed_rId not in rels_text:
                        dangling.append((name, embed_rId))
        assert dangling == [], "dangling r:embed refs: %s" % dangling


# ---------------------------------------------------------------------------
# Multiple imports — partname collision handling
# ---------------------------------------------------------------------------


class Describe_import_slide_partnames:
    def it_avoids_duplicate_partnames_across_multiple_imports(self):
        """Multiple clone imports must not produce duplicate zip entries."""
        src = _make_prs_with_text("A", "B", "C")
        dst = Presentation()

        for slide in src.slides:
            dst.import_slide(slide, merge_master="clone")

        buf = io.BytesIO()
        dst.save(buf)
        buf.seek(0)

        import zipfile

        with zipfile.ZipFile(buf) as z:
            names = [i.filename for i in z.infolist()]

        # Partnames must be unique
        assert len(names) == len(set(names)), f"Duplicate partnames: {[n for n in names if names.count(n) > 1]}"

    def it_gives_the_imported_slide_a_unique_slide_id(self):
        src = _make_prs_with_text("X")
        dst = _make_prs_with_text("Y", "Z")

        dst.import_slide(src.slides[0])

        slide_ids = [slide.slide_id for slide in dst.slides]
        assert len(slide_ids) == len(set(slide_ids)), "Duplicate slide IDs found"


# ---------------------------------------------------------------------------
# Notes slide
# ---------------------------------------------------------------------------


class Describe_import_slide_notes:
    def it_preserves_a_notes_slide_if_present(self):
        src = Presentation()
        slide = src.slides.add_slide(src.slide_layouts[6])
        notes = slide.notes_slide
        notes.notes_text_frame.text = "Speaker note text"

        dst = Presentation()
        dst.import_slide(src.slides[0])

        imported_slide = dst.slides[0]
        assert imported_slide.has_notes_slide
        assert imported_slide.notes_slide.notes_text_frame.text == "Speaker note text"

    def it_binds_the_notes_slide_to_the_registered_slide_not_an_orphan_clone(self):
        # Regression: the copied notes slide's back-reference to its slide
        # used to trigger a SECOND clone of the whole slide graph — an orphan
        # part in the zip that the notes slide pointed at instead of the
        # slide registered in p:sldIdLst.
        import zipfile

        from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT

        src = Presentation()
        slide = src.slides.add_slide(src.slide_layouts[6])
        slide.notes_slide.notes_text_frame.text = "n"

        dst = Presentation()
        imported = dst.import_slide(src.slides[0])

        notes_part = imported.notes_slide.part
        assert notes_part.part_related_by(RT.SLIDE) is imported.part

        buf = io.BytesIO()
        dst.save(buf)
        with zipfile.ZipFile(buf) as z:
            slide_parts = [
                n for n in z.namelist()
                if n.startswith("ppt/slides/slide") and n.endswith(".xml")
            ]
        assert len(slide_parts) == len(dst.slides)

    def it_relinks_the_notes_slide_to_the_destination_notes_master(self):
        # ECMA-376 requires the notesSlide→notesMaster relationship;
        # PowerPoint always writes it, and its absence risks repair when
        # entering notes view or printing notes pages.
        from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT

        src = Presentation()
        slide = src.slides.add_slide(src.slide_layouts[6])
        slide.notes_slide.notes_text_frame.text = "n"

        dst = Presentation()
        imported = dst.import_slide(src.slides[0])

        notes_part = imported.notes_slide.part
        notes_master_part = notes_part.part_related_by(RT.NOTES_MASTER)
        assert notes_master_part is dst.part.notes_master_part

    def it_keeps_partnames_unique_when_a_slide_is_added_after_import(self):
        # Regression: the next-slide-partname allocator counted p:sldIdLst
        # entries only, so a slide added after an import could be written
        # under a partname the zip already carried — two different parts
        # with one name, which PowerPoint's package reader rejects.
        import zipfile
        from collections import Counter

        src = Presentation()
        slide = src.slides.add_slide(src.slide_layouts[6])
        slide.notes_slide.notes_text_frame.text = "n"

        dst = Presentation()
        dst.import_slide(src.slides[0])
        dst.slides.add_slide(dst.slide_layouts[6])

        buf = io.BytesIO()
        dst.save(buf)
        with zipfile.ZipFile(buf) as z:
            duplicated = [n for n, count in Counter(z.namelist()).items() if count > 1]
        assert duplicated == []


# 1x1 transparent PNG.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360000002000100ffff03000006000557bfabd4000000"
    "0049454e44ae426082"
)


class Describe_import_slide_relationship_remap:
    def it_keeps_image_embed_references_pointing_at_the_image(self):
        # Regression: the cloned slide XML kept the source rIds while
        # relationships were re-created in copy order, so a picture's
        # r:embed could end up pointing at the slide layout (wrong part) ->
        # PowerPoint repairs the deck and drops the image.
        import re
        import zipfile

        src = Presentation()
        s = src.slides.add_slide(src.slide_layouts[6])
        # A textbox first so the image is NOT the slide's first relationship.
        tb = s.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
        tb.text_frame.text = "hi"
        s.shapes.add_picture(io.BytesIO(_PNG), Inches(3), Inches(3), Inches(1), Inches(1))

        dst = Presentation()
        dst.import_slide(src.slides[0])
        buf = io.BytesIO()
        dst.save(buf)
        buf.seek(0)
        with zipfile.ZipFile(buf) as z:
            slide_parts = [
                n for n in z.namelist()
                if n.startswith("ppt/slides/slide") and n.endswith(".xml")
            ]
            idx = len(slide_parts)
            sx = z.read("ppt/slides/slide%d.xml" % idx).decode()
            rels = z.read("ppt/slides/_rels/slide%d.xml.rels" % idx).decode()
        relmap = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels))

        embeds = re.findall(r'r:embed="([^"]+)"', sx)
        assert embeds, "imported slide should still reference an image"
        for rid in embeds:
            assert rid in relmap, "r:embed=%r is dangling" % rid
            assert "media/" in relmap[rid], (
                "r:embed=%r points at %r, not an image" % (rid, relmap[rid])
            )
