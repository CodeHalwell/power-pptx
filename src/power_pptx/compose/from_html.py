"""Compose a presentation from styled HTML sections using browser capture."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from power_pptx.design._html import HtmlSource, capture_html

if TYPE_CHECKING:
    from power_pptx.presentation import Presentation


def from_html(
    html: HtmlSource,
    *,
    selector: str | None = "[data-slide]",
    slide_size: Any = "16:9",
    viewport: tuple[int, int] = (1280, 720),
    device_scale_factor: float = 2.0,
    fit: str = "contain",
    include_notes: bool = True,
    check_overflow: bool = True,
    wait_until: str = "load",
    wait_for_function: str | None = None,
    timeout_ms: int = 15000,
    browser_path: str | None = None,
    mode: str = "capture",
    font_map: dict[str, str] | None = None,
    strict_fonts: bool = True,
    reference_dir: str | os.PathLike[str] | None = None,
) -> Presentation:
    """Return a deck with one browser-rendered picture per HTML section.

    Accepts markup, UTF-8 bytes, or a local HTML path (relative assets work).
    Matching elements are captured in DOM order using one browser session.
    Use fixed-size sections, e.g. ``<section data-slide style="width:1280px;
    height:720px">...``. ``selector=None`` makes one viewport slide.

    Captures preserve CSS, inline SVG, and browser-rendered charts as static
    images. They do not become editable PowerPoint text/shapes. Visible text
    is copied into speaker notes by default, with a title/alt text on each
    picture. Native overlays can be added to the returned presentation.

    ``slide_size`` accepts the same shorthands/dimensions as ``from_spec``.
    ``fit`` defaults to aspect-preserving containment; use ``cover`` to crop
    or ``stretch`` explicitly. Container overflow raises by default.

    Requires ``pip install 'power-pptx[html]'`` and
    ``python -m playwright install chromium``.

    ``mode="hybrid"`` converts explicit ``data-pptx="text|chart|table"``
    regions into editable native objects and captures ``data-pptx="capture"``
    regions separately. Unmarked CSS remains a background image. Charts use
    a ``data-pptx-chart`` JSON data specification. Regions cannot be nested;
    DOM order and explicit z-index order the foreground layers. This is an
    annotation contract, not an arbitrary CSS-to-DrawingML converter.
    Hybrid mode requires contain fitting and installed native fonts; use
    ``font_map`` for deliberate substitutions. ``reference_dir`` writes each
    original browser view as ``slide-00.png`` etc. for review comparisons.
    """
    from power_pptx import Presentation
    from power_pptx.compose.from_spec import _apply_slide_size
    from power_pptx.design.figures import _embed_html_png
    from power_pptx.util import Emu

    if fit not in {"contain", "cover", "stretch"}:
        raise ValueError("fit must be 'contain', 'cover', or 'stretch'")
    if mode not in {"capture", "hybrid"}:
        raise ValueError("mode must be 'capture' or 'hybrid'")
    if mode == "hybrid" and (fit != "contain" or selector is None):
        raise ValueError("hybrid mode requires fit='contain' and a section selector")
    prs = Presentation()
    _apply_slide_size(prs, slide_size)
    capture_options: dict[str, Any] = {"hybrid": True} if mode == "hybrid" else {}
    captures = capture_html(
        html,
        selector=selector,
        multiple=True,
        viewport=viewport,
        device_scale_factor=device_scale_factor,
        check_overflow=check_overflow,
        wait_until=wait_until,
        wait_for_function=wait_for_function,
        timeout_ms=timeout_ms,
        browser_path=browser_path,
        **capture_options,
    )
    if mode == "hybrid":
        from power_pptx.compose._hybrid import prepare_layers

        for capture in captures:
            prepare_layers(capture, font_map=font_map or {}, strict_fonts=strict_fonts)
    for index, capture in enumerate(captures):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        picture = _embed_html_png(
            slide,
            capture.png,
            Emu(0),
            Emu(0),
            prs.slide_width,
            prs.slide_height,
            fit=fit,
            device_scale_factor=device_scale_factor,
        )
        picture.name = capture.title or f"HTML slide {index + 1}"
        picture.alt_text = capture.text or capture.title
        if mode == "hybrid":
            from power_pptx.compose._hybrid import add_layers

            # Only background/child overlap is licensed; native foreground
            # regions keep their independent collision checks.
            add_layers(slide, capture, slide_width=prs.slide_width, slide_height=prs.slide_height)
            for child in list(slide.shapes)[1:]:
                picture.allow_overlap_with(child)
        if include_notes:
            notes = slide.notes_slide.notes_text_frame
            if notes is not None:
                notes.text = capture.text
    if reference_dir is not None:
        target = Path(reference_dir)
        target.mkdir(parents=True, exist_ok=True)
        for index, capture in enumerate(captures):
            (target / f"slide-{index:02d}.png").write_bytes(capture.reference_png or capture.png)
    return prs
