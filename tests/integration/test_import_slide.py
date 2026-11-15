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

    def it_keeps_deduping_onto_a_master_it_cloned_earlier(self):
        # Regression (PR #41 review): cloning rebuilds the master's
        # p:sldLayoutIdLst with fresh rIds/ids, so a raw-XML fingerprint no
        # longer matched the source and every subsequent import cloned yet
        # another master/layout set. The fingerprint now normalises those
        # package-allocation artifacts out.
        src = Presentation()
        src.slide_masters[0]._element.cSld.set("name", "BrandedMaster")
        src.slides.add_slide(src.slide_layouts[6])
        src.slides.add_slide(src.slide_layouts[0])

        dst = Presentation()
        dst.import_slide(src.slides[0])  # dedupe miss -> clone
        assert len(dst.slide_masters) == 2
        dst.import_slide(src.slides[1])  # must dedupe onto that clone
        assert len(dst.slide_masters) == 2

    def but_masters_differing_only_in_referenced_image_content_do_not_dedupe(self):
        # The fingerprint normalises relationship ids with a token derived
        # from the referenced part's *content* — masking them with a constant
        # would let a source master with a different logo false-match a
        # destination master and hand the slide the wrong branding.
        from copy import deepcopy

        from power_pptx._slide_importer import _master_fingerprint
        from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT

        png_b = bytes.fromhex(
            "89504e470d0a1a0a0000000d494844520000000100000001080600"
            "00001f15c4890000000d49444154789c626001000000ffff030000"
            "060005a5f5e2bd0000000049454e44ae426082"
        )

        def deck_with_master_logo(png_bytes):
            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            pic = slide.shapes.add_picture(
                io.BytesIO(png_bytes), Inches(8), Inches(6), Inches(1), Inches(1)
            )
            master = prs.slide_masters[0]
            image_part = slide.part.related_part(pic._element.blip_rId)
            rId = master.part.relate_to(image_part, RT.IMAGE)
            pic_el = deepcopy(pic._element)
            for el in pic_el.iter():
                for attr_name in list(el.attrib):
                    if attr_name.endswith("}embed"):
                        el.set(attr_name, rId)
                if el.tag.endswith("}cNvPr"):
                    el.set("id", "999")
            master.shapes._spTree.append(pic_el)
            pic._element.getparent().remove(pic._element)
            return prs

        deck_a = deck_with_master_logo(_PNG)
        deck_b = deck_with_master_logo(png_b)

        fp_a = _master_fingerprint(deck_a.slide_masters[0].part)
        fp_b = _master_fingerprint(deck_b.slide_masters[0].part)
        assert fp_a != fp_b
        # ...while the same deck built twice fingerprints identically
        # (rId-allocation differences must not matter).
        deck_a2 = deck_with_master_logo(_PNG)
        assert _master_fingerprint(deck_a2.slide_masters[0].part) == fp_a

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


# ---------------------------------------------------------------------------
# Links from the imported slide to other slides
# ---------------------------------------------------------------------------


def _slide_part_names(prs: Presentation) -> list[str]:
    """Names of the slide parts in the package `prs` saves to."""
    import zipfile

    buf = io.BytesIO()
    prs.save(buf)
    with zipfile.ZipFile(buf) as z:
        return sorted(
            n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")
        )


def _saved_bytes(prs: Presentation) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _linked_source() -> Presentation:
    """Three slides: the first has a button that jumps to the second."""
    src = Presentation()
    blank = src.slide_layouts[6]
    a, b, c = (src.slides.add_slide(blank) for _ in range(3))
    button = a.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
    button.text_frame.text = "Go to appendix"
    button.click_action.target_slide = b
    b.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1)).text_frame.text = (
        "CONFIDENTIAL salary table"
    )
    c.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1)).text_frame.text = (
        "Public summary"
    )
    return src


class Describe_import_slide_links_to_other_slides:
    """Regression: a slide-jump link dragged its target slide into the package.

    The target arrived as an orphan part — not in `p:sldIdLst`, no layout
    relationship — carrying content the caller never asked to import.
    """

    def it_does_not_copy_a_slide_the_imported_slide_links_to(self):
        import zipfile

        src = _linked_source()
        dst = Presentation()

        dst.import_slide(src.slides[0])
        dst.import_slide(src.slides[2])

        assert len(dst.slides) == 2
        saved = _saved_bytes(dst)
        with zipfile.ZipFile(io.BytesIO(saved)) as z:
            slide_parts = [
                n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")
            ]
            leaked = [n for n in z.namelist() if b"CONFIDENTIAL" in z.read(n)]
        assert sorted(slide_parts) == ["ppt/slides/slide1.xml", "ppt/slides/slide2.xml"]
        assert leaked == []

    def it_removes_the_link_but_keeps_the_shape(self):
        src = _linked_source()
        dst = Presentation()

        imported = dst.import_slide(src.slides[0])

        button = imported.shapes[0]
        assert button.text_frame.text == "Go to appendix"
        assert button.click_action.target_slide is None
        assert button.click_action.hyperlink.address is None
        assert imported.part._element.xpath("//a:hlinkClick") == []
        assert not any(
            rel.reltype.endswith("/slide") for rel in imported.part.rels.values()
        )
        # -- the source deck is untouched --
        assert src.slides[0].shapes[0].click_action.target_slide == src.slides[1]

    def it_removes_a_text_run_link_to_a_slide_that_is_not_imported(self):
        from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT
        from power_pptx.oxml import parse_xml
        from power_pptx.oxml.ns import nsdecls

        src = _linked_source()
        a, b = src.slides[0], src.slides[1]
        box = a.shapes.add_textbox(Inches(1), Inches(3), Inches(3), Inches(1))
        run = box.text_frame.paragraphs[0].add_run()
        run.text = "see the appendix"
        rId = a.part.relate_to(b.part, RT.SLIDE)
        run._r.get_or_add_rPr().append(
            parse_xml(
                '<a:hlinkClick %s r:id="%s" action="ppaction://hlinksldjump"/>'
                % (nsdecls("a", "r"), rId)
            )
        )

        dst = Presentation()
        imported = dst.import_slide(a)

        assert imported.shapes[1].text_frame.text == "see the appendix"
        assert imported.part._element.xpath("//a:hlinkClick") == []
        assert _slide_part_names(dst) == ["ppt/slides/slide1.xml"]

    def it_repoints_the_link_at_a_target_imported_earlier(self):
        src = _linked_source()
        dst = Presentation()

        target = dst.import_slide(src.slides[1])
        linking = dst.import_slide(src.slides[0])

        assert linking.shapes[0].click_action.target_slide == target
        assert _slide_part_names(dst) == ["ppt/slides/slide1.xml", "ppt/slides/slide2.xml"]
        reopened = _round_trip(dst)
        assert reopened.slides[1].shapes[0].click_action.target_slide == reopened.slides[0]

    def but_not_at_a_target_that_has_since_been_deleted(self):
        src = _linked_source()
        dst = Presentation()
        dst.import_slide(src.slides[1])
        sldIdLst = dst.slides._sldIdLst
        dst.part.drop_rel(sldIdLst[0].rId)
        sldIdLst.remove(sldIdLst[0])

        linking = dst.import_slide(src.slides[0])

        assert linking.shapes[0].click_action.target_slide is None
        assert _slide_part_names(dst) == ["ppt/slides/slide1.xml"]

    def it_keeps_the_link_in_a_same_deck_import(self):
        deck = _linked_source()

        duplicate = deck.import_slide(deck.slides[0])

        assert len(deck.slides) == 4
        assert duplicate.shapes[0].click_action.target_slide == deck.slides[1]
        assert len(_slide_part_names(deck)) == 4

    def it_points_a_slide_that_links_to_itself_at_its_own_copy(self):
        src = Presentation()
        slide = src.slides.add_slide(src.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
        box.click_action.target_slide = slide

        dst = Presentation()
        dst.slides.add_slide(dst.slide_layouts[6])
        imported = dst.import_slide(slide)

        assert imported.shapes[0].click_action.target_slide == imported
        assert len(_slide_part_names(dst)) == 2

    def it_saves_a_package_that_survives_reopen_and_resave(self):
        # The orphan used to be renumbered onto a visible slide's partname the
        # moment `prs.slides` was touched after a reopen, so the next save
        # wrote two zip members called ppt/slides/slide2.xml.
        import zipfile
        from collections import Counter

        src = _linked_source()
        dst = Presentation()
        dst.import_slide(src.slides[0])
        dst.import_slide(src.slides[2])

        reopened = _round_trip(dst)
        assert len(reopened.slides) == 2
        resaved = _saved_bytes(reopened)

        with zipfile.ZipFile(io.BytesIO(resaved)) as z:
            duplicated = [n for n, count in Counter(z.namelist()).items() if count > 1]
        assert duplicated == []
        again = Presentation(io.BytesIO(resaved))
        assert [_first_textbox_text(s) for s in again.slides] == [
            "Go to appendix",
            "Public summary",
        ]


# ---------------------------------------------------------------------------
# Shared pictures / media and awkward partnames
# ---------------------------------------------------------------------------


class Describe_import_slide_shared_binaries:
    def it_reuses_an_image_the_destination_already_has(self):
        # Regression: ten slides sharing one picture arrived with ten copies
        # of it, multiplying the size of the merged deck.
        import zipfile

        src = Presentation()
        for _ in range(10):
            slide = src.slides.add_slide(src.slide_layouts[6])
            slide.shapes.add_picture(io.BytesIO(_PNG), Inches(1), Inches(1), Inches(2), Inches(2))

        dst = Presentation()
        for slide in src.slides:
            dst.import_slide(slide)

        with zipfile.ZipFile(io.BytesIO(_saved_bytes(dst))) as z:
            media = [n for n in z.namelist() if n.startswith("ppt/media/")]
        assert len(media) == 1
        image_parts = {id(s.part.related_part(s.shapes[0]._element.blip_rId)) for s in dst.slides}
        assert len(image_parts) == 1
        assert [s.shapes[0].image.blob for s in _round_trip(dst).slides] == [_PNG] * 10

    def it_reuses_an_image_added_to_the_destination_directly(self):
        src = Presentation()
        src.slides.add_slide(src.slide_layouts[6]).shapes.add_picture(
            io.BytesIO(_PNG), Inches(1), Inches(1)
        )
        dst = Presentation()
        own = dst.slides.add_slide(dst.slide_layouts[6]).shapes.add_picture(
            io.BytesIO(_PNG), Inches(1), Inches(1)
        )

        imported = dst.import_slide(src.slides[0])

        own_part = dst.slides[0].part.related_part(own._element.blip_rId)
        assert imported.part.related_part(imported.shapes[0]._element.blip_rId) is own_part

    def it_does_not_duplicate_an_image_in_a_same_deck_import(self):
        import zipfile

        deck = Presentation()
        deck.slides.add_slide(deck.slide_layouts[6]).shapes.add_picture(
            io.BytesIO(_PNG), Inches(1), Inches(1)
        )

        deck.import_slide(deck.slides[0])

        with zipfile.ZipFile(io.BytesIO(_saved_bytes(deck))) as z:
            media = [n for n in z.namelist() if n.startswith("ppt/media/")]
        assert len(media) == 1

    def but_it_keeps_different_images_apart(self):
        import zipfile

        other_png = bytes.fromhex(
            "89504e470d0a1a0a0000000d494844520000000100000001080600"
            "00001f15c4890000000d49444154789c626001000000ffff030000"
            "060005a5f5e2bd0000000049454e44ae426082"
        )
        src = Presentation()
        for png in (_PNG, other_png):
            src.slides.add_slide(src.slide_layouts[6]).shapes.add_picture(
                io.BytesIO(png), Inches(1), Inches(1)
            )

        dst = Presentation()
        for slide in src.slides:
            dst.import_slide(slide)

        with zipfile.ZipFile(io.BytesIO(_saved_bytes(dst))) as z:
            media = [n for n in z.namelist() if n.startswith("ppt/media/")]
        assert len(media) == 2
        assert [s.shapes[0].image.blob for s in _round_trip(dst).slides] == [_PNG, other_png]

    def it_gives_each_imported_chart_its_own_copy(self):
        # Only opaque binaries are shared; a chart is editable per slide.
        from power_pptx.chart.data import CategoryChartData
        from power_pptx.enum.chart import XL_CHART_TYPE

        src = Presentation()
        slide = src.slides.add_slide(src.slide_layouts[6])
        chart_data = CategoryChartData()
        chart_data.categories = ["a", "b"]
        chart_data.add_series("s", (1, 2))
        slide.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1), Inches(5), Inches(3), chart_data
        )

        dst = Presentation()
        first = dst.import_slide(src.slides[0])
        second = dst.import_slide(src.slides[0])

        assert first.shapes[0].chart.part is not second.shapes[0].chart.part


class Describe_import_slide_awkward_partnames:
    def it_imports_a_part_whose_name_contains_a_percent_sign(self):
        # Regression: the partname was spliced into a printf template, so
        # `/ppt/media/my%20logo.png` raised "not enough arguments for format
        # string".
        import zipfile

        deck = Presentation()
        deck.slides.add_slide(deck.slide_layouts[6]).shapes.add_picture(
            io.BytesIO(_PNG), Inches(1), Inches(1)
        )
        renamed = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(_saved_bytes(deck))) as zin, zipfile.ZipFile(
            renamed, "w", zipfile.ZIP_DEFLATED
        ) as zout:
            for name in zin.namelist():
                data = zin.read(name)
                if name == "ppt/media/image1.png":
                    name = "ppt/media/my%20logo.png"
                if name.endswith(".rels"):
                    data = data.replace(b"media/image1.png", b"media/my%20logo.png")
                zout.writestr(name, data)
        src = Presentation(io.BytesIO(renamed.getvalue()))
        assert any(
            part.partname == "/ppt/media/my%20logo.png" for part in src.part.package.iter_parts()
        )

        dst = Presentation()
        imported = dst.import_slide(src.slides[0])

        assert imported.shapes[0].image.blob == _PNG
        assert _round_trip(dst).slides[0].shapes[0].image.blob == _PNG

    def it_allocates_names_from_plain_prefix_and_suffix_pieces(self):
        from power_pptx._slide_importer import _numbered_partname

        assert _numbered_partname("/ppt/charts/chart3.xml") == ("/ppt/charts/chart", ".xml")
        assert _numbered_partname("/ppt/media/my%20logo.png") == ("/ppt/media/my%20logo", ".png")
        assert _numbered_partname("/ppt/media/100%.png") == ("/ppt/media/100%", ".png")
        assert _numbered_partname("/ppt/embeddings/ole12") == ("/ppt/embeddings/ole", "")
        assert _numbered_partname("/ppt/v1.2/thing7.bin") == ("/ppt/v1.2/thing", ".bin")


def _src_on_layout(index: int, *, name: str | None = None, type_: str | None = None):
    """A one-slide source deck on layout *index*, that layout renamed and retyped as given.

    A *type_* of ``""`` removes the layout's ``type`` attribute.
    """
    src = Presentation()
    layout = src.slide_layouts[index]
    if name is not None:
        layout._element.cSld.set("name", name)
    if type_ == "":
        del layout._element.attrib["type"]
    elif type_ is not None:
        layout._element.set("type", type_)
    src.slides.add_slide(layout)
    return src


class Describe_import_slide_layout_matching:
    """On a dedupe hit the slide goes on the matching master's layout of its name, else type."""

    def it_uses_the_layout_of_the_same_name(self):
        # -- "Blank" by name, although the type says "Title Only" --
        src = _src_on_layout(5, name="Blank", type_="titleOnly")
        dst = Presentation()

        imported = dst.import_slide(src.slides[0])

        assert len(dst.slide_masters) == 1
        assert imported.slide_layout == dst.slide_layouts[6]
        assert len(dst.slide_layouts) == 11

    def it_uses_the_layout_of_the_same_type_when_no_name_matches(self):
        src = _src_on_layout(5, name="House style: headline only")
        dst = Presentation()

        imported = dst.import_slide(src.slides[0])

        assert imported.slide_layout == dst.slide_layouts[5]
        assert len(dst.slide_layouts) == 11

    @pytest.mark.parametrize("type_", ["tbl", ""])
    def it_clones_the_layout_into_the_master_when_neither_matches(self, type_):
        src = _src_on_layout(5, name="House style: headline only", type_=type_)
        dst = Presentation()

        imported = dst.import_slide(src.slides[0])

        assert len(dst.slide_masters) == 1
        assert len(dst.slide_layouts) == 12
        assert imported.slide_layout == dst.slide_layouts[11]
        assert imported.slide_layout.name == "House style: headline only"
        reopened = _round_trip(dst)
        assert reopened.slides[0].slide_layout.name == "House style: headline only"


class Describe_remap_rids:
    """`_remap_rids()` rewrites relationship ids and drops links to what was left behind."""

    def _element(self, xml: str):
        from power_pptx.oxml import parse_xml
        from power_pptx.oxml.ns import nsdecls

        return parse_xml("<p:root %s>%s</p:root>" % (nsdecls("p", "a", "r"), xml))

    def _xml(self, element) -> str:
        from lxml import etree

        text = etree.tostring(element).decode()
        return text[text.index(">") + 1 : text.rindex("<")]

    def it_rewrites_each_known_id_and_leaves_the_rest(self):
        from power_pptx._slide_importer import _remap_rids

        element = self._element(
            '<a:blip r:embed="rId1" r:link="rId7" name="rId1"/><p:x r:id="rId2" id="rId2"/>'
        )

        _remap_rids(element, {"rId1": "rId10", "rId2": "rId20"})

        assert self._xml(element) == (
            '<a:blip r:embed="rId10" r:link="rId7" name="rId1"/><p:x r:id="rId20" id="rId2"/>'
        )

    def it_removes_a_hyperlink_whose_relationship_was_dropped(self):
        from power_pptx._slide_importer import _remap_rids

        element = self._element(
            '<a:rPr><a:hlinkClick r:id="rId3"/><a:hlinkMouseOver r:id="rId3"/></a:rPr>'
            '<a:hlinkHover r:id="rId1"/>'
        )

        _remap_rids(element, {"rId1": "rId9"}, {"rId3"})

        assert self._xml(element) == '<a:rPr/><a:hlinkHover r:id="rId9"/>'

    def but_only_the_attribute_on_another_element(self):
        from power_pptx._slide_importer import _remap_rids

        element = self._element('<p:custData r:id="rId3" name="kept"/><a:blip r:embed="rId4"/>')

        _remap_rids(element, {}, {"rId3"})

        assert self._xml(element) == '<p:custData name="kept"/><a:blip r:embed="rId4"/>'

    def and_it_leaves_a_hyperlink_that_has_no_parent_to_be_removed_from(self):
        from power_pptx._slide_importer import _remap_rids
        from power_pptx.oxml import parse_xml
        from power_pptx.oxml.ns import nsdecls

        element = parse_xml('<a:hlinkClick %s r:id="rId3"/>' % nsdecls("a", "r"))

        _remap_rids(element, {}, {"rId3"})

        assert element.xml == parse_xml('<a:hlinkClick %s r:id="rId3"/>' % nsdecls("a", "r")).xml

    def it_does_nothing_with_nothing_to_remap(self):
        from power_pptx._slide_importer import _remap_rids

        element = self._element('<a:hlinkClick r:id="rId3"/>')

        _remap_rids(element, {})

        assert self._xml(element) == '<a:hlinkClick r:id="rId3"/>'


class Describe_normalized_master_xml:
    """The master XML hashed for dedupe names each referenced part by its content."""

    def it_replaces_each_relationship_id_by_what_it_points_at(self):
        import hashlib

        from lxml import etree

        from power_pptx._slide_importer import _normalized_master_xml
        from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT
        from power_pptx.oxml import parse_xml
        from power_pptx.oxml.ns import nsdecls

        src = Presentation()
        slide = src.slides.add_slide(src.slide_layouts[6])
        picture = slide.shapes.add_picture(io.BytesIO(_PNG), Inches(1), Inches(1))
        image_part = slide.part.related_part(picture._element.blip_rId)
        master_part = src.slide_masters[0].part
        image_rId = master_part.relate_to(image_part, RT.IMAGE)
        link_rId = master_part.relate_to(
            "https://example.com/brand", RT.HYPERLINK, is_external=True
        )
        element = parse_xml(
            '<p:sldMaster %s><p:sldLayoutIdLst><p:sldLayoutId r:id="rId1"/></p:sldLayoutIdLst>'
            '<a:blip r:embed="%s"/><a:blip r:embed="%s" name="again"/>'
            '<a:hlinkClick r:id="%s"/><a:blip r:embed="rId999"/></p:sldMaster>'
            % (nsdecls("p", "a", "r"), image_rId, image_rId, link_rId)
        )

        normalized = _normalized_master_xml(master_part, element)

        image_token = hashlib.sha1(_PNG).hexdigest()
        expected = parse_xml(
            '<p:sldMaster %s><a:blip r:embed="%s"/><a:blip r:embed="%s" name="again"/>'
            '<a:hlinkClick r:id="external:https://example.com/brand"/>'
            '<a:blip r:embed="unresolved"/></p:sldMaster>'
            % (nsdecls("p", "a", "r"), image_token, image_token)
        )
        assert normalized == etree.tostring(expected)
        # -- the element given is left as it was --
        assert len(element) == 5


class Describe_import_slide_merge_master_argument:
    @pytest.mark.parametrize("bad", ["dedup", "Clone", "", None, "merge"])
    def it_rejects_an_unknown_merge_master_value(self, bad):
        # "dedup" used to be accepted silently and behave like "clone".
        src = _make_prs_with_text("A")
        dst = Presentation()

        with pytest.raises(ValueError, match="merge_master must be 'dedupe' or 'clone'"):
            dst.import_slide(src.slides[0], merge_master=bad)

        assert len(dst.slides) == 0
        assert len(dst.slide_masters) == 1
