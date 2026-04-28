"""Slide thumbnail rendering via a headless LibreOffice/soffice shell-out.

PowerPoint's own renderer is the only pixel-perfect option for a deck;
since this library deliberately runs without PowerPoint, the next-best
practical option is to drive LibreOffice in headless mode.  That's what
:func:`render_slide_thumbnails` (and the convenience methods on
:class:`~pptx.api.Presentation` and ``Slide``) do: save the deck to a
temporary file, ask ``soffice --headless --convert-to png`` to render
each slide, and return the resulting paths (or PNG bytes).

This is an *optional* feature with no hard dependency: callers must have
``soffice`` (LibreOffice) on ``PATH``.  When it isn't available the
functions raise :class:`ThumbnailRendererUnavailable` with an actionable
hint so the failure mode is obvious.

The current implementation shells out with plain ``--convert-to png``
and relies on LibreOffice to emit PNG files for the presentation —
typically one per slide named ``<deck>-<index>.png``, though the exact
naming and per-slide vs. first-slide-only behavior varies between
LibreOffice versions.  When callers request a specific slide via
``slide_indexes=``, the renderer still converts the whole deck and
filters the generated files in Python rather than asking ``soffice``
for a slide-range export; that's deliberately simple and matches the
broadest version compatibility.

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
    from pptx.api import Presentation as _Presentation
    from pptx.slide import Slide as _Slide

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


def render_slide_thumbnails(
    prs: "_Presentation",
    *,
    out_dir: Optional[Union[str, os.PathLike[str]]] = None,
    slide_indexes: Optional[Sequence[int]] = None,
    soffice_bin: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    return_bytes: bool = False,
) -> Union[List[Path], List[bytes]]:
    """Render slide thumbnails for `prs` via headless LibreOffice.

    `out_dir` is the directory to write PNGs into; if ``None``, a
    temporary directory is used and the returned paths point inside it
    (the caller is responsible for cleanup).  When ``return_bytes=True``
    the function reads each PNG into memory and returns ``bytes``
    objects instead, deleting the temporary directory before returning.

    `slide_indexes` is a 0-based list of slide indexes to return; when
    ``None``, all slides are returned in deck order.  LibreOffice always
    renders the *whole* deck (it has no per-slide convert mode that
    works reliably across versions), so this filter is applied to the
    output paths after the conversion.

    Raises :class:`ThumbnailRendererUnavailable` when ``soffice`` cannot
    be located, and :class:`ThumbnailRendererError` when the conversion
    completes with no PNG output (typically a corrupted deck or a
    LibreOffice version that doesn't ship the PNG filter).
    """
    bin_path = _resolve_binary(soffice_bin)

    cleanup_tmp = out_dir is None
    work_dir = Path(out_dir) if out_dir is not None else Path(tempfile.mkdtemp(prefix="pptx-thumbs-"))
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        deck_path = work_dir / "_render_input.pptx"
        _save_to_path(prs, deck_path)

        # Snapshot any PNGs already in `work_dir` so we can later
        # subtract them from the result set.  Otherwise, when a caller
        # points `out_dir=` at a non-empty directory (a shared artifacts
        # folder, a cache, …) stray PNGs get treated as slide renders
        # and corrupt `slide_indexes` lookups / out-of-range errors.
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
        if not png_paths:
            raise ThumbnailRendererError(
                "soffice produced no PNG output; ensure your LibreOffice "
                "build includes the `impress_png_Export` filter."
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


def _presentation_for(slide: "_Slide") -> "_Presentation":
    """Walk back from a Slide to its owning Presentation.

    ``Slide.part.package.presentation_part.presentation`` is the canonical
    accessor; we go through ``part`` to avoid importing Presentation here
    (would cause a circular import on `pptx.api`).
    """
    return slide.part.package.presentation_part.presentation
