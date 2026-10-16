"""Browser-backed HTML capture shared by figures and presentation composition."""

from __future__ import annotations

import math
import os
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any, Literal, Union, cast
from urllib.parse import quote

HtmlSource = Union[str, bytes, "os.PathLike[str]"]


@dataclass(frozen=True)
class HtmlCapture:
    png: bytes
    title: str
    text: str
    exported: str | None = None
    elements: tuple[dict[str, Any], ...] = ()
    reference_png: bytes | None = None
    size: tuple[float, float] | None = None


# Wait for actual image decoding, including lazy images in a selected section.
# Font readiness is checked afterwards because loading CSS can introduce fonts.
_READY = """async (root, timeout) => {
    let timer;
    const ready = async () => {
    const images = [...root.querySelectorAll('img')];
    if (root.tagName === 'IMG') images.unshift(root);
    await Promise.all(images.map(async image => {
        image.loading = 'eager';
        try { await image.decode(); }
        catch {
            throw new Error('Could not decode HTML image: ' + (image.currentSrc || image.src));
        }
    }));
    await document.fonts.ready;
    const failedFonts = [...document.fonts].filter(font => font.status === 'error');
    if (failedFonts.length) {
        throw new Error('Could not load HTML font: ' + failedFonts.map(f => f.family).join(', '));
    }
    };
    try {
        await Promise.race([ready(), new Promise((_, reject) => {
            timer = setTimeout(() => reject(new Error('Timed out waiting for HTML images/fonts')),
                               timeout);
        })]);
    } finally { clearTimeout(timer); }
}"""


def capture_html(
    html: HtmlSource,
    *,
    viewport: tuple[int, int] = (1280, 720),
    device_scale_factor: float = 2.0,
    selector: str | None = None,
    multiple: bool = False,
    wait_until: str = "load",
    wait_for_function: str | None = None,
    full_page: bool = False,
    timeout_ms: int = 15000,
    omit_background: bool = False,
    browser_path: str | os.PathLike[str] | None = None,
    check_overflow: bool = False,
    export_script: str | None = None,
    hybrid: bool = False,
) -> list[HtmlCapture]:
    """Capture a viewport or selected elements in one browser session.

    Paths are served from a temporary loopback HTTP server so adjacent assets
    retain their base directory, including in browsers that prohibit file URLs.
    Inline markup keeps normal browser URL rules.
    """
    from power_pptx.design.figures import FigureBackendUnavailable

    if len(viewport) != 2 or any(
        isinstance(n, bool) or not isinstance(n, int) or n <= 0 for n in viewport
    ):
        raise ValueError("viewport must contain two positive integer CSS pixel dimensions")
    if not math.isfinite(device_scale_factor) or device_scale_factor <= 0:
        raise ValueError("device_scale_factor must be finite and positive")
    if timeout_ms <= 0:
        raise ValueError("timeout_ms must be positive")
    if wait_until not in {"load", "domcontentloaded", "networkidle"}:
        raise ValueError("wait_until must be 'load', 'domcontentloaded', or 'networkidle'")
    load_state = cast(Literal["load", "domcontentloaded", "networkidle"], wait_until)
    if selector is not None and (not isinstance(selector, str) or not selector.strip()):
        raise ValueError("selector must be a non-empty CSS selector or None")
    if selector is not None and full_page:
        raise ValueError("full_page and selector cannot be used together")
    if hybrid and selector is None:
        raise ValueError("hybrid capture requires an explicit section selector")

    # Strings ending in .html/.htm are accepted as file paths; use bytes to
    # represent literal text with that suffix. PathLike inputs always mean files.
    path = None
    if isinstance(html, os.PathLike) or (
        isinstance(html, str)
        and not html.lstrip().startswith("<")
        and Path(html).suffix.lower() in {".html", ".htm"}
    ):
        path = Path(html).expanduser().resolve(strict=True)
    elif isinstance(html, bytes):
        html = html.decode("utf-8-sig")
    elif not isinstance(html, str):
        raise TypeError("html must be markup, UTF-8 bytes, or a local HTML path")

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise FigureBackendUnavailable(
            "HTML rendering needs Playwright; install with "
            "`pip install 'power-pptx[html]' && python -m playwright install chromium`."
        ) from exc

    with ExitStack() as stack:
        source_url = stack.enter_context(_serve_html(path)) if path is not None else None
        pw = stack.enter_context(sync_playwright())
        executable = browser_path or os.environ.get("POWER_PPTX_CHROMIUM")
        try:
            browser = pw.chromium.launch(
                executable_path=os.fspath(executable) if executable else None
            )
        except PlaywrightError as exc:
            raise FigureBackendUnavailable(
                "Playwright failed to launch Chromium. Run `python -m playwright install chromium` "
                "or set POWER_PPTX_CHROMIUM to an installed Chromium executable. "
                f"Original error: {exc}"
            ) from exc
        try:
            page = browser.new_page(
                viewport={"width": viewport[0], "height": viewport[1]},
                device_scale_factor=device_scale_factor,
                reduced_motion="reduce",
            )
            page.set_default_timeout(timeout_ms)
            page.set_default_navigation_timeout(timeout_ms)
            if source_url is not None:
                page.goto(source_url, wait_until=load_state)
            else:
                page.set_content(cast(str, html), wait_until=load_state)
            if wait_for_function:
                page.wait_for_function(wait_for_function)

            if selector is None:
                targets = [page.locator("body")]
            else:
                matches = page.locator(selector)
                matches.first.wait_for(state="visible")
                count = matches.count()
                if not multiple and count != 1:
                    raise ValueError(
                        f"selector {selector!r} must match one element; matched {count}"
                    )
                targets = [matches.nth(index) for index in range(count)]

            captures = []
            for index, target in enumerate(targets):
                if selector is not None:
                    target.scroll_into_view_if_needed()
                target.evaluate(_READY, timeout_ms)
                if check_overflow and target.evaluate(
                    "el => el.scrollWidth > el.clientWidth + 1 || "
                    "el.scrollHeight > el.clientHeight + 1"
                ):
                    raise ValueError(
                        f"HTML section {index + 1} overflows its container; resize it, shorten "
                        "the content, or set check_overflow=False for intentional overflow"
                    )
                text = target.inner_text().strip()
                title = target.get_attribute("data-title") or target.get_attribute("aria-label")
                if not title:
                    headings = target.locator("h1, h2, h3")
                    title = headings.first.inner_text() if headings.count() else text[:120]
                png = (
                    page.screenshot(
                        full_page=full_page,
                        type="png",
                        animations="disabled",
                        caret="hide",
                        omit_background=omit_background,
                    )
                    if selector is None
                    else target.screenshot(
                        type="png",
                        animations="disabled",
                        caret="hide",
                        omit_background=omit_background,
                    )
                )
                reference = None
                elements = ()
                size = None
                if hybrid:
                    from power_pptx.design._html_layers import capture_layers, restore_layers

                    reference = png
                    bounds = target.bounding_box()
                    if bounds is None:
                        raise ValueError("HTML slide has no visible bounds")
                    size = (bounds["width"], bounds["height"])
                    elements, original = capture_layers(target, timeout_ms=timeout_ms)
                    try:
                        png = target.screenshot(
                            type="png",
                            animations="disabled",
                            caret="hide",
                            omit_background=omit_background,
                        )
                    finally:
                        restore_layers(target, original)
                exported = page.evaluate(export_script) if export_script else None
                if exported is not None and not isinstance(exported, str):
                    raise ValueError("HTML export_script must return a string")
                captures.append(
                    HtmlCapture(png, title.strip(), text, exported, elements, reference, size)
                )
            return captures
        except PlaywrightError as exc:
            raise RuntimeError(f"HTML capture failed: {exc}") from exc
        finally:
            browser.close()


@contextmanager
def _serve_html(path: Path):
    """Serve only the document directory on an ephemeral loopback port."""

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(path.parent)))
    thread = Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/{quote(path.name)}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
