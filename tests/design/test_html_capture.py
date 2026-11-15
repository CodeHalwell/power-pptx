"""Validation and aspect-ratio invariants without optional browser dependencies."""

import inspect
import io
import socket
import urllib.error
import urllib.request
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PIL import Image

from power_pptx import Presentation
from power_pptx.compose import from_html
from power_pptx.design._html import (
    _block_network,
    _network_blocked,
    _offline_arguments,
    _refused_port,
    _serve_html,
    capture_html,
)
from power_pptx.design.figures import _embed_html_png, add_html_figure, add_plotly_figure
from power_pptx.util import Inches


@pytest.mark.parametrize(
    "options",
    [
        {"viewport": (0, 100)},
        {"viewport": (100.5, 100)},
        {"viewport": (True, 100)},
        {"device_scale_factor": 0},
        {"device_scale_factor": float("nan")},
        {"timeout_ms": 0},
        {"wait_until": "forever"},
        {"selector": ""},
        {"selector": ".slide", "full_page": True},
    ],
)
def test_invalid_options_fail_before_browser_launch(options):
    with patch("builtins.__import__", wraps=__import__) as imports:
        with pytest.raises(ValueError):
            capture_html("<h1>Example</h1>", **options)
    assert not any(call.args[0].startswith("playwright") for call in imports.call_args_list)


@pytest.mark.parametrize("fit", ["contain", "cover", "stretch"])
def test_picture_fitting_preserves_or_crops_as_requested(fit):
    data = io.BytesIO()
    Image.new("RGB", (400, 200)).save(data, format="PNG")
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    picture = _embed_html_png(
        slide,
        data.getvalue(),
        Inches(1),
        Inches(1),
        Inches(4),
        Inches(4),
        fit=fit,
        device_scale_factor=2,
    )
    assert picture.width == Inches(4)
    if fit == "contain":
        assert picture.height == Inches(2)
        assert picture.top == Inches(2)
    elif fit == "cover":
        assert picture.height == Inches(4)
        assert picture.crop_left == picture.crop_right == 0.25
    else:
        assert picture.height == Inches(4)
        assert picture.crop_left == 0


@pytest.fixture
def document_tree(tmp_path):
    """A document directory with a sibling, a sub-directory and a way out of it."""
    (tmp_path / "secret.txt").write_text("TOP-SECRET", encoding="utf-8")
    docs = tmp_path / "docs"
    (docs / "sub").mkdir(parents=True)
    (docs / "page.html").write_text("<h1>Page</h1>", encoding="utf-8")
    (docs / "style.css").write_text("h1 { color: red }", encoding="utf-8")
    (docs / "sub" / "inner.txt").write_text("inner", encoding="utf-8")
    (docs / "sub" / "index.html").write_text("<h1>Index</h1>", encoding="utf-8")
    return docs


def _status(url):
    # No proxies: the request must reach the loopback server directly.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def test_document_server_serves_the_document_and_its_assets(document_tree):
    with _serve_html(document_tree / "page.html") as url:
        base = url.rsplit("/", 1)[0]
        assert _status(url) == (200, b"<h1>Page</h1>")
        assert _status(f"{base}/style.css") == (200, b"h1 { color: red }")
        assert _status(f"{base}/sub/inner.txt") == (200, b"inner")


@pytest.mark.parametrize("request_path", ["", "sub", "sub/", "missing.txt"])
def test_document_server_never_lists_a_directory(document_tree, request_path):
    with _serve_html(document_tree / "page.html") as url:
        status, body = _status(f"{url.rsplit('/', 1)[0]}/{request_path}")
    assert status == 404
    assert b"inner.txt" not in body
    assert b"page.html" not in body


def test_document_server_does_not_follow_a_symlink_out_of_the_directory(document_tree):
    try:
        (document_tree / "link.txt").symlink_to(document_tree.parent / "secret.txt")
        (document_tree / "outside").symlink_to(document_tree.parent, target_is_directory=True)
        (document_tree / "alias.css").symlink_to(document_tree / "style.css")
    except OSError:
        pytest.skip("symlinks are not available")
    with _serve_html(document_tree / "page.html") as url:
        base = url.rsplit("/", 1)[0]
        for escape in ("link.txt", "outside/secret.txt", "../secret.txt", "%2e%2e/secret.txt"):
            status, body = _status(f"{base}/{escape}")
            assert status == 404, escape
            assert b"TOP-SECRET" not in body
        # A link that stays inside the directory is an ordinary asset.
        assert _status(f"{base}/alias.css") == (200, b"h1 { color: red }")


class _Route:
    def __init__(self, url):
        self.request = SimpleNamespace(url=url)
        self.outcome = None

    def continue_(self):
        self.outcome = "continued"

    def abort(self, code):
        self.outcome = f"aborted:{code}"


class _Context:
    def route(self, pattern, handler):
        self.pattern, self.handler = pattern, handler


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("data:image/png;base64,AAAA", True),
        ("blob:null/1b2c", True),
        ("about:blank", True),
        ("http://127.0.0.1:5000/deck.html", True),
        ("http://127.0.0.1:5000/assets/logo.svg", True),
        ("http://127.0.0.1:5001/admin", False),
        ("http://127.0.0.1:50001/admin", False),
        ("http://localhost:5000/deck.html", False),
        ("https://cdn.example.com/chart.js", False),
        ("http://169.254.169.254/latest/meta-data/", False),
        ("file:///etc/hostname", False),
        ("ftp://example.com/x", False),
    ],
)
def test_blocked_network_allows_only_local_content_and_the_document_origin(url, allowed):
    context, blocked = _Context(), []
    _block_network(context, "http://127.0.0.1:5000/deck.html", blocked)
    route = _Route(url)
    context.handler(route)
    assert context.pattern == "**/*"
    assert route.outcome == ("continued" if allowed else "aborted:blockedbyclient")
    assert blocked == ([] if allowed else [url])


def test_blocked_network_allows_no_origin_for_inline_markup():
    context, blocked = _Context(), []
    _block_network(context, None, blocked)
    route = _Route("http://127.0.0.1:5000/deck.html")
    context.handler(route)
    assert route.outcome == "aborted:blockedbyclient"


def test_offline_browser_arguments_exempt_only_the_document_server():
    arguments = _offline_arguments(4321, "http://127.0.0.1:5000/deck%20page.html")
    assert "--proxy-server=http://127.0.0.1:4321" in arguments
    # ``<-loopback>`` removes Chromium's blanket exemption for loopback
    # addresses; the document server is then the one address added back.
    assert "--proxy-bypass-list=<-loopback>;127.0.0.1:5000" in arguments
    assert "--proxy-bypass-list=<-loopback>" in _offline_arguments(4321, None)


def test_refused_port_rejects_connections_while_held():
    with _refused_port() as port:
        probe = socket.socket()
        probe.settimeout(2)
        try:
            assert probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()


def test_blocked_requests_are_summarised_once_each():
    urls = [f"https://example.com/{n}" for n in range(7)]
    message = str(_network_blocked([urls[0], *urls]))
    assert "blocked 7 request(s) because allow_network=False" in message
    assert "https://example.com/4" in message
    assert "https://example.com/5" not in message
    assert "and 2 more" in message


@pytest.mark.parametrize(
    "function",
    [capture_html, add_html_figure, add_plotly_figure, from_html],
)
def test_network_access_stays_on_unless_asked_otherwise(function):
    assert inspect.signature(function).parameters["allow_network"].default is True


def test_capture_density_does_not_change_physical_size():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    sizes = []
    for density in [1, 2, 3]:
        data = io.BytesIO()
        Image.new("RGB", (200 * density, 100 * density)).save(data, format="PNG")
        picture = _embed_html_png(
            slide,
            data.getvalue(),
            Inches(0),
            Inches(0),
            None,
            None,
            fit="contain",
            device_scale_factor=density,
        )
        sizes.append((picture.width, picture.height))
    assert len(set(sizes)) == 1
