"""Slide thumbnail rendering via a headless LibreOffice/soffice shell-out.

PowerPoint's own renderer is the only pixel-perfect option for a deck;
since this library deliberately runs without PowerPoint, the next-best
practical option is to drive LibreOffice in headless mode.  That's what
:func:`render_slide_thumbnails` (and the convenience methods on
:class:`~power_pptx.api.Presentation` and ``Slide``) do: save the deck to a
temporary file, ask headless ``soffice`` to convert it, and return one
PNG per slide as paths (or PNG bytes).

This is an *optional* feature with no hard dependency: callers must have
LibreOffice installed, found as ``soffice`` or ``libreoffice`` on ``PATH`` or
named by ``soffice_bin`` / ``POWER_PPTX_SOFFICE``.  When it isn't available the
functions raise :class:`ThumbnailRendererUnavailable` with an actionable
hint so the failure mode is obvious.

Two rendering strategies are supported:

1. ``soffice --convert-to pdf`` followed by per-page PDF→PNG split —
   reliable across LibreOffice versions because the PDF export includes
   every slide (hidden ones when asked, which we do), and the only one
   that honours ``dpi=``.  The split prefers ``pdftoppm`` (Poppler,
   ubiquitous on Linux/macOS), then ``pypdfium2`` if installed.

2. ``soffice --convert-to png`` — a single subprocess with nothing else
   to install, but stock LibreOffice 7+ only emits the *first* slide of
   a multi-slide deck when targeting PNG directly, at a size LibreOffice
   chooses.  We accept this output only when the number of PNGs
   produced matches the slide count.

Callers can force a specific strategy with ``strategy="pdf"`` or
``strategy="png"``; the default ``"auto"`` uses PDF, and PNG only when
neither ``pdftoppm`` nor ``pypdfium2`` is available to split a PDF.

The shell-out is deliberately quarantined to a single small module so
the rest of the library never depends on subprocess or LibreOffice.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import zipfile
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Sequence, Union, cast

if TYPE_CHECKING:
    from power_pptx.presentation import Presentation as _Presentation
    from power_pptx.slide import Slide as _Slide

DEFAULT_SOFFICE_BIN = "soffice"
DEFAULT_TIMEOUT_SECONDS = 120

#: Names looked up on ``PATH``, in order, when the caller names no binary.
#: Some installs provide only ``libreoffice``.
_SOFFICE_BIN_NAMES = (DEFAULT_SOFFICE_BIN, "libreoffice")

#: Stem of the deck saved for conversion, and so of every PNG made from it.
_RENDER_STEM = "_render_input"

#: ``--convert-to`` target that makes the PDF export include hidden slides
#: (``<p:sld show="0">``), which LibreOffice leaves out by default.  The JSON
#: filter options need LibreOffice 7.4 or later; an older build ignores them
#: and exports the visible slides only.
_PDF_WITH_HIDDEN_SLIDES = (
    'pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}'
)


class ThumbnailRendererUnavailable(RuntimeError):
    """Raised when LibreOffice (``soffice`` or ``libreoffice``) cannot be found.

    The message includes an install hint so callers can route users to
    a working configuration without grepping documentation.
    """


class ThumbnailRendererError(RuntimeError):
    """Raised when LibreOffice runs but produces no output, errors or times out."""


def _resolve_binary(binary: Optional[str]) -> str:
    """Return the path of the LibreOffice binary to run.

    *binary*, then ``POWER_PPTX_SOFFICE``, names it explicitly.  Otherwise
    the first of ``soffice`` and ``libreoffice`` found on ``PATH`` is used.
    """
    explicit = binary or os.environ.get("POWER_PPTX_SOFFICE")
    for candidate in (explicit,) if explicit else _SOFFICE_BIN_NAMES:
        resolved = shutil.which(candidate)
        if resolved is not None:
            return resolved
    raise ThumbnailRendererUnavailable(
        "could not locate %r on PATH; install LibreOffice (provides the "
        "`soffice` binary) or set POWER_PPTX_SOFFICE to the absolute path "
        "of a compatible binary." % (explicit or DEFAULT_SOFFICE_BIN)
    )


def _save_to_path(prs, path: Path) -> None:
    prs.save(str(path))


#: System fontconfig files a generated ``fonts.conf`` includes when
#: ``FONTCONFIG_FILE`` isn't already set (Linux, then Homebrew on Apple
#: silicon and Intel). Missing files are ignored by fontconfig.
_SYSTEM_FONTCONFIG_FILES = (
    "/etc/fonts/fonts.conf",
    "/opt/homebrew/etc/fonts/fonts.conf",
    "/usr/local/etc/fonts/fonts.conf",
)


def _soffice_env(
    work_dir: Path, font_dirs: Optional[Iterable[Union[str, os.PathLike[str]]]] = None
) -> Optional[dict]:
    """Return an environment that points LibreOffice's fontconfig at extra folders.

    Combines *font_dirs* with folders registered through
    :func:`power_pptx.text.register_font_dir` / ``POWER_PPTX_FONT_DIRS``.
    Writes a ``fonts.conf`` in *work_dir* that includes the system
    configuration, the operating-system font folders (LibreOffice's bundled
    fontconfig on macOS doesn't search ``~/Library/Fonts``) and the extra
    folders. Returns ``None`` when there is nothing to add, so the subprocess
    inherits the caller's environment unchanged.
    """
    from xml.sax.saxutils import escape

    from power_pptx.text.fonts import FontFiles, registered_font_dirs, registered_font_files

    extra: list[str] = []
    for directory in font_dirs or ():
        path = os.path.abspath(os.fspath(directory))
        if not os.path.isdir(path):
            raise ValueError(f"Font directory {path!r} does not exist")
        extra.append(path)
    extra.extend(registered_font_dirs())
    files = registered_font_files()
    if files:
        # -- register_font_family files, without the rest of their folders --
        copies = work_dir / ".fontconfig" / "files"
        copies.mkdir(parents=True, exist_ok=True)
        for number, font_file in enumerate(files):
            shutil.copyfile(font_file, copies / f"{number}-{os.path.basename(font_file)}")
        extra.append(str(copies))
    extra = list(dict.fromkeys(extra))
    if not extra:
        return None
    current = os.environ.get("FONTCONFIG_FILE")
    includes = [current] if current else list(_SYSTEM_FONTCONFIG_FILES)
    system_dirs = [
        d
        for d in FontFiles._font_directories()  # pyright: ignore[reportPrivateUsage]
        if os.path.isdir(d)
    ]
    conf_dir = work_dir / ".fontconfig"
    conf_dir.mkdir(parents=True, exist_ok=True)
    lines = ['<?xml version="1.0"?>', '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">', "<fontconfig>"]
    lines += [f'  <include ignore_missing="yes">{escape(f)}</include>' for f in includes]
    lines += [f"  <dir>{escape(d)}</dir>" for d in dict.fromkeys([*system_dirs, *extra])]
    lines += [f"  <cachedir>{escape(str(conf_dir / 'cache'))}</cachedir>", "</fontconfig>"]
    conf = conf_dir / "fonts.conf"
    conf.write_text("\n".join(lines) + "\n", encoding="utf-8")
    env = dict(os.environ)
    env["FONTCONFIG_FILE"] = str(conf)
    return env


def _kill_process_tree(process: "subprocess.Popen[bytes]") -> None:
    """Stop *process* and every process it started.

    ``soffice`` is only a launcher (a shell script on Linux and macOS,
    ``soffice.exe`` on Windows) for the real ``soffice.bin``, so killing the
    one process we started would leave the converter running.
    """
    if sys.platform == "win32":
        with suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
                timeout=30,
            )
    else:
        # -- the process leads its own group; see `start_new_session` in `_run` --
        with suppress(OSError):
            os.killpg(process.pid, signal.SIGKILL)
    with suppress(OSError):
        process.kill()


def _run(
    cmd: Sequence[str], *, timeout: float, env: Optional[dict] = None
) -> "subprocess.CompletedProcess[bytes]":
    """Run *cmd* to completion and return its result, never leaving it running.

    The command gets its own session, hence its own process group, so the
    whole group can be stopped when it overruns *timeout* (seconds) or the
    caller is interrupted.  A timeout raises :class:`ThumbnailRendererError`.
    """
    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        start_new_session=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_tree(process)
            raise ThumbnailRendererError(
                "%s did not finish within %s seconds and was stopped; pass a "
                "larger timeout= if the deck needs longer to convert."
                % (Path(cmd[0]).name, timeout)
            ) from None
        except BaseException:
            _kill_process_tree(process)
            raise
    return subprocess.CompletedProcess(list(cmd), process.returncode, stdout, stderr)


# -- Settings for the profile LibreOffice is started with. `BlockUntrustedRefererLinks`
# -- stops it loading what a document links to rather than contains, such as a picture
# -- whose relationship is `TargetMode="External"` with a `file:///` target, which it
# -- would otherwise read from disk and draw. Macros are never wanted when converting.
_PROFILE_SETTINGS = """\
<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry"\
 xmlns:xs="http://www.w3.org/2001/XMLSchema"\
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting">\
<prop oor:name="BlockUntrustedRefererLinks" oor:op="fuse"><value>true</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting">\
<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting">\
<prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop></item>
</oor:items>
"""


def _seed_profile(profile: Path) -> None:
    """Write the settings LibreOffice is to start with into its (new) *profile* directory."""
    settings = profile / "user" / "registrymodifications.xcu"
    if settings.exists():
        return
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(_PROFILE_SETTINGS, encoding="utf-8")


def _neutralise_deck(deck_path: Path) -> None:
    """Rewrite the SVG pictures in the deck at *deck_path* so they draw from themselves alone.

    LibreOffice draws an embedded SVG from the SVG itself, and follows the
    references in it: ``<image href="file:///...">`` puts that file in the
    rendered slide. The profile setting that stops linked pictures does not
    cover this, so the references are removed from the copy being rendered.
    A deck with no SVG in it, or one that is not a zip archive, is left alone.
    """
    from power_pptx._svg import neutralise_external_references

    try:
        with zipfile.ZipFile(deck_path) as package:
            svg_names = {m.filename for m in package.infolist() if _holds_svg(package, m)}
            if not svg_names:
                return
            contents = [(m.filename, package.read(m)) for m in package.infolist()]
    except (OSError, zipfile.BadZipFile):
        return
    with zipfile.ZipFile(deck_path, "w", zipfile.ZIP_DEFLATED) as package:
        for name, data in contents:
            if name in svg_names:
                data = neutralise_external_references(data)
            package.writestr(name, data)


def _holds_svg(package: zipfile.ZipFile, member: zipfile.ZipInfo) -> bool:
    """True when *member* of *package* may be an SVG, whatever its name says.

    A renderer goes by content, so a deck can carry an SVG under any name. The
    package's own XML (parts and relationships) is not a picture and is left.
    """
    name = member.filename.lower()
    if name.endswith(".svg"):
        return True
    if name.endswith((".xml", ".rels")):
        return False
    try:
        with package.open(member) as stream:
            head = stream.read(4096)
    except (OSError, RuntimeError, NotImplementedError, zipfile.BadZipFile):
        return False
    return b"<svg" in head.lower() or head.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<")


def _soffice_convert(
    soffice_bin: str,
    deck_path: Path,
    out_dir: Path,
    timeout: float,
    env: Optional[dict],
    target: str,
) -> "subprocess.CompletedProcess[bytes]":
    """Run ``soffice --convert-to <target>`` on *deck_path*, writing into *out_dir*.

    *deck_path* is the renderer's own temporary copy of the deck. Before
    LibreOffice sees it, what would make LibreOffice read other files is taken
    out of it (see :func:`_neutralise_deck`), and the throwaway profile it runs
    with is told not to follow links (see :func:`_seed_profile`): a deck may
    come from anywhere, and rendering it must not draw the host's files into
    the output.
    """
    profile = out_dir / ".soffice-profile"
    _seed_profile(profile)
    _neutralise_deck(deck_path)
    cmd = [
        soffice_bin,
        "-env:UserInstallation=" + profile.resolve().as_uri(),
        "--headless",
        "--norestore",
        "--nologo",
        "--nofirststartwizard",
        "--convert-to",
        target,
        "--outdir",
        str(out_dir),
        str(deck_path),
    ]
    return _run(cmd, timeout=timeout, env=env)


def _run_soffice(
    soffice_bin: str,
    deck_path: Path,
    out_dir: Path,
    timeout: float,
    env: Optional[dict] = None,
) -> "subprocess.CompletedProcess[bytes]":
    """Convert *deck_path* to PNG using ``soffice --convert-to png``.

    Stock LibreOffice 7+ writes only the first slide for a multi-slide
    deck through this filter; older builds (and a handful of forks) write
    one PNG per slide.  Callers are responsible for verifying the output
    count matches the slide count.
    """
    return _soffice_convert(soffice_bin, deck_path, out_dir, timeout, env, "png")


def _run_soffice_pdf(
    soffice_bin: str,
    deck_path: Path,
    out_dir: Path,
    timeout: float,
    env: Optional[dict] = None,
    *,
    hidden_slides: bool = False,
) -> "subprocess.CompletedProcess[bytes]":
    """Convert *deck_path* to PDF using ``soffice --convert-to pdf``.

    Unlike the PNG filter, the PDF export reliably contains every slide
    on every LibreOffice version we've tested, which makes it the
    authoritative source for per-slide thumbnails.  It leaves hidden
    slides out unless *hidden_slides* asks for them; pass it only for a
    deck that has some, so other decks convert exactly as before.
    """
    target = _PDF_WITH_HIDDEN_SLIDES if hidden_slides else "pdf"
    return _soffice_convert(soffice_bin, deck_path, out_dir, timeout, env, target)


def _pdf_rasteriser_available() -> bool:
    """True when a PDF can be split into PNGs here (``pdftoppm`` or ``pypdfium2``)."""
    return shutil.which("pdftoppm") is not None or importlib.util.find_spec("pypdfium2") is not None


def _output_name(slide_index: int, slide_count: int) -> str:
    """Return the file name for a slide's PNG: ``_render_input-page-N.png``.

    N is the 1-based slide number, zero-padded to the width of the slide
    count.  That is what ``pdftoppm`` writes, so a slide's file name depends
    on the deck alone, not on the pipeline that happened to render it.
    """
    return "%s-page-%0*d.png" % (_RENDER_STEM, len(str(slide_count)), slide_index + 1)


def _hidden_slide_indexes(prs: "_Presentation") -> List[int]:
    """Return the 0-based indexes of the slides marked hidden (``show="0"``)."""
    return [
        index
        for index, slide in enumerate(prs.slides)
        if slide.element.get("show") in ("0", "false")
    ]


def _pages_by_slide(
    pages: Sequence[Path], slide_count: int, hidden: Sequence[int]
) -> Dict[int, Path]:
    """Map rendered *pages*, in deck order, onto 0-based slide indexes.

    Normally there is one page per slide.  A LibreOffice that leaves hidden
    slides out of its export although asked for them (before 7.4) produces
    one page per *visible* slide; those are matched to the slides they show,
    so an index never points at a neighbouring slide's image.  Any other
    count is an error.
    """
    if len(pages) == slide_count:
        return dict(enumerate(pages))
    hidden_indexes = set(hidden)
    visible = [index for index in range(slide_count) if index not in hidden_indexes]
    if hidden and len(pages) == len(visible):
        return dict(zip(visible, pages))
    raise ThumbnailRendererError(
        "rendering emitted %d PNG(s) for a %d-slide deck" % (len(pages), slide_count)
    )


def _select_pages(pages: Dict[int, Path], indexes: Iterable[int], slide_count: int) -> List[Path]:
    """Return the page for each 0-based slide index in *indexes*, in that order."""
    selected = []
    for index in indexes:
        if index < 0 or index >= slide_count:
            raise IndexError(
                "slide index %d out of range for deck with %d slides" % (index, slide_count)
            )
        if index not in pages:
            raise ThumbnailRendererError(
                "slide %d (index %d) is hidden and this LibreOffice left hidden "
                "slides out of its export; LibreOffice 7.4 or later includes "
                "them.  Unhide the slide, or pass slide_indexes= naming only "
                "visible slides." % (index + 1, index)
            )
        selected.append(pages[index])
    return selected


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
    font_dirs: Optional[Sequence[Union[str, os.PathLike[str]]]] = None,
) -> Union[List[Path], List[bytes]]:
    """Render slide thumbnails for `prs` via headless LibreOffice.

    `out_dir` is the directory to write PNGs into; if ``None``, a
    temporary output directory is used (the caller is responsible for
    cleanup). Conversion always happens in a separate private workspace,
    so repeated calls never include stale images from ``out_dir``.
    When ``return_bytes=True``, only PNG bytes are returned; no output
    files are copied and the workspace is removed before returning.

    `slide_indexes` is a 0-based list of slide indexes to return; when
    ``None``, all slides are returned in deck order.  Hidden slides count
    and are rendered like any other, so an index always means the slide
    at that position in ``prs.slides``.

    `strategy` controls which LibreOffice export pipeline is used:

    * ``"auto"`` (default) — PDF + per-page split.  Only when neither
      ``pdftoppm`` nor ``pypdfium2`` is available to split a PDF is
      ``--convert-to png`` used instead; stock LibreOffice 7+ writes just
      the first slide that way, so it then serves one-slide decks only.
    * ``"pdf"`` — always go through PDF + per-page split.
    * ``"png"`` — only the PNG path; raises :class:`ThumbnailRendererError`
      when LibreOffice produces fewer than one PNG per slide.

    `dpi` controls the PDF→PNG raster resolution (150 DPI by default —
    a reasonable balance between fidelity and file size).  The PNG path
    ignores it and renders at a size LibreOffice chooses.

    Files are named ``_render_input-page-N.png``, N being the 1-based
    slide number zero-padded to the width of the slide count, whichever
    strategy rendered them.

    `font_dirs` lists extra font folders LibreOffice should use, on top of
    folders registered with :func:`power_pptx.text.register_font_dir` or
    ``POWER_PPTX_FONT_DIRS`` (which are always passed through). They're set
    through a temporary ``fonts.conf`` for the ``soffice`` subprocess only.

    `timeout` is how many seconds each external process (the LibreOffice
    conversion, then the PDF split) may take.  One that overruns is
    stopped, along with every process it started.

    Raises :class:`ThumbnailRendererUnavailable` when ``soffice`` cannot
    be located, and :class:`ThumbnailRendererError` when the conversion
    times out or completes with no PNG output (typically a corrupted deck
    or a LibreOffice version that doesn't ship the PNG filter).
    """
    if strategy not in ("auto", "png", "pdf"):
        raise ValueError(f"strategy must be 'auto', 'png', or 'pdf'; got {strategy!r}")

    bin_path = _resolve_binary(soffice_bin)

    expected_slide_count = len(list(prs.slides))
    hidden = _hidden_slide_indexes(prs)
    # -- PDF is the pipeline of choice: every slide, at the requested `dpi`.
    # -- The PNG filter is used unasked only when nothing can split a PDF. --
    use_pdf = strategy == "pdf" or (strategy == "auto" and _pdf_rasteriser_available())

    with tempfile.TemporaryDirectory(prefix="pptx-render-") as tmp:
        work_dir = Path(tmp)
        deck_path = work_dir / (_RENDER_STEM + ".pptx")
        _save_to_path(prs, deck_path)
        env = _soffice_env(work_dir, font_dirs)

        if use_pdf:
            png_paths = _render_via_pdf(
                bin_path,
                deck_path,
                work_dir,
                timeout,
                dpi=dpi,
                env=env,
                hidden_slides=bool(hidden),
            )
        else:
            png_paths = _render_via_png(bin_path, deck_path, work_dir, timeout, env=env)
            if len(png_paths) != expected_slide_count:
                remedy = (
                    "pass strategy='auto' or 'pdf' to render through PDF instead."
                    if strategy == "png"
                    else "install `pdftoppm` (Poppler) or the `pypdfium2` package "
                    "so the slides can be rendered through PDF instead."
                )
                raise ThumbnailRendererError(
                    "soffice --convert-to png emitted %d PNG(s) for a "
                    "%d-slide deck.  Most LibreOffice 7+ builds only write "
                    "the first slide via the PNG filter; %s"
                    % (len(png_paths), expected_slide_count, remedy)
                )

        if not png_paths:
            raise ThumbnailRendererError(
                "no PNG output produced by the rendering pipeline.  Verify "
                "LibreOffice can convert this deck (`soffice --convert-to pdf "
                "<deck>.pptx`); rendering through PDF also requires "
                "`pdftoppm` (Poppler) or `pypdfium2`."
            )

        pages = _pages_by_slide(png_paths, expected_slide_count, hidden)
        wanted = list(range(expected_slide_count) if slide_indexes is None else slide_indexes)
        png_paths = _select_pages(pages, wanted, expected_slide_count)

        if return_bytes:
            return [p.read_bytes() for p in png_paths]

        output_dir = (
            Path(out_dir) if out_dir is not None else Path(tempfile.mkdtemp(prefix="pptx-thumbs-"))
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for index, png_path in zip(wanted, png_paths):
            # -- named for the slide, not for whatever the pipeline called it --
            target = output_dir / _output_name(index, expected_slide_count)
            shutil.copy2(png_path, target)
            paths.append(target)
        return paths


def _render_via_png(
    bin_path: str, deck_path: Path, work_dir: Path, timeout: int, *, env: Optional[dict] = None
) -> List[Path]:
    """Run the soffice PNG filter and return the produced PNG paths."""
    # Snapshot any PNGs already in `work_dir` so we can later subtract
    # them from the result set.  Otherwise, when a caller points
    # `out_dir=` at a non-empty directory (a shared artifacts folder, a
    # cache, …) stray PNGs get treated as slide renders and corrupt
    # `slide_indexes` lookups / out-of-range errors.
    preexisting_pngs = {p.name for p in work_dir.glob("*.png")}

    result = _run_soffice(bin_path, deck_path, work_dir, timeout, env=env)
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
    bin_path: str,
    deck_path: Path,
    work_dir: Path,
    timeout: int,
    *,
    dpi: int,
    env: Optional[dict] = None,
    hidden_slides: bool = False,
) -> List[Path]:
    """Run the soffice PDF filter, then split each PDF page into a PNG.

    Splits prefer the ``pdftoppm`` binary (Poppler) since it's a single
    subprocess and ubiquitous on Linux/macOS; ``pypdfium2`` is the
    pure-Python fallback when callers can't depend on Poppler.

    *hidden_slides* says the deck has hidden slides, which are then exported
    as well so there is a page for every slide.
    """
    # Snapshot existing PDFs so a stale one in a shared work_dir doesn't
    # get treated as our output.
    preexisting_pdfs = {p.name for p in work_dir.glob("*.pdf")}

    result = _run_soffice_pdf(
        bin_path, deck_path, work_dir, timeout, env=env, hidden_slides=hidden_slides
    )
    if result.returncode != 0:
        raise ThumbnailRendererError(
            "soffice --convert-to pdf exited with status %d: %s"
            % (result.returncode, (result.stderr or b"").decode("utf-8", "replace"))
        )

    pdfs = [p for p in work_dir.glob("*.pdf") if p.name not in preexisting_pdfs]
    if not pdfs:
        raise ThumbnailRendererError(
            "soffice --convert-to pdf produced no PDF output; "
            "ensure your LibreOffice build includes the PDF export filter."
        )

    pdf_path = pdfs[0]
    try:
        return _pdf_to_pngs(pdf_path, work_dir, dpi=dpi, timeout=timeout)
    finally:
        with suppress(OSError):
            pdf_path.unlink()


def _pdf_to_pngs(
    pdf_path: Path, out_dir: Path, *, dpi: int, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> List[Path]:
    """Split a PDF into one PNG per page in *out_dir* and return the paths.

    Tries ``pdftoppm`` first (Poppler), then ``pypdfium2``.  Raises
    :class:`ThumbnailRendererError` with an install hint when neither is
    available — the message names both options so the user can pick
    whichever fits their environment.  *timeout* (seconds) bounds the
    ``pdftoppm`` process.
    """
    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm is not None:
        return _pdf_to_pngs_via_pdftoppm(pdftoppm, pdf_path, out_dir, dpi=dpi, timeout=timeout)

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
    pdftoppm: str,
    pdf_path: Path,
    out_dir: Path,
    *,
    dpi: int,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
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
    result = _run(cmd, timeout=timeout)
    if result.returncode != 0:
        raise ThumbnailRendererError(
            "pdftoppm exited with status %d: %s"
            % (result.returncode, (result.stderr or b"").decode("utf-8", "replace"))
        )
    pages = sorted(out_dir.glob(prefix + "-*.png"), key=_natural_sort_key)
    return pages


def _pdf_to_pngs_via_pypdfium2(pdf_path: Path, out_dir: Path, *, dpi: int) -> List[Path]:
    import pypdfium2 as pdfium  # type: ignore[import-not-found]

    scale = float(dpi) / 72.0  # pypdfium2 uses 1.0 == 72 DPI
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        pages: List[Path] = []
        prefix = pdf_path.stem + "-page"
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                # -- pypdfium2 leaves `scale` unannotated with an `int` default,
                # -- so a checker infers `int`; any real number is accepted --
                bitmap = page.render(scale=scale)  # pyright: ignore[reportArgumentType]
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


def render_slide_thumbnail(
    slide: "_Slide",
    *,
    out_path: Optional[Union[str, os.PathLike[str]]] = None,
    soffice_bin: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    return_bytes: bool = False,
    strategy: str = "auto",
    dpi: int = 150,
    font_dirs: Optional[Sequence[Union[str, os.PathLike[str]]]] = None,
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

    *strategy*, *dpi* and *font_dirs* mirror the same arguments on
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
            font_dirs=font_dirs,
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
            font_dirs=font_dirs,
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
    font_dirs: Optional[Sequence[Union[str, os.PathLike[str]]]] = None,
) -> Union[List[Path], List[bytes]]:
    """Render slide thumbnails — friendlier wrapper around :func:`render_slide_thumbnails`.

    Same semantics as :func:`render_slide_thumbnails` but with two
    quality-of-life additions:

    * ``slides=`` (cleaner name than ``slide_indexes=``).
    * ``name_template=`` — a ``str.format``-able template like
      ``"slide-{:02d}.png"`` applied to the rendered PNGs.  Index is
      0-based.  Defaults to the ``"_render_input-page-N.png"`` names of
      :func:`render_slide_thumbnails` (1-based) if omitted.
    * ``scale=`` is accepted and translated to ``dpi=``: 1.0 is 72 DPI,
      one pixel per point, so ``scale=2`` ≙ ``dpi=144`` and ``scale=0.5``
      ≙ ``dpi=36``, which is also the minimum.  It overrides ``dpi=`` when
      both are given.
    * ``font_dirs=`` hands extra font folders to LibreOffice (see
      :func:`render_slide_thumbnails`).
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
        font_dirs=font_dirs,
    )
    if return_bytes or name_template is None:
        return paths
    # ``paths`` here is List[Path].
    renamed: list[Path] = []
    if slides is None:
        index_iter: list[int] = list(range(len(paths)))
    else:
        index_iter = list(slides)
    for idx, p in zip(index_iter, cast(List[Path], paths)):
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
