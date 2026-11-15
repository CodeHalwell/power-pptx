"""Installed validation checks actual packages without changing the source."""

import io
import warnings
from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree

from power_pptx import Presentation
from power_pptx.util import Inches
from power_pptx.validation import (
    presentation_bytes,
    roundtrip_changes,
    schema_validation_available,
    validate_presentation,
)

FIXTURE_DECKS = sorted(
    (Path(__file__).parents[1] / "features" / "steps" / "test_files").glob("*.pptx")
)


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


def _rewritten(blob, edit):
    """Return *blob* with each member passed through ``edit(name, data) -> data | None``."""
    output = io.BytesIO()
    with ZipFile(io.BytesIO(blob)) as original, ZipFile(output, "w") as changed:
        for name in original.namelist():
            data = edit(name, original.read(name))
            if data is not None:
                changed.writestr(name, data)
    return output.getvalue()


def _reversed_children(data):
    root = etree.fromstring(data)
    root[:] = reversed(root)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


class DescribeUntrustedInput:
    """A package that declares XML entities is reported, never expanded."""

    def it_reports_entity_references_instead_of_failing_on_them(self):
        def add_entity(name, data):
            if name == "ppt/slides/slide1.xml":
                declaration, root = data.split(b"?>", 1)
                assert b"Review me" in root
                return (
                    declaration
                    + b'?><!DOCTYPE sld [<!ENTITY more "AND MORE">]>'
                    + root.replace(b"Review me", b"Review me &more;")
                )
            return data

        report = validate_presentation(_rewritten(presentation_bytes(deck()), add_entity))

        assert report.has_errors
        assert any(
            part == "ppt/slides/slide1.xml" and "declares a DTD" in message
            for part, message in report.schema_violations
        )
        # -- the checks after the schema pass still ran: canonicalising a part
        # -- that holds an entity reference used to raise AttributeError --
        assert report.errors == []
        assert report.roundtrip_checked
        assert report.slide_count == 1
        assert report.audit


class DescribeRoundtripChanges:
    """The save/reopen check compares what a package means, not how it is spelled."""

    def it_ignores_the_order_of_relationships_and_content_types(self):
        ours = presentation_bytes(deck())

        def reorder(name, data):
            if name.endswith(".rels") or name == "[Content_Types].xml":
                return _reversed_children(data)
            return data

        foreign = _rewritten(ours, reorder)

        assert roundtrip_changes(foreign, ours) == []
        report = validate_presentation(foreign)
        assert report.roundtrip_checked
        assert report.roundtrip_changed_parts == []
        assert not report.has_errors

    def it_ignores_how_a_target_or_content_type_is_spelled(self):
        ours = presentation_bytes(deck())

        def respell(name, data):
            if name == "ppt/slides/_rels/slide1.xml.rels":
                assert b'Target="../slideLayouts/' in data
                return data.replace(b'Target="../slideLayouts/', b'Target="/ppt/slideLayouts/')
            if name == "[Content_Types].xml":
                # -- declare the `.rels` type per part instead of per extension --
                root = etree.fromstring(data)
                namespace = etree.QName(root).namespace
                (default,) = [e for e in root if e.get("Extension") == "rels"]
                root.remove(default)
                with ZipFile(io.BytesIO(ours)) as package:
                    for member in package.namelist():
                        if member.endswith(".rels"):
                            override = etree.SubElement(root, "{%s}Override" % namespace)
                            override.set("PartName", "/" + member)
                            override.set("ContentType", default.get("ContentType"))
                return etree.tostring(root)
            return data

        assert roundtrip_changes(_rewritten(ours, respell), ours) == []

    @pytest.mark.parametrize("path", FIXTURE_DECKS, ids=lambda path: path.name)
    def it_reports_no_change_for_a_deck_another_producer_wrote(self, path):
        data = path.read_bytes()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            resaved = presentation_bytes(Presentation(io.BytesIO(data)))

        assert roundtrip_changes(data, resaved) == []

    def it_measures_the_save_alone_not_what_reading_the_deck_does(self):
        # -- `Presentation.slides` adds an empty `p:sldIdLst` to a deck without one --
        path = Path(__file__).parent / "test_files" / "no-slides.pptx"

        report = validate_presentation(path, check_fonts=False)

        assert report.roundtrip_checked
        assert report.roundtrip_changed_parts == []
        assert report.errors == ["Presentation has no slides"]

    def but_it_reports_a_relationship_that_changed(self):
        ours = presentation_bytes(deck())
        rels = "ppt/slides/_rels/slide1.xml.rels"

        def retarget(name, data):
            if name == rels:
                assert b"slideLayout7.xml" in data
                return data.replace(b"slideLayout7.xml", b"slideLayout1.xml")
            return data

        def add_one(name, data):
            if name == rels:
                return data.replace(
                    b"</Relationships>",
                    b'<Relationship Id="rId99" Type="http://example.com/rel" '
                    b'Target="http://example.com/" TargetMode="External"/></Relationships>',
                )
            return data

        assert roundtrip_changes(_rewritten(ours, retarget), ours) == [rels]
        assert roundtrip_changes(_rewritten(ours, add_one), ours) == [rels]

    def and_it_reports_a_content_type_that_changed(self):
        ours = presentation_bytes(deck())

        def retype(name, data):
            if name == "[Content_Types].xml":
                assert b"presentationml.slide+xml" in data
                return data.replace(b"presentationml.slide+xml", b"presentationml.slideLayout+xml")
            return data

        assert roundtrip_changes(_rewritten(ours, retype), ours) == ["[Content_Types].xml"]

    def and_it_reports_parts_that_were_dropped_added_or_edited(self):
        ours = presentation_bytes(deck())

        def edit(name, data):
            if name == "docProps/core.xml":
                return None
            if name == "ppt/slides/slide1.xml":
                return data.replace(b"Review me", b"Review me again")
            return data

        changed = _rewritten(ours, edit)

        assert roundtrip_changes(ours, changed) == ["docProps/core.xml", "ppt/slides/slide1.xml"]
        assert roundtrip_changes(changed, ours) == ["docProps/core.xml", "ppt/slides/slide1.xml"]
