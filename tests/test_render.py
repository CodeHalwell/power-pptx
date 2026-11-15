"""Unit-test suite for `power_pptx.render`.

LibreOffice is mocked out: these tests cover argument plumbing, error
handling, and selection of slide indexes — not the actual rendering.
The real pipeline is exercised by `tests/integration/test_render_libreoffice.py`.
"""

from __future__ import annotations

import os
import signal
import sys
import tempfile
import time
from contextlib import contextmanager, suppress
from pathlib import Path
from unittest.mock import patch

import pytest

from power_pptx import Presentation
from power_pptx.render import (
    DEFAULT_TIMEOUT_SECONDS,
    ThumbnailRendererError,
    ThumbnailRendererUnavailable,
    render_slide_thumbnail,
    render_slide_thumbnails,
)


@pytest.fixture
def two_slide_prs():
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[5])
    prs.slides.add_slide(prs.slide_layouts[5])
    return prs


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _fake_soffice_run(work_dir: Path, *, num_slides=2, exit_code=0, stderr=b""):
    """Stand in for `_run_soffice` (the PNG filter): slide N is a PNG whose payload is N."""
    from subprocess import CompletedProcess

    def _runner(soffice_bin, deck_path, out_dir, timeout, env=None):
        if exit_code == 0:
            for i in range(num_slides):
                (Path(out_dir) / f"slide{i}.png").write_bytes(PNG_MAGIC + b"%d" % i)
        return CompletedProcess(args=[], returncode=exit_code, stdout=b"", stderr=stderr)

    return _runner


def _fake_soffice_run_with_names(work_dir: Path, names):
    """Variant fake runner writing specific filenames; each PNG's payload is its name."""
    from subprocess import CompletedProcess

    def _runner(soffice_bin, deck_path, out_dir, timeout, env=None):
        for n in names:
            (Path(out_dir) / n).write_bytes(PNG_MAGIC + n.encode())
        return CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")

    return _runner


def _fake_pdf_run(work_dir, *, exit_code=0, stderr=b"", captured=None):
    """Stand in for `_run_soffice_pdf`: write an empty PDF, record how it was asked."""
    from subprocess import CompletedProcess

    def _runner(soffice_bin, deck_path, out_dir, timeout, env=None, hidden_slides=False):
        if captured is not None:
            captured.update(
                bin=soffice_bin, timeout=timeout, env=env, hidden_slides=hidden_slides
            )
        if exit_code == 0:
            (Path(out_dir) / "_render_input.pdf").write_bytes(b"%PDF-1.4\n")
        return CompletedProcess(args=[], returncode=exit_code, stdout=b"", stderr=stderr)

    return _runner


def _fake_pdf_split(work_dir, *, num_pages, captured=None, name="{prefix}-{number}.png"):
    """Stand in for `_pdf_to_pngs`: page N (0-based) is a PNG whose payload is N."""

    def _split(pdf_path, out_dir, *, dpi, timeout=None):
        if captured is not None:
            captured.update(dpi=dpi, split_timeout=timeout)
        paths = []
        prefix = pdf_path.stem + "-page"
        for i in range(num_pages):
            p = Path(out_dir) / name.format(prefix=prefix, number=i + 1)
            p.write_bytes(PNG_MAGIC + b"%d" % i)
            paths.append(p)
        return paths

    return _split


def _payload(png):
    """What a fake PNG stands for: its page or slide number, or its original name."""
    data = png if isinstance(png, bytes) else Path(png).read_bytes()
    assert data.startswith(PNG_MAGIC)
    return data[len(PNG_MAGIC) :].decode()


def _page_number(png):
    """The 0-based page a fake PNG stands for."""
    return int(_payload(png))


def _png_filter_must_not_run(*args, **kwargs):
    raise AssertionError("the PNG conversion must not run when slides render through PDF")


@contextmanager
def _fake_libreoffice(work_dir, *, num_pages=2, exit_code=0, stderr=b"", captured=None):
    """Stand in for LibreOffice and the PDF split on the default, PDF, pipeline."""
    with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
        "power_pptx.render._run_soffice", side_effect=_png_filter_must_not_run
    ), patch(
        "power_pptx.render._run_soffice_pdf",
        side_effect=_fake_pdf_run(work_dir, exit_code=exit_code, stderr=stderr, captured=captured),
    ), patch(
        "power_pptx.render._pdf_to_pngs",
        side_effect=_fake_pdf_split(work_dir, num_pages=num_pages, captured=captured),
    ):
        yield


class DescribeRenderSlideThumbnails:
    def it_can_render_twice_into_the_same_directory(self, tmp_path, two_slide_prs):
        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)
        ):
            first = render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, strategy="png")
            second = render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, strategy="png")

        assert first == second
        assert all(path.exists() for path in second)
        assert not (tmp_path / "_render_input.pptx").exists()

    def it_leaves_no_output_on_conversion_failure(self, tmp_path, two_slide_prs):
        with _fake_libreoffice(tmp_path, exit_code=1), pytest.raises(ThumbnailRendererError):
            render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

        assert list(tmp_path.iterdir()) == []

    def it_returns_paths_for_every_slide_by_default(self, tmp_path, two_slide_prs):
        with _fake_libreoffice(tmp_path):
            paths = render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

        assert len(paths) == 2
        assert all(p.suffix == ".png" for p in paths)
        assert [_page_number(p) for p in paths] == [0, 1]

    def it_returns_only_requested_indexes(self, tmp_path, two_slide_prs):
        with _fake_libreoffice(tmp_path):
            paths = render_slide_thumbnails(
                two_slide_prs, out_dir=tmp_path, slide_indexes=[1]
            )

        assert len(paths) == 1
        assert _page_number(paths[0]) == 1
        # -- the file is named for the slide (1-based), not its place in the result --
        assert paths[0].name == "_render_input-page-2.png"

    def it_raises_when_index_is_out_of_range(self, tmp_path, two_slide_prs):
        with _fake_libreoffice(tmp_path):
            with pytest.raises(IndexError, match="out of range"):
                render_slide_thumbnails(
                    two_slide_prs, out_dir=tmp_path, slide_indexes=[5]
                )

    def it_returns_bytes_when_asked(self, tmp_path, two_slide_prs):
        with _fake_libreoffice(tmp_path):
            data = render_slide_thumbnails(
                two_slide_prs, out_dir=tmp_path, return_bytes=True
            )

        assert all(isinstance(d, bytes) for d in data)
        assert data[0].startswith(b"\x89PNG")
        assert list(tmp_path.iterdir()) == []

    def it_raises_unavailable_when_soffice_is_missing(self, two_slide_prs):
        with patch("power_pptx.render.shutil.which", return_value=None):
            with pytest.raises(ThumbnailRendererUnavailable, match="install LibreOffice"):
                render_slide_thumbnails(two_slide_prs)

    def it_raises_when_soffice_exits_non_zero(self, tmp_path, two_slide_prs):
        with _fake_libreoffice(tmp_path, exit_code=1, stderr=b"boom"):
            with pytest.raises(ThumbnailRendererError, match="status 1: boom"):
                render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

    def it_raises_when_the_png_filter_exits_non_zero(self, tmp_path, two_slide_prs):
        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice",
            side_effect=_fake_soffice_run(tmp_path, exit_code=1, stderr=b"boom"),
        ):
            with pytest.raises(ThumbnailRendererError, match="status 1"):
                render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, strategy="png")

    def it_raises_when_soffice_produces_no_pngs(self, tmp_path, two_slide_prs):
        # ``strategy="png"`` never goes through PDF, so callers can
        # still assert on the PNG-only failure mode.
        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path, num_slides=0)
        ):
            with pytest.raises(ThumbnailRendererError, match="emitted 0 PNG"):
                render_slide_thumbnails(
                    two_slide_prs, out_dir=tmp_path, strategy="png"
                )

    def it_passes_the_default_timeout_through(self, tmp_path, two_slide_prs):
        captured = {}

        with _fake_libreoffice(tmp_path, captured=captured):
            render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

        assert captured["timeout"] == DEFAULT_TIMEOUT_SECONDS
        assert captured["split_timeout"] == DEFAULT_TIMEOUT_SECONDS

    def it_honours_custom_soffice_bin(self, tmp_path, two_slide_prs):
        captured = {}

        with _fake_libreoffice(tmp_path, captured=captured), patch(
            "power_pptx.render.shutil.which", return_value="/opt/libre/soffice"
        ):
            render_slide_thumbnails(
                two_slide_prs, out_dir=tmp_path, soffice_bin="/opt/libre/soffice"
            )

        assert captured["bin"] == "/opt/libre/soffice"


class DescribeResolveBinary:
    """Which LibreOffice binary runs: the one named, else `soffice`, else `libreoffice`."""

    @pytest.fixture(autouse=True)
    def _no_override(self, monkeypatch):
        monkeypatch.delenv("POWER_PPTX_SOFFICE", raising=False)

    def _which(self, installed):
        return patch("power_pptx.render.shutil.which", side_effect=installed.get)

    def it_prefers_soffice_on_path(self):
        from power_pptx.render import _resolve_binary

        installed = {"soffice": "/usr/bin/soffice", "libreoffice": "/usr/bin/libreoffice"}
        with self._which(installed):
            assert _resolve_binary(None) == "/usr/bin/soffice"

    def it_falls_back_to_libreoffice_on_path(self):
        from power_pptx.render import _resolve_binary

        with self._which({"libreoffice": "/snap/bin/libreoffice"}):
            assert _resolve_binary(None) == "/snap/bin/libreoffice"

    def but_a_binary_named_explicitly_has_no_fallback(self, monkeypatch):
        from power_pptx.render import _resolve_binary

        with self._which({"libreoffice": "/snap/bin/libreoffice"}):
            with pytest.raises(ThumbnailRendererUnavailable, match="'/opt/lo/soffice'"):
                _resolve_binary("/opt/lo/soffice")
            monkeypatch.setenv("POWER_PPTX_SOFFICE", "/env/soffice")
            with pytest.raises(ThumbnailRendererUnavailable, match="'/env/soffice'"):
                _resolve_binary(None)

    def and_the_argument_wins_over_the_environment_variable(self, monkeypatch):
        from power_pptx.render import _resolve_binary

        monkeypatch.setenv("POWER_PPTX_SOFFICE", "/env/soffice")
        installed = {"/arg/soffice": "/arg/soffice", "/env/soffice": "/env/soffice"}
        with self._which(installed):
            assert _resolve_binary("/arg/soffice") == "/arg/soffice"
            assert _resolve_binary(None) == "/env/soffice"


class DescribeRenderSlideThumbnail:
    def it_renders_the_specific_slide(self, tmp_path, two_slide_prs):
        slide = two_slide_prs.slides[1]

        with _fake_libreoffice(tmp_path):
            target = tmp_path / "out" / "slide.png"
            path = render_slide_thumbnail(slide, out_path=target)

        assert path == target
        assert path.exists()
        assert _page_number(path) == 1

    def it_returns_bytes_when_asked(self, tmp_path, two_slide_prs):
        slide = two_slide_prs.slides[0]

        with _fake_libreoffice(tmp_path):
            data = render_slide_thumbnail(slide, return_bytes=True)

        assert isinstance(data, bytes)
        assert data.startswith(b"\x89PNG")
        assert _page_number(data) == 0


class DescribePresentationConvenienceMethods:
    def it_exposes_render_thumbnails_on_presentation(self, tmp_path, two_slide_prs):
        with _fake_libreoffice(tmp_path):
            paths = two_slide_prs.render_thumbnails(out_dir=tmp_path)

        assert len(paths) == 2

    def it_exposes_render_thumbnail_on_slide(self, tmp_path, two_slide_prs):
        slide = two_slide_prs.slides[0]

        with _fake_libreoffice(tmp_path):
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

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=runner
        ):
            paths = render_slide_thumbnails(prs, out_dir=tmp_path, strategy="png")

        # With natural sort, slide #2 (index 1) is the second entry — not #10.
        assert [_payload(p) for p in paths] == names

        # Spot-check the key for completeness.
        assert _natural_sort_key(Path("deck-2.png")) < _natural_sort_key(
            Path("deck-10.png")
        )

    def it_returns_the_correct_slide_for_high_indexes(self, tmp_path):
        """`slide_indexes=[9]` must hit `deck-10.png`, not `deck-2.png`."""
        from power_pptx import Presentation

        prs = Presentation()
        for _ in range(11):
            prs.slides.add_slide(prs.slide_layouts[5])

        names = [f"deck-{i}.png" for i in range(1, 12)]
        runner = _fake_soffice_run_with_names(tmp_path, names)

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=runner
        ):
            paths = render_slide_thumbnails(
                prs, out_dir=tmp_path, slide_indexes=[9], strategy="png"
            )

        assert _payload(paths[0]) == "deck-10.png"


class DescribePngFiltering:
    """`render_slide_thumbnails` must ignore PNGs already in `out_dir`."""

    @pytest.mark.parametrize("strategy", ["png", "pdf"])
    def it_ignores_preexisting_pngs_in_the_output_directory(
        self, tmp_path, two_slide_prs, strategy
    ):
        # Drop a stray PNG in the directory before rendering — perhaps
        # left over from a previous job or simply present in a shared
        # artifacts folder.
        (tmp_path / "stale.png").write_bytes(b"\x89PNG\r\n\x1a\nstale")

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)
        ), patch("power_pptx.render._run_soffice_pdf", side_effect=_fake_pdf_run(tmp_path)), patch(
            "power_pptx.render._pdf_to_pngs", side_effect=_fake_pdf_split(tmp_path, num_pages=2)
        ):
            paths = render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, strategy=strategy)

        names = {p.name for p in paths}
        assert "stale.png" not in names
        assert len(paths) == 2  # two slides, not three
        assert (tmp_path / "stale.png").read_bytes().endswith(b"stale")

    def it_keeps_indexes_aligned_when_strays_are_present(self, tmp_path, two_slide_prs):
        # A stray that would lex-sort *between* the two genuine outputs.
        (tmp_path / "slide05.png").write_bytes(b"\x89PNG\r\n\x1a\nstale")

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)
        ):
            paths = render_slide_thumbnails(
                two_slide_prs, out_dir=tmp_path, slide_indexes=[1], strategy="png"
            )

        # Without the filter we'd risk returning slide05.png; with it,
        # index 1 maps to the genuine second render (slide 1 from the
        # fake runner, which writes slide{0,1}.png).
        assert _page_number(paths[0]) == 1


class DescribeHiddenSlides:
    """A hidden slide (``<p:sld show="0">``) is rendered and keeps its index."""

    @pytest.fixture
    def hidden_middle_prs(self):
        prs = Presentation()
        for _ in range(3):
            prs.slides.add_slide(prs.slide_layouts[5])
        prs.slides[1]._element.set("show", "0")
        return prs

    def _render(self, prs, tmp_path, *, num_pages, captured=None, **kwargs):
        with _fake_libreoffice(tmp_path, num_pages=num_pages, captured=captured):
            return render_slide_thumbnails(prs, return_bytes=True, **kwargs)

    def it_asks_libreoffice_to_export_hidden_slides(self, tmp_path, hidden_middle_prs):
        captured = {}

        pngs = self._render(hidden_middle_prs, tmp_path, num_pages=3, captured=captured)

        assert captured["hidden_slides"] is True
        assert [_page_number(png) for png in pngs] == [0, 1, 2]

    def but_it_leaves_the_conversion_alone_for_a_deck_without_any(self, tmp_path, two_slide_prs):
        captured = {}

        self._render(two_slide_prs, tmp_path, num_pages=2, captured=captured)

        assert captured["hidden_slides"] is False

    def it_passes_the_export_option_on_the_soffice_command_line(self, tmp_path):
        from subprocess import CompletedProcess

        from power_pptx.render import _run_soffice_pdf

        commands = []

        def _record(cmd, *, timeout, env=None):
            commands.append(cmd)
            return CompletedProcess(cmd, 0, b"", b"")

        with patch("power_pptx.render._run", side_effect=_record):
            _run_soffice_pdf("soffice", tmp_path / "deck.pptx", tmp_path, 30)
            _run_soffice_pdf("soffice", tmp_path / "deck.pptx", tmp_path, 30, hidden_slides=True)

        plain, with_hidden = (cmd[cmd.index("--convert-to") + 1] for cmd in commands)
        assert plain == "pdf"
        assert with_hidden == (
            'pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}'
        )

    def it_matches_pages_to_visible_slides_when_hidden_ones_are_left_out(
        self, tmp_path, hidden_middle_prs
    ):
        # -- a LibreOffice older than 7.4 ignores the option: 2 pages for 3 slides --
        (png,) = self._render(hidden_middle_prs, tmp_path, num_pages=2, slide_indexes=[2])

        # -- the second page shows the third slide, not the hidden second one --
        assert _page_number(png) == 1

    def and_it_says_so_when_a_hidden_slide_could_not_be_rendered(
        self, tmp_path, hidden_middle_prs
    ):
        with pytest.raises(ThumbnailRendererError, match=r"slide 2 \(index 1\) is hidden"):
            self._render(hidden_middle_prs, tmp_path, num_pages=2, slide_indexes=[1])
        with pytest.raises(ThumbnailRendererError, match="is hidden"):
            self._render(hidden_middle_prs, tmp_path, num_pages=2)

    def but_any_other_page_count_is_still_an_error(self, tmp_path, hidden_middle_prs):
        with pytest.raises(ThumbnailRendererError, match="1 PNG.*3-slide deck"):
            self._render(hidden_middle_prs, tmp_path, num_pages=1)


class DescribeStrategies:
    """`auto` renders through PDF; the PNG filter is for when a PDF cannot be split."""

    @pytest.fixture
    def one_slide_prs(self):
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        return prs

    def it_renders_through_pdf_by_default_without_trying_png_first(
        self, tmp_path, two_slide_prs
    ):
        with _fake_libreoffice(tmp_path):
            paths = render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

        assert len(paths) == 2
        assert all(p.suffix == ".png" for p in paths)

    def it_honours_dpi_for_a_one_slide_deck_too(self, tmp_path, one_slide_prs):
        # -- the PNG filter emits one image, which `auto` used to accept for a
        # -- one-slide deck, silently dropping `dpi` --
        captured = {}

        with _fake_libreoffice(tmp_path, num_pages=1, captured=captured):
            paths = render_slide_thumbnails(one_slide_prs, out_dir=tmp_path, dpi=300)

        assert captured["dpi"] == 300
        assert [p.name for p in paths] == ["_render_input-page-1.png"]

    def it_uses_pdf_directly_when_strategy_is_pdf(self, tmp_path, two_slide_prs):
        with _fake_libreoffice(tmp_path):
            paths = render_slide_thumbnails(
                two_slide_prs, out_dir=tmp_path, strategy="pdf"
            )

        assert len(paths) == 2

    def it_uses_the_png_filter_when_nothing_can_split_a_pdf(self, tmp_path, one_slide_prs):
        def _no_pdf(*args, **kwargs):
            raise AssertionError("PDF cannot be split here, so it must not be produced")

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._pdf_rasteriser_available", return_value=False
        ), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path, num_slides=1)
        ), patch("power_pptx.render._run_soffice_pdf", side_effect=_no_pdf):
            paths = render_slide_thumbnails(one_slide_prs, out_dir=tmp_path)

        assert [_page_number(p) for p in paths] == [0]
        # -- and the file is named as the PDF pipeline would have named it --
        assert [p.name for p in paths] == ["_render_input-page-1.png"]

    def and_it_names_the_missing_tools_when_the_png_filter_falls_short(
        self, tmp_path, two_slide_prs
    ):
        # Stock LibreOffice 7+ writes only the first slide via the PNG filter.
        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._pdf_rasteriser_available", return_value=False
        ), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path, num_slides=1)
        ):
            with pytest.raises(ThumbnailRendererError, match="1 PNG.*2-slide deck.*pypdfium2"):
                render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

    def it_knows_whether_a_pdf_can_be_split(self):
        from power_pptx.render import _pdf_rasteriser_available

        def available(pdftoppm, pypdfium2):
            with patch("power_pptx.render.shutil.which", return_value=pdftoppm), patch(
                "power_pptx.render.importlib.util.find_spec", return_value=pypdfium2
            ):
                return _pdf_rasteriser_available()

        assert available("/usr/bin/pdftoppm", None)
        assert available(None, object())
        assert not available(None, None)

    @pytest.mark.parametrize(
        ("slide_count", "expected"),
        [
            (2, ["_render_input-page-1.png", "_render_input-page-2.png"]),
            (11, ["_render_input-page-%02d.png" % n for n in range(1, 12)]),
        ],
    )
    @pytest.mark.parametrize("strategy", ["png", "pdftoppm", "pypdfium2"])
    def it_names_files_for_their_slide_whatever_rendered_them(
        self, tmp_path, strategy, slide_count, expected
    ):
        prs = Presentation()
        for _ in range(slide_count):
            prs.slides.add_slide(prs.slide_layouts[6])
        # -- pdftoppm pads page numbers to the width of the page count; pypdfium2
        # -- output is not padded; the PNG filter has names of its own --
        page_name = "{prefix}-{number:0%dd}.png" % (
            len(str(slide_count)) if strategy == "pdftoppm" else 1
        )

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice",
            side_effect=_fake_soffice_run(tmp_path, num_slides=slide_count),
        ), patch("power_pptx.render._run_soffice_pdf", side_effect=_fake_pdf_run(tmp_path)), patch(
            "power_pptx.render._pdf_to_pngs",
            side_effect=_fake_pdf_split(tmp_path, num_pages=slide_count, name=page_name),
        ):
            paths = render_slide_thumbnails(
                prs, out_dir=tmp_path, strategy="png" if strategy == "png" else "pdf"
            )

        assert [p.name for p in paths] == expected
        assert [_page_number(p) for p in paths] == list(range(slide_count))

    def it_bounds_the_pdf_split_with_the_same_timeout(self, tmp_path, two_slide_prs):
        captured = {}

        with _fake_libreoffice(tmp_path, captured=captured):
            render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, strategy="pdf", timeout=7)

        assert captured["split_timeout"] == 7

    def it_does_not_return_stale_pages_from_an_earlier_render(
        self, tmp_path, two_slide_prs, one_slide_prs
    ):
        with _fake_libreoffice(tmp_path):
            render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, strategy="pdf")

        with _fake_libreoffice(tmp_path, num_pages=1):
            paths = render_slide_thumbnails(one_slide_prs, out_dir=tmp_path, strategy="pdf")

        assert [path.name for path in paths] == ["_render_input-page-1.png"]

    def it_rejects_an_incomplete_pdf_render(self, tmp_path, two_slide_prs):
        with _fake_libreoffice(tmp_path, num_pages=1), pytest.raises(
            ThumbnailRendererError, match="1 PNG.*2-slide deck"
        ):
            render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, strategy="pdf")

    def it_raises_when_the_pdf_pipeline_produces_no_pngs(self, tmp_path, two_slide_prs):
        with _fake_libreoffice(tmp_path, num_pages=0):
            with pytest.raises(ThumbnailRendererError, match="no PNG output"):
                render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)


class DescribeRenderSlidesScale:
    """`render_slides(scale=)` is a resolution: 1.0 is 72 DPI."""

    @pytest.mark.parametrize(
        ("scale", "dpi"), [(1.0, 72), (2, 144), (0.5, 36), (0.1, 36), (1.5, 108)]
    )
    def it_translates_scale_to_dpi(self, tmp_path, scale, dpi):
        from power_pptx.render import render_slides

        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        captured = {}

        with _fake_libreoffice(tmp_path, num_pages=1, captured=captured):
            render_slides(prs, out_dir=tmp_path, scale=scale, dpi=600)

        assert captured["dpi"] == dpi

    def it_documents_the_scale_it_implements(self):
        from power_pptx.render import render_slides

        doc = " ".join(render_slides.__doc__.split())
        assert "1.0 is 72 DPI" in doc
        assert "``scale=0.5`` ≙ ``dpi=36``" in doc


def _is_running(pid):
    """True while process *pid* is still doing work (a zombie is not)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    if not os.path.isdir("/proc"):
        return True
    try:
        # -- Linux: killed, but not yet collected by whatever adopted it --
        return "zombie" not in Path(f"/proc/{pid}/status").read_text().lower()
    except OSError:
        return False


def _wait_until_stopped(pid, seconds=5.0):
    deadline = time.monotonic() + seconds
    while _is_running(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


@pytest.mark.skipif(sys.platform == "win32", reason="the fake launchers are POSIX shell scripts")
class DescribeProcessTimeouts:
    """A converter that overruns is stopped, with all it started, and reported."""

    @pytest.fixture
    def hanging(self, tmp_path):
        """Make a launcher that starts a worker and waits on it, as `soffice` does.

        Returns a function giving the launcher's path for a name, and the file
        the launcher writes its worker's pid to.
        """
        pid_file = tmp_path / "worker.pid"

        def make(name):
            script = tmp_path / name
            script.write_text(f"#!/bin/sh\nsleep 300 &\necho $! > '{pid_file}'\nwait\n")
            script.chmod(0o755)
            return script

        yield make, pid_file
        if pid_file.exists():
            with suppress(OSError, ValueError):
                os.kill(int(pid_file.read_text()), signal.SIGKILL)

    @pytest.mark.parametrize("strategy", ["pdf", "png"])
    def it_stops_a_hung_soffice_and_raises_the_renderer_error(
        self, hanging, two_slide_prs, strategy
    ):
        make, pid_file = hanging

        with pytest.raises(ThumbnailRendererError, match="did not finish within 2 seconds"):
            render_slide_thumbnails(
                two_slide_prs,
                soffice_bin=str(make("soffice")),
                timeout=2,
                strategy=strategy,
                return_bytes=True,
            )

        worker = int(pid_file.read_text())
        assert _wait_until_stopped(worker), "the process soffice started was left running"

    def it_stops_a_hung_pdftoppm_too(self, hanging, tmp_path):
        from power_pptx.render import _pdf_to_pngs_via_pdftoppm

        make, pid_file = hanging
        pdf = tmp_path / "deck.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")

        with pytest.raises(ThumbnailRendererError, match="pdftoppm did not finish within 2"):
            _pdf_to_pngs_via_pdftoppm(str(make("pdftoppm")), pdf, tmp_path, dpi=72, timeout=2)

        assert _wait_until_stopped(int(pid_file.read_text()))

    def it_returns_the_exit_status_and_output_of_a_command_that_finishes(self):
        from power_pptx.render import _run

        result = _run(
            [sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"],
            timeout=60,
        )

        assert result.returncode == 3
        assert result.stderr == b"boom"
        assert result.stdout == b""


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

        with _fake_libreoffice(tmp_path), patch(
            "power_pptx.render.tempfile.TemporaryDirectory", side_effect=_spy_tmp
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

        with _fake_libreoffice(tmp_path), patch(
            "power_pptx.render.tempfile.TemporaryDirectory", side_effect=_spy_tmp
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


class DescribeFontDirs:
    """Extra font folders reach LibreOffice through a private fonts.conf."""

    FONTS = Path(__file__).parent / "fonts"

    @pytest.fixture(autouse=True)
    def _clean_registry(self, monkeypatch):
        from power_pptx.text import clear_registered_fonts

        monkeypatch.delenv("POWER_PPTX_FONT_DIRS", raising=False)
        monkeypatch.delenv("FONTCONFIG_FILE", raising=False)
        clear_registered_fonts()
        yield
        clear_registered_fonts()

    def it_leaves_the_environment_alone_without_extra_folders(self, tmp_path):
        from power_pptx.render import _soffice_env

        assert _soffice_env(tmp_path) is None

    def it_writes_a_fonts_conf_including_the_system_config(self, tmp_path):
        from power_pptx.render import _soffice_env

        env = _soffice_env(tmp_path, [self.FONTS])

        conf = Path(env["FONTCONFIG_FILE"]).read_text()
        assert f"<dir>{self.FONTS}</dir>" in conf
        assert '<include ignore_missing="yes">/etc/fonts/fonts.conf</include>' in conf
        assert "<cachedir>" in conf

    def it_includes_an_existing_fontconfig_file(self, tmp_path, monkeypatch):
        from power_pptx.render import _soffice_env

        monkeypatch.setenv("FONTCONFIG_FILE", "/custom/fonts.conf")
        conf = Path(_soffice_env(tmp_path, [self.FONTS])["FONTCONFIG_FILE"]).read_text()

        assert '<include ignore_missing="yes">/custom/fonts.conf</include>' in conf
        assert "/etc/fonts/fonts.conf" not in conf

    def it_passes_registered_folders_through(self, tmp_path):
        from power_pptx.render import _soffice_env
        from power_pptx.text import register_font_dir

        register_font_dir(self.FONTS)

        conf = Path(_soffice_env(tmp_path)["FONTCONFIG_FILE"]).read_text()
        assert f"<dir>{self.FONTS}</dir>" in conf

    def it_passes_registered_files_without_their_folders(self, tmp_path):
        from power_pptx.render import _soffice_env
        from power_pptx.text import register_font_family

        register_font_family("Brand Sans", regular=self.FONTS / "Outfit-Regular.ttf")

        conf = Path(_soffice_env(tmp_path)["FONTCONFIG_FILE"]).read_text()
        copies = tmp_path / ".fontconfig" / "files"
        assert f"<dir>{copies}</dir>" in conf
        assert f"<dir>{self.FONTS}</dir>" not in conf
        assert [p.name for p in copies.iterdir()] == ["0-Outfit-Regular.ttf"]

    def it_rejects_missing_folders(self, tmp_path):
        from power_pptx.render import _soffice_env

        with pytest.raises(ValueError, match="does not exist"):
            _soffice_env(tmp_path, [tmp_path / "missing"])

    def it_hands_the_environment_to_soffice(self, tmp_path, two_slide_prs):
        captured = {}

        with _fake_libreoffice(tmp_path, captured=captured):
            render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, font_dirs=[self.FONTS])

        assert captured["env"]["FONTCONFIG_FILE"].endswith("fonts.conf")

    def it_hands_the_environment_to_the_png_filter_too(self, tmp_path, two_slide_prs):
        captured = {}

        def _capture(soffice_bin, deck_path, out_dir, timeout, env=None):
            captured["env"] = env
            return _fake_soffice_run(tmp_path)(soffice_bin, deck_path, out_dir, timeout)

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_capture
        ):
            render_slide_thumbnails(
                two_slide_prs, out_dir=tmp_path, font_dirs=[self.FONTS], strategy="png"
            )

        assert captured["env"]["FONTCONFIG_FILE"].endswith("fonts.conf")
