"""Real Chromium proves annotations become editable, data-backed objects."""

from __future__ import annotations

import io
import os
import shutil
from pathlib import Path

import pytest
from PIL import Image

from power_pptx import Presentation, add_plotly_figure
from power_pptx.compose import from_html
from power_pptx.enum.shapes import MSO_SHAPE_TYPE
from power_pptx.util import Inches

from ..schema.oxml_schema_validator import assert_schema_valid


@pytest.fixture(scope="module")
def browser_path():
    api = pytest.importorskip("playwright.sync_api")
    executable = os.environ.get("POWER_PPTX_CHROMIUM") or shutil.which("chromium")
    if executable:
        return executable
    with api.sync_playwright() as pw:
        if not Path(pw.chromium.executable_path).is_file():
            pytest.skip("Chromium is not installed")
    return None


def annotated(content):
    return (
        """<!doctype html><style>*{box-sizing:border-box}
    body{margin:0;font:24px "DejaVu Sans";color:#172334}
    section{width:1280px;height:720px;background:#f1f4fa;position:relative}
    h1{position:absolute;left:64px;top:70px;width:1100px;margin:0;font-size:56px;line-height:1.2}
    .card{position:absolute;left:64px;top:250px;width:680px;height:370px;
    border-radius:24px;background:white}
    .chart{position:absolute;left:90px;top:280px;width:620px;height:300px;font-size:18px}
    .visual{position:absolute;left:830px;top:280px;width:320px;height:280px;
    background:#6554e8;border-radius:50%;color:white;display:grid;place-items:center}
    table{position:absolute;left:64px;top:280px;width:1100px;height:300px;
    border-collapse:collapse;font-size:22px}
    td,th{padding:12px 18px;border-bottom:1px solid #c5cfdc;text-align:left}
    th{background:#172334;color:white}
    </style><section data-slide data-title="Editable source">"""
        + content
        + "</section>"
    )


def test_hybrid_removes_duplicate_text_and_preserves_rich_native_runs(browser_path, tmp_path):
    html = annotated(
        '<h1 data-pptx="text" data-name="headline">One <b>editable</b> headline<br>'
        'With a second line</h1><div class="visual" data-pptx="capture">Captured artwork</div>'
    )
    prs = from_html(html, mode="hybrid", browser_path=browser_path, reference_dir=tmp_path)
    slide = prs.slides[0]
    texts = [s for s in slide.shapes if s.has_text_frame and s.text]
    assert len(texts) == 1
    assert texts[0].name == "headline"
    assert "One editable headline" in texts[0].text
    assert "With a second line" in texts[0].text
    assert any(
        r.text == "editable" and r.font.bold for p in texts[0].text_frame.paragraphs for r in p.runs
    )
    assert sum(s.shape_type == MSO_SHAPE_TYPE.PICTURE for s in slide.shapes) == 2
    assert slide.shapes[0].image.blob != (tmp_path / "slide-00.png").read_bytes()
    # Header is absent from the background image, so editing it cannot reveal a duplicate.
    with Image.open(io.BytesIO(slide.shapes[0].image.blob)) as image:
        colors = image.crop((128, 140, 2200, 390)).getcolors(3000000)
        assert len(colors) == 1
    buf = io.BytesIO()
    prs.save(buf)
    assert_schema_valid(buf.getvalue())
    reopened = Presentation(io.BytesIO(buf.getvalue()))
    assert reopened.slides[0].shapes[1].text == texts[0].text


def test_hybrid_creates_editable_chart_with_embedded_workbook(browser_path):
    content = """<h1 data-pptx="text">An editable chart</h1><div class="card"></div>
    <div class="chart" data-pptx="chart" data-pptx-chart='{"type":"column",
    "categories":["Q1","Q2","Q3"],"series":[{"name":"Revenue","values":[12,18,26]}],
    "colors":["#6554E8"]}'>Browser chart placeholder</div>"""
    prs = from_html(annotated(content), mode="hybrid", browser_path=browser_path)
    chart = next(s.chart for s in prs.slides[0].shapes if s.has_chart)
    assert list(chart.series[0].values) == [12, 18, 26]
    assert [c.label for c in chart.plots[0].categories] == ["Q1", "Q2", "Q3"]
    assert chart.part.chart_workbook.xlsx_part.blob
    out = io.BytesIO()
    prs.save(out)
    assert_schema_valid(out.getvalue())


def test_hybrid_table_merges_and_styles_remain_editable(browser_path):
    table = """<table data-pptx="table"><tr><th colspan="3">Quarterly plan</th></tr>
    <tr><td>Product</td><td>240</td><td>On track</td></tr>
    <tr><td>Growth</td><td>180</td><td>Ahead</td></tr></table>"""
    prs = from_html(annotated(table), mode="hybrid", browser_path=browser_path)
    t = next(s.table for s in prs.slides[0].shapes if s.has_table)
    assert t.cell(0, 0).is_merge_origin
    assert t.cell(0, 0).span_width == 3
    assert t.cell(1, 0).text == "Product"
    assert t.cell(0, 0).text_frame.paragraphs[0].runs[0].font.bold
    out = io.BytesIO()
    prs.save(out)
    assert_schema_valid(out.getvalue())


@pytest.mark.parametrize(
    ("content", "match"),
    [
        ('<h1 data-pptx="text" style="transform:rotate(5deg)">Rotated</h1>', "transformed"),
        ('<h1 data-pptx="text"><b data-pptx="text">Nested</b></h1>', "nested"),
        ('<h1 data-pptx="unknown">Wrong</h1>', "expected text"),
        ('<h1 data-pptx="text" style="text-transform:uppercase">Title</h1>', "text transforms"),
        ('<h1 data-pptx="text" style="background:white">Title</h1>', "backgrounds"),
        ('<h1 data-pptx="text" style="box-shadow:0 2px 5px black">Title</h1>', "effects"),
        ('<div class="chart" data-pptx="chart" style="opacity:.5">Chart</div>', "opacity"),
        (
            '<div class="chart" data-pptx="chart" style="border-radius:12px">Chart</div>',
            "decorations",
        ),
        ('<h1 data-pptx="text"><span style="letter-spacing:2px">Wide</span></h1>', "decorations"),
        ('<h1 data-pptx="text" style="font-family:MissingFontXYZ">Font</h1>', "not installed"),
        (
            '<div class="chart" data-pptx="chart" data-pptx-chart=\'{"categories":["A"],'
            '"series":[{"name":"x","values":[1,2]}]}\'></div>',
            "category count",
        ),
    ],
)
def test_invalid_annotations_fail_contextually(browser_path, content, match):
    with pytest.raises((ValueError, RuntimeError), match=match):
        from_html(annotated(content), mode="hybrid", browser_path=browser_path)


@pytest.mark.parametrize("format", ["png", "svg"])
def test_real_plotly_browser_export_and_round_trip(browser_path, format):
    go = pytest.importorskip("plotly.graph_objects")
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    figure = go.Figure(go.Bar(x=["A", "B"], y=[12, 24], marker_color="#6554E8"))
    figure.update_layout(width=1200, height=800)
    picture = add_plotly_figure(
        slide,
        figure,
        Inches(1),
        Inches(1),
        backend="browser",
        format=format,
        browser_path=browser_path,
        width_px=600,
        height_px=300,
    )
    assert picture.width == Inches(600 / 96)
    assert picture.height == Inches(300 / 96)
    assert figure.layout.width == 1200
    assert figure.layout.height == 800
    with Image.open(io.BytesIO(picture.image.blob)) as png:
        assert png.size == (1200, 600)  # default 2x density, explicit 600x300 canvas
    assert ("svgBlip" in picture.element.xml) == (format == "svg")
    data = io.BytesIO()
    prs.save(data)
    assert_schema_valid(data.getvalue())


def test_real_plotly_auto_falls_back_after_kaleido_failure(browser_path, monkeypatch):
    go = pytest.importorskip("plotly.graph_objects")
    from power_pptx.design import figures

    def fail(*args, **kwargs):
        raise figures.FigureBackendUnavailable("Kaleido unavailable")

    monkeypatch.setattr(figures, "_plotly_to_blob", fail)
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    picture = add_plotly_figure(
        slide,
        go.Figure(go.Bar(y=[1, 2])),
        Inches(1),
        Inches(1),
        backend="auto",
        browser_path=browser_path,
    )
    assert "svgBlip" in picture.element.xml


def test_html_cli_hybrid_retains_external_references(browser_path, tmp_path):
    if not shutil.which("soffice") or not shutil.which("pdftoppm"):
        pytest.skip("LibreOffice and Poppler are required")
    from power_pptx.review import main

    source = tmp_path / "source.html"
    source.write_text(annotated('<h1 data-pptx="text">Editable in the CLI</h1>'))
    refs = tmp_path / "references"
    from_html(source, browser_path=browser_path, reference_dir=refs)
    reference = (refs / "slide-00.png").read_bytes()
    args = [
        str(source),
        "--mode",
        "hybrid",
        "--reference-dir",
        str(refs),
        "--out-dir",
        str(tmp_path / "review"),
        "--dpi",
        "36",
    ]
    if browser_path:
        args += ["--browser-path", browser_path]
    assert main(args) == 0
    assert (refs / "slide-00.png").read_bytes() == reference
    reopened = Presentation(tmp_path / "review/presentation.pptx")
    assert any(
        s.has_text_frame and "Editable in the CLI" in s.text for s in reopened.slides[0].shapes
    )
