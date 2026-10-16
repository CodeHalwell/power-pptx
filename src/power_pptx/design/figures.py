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
import json
import math
import os
from typing import IO, TYPE_CHECKING, Any, Optional, Tuple, Union
from urllib.parse import unquote_to_bytes

from PIL import Image

from power_pptx.design._html import HtmlSource, capture_html
from power_pptx.util import Emu, Inches

if TYPE_CHECKING:
    from power_pptx.shapes.picture import Picture
    from power_pptx.slide import Slide
    from power_pptx.util import Length


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
    backend: str = "auto",
    browser_path: str | os.PathLike[str] | None = None,
    timeout_ms: int = 15000,
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

    ``backend="auto"`` first uses Kaleido, then falls back to Playwright
    when export fails and the figure supports ``to_html``. ``"kaleido"``
    disables fallback; ``"browser"`` uses self-contained Plotly HTML and
    requires ``power-pptx[html]`` plus Chromium. Browser SVG export includes
    a browser-rendered PNG companion and needs no CairoSVG. Explicit formats
    are respected by both backends. Browser readiness waits for Plotly's
    post-render callback, decoded images, and fonts.
    """
    if backend not in {"auto", "kaleido", "browser"}:
        raise ValueError("backend must be 'auto', 'kaleido', or 'browser'")
    if format not in {"auto", "png", "svg"}:
        raise ValueError("format must be 'auto', 'png', or 'svg'")
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("scale must be finite and positive")
    for value in (width_px, height_px):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
        ):
            raise ValueError("width_px and height_px must be positive integers")
    failure = None
    if backend != "browser":
        try:
            blob, fmt = _plotly_to_blob(
                figure,
                format=format,
                scale=scale,
                width_px=width_px,
                height_px=height_px,
            )
        except FigureBackendUnavailable as exc:
            if backend == "kaleido" or not callable(getattr(figure, "to_html", None)):
                raise
            failure = exc
        else:
            return _embed_blob(slide, blob, fmt, left, top, width, height)
    try:
        capture, logical_width, logical_height = _plotly_browser_capture(
            figure,
            format=format,
            scale=scale,
            width_px=width_px,
            height_px=height_px,
            browser_path=browser_path,
            timeout_ms=timeout_ms,
        )
    except Exception as exc:
        if failure is not None:
            raise FigureBackendUnavailable(
                f"Plotly export failed with both backends. Kaleido: {failure}. Browser: {exc}"
            ) from exc
        if isinstance(exc, (TypeError, ValueError, FigureBackendUnavailable)):
            raise
        raise FigureBackendUnavailable(f"Plotly browser export failed: {exc}") from exc
    if capture.exported is not None:
        if not capture.exported.startswith("data:image/svg+xml,"):
            raise FigureBackendUnavailable("Plotly browser did not return an SVG data URL")
        svg = unquote_to_bytes(capture.exported.partition(",")[2])
        if width is None and height is None:
            width = Inches(logical_width / 96)
            height = Inches(logical_height / 96)
        return slide.shapes.add_svg_picture(
            svg,
            left,
            top,
            width,
            height,
            png_fallback=capture.png,
        )
    return _embed_html_png(
        slide,
        capture.png,
        left,
        top,
        width,
        height,
        fit="contain",
        device_scale_factor=scale,
    )


def _plotly_browser_capture(
    figure,
    *,
    format,
    scale,
    width_px,
    height_px,
    browser_path,
    timeout_ms,
):
    if not callable(getattr(figure, "to_html", None)):
        raise TypeError("Plotly browser backend requires a Plotly Figure exposing to_html()")
    layout = figure.to_plotly_json().get("layout", {})
    w = width_px or layout.get("width") or 700
    h = height_px or layout.get("height") or 450
    if any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 1
        for v in (w, h)
    ):
        raise ValueError("Plotly layout dimensions must be positive numbers")
    w, h = round(w), round(h)
    markup = figure.to_html(
        include_plotlyjs=True,
        full_html=True,
        div_id="power-pptx-plot",
        default_width=w,
        default_height=h,
        config={"displayModeBar": False, "responsive": False},
        post_script=(
            "const powerPptxPlot = document.getElementById('power-pptx-plot');"
            f"powerPptxPlot.style.width = '{w}px';powerPptxPlot.style.height = '{h}px';"
            "Plotly.relayout(powerPptxPlot, "
            + json.dumps({"width": w, "height": h})
            + ").then(() => {window.powerPptxPlotReady = true})"
        ),
    )
    if not isinstance(markup, str):
        raise TypeError("Plotly to_html() must return HTML text")
    markup = markup.replace("<head>", "<head><style>body{margin:0}</style>", 1)
    export_script = None
    if format != "png":
        options = json.dumps({"format": "svg", "width": w, "height": h})
        export_script = (
            "async () => await Plotly.toImage(document.getElementById('power-pptx-plot'), "
            + options
            + ")"
        )
    capture = capture_html(
        markup,
        viewport=(w, h),
        selector="#power-pptx-plot",
        device_scale_factor=scale,
        wait_for_function="window.powerPptxPlotReady === true",
        browser_path=browser_path,
        timeout_ms=timeout_ms,
        export_script=export_script,
    )[0]
    return capture, w, h


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
                "plotly kaleido`); the underlying error was: %s" % (exc,)
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
    """Embed an arbitrary SVG (markup, path, file-like, or bytes) on *slide*.

    Thin wrapper over :meth:`ShapeTree.add_svg_picture` — useful as the
    same-shape entry point alongside :func:`add_plotly_figure` /
    :func:`add_matplotlib_figure` so authoring code can route every
    figure kind through the ``power_pptx.design.figures`` module.

    When *png_fallback* is omitted the SVG is rasterised via
    ``cairosvg`` for the Office SVG-extension PNG companion.
    """
    return slide.shapes.add_svg_picture(svg, left, top, width, height, png_fallback=png_fallback)


# ---------------------------------------------------------------------------
# HTML (headless browser proxy)
# ---------------------------------------------------------------------------


def add_html_figure(
    slide: "Slide",
    html: HtmlSource,
    left: Length,
    top: Length,
    width: Optional[Length] = None,
    height: Optional[Length] = None,
    *,
    viewport: Tuple[int, int] = (1280, 720),
    device_scale_factor: float = 2.0,
    wait_until: str = "load",
    full_page: bool = False,
    timeout_ms: int = 15000,
    selector: str | None = None,
    wait_for_function: str | None = None,
    omit_background: bool = False,
    browser_path: str | os.PathLike[str] | None = None,
    fit: str = "contain",
) -> "Picture":
    """Render an HTML snippet to a screenshot via Playwright and embed it.

    PowerPoint has no HTML-rendering surface.  This adapter screenshots
    the rendered DOM in a headless Chromium and embeds the PNG —
    suitable for diagrams from web-based tools (Mermaid, D3, Vega-Lite
    via mini-HTML wrappers, branded layouts) that don't have a direct
    image export.

    *html* may be raw markup, UTF-8 ``bytes``, or a local ``.html`` path.
    File inputs preserve relative CSS, font, and image paths. External
    URLs (``<img src="https://...">``) are loaded as long as the
    process has network access.

    *viewport* sizes the headless browser canvas in CSS pixels;
    *device_scale_factor* renders at the equivalent of a retina
    display by default for crisper text.  *full_page=True* captures
    the entire scroll height instead of just the viewport — useful
    when the rendered content overflows.

    *selector* captures one matching element rather than the viewport.
    Images are decoded and web fonts are ready before capture; use
    *wait_for_function* for asynchronous chart/application readiness.
    CSS animations are disabled in the screenshot. *omit_background*
    preserves transparency. *browser_path* (or ``POWER_PPTX_CHROMIUM``)
    selects an installed Chromium instead of Playwright's managed browser.

    *fit* is ``"contain"`` (preserve aspect ratio inside the requested box),
    ``"cover"`` (crop to fill it), or ``"stretch"``. Without geometry,
    native size uses 96 CSS pixels per inch, independent of capture density.

    Requires ``playwright`` and a browser install::

        pip install playwright
        playwright install chromium
    """
    if fit not in {"contain", "cover", "stretch"}:
        raise ValueError("fit must be 'contain', 'cover', or 'stretch'")
    blob = _html_to_png(
        html,
        viewport=viewport,
        device_scale_factor=device_scale_factor,
        wait_until=wait_until,
        full_page=full_page,
        timeout_ms=timeout_ms,
        selector=selector,
        wait_for_function=wait_for_function,
        omit_background=omit_background,
        browser_path=browser_path,
    )
    return _embed_html_png(
        slide,
        blob,
        left,
        top,
        width,
        height,
        fit=fit,
        device_scale_factor=device_scale_factor,
    )


def _html_to_png(
    html: HtmlSource,
    *,
    viewport: Tuple[int, int],
    device_scale_factor: float,
    wait_until: str,
    full_page: bool,
    timeout_ms: int,
    selector: str | None = None,
    wait_for_function: str | None = None,
    omit_background: bool = False,
    browser_path: str | os.PathLike[str] | None = None,
) -> bytes:
    return capture_html(
        html,
        viewport=viewport,
        device_scale_factor=device_scale_factor,
        wait_until=wait_until,
        full_page=full_page,
        timeout_ms=timeout_ms,
        selector=selector,
        wait_for_function=wait_for_function,
        omit_background=omit_background,
        browser_path=browser_path,
    )[0].png


def _embed_html_png(
    slide: "Slide",
    blob: bytes,
    left: "Length",
    top: "Length",
    width: "Length | None",
    height: "Length | None",
    *,
    fit: str,
    device_scale_factor: float,
) -> "Picture":
    """Place browser pixels with consistent physical sizing and aspect ratio."""
    if fit not in {"contain", "cover", "stretch"}:
        raise ValueError("fit must be 'contain', 'cover', or 'stretch'")
    with Image.open(io.BytesIO(blob)) as image:
        px_w, px_h = image.size
    if width is None:
        if height is None:
            width = Inches(px_w / device_scale_factor / 96)
            height = Inches(px_h / device_scale_factor / 96)
        else:
            width = Emu(round(height * px_w / px_h))
    if height is None:
        height = Emu(round(width * px_h / px_w))
    if width <= 0 or height <= 0:
        raise ValueError("HTML figure width and height must be positive")

    if fit == "contain":
        scale = min(width / px_w, height / px_h)
        actual_w, actual_h = Emu(round(px_w * scale)), Emu(round(px_h * scale))
        left = Emu(round(left + (width - actual_w) / 2))
        top = Emu(round(top + (height - actual_h) / 2))
        width, height = actual_w, actual_h
    picture = slide.shapes.add_picture(io.BytesIO(blob), left, top, width, height)
    if fit == "cover":
        image_ratio, box_ratio = px_w / px_h, width / height
        if image_ratio > box_ratio:
            picture.crop_left = picture.crop_right = (1 - box_ratio / image_ratio) / 2
        else:
            picture.crop_top = picture.crop_bottom = (1 - image_ratio / box_ratio) / 2
    return picture


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
        return slide.shapes.add_svg_picture(blob, left, top, width, height)
    return slide.shapes.add_picture(io.BytesIO(blob), left, top, width=width, height=height)


def _resolve_format(format: str) -> str:
    """Return ``"svg"`` or ``"png"`` based on *format* and cairosvg availability."""
    if format not in ("auto", "svg", "png"):
        raise ValueError(f"format must be 'auto', 'svg', or 'png'; got {format!r}")
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
