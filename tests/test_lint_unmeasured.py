"""Per-axis text overflow figures and the `TextUnmeasured` issue (issue #58)."""

from __future__ import annotations

import json

import pytest

from power_pptx import Presentation
from power_pptx.lint import LintSeverity, TextOverflow, TextUnmeasured
from power_pptx.lint_cli import EXIT_CLEAN, EXIT_ISSUES, EXIT_USAGE, main
from power_pptx.util import Inches, Pt


@pytest.fixture
def slide():
    prs = Presentation()
    return prs.slides.add_slide(prs.slide_layouts[6])


def _textbox(slide, name, text, *, width=2.0, height=0.5, wrap=True, size=18):
    shape = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(width), Inches(height))
    shape.name = name
    frame = shape.text_frame
    frame.word_wrap = wrap
    frame.text = text
    for paragraph in frame.paragraphs:
        for run in paragraph.runs:
            run.font.size = Pt(size)
    return shape


def _only(report, cls):
    found = [issue for issue in report.issues if isinstance(issue, cls)]
    assert len(found) == 1, report.summary()
    return found[0]


class DescribeTextOverflowAxes:
    def it_reports_both_axes_when_both_overflow(self, slide):
        _textbox(
            slide,
            "Both",
            "A line that is far wider than the box that holds it\ntwo\nthree\nfour\nfive",
            width=1.0,
            height=0.3,
            wrap=False,
        )

        issue = _only(slide.lint(), TextOverflow)

        assert issue.width_ratio is not None
        assert issue.width_ratio > 1
        assert issue.height_ratio is not None
        assert issue.height_ratio > 1
        assert issue.width_overflow_pt > 0
        assert issue.height_overflow_pt > 0
        # -- the legacy fields go on describing whichever axis is further out --
        assert issue.ratio == max(issue.width_ratio, issue.height_ratio)
        worse = "width" if issue.width_ratio >= issue.height_ratio else "height"
        assert issue.dimension == worse
        assert issue.overflow_pt == getattr(issue, worse + "_overflow_pt")
        assert "too wide" in issue.message
        assert "too tall" in issue.message

    def it_leaves_the_axis_that_fits_empty(self, slide):
        _textbox(slide, "Tall", "word " * 80, width=2.0, height=0.4)

        issue = _only(slide.lint(), TextOverflow)

        assert issue.dimension == "height"
        assert issue.height_ratio == issue.ratio
        assert issue.height_overflow_pt == issue.overflow_pt
        assert issue.width_ratio is None
        assert issue.width_overflow_pt == 0.0

    def it_puts_the_axes_in_the_json_payload_beside_the_legacy_fields(self, slide):
        _textbox(slide, "Tall", "word " * 80, width=2.0, height=0.4)

        payload = _only(slide.lint(), TextOverflow).to_dict()

        assert {"ratio", "dimension", "overflow_pt"} <= set(payload)
        assert payload["height_ratio"] == payload["ratio"]
        assert payload["width_ratio"] is None
        json.dumps(payload)

    def it_reports_a_table_row_as_a_height_overflow(self, slide):
        frame = slide.shapes.add_table(1, 1, Inches(1), Inches(1), Inches(1), Inches(0.3))
        frame.table.cell(0, 0).text = "word " * 60

        issue = _only(slide.lint(), TextOverflow)

        assert issue.row == 0
        assert issue.height_ratio == issue.ratio
        assert issue.width_ratio is None


class DescribeTextUnmeasured:
    def it_reports_a_frame_with_text_and_no_size(self, slide):
        shape = slide.shapes.add_textbox(Inches(1), Inches(1), 0, 0)
        shape.name = "Zero"
        shape.text_frame.text = "hello"

        issue = _only(slide.lint(), TextUnmeasured)

        assert issue.code == "TextUnmeasured"
        assert issue.severity is LintSeverity.INFO
        assert issue.reason == "no-size"
        assert issue.shape_id == shape.shape_id
        assert issue.shapes == (shape,)
        assert "Zero" in issue.message
        assert "not checked for overflow" in issue.message

    def it_reports_stacked_text(self, slide):
        shape = _textbox(slide, "Stacked", "hello", height=2.0)
        shape._element.txBody.bodyPr.set("vert", "wordArtVert")

        assert _only(slide.lint(), TextUnmeasured).reason == "stacked-text"

    def it_reports_a_frame_whose_insets_leave_no_room(self, slide):
        shape = _textbox(slide, "Squeezed", "hello", width=0.5, height=1.0)
        shape.text_frame.margin_left = shape.text_frame.margin_right = Inches(0.3)

        assert _only(slide.lint(), TextUnmeasured).reason == "no-room"

    def it_reports_the_table_cells_it_does_not_measure(self, slide):
        frame = slide.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(4), Inches(1))
        table = frame.table
        rotated = table.cell(0, 0)
        rotated.text = "rotated"
        rotated._tc.get_or_add_tcPr().set("vert", "vert270")
        table.cell(0, 1).merge(table.cell(1, 1))
        table.cell(0, 1).text = "spans two rows"

        issues = [i for i in slide.lint().issues if isinstance(i, TextUnmeasured)]

        assert sorted((i.row, i.col, i.reason) for i in issues) == [
            (0, 0, "rotated-cell-text"),
            (0, 1, "row-span"),
        ]
        assert all("cell (0, " in i.message for i in issues)

    def it_says_nothing_about_frames_it_measured_or_that_hold_no_text(self, slide):
        _textbox(slide, "Fits", "ok", width=4.0, height=1.0)
        slide.shapes.add_textbox(Inches(5), Inches(5), 0, 0).name = "Empty"

        report = slide.lint()

        assert report.unmeasured == []
        assert not any(isinstance(i, (TextOverflow, TextUnmeasured)) for i in report.issues)

    def it_is_not_an_error_but_is_easy_to_find(self, slide):
        slide.shapes.add_textbox(Inches(1), Inches(1), 0, 0).text_frame.text = "hello"

        report = slide.lint()

        assert not report.has_errors
        assert [issue.reason for issue in report.unmeasured] == ["no-size"]
        assert report.to_dict()["issues"][0]["reason"] == "no-size"

    def it_can_be_disabled_or_filtered_out_like_any_other_issue(self, slide):
        slide.shapes.add_textbox(Inches(1), Inches(1), 0, 0).text_frame.text = "hello"

        assert slide.lint(disable=["TextUnmeasured"]).unmeasured == []
        assert slide.lint(min_severity="warning").unmeasured == []

    def it_is_kept_apart_from_an_estimated_measurement(self, slide):
        shape = _textbox(slide, "Estimated", "word " * 80, width=2.0, height=0.4)
        shape.text_frame.paragraphs[0].runs[0].font.name = "No Such Typeface 123"

        report = slide.lint()

        assert _only(report, TextOverflow).estimated is True
        assert report.unmeasured == []


class DescribeFailOnUnmeasured:
    @pytest.fixture
    def deck(self, tmp_path):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shape = slide.shapes.add_textbox(Inches(1), Inches(1), 0, 0)
        shape.name = "Zero"
        shape.text_frame.text = "hello"
        path = tmp_path / "deck.pptx"
        prs.save(str(path))
        return path

    def it_passes_a_deck_with_unmeasured_text_unless_asked(self, deck, capsys):
        assert main([str(deck)]) == EXIT_CLEAN
        assert "TextUnmeasured" in capsys.readouterr().out

    def it_fails_it_when_asked(self, deck, capsys):
        assert main([str(deck), "--fail-on-unmeasured"]) == EXIT_ISSUES
        assert main([str(deck), "--fail-on", "never", "--fail-on-unmeasured"]) == EXIT_ISSUES
        capsys.readouterr()

    def it_passes_a_fully_measured_deck_when_asked(self, tmp_path, capsys):
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        path = tmp_path / "clean.pptx"
        prs.save(str(path))

        assert main([str(path), "--fail-on-unmeasured"]) == EXIT_CLEAN
        capsys.readouterr()

    def it_counts_them_in_the_json_report(self, deck, capsys):
        status = main([str(deck), "--format", "json", "--fail-on-unmeasured"])
        document = json.loads(capsys.readouterr().out)

        assert status == document["exit_code"] == EXIT_ISSUES
        assert document["fail_on_unmeasured"] is True
        assert document["unmeasured_count"] == 1
        issue = document["decks"][0]["slides"][0]["issues"][0]
        assert (issue["code"], issue["reason"], issue["shapes"]) == (
            "TextUnmeasured",
            "no-size",
            ["Zero"],
        )
        assert document["decks"][0]["slides"][0]["number"] == 1

    def it_refuses_to_run_with_the_issue_filtered_out(self, deck, capsys):
        status = main([str(deck), "--fail-on-unmeasured", "--min-severity", "warning"])

        assert status == EXIT_USAGE
        assert "--fail-on-unmeasured needs --min-severity info" in capsys.readouterr().err
