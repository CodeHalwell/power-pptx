"""Exercise the real optional rendering tools, including directory reuse."""

import os
import shutil

import pytest
from PIL import Image

from power_pptx import Presentation
from power_pptx.render import render_slide_thumbnails
from power_pptx.util import Inches

pytestmark = pytest.mark.skipif(
    not shutil.which(os.environ.get("POWER_PPTX_SOFFICE", "soffice"))
    or not shutil.which("pdftoppm"),
    reason="LibreOffice and Poppler are required for the rendering integration tests",
)


def _deck(count):
    prs = Presentation()
    for index in range(count):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        box.text = f"Slide {index + 1}"
    return prs


@pytest.mark.parametrize("strategy", ["png", "pdf"])
def test_reuses_output_directory_with_real_renderer(tmp_path, strategy):
    prs = _deck(1)
    for _ in range(2):
        paths = render_slide_thumbnails(prs, out_dir=tmp_path, strategy=strategy, dpi=36)
        assert len(paths) == 1
        with Image.open(paths[0]) as image:
            assert image.format == "PNG"
            assert min(image.size) > 0
            image.verify()


def test_shorter_deck_does_not_return_old_pages(tmp_path):
    paths = render_slide_thumbnails(_deck(2), out_dir=tmp_path, strategy="pdf", dpi=36)
    assert len(paths) == 2
    # An unrelated image must survive the second render, too.
    unrelated = tmp_path / "unrelated.png"
    unrelated.write_bytes(b"user data")

    paths = render_slide_thumbnails(_deck(1), out_dir=tmp_path, strategy="pdf", dpi=36)

    assert len(paths) == 1
    assert unrelated.read_bytes() == b"user data"
    assert not (tmp_path / "_render_input.pptx").exists()


@pytest.mark.skipif(not shutil.which("pdffonts"), reason="pdffonts (Poppler) is required")
def test_font_dirs_reach_libreoffice(tmp_path):
    import subprocess
    from pathlib import Path

    from power_pptx.render import _resolve_binary, _run_soffice_pdf, _soffice_env

    fonts = Path(__file__).parents[1] / "fonts"
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_text(
        Inches(1), Inches(1), Inches(6), Inches(1), text="Bundled font", font="Tektur"
    )
    deck = tmp_path / "deck.pptx"
    prs.save(deck)

    env = _soffice_env(tmp_path, [fonts])
    result = _run_soffice_pdf(_resolve_binary(None), deck, tmp_path, 120, env=env)

    assert result.returncode == 0
    listing = subprocess.run(
        ["pdffonts", str(tmp_path / "deck.pdf")], capture_output=True, text=True, check=True
    ).stdout
    assert "Tektur" in listing
