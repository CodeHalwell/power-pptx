"""SOURCE_DATE_EPOCH pins every clock-derived timestamp in a saved package."""

from __future__ import annotations

import io
import time
import zipfile

import pytest

from power_pptx import Presentation
from power_pptx._reproducible import SOURCE_DATE_EPOCH, source_date_epoch, zip_date_time
from power_pptx.chart.data import CategoryChartData
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.util import Inches


def _build() -> bytes:
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    data = CategoryChartData()
    data.categories = ["North", "South"]
    data.add_series("Revenue", (1.0, 2.0))
    slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1), Inches(4), Inches(3), data
    )
    slide.shapes.add_text(Inches(1), Inches(5), Inches(4), Inches(1), text="Same input")
    stream = io.BytesIO()
    prs.save(stream)
    return stream.getvalue()


def _workbook_core(package: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(package)) as outer:
        name = next(n for n in outer.namelist() if n.endswith(".xlsx"))
        with zipfile.ZipFile(io.BytesIO(outer.read(name))) as inner:
            return inner.read("docProps/core.xml")


class DescribeSourceDateEpoch:
    def it_makes_repeated_builds_byte_identical(self, monkeypatch):
        monkeypatch.setenv(SOURCE_DATE_EPOCH, "1700000000")
        first = _build()
        time.sleep(1.1)  # cross a second boundary so unpinned zip times would differ

        assert _build() == first

    def it_pins_zip_member_times_and_embedded_workbook_dates(self, monkeypatch):
        monkeypatch.setenv(SOURCE_DATE_EPOCH, "1700000000")
        package = _build()

        with zipfile.ZipFile(io.BytesIO(package)) as z:
            assert {info.date_time for info in z.infolist()} == {(2023, 11, 14, 22, 13, 20)}
            assert all(info.compress_type == zipfile.ZIP_DEFLATED for info in z.infolist())
        core = _workbook_core(package)
        assert b"<dcterms:created" in core
        assert core.count(b"2023-11-14T22:13:20Z") == 2

    def it_leaves_unpinned_builds_on_the_clock(self, monkeypatch):
        monkeypatch.delenv(SOURCE_DATE_EPOCH, raising=False)

        assert source_date_epoch() is None
        assert zip_date_time() is None
        assert b"2023-11-14T22:13:20Z" not in _workbook_core(_build())

    def it_clamps_zip_times_to_1980(self, monkeypatch):
        monkeypatch.setenv(SOURCE_DATE_EPOCH, "0")

        assert zip_date_time() == (1980, 1, 1, 0, 0, 0)

    @pytest.mark.parametrize("value", ["soon", "-5", "1.5"])
    def it_rejects_invalid_values(self, monkeypatch, value):
        monkeypatch.setenv(SOURCE_DATE_EPOCH, value)

        with pytest.raises(ValueError, match=SOURCE_DATE_EPOCH):
            source_date_epoch()

    def it_pins_default_core_properties(self, monkeypatch):
        from power_pptx.parts.coreprops import CorePropertiesPart

        monkeypatch.setenv(SOURCE_DATE_EPOCH, "1700000000")
        core = CorePropertiesPart.default(None)  # type: ignore[arg-type]

        assert core.modified.isoformat() == "2023-11-14T22:13:20"


def _sectioned() -> tuple[bytes, list[str]]:
    """Build a deck with sections; return its bytes and the ids of its sections."""
    prs = Presentation()
    for _ in range(4):
        prs.slides.add_slide(prs.slide_layouts[6])
    # -- starting past the first slide also creates a "Default Section" before it --
    prs.sections.add("Body", start_slide_index=1)
    prs.sections.add("Appendix", start_slide_index=3)
    prs.sections.add("Appendix")
    stream = io.BytesIO()
    prs.save(stream)
    return stream.getvalue(), [section.id for section in prs.sections]


class DescribeSectionIds:
    """Section ids are GUIDs: random, except in a pinned build."""

    GUID = r"\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}"

    def it_makes_builds_of_a_deck_with_sections_byte_identical(self, monkeypatch):
        monkeypatch.setenv(SOURCE_DATE_EPOCH, "1700000000")

        first, first_ids = _sectioned()
        second, second_ids = _sectioned()

        assert first_ids == second_ids
        assert second == first

    def it_still_gives_every_section_its_own_well_formed_id(self, monkeypatch):
        import re

        monkeypatch.setenv(SOURCE_DATE_EPOCH, "1700000000")

        _, ids = _sectioned()

        # -- two of the four sections share a name --
        assert len(ids) == len(set(ids)) == 4
        assert all(re.fullmatch(self.GUID, section_id) for section_id in ids)

    def it_does_not_reuse_the_id_of_a_section_that_is_still_there(self, monkeypatch):
        monkeypatch.setenv(SOURCE_DATE_EPOCH, "1700000000")
        prs = Presentation()
        first = prs.sections.add("Same")
        second = prs.sections.add("Same")
        # -- the next section has the name and the position `second` was given --
        first.delete()

        third = prs.sections.add("Same")

        assert third.id != second.id

    def it_keeps_an_id_the_caller_supplies(self, monkeypatch):
        monkeypatch.setenv(SOURCE_DATE_EPOCH, "1700000000")
        supplied = "{11111111-2222-3333-4444-555555555555}"
        prs = Presentation()

        assert prs.sections.add("Mine", id=supplied).id == supplied

    def it_leaves_unpinned_ids_random(self, monkeypatch):
        import re

        monkeypatch.delenv(SOURCE_DATE_EPOCH, raising=False)

        _, first_ids = _sectioned()
        _, second_ids = _sectioned()

        assert not set(first_ids) & set(second_ids)
        assert all(re.fullmatch(self.GUID, section_id) for section_id in first_ids)


class DescribeNewUuid:
    def it_is_random_when_unpinned(self, monkeypatch):
        from power_pptx._reproducible import new_uuid

        monkeypatch.delenv(SOURCE_DATE_EPOCH, raising=False)

        assert new_uuid("section", 0, "Intro") != new_uuid("section", 0, "Intro")
        assert new_uuid("section", 0, "Intro").version == 4

    def it_depends_only_on_what_it_identifies_when_pinned(self, monkeypatch):
        from power_pptx._reproducible import new_uuid

        monkeypatch.setenv(SOURCE_DATE_EPOCH, "1700000000")
        intro = new_uuid("section", 0, "Intro")

        assert new_uuid("section", 0, "Intro") == intro
        assert new_uuid("section", 1, "Intro") != intro
        assert new_uuid("section", 0, "Outro") != intro
        # -- the parts are kept apart, not run together --
        assert new_uuid("section", 1, "0Intro") != new_uuid("section", 10, "Intro")
        monkeypatch.setenv(SOURCE_DATE_EPOCH, "1800000000")
        assert new_uuid("section", 0, "Intro") == intro
