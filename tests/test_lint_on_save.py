"""Unit-test suite for the `Presentation.lint_on_save` validation hook."""

from __future__ import annotations

import logging

import pytest

import power_pptx
from power_pptx.exc import LintError
from power_pptx.util import Inches


def _prs_with_off_slide_shape():
    """Return a |Presentation| whose single slide has an error-severity lint issue.

    A textbox placed well past the right edge of the slide produces an
    ERROR-severity ``OffSlide`` issue.
    """
    prs = power_pptx.Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    textbox = slide.shapes.add_textbox(Inches(20), Inches(1), Inches(2), Inches(1))
    textbox.text_frame.text = "way off the slide"
    return prs


class DescribeLintOnSave(object):
    def it_defaults_to_off(self):
        prs = power_pptx.Presentation()
        assert prs.lint_on_save == "off"

    def it_can_change_its_lint_on_save_mode(self):
        prs = power_pptx.Presentation()
        prs.lint_on_save = "warn"
        assert prs.lint_on_save == "warn"
        prs.lint_on_save = "raise"
        assert prs.lint_on_save == "raise"
        prs.lint_on_save = "off"
        assert prs.lint_on_save == "off"

    def it_raises_on_an_invalid_lint_on_save_mode(self):
        prs = power_pptx.Presentation()
        with pytest.raises(ValueError, match="'off', 'warn', or 'raise'"):
            prs.lint_on_save = "nope"  # pyright: ignore[reportAttributeAccessIssue]
        assert prs.lint_on_save == "off"

    def it_saves_a_broken_deck_silently_when_off(self, tmp_path, caplog):
        prs = _prs_with_off_slide_shape()
        pptx_path = tmp_path / "off.pptx"
        with caplog.at_level(logging.DEBUG, logger="power_pptx.presentation"):
            prs.save(str(pptx_path))
        assert pptx_path.exists()
        assert caplog.records == []

    def it_logs_error_issues_and_still_saves_when_warn(self, tmp_path, caplog):
        prs = _prs_with_off_slide_shape()
        prs.lint_on_save = "warn"
        pptx_path = tmp_path / "warn.pptx"
        with caplog.at_level(logging.WARNING, logger="power_pptx.presentation"):
            prs.save(str(pptx_path))
        assert pptx_path.exists()
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelno == logging.WARNING
        assert "slide 0" in record.getMessage()
        assert "OffSlide" in record.getMessage()

    def it_does_not_log_when_warn_and_the_deck_is_clean(self, tmp_path, caplog):
        prs = power_pptx.Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.lint_on_save = "warn"
        pptx_path = tmp_path / "clean.pptx"
        with caplog.at_level(logging.DEBUG, logger="power_pptx.presentation"):
            prs.save(str(pptx_path))
        assert pptx_path.exists()
        assert caplog.records == []

    def it_raises_LintError_naming_the_slide_when_raise(self, tmp_path):
        prs = _prs_with_off_slide_shape()
        prs.lint_on_save = "raise"
        pptx_path = tmp_path / "raise.pptx"
        with pytest.raises(LintError) as exc:
            prs.save(str(pptx_path))
        message = str(exc.value)
        assert "slide 0" in message
        assert "OffSlide" in message

    def it_does_not_write_the_file_when_raise(self, tmp_path):
        prs = _prs_with_off_slide_shape()
        prs.lint_on_save = "raise"
        pptx_path = tmp_path / "not-written.pptx"
        with pytest.raises(LintError):
            prs.save(str(pptx_path))
        assert not pptx_path.exists()

    def it_saves_a_clean_deck_when_raise(self, tmp_path):
        prs = power_pptx.Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.lint_on_save = "raise"
        pptx_path = tmp_path / "clean-raise.pptx"
        prs.save(str(pptx_path))
        assert pptx_path.exists()

    def it_does_not_persist_the_setting_into_the_saved_file(self, tmp_path):
        prs = power_pptx.Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.lint_on_save = "warn"
        pptx_path = tmp_path / "round-trip.pptx"
        prs.save(str(pptx_path))
        assert prs.lint_on_save == "warn"

        reopened = power_pptx.Presentation(str(pptx_path))
        assert reopened.lint_on_save == "off"

    def it_keeps_the_setting_on_the_same_presentation_object(self):
        prs = power_pptx.Presentation()
        prs.lint_on_save = "raise"
        # ---- the proxy is a singleton per part, so the setting survives a
        # ---- round-trip through the part it belongs to
        assert prs.part.presentation is prs
        assert prs.part.presentation.lint_on_save == "raise"
