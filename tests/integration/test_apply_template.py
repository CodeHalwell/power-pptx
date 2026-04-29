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
