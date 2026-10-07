"""Unit tests for :func:`power_pptx.audit.audit`."""

from __future__ import annotations

import pytest
from lxml import etree

from power_pptx import BBox, Presentation, audit
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.util import Inches


@pytest.fixture
def prs():
    return Presentation()


class DescribeAudit:
    def it_returns_a_clean_report_for_empty_deck(self, prs):
        prs.slides.add_slide(prs.slide_layouts[6])
        report = audit(prs)
        assert report.total_slides == 1
        assert not report.has_errors
        assert report.empty_slides == [0]

    def it_flags_offslide_via_lint(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(15), Inches(10), Inches(2), Inches(1))
        report = audit(prs)
        assert report.has_errors
        codes = {issue.code for _idx, issue in report.lint_issues}
        assert "OffSlide" in codes

    def it_aggregates_across_slides(self, prs):
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.slides.add_slide(prs.slide_layouts[6])
        report = audit(prs)
        assert report.total_slides == 2

    def it_renders_to_markdown(self, prs):
        prs.slides.add_slide(prs.slide_layouts[6])
        report = audit(prs)
        md = report.markdown()
        assert "Audit report" in md
        assert "1 slide" in md

    def it_flags_uncommon_fonts(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.shapes.add_text(
            BBox.from_inches(1, 1, 4, 1),
            text="Hi",
            font="Definitely-Not-A-Real-Font-Name",
        )
        report = audit(prs)
        assert any(font == "Definitely-Not-A-Real-Font-Name" for _, font in report.font_warnings)

    def it_treats_full_bleed_only_slide_as_empty(self, prs):
        # A slide whose only shape is a slide-spanning background rect
        # should be reported as empty (it has no content).
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(0),
            Inches(0),
            prs.slide_width,
            prs.slide_height,
        )
        report = audit(prs)
        assert 0 in report.empty_slides


class DescribeAuditIsReadOnly:
    """``audit()`` documents itself as read-only; its own loops must keep that promise.

    ``shape.text_frame`` adds a ``<p:txBody>`` to a shape that has none and ``run.font`` adds an
    ``<a:rPr/>`` to a run that has none, so the checks that merely *look* at text (placeholder
    skipping, the full-bleed test, the font sweep) have to go around them.
    """

    def it_adds_no_run_properties_while_sweeping_fonts(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
        box.text_frame.text = "bare runs\nin two paragraphs"
        before = etree.tostring(slide._element)

        audit(prs, check_fonts=True)

        assert etree.tostring(slide._element) == before

    def it_adds_no_text_body_to_a_picture_placeholder(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[8])  # Picture with Caption
        before = etree.tostring(slide._element)

        audit(prs)

        assert etree.tostring(slide._element) == before

    def it_adds_no_text_body_while_testing_for_a_full_bleed_background(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        backdrop = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), prs.slide_width, prs.slide_height
        )
        backdrop._element.remove(backdrop._element.txBody)
        before = etree.tostring(slide._element)

        report = audit(prs)

        assert etree.tostring(slide._element) == before
        assert report.empty_slides == [0]

    def it_still_reports_a_slide_of_untouched_placeholders_as_empty(self, prs):
        prs.slides.add_slide(prs.slide_layouts[8])  # Picture with Caption
        assert audit(prs).empty_slides == [0]

    def it_still_counts_a_full_bleed_shape_that_carries_text_as_content(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        banner = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), prs.slide_width, prs.slide_height
        )
        banner.text_frame.text = "Full-bleed title card"
        assert audit(prs).empty_slides == []

    def it_still_reads_a_font_name_from_explicit_run_properties(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
        box.text_frame.text = "one run with a face, one bare run\vbare"
        box.text_frame.paragraphs[0].runs[0].font.name = "Definitely-Not-A-Real-Font-Name"

        report = audit(prs)

        assert report.font_warnings == [(0, "Definitely-Not-A-Real-Font-Name")]


class DescribeAuditMachineReadable:
    """``AuditReport.to_dict`` / ``to_json``."""

    def it_serializes_a_clean_deck(self, prs):
        import json

        prs.slides.add_slide(prs.slide_layouts[6])
        payload = json.loads(audit(prs).to_json())

        assert payload["total_slides"] == 1
        assert payload["has_errors"] is False
        assert payload["lint_issues"] == []
        assert payload["empty_slides"] == [0]

    def it_expands_lint_issues_with_slide_index(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(15), Inches(10), Inches(2), Inches(1))

        d = audit(prs).to_dict()

        assert d["has_errors"] is True
        assert any(
            issue["slide"] == 0 and issue["code"] == "OffSlide" for issue in d["lint_issues"]
        )

    def it_is_json_serializable_for_a_rich_deck(self, prs):
        import json

        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.shapes.add_text(
            BBox.from_inches(1, 1, 4, 1),
            text="Hi",
            font="Definitely-Not-A-Real-Font-Name",
        )
        # must not raise and must round-trip through json
        assert json.loads(audit(prs).to_json()) == audit(prs).to_dict()
