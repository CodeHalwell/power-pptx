"""Browser-backed HTML capture shared by figures and presentation composition."""

from __future__ import annotations

import asyncio
import math
import os
import socket
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any, Iterator, Literal, Union, cast
from urllib.parse import quote, urlsplit

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
# An <img> that names no source has nothing to decode — the browser shows its
# alt text or nothing — so it is skipped instead of failing the capture.
_READY = """async (root, timeout) => {
    let timer;
    const ready = async () => {
    const images = [...root.querySelectorAll('img')];
    if (root.tagName === 'IMG') images.unshift(root);
    await Promise.all(images.map(async image => {
        if (!image.getAttribute('src') && !image.getAttribute('srcset') && !image.currentSrc)
            return;
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

# URL schemes that never leave the page: the content is already in it.
_LOCAL_SCHEMES = frozenset({"data", "about", "blob"})


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
    allow_network: bool = True,
) -> list[HtmlCapture]:
    """Capture a viewport or selected elements in one browser session.

    Paths are served from a temporary loopback HTTP server so adjacent assets
    retain their base directory, including in browsers that prohibit file URLs.
    The server answers only for files that really live under the document's
    directory: no directory listings, and no symlink that leads out of it.
    Inline markup keeps normal browser URL rules.

    ``allow_network=False`` is for documents you did not write. Every request
    the page makes is routed, and only ``data:`` / ``blob:`` URLs and the
    capture's own loopback document may load; anything else — a remote
    stylesheet, an ``<iframe>`` onto an internal address — is aborted, and the
    capture then fails with a :class:`ValueError` listing what was blocked
    rather than producing a picture with pieces missing. Underneath the
    routing the browser itself is started with no route out (see
    :func:`_offline_arguments`), which is what stops the channels routing does
    not see, such as a WebSocket opened from a worker.

    The capture uses Playwright's synchronous API, so it cannot be called from
    a thread that is running an asyncio event loop; run it on a worker thread
    (``await asyncio.to_thread(...)``) there.
    """
    request = _CaptureRequest(
        viewport=viewport,
        device_scale_factor=device_scale_factor,
        selector=selector,
        multiple=multiple,
        wait_until=wait_until,
        wait_for_function=wait_for_function,
        full_page=full_page,
        timeout_ms=timeout_ms,
        omit_background=omit_background,
        browser_path=browser_path,
        check_overflow=check_overflow,
        export_script=export_script,
        hybrid=hybrid,
        allow_network=allow_network,
    )
    path, markup = _html_document(html)
    playwright_error, sync_playwright = _import_playwright()
    _refuse_running_event_loop()

    with ExitStack() as stack:
        source_url = stack.enter_context(_serve_html(path)) if path is not None else None
        pw = stack.enter_context(sync_playwright())
        browser = _launch_browser(pw, stack, request, source_url)
        blocked: list[str] = []
        try:
            page = _open_page(browser, request, source_url, blocked)
            _load_document(page, request, source_url, markup)
            captures = [
                _capture_target(page, target, index, request)
                for index, target in enumerate(_select_targets(page, request))
            ]
            if blocked:
                raise _network_blocked(blocked)
            return captures
        except playwright_error as exc:
            if blocked:
                # A blocked resource is usually *why* the page failed to
                # settle (an image that never decodes, a ready flag set by
                # a script that never loaded) — report the cause.
                raise _network_blocked(blocked) from exc
            raise RuntimeError(f"HTML capture failed: {exc}") from exc
        finally:
            browser.close()


@dataclass(frozen=True)
class _CaptureRequest:
    """The options of one :func:`capture_html` call, checked when it is made."""

    viewport: tuple[int, int]
    device_scale_factor: float
    selector: str | None
    multiple: bool
    wait_until: str
    wait_for_function: str | None
    full_page: bool
    timeout_ms: int
    omit_background: bool
    browser_path: str | os.PathLike[str] | None
    check_overflow: bool
    export_script: str | None
    hybrid: bool
    allow_network: bool

    def __post_init__(self) -> None:
        self._check_page()
        self._check_selection()

    def _check_page(self) -> None:
        viewport = self.viewport
        if len(viewport) != 2 or any(
            isinstance(n, bool) or not isinstance(n, int) or n <= 0 for n in viewport
        ):
            raise ValueError("viewport must contain two positive integer CSS pixel dimensions")
        if not math.isfinite(self.device_scale_factor) or self.device_scale_factor <= 0:
            raise ValueError("device_scale_factor must be finite and positive")
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if self.wait_until not in {"load", "domcontentloaded", "networkidle"}:
            raise ValueError("wait_until must be 'load', 'domcontentloaded', or 'networkidle'")

    def _check_selection(self) -> None:
        selector = self.selector
        if selector is not None and (not isinstance(selector, str) or not selector.strip()):
            raise ValueError("selector must be a non-empty CSS selector or None")
        if selector is not None and self.full_page:
            raise ValueError("full_page and selector cannot be used together")
        if self.hybrid and selector is None:
            raise ValueError("hybrid capture requires an explicit section selector")

    @property
    def load_state(self) -> Literal["load", "domcontentloaded", "networkidle"]:
        return cast(Literal["load", "domcontentloaded", "networkidle"], self.wait_until)


def _html_document(html: HtmlSource) -> tuple[Path | None, str | None]:
    """Return the file to serve for *html*, or else the markup to load."""
    # Strings ending in .html/.htm are accepted as file paths; use bytes to
    # represent literal text with that suffix. PathLike inputs always mean files.
    if isinstance(html, os.PathLike) or (
        isinstance(html, str)
        and not html.lstrip().startswith("<")
        and Path(html).suffix.lower() in {".html", ".htm"}
    ):
        return Path(html).expanduser().resolve(strict=True), None
    if isinstance(html, bytes):
        return None, html.decode("utf-8-sig")
    if not isinstance(html, str):
        raise TypeError("html must be markup, UTF-8 bytes, or a local HTML path")
    return None, html


def _import_playwright() -> tuple[type[Exception], Any]:
    """Return Playwright's error class and sync entry point, or say how to install it."""
    from power_pptx.design.figures import FigureBackendUnavailable

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise FigureBackendUnavailable(
            "HTML rendering needs Playwright; install with "
            "`pip install 'power-pptx[html]' && python -m playwright install chromium`."
        ) from exc
    return PlaywrightError, sync_playwright


def _refuse_running_event_loop() -> None:
    """Fail clearly on a thread that is running an asyncio event loop.

    Playwright's sync API refuses to start there, with an error that names
    neither this library nor the remedy.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    raise RuntimeError(
        "HTML capture drives the browser through Playwright's synchronous API, which "
        "cannot run on a thread that is already running an asyncio event loop (a "
        "Jupyter notebook, an async web handler or agent). Run the call on a worker "
        "thread instead, for example `await asyncio.to_thread(from_html, ...)`."
    )


def _launch_browser(
    pw: Any, stack: ExitStack, request: _CaptureRequest, source_url: str | None
) -> Any:
    """Start Chromium; without network access, with no route out of the machine.

    The refusing proxy port that an offline browser needs is held on *stack*.
    """
    from playwright.sync_api import Error as PlaywrightError

    from power_pptx.design.figures import FigureBackendUnavailable

    executable = request.browser_path or os.environ.get("POWER_PPTX_CHROMIUM")
    arguments = (
        None
        if request.allow_network
        else _offline_arguments(stack.enter_context(_refused_port()), source_url)
    )
    try:
        return pw.chromium.launch(
            executable_path=os.fspath(executable) if executable else None,
            args=arguments,
        )
    except PlaywrightError as exc:
        raise FigureBackendUnavailable(
            "Playwright failed to launch Chromium. Run `python -m playwright install chromium` "
            "or set POWER_PPTX_CHROMIUM to an installed Chromium executable. "
            f"Original error: {exc}"
        ) from exc


def _open_page(
    browser: Any, request: _CaptureRequest, source_url: str | None, blocked: list[str]
) -> Any:
    """Open a page with the capture's viewport and timeouts.

    Without network access its requests are routed through
    :func:`_block_network`, which records what it refuses in *blocked*.
    """
    context = browser.new_context(
        viewport={"width": request.viewport[0], "height": request.viewport[1]},
        device_scale_factor=request.device_scale_factor,
        reduced_motion="reduce",
        service_workers="allow" if request.allow_network else "block",
    )
    if not request.allow_network:
        _block_network(context, source_url, blocked)
    page = context.new_page()
    page.set_default_timeout(request.timeout_ms)
    page.set_default_navigation_timeout(request.timeout_ms)
    return page


def _load_document(
    page: Any, request: _CaptureRequest, source_url: str | None, markup: str | None
) -> None:
    """Load the served file or the markup, then wait for the caller's readiness check."""
    if source_url is not None:
        page.goto(source_url, wait_until=request.load_state)
    else:
        page.set_content(cast(str, markup), wait_until=request.load_state)
    if request.wait_for_function:
        page.wait_for_function(request.wait_for_function)


def _select_targets(page: Any, request: _CaptureRequest) -> list[Any]:
    """Return the elements to capture: the body, or what the selector matches."""
    selector = request.selector
    if selector is None:
        return [page.locator("body")]
    matches = page.locator(selector)
    # Readiness is settled when the caller defined it, or when the
    # document has no script that could still add the element.
    settled = bool(request.wait_for_function) or page.evaluate(
        "() => document.scripts.length === 0"
    )
    count = _count_matches(matches, selector, settled, request.timeout_ms)
    _wait_until_visible(matches, selector, count, settled)
    if not request.multiple and count != 1:
        raise ValueError(f"selector {selector!r} must match one element; matched {count}")
    return [matches.nth(index) for index in range(count)]


def _count_matches(matches: Any, selector: str, settled: bool, timeout_ms: int) -> int:
    """Count the matches, first giving a page that still runs scripts time to add one."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    if matches.count() == 0 and not settled:
        with suppress(PlaywrightTimeoutError):
            matches.first.wait_for(state="attached")
    count = matches.count()
    if count == 0:
        raise ValueError(_no_match_message(selector, settled, timeout_ms))
    return count


def _wait_until_visible(matches: Any, selector: str, count: int, settled: bool) -> None:
    """Wait for the first match to show, or explain that it has no visible size."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    try:
        if settled and not matches.first.is_visible():
            raise PlaywrightTimeoutError("not visible")
        matches.first.wait_for(state="visible")
    except PlaywrightTimeoutError as exc:
        raise ValueError(
            f"selector {selector!r} matches {count} element(s), but the first is "
            "not visible (display:none, visibility:hidden or zero size). Give "
            'each captured element a size, e.g. style="width:1280px;height:720px"'
        ) from exc


def _capture_target(page: Any, target: Any, index: int, request: _CaptureRequest) -> HtmlCapture:
    """Wait for one element's images and fonts, then photograph it and read its text."""
    if request.selector is not None:
        target.scroll_into_view_if_needed()
    target.evaluate(_READY, request.timeout_ms)
    if request.check_overflow and target.evaluate(
        "el => el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1"
    ):
        raise ValueError(
            f"HTML section {index + 1} overflows its container; resize it, shorten "
            "the content, or set check_overflow=False for intentional overflow"
        )
    text = target.inner_text().strip()
    title = _title(target, text)
    png = _screenshot(page, target, request)
    reference = None
    elements: tuple[dict[str, Any], ...] = ()
    size = None
    if request.hybrid:
        reference, size = png, _visible_size(target)
        elements, png = _lift_layers(target, request.timeout_ms, request.omit_background)
    exported = _exported(page, request.export_script)
    return HtmlCapture(png, title.strip(), text, exported, elements, reference, size)


def _title(target: Any, text: str) -> str:
    """Name a capture by data-title, aria-label, its first heading, or its text."""
    title = target.get_attribute("data-title") or target.get_attribute("aria-label")
    if title:
        return title
    headings = target.locator("h1, h2, h3")
    return headings.first.inner_text() if headings.count() else text[:120]


def _screenshot(page: Any, target: Any, request: _CaptureRequest) -> bytes:
    """Photograph the viewport (or the whole page), or else the selected element."""
    if request.selector is None:
        return page.screenshot(
            full_page=request.full_page,
            type="png",
            animations="disabled",
            caret="hide",
            omit_background=request.omit_background,
        )
    return _element_screenshot(target, request.omit_background)


def _element_screenshot(target: Any, omit_background: bool) -> bytes:
    return target.screenshot(
        type="png",
        animations="disabled",
        caret="hide",
        omit_background=omit_background,
    )


def _visible_size(target: Any) -> tuple[float, float]:
    """The element's rendered size in CSS pixels."""
    bounds = target.bounding_box()
    if bounds is None:
        raise ValueError("HTML slide has no visible bounds")
    return (bounds["width"], bounds["height"])


def _lift_layers(
    target: Any, timeout_ms: int, omit_background: bool
) -> tuple[tuple[dict[str, Any], ...], bytes]:
    """Record the element's native layers, then photograph it without them.

    The element is restored afterwards whether or not the photograph succeeds.
    """
    from power_pptx.design._html_layers import capture_layers, restore_layers

    elements, original = capture_layers(target, timeout_ms=timeout_ms)
    try:
        png = _element_screenshot(target, omit_background)
    finally:
        restore_layers(target, original)
    return elements, png


def _exported(page: Any, export_script: str | None) -> str | None:
    """Run *export_script* in the page; it must return a string or nothing."""
    exported = page.evaluate(export_script) if export_script else None
    if exported is not None and not isinstance(exported, str):
        raise ValueError("HTML export_script must return a string")
    return exported


def _no_match_message(selector: str, settled: bool, timeout_ms: int) -> str:
    """Explain that *selector* matched nothing and what the document needs."""
    message = f"no element matches the selector {selector!r}, so there is nothing to capture. "
    if selector == "[data-slide]":
        message += (
            "Each slide is one element carrying the data-slide attribute — for example "
            '<section data-slide style="width:1280px;height:720px">…</section> — or pass '
            "selector=None to capture the viewport as a single slide."
        )
    else:
        message += "Check the selector, or pass selector=None to capture the whole viewport."
    if not settled:
        message += (
            f" (Waited {timeout_ms} ms for a script to add it; if the page builds its "
            "content later, pass wait_for_function.)"
        )
    return message


def _block_network(context: Any, source_url: str | None, blocked: list[str]) -> None:
    """Abort every request from *context* that would leave the capture.

    Allowed: URLs whose content is already in the page (``data:``, ``blob:``,
    ``about:``) and the capture's own loopback document origin. Everything
    else is aborted and its URL appended to *blocked*.
    """
    origin = None
    if source_url is not None:
        parts = urlsplit(source_url)
        origin = f"{parts.scheme}://{parts.netloc}"

    def is_local(url: str) -> bool:
        if urlsplit(url).scheme.lower() in _LOCAL_SCHEMES:
            return True
        return origin is not None and (url == origin or url.startswith(origin + "/"))

    def handle(route: Any) -> None:
        url = route.request.url
        if is_local(url):
            route.continue_()
        else:
            blocked.append(url)
            route.abort("blockedbyclient")

    def close_socket(socket: Any) -> None:
        blocked.append(socket.url)
        socket.close()

    context.route("**/*", handle)
    # Playwright 1.48+. It only improves the report: whether or not the
    # attempt is seen here, the socket has nowhere to connect to.
    if hasattr(context, "route_web_socket"):
        context.route_web_socket("**/*", close_socket)


@contextmanager
def _refused_port() -> Iterator[int]:
    """Hold a loopback port that refuses every connection while it is held.

    The socket is bound but never listens, so a connection attempt is
    rejected at once, and no other process can start listening there.
    """
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        holder.bind(("127.0.0.1", 0))
        yield holder.getsockname()[1]
    finally:
        holder.close()


def _offline_arguments(refused_port: int, source_url: str | None) -> list[str]:
    """Return Chromium arguments that leave the browser no route out.

    Request routing only sees what the page asks for over HTTP. These
    arguments close the rest at the network layer: all traffic is sent to a
    proxy address that refuses connections, with the capture's own document
    server as the single exception; host names are never resolved, so nothing
    can leak through DNS; and WebRTC may not send UDP around the proxy.
    """
    bypass = "<-loopback>"  # without it Chromium exempts every loopback address
    if source_url is not None:
        bypass += f";{urlsplit(source_url).netloc}"
    return [
        f"--proxy-server=http://127.0.0.1:{refused_port}",
        f"--proxy-bypass-list={bypass}",
        "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
        "--webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--force-webrtc-ip-handling-policy",
    ]


def _network_blocked(blocked: list[str]) -> ValueError:
    """Return the error for a capture that tried to use the network."""
    urls = list(dict.fromkeys(blocked))
    shown = ", ".join(url if len(url) <= 200 else url[:197] + "..." for url in urls[:5])
    more = f" and {len(urls) - 5} more" if len(urls) > 5 else ""
    return ValueError(
        f"HTML capture blocked {len(urls)} request(s) because allow_network=False: "
        f"{shown}{more}. Inline what the document needs (data: URLs, <style>, <script>), "
        "or capture with allow_network=True if you trust the document."
    )


class _DocumentHandler(SimpleHTTPRequestHandler):
    """Serve the files that live under one directory, and nothing else.

    ``SimpleHTTPRequestHandler`` already keeps ``..`` inside its directory,
    but it follows symlinks out of it and lists any directory that has no
    index page. A captured page can run scripts, so both would let it read
    files its author was never given: this handler answers 404 for a
    directory and for anything whose real path is outside the root.
    """

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    def list_directory(self, path: Any) -> None:
        self.send_error(404, "File not found")
        return None

    def send_head(self) -> Any:
        root = os.path.realpath(self.directory)
        target = os.path.realpath(self.translate_path(self.path))
        try:
            inside = os.path.commonpath([root, target]) == root
        except ValueError:  # different drives on Windows
            inside = False
        if not inside or not os.path.isfile(target):
            self.send_error(404, "File not found")
            return None
        return super().send_head()


@contextmanager
def _serve_html(path: Path) -> Iterator[str]:
    """Serve only the document directory on an ephemeral loopback port."""
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(_DocumentHandler, directory=str(path.parent))
    )
    thread = Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/{quote(path.name)}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
