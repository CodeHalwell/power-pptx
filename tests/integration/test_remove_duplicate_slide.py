"""Package-level tests for `Slides.remove()` and `Slides.duplicate()`.

Each deck is saved, reopened and saved again: what was removed must be gone
from the package, nothing may be left dangling, and the result must survive a
round trip unchanged.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from power_pptx import Presentation
from power_pptx.chart.data import CategoryChartData
from power_pptx.validation import iter_schema_violations

from ..unitutil.slide_links import (
    OTHER_PNG,
    PNG,
    add_chart,
    custom_show_slides,
    linked_deck,
    titled_deck,
)
from .round_trip import assert_round_trip


@pytest.fixture(autouse=True)
def _pinned_zip_timestamps(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")


def _saved(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _members(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {name: z.read(name) for name in z.namelist()}


def _names(data: bytes, prefix: str) -> list[str]:
    return sorted(n for n in _members(data) if n.startswith(prefix) and not n.endswith(".rels"))


def _titles(prs) -> list[str]:
    return [slide.shapes[0].text_frame.text for slide in prs.slides]


class DescribeRemovedSlidePackage:
    def it_leaves_nothing_of_the_slide_in_the_saved_package(self):
        prs = linked_deck()

        prs.slides.remove(prs.slides[1])
        data = _saved(prs)

        assert _names(data, "ppt/slides/") == [
            "ppt/slides/slide1.xml",
            "ppt/slides/slide2.xml",
            "ppt/slides/slide3.xml",
        ]
        # -- slide "a" keeps the notes slide it has; "b"'s goes --
        assert len(_names(data, "ppt/notesSlides/")) == 1
        assert _names(data, "ppt/charts/") == []
        assert _names(data, "ppt/embeddings/") == []
        assert not any(b"notes of b" in blob for blob in _members(data).values())

    def it_keeps_a_picture_another_slide_also_shows(self):
        prs = linked_deck()

        prs.slides.remove(prs.slides[1])
        data = _saved(prs)

        media = [_members(data)[name] for name in _names(data, "ppt/media/")]
        assert media == [PNG]
        reopened = Presentation(io.BytesIO(data))
        assert reopened.slides[0].shapes[1].image.blob == PNG
        assert OTHER_PNG not in media

    def it_saves_a_package_with_no_schema_violations_or_orphans(self):
        prs = linked_deck()

        prs.slides.remove(prs.slides[1])

        assert list(iter_schema_violations(_saved(prs))) == []

    def it_round_trips(self):
        def factory():
            prs = linked_deck()
            prs.slides.remove(prs.slides[1])
            return prs

        assert_round_trip(factory)

    def it_keeps_the_rest_of_the_deck_as_it_was_after_reopening(self):
        prs = linked_deck()

        prs.slides.remove(prs.slides[1])
        reopened = Presentation(io.BytesIO(_saved(prs)))

        a, c, d = reopened.slides
        assert _titles(reopened) == ["a", "c", "d"]
        assert a.shapes[0].click_action.target_slide is None
        assert c.shapes[0].text_frame.paragraphs[0].runs[0].hyperlink.target_slide is None
        assert a.notes == "see b"
        assert [s.slide_ids for s in reopened.sections] == [[a.slide_id], [c.slide_id, d.slide_id]]
        assert custom_show_slides(reopened) == [[c]]

    def it_lets_a_slide_be_added_after_a_removal(self):
        prs = titled_deck("a", "b", "c")
        prs.slides.remove(prs.slides[0])

        prs.slides.add_slide(prs.slide_layouts[6])
        data = _saved(prs)

        assert len(Presentation(io.BytesIO(data)).slides) == 3
        assert list(iter_schema_violations(data)) == []


class DescribeDuplicatedSlidePackage:
    @staticmethod
    def _deck():
        prs = titled_deck("a", "b")
        a, b = prs.slides
        a.notes = "notes of a"
        add_chart(a)
        a.shapes.add_picture(io.BytesIO(PNG), 0, 0)
        a.shapes[0].click_action.target_slide = b
        prs.sections.add("Only", start_slide_index=0)
        return prs

    def it_saves_a_package_with_no_schema_violations(self):
        prs = self._deck()

        prs.slides.duplicate(prs.slides[0])

        assert list(iter_schema_violations(_saved(prs))) == []

    def it_round_trips(self):
        def factory():
            prs = self._deck()
            prs.slides.duplicate(prs.slides[0])
            return prs

        assert_round_trip(factory)

    def it_stores_the_chart_and_notes_twice_and_the_picture_once(self):
        prs = self._deck()

        prs.slides.duplicate(prs.slides[0])
        data = _saved(prs)

        assert len(_names(data, "ppt/charts/")) == 2
        assert len(_names(data, "ppt/embeddings/")) == 2
        assert len(_names(data, "ppt/notesSlides/")) == 2
        assert len(_names(data, "ppt/media/")) == 1

    def it_keeps_the_copy_independent_after_reopening(self):
        prs = self._deck()
        copy = prs.slides.duplicate(prs.slides[0])
        chart_data = CategoryChartData()
        chart_data.categories = ["a", "b"]
        chart_data.add_series("s", (7, 9))
        copy.shapes[1].chart.replace_data(chart_data)
        copy.notes = "notes of the copy"

        reopened = Presentation(io.BytesIO(_saved(prs)))

        original, copy, b = reopened.slides
        assert list(original.shapes[1].chart.plots[0].series[0].values) == [1.0, 2.0]
        assert list(copy.shapes[1].chart.plots[0].series[0].values) == [7.0, 9.0]
        assert (original.notes, copy.notes) == ("notes of a", "notes of the copy")
        assert copy.shapes[0].click_action.target_slide == b

    def it_keeps_the_copy_whole_when_the_original_is_removed(self):
        prs = self._deck()
        prs.slides.duplicate(prs.slides[0])

        prs.slides.remove(prs.slides[0])
        data = _saved(prs)

        assert list(iter_schema_violations(data)) == []
        reopened = Presentation(io.BytesIO(data))
        copy = reopened.slides[0]
        assert copy.shapes[2].image.blob == PNG
        assert list(copy.shapes[1].chart.plots[0].series[0].values) == [1.0, 2.0]
        assert copy.notes == "notes of a"
