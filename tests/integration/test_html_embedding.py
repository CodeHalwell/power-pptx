"""Real Chromium coverage for styled HTML, relative assets and deck composition."""

from __future__ import annotations

import asyncio
import http.server
import io
import os
import shutil
import socket
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from power_pptx import Presentation, add_html_figure
from power_pptx.compose import from_html, from_spec
from power_pptx.design._html import capture_html
from power_pptx.design.figures import FigureBackendUnavailable
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
        Path(__file__).parents[1] / "test_files" / "Outfit-Bold.ttf", tmp_path / "brand.ttf"
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


def test_json_figure_accepts_html_paths_and_capture_options(styled_html, browser_path, monkeypatch):
    # A spec cannot name the browser executable; the process chooses it.
    if browser_path:
        monkeypatch.setenv("POWER_PPTX_CHROMIUM", browser_path)
    prs = from_spec(
        {
            "slides": [
                {
                    "layout": "figure",
                    "title": "Selected section",
                    "figure": str(styled_html),
                    "html_options": {
                        "selector": "section:first-of-type",
                        "viewport": [320, 180],
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


def test_unmatched_selector_is_reported_at_once_and_says_what_is_missing(browser_path):
    # A static document cannot grow a matching element, so nothing is gained
    # by waiting out the timeout before saying so.
    started = time.monotonic()
    with pytest.raises(ValueError, match=r"no element matches the selector '\[data-slide\]'") as e:
        from_html("<h1>No slide sections</h1>", browser_path=browser_path, timeout_ms=30000)
    assert time.monotonic() - started < 20
    assert "<section data-slide" in str(e.value)


def test_unmatched_selector_waits_for_a_script_but_stays_bounded(browser_path):
    late = (
        "<body><script>setTimeout(() => { document.body.innerHTML = "
        "'<section data-slide style=\"width:320px;height:180px\">Late</section>' }, 150)"
        "</script></body>"
    )
    prs = from_html(late, browser_path=browser_path, viewport=(320, 180), timeout_ms=10000)
    assert len(prs.slides) == 1
    never = "<body><p>nothing</p><script>window.x = 1</script></body>"
    with pytest.raises(ValueError, match="Waited 300 ms for a script to add it"):
        from_html(never, browser_path=browser_path, timeout_ms=300)


def test_invisible_section_says_it_needs_a_size(browser_path):
    with pytest.raises(ValueError, match="matches 1 element.*not visible"):
        from_html(
            '<section data-slide style="display:none">Hidden</section>',
            browser_path=browser_path,
            timeout_ms=30000,
        )


def test_image_without_a_source_does_not_abort_the_capture(browser_path):
    prs = from_html(
        '<section data-slide style="width:320px;height:180px">'
        '<img alt="placeholder"><img src="" alt="empty"><p>Text</p></section>',
        browser_path=browser_path,
        viewport=(320, 180),
    )
    assert "Text" in prs.slides[0].notes_slide.notes_text_frame.text


def test_capture_inside_a_running_event_loop_explains_itself(browser_path):
    async def call():
        return from_html("<section data-slide>x</section>", browser_path=browser_path)

    with pytest.raises(RuntimeError, match=r"asyncio\.to_thread") as e:
        asyncio.run(call())
    assert "event loop" in str(e.value)


def test_notes_can_be_omitted(browser_path):
    prs = from_html(
        "<section data-slide>Only a picture</section>",
        include_notes=False,
        check_overflow=False,
        browser_path=browser_path,
    )
    assert not prs.slides[0].has_notes_slide


# -- capture options ---------------------------------------------------------


def _png_size(data):
    with Image.open(io.BytesIO(data)) as image:
        return image.size


def test_a_selector_matching_several_elements_needs_multiple(browser_path):
    markup = '<div class="x" style="width:20px;height:20px"></div>' * 2
    with pytest.raises(ValueError, match=r"selector '\.x' must match one element; matched 2"):
        capture_html(markup, selector=".x", browser_path=browser_path)
    captures = capture_html(markup, selector=".x", multiple=True, browser_path=browser_path)
    assert [_png_size(c.png) for c in captures] == [(40, 40), (40, 40)]


def test_titles_fall_back_from_attributes_to_headings_to_text(browser_path):
    long_text = "word " * 40
    markup = (
        '<section data-title=" Named " aria-label="Ignored"><h1>Heading</h1></section>'
        '<section aria-label="Labelled"><h1>Heading</h1></section>'
        "<section><p>Intro</p><h2>Second heading</h2></section>"
        f"<section><p>  {long_text}  </p></section>"
    )
    captures = capture_html(
        markup, selector="section", multiple=True, browser_path=browser_path, viewport=(320, 180)
    )
    assert [c.title for c in captures] == [
        "Named",
        "Labelled",
        "Second heading",
        long_text.strip()[:120].strip(),
    ]
    assert captures[3].text == long_text.strip()
    assert captures[2].text == "Intro\n\nSecond heading"


def test_markup_bytes_and_html_like_strings_are_documents(browser_path):
    from_bytes = capture_html(b"\xef\xbb\xbf<h1>From bytes</h1>", browser_path=browser_path)
    assert from_bytes[0].text == "From bytes"
    markup = capture_html("<p>see page.html</p>", browser_path=browser_path)
    assert markup[0].text == "see page.html"


def test_full_page_captures_beyond_the_viewport(browser_path):
    markup = '<body style="margin:0"><div style="width:100px;height:400px"></div></body>'
    options = {"viewport": (320, 180), "device_scale_factor": 1, "browser_path": browser_path}
    assert _png_size(capture_html(markup, **options)[0].png) == (320, 180)
    assert _png_size(capture_html(markup, full_page=True, **options)[0].png) == (320, 400)


def test_export_script_results_are_strings_or_nothing(browser_path):
    markup = "<h1>Export</h1>"
    exported = capture_html(markup, export_script="() => 'svg'", browser_path=browser_path)
    assert exported[0].exported == "svg"
    nothing = capture_html(markup, export_script="() => null", browser_path=browser_path)
    assert nothing[0].exported is None
    with pytest.raises(ValueError, match="export_script must return a string"):
        capture_html(markup, export_script="() => 42", browser_path=browser_path)


def test_a_browser_that_cannot_start_is_reported_as_unavailable(tmp_path):
    pytest.importorskip("playwright.sync_api")
    page = tmp_path / "page.html"
    page.write_text("<h1>x</h1>", encoding="utf-8")
    with pytest.raises(FigureBackendUnavailable, match="Playwright failed to launch Chromium"):
        capture_html(page, browser_path=tmp_path / "no-such-chromium")


def test_a_browser_error_is_reported_as_a_capture_failure(browser_path):
    with pytest.raises(RuntimeError, match="HTML capture failed: .*boom"):
        capture_html(
            "<h1>x</h1>",
            browser_path=browser_path,
            wait_for_function="() => { throw new Error('boom') }",
        )


def test_a_blocked_request_is_named_as_the_cause_of_a_failure(browser_path):
    url = "http://198.51.100.7/chart.png"
    with pytest.raises(ValueError, match="blocked 1 request") as error:
        capture_html(
            f'<img src="{url}" width="10" height="10">',
            browser_path=browser_path,
            allow_network=False,
            timeout_ms=5000,
        )
    assert url in str(error.value)
    assert isinstance(error.value.__cause__, Exception)


# -- what a captured document can reach --------------------------------------


class _Recorder(http.server.BaseHTTPRequestHandler):
    hits: list = []

    def do_GET(self):
        self.hits.append(self.path)
        body = b"<html><body><h1>INTERNAL-ONLY</h1></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def internal_service():
    """A loopback HTTP service standing in for something the page must not reach."""
    _Recorder.hits = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_port, _Recorder.hits
    server.shutdown()
    server.server_close()
    thread.join()


def _probing_markup(port):
    return (
        f'<html><body><h1>Chart</h1><iframe src="http://127.0.0.1:{port}/admin/keys" '
        'width="300" height="100"></iframe><script>'
        f"fetch('http://127.0.0.1:{port}/metadata', {{mode: 'no-cors'}}).catch(() => {{}})"
        ".finally(() => { window.done = true })</script></body></html>"
    )


def test_network_access_is_on_by_default(browser_path, internal_service):
    port, hits = internal_service
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_html_figure(
        slide,
        _probing_markup(port),
        Inches(0),
        Inches(0),
        browser_path=browser_path,
        wait_for_function="window.done === true",
    )
    assert "/admin/keys" in hits


def test_allow_network_false_blocks_requests_and_reports_them(browser_path, internal_service):
    port, hits = internal_service
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    with pytest.raises(ValueError, match="allow_network=False") as e:
        add_html_figure(
            slide,
            _probing_markup(port),
            Inches(0),
            Inches(0),
            browser_path=browser_path,
            wait_for_function="window.done === true",
            allow_network=False,
        )
    assert hits == []
    assert f"http://127.0.0.1:{port}/admin/keys" in str(e.value)
    assert len(slide.shapes) == 0


def test_allow_network_false_stops_a_worker_websocket(browser_path):
    # Request routing never sees a socket opened from a worker; the browser
    # has to be unable to connect in the first place.
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    listener.settimeout(0.2)
    port = listener.getsockname()[1]
    markup = (
        "<body><p>x</p><script>const w = new Worker(URL.createObjectURL(new Blob(["
        f"\"const s = new WebSocket('ws://127.0.0.1:{port}/x');"
        "s.onerror = () => postMessage('error'); s.onopen = () => postMessage('open');\""
        "], {type: 'text/javascript'})));"
        "w.onmessage = e => { window.socketState = e.data };"
        "setTimeout(() => { window.done = true }, 1500);</script></body>"
    )
    try:
        from power_pptx.design._html import capture_html

        capture_html(
            markup,
            browser_path=browser_path,
            wait_for_function="window.done === true",
            allow_network=False,
        )
        with pytest.raises(socket.timeout):
            listener.accept()
    finally:
        listener.close()


def test_allow_network_false_keeps_the_documents_own_assets(styled_html, browser_path):
    styled_html.write_text(
        styled_html.read_text(encoding="utf-8").replace(
            "<p>Preserved in notes</p>",
            '<p>Preserved in notes</p><img width="2" height="2" src="data:image/png;base64,'
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAA"
            'AABJRU5ErkJggg==">',
        ),
        encoding="utf-8",
    )
    prs = from_html(
        styled_html,
        viewport=(320, 180),
        browser_path=browser_path,
        wait_for_function="window.deckReady === true",
        allow_network=False,
    )
    with Image.open(io.BytesIO(prs.slides[0].shapes[0].image.blob)) as image:
        colors = {color[:3] for _count, color in image.getcolors(image.width * image.height)}
    # The stylesheet, the web font and the image all came from the loopback server.
    assert (17, 34, 51) in colors
    assert (255, 153, 0) in colors


def test_captured_page_cannot_list_or_leave_its_directory(tmp_path, browser_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET", encoding="utf-8")
    docs = tmp_path / "docs"
    (docs / "sub").mkdir(parents=True)
    (docs / "sub" / "inner.txt").write_text("inner", encoding="utf-8")
    (docs / "notes.txt").write_text("sibling", encoding="utf-8")
    try:
        (docs / "link.txt").symlink_to(secret)
    except OSError:
        pytest.skip("symlinks are not available")
    (docs / "page.html").write_text(
        """<body><pre id="out"></pre><script>(async () => {
        const lines = [];
        for (const url of ['./', 'sub/', 'notes.txt', 'link.txt', '../secret.txt']) {
            const response = await fetch(url);
            lines.push(url + ' ' + response.status + ' ' + (await response.text()).length);
        }
        document.getElementById('out').textContent = lines.join('|');
        window.done = true;
        })()</script></body>""",
        encoding="utf-8",
    )
    from power_pptx.design._html import capture_html

    text = capture_html(
        docs / "page.html", browser_path=browser_path, wait_for_function="window.done === true"
    )[0].text
    results = dict(line.split(" ", 1) for line in text.split("|"))
    assert results["notes.txt"] == "200 7"
    assert results["./"].startswith("404")
    assert results["sub/"].startswith("404")
    assert results["link.txt"].startswith("404")
    assert results["../secret.txt"].startswith("404")
    assert "TOP-SECRET" not in text


def test_safe_spec_captures_html_figures_offline(browser_path, internal_service, monkeypatch):
    port, hits = internal_service
    if browser_path:
        monkeypatch.setenv("POWER_PPTX_CHROMIUM", browser_path)
    spec = {
        "slides": [
            {
                "layout": "figure",
                "title": "Quarterly chart",
                "figure": f"<html><body><iframe src='http://127.0.0.1:{port}/latest/meta-data'>"
                "</iframe></body></html>",
            }
        ]
    }
    with pytest.raises(ValueError, match=r"slides\[0\]\.figure: .*allow_network=False"):
        from_spec(spec, safe=True)
    assert hits == []
    # Without safe mode the same spec is the caller's responsibility, as before.
    from_spec(spec)
    assert hits == ["/latest/meta-data"]
