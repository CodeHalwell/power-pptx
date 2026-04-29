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
