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

    def it_treats_full_bleed_only_slide_as_empty(self, prs):
        # A slide whose only shape is a slide-spanning background rect
        # should be reported as empty (it has no content).
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(0), Inches(0), prs.slide_width, prs.slide_height,
        )
        report = audit(prs)
        assert 0 in report.empty_slides


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
            issue["slide"] == 0 and issue["code"] == "OffSlide"
            for issue in d["lint_issues"]
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
