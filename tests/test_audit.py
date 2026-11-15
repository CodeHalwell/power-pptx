"""Unit tests for :func:`power_pptx.audit.audit`."""

from __future__ import annotations

import io

import pytest

from power_pptx import BBox, Presentation, audit
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.oxml.ns import qn
from power_pptx.util import Emu, Inches


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

    def it_resolves_a_theme_font_reference_instead_of_flagging_it(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        box.text_frame.text = "Theme body font"
        # How PowerPoint writes "use the theme's body font".
        box.text_frame.paragraphs[0].runs[0].font.name = "+mn-lt"

        report = audit(prs)

        # The default theme's minor font is Calibri, which is common.
        assert report.font_warnings == []

    def it_reports_the_theme_font_a_reference_stands_for(self, prs):
        prs.theme.fonts.minor = "Instrument Serif"
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        box.text_frame.text = "Theme body font"
        box.text_frame.paragraphs[0].runs[0].font.name = "+mn-lt"

        assert audit(prs).font_warnings == [(0, "Instrument Serif")]

    def it_checks_fonts_set_on_a_paragraph_and_in_table_cells(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        box.text_frame.text = "Brand font set on the paragraph"
        box.text_frame.paragraphs[0].font.name = "Instrument Serif"
        table = slide.shapes.add_table(1, 1, Inches(6), Inches(1), Inches(2), Inches(1)).table
        table.cell(0, 0).text = "cell"
        table.cell(0, 0).text_frame.paragraphs[0].runs[0].font.name = "Papyrus"

        report = audit(prs)

        assert report.font_warnings == [(0, "Instrument Serif"), (0, "Papyrus")]

    def it_does_not_change_the_deck(self):
        from tests.test_accessibility import foreign_deck, slide_snapshot

        prs, before = foreign_deck()

        audit(prs)

        assert slide_snapshot(prs) == before

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


def _image(fmt, size=(8, 8)):
    from PIL import Image

    data = io.BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(data, format=fmt)
    data.seek(0)
    return data


def _image_part(picture):
    return picture.part.related_part(picture._pic.blip_rId)


class DescribeAuditPictures:
    def it_accepts_a_sound_picture(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.shapes.add_picture(_image("PNG"), Inches(1), Inches(1), Inches(1), Inches(1))

        report = audit(prs)

        assert report.broken_pictures == []
        assert report.size_warnings == []
        assert report.empty_slides == []

    def it_flags_a_zero_sized_picture(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        picture = slide.shapes.add_picture(_image("PNG"), Inches(1), Inches(1), Inches(1))
        picture.height = Emu(0)

        assert audit(prs).broken_pictures == [(0, picture)]

    def it_flags_a_picture_with_no_embedded_image(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        picture = slide.shapes.add_picture(_image("PNG"), Inches(1), Inches(1), Inches(1))
        blip = picture._element.find(".//" + qn("a:blip"))
        del blip.attrib[qn("r:embed")]

        report = audit(prs)

        assert report.broken_pictures == [(0, picture)]
        assert report.has_errors

    @pytest.mark.parametrize("blob", [b"", b"\x89PNG\r\n\x1a\n but no image data"])
    def it_flags_a_picture_whose_image_data_is_empty_or_corrupt(self, prs, blob):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        picture = slide.shapes.add_picture(_image("PNG"), Inches(1), Inches(1), Inches(1))
        _image_part(picture)._blob = blob

        assert audit(prs).broken_pictures == [(0, picture)]

    def but_it_does_not_decode_an_image_type_it_cannot_check(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        picture = slide.shapes.add_picture(_image("PNG"), Inches(1), Inches(1), Inches(1))
        part = _image_part(picture)
        part._blob = b"not checked"
        part._content_type = "image/x-wmf"

        assert audit(prs).broken_pictures == []

    def it_warns_about_a_large_picture(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        picture = slide.shapes.add_picture(_image("BMP", (100, 100)), Inches(1), Inches(1))
        size = len(_image_part(picture).blob)

        report = audit(prs, size_warn_bytes=size - 1)

        assert report.size_warnings == [(0, picture.name, size)]
        assert audit(prs, size_warn_bytes=size).size_warnings == []


class DescribeAuditContent:
    def it_counts_a_shape_without_a_stored_size_as_content(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
        shape._element.spPr.remove(shape._element.spPr.xfrm)

        assert audit(prs).empty_slides == []

    def it_counts_a_full_bleed_rectangle_with_text_as_content(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
        shape.text_frame.text = "Agenda"

        assert audit(prs).empty_slides == []

    def it_does_not_count_empty_placeholders_as_content(self, prs):
        prs.slides.add_slide(prs.slide_layouts[1])
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = "Title"

        assert audit(prs).empty_slides == [0]

    def it_checks_fonts_only_when_asked(self, prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.shapes.add_text(BBox.from_inches(1, 1, 4, 1), text="Hi", font="Papyrus")

        assert audit(prs, check_fonts=False).font_warnings == []


class DescribeAuditMarkdown:
    def it_lists_every_kind_of_finding(self):
        from power_pptx.audit import AuditReport
        from power_pptx.lint import OffSlide

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(-1), 0, Inches(1), Inches(1))
        picture = slide.shapes.add_picture(_image("PNG"), Inches(1), Inches(1), Inches(1))
        report = AuditReport(
            lint_issues=[(0, OffSlide(shape, "left"))],
            broken_pictures=[(0, picture)],
            empty_slides=[1, 2],
            font_warnings=[(0, "Papyrus"), (0, "Papyrus"), (2, "Papyrus")],
            size_warnings=[(0, "Picture 2", 2_500_000)],
            total_slides=3,
        )

        assert report.markdown() == "\n".join(
            [
                "# Audit report — 3 slide(s)",
                "",
                "## Lint (1)",
                f"- slide 0: [ERROR] OffSlide: Shape '{shape.name}' extends beyond the left "
                "edge of the slide.",
                "",
                "## Broken pictures (1)",
                f"- slide 0: `{picture.name}` is zero-sized or has missing/corrupt image data",
                "",
                "## Empty slides",
                "- slide 1: no content-bearing shapes",
                "- slide 2: no content-bearing shapes",
                "",
                "## Font warnings (3)",
                "- slide 0: uses `Papyrus` (not in the common safe-list)",
                "- slide 2: uses `Papyrus` (not in the common safe-list)",
                "",
                "## Large pictures (1)",
                "- slide 0: `Picture 2` is 2.5 MB",
            ]
        )
        assert str(report) == report.markdown()

    def it_leaves_out_the_sections_that_are_empty(self):
        from power_pptx.audit import AuditReport

        report = AuditReport(empty_slides=[0], total_slides=1)

        assert report.markdown() == (
            "# Audit report — 1 slide(s)\n\n## Empty slides\n- slide 0: no content-bearing shapes"
        )

    def it_says_so_when_there_is_nothing_to_report(self):
        from power_pptx.audit import AuditReport

        assert AuditReport(total_slides=2).markdown() == (
            "# Audit report — 2 slide(s)\n\n**No issues found.**"
        )
