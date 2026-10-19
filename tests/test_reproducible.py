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
