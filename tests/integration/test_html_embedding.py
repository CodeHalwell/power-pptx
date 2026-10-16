"""Real Chromium coverage for styled HTML, relative assets and deck composition."""

from __future__ import annotations

import io
import os
import shutil
from pathlib import Path

import pytest
from PIL import Image

from power_pptx import Presentation, add_html_figure
from power_pptx.compose import from_html, from_spec
from power_pptx.design.recipes import figure_slide
from power_pptx.enum.shapes import MSO_SHAPE_TYPE
from power_pptx.util import Inches

from ..schema.oxml_schema_validator import assert_schema_valid, schema_validation_available


@pytest.fixture(scope="module")
def browser_path():
    api = pytest.importorskip("playwright.sync_api")
    executable = os.environ.get("POWER_PPTX_CHROMIUM") or shutil.which("chromium")
    if executable:
        return executable
    with api.sync_playwright() as pw:
        if not Path(pw.chromium.executable_path).exists():
            pytest.skip("Playwright Chromium is not installed")
    return None


@pytest.fixture
def styled_html(tmp_path):
    Image.new("RGB", (20, 20), "#ff9900").save(tmp_path / "asset.png")
    shutil.copyfile(
        Path(__file__).parents[1] / "test_files" / "calibriz.ttf", tmp_path / "brand.ttf"
    )
    (tmp_path / "style.css").write_text(
        "body { margin:0 } section { box-sizing:border-box; width:320px; height:180px;"
        "padding:20px; background:#112233; color:white; font:18px TestBrand,sans-serif }"
        "@font-face { font-family:TestBrand; src:url(brand.ttf) }"
        "section + section { background:#223344 } h1 { margin:0 0 10px }",
        encoding="utf-8",
    )
    path = tmp_path / "deck.html"
    path.write_text(
        """<!doctype html><html><head><link rel="stylesheet" href="style.css"></head>
    <body><section data-slide data-title="Overview"><h1 id="heading">Loading</h1>
    <img src="asset.png" loading="lazy" width="20" height="20">
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">
      <rect width="20" height="20" fill="#00ff00"/></svg></section>
    <section data-slide><h1>Second slide</h1><img src="asset.png" loading="lazy"
      width="20" height="20"><p>Preserved in notes</p></section>
    <script>setTimeout(() => {
      document.querySelector('#heading').textContent = 'Ready to present';
      window.deckReady = true;
    }, 40);</script></body></html>""",
        encoding="utf-8",
    )
    return path


def test_html_sections_preserve_styles_assets_notes_and_round_trip(styled_html, browser_path):
    prs = from_html(
        styled_html,
        viewport=(320, 180),
        device_scale_factor=2,
        browser_path=browser_path,
        wait_for_function="window.deckReady === true",
    )
    assert len(prs.slides) == 2
    first, second = prs.slides
    assert first.shapes[0].name == "Overview"
    assert "Ready to present" in first.shapes[0].alt_text
    assert "Ready to present" in first.notes_slide.notes_text_frame.text
    assert "Preserved in notes" in second.notes_slide.notes_text_frame.text
    with Image.open(io.BytesIO(first.shapes[0].image.blob)) as image:
        assert image.size == (640, 360)
        assert image.getpixel((639, 359))[:3] == (17, 34, 51)
        colors = {color[:3] for _count, color in image.getcolors(image.width * image.height)}
        assert (255, 153, 0) in colors
        assert (0, 255, 0) in colors
    output = io.BytesIO()
    prs.save(output)
    if schema_validation_available():
        assert_schema_valid(output.getvalue())
    output.seek(0)
    reopened = Presentation(output)
    assert reopened.slides[0].shapes[0].name == "Overview"
    assert reopened.slides[0].shapes[0].image.blob == first.shapes[0].image.blob
    assert "Preserved in notes" in reopened.slides[1].notes_slide.notes_text_frame.text


def test_one_element_capture_preserves_transparency(browser_path):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    picture = add_html_figure(
        slide,
        '<div id="card" style="width:200px;height:100px;color:red">Hello</div>',
        Inches(0),
        Inches(0),
        selector="#card",
        omit_background=True,
        browser_path=browser_path,
        device_scale_factor=2,
    )
    assert picture.width.inches == pytest.approx(200 / 96, abs=0.001)
    assert picture.height.inches == pytest.approx(100 / 96, abs=0.001)
    with Image.open(io.BytesIO(picture.image.blob)) as image:
        assert image.size == (400, 200)
        assert image.getpixel((399, 199))[3] == 0


def test_html_with_inline_svg_is_dispatched_as_html(browser_path):
    prs = Presentation()
    html = '<html><body><svg width="20" height="20"></svg><h1>HTML title</h1></body></html>'
    slide = figure_slide(
        prs,
        title="Browser figure",
        figure=html,
        html_options={"browser_path": browser_path, "viewport": (320, 180)},
    )
    assert len([shape for shape in slide.shapes if shape.shape_type == MSO_SHAPE_TYPE.PICTURE]) == 1


def test_json_figure_accepts_html_paths_and_capture_options(styled_html, browser_path):
    prs = from_spec(
        {
            "slides": [
                {
                    "layout": "figure",
                    "title": "Selected section",
                    "figure": str(styled_html),
                    "html_options": {
                        "selector": "section:first-of-type",
                        "viewport": (320, 180),
                        "browser_path": browser_path,
                    },
                }
            ]
        }
    )
    assert len(prs.slides) == 1


@pytest.mark.parametrize(
    ("html", "match"),
    [
        (
            '<section data-slide style="width:320px;height:100px"><div style="height:200px"></div>'
            "</section>",
            "overflows",
        ),
        (
            '<section data-slide><img src="file:///no-such-image.png"></section>',
            "decode HTML image",
        ),
    ],
)
def test_capture_reports_content_failures(browser_path, html, match):
    with pytest.raises((ValueError, RuntimeError), match=match):
        from_html(html, browser_path=browser_path, viewport=(320, 180), timeout_ms=1000)


def test_unmatched_selector_has_a_bounded_failure(browser_path):
    with pytest.raises(RuntimeError, match="HTML capture failed"):
        from_html("<h1>No slide sections</h1>", browser_path=browser_path, timeout_ms=100)


def test_notes_can_be_omitted(browser_path):
    prs = from_html(
        "<section data-slide>Only a picture</section>",
        include_notes=False,
        check_overflow=False,
        browser_path=browser_path,
    )
    assert not prs.slides[0].has_notes_slide
