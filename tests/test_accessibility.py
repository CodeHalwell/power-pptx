"""Unit tests for shape alt text and :func:`power_pptx.accessibility`."""

from __future__ import annotations

import json
import os

import pytest

from power_pptx import Presentation
from power_pptx.accessibility import (
    AccessibilityReport,
    AccessibilitySeverity,
    audit_accessibility,
)
from power_pptx.dml.color import RGBColor
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.util import Inches

_HERE = os.path.dirname(__file__)
_IMAGE = os.path.join(_HERE, "test_files", "python-powered.png")


@pytest.fixture
def prs():
    return Presentation()


# ---------------------------------------------------------------------------
# shape.alt_text / shape.title_text
# ---------------------------------------------------------------------------


class DescribeAltText:
    def it_defaults_to_empty_string(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1)
        )
        assert shape.alt_text == ""
        assert shape.title_text == ""

    def it_round_trips_through_the_setter(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1)
        )
        shape.alt_text = "A blue rectangle."
        assert shape.alt_text == "A blue rectangle."

    def it_writes_the_descr_attribute_on_cNvPr(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1)
        )
        shape.alt_text = "Described."
        cNvPr = shape._element._nvXxPr.cNvPr
        assert cNvPr.get("descr") == "Described."

    def it_writes_the_title_attribute_on_cNvPr(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1)
        )
        shape.title_text = "Rect"
        cNvPr = shape._element._nvXxPr.cNvPr
        assert cNvPr.get("title") == "Rect"

    def it_clears_the_attribute_when_set_empty(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1)
        )
        shape.alt_text = "x"
        shape.alt_text = ""
        assert shape.alt_text == ""
        assert "descr" not in shape._element._nvXxPr.cNvPr.attrib

    def it_clears_the_attribute_when_set_none(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1)
        )
        shape.alt_text = "x"
        shape.alt_text = None
        assert shape.alt_text == ""

    def it_rejects_non_string(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1)
        )
        with pytest.raises(TypeError):
            shape.alt_text = 123


# ---------------------------------------------------------------------------
# audit_accessibility
# ---------------------------------------------------------------------------


class DescribeAuditAccessibility:
    def it_flags_a_picture_missing_alt_text_as_error(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        pic = slide.shapes.add_picture(
            _IMAGE, Inches(1), Inches(1), Inches(2), Inches(2)
        )
        pic.alt_text = ""  # clear the filename auto-fill
        report = audit_accessibility(prs)
        alt_issues = [i for i in report.issues if i.code == "MissingAltText"]
        assert alt_issues
        assert alt_issues[0].severity == AccessibilitySeverity.ERROR
        assert report.has_errors

    def it_does_not_flag_a_picture_with_alt_text(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        pic = slide.shapes.add_picture(
            _IMAGE, Inches(1), Inches(1), Inches(2), Inches(2)
        )
        pic.alt_text = "The Python Powered logo."
        report = audit_accessibility(prs)
        assert not any(i.code == "MissingAltText" for i in report.issues)

    def it_flags_a_slide_with_no_title(self, prs):
        prs.slides.add_slide(prs.slide_layouts[6])  # blank layout, no title
        report = audit_accessibility(prs)
        assert any(i.code == "NoSlideTitle" and i.slide == 0 for i in report.issues)

    def it_does_not_flag_a_slide_with_a_title(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[0])  # title layout
        if slide.shapes.title is not None:
            slide.shapes.title.text = "Welcome"
        report = audit_accessibility(prs)
        assert not any(i.code == "NoSlideTitle" for i in report.issues)

    def it_flags_low_contrast_text(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(4), Inches(2)
        )
        shape.fill_hex("#FFFFFF")
        shape.text_frame.text = "barely visible"
        run = shape.text_frame.paragraphs[0].runs[0]
        run.font.color.rgb = RGBColor(0xEE, 0xEE, 0xEE)
        report = audit_accessibility(prs)
        assert any(i.code == "LowContrast" for i in report.issues)

    def it_returns_clean_for_a_well_formed_deck(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        if slide.shapes.title is not None:
            slide.shapes.title.text = "All good"
        pic = slide.shapes.add_picture(
            _IMAGE, Inches(1), Inches(3), Inches(2), Inches(2)
        )
        pic.alt_text = "Logo."
        report = audit_accessibility(prs)
        assert report.issues == []
        assert not report.has_errors

    def it_counts_total_slides(self, prs):
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.slides.add_slide(prs.slide_layouts[6])
        report = audit_accessibility(prs)
        assert report.total_slides == 2

    def it_renders_markdown(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        pic = slide.shapes.add_picture(
            _IMAGE, Inches(1), Inches(1), Inches(2), Inches(2)
        )
        pic.alt_text = ""
        md = audit_accessibility(prs).markdown()
        assert "Accessibility report" in md
        assert "MissingAltText" in md

    def it_renders_clean_markdown(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        if slide.shapes.title is not None:
            slide.shapes.title.text = "Title"
        md = audit_accessibility(prs).markdown()
        assert "No accessibility issues found." in md

    def it_to_dict_is_json_serializable(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        pic = slide.shapes.add_picture(
            _IMAGE, Inches(1), Inches(1), Inches(2), Inches(2)
        )
        pic.alt_text = ""
        report = audit_accessibility(prs)
        d = report.to_dict()
        # Must round-trip through json without error.
        text = json.dumps(d)
        again = json.loads(text)
        assert again["total_slides"] == 1
        assert again["has_errors"] is True
        assert isinstance(again["issues"], list)

    def it_to_json_round_trips(self, prs):
        prs.slides.add_slide(prs.slide_layouts[6])
        report = audit_accessibility(prs)
        parsed = json.loads(report.to_json())
        assert "issues" in parsed


# ---------------------------------------------------------------------------
# Round-trip safety + schema validity
# ---------------------------------------------------------------------------


def _deck_with_alt_text() -> Presentation:
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    if slide.shapes.title is not None:
        slide.shapes.title.text = "Accessible deck"
    pic = slide.shapes.add_picture(_IMAGE, Inches(1), Inches(3), Inches(2), Inches(2))
    pic.alt_text = "The Python Powered logo."
    pic.title_text = "Logo"
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(4), Inches(3), Inches(2), Inches(1)
    )
    shape.alt_text = "A decorative rectangle."
    return prs


def test_alt_text_round_trips():
    from tests.integration.round_trip import assert_round_trip

    assert_round_trip(_deck_with_alt_text)


def test_alt_text_is_schema_valid():
    import io

    from tests.schema.oxml_schema_validator import (
        iter_schema_violations,
        schema_validation_available,
    )

    if not schema_validation_available():
        pytest.skip("schema validation unavailable (lxml or XSDs missing)")

    prs = _deck_with_alt_text()
    buf = io.BytesIO()
    prs.save(buf)
    violations = list(iter_schema_violations(buf.getvalue()))
    assert not violations, violations


def test_alt_text_survives_save_load_read():
    """The descr/title attrs are readable after a save→load cycle."""
    import io

    prs = _deck_with_alt_text()
    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    reopened = Presentation(buf)
    slide = reopened.slides[0]
    descrs = {s.alt_text for s in slide.shapes if s.alt_text}
    assert "The Python Powered logo." in descrs


def test_report_dataclass_default_factory():
    # Smoke: a default-constructed report is empty and clean.
    report = AccessibilityReport()
    assert report.issues == []
    assert report.total_slides == 0
    assert not report.has_errors
