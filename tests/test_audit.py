"""Unit tests for :func:`power_pptx.audit.audit`."""

from __future__ import annotations

import pytest

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
        assert any(font == "Definitely-Not-A-Real-Font-Name"
                   for _, font in report.font_warnings)
