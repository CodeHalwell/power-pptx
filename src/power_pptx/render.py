"""Slide thumbnail rendering via a headless LibreOffice/soffice shell-out.

PowerPoint's own renderer is the only pixel-perfect option for a deck;
since this library deliberately runs without PowerPoint, the next-best
practical option is to drive LibreOffice in headless mode.  That's what
:func:`render_slide_thumbnails` (and the convenience methods on
:class:`~power_pptx.api.Presentation` and ``Slide``) do: save the deck to a
temporary file, ask ``soffice --headless --convert-to png`` to render
each slide, and return the resulting paths (or PNG bytes).

This is an *optional* feature with no hard dependency: callers must have
``soffice`` (LibreOffice) on ``PATH``.  When it isn't available the
functions raise :class:`ThumbnailRendererUnavailable` with an actionable
hint so the failure mode is obvious.

Two rendering strategies are supported, tried in order:

1. ``soffice --convert-to png`` — fast, single subprocess, but stock
   LibreOffice 7+ only emits the *first* slide of a multi-slide deck
   when targeting PNG directly.  We accept this output only when the
   number of PNGs produced matches the slide count.

2. ``soffice --convert-to pdf`` followed by per-page PDF→PNG split —
   reliable across LibreOffice versions because the PDF export always
   includes every slide.  The split prefers ``pdftoppm`` (Poppler,
   ubiquitous on Linux/macOS), then ``pypdfium2`` if installed.

Callers can force a specific strategy with ``strategy="png"`` or
``strategy="pdf"``; the default ``"auto"`` tries PNG first and falls
back to PDF on a slide-count mismatch.

The shell-out is deliberately quarantined to a single small module so
the rest of the library never depends on subprocess or LibreOffice.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import IO, TYPE_CHECKING, Iterable, List, Optional, Sequence, Union

if TYPE_CHECKING:
    from power_pptx.api import Presentation as _Presentation
    from power_pptx.slide import Slide as _Slide

DEFAULT_SOFFICE_BIN = "soffice"
DEFAULT_TIMEOUT_SECONDS = 120


class ThumbnailRendererUnavailable(RuntimeError):
    """Raised when LibreOffice/soffice is not available on PATH.

    The message includes an install hint so callers can route users to
    a working configuration without grepping documentation.
    """


class ThumbnailRendererError(RuntimeError):
    """Raised when LibreOffice runs but produces no output (or errors)."""


def _resolve_binary(binary: Optional[str]) -> str:
    candidate = binary or os.environ.get("POWER_PPTX_SOFFICE") or DEFAULT_SOFFICE_BIN
    resolved = shutil.which(candidate)
    if resolved is None:
        raise ThumbnailRendererUnavailable(
            "could not locate %r on PATH; install LibreOffice (provides the "
            "`soffice` binary) or set POWER_PPTX_SOFFICE to the absolute path "
            "of a compatible binary." % candidate
        )
    return resolved


def _save_to_path(prs, path: Path) -> None:
    prs.save(str(path))


def _run_soffice(
    soffice_bin: str,
    deck_path: Path,
    out_dir: Path,
    timeout: int,
) -> subprocess.CompletedProcess:
    """Convert *deck_path* to PNG using ``soffice --convert-to png``.

    Stock LibreOffice 7+ writes only the first slide for a multi-slide
    deck through this filter; older builds (and a handful of forks) write
    one PNG per slide.  Callers are responsible for verifying the output
    count matches the slide count and falling back to the PDF path when
    it doesn't.
    """
    cmd = [
        soffice_bin,
        "--headless",
        "--norestore",
        "--nologo",
        "--nofirststartwizard",
        "--convert-to",
        "png",
        "--outdir",
        str(out_dir),
        str(deck_path),
    ]
    return subprocess.run(
        cmd,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _run_soffice_pdf(
    soffice_bin: str,
    deck_path: Path,
    out_dir: Path,
    timeout: int,
) -> subprocess.CompletedProcess:
    """Convert *deck_path* to PDF using ``soffice --convert-to pdf``.

    Unlike the PNG filter, the PDF export reliably contains every slide
    on every LibreOffice version we've tested, which makes it the
    authoritative source for per-slide thumbnails.
    """
    cmd = [
        soffice_bin,
        "--headless",
        "--norestore",
        "--nologo",
        "--nofirststartwizard",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(deck_path),
    ]
    return subprocess.run(
        cmd,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def render_slide_thumbnails(
    prs: "_Presentation",
    *,
    out_dir: Optional[Union[str, os.PathLike[str]]] = None,
    slide_indexes: Optional[Sequence[int]] = None,
    soffice_bin: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    return_bytes: bool = False,
    strategy: str = "auto",
    dpi: int = 150,
) -> Union[List[Path], List[bytes]]:
    """Render slide thumbnails for `prs` via headless LibreOffice.

    `out_dir` is the directory to write PNGs into; if ``None``, a
    temporary directory is used and the returned paths point inside it
    (the caller is responsible for cleanup).  When ``return_bytes=True``
    the function reads each PNG into memory and returns ``bytes``
    objects instead, deleting the temporary directory before returning.

    `slide_indexes` is a 0-based list of slide indexes to return; when
    ``None``, all slides are returned in deck order.

    `strategy` controls which LibreOffice export pipeline is used:

    * ``"auto"`` (default) — try ``--convert-to png`` first; if it emits
      fewer PNGs than the slide count (typical of stock LibreOffice 7+,
      which only writes the first slide), fall back to PDF + per-page
      split.
    * ``"png"`` — only the PNG path; raises :class:`ThumbnailRendererError`
      when LibreOffice produces fewer than one PNG per slide.
    * ``"pdf"`` — skip the PNG path entirely and always go through PDF +
      per-page split.

    `dpi` controls the PDF→PNG raster resolution (150 DPI by default —
    a reasonable balance between fidelity and file size).  Ignored on
    the PNG-only path.

    Raises :class:`ThumbnailRendererUnavailable` when ``soffice`` cannot
    be located, and :class:`ThumbnailRendererError` when the conversion
    completes with no PNG output (typically a corrupted deck or a
    LibreOffice version that doesn't ship the PNG filter).
    """
    if strategy not in ("auto", "png", "pdf"):
        raise ValueError(
            f"strategy must be 'auto', 'png', or 'pdf'; got {strategy!r}"
        )

    bin_path = _resolve_binary(soffice_bin)

    cleanup_tmp = out_dir is None
    work_dir = Path(out_dir) if out_dir is not None else Path(tempfile.mkdtemp(prefix="pptx-thumbs-"))
    work_dir.mkdir(parents=True, exist_ok=True)

    expected_slide_count = len(list(prs.slides))

    try:
        deck_path = work_dir / "_render_input.pptx"
        _save_to_path(prs, deck_path)

        png_paths: List[Path] = []

        if strategy in ("auto", "png"):
            png_paths = _render_via_png(
                bin_path, deck_path, work_dir, timeout
            )
            if strategy == "png" and len(png_paths) < expected_slide_count:
                raise ThumbnailRendererError(
                    "soffice --convert-to png emitted %d PNG(s) for a "
                    "%d-slide deck.  Most LibreOffice 7+ builds only write "
                    "the first slide via the PNG filter; pass "
                    "strategy='auto' or 'pdf' to use the PDF-split fallback."
                    % (len(png_paths), expected_slide_count)
                )

        # Auto-fallback: PNG path didn't produce one image per slide.
        if strategy == "pdf" or (
            strategy == "auto" and len(png_paths) < expected_slide_count
        ):
            # Clean up partial PNG output from the auto-mode first attempt
            # so we don't confuse the slide-index lookup.
            for stale in png_paths:
                try:
                    stale.unlink()
                except OSError:
                    pass
            png_paths = _render_via_pdf(
                bin_path, deck_path, work_dir, timeout, dpi=dpi
            )

        if not png_paths:
            raise ThumbnailRendererError(
                "no PNG output produced by either the PNG or PDF rendering "
                "pipeline.  Verify LibreOffice can convert this deck "
                "(`soffice --convert-to pdf <deck>.pptx`); the PDF-split "
                "fallback also requires `pdftoppm` (Poppler) or `pypdfium2`."
            )

        if slide_indexes is not None:
            wanted = list(slide_indexes)
            png_paths = _select_indexes(png_paths, wanted)

        if return_bytes:
            data = [p.read_bytes() for p in png_paths]
            return data
        return list(png_paths)
    finally:
        if cleanup_tmp and return_bytes:
            shutil.rmtree(work_dir, ignore_errors=True)


def _render_via_png(
    bin_path: str, deck_path: Path, work_dir: Path, timeout: int
) -> List[Path]:
    """Run the soffice PNG filter and return the produced PNG paths."""
    # Snapshot any PNGs already in `work_dir` so we can later subtract
    # them from the result set.  Otherwise, when a caller points
    # `out_dir=` at a non-empty directory (a shared artifacts folder, a
    # cache, …) stray PNGs get treated as slide renders and corrupt
    # `slide_indexes` lookups / out-of-range errors.
    preexisting_pngs = {p.name for p in work_dir.glob("*.png")}

    result = _run_soffice(bin_path, deck_path, work_dir, timeout)
    if result.returncode != 0:
        raise ThumbnailRendererError(
            "soffice exited with status %d: %s"
            % (result.returncode, (result.stderr or b"").decode("utf-8", "replace"))
        )

    png_paths = sorted(
        (
            p
            for p in work_dir.glob("*.png")
            if p.name != deck_path.name and p.name not in preexisting_pngs
        ),
        key=_natural_sort_key,
    )
    return png_paths


def _render_via_pdf(
    bin_path: str, deck_path: Path, work_dir: Path, timeout: int, *, dpi: int
) -> List[Path]:
    """Run the soffice PDF filter, then split each PDF page into a PNG.

    Splits prefer the ``pdftoppm`` binary (Poppler) since it's a single
    subprocess and ubiquitous on Linux/macOS; ``pypdfium2`` is the
    pure-Python fallback when callers can't depend on Poppler.
    """
    # Snapshot existing PDFs so a stale one in a shared work_dir doesn't
    # get treated as our output.
    preexisting_pdfs = {p.name for p in work_dir.glob("*.pdf")}

    result = _run_soffice_pdf(bin_path, deck_path, work_dir, timeout)
    if result.returncode != 0:
        raise ThumbnailRendererError(
            "soffice --convert-to pdf exited with status %d: %s"
            % (result.returncode, (result.stderr or b"").decode("utf-8", "replace"))
        )

    pdfs = [
        p for p in work_dir.glob("*.pdf")
        if p.name not in preexisting_pdfs
    ]
    if not pdfs:
        raise ThumbnailRendererError(
            "soffice --convert-to pdf produced no PDF output; "
            "ensure your LibreOffice build includes the PDF export filter."
        )

    pdf_path = pdfs[0]
    try:
        return _pdf_to_pngs(pdf_path, work_dir, dpi=dpi)
    finally:
        try:
            pdf_path.unlink()
        except OSError:
            pass


def _pdf_to_pngs(pdf_path: Path, out_dir: Path, *, dpi: int) -> List[Path]:
    """Split a PDF into one PNG per page in *out_dir* and return the paths.

    Tries ``pdftoppm`` first (Poppler), then ``pypdfium2``.  Raises
    :class:`ThumbnailRendererError` with an install hint when neither is
    available — the message names both options so the user can pick
    whichever fits their environment.
    """
    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm is not None:
        return _pdf_to_pngs_via_pdftoppm(pdftoppm, pdf_path, out_dir, dpi=dpi)

    try:
        import pypdfium2  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        raise ThumbnailRendererError(
            "PDF-split fallback needs either `pdftoppm` (install Poppler: "
            "`apt install poppler-utils` / `brew install poppler`) or the "
            "`pypdfium2` Python package (`pip install pypdfium2`); neither "
            "is available."
        )
    return _pdf_to_pngs_via_pypdfium2(pdf_path, out_dir, dpi=dpi)


def _pdf_to_pngs_via_pdftoppm(
    pdftoppm: str, pdf_path: Path, out_dir: Path, *, dpi: int
) -> List[Path]:
    prefix = pdf_path.stem + "-page"
    cmd = [
        pdftoppm,
        "-png",
        "-r",
        str(int(dpi)),
        str(pdf_path),
        str(out_dir / prefix),
    ]
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        raise ThumbnailRendererError(
            "pdftoppm exited with status %d: %s"
            % (result.returncode, (result.stderr or b"").decode("utf-8", "replace"))
        )
    pages = sorted(
        out_dir.glob(prefix + "-*.png"), key=_natural_sort_key
    )
    return pages


def _pdf_to_pngs_via_pypdfium2(
    pdf_path: Path, out_dir: Path, *, dpi: int
) -> List[Path]:
    import pypdfium2 as pdfium  # type: ignore[import-not-found]

    scale = float(dpi) / 72.0  # pypdfium2 uses 1.0 == 72 DPI
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        pages: List[Path] = []
        prefix = pdf_path.stem + "-page"
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                bitmap = page.render(scale=scale)
                pil_image = bitmap.to_pil()
                # 1-based numbering matches pdftoppm's convention so the
                # natural-sort key produces the same order.
                target = out_dir / f"{prefix}-{i + 1}.png"
                pil_image.save(str(target), format="PNG")
                pages.append(target)
            finally:
                # pypdfium2 page handles need explicit close to avoid
                # holding the underlying PDF mapping open.
                page.close()
        return pages
    finally:
        pdf.close()


_NATURAL_SORT_RE = re.compile(r"(\d+)")


def _natural_sort_key(path: Path):
    """Return a sort key that treats embedded digit runs as integers.

    LibreOffice writes one PNG per slide with the slide index appended to
    the basename — e.g. ``deck-1.png``, ``deck-2.png``, …, ``deck-10.png``.
    Plain lexicographic sorting puts ``deck-10.png`` before ``deck-2.png``,
    which silently scrambles ``slide_indexes=`` lookups for any deck with
    ten or more slides.  Splitting the name into alternating
    text / int chunks gives the human-intuitive ordering.
    """
    parts = _NATURAL_SORT_RE.split(path.name)
    return tuple((int(p) if p.isdigit() else p) for p in parts)


def _select_indexes(paths: Sequence[Path], indexes: Iterable[int]) -> List[Path]:
    selected = []
    for i in indexes:
        if i < 0 or i >= len(paths):
            raise IndexError(
                "slide index %d out of range for deck with %d slides"
                % (i, len(paths))
            )
        selected.append(paths[i])
    return selected


def render_slide_thumbnail(
    slide: "_Slide",
    *,
    out_path: Optional[Union[str, os.PathLike[str]]] = None,
    soffice_bin: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    return_bytes: bool = False,
    strategy: str = "auto",
    dpi: int = 150,
) -> Union[Path, bytes]:
    """Render a single slide to PNG.

    The slide must belong to a :class:`Presentation` whose ``save()``
    will produce a complete deck on disk.  Internally this calls
    :func:`render_slide_thumbnails` against a private temporary
    directory; that directory is always cleaned up before this
    function returns, regardless of which return mode is selected:

    * ``return_bytes=True``  — returns PNG ``bytes``; temp dir removed.
    * ``out_path=...``       — returns the destination ``Path``; temp dir removed.
    * neither                — returns a stable ``Path`` to a small
      ``NamedTemporaryFile`` PNG (``delete=False``).  The bigger temp
      directory holding the saved deck is cleaned up; the caller owns
      cleanup of the returned PNG file.

    *strategy* and *dpi* mirror the same arguments on
    :func:`render_slide_thumbnails`.
    """
    prs = _presentation_for(slide)
    idx = list(prs.slides).index(slide)

    if return_bytes:
        # `render_slide_thumbnails` cleans up its own temp dir when
        # `return_bytes=True`, so no extra wrapping is needed here.
        data = render_slide_thumbnails(
            prs,
            slide_indexes=[idx],
            soffice_bin=soffice_bin,
            timeout=timeout,
            return_bytes=True,
            strategy=strategy,
            dpi=dpi,
        )
        return data[0]

    # Otherwise, control the temp dir ourselves so we can copy the PNG
    # out and remove the directory (which also holds the saved deck).
    with tempfile.TemporaryDirectory(prefix="pptx-thumb-") as tmp:
        paths = render_slide_thumbnails(
            prs,
            slide_indexes=[idx],
            out_dir=tmp,
            soffice_bin=soffice_bin,
            timeout=timeout,
            strategy=strategy,
            dpi=dpi,
        )
        src = paths[0]
        if out_path is not None:
            target = Path(out_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target)
            return target
        # No destination given: persist the single PNG to a stable
        # tempfile so the returned path remains valid after the
        # `TemporaryDirectory` context exits.
        fd, persistent = tempfile.mkstemp(prefix="pptx-thumb-", suffix=".png")
        os.close(fd)
        shutil.copyfile(src, persistent)
        return Path(persistent)


def render_slides(
    prs: "_Presentation",
    *,
    out_dir: Optional[Union[str, os.PathLike[str]]] = None,
    slides: Optional[Sequence[int]] = None,
    name_template: Optional[str] = None,
    soffice_bin: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    return_bytes: bool = False,
    strategy: str = "auto",
    dpi: int = 150,
    scale: Optional[float] = None,
) -> Union[List[Path], List[bytes]]:
    """Render slide thumbnails — friendlier wrapper around :func:`render_slide_thumbnails`.

    Same semantics as :func:`render_slide_thumbnails` but with two
    quality-of-life additions:

    * ``slides=`` (cleaner name than ``slide_indexes=``).
    * ``name_template=`` — a ``str.format``-able template like
      ``"slide-{:02d}.png"`` applied to the rendered PNGs.  Index is
      0-based.  Defaults to LibreOffice's own ``"_render_input-page-NN"``
      output if omitted.
    * ``scale=`` is accepted and translated to ``dpi=`` (``scale=0.5``
      ≙ ``dpi=72``).
    """
    if scale is not None:
        dpi = max(int(72 * float(scale)), 36)
    # Validate name_template *before* rendering — a template without a
    # format placeholder would rename every slide to the same filename
    # and silently overwrite all but the last PNG.
    if name_template is not None and not return_bytes:
        try:
            sample_a = name_template.format(0)
            sample_b = name_template.format(1)
        except (IndexError, ValueError, KeyError) as exc:
            raise ValueError(
                f"name_template {name_template!r} is not a valid str.format "
                "template (expected one positional placeholder like "
                "'slide-{:02d}.png'): " + str(exc)
            ) from exc
        if sample_a == sample_b:
            raise ValueError(
                f"name_template {name_template!r} produces the same filename "
                "for every slide — include a positional placeholder such as "
                "'slide-{:02d}.png' so each PNG gets a unique name."
            )
    paths = render_slide_thumbnails(
        prs,
        out_dir=out_dir,
        slide_indexes=slides,
        soffice_bin=soffice_bin,
        timeout=timeout,
        return_bytes=return_bytes,
        strategy=strategy,
        dpi=dpi,
    )
    if return_bytes or name_template is None:
        return paths
    # ``paths`` here is List[Path].
    renamed: list[Path] = []
    if slides is None:
        index_iter: list[int] = list(range(len(paths)))
    else:
        index_iter = list(slides)
    for idx, p in zip(index_iter, paths):
        new_name = name_template.format(idx)
        target = p.parent / new_name
        if p != target:
            shutil.move(str(p), str(target))
        renamed.append(target)
    return renamed


def _presentation_for(slide: "_Slide") -> "_Presentation":
    """Walk back from a Slide to its owning Presentation.

    ``Slide.part.package.presentation_part.presentation`` is the canonical
    accessor; we go through ``part`` to avoid importing Presentation here
    (would cause a circular import on `power_pptx.api`).
    """
    return slide.part.package.presentation_part.presentation
