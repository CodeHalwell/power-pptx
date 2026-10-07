"""Unit-test suite for `power_pptx.render`.

LibreOffice is mocked out: these tests cover argument plumbing, error
handling, and selection of slide indexes — not the actual rendering.
"""

from __future__ import annotations

import importlib.util
import logging
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from power_pptx import Presentation
from power_pptx.render import (
    DEFAULT_TIMEOUT_SECONDS,
    ThumbnailRendererError,
    ThumbnailRendererUnavailable,
    _pdf_to_pngs_via_pdftoppm,
    _resolve_binary,
    render_slide_thumbnail,
    render_slide_thumbnails,
    render_slides,
)
from power_pptx.util import Inches


@pytest.fixture
def two_slide_prs():
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[5])
    prs.slides.add_slide(prs.slide_layouts[5])
    return prs


def _deck(slide_count, hidden=()):
    """A `Presentation` of `slide_count` blank slides, those in `hidden` marked ``show="0"``."""
    prs = Presentation()
    for idx in range(slide_count):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        if idx in hidden:
            slide._element.set("show", "0")
    return prs


class _FakeToolchain:
    """Stands in for `subprocess.run` for both ``soffice`` and ``pdftoppm``.

    The commands are simulated at the process boundary so the real orchestration (strategy
    selection, page-to-slide mapping, output handling) runs. Like LibreOffice 24.2 it writes
    one PNG, of the first slide, for ``--convert-to png``. Each ``--convert-to pdf`` consumes
    the next entry of `pdf_pages`, the number of pages in the PDF it "exports" (LibreOffice
    skips hidden slides, so that is the number of visible slides). ``pdftoppm`` then writes
    one PNG per page whose content names the PDF it came from and the page number.
    """

    PNG = b"\x89PNG\r\n\x1a\n"

    def __init__(self, pdf_pages=()):
        self._pdf_pages = list(pdf_pages)
        self.commands = []
        self._pdf_count = 0

    def __call__(self, cmd, **kwargs):
        self.commands.append(list(cmd))
        tool = Path(cmd[0]).name
        if tool == "soffice":
            self._soffice(cmd)
        elif tool == "pdftoppm":
            self._pdftoppm(cmd)
        else:  # pragma: no cover
            raise AssertionError(f"unexpected command {cmd!r}")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    def _soffice(self, cmd):
        fmt = cmd[cmd.index("--convert-to") + 1]
        out_dir = Path(cmd[cmd.index("--outdir") + 1])
        stem = Path(cmd[-1]).stem
        if fmt == "png":
            (out_dir / f"{stem}.png").write_bytes(self.PNG + b"png-slide-1")
            return
        assert self._pdf_pages, "LibreOffice was asked for a PDF export nobody expected"
        self._pdf_count += 1
        pages = self._pdf_pages.pop(0)
        (out_dir / f"{stem}.pdf").write_bytes(b"%%PDF-%d:%d" % (pages, self._pdf_count))

    def _pdftoppm(self, cmd):
        pdf_path, prefix = Path(cmd[-2]), cmd[-1]
        pages, pdf_no = (int(n) for n in pdf_path.read_bytes()[5:].split(b":"))
        for page in range(1, pages + 1):
            png = Path(f"{prefix}-{page}.png")
            png.write_bytes(self.PNG + b"pdf%d-page%d" % (pdf_no, page))

    @property
    def soffice_runs(self):
        return [cmd for cmd in self.commands if Path(cmd[0]).name == "soffice"]


@contextmanager
def _fake_toolchain(toolchain):
    """Route `soffice`, `pdftoppm` and their discovery to `toolchain`."""
    binaries = {"soffice": "/fake/soffice", "pdftoppm": "/fake/pdftoppm"}
    with (
        patch("power_pptx.render.shutil.which", side_effect=binaries.get),
        patch("power_pptx.render.subprocess.run", side_effect=toolchain),
    ):
        yield toolchain


def _prs_with_off_slide_shape():
    """A deck whose slide has an ERROR-severity lint issue (a textbox off the right edge)."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_textbox(Inches(20), Inches(1), Inches(2), Inches(1)).text_frame.text = "off"
    return prs


def _fake_soffice_run(work_dir: Path, *, num_slides=2, exit_code=0, stderr=b""):
    """Drop fake `*.png` files in the work_dir and return a stub CompletedProcess."""
    from subprocess import CompletedProcess

    def _runner(soffice_bin, deck_path, out_dir, timeout):
        if exit_code == 0:
            for i in range(num_slides):
                (Path(out_dir) / f"slide{i}.png").write_bytes(b"\x89PNG\r\n\x1a\n%d" % i)
        return CompletedProcess(args=[], returncode=exit_code, stdout=b"", stderr=stderr)

    return _runner


def _fake_soffice_run_with_names(work_dir: Path, names):
    """Variant fake runner that writes specific filenames in a given order."""
    from subprocess import CompletedProcess

    def _runner(soffice_bin, deck_path, out_dir, timeout):
        for n in names:
            (Path(out_dir) / n).write_bytes(b"\x89PNG\r\n\x1a\n")
        return CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")

    return _runner


class DescribeRenderSlideThumbnails:
    def it_returns_paths_for_every_slide_by_default(self, tmp_path, two_slide_prs):
        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)),
        ):
            paths = render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

        assert len(paths) == 2
        assert all(p.suffix == ".png" for p in paths)

    def it_returns_only_requested_indexes(self, tmp_path, two_slide_prs):
        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)),
        ):
            paths = render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, slide_indexes=[1])

        assert len(paths) == 1
        assert paths[0].name.endswith("1.png")

    def it_raises_when_index_is_out_of_range(self, tmp_path, two_slide_prs):
        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)),
        ):
            with pytest.raises(IndexError, match="out of range"):
                render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, slide_indexes=[5])

    def it_returns_bytes_when_asked(self, tmp_path, two_slide_prs):
        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)),
        ):
            data = render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, return_bytes=True)

        assert all(isinstance(d, bytes) for d in data)
        assert data[0].startswith(b"\x89PNG")

    def it_raises_unavailable_when_soffice_is_missing(self, two_slide_prs):
        with patch("power_pptx.render.shutil.which", return_value=None):
            with pytest.raises(ThumbnailRendererUnavailable, match="install LibreOffice"):
                render_slide_thumbnails(two_slide_prs)

    def it_raises_when_soffice_exits_non_zero(self, tmp_path, two_slide_prs):
        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch(
                "power_pptx.render._run_soffice",
                side_effect=_fake_soffice_run(tmp_path, exit_code=1, stderr=b"boom"),
            ),
        ):
            with pytest.raises(ThumbnailRendererError, match="status 1"):
                render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

    def it_raises_when_soffice_produces_no_pngs(self, tmp_path, two_slide_prs):
        # ``strategy="png"`` skips the PDF-split fallback so callers can
        # still assert on the PNG-only failure mode.
        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch(
                "power_pptx.render._run_soffice",
                side_effect=_fake_soffice_run(tmp_path, num_slides=0),
            ),
        ):
            with pytest.raises(ThumbnailRendererError, match="emitted 0 PNG"):
                render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, strategy="png")

    def it_passes_the_default_timeout_through(self, tmp_path, two_slide_prs):
        captured = {}

        def _capture(soffice_bin, deck_path, out_dir, timeout):
            captured["timeout"] = timeout
            return _fake_soffice_run(tmp_path)(soffice_bin, deck_path, out_dir, timeout)

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_capture),
        ):
            render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

        assert captured["timeout"] == DEFAULT_TIMEOUT_SECONDS

    def it_honours_custom_soffice_bin(self, tmp_path, two_slide_prs):
        captured = {}

        def _capture(soffice_bin, deck_path, out_dir, timeout):
            captured["bin"] = soffice_bin
            return _fake_soffice_run(tmp_path)(soffice_bin, deck_path, out_dir, timeout)

        with (
            patch("power_pptx.render.shutil.which", return_value="/opt/libre/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_capture),
        ):
            render_slide_thumbnails(
                two_slide_prs, out_dir=tmp_path, soffice_bin="/opt/libre/soffice"
            )

        assert captured["bin"] == "/opt/libre/soffice"


class DescribeRenderSlideThumbnail:
    def it_renders_the_specific_slide(self, tmp_path, two_slide_prs):
        slide = two_slide_prs.slides[1]

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)),
        ):
            target = tmp_path / "out" / "slide.png"
            path = render_slide_thumbnail(slide, out_path=target)

        assert path == target
        assert path.exists()

    def it_returns_bytes_when_asked(self, tmp_path, two_slide_prs):
        slide = two_slide_prs.slides[0]

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)),
        ):
            data = render_slide_thumbnail(slide, return_bytes=True)

        assert isinstance(data, bytes)
        assert data.startswith(b"\x89PNG")


class DescribePresentationConvenienceMethods:
    def it_exposes_render_thumbnails_on_presentation(self, tmp_path, two_slide_prs):
        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)),
        ):
            paths = two_slide_prs.render_thumbnails(out_dir=tmp_path)

        assert len(paths) == 2

    def it_exposes_render_thumbnail_on_slide(self, tmp_path, two_slide_prs):
        slide = two_slide_prs.slides[0]

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)),
        ):
            path = slide.render_thumbnail(out_path=tmp_path / "s.png")

        assert path.exists()


class DescribeNaturalSort:
    """Regression tests for the lexicographic-sort bug on 10+ slide decks."""

    def it_orders_double_digit_slide_numbers_correctly(self, tmp_path):
        from power_pptx import Presentation
        from power_pptx.render import _natural_sort_key

        prs = Presentation()
        for _ in range(11):
            prs.slides.add_slide(prs.slide_layouts[5])

        # Names mirror what LibreOffice emits: deck-1.png .. deck-11.png
        names = [f"deck-{i}.png" for i in range(1, 12)]
        runner = _fake_soffice_run_with_names(tmp_path, names)

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=runner),
        ):
            paths = render_slide_thumbnails(prs, out_dir=tmp_path)

        # With natural sort, slide #2 (index 1) is the second entry — not #10.
        assert [p.name for p in paths] == names

        # Spot-check the key for completeness.
        assert _natural_sort_key(Path("deck-2.png")) < _natural_sort_key(Path("deck-10.png"))

    def it_returns_the_correct_slide_for_high_indexes(self, tmp_path):
        """`slide_indexes=[9]` must hit `deck-10.png`, not `deck-2.png`."""
        from power_pptx import Presentation

        prs = Presentation()
        for _ in range(11):
            prs.slides.add_slide(prs.slide_layouts[5])

        names = [f"deck-{i}.png" for i in range(1, 12)]
        runner = _fake_soffice_run_with_names(tmp_path, names)

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=runner),
        ):
            paths = render_slide_thumbnails(prs, out_dir=tmp_path, slide_indexes=[9])

        assert paths[0].name == "deck-10.png"


class DescribePngFiltering:
    """`render_slide_thumbnails` must ignore PNGs already in `out_dir`."""

    def it_ignores_preexisting_pngs_in_the_output_directory(self, tmp_path, two_slide_prs):
        # Drop a stray PNG in the directory before rendering — perhaps
        # left over from a previous job or simply present in a shared
        # artifacts folder.
        (tmp_path / "stale.png").write_bytes(b"\x89PNG\r\n\x1a\nstale")

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)),
        ):
            paths = render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

        names = {p.name for p in paths}
        assert "stale.png" not in names
        assert len(paths) == 2  # two slides, not three

    def it_keeps_indexes_aligned_when_strays_are_present(self, tmp_path, two_slide_prs):
        # A stray that would lex-sort *between* the two genuine outputs.
        (tmp_path / "slide05.png").write_bytes(b"\x89PNG\r\n\x1a\nstale")

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)),
        ):
            paths = render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, slide_indexes=[1])

        # Without the filter we'd risk returning slide05.png; with it,
        # index 1 maps to the genuine second render (slide1.png from the
        # fake runner, which writes slide{0,1}.png).
        assert paths[0].name == "slide1.png"


class DescribePdfFallback:
    """When ``--convert-to png`` only emits one slide, fall back to PDF split."""

    def _fake_pdf_run(self, work_dir, *, exit_code=0, stderr=b""):
        from subprocess import CompletedProcess

        def _runner(soffice_bin, deck_path, out_dir, timeout):
            if exit_code == 0:
                (Path(out_dir) / "_render_input.pdf").write_bytes(b"%PDF-1.4\n")
            return CompletedProcess(args=[], returncode=exit_code, stdout=b"", stderr=stderr)

        return _runner

    def _fake_pdf_split(self, work_dir, *, num_pages):
        def _split(pdf_path, out_dir, *, dpi):
            paths = []
            prefix = pdf_path.stem + "-page"
            for i in range(num_pages):
                p = Path(out_dir) / f"{prefix}-{i + 1}.png"
                p.write_bytes(b"\x89PNG\r\n\x1a\n%d" % i)
                paths.append(p)
            return paths

        return _split

    def it_falls_back_when_png_misses_slides(self, tmp_path, two_slide_prs):
        # Stock LibreOffice 7+ writes only the first slide via the PNG
        # filter — simulate that and verify we transparently switch to
        # the PDF-split path so the caller still gets one PNG per slide.
        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch(
                "power_pptx.render._run_soffice",
                side_effect=_fake_soffice_run(tmp_path, num_slides=1),
            ),
            patch(
                "power_pptx.render._run_soffice_pdf",
                side_effect=self._fake_pdf_run(tmp_path),
            ),
            patch(
                "power_pptx.render._pdf_to_pngs",
                side_effect=self._fake_pdf_split(tmp_path, num_pages=2),
            ),
        ):
            paths = render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

        assert len(paths) == 2
        assert all(p.suffix == ".png" for p in paths)

    def it_uses_pdf_directly_when_strategy_is_pdf(self, tmp_path, two_slide_prs):
        png_called = False

        def _no_png(*args, **kwargs):
            nonlocal png_called
            png_called = True
            raise AssertionError("PNG path should be skipped when strategy='pdf'")

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_no_png),
            patch(
                "power_pptx.render._run_soffice_pdf",
                side_effect=self._fake_pdf_run(tmp_path),
            ),
            patch(
                "power_pptx.render._pdf_to_pngs",
                side_effect=self._fake_pdf_split(tmp_path, num_pages=2),
            ),
        ):
            paths = render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, strategy="pdf")

        assert len(paths) == 2
        assert not png_called

    def it_raises_when_neither_pipeline_produces_pngs(self, tmp_path, two_slide_prs):
        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch(
                "power_pptx.render._run_soffice",
                side_effect=_fake_soffice_run(tmp_path, num_slides=0),
            ),
            patch(
                "power_pptx.render._run_soffice_pdf",
                side_effect=self._fake_pdf_run(tmp_path, exit_code=1, stderr=b"boom"),
            ),
        ):
            with pytest.raises(ThumbnailRendererError, match="status 1"):
                render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)


class DescribeRenderSlideThumbnailCleanup:
    """The single-slide renderer must not leak temp directories."""

    def it_cleans_the_temp_dir_when_out_path_is_given(self, tmp_path, two_slide_prs):
        slide = two_slide_prs.slides[0]
        created_dirs = []

        real_tmp = tempfile.TemporaryDirectory

        def _spy_tmp(*args, **kwargs):
            ctx = real_tmp(*args, **kwargs)
            created_dirs.append(ctx.name)
            return ctx

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)),
            patch("power_pptx.render.tempfile.TemporaryDirectory", side_effect=_spy_tmp),
        ):
            path = render_slide_thumbnail(slide, out_path=tmp_path / "s.png")

        assert path.exists()
        # Every temp dir we created in the spy must have been cleaned up.
        assert created_dirs, "expected at least one TemporaryDirectory"
        for d in created_dirs:
            assert not Path(d).exists(), f"temp dir {d} not cleaned"

    def it_cleans_the_temp_dir_when_no_out_path_is_given(self, tmp_path, two_slide_prs):
        slide = two_slide_prs.slides[0]
        created_dirs = []

        real_tmp = tempfile.TemporaryDirectory

        def _spy_tmp(*args, **kwargs):
            ctx = real_tmp(*args, **kwargs)
            created_dirs.append(ctx.name)
            return ctx

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)),
            patch("power_pptx.render.tempfile.TemporaryDirectory", side_effect=_spy_tmp),
        ):
            path = render_slide_thumbnail(slide)

        try:
            assert path.exists()
            assert path.suffix == ".png"
            for d in created_dirs:
                assert not Path(d).exists(), f"temp dir {d} not cleaned"
        finally:
            # Caller owns this NamedTemporaryFile; clean up after the test.
            path.unlink(missing_ok=True)


class DescribeRenderingIntoAnExistingDirectory:
    """Pages of an earlier render sitting in `out_dir` must not be mistaken for this one's."""

    def it_returns_only_the_pages_of_this_render_when_rendering_twice(self, tmp_path):
        toolchain = _FakeToolchain(pdf_pages=[3, 2])

        with _fake_toolchain(toolchain):
            first = render_slide_thumbnails(_deck(3), out_dir=tmp_path, strategy="pdf")
            second = render_slide_thumbnails(_deck(2), out_dir=tmp_path, strategy="pdf")

        assert len(first) == 3
        # -- a 2-slide deck gives 2 paths, not the 3 pages of the first render --
        assert len(second) == 2
        assert [p.read_bytes() for p in second] == [
            _FakeToolchain.PNG + b"pdf2-page1",
            _FakeToolchain.PNG + b"pdf2-page2",
        ]

    def it_does_not_pick_up_leftover_pdftoppm_pages(self, tmp_path):
        pdf = tmp_path / "deck.pdf"
        pdf.write_bytes(b"%PDF-2:1")
        for n in (1, 2, 3):
            (tmp_path / f"deck-page-{n}.png").write_bytes(b"stale")

        with patch("power_pptx.render.subprocess.run", side_effect=_FakeToolchain()):
            pages = _pdf_to_pngs_via_pdftoppm("/fake/pdftoppm", pdf, tmp_path, dpi=150)

        assert [p.name for p in pages] == ["deck-page-1.png", "deck-page-2.png"]
        assert all(p.read_bytes().startswith(_FakeToolchain.PNG) for p in pages)

    def it_leaves_other_files_in_the_directory_alone(self, tmp_path):
        keep = tmp_path / "notes.txt"
        keep.write_text("keep me")
        stale = tmp_path / "_render_input-page-3.png"
        stale.write_bytes(b"stale")

        with _fake_toolchain(_FakeToolchain(pdf_pages=[2])):
            render_slide_thumbnails(_deck(2), out_dir=tmp_path, strategy="pdf")

        assert keep.read_text() == "keep me"
        assert stale.read_bytes() == b"stale"

    def it_does_not_leave_scratch_directories_behind(self, tmp_path):
        with _fake_toolchain(_FakeToolchain(pdf_pages=[2])):
            render_slide_thumbnails(_deck(2), out_dir=tmp_path, strategy="pdf")

        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "_render_input-page-1.png",
            "_render_input-page-2.png",
        ]

    def it_returns_the_same_page_twice_for_a_slide_requested_twice(self, tmp_path):
        with _fake_toolchain(_FakeToolchain(pdf_pages=[2])):
            paths = render_slide_thumbnails(
                _deck(2), out_dir=tmp_path, slide_indexes=[1, 0, 1], strategy="pdf"
            )

        assert [p.name for p in paths] == [
            "_render_input-page-2.png",
            "_render_input-page-1.png",
            "_render_input-page-2.png",
        ]
        assert all(p.exists() for p in paths)


class DescribeTheSavedInputDeck:
    """The `.pptx` handed to LibreOffice is a private temp file, never the caller's output."""

    def it_does_not_leave_the_input_deck_in_the_output_directory(self, tmp_path, two_slide_prs):
        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)),
        ):
            render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

        assert list(tmp_path.glob("*.pptx")) == []

    def it_saves_the_deck_outside_the_output_directory(self, tmp_path, two_slide_prs):
        seen = {}

        def _inspect(soffice_bin, deck_path, out_dir, timeout):
            seen["deck_exists"] = Path(deck_path).exists()
            seen["deck_dir"] = Path(deck_path).parent
            return _fake_soffice_run(tmp_path)(soffice_bin, deck_path, out_dir, timeout)

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_inspect),
        ):
            render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

        assert seen["deck_exists"] is True
        assert seen["deck_dir"] != tmp_path
        # -- and it is gone once the render is over --
        assert not seen["deck_dir"].exists() or list(seen["deck_dir"].glob("*.pptx")) == []

    def it_removes_the_input_deck_when_rendering_fails(self, tmp_path, two_slide_prs):
        decks = []

        def _failing(soffice_bin, deck_path, out_dir, timeout):
            decks.append(Path(deck_path))
            return _fake_soffice_run(tmp_path, exit_code=1, stderr=b"boom")(
                soffice_bin, deck_path, out_dir, timeout
            )

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_failing),
        ):
            with pytest.raises(ThumbnailRendererError, match="status 1"):
                render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

        assert list(tmp_path.glob("*.pptx")) == []
        (deck,) = decks
        assert not deck.exists()

    def it_keeps_the_input_deck_out_of_the_temp_directory_it_hands_back(self, two_slide_prs):
        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render._run_soffice", side_effect=_fake_soffice_run(Path("."))),
        ):
            paths = render_slide_thumbnails(two_slide_prs)

        try:
            assert len(paths) == 2
            assert all(p.exists() for p in paths)
            assert list(paths[0].parent.glob("*.pptx")) == []
        finally:
            shutil.rmtree(paths[0].parent, ignore_errors=True)


class DescribeRenderingAndLintOnSave:
    """Rendering is for looking at a deck, broken or not; it must not run the save-time lint."""

    @pytest.mark.parametrize("mode", ["raise", "warn"])
    def it_does_not_run_the_lint_on_save_hook(self, tmp_path, caplog, mode):
        prs = _prs_with_off_slide_shape()
        prs.lint_on_save = mode

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch(
                "power_pptx.render._run_soffice",
                side_effect=_fake_soffice_run(tmp_path, num_slides=1),
            ),
            caplog.at_level(logging.WARNING, logger="power_pptx.presentation"),
        ):
            paths = render_slide_thumbnails(prs, out_dir=tmp_path)

        assert len(paths) == 1
        assert caplog.records == []

    def it_renders_a_single_slide_of_a_deck_that_would_fail_the_lint(self, tmp_path):
        prs = _prs_with_off_slide_shape()
        prs.lint_on_save = "raise"

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch(
                "power_pptx.render._run_soffice",
                side_effect=_fake_soffice_run(tmp_path, num_slides=1),
            ),
        ):
            path = prs.slides[0].render_thumbnail(out_path=tmp_path / "broken.png")

        assert path.exists()

    def it_does_not_change_what_an_explicit_save_does(self, tmp_path):
        from power_pptx.exc import LintError

        prs = _prs_with_off_slide_shape()
        prs.lint_on_save = "raise"

        with pytest.raises(LintError):
            prs.save(str(tmp_path / "broken.pptx"))


class DescribeHiddenSlides:
    """LibreOffice's PDF export skips slides marked ``show="0"``, so pages shift."""

    def it_maps_pages_to_the_visible_slides(self, tmp_path):
        # -- slide 2 of 3 is hidden: the PDF has two pages, for slides 1 and 3 --
        prs = _deck(3, hidden={1})
        toolchain = _FakeToolchain(pdf_pages=[2])

        with _fake_toolchain(toolchain):
            paths = render_slide_thumbnails(
                prs, out_dir=tmp_path, slide_indexes=[2], strategy="pdf"
            )

        # -- slide 3 is the *second* page, not the (non-existent) third --
        assert [p.read_bytes() for p in paths] == [_FakeToolchain.PNG + b"pdf1-page2"]

    def it_returns_the_visible_slides_when_asked_for_every_slide(self, tmp_path):
        prs = _deck(3, hidden={1})

        with _fake_toolchain(_FakeToolchain(pdf_pages=[2])):
            paths = render_slide_thumbnails(prs, out_dir=tmp_path, strategy="pdf")

        assert [p.read_bytes() for p in paths] == [
            _FakeToolchain.PNG + b"pdf1-page1",
            _FakeToolchain.PNG + b"pdf1-page2",
        ]

    def it_maps_pages_correctly_when_the_first_slide_is_hidden(self, tmp_path):
        prs = _deck(3, hidden={0})

        with _fake_toolchain(_FakeToolchain(pdf_pages=[2])):
            paths = render_slide_thumbnails(
                prs, out_dir=tmp_path, slide_indexes=[1, 2], strategy="pdf"
            )

        assert [p.read_bytes() for p in paths] == [
            _FakeToolchain.PNG + b"pdf1-page1",
            _FakeToolchain.PNG + b"pdf1-page2",
        ]

    def it_raises_for_a_requested_slide_that_is_hidden(self, tmp_path):
        prs = _deck(3, hidden={1})
        toolchain = _FakeToolchain(pdf_pages=[2])

        with _fake_toolchain(toolchain):
            with pytest.raises(ThumbnailRendererError, match=r"slide 1 is hidden"):
                render_slide_thumbnails(prs, out_dir=tmp_path, slide_indexes=[0, 1])

        # -- nothing to gain from running LibreOffice for a request that cannot be met --
        assert toolchain.soffice_runs == []

    def it_names_every_hidden_slide_that_was_requested(self, tmp_path):
        prs = _deck(4, hidden={1, 3})

        with _fake_toolchain(_FakeToolchain()):
            with pytest.raises(ThumbnailRendererError, match=r"slides 1, 3 are hidden"):
                render_slide_thumbnails(prs, out_dir=tmp_path, slide_indexes=[0, 1, 2, 3])

    def it_raises_for_the_single_slide_renderer_too(self):
        prs = _deck(3, hidden={1})

        with _fake_toolchain(_FakeToolchain()):
            with pytest.raises(ThumbnailRendererError, match="hidden"):
                render_slide_thumbnail(prs.slides[1], return_bytes=True)

    def it_raises_when_every_slide_is_hidden(self, tmp_path):
        prs = _deck(2, hidden={0, 1})
        toolchain = _FakeToolchain()

        with _fake_toolchain(toolchain):
            with pytest.raises(ThumbnailRendererError, match="every slide .* hidden"):
                render_slide_thumbnails(prs, out_dir=tmp_path)

        assert toolchain.soffice_runs == []

    def it_still_reports_an_out_of_range_index_as_an_IndexError(self, tmp_path):
        prs = _deck(3, hidden={1})

        with _fake_toolchain(_FakeToolchain()):
            with pytest.raises(IndexError, match="slide index 3 out of range for deck with 3"):
                render_slide_thumbnails(prs, out_dir=tmp_path, slide_indexes=[3])

    def it_does_not_trust_the_png_filters_single_image_for_a_hidden_first_slide(self, tmp_path):
        # -- the PNG filter always renders slide 1, hidden or not. One visible slide and one
        # -- PNG look like a match, but that image is the hidden slide, not the visible one.
        prs = _deck(2, hidden={0})
        toolchain = _FakeToolchain(pdf_pages=[1])

        with _fake_toolchain(toolchain):
            paths = render_slide_thumbnails(prs, out_dir=tmp_path, slide_indexes=[1])

        assert [p.read_bytes() for p in paths] == [_FakeToolchain.PNG + b"pdf1-page1"]

    def it_refuses_the_png_strategy_when_it_cannot_tell_which_slide_an_image_shows(self, tmp_path):
        prs = _deck(3, hidden={1})

        with _fake_toolchain(_FakeToolchain()):
            with pytest.raises(ThumbnailRendererError, match="emitted 1 PNG"):
                render_slide_thumbnails(prs, out_dir=tmp_path, slide_indexes=[0], strategy="png")

    def it_raises_when_the_page_count_matches_neither_the_deck_nor_its_visible_slides(
        self, tmp_path
    ):
        prs = _deck(3, hidden={1})

        with _fake_toolchain(_FakeToolchain(pdf_pages=[5])):
            with pytest.raises(ThumbnailRendererError, match=r"5 page.*3 slide.*2 .*not hidden"):
                render_slide_thumbnails(prs, out_dir=tmp_path, strategy="pdf")

    def it_raises_when_a_deck_without_hidden_slides_gets_the_wrong_page_count(self, tmp_path):
        prs = _deck(3)

        with _fake_toolchain(_FakeToolchain(pdf_pages=[2])):
            with pytest.raises(ThumbnailRendererError, match=r"2 page.*3 slide"):
                render_slide_thumbnails(prs, out_dir=tmp_path, strategy="pdf")

    def it_accepts_one_page_per_slide_from_a_build_that_exports_hidden_slides(self, tmp_path):
        prs = _deck(3, hidden={1})

        with _fake_toolchain(_FakeToolchain(pdf_pages=[3])):
            paths = render_slide_thumbnails(
                prs, out_dir=tmp_path, slide_indexes=[2], strategy="pdf"
            )

        assert [p.read_bytes() for p in paths] == [_FakeToolchain.PNG + b"pdf1-page3"]

    @pytest.mark.parametrize(
        ("show", "hidden"),
        [("0", True), ("false", True), ("1", False), ("true", False), (None, False)],
    )
    def it_reads_the_show_attribute_as_an_xsd_boolean(self, tmp_path, show, hidden):
        prs = _deck(1)
        if show is not None:
            prs.slides[0]._element.set("show", show)

        with _fake_toolchain(_FakeToolchain(pdf_pages=[1])):
            if hidden:
                with pytest.raises(ThumbnailRendererError, match="hidden"):
                    render_slide_thumbnails(prs, out_dir=tmp_path, slide_indexes=[0])
            else:
                assert len(render_slide_thumbnails(prs, out_dir=tmp_path, slide_indexes=[0])) == 1


class DescribeRenderSlidesNaming:
    def it_names_each_png_after_its_slide_index_when_a_slide_is_hidden(self, tmp_path):
        prs = _deck(3, hidden={1})

        with _fake_toolchain(_FakeToolchain(pdf_pages=[2])):
            paths = render_slides(
                prs, out_dir=tmp_path, name_template="slide-{:02d}.png", strategy="pdf"
            )

        # -- slide 3 is not "slide-01": the template index is the slide's, not the page's --
        assert [p.name for p in paths] == ["slide-00.png", "slide-02.png"]
        assert paths[1].read_bytes() == _FakeToolchain.PNG + b"pdf1-page2"

    def it_names_requested_slides_after_their_slide_index(self, tmp_path):
        prs = _deck(3, hidden={0})

        with _fake_toolchain(_FakeToolchain(pdf_pages=[2])):
            paths = render_slides(
                prs,
                out_dir=tmp_path,
                slides=[2],
                name_template="slide-{:02d}.png",
                strategy="pdf",
            )

        assert [p.name for p in paths] == ["slide-02.png"]


class DescribeSofficeTimeout:
    """`subprocess.run(timeout=)` raises TimeoutExpired; callers are promised a renderer error."""

    @pytest.mark.parametrize("strategy", ["png", "pdf"])
    def it_reports_a_timeout_as_a_ThumbnailRendererError(self, tmp_path, strategy):
        def _hang(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render.subprocess.run", side_effect=_hang),
        ):
            with pytest.raises(ThumbnailRendererError, match="timed out after 7"):
                render_slide_thumbnails(_deck(2), out_dir=tmp_path, timeout=7, strategy=strategy)

    def it_does_not_leave_the_input_deck_behind_after_a_timeout(self, tmp_path):
        def _hang(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

        with (
            patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"),
            patch("power_pptx.render.subprocess.run", side_effect=_hang),
        ):
            with pytest.raises(ThumbnailRendererError):
                render_slide_thumbnails(_deck(2), out_dir=tmp_path, strategy="pdf")

        assert list(tmp_path.iterdir()) == []


class Describe_resolve_binary:
    @pytest.fixture(autouse=True)
    def _no_environment_override(self, monkeypatch):
        monkeypatch.delenv("POWER_PPTX_SOFFICE", raising=False)

    def it_prefers_soffice_on_the_path(self):
        found = {"soffice": "/usr/bin/soffice", "libreoffice": "/usr/bin/libreoffice"}
        with patch("power_pptx.render.shutil.which", side_effect=found.get):
            assert _resolve_binary(None) == "/usr/bin/soffice"

    def it_falls_back_to_libreoffice_on_the_path(self):
        found = {"libreoffice": "/usr/bin/libreoffice"}
        with patch("power_pptx.render.shutil.which", side_effect=found.get):
            assert _resolve_binary(None) == "/usr/bin/libreoffice"

    def it_names_both_candidates_when_neither_is_found(self):
        with patch("power_pptx.render.shutil.which", return_value=None):
            with pytest.raises(ThumbnailRendererUnavailable, match=r"soffice.*libreoffice") as e:
                _resolve_binary(None)
        assert "install LibreOffice" in str(e.value)

    def it_does_not_fall_back_when_a_binary_was_asked_for_explicitly(self):
        found = {"soffice": "/usr/bin/soffice", "libreoffice": "/usr/bin/libreoffice"}
        with patch("power_pptx.render.shutil.which", side_effect=found.get):
            with pytest.raises(ThumbnailRendererUnavailable, match="/opt/missing/soffice"):
                _resolve_binary("/opt/missing/soffice")

    def it_honours_the_environment_variable_over_the_defaults(self, monkeypatch):
        monkeypatch.setenv("POWER_PPTX_SOFFICE", "/opt/lo/soffice")
        found = {"/opt/lo/soffice": "/opt/lo/soffice", "soffice": "/usr/bin/soffice"}
        with patch("power_pptx.render.shutil.which", side_effect=found.get):
            assert _resolve_binary(None) == "/opt/lo/soffice"

    def it_prefers_the_argument_over_the_environment_variable(self, monkeypatch):
        monkeypatch.setenv("POWER_PPTX_SOFFICE", "/opt/lo/soffice")
        found = {"/opt/lo/soffice": "/opt/lo/soffice", "/opt/other/soffice": "/opt/other/soffice"}
        with patch("power_pptx.render.shutil.which", side_effect=found.get):
            assert _resolve_binary("/opt/other/soffice") == "/opt/other/soffice"


class DescribeRenderSlidesScale:
    """`scale=` is a multiplier of the resolution (``dpi=``, 150 by default)."""

    @staticmethod
    def _dpi_passed_on(**kwargs):
        captured = {}

        def _capture(prs, **kw):
            captured.update(kw)
            return []

        with patch("power_pptx.render.render_slide_thumbnails", side_effect=_capture):
            render_slides(_deck(1), **kwargs)
        return captured["dpi"]

    @pytest.mark.parametrize(
        ("scale", "expected_dpi"),
        [(None, 150), (1.0, 150), (0.5, 75), (2.0, 300), (0.1, 36)],
    )
    def it_scales_the_default_resolution(self, scale, expected_dpi):
        assert self._dpi_passed_on(scale=scale) == expected_dpi

    def it_scales_an_explicit_dpi(self):
        assert self._dpi_passed_on(dpi=200, scale=0.5) == 100

    def it_leaves_an_explicit_dpi_alone_without_a_scale(self):
        assert self._dpi_passed_on(dpi=96) == 96


def _libreoffice_toolchain_available():
    has_office = shutil.which("soffice") or shutil.which("libreoffice")
    has_splitter = shutil.which("pdftoppm") or importlib.util.find_spec("pypdfium2")
    return bool(has_office and has_splitter)


def _color_deck():
    """Red, green and blue slides, the green one hidden."""
    from power_pptx.dml.color import RGBColor

    prs = Presentation()
    for rgb in ((255, 0, 0), (0, 200, 0), (0, 0, 255)):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor(*rgb)
    prs.slides[1]._element.set("show", "0")
    return prs


def _dominant_color(png_path):
    """Name of the strongest channel at the centre of the image."""
    from PIL import Image

    with Image.open(png_path) as image:
        red, green, blue = image.convert("RGB").getpixel((image.width // 2, image.height // 2))
    return max(zip((red, green, blue), ("red", "green", "blue")))[1]


@pytest.fixture(scope="module")
def libreoffice_rendered(tmp_path_factory):
    """The colour deck rendered once, every slide LibreOffice can, as PNG files in `out_dir`."""
    prs = _color_deck()
    out_dir = tmp_path_factory.mktemp("thumbs")
    return prs, render_slide_thumbnails(prs, out_dir=out_dir), out_dir


@pytest.mark.skipif(
    not _libreoffice_toolchain_available(), reason="needs LibreOffice and pdftoppm or pypdfium2"
)
class DescribeRenderingWithLibreOffice:
    """End to end against the real LibreOffice, identifying each slide by its background."""

    def it_renders_the_visible_slides_only(self, libreoffice_rendered):
        _, paths, _ = libreoffice_rendered
        assert [_dominant_color(p) for p in paths] == ["red", "blue"]

    def it_returns_the_right_slide_for_an_index_after_a_hidden_one(self, tmp_path):
        (path,) = render_slide_thumbnails(_color_deck(), out_dir=tmp_path, slide_indexes=[2])

        assert _dominant_color(path) == "blue"

    def it_does_not_return_the_hidden_first_slide_for_the_visible_one(self, tmp_path):
        # -- LibreOffice's PNG filter always renders slide 1, hidden or not, and one image for
        # -- one visible slide would look like a match; the image would be the wrong slide --
        from power_pptx.dml.color import RGBColor

        prs = Presentation()
        for rgb in ((0, 0, 255), (255, 0, 0)):
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            slide.background.fill.solid()
            slide.background.fill.fore_color.rgb = RGBColor(*rgb)
        prs.slides[0]._element.set("show", "0")

        (path,) = render_slide_thumbnails(prs, out_dir=tmp_path, slide_indexes=[1])

        assert _dominant_color(path) == "red"

    def it_leaves_only_the_pngs_in_the_output_directory(self, libreoffice_rendered):
        _, paths, out_dir = libreoffice_rendered
        assert sorted(p.name for p in out_dir.iterdir()) == sorted(p.name for p in paths)

    def it_refuses_to_render_the_hidden_slide(self, libreoffice_rendered, tmp_path):
        prs, _, _ = libreoffice_rendered
        with pytest.raises(ThumbnailRendererError, match="slide 1 is hidden"):
            render_slide_thumbnails(prs, out_dir=tmp_path, slide_indexes=[1])
