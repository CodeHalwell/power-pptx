"""Integration tests for ``Presentation.apply_template()``."""

from __future__ import annotations

import io
import zipfile

import pytest

from power_pptx import Presentation
from power_pptx.util import Inches


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

        before_master_count = len(deck.slide_masters)
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
        import io as _io, zipfile as _zf

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
# Master / layout wiring of the applied template
# ---------------------------------------------------------------------------

_RED_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360000002000100ffff03000006000557bfabd4000000"
    "0049454e44ae426082"
)
_OTHER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600"
    "00001f15c4890000000d49444154789c626001000000ffff030000"
    "060005a5f5e2bd0000000049454e44ae426082"
)


def _add_picture_to(owner, prs, png_bytes: bytes) -> None:
    """Put a picture on a slide master or layout (neither has `add_picture()`)."""
    from copy import deepcopy

    from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT

    scratch = prs.slides.add_slide(prs.slide_layouts[6])
    pic = scratch.shapes.add_picture(
        io.BytesIO(png_bytes), Inches(0.2), Inches(0.2), Inches(1), Inches(1)
    )
    image_part = scratch.part.related_part(pic._element.blip_rId)
    rId = owner.part.relate_to(image_part, RT.IMAGE)
    pic_el = deepcopy(pic._element)
    pic_el.blipFill.blip.rEmbed = rId
    pic_el.nvPicPr.cNvPr.id = 1 + max(int(v) for v in owner._element.xpath("//p:cNvPr/@id"))
    owner.shapes._spTree.append(pic_el)
    # -- the scratch slide was only a way to get a p:pic element --
    sldIdLst = prs.slides._sldIdLst
    sldId = sldIdLst[-1]
    prs.part.drop_rel(sldId.rId)
    sldIdLst.remove(sldId)


def _branded_template() -> io.BytesIO:
    """A template with one picture on its master and another on a layout."""
    template = Presentation()
    _add_picture_to(template.slide_master, template, _RED_PNG)
    _add_picture_to(template.slide_layouts[1], template, _OTHER_PNG)
    return _as_stream(template)


def _picture_blobs(shapes) -> list[bytes]:
    return [shape.image.blob for shape in shapes if hasattr(shape, "image")]


class Describe_apply_template_master_wiring:
    """Regression: the cloned master kept the template's `p:sldLayoutIdLst`.

    Its relationships were rebuilt theme-first, so every layout id was off by
    one: the first resolved to the theme part and the deck could neither be
    used in the same session nor reopened and iterated.
    """

    def it_leaves_the_deck_usable_in_the_same_session(self):
        deck = Presentation()
        deck.slides.add_slide(deck.slide_layouts[1])
        template = _as_stream(Presentation())

        deck.apply_template(template)

        assert deck.slide_layouts[1].name == "Title and Content"
        assert [layout.name for layout in deck.slide_layouts] == [
            layout.name for layout in Presentation().slide_layouts
        ]
        assert deck.slide_master.name == Presentation().slide_master.name
        assert deck.theme is not None
        new_slide = deck.slides.add_slide(deck.slide_layouts[1])
        assert new_slide.slide_layout.name == "Title and Content"
        assert len(deck.slides) == 2

    def it_keeps_slide_masters_obtained_earlier_in_step(self):
        # `prs.slide_masters` is cached on the Presentation object; it must
        # see the template's masters, not a detached list of dropped rIds.
        deck = _make_deck("A", "B")
        masters = deck.slide_masters
        assert len(masters) == 1

        deck.apply_template(_as_stream(Presentation()))

        assert deck.slide_masters is masters
        assert len(masters) == 1
        assert masters[0].part.partname.startswith("/ppt/slideMasters/")
        assert len(masters[0].slide_layouts) == 11
        for slide in deck.slides:
            assert slide.slide_layout.slide_master == masters[0]

    def it_points_every_layout_id_at_a_layout_in_the_saved_package(self):
        import re

        deck = Presentation()
        deck.slides.add_slide(deck.slide_layouts[1])
        deck.apply_template(_as_stream(Presentation()))

        with zipfile.ZipFile(_as_stream(deck)) as z:
            names = z.namelist()
            masters = [n for n in names if re.fullmatch(r"ppt/slideMasters/slideMaster\d+\.xml", n)]
            assert len(masters) == 1
            master_xml = z.read(masters[0]).decode()
            rels_xml = z.read(
                masters[0].replace("slideMasters/", "slideMasters/_rels/") + ".rels"
            ).decode()
            presentation_rels = z.read("ppt/_rels/presentation.xml.rels").decode()

        targets = {}
        for relationship in re.findall(r"<Relationship [^>]*>", rels_xml):
            rId = re.search(r'Id="([^"]+)"', relationship).group(1)
            targets[rId] = re.search(r'Target="([^"]+)"', relationship).group(1)
        layout_rIds = re.findall(r'<p:sldLayoutId [^>]*r:id="(rId\d+)"', master_xml)
        assert len(layout_rIds) == 11
        assert len(set(layout_rIds)) == 11
        for rId in layout_rIds:
            assert "slideLayouts/slideLayout" in targets[rId], (rId, targets.get(rId))
        # -- exactly one theme reaches the package, through the slide master,
        # -- and the presentation's own theme relationship names that one --
        master_themes = [t for t in targets.values() if "theme/" in t]
        assert len(master_themes) == 1
        theme_name = master_themes[0].rsplit("/", 1)[1]
        assert 'Target="theme/%s"' % theme_name in presentation_rels
        assert [n for n in names if re.fullmatch(r"ppt/theme/theme\d+\.xml", n)] == [
            "ppt/theme/%s" % theme_name
        ]

    def it_reopens_with_iterable_layouts_and_accepts_a_new_slide(self):
        deck = Presentation()
        deck.slides.add_slide(deck.slide_layouts[1])
        deck.apply_template(_as_stream(Presentation()))

        reopened = _round_trip(deck)

        assert len(reopened.slide_masters) == 1
        assert len(reopened.slide_layouts) == 11
        for layout in reopened.slide_layouts:
            assert layout.part.partname.startswith("/ppt/slideLayouts/")
            assert layout.slide_master == reopened.slide_master
        assert reopened.slides[0].slide_layout.name == "Title and Content"
        slide = reopened.slides.add_slide(reopened.slide_layouts[0])
        assert slide.slide_layout.name == "Title Slide"
        again = _round_trip(reopened)
        assert len(again.slides) == 2

    def it_gives_the_new_masters_and_layouts_unique_ids(self):
        deck = _make_deck("A")
        deck.apply_template(_as_stream(Presentation()))

        ids = list(deck.part._element.xpath("p:sldMasterIdLst/p:sldMasterId/@id"))
        for master in deck.slide_masters:
            ids += list(master._element.xpath("p:sldLayoutIdLst/p:sldLayoutId/@id"))

        assert len(ids) == 12
        assert len(set(ids)) == len(ids)
        assert all(int(i) >= 2147483648 for i in ids)

    def it_copies_pictures_on_the_template_master_and_layouts(self):
        deck = Presentation()
        deck.slides.add_slide(deck.slide_layouts[1])

        deck.apply_template(_branded_template())

        assert _picture_blobs(deck.slide_master.shapes) == [_RED_PNG]
        assert _picture_blobs(deck.slide_layouts[1].shapes) == [_OTHER_PNG]

        reopened = _round_trip(deck)
        assert _picture_blobs(reopened.slide_master.shapes) == [_RED_PNG]
        assert _picture_blobs(reopened.slide_layouts[1].shapes) == [_OTHER_PNG]
        assert _picture_blobs(reopened.slides[0].slide_layout.shapes) == [_OTHER_PNG]
        with zipfile.ZipFile(_as_stream(deck)) as z:
            media = sorted(n for n in z.namelist() if n.startswith("ppt/media/"))
        assert len(media) == 2

    def it_can_be_applied_again(self):
        deck = _make_deck("A", "B")
        deck.apply_template(_as_stream(Presentation()))
        deck.apply_template(_branded_template())

        reopened = _round_trip(deck)

        assert len(reopened.slide_masters) == 1
        assert len(reopened.slide_layouts) == 11
        assert _picture_blobs(reopened.slide_master.shapes) == [_RED_PNG]
        assert _all_text(reopened) == ["A", "B"]

    def but_it_changes_nothing_when_the_template_has_no_layouts(self):
        deck = _make_deck("A")
        before = _as_stream(deck).getvalue()
        template = Presentation()
        master = template.slide_master
        for layout in list(master.slide_layouts):
            master.slide_layouts.remove(layout)
        assert len(template.slide_layouts) == 0

        with pytest.raises(ValueError, match="no slide layouts"):
            deck.apply_template(_as_stream(template))

        assert _as_stream(deck).getvalue() == before
        assert deck.slides[0].slide_layout.name == "Title Slide"

    def it_survives_save_open_save_unchanged(self):
        from .round_trip import assert_round_trip

        deck = _make_deck("A", "B")
        deck.apply_template(_branded_template())

        assert_round_trip(deck)
        # -- and with `prs.slides` touched after the reopen, which renames
        # -- slide parts into sequence --
        reopened = _round_trip(deck)
        assert len(reopened.slides) == 2
        assert_round_trip(reopened)
