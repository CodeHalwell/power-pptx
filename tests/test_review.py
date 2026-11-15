"""Unit tests for `power_pptx.review` that need neither LibreOffice nor a browser.

The rendering paths are exercised by `tests/integration/test_review.py`.
"""

from __future__ import annotations

import json

import pytest

from power_pptx import Presentation
from power_pptx.review import _clear_previous_run, main, review_presentation
from power_pptx.util import Inches


def _deck():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1)).text = "Review me"
    return prs


#: What a four-slide review with references leaves in its output directory.
PREVIOUS_RUN = [
    "presentation.pptx",
    "presentation.pdf",
    "manifest.json",
    "REVIEW.md",
    "index.html",
    "contact-01.png",
    "contact-02.png",
    "slides/slide-00.png",
    "slides/slide-01.png",
    "slides/slide-02.png",
    "slides/slide-03.png",
    "references/slide-00.png",
    "differences/slide-00.png",
    "browser-reference/slide-00.png",
]

#: Files a review never writes, in the places where it writes its own.
CALLERS_FILES = [
    "notes.txt",
    "contact-sheet-draft.png",
    "slide-00.png",
    "slides/slide-00.psd",
    "slides/cover.png",
    "assets/slides/slide-00.png",
]


@pytest.fixture
def reused(tmp_path):
    """An output directory holding an earlier review and some files of the caller's."""
    out = tmp_path / "review"
    for name in PREVIOUS_RUN + CALLERS_FILES:
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"from before")
    return out


def _files(directory):
    return sorted(
        path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()
    )


class DescribeClearPreviousRun:
    def it_removes_what_an_earlier_review_wrote_and_nothing_else(self, reused):
        _clear_previous_run(reused)

        assert _files(reused) == sorted(CALLERS_FILES)
        # -- folders the review made are gone once empty; one still in use stays --
        assert not (reused / "references").exists()
        assert not (reused / "differences").exists()
        assert not (reused / "browser-reference").exists()
        assert (reused / "slides").is_dir()

    def it_does_nothing_for_a_directory_that_is_not_there_yet(self, tmp_path):
        _clear_previous_run(tmp_path / "absent")

        assert not (tmp_path / "absent").exists()

    def it_does_not_follow_a_linked_folder(self, tmp_path):
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "slide-00.png").write_bytes(b"not ours")
        out = tmp_path / "review"
        out.mkdir()
        try:
            (out / "slides").symlink_to(elsewhere, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symbolic links are not available here")

        _clear_previous_run(out)

        assert (elsewhere / "slide-00.png").read_bytes() == b"not ours"


class DescribeReviewPresentationReuse:
    def it_replaces_the_previous_run_even_when_this_one_cannot_render(self, reused):
        report = review_presentation(_deck(), out_dir=reused, soffice_bin="/absent/soffice")

        assert report.has_errors
        assert report.manifest["slides"] == []
        # -- the earlier run's pages, sheets, comparison and PDF are gone ... --
        assert _files(reused) == sorted(
            CALLERS_FILES + ["presentation.pptx", "manifest.json", "REVIEW.md", "index.html"]
        )
        # -- ... and what remains is this run's, not a leftover of the same name --
        assert json.loads((reused / "manifest.json").read_text())["passed"] is False
        assert (reused / "presentation.pptx").read_bytes() != b"from before"
        assert (reused / "notes.txt").read_bytes() == b"from before"


class DescribeReviewCli:
    def it_keeps_the_last_review_when_the_input_cannot_be_read(self, reused, tmp_path):
        missing = tmp_path / "missing.pptx"

        assert main([str(missing), "--out-dir", str(reused)]) == 1

        # -- nothing was reviewed, so nothing of the earlier review is discarded --
        assert _files(reused) == sorted(PREVIOUS_RUN + CALLERS_FILES)
        assert json.loads((reused / "manifest.json").read_text())["passed"] is False
        assert (reused / "slides" / "slide-03.png").read_bytes() == b"from before"

    def it_never_removes_an_input_that_lives_in_the_output_directory(self, tmp_path):
        out = tmp_path / "review"
        out.mkdir()
        source = out / "presentation.pptx"
        _deck().save(source)
        original = source.read_bytes()

        assert main([str(source), "--out-dir", str(out)]) == 1

        assert source.read_bytes() == original
        assert "overwrite" in json.loads((out / "manifest.json").read_text())["error"]
