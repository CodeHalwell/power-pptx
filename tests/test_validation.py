"""Installed validation checks actual packages without changing the source."""

import io
from zipfile import ZipFile

from power_pptx import Presentation
from power_pptx.util import Inches
from power_pptx.validation import schema_validation_available, validate_presentation


def deck():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1)).text = "Review me"
    return prs


def test_packaged_validation_is_read_only_and_roundtrips(tmp_path):
    prs = deck()
    before = prs.slides[0].element.xml
    path = tmp_path / "source.pptx"
    prs.save(path)
    original = path.read_bytes()
    assert schema_validation_available()
    report = validate_presentation(path)
    assert report.slide_count == 1
    assert report.schema_checked
    assert report.roundtrip_checked
    assert not report.has_errors
    assert path.read_bytes() == original
    assert prs.slides[0].element.xml == before
    assert not validate_presentation(prs).has_errors
    from power_pptx import audit

    audit(prs)
    assert prs.slides[0].element.xml == before


def test_invalid_packages_and_empty_decks_have_actionable_reports():
    invalid = validate_presentation(b"broken zip")
    assert invalid.has_errors
    assert "BadZipFile" in invalid.errors[0]
    assert validate_presentation(Presentation()).has_errors


def test_schema_detects_real_duplicate_shape_ids():
    source = io.BytesIO()
    deck().save(source)
    output = io.BytesIO()
    with ZipFile(source) as original, ZipFile(output, "w") as changed:
        for name in original.namelist():
            data = original.read(name)
            if name == "ppt/slides/slide1.xml":
                data = data.replace(b'id="2"', b'id="1"')
            changed.writestr(name, data)
    report = validate_presentation(output.getvalue())
    assert report.has_errors
    assert any("duplicate" in message.lower() for _, message in report.schema_violations)


def test_missing_explicit_font_is_reported_without_failing_structural_checks():
    prs = deck()
    prs.slides[0].shapes[0].text_frame.paragraphs[0].runs[0].font.name = "AbsentReviewFont"
    report = validate_presentation(prs)
    assert report.missing_fonts == ["AbsentReviewFont"]
    assert not report.has_errors
    assert validate_presentation(prs, check_fonts=False).missing_fonts == []
