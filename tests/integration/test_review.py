"""Review the saved presentation through real LibreOffice and browser output."""

import json
import shutil

import pytest

from power_pptx import Presentation
from power_pptx.review import main, review_presentation
from power_pptx.util import Inches

pytestmark = pytest.mark.skipif(
    not shutil.which("soffice") or not shutil.which("pdftoppm"),
    reason="LibreOffice and Poppler are required",
)


def deck(count=2):
    prs = Presentation()
    for index in range(count):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1)).text = str(index)
    return prs


def test_review_exports_all_pages_and_compares_references(tmp_path):
    first = review_presentation(deck(), out_dir=tmp_path / "first", dpi=36)
    assert not first.has_errors
    assert len(first.images) == 2
    for name in ["presentation.pptx", "presentation.pdf", "contact-01.png", "index.html"]:
        assert (first.directory / name).is_file()
    second = review_presentation(
        deck(),
        out_dir=tmp_path / "second",
        dpi=36,
        reference_dir=first.directory / "slides",
        max_mean_error=0,
    )
    assert not second.has_errors
    assert all(item["mean_error"] == 0 for item in second.manifest["comparisons"])
    assert second.manifest["visual_review"] == "pending"
    assert (second.directory / "differences/slide-01.png").is_file()


def test_review_reuse_cannot_count_stale_pages_and_mismatch_fails(tmp_path):
    review_presentation(deck(), out_dir=tmp_path / "reuse", dpi=36)
    stale = tmp_path / "reuse/slides/slide-01.png"
    assert stale.is_file()
    shorter = review_presentation(deck(1), out_dir=tmp_path / "reuse", dpi=36)
    assert len(shorter.images) == 1
    assert len(json.loads((shorter.directory / "manifest.json").read_text())["slides"]) == 1
    failed = review_presentation(
        deck(),
        out_dir=tmp_path / "failed",
        dpi=36,
        reference_dir=tmp_path / "reuse/slides",
        max_mean_error=0,
    )
    # A previous run may have extra files; references require an explicit exact set.
    assert not failed.has_errors
    empty = tmp_path / "empty"
    empty.mkdir()
    mismatch = review_presentation(deck(), out_dir=tmp_path / "mismatch", reference_dir=empty)
    assert mismatch.has_errors
    assert "Reference count" in mismatch.manifest["errors"][-1]
    assert (mismatch.directory / "presentation.pdf").is_file()


def test_review_failure_keeps_validation_and_does_not_overwrite_input(tmp_path):
    path = tmp_path / "presentation.pptx"
    deck(1).save(path)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        review_presentation(path, out_dir=tmp_path)
    failed = review_presentation(path, out_dir=tmp_path / "failed", soffice_bin="/absent/soffice")
    assert failed.has_errors
    assert failed.manifest["validation"]["schema_checked"]
    assert path.read_bytes() == before
    assert 'href="presentation.pdf"' not in (failed.directory / "index.html").read_text()


def test_cli_batch_continues_after_failure_and_writes_navigation(tmp_path):
    good = tmp_path / "good.pptx"
    deck(1).save(good)
    missing = tmp_path / "missing.pptx"
    target = tmp_path / "batch"
    assert main([str(good), str(missing), "--out-dir", str(target), "--dpi", "36"]) == 1
    results = json.loads((target / "batch.json").read_text())
    assert [r["passed"] for r in results] == [True, False]
    assert (target / "good/presentation.pdf").is_file()
    assert (target / "missing/manifest.json").is_file()
    assert "missing/index.html" in (target / "index.html").read_text()


@pytest.mark.parametrize("suffix", ["json", "yaml"])
def test_cli_accepts_declarative_sources(tmp_path, suffix):
    spec = {"slides": [{"layout": "title", "title": "A declarative source"}]}
    source = tmp_path / f"brief.{suffix}"
    if suffix == "json":
        source.write_text(json.dumps(spec))
    else:
        yaml = pytest.importorskip("yaml")
        source.write_text(yaml.safe_dump(spec))
    target = tmp_path / "review"
    assert main([str(source), "--out-dir", str(target), "--dpi", "36"]) == 0
    report = json.loads((target / "manifest.json").read_text())
    assert report["slide_count"] == 1
    assert report["validation"]["schema_checked"]
    reopened = Presentation(target / "presentation.pptx")
    assert reopened.slides[0].shapes.title.text == "A declarative source"


def test_cli_font_dir_registers_and_renders_bundled_fonts(tmp_path):
    from pathlib import Path

    from power_pptx.text import clear_registered_fonts

    fonts = Path(__file__).parents[1] / "fonts"
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_text(
        Inches(1), Inches(1), Inches(6), Inches(1), text="Bundled font", font="Tektur"
    )
    source = tmp_path / "deck.pptx"
    prs.save(source)
    target = tmp_path / "review"
    try:
        assert (
            main(
                [
                    str(source),
                    "--out-dir",
                    str(target),
                    "--dpi",
                    "36",
                    "--font-policy",
                    "error",
                    "--font-dir",
                    str(fonts),
                ]
            )
            == 0
        )
    finally:
        clear_registered_fonts()
    report = json.loads((target / "manifest.json").read_text())
    assert report["passed"]
