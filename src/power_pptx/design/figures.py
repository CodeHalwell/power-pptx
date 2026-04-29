"""Figure / plot embedding for slides — Plotly, Matplotlib, SVG, HTML.

PowerPoint can't render Plotly traces, Matplotlib axes, or HTML
documents directly: every external visualisation has to land on a
slide as a static image (PNG / SVG via Office's SVG extension) or, for
HTML, as a screenshot.  This module owns those conversion paths so
recipes and authoring code don't have to re-derive them.

Every adapter is **optional**: the third-party libraries the adapters
need are imported lazily, and missing dependencies surface a clear
``ImportError`` naming the right install command rather than a deep
stack trace from inside the integration.

Public functions
----------------

* :func:`add_plotly_figure` — render a Plotly ``Figure`` and embed it.
* :func:`add_matplotlib_figure` — render a Matplotlib ``Figure`` and embed it.
* :func:`add_svg_figure` — embed any SVG markup (path, file-like, or bytes).
* :func:`add_html_figure` — render an HTML snippet via headless Playwright
  and embed the screenshot.

Each returns the embedded :class:`~power_pptx.shapes.picture.Picture` shape.

Quick install matrix
~~~~~~~~~~~~~~~~~~~~

* Plotly  → ``pip install plotly kaleido``
* Plotly with SVG output → also ``pip install cairosvg``
* Matplotlib → ``pip install matplotlib``
* HTML → ``pip install playwright && playwright install chromium``
"""

from __future__ import annotations

import io
import os
from typing import IO, TYPE_CHECKING, Any, Optional, Tuple, Union

from power_pptx.util import Length

if TYPE_CHECKING:
    from power_pptx.shapes.picture import Picture
    from power_pptx.slide import Slide


PathOrFile = Union[str, "os.PathLike[str]", IO[bytes], bytes]


__all__ = (
    "add_plotly_figure",
    "add_matplotlib_figure",
    "add_svg_figure",
    "add_html_figure",
    "FigureBackendUnavailable",
)


class FigureBackendUnavailable(ImportError):
    """Raised when an optional figure-rendering dependency is missing.

    Subclasses :class:`ImportError` so callers can still catch it via
    ``except ImportError`` while letting code that knows about the
    figure pipeline distinguish a missing-dep failure from any other
    import error.
    """


# ---------------------------------------------------------------------------
# Plotly
# ---------------------------------------------------------------------------


def add_plotly_figure(
    slide: "Slide",
    figure: Any,
    left: Length,
    top: Length,
    width: Optional[Length] = None,
    height: Optional[Length] = None,
    *,
    format: str = "auto",
    scale: float = 2.0,
    width_px: Optional[int] = None,
    height_px: Optional[int] = None,
) -> "Picture":
    """Render a Plotly ``Figure`` and embed the result on *slide*.

    *figure* is a ``plotly.graph_objects.Figure`` (or anything that
    exposes a ``.to_image(format=...)`` method, which is the public
    plotly contract).  *left* / *top* / *width* / *height* are slide
    coordinates; if *width* / *height* are omitted the picture's
    rendered size determines them, exactly like
    :meth:`ShapeTree.add_picture`.

    *format* picks the embedded image format:

    * ``"svg"`` — vector, sharpest at any zoom; embedded via Office's
      SVG extension with a PNG fallback (requires ``cairosvg``).
    * ``"png"`` — raster, no extra dependencies beyond ``kaleido``.
    * ``"auto"`` (default) — SVG when ``cairosvg`` is available, PNG
      otherwise.

    *scale* scales raster output to higher pixel density (2.0 ≈ retina).
    *width_px* / *height_px* override the renderer's pixel canvas; by
    default Plotly's own layout sizing wins.

    Requires ``plotly`` and ``kaleido``::

        pip install plotly kaleido
    """
    blob, fmt = _plotly_to_blob(
        figure, format=format, scale=scale,
        width_px=width_px, height_px=height_px,
    )
    return _embed_blob(slide, blob, fmt, left, top, width, height)


def _plotly_to_blob(
    figure: Any,
    *,
    format: str,
    scale: float,
    width_px: Optional[int],
    height_px: Optional[int],
) -> Tuple[bytes, str]:
    if not hasattr(figure, "to_image"):
        raise TypeError(
            "add_plotly_figure expects a Plotly Figure (or an object "
            "exposing .to_image(format=...)); got "
            f"{type(figure).__name__!r}.  If you have a dict spec, wrap "
            "it with plotly.graph_objects.Figure(spec) first."
        )

    fmt = _resolve_format(format)
    if fmt == "svg":
        try:
            blob = figure.to_image(
                format="svg",
                scale=scale,
                width=width_px,
                height=height_px,
            )
        except Exception as exc:
            raise FigureBackendUnavailable(
                "Plotly figure → SVG export failed.  Ensure both "
                "`plotly` and `kaleido` are installed (`pip install "
                "plotly kaleido`); the underlying error was: %s"
                % (exc,)
            ) from exc
        return blob, "svg"

    try:
        blob = figure.to_image(
            format="png",
            scale=scale,
            width=width_px,
            height=height_px,
        )
    except Exception as exc:
        raise FigureBackendUnavailable(
            "Plotly figure → PNG export failed.  Ensure both `plotly` "
            "and `kaleido` are installed (`pip install plotly kaleido`); "
            "the underlying error was: %s" % (exc,)
        ) from exc
    return blob, "png"


# ---------------------------------------------------------------------------
# Matplotlib
# ---------------------------------------------------------------------------


def add_matplotlib_figure(
    slide: "Slide",
    figure: Any,
    left: Length,
    top: Length,
    width: Optional[Length] = None,
    height: Optional[Length] = None,
    *,
    format: str = "auto",
    dpi: int = 200,
) -> "Picture":
    """Render a Matplotlib ``Figure`` and embed the result on *slide*.

    *figure* is a ``matplotlib.figure.Figure`` (or anything with a
    ``.savefig(buf, format=...)`` method).  Geometry args mirror
    :func:`add_plotly_figure`.

    *format* picks the embedded image format:

    * ``"svg"`` — vector, sharpest at zoom; needs ``cairosvg`` for the
      PNG fallback (Office's SVG extension requires both).
    * ``"png"`` — raster only.
    * ``"auto"`` (default) — SVG when ``cairosvg`` is available, PNG
      otherwise.

    *dpi* applies to PNG output only; SVG is resolution-independent.

    Requires ``matplotlib``::

        pip install matplotlib
    """
    if not hasattr(figure, "savefig"):
        raise TypeError(
            "add_matplotlib_figure expects a Matplotlib Figure (or an "
            "object exposing .savefig); got "
            f"{type(figure).__name__!r}."
        )

    fmt = _resolve_format(format)
    buf = io.BytesIO()
    try:
        if fmt == "svg":
            figure.savefig(buf, format="svg", bbox_inches="tight")
        else:
            figure.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    except ImportError as exc:  # pragma: no cover - defensive
        raise FigureBackendUnavailable(
            "matplotlib not installed; `pip install matplotlib`."
        ) from exc
    return _embed_blob(slide, buf.getvalue(), fmt, left, top, width, height)


# ---------------------------------------------------------------------------
# SVG (any source)
# ---------------------------------------------------------------------------


def add_svg_figure(
    slide: "Slide",
    svg: PathOrFile,
    left: Length,
    top: Length,
    width: Optional[Length] = None,
    height: Optional[Length] = None,
    *,
    png_fallback: Optional[PathOrFile] = None,
) -> "Picture":
    """Embed an arbitrary SVG (path, file-like, or bytes) on *slide*.

    Thin wrapper over :meth:`ShapeTree.add_svg_picture` — useful as the
    same-shape entry point alongside :func:`add_plotly_figure` /
    :func:`add_matplotlib_figure` so authoring code can route every
    figure kind through the ``power_pptx.design.figures`` module.

    When *png_fallback* is omitted the SVG is rasterised via
    ``cairosvg`` for the Office SVG-extension PNG companion.
    """
    return slide.shapes.add_svg_picture(
        svg, left, top, width, height, png_fallback=png_fallback
    )


# ---------------------------------------------------------------------------
# HTML (headless browser proxy)
# ---------------------------------------------------------------------------


def add_html_figure(
    slide: "Slide",
    html: Union[str, bytes],
    left: Length,
    top: Length,
    width: Optional[Length] = None,
    height: Optional[Length] = None,
    *,
    viewport: Tuple[int, int] = (1280, 720),
    device_scale_factor: float = 2.0,
    wait_until: str = "networkidle",
    full_page: bool = False,
    timeout_ms: int = 15000,
) -> "Picture":
    """Render an HTML snippet to a screenshot via Playwright and embed it.

    PowerPoint has no HTML-rendering surface.  This adapter screenshots
    the rendered DOM in a headless Chromium and embeds the PNG —
    suitable for diagrams from web-based tools (Mermaid, D3, Vega-Lite
    via mini-HTML wrappers, branded layouts) that don't have a direct
    image export.

    *html* may be raw markup or already-encoded ``bytes``.  External
    URLs (``<img src="https://...">``) are loaded as long as the
    process has network access.

    *viewport* sizes the headless browser canvas in CSS pixels;
    *device_scale_factor* renders at the equivalent of a retina
    display by default for crisper text.  *full_page=True* captures
    the entire scroll height instead of just the viewport — useful
    when the rendered content overflows.

    Requires ``playwright`` and a browser install::

        pip install playwright
        playwright install chromium
    """
    blob = _html_to_png(
        html,
        viewport=viewport,
        device_scale_factor=device_scale_factor,
        wait_until=wait_until,
        full_page=full_page,
        timeout_ms=timeout_ms,
    )
    return _embed_blob(slide, blob, "png", left, top, width, height)


def _html_to_png(
    html: Union[str, bytes],
    *,
    viewport: Tuple[int, int],
    device_scale_factor: float,
    wait_until: str,
    full_page: bool,
    timeout_ms: int,
) -> bytes:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except ImportError as exc:
        raise FigureBackendUnavailable(
            "HTML rendering needs Playwright; install with "
            "`pip install playwright && playwright install chromium`."
        ) from exc

    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as exc:
            raise FigureBackendUnavailable(
                "Playwright failed to launch Chromium.  Did you run "
                "`playwright install chromium`?  Original error: %s"
                % (exc,)
            ) from exc
        try:
            page = browser.new_page(
                viewport={"width": viewport[0], "height": viewport[1]},
                device_scale_factor=device_scale_factor,
            )
            page.set_default_timeout(timeout_ms)
            page.set_content(html, wait_until=wait_until)
            return page.screenshot(full_page=full_page, type="png")
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Internal: embed a blob (PNG or SVG) using the right shapetree path.
# ---------------------------------------------------------------------------


def _embed_blob(
    slide: "Slide",
    blob: bytes,
    fmt: str,
    left: Length,
    top: Length,
    width: Optional[Length],
    height: Optional[Length],
) -> "Picture":
    if fmt == "svg":
        return slide.shapes.add_svg_picture(
            blob, left, top, width, height
        )
    return slide.shapes.add_picture(
        io.BytesIO(blob), left, top, width=width, height=height
    )


def _resolve_format(format: str) -> str:
    """Return ``"svg"`` or ``"png"`` based on *format* and cairosvg availability."""
    if format not in ("auto", "svg", "png"):
        raise ValueError(
            f"format must be 'auto', 'svg', or 'png'; got {format!r}"
        )
    if format == "auto":
        # SVG is the visual win when both halves of the Office SVG
        # extension can be produced — i.e. when cairosvg is installed
        # to rasterise the PNG fallback.  Fall back to PNG otherwise
        # so callers without cairosvg still get a working picture.
        try:
            import cairosvg  # type: ignore[import-not-found]  # noqa: F401
        except ImportError:
            return "png"
        return "svg"
    return format
