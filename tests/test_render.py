"""Unit-test suite for `power_pptx.render`.

LibreOffice is mocked out: these tests cover argument plumbing, error
handling, and selection of slide indexes — not the actual rendering.
"""

from __future__ import annotations

import tempfile
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


def _fake_soffice_run(work_dir: Path, *, num_slides=2, exit_code=0, stderr=b""):
    """Drop fake `*.png` files in the work_dir and return a stub CompletedProcess."""
    from subprocess import CompletedProcess

    def _runner(soffice_bin, deck_path, out_dir, timeout, env=None):
        if exit_code == 0:
            for i in range(num_slides):
                (Path(out_dir) / f"slide{i}.png").write_bytes(b"\x89PNG\r\n\x1a\n%d" % i)
        return CompletedProcess(args=[], returncode=exit_code, stdout=b"", stderr=stderr)

    return _runner


def _fake_soffice_run_with_names(work_dir: Path, names):
    """Variant fake runner that writes specific filenames in a given order."""
    from subprocess import CompletedProcess

    def _runner(soffice_bin, deck_path, out_dir, timeout, env=None):
        for n in names:
            (Path(out_dir) / n).write_bytes(b"\x89PNG\r\n\x1a\n")
        return CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")

    return _runner


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
        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice",
            side_effect=_fake_soffice_run(tmp_path, exit_code=1),
        ), pytest.raises(ThumbnailRendererError):
            render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

        assert list(tmp_path.iterdir()) == []

    def it_returns_paths_for_every_slide_by_default(self, tmp_path, two_slide_prs):
        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)
        ):
            paths = render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

        assert len(paths) == 2
        assert all(p.suffix == ".png" for p in paths)

    def it_returns_only_requested_indexes(self, tmp_path, two_slide_prs):
        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)
        ):
            paths = render_slide_thumbnails(
                two_slide_prs, out_dir=tmp_path, slide_indexes=[1]
            )

        assert len(paths) == 1
        assert paths[0].name.endswith("1.png")

    def it_raises_when_index_is_out_of_range(self, tmp_path, two_slide_prs):
        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)
        ):
            with pytest.raises(IndexError, match="out of range"):
                render_slide_thumbnails(
                    two_slide_prs, out_dir=tmp_path, slide_indexes=[5]
                )

    def it_returns_bytes_when_asked(self, tmp_path, two_slide_prs):
        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)
        ):
            data = render_slide_thumbnails(
                two_slide_prs, out_dir=tmp_path, return_bytes=True
            )

        assert all(isinstance(d, bytes) for d in data)
        assert data[0].startswith(b"\x89PNG")

    def it_raises_unavailable_when_soffice_is_missing(self, two_slide_prs):
        with patch("power_pptx.render.shutil.which", return_value=None):
            with pytest.raises(ThumbnailRendererUnavailable, match="install LibreOffice"):
                render_slide_thumbnails(two_slide_prs)

    def it_raises_when_soffice_exits_non_zero(self, tmp_path, two_slide_prs):
        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice",
            side_effect=_fake_soffice_run(tmp_path, exit_code=1, stderr=b"boom"),
        ):
            with pytest.raises(ThumbnailRendererError, match="status 1"):
                render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

    def it_raises_when_soffice_produces_no_pngs(self, tmp_path, two_slide_prs):
        # ``strategy="png"`` skips the PDF-split fallback so callers can
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

        def _capture(soffice_bin, deck_path, out_dir, timeout, env=None):
            captured["timeout"] = timeout
            return _fake_soffice_run(tmp_path)(soffice_bin, deck_path, out_dir, timeout)

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_capture
        ):
            render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

        assert captured["timeout"] == DEFAULT_TIMEOUT_SECONDS

    def it_honours_custom_soffice_bin(self, tmp_path, two_slide_prs):
        captured = {}

        def _capture(soffice_bin, deck_path, out_dir, timeout, env=None):
            captured["bin"] = soffice_bin
            return _fake_soffice_run(tmp_path)(soffice_bin, deck_path, out_dir, timeout)

        with patch("power_pptx.render.shutil.which", return_value="/opt/libre/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_capture
        ):
            render_slide_thumbnails(
                two_slide_prs, out_dir=tmp_path, soffice_bin="/opt/libre/soffice"
            )

        assert captured["bin"] == "/opt/libre/soffice"


class DescribeRenderSlideThumbnail:
    def it_renders_the_specific_slide(self, tmp_path, two_slide_prs):
        slide = two_slide_prs.slides[1]

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)
        ):
            target = tmp_path / "out" / "slide.png"
            path = render_slide_thumbnail(slide, out_path=target)

        assert path == target
        assert path.exists()

    def it_returns_bytes_when_asked(self, tmp_path, two_slide_prs):
        slide = two_slide_prs.slides[0]

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)
        ):
            data = render_slide_thumbnail(slide, return_bytes=True)

        assert isinstance(data, bytes)
        assert data.startswith(b"\x89PNG")


class DescribePresentationConvenienceMethods:
    def it_exposes_render_thumbnails_on_presentation(self, tmp_path, two_slide_prs):
        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)
        ):
            paths = two_slide_prs.render_thumbnails(out_dir=tmp_path)

        assert len(paths) == 2

    def it_exposes_render_thumbnail_on_slide(self, tmp_path, two_slide_prs):
        slide = two_slide_prs.slides[0]

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)
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

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=runner
        ):
            paths = render_slide_thumbnails(prs, out_dir=tmp_path)

        # With natural sort, slide #2 (index 1) is the second entry — not #10.
        assert [p.name for p in paths] == names

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
                prs, out_dir=tmp_path, slide_indexes=[9]
            )

        assert paths[0].name == "deck-10.png"


class DescribePngFiltering:
    """`render_slide_thumbnails` must ignore PNGs already in `out_dir`."""

    def it_ignores_preexisting_pngs_in_the_output_directory(self, tmp_path, two_slide_prs):
        # Drop a stray PNG in the directory before rendering — perhaps
        # left over from a previous job or simply present in a shared
        # artifacts folder.
        (tmp_path / "stale.png").write_bytes(b"\x89PNG\r\n\x1a\nstale")

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)
        ):
            paths = render_slide_thumbnails(two_slide_prs, out_dir=tmp_path)

        names = {p.name for p in paths}
        assert "stale.png" not in names
        assert len(paths) == 2  # two slides, not three

    def it_keeps_indexes_aligned_when_strays_are_present(self, tmp_path, two_slide_prs):
        # A stray that would lex-sort *between* the two genuine outputs.
        (tmp_path / "slide05.png").write_bytes(b"\x89PNG\r\n\x1a\nstale")

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)
        ):
            paths = render_slide_thumbnails(
                two_slide_prs, out_dir=tmp_path, slide_indexes=[1]
            )

        # Without the filter we'd risk returning slide05.png; with it,
        # index 1 maps to the genuine second render (slide1.png from the
        # fake runner, which writes slide{0,1}.png).
        assert paths[0].name == "slide1.png"


class DescribePdfFallback:
    """When ``--convert-to png`` only emits one slide, fall back to PDF split."""

    def _fake_pdf_run(self, work_dir, *, exit_code=0, stderr=b""):
        from subprocess import CompletedProcess

        def _runner(soffice_bin, deck_path, out_dir, timeout, env=None):
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
        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice",
            side_effect=_fake_soffice_run(tmp_path, num_slides=1),
        ), patch(
            "power_pptx.render._run_soffice_pdf",
            side_effect=self._fake_pdf_run(tmp_path),
        ), patch(
            "power_pptx.render._pdf_to_pngs",
            side_effect=self._fake_pdf_split(tmp_path, num_pages=2),
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

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_no_png
        ), patch(
            "power_pptx.render._run_soffice_pdf",
            side_effect=self._fake_pdf_run(tmp_path),
        ), patch(
            "power_pptx.render._pdf_to_pngs",
            side_effect=self._fake_pdf_split(tmp_path, num_pages=2),
        ):
            paths = render_slide_thumbnails(
                two_slide_prs, out_dir=tmp_path, strategy="pdf"
            )

        assert len(paths) == 2
        assert not png_called

    def it_does_not_return_stale_pages_from_an_earlier_render(self, tmp_path, two_slide_prs):
        one_slide = Presentation()
        one_slide.slides.add_slide(one_slide.slide_layouts[6])
        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice_pdf", side_effect=self._fake_pdf_run(tmp_path)
        ), patch(
            "power_pptx.render._pdf_to_pngs",
            side_effect=self._fake_pdf_split(tmp_path, num_pages=2),
        ):
            render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, strategy="pdf")

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice_pdf", side_effect=self._fake_pdf_run(tmp_path)
        ), patch(
            "power_pptx.render._pdf_to_pngs",
            side_effect=self._fake_pdf_split(tmp_path, num_pages=1),
        ):
            paths = render_slide_thumbnails(one_slide, out_dir=tmp_path, strategy="pdf")

        assert [path.name for path in paths] == ["_render_input-page-1.png"]

    def it_rejects_an_incomplete_pdf_render(self, tmp_path, two_slide_prs):
        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice_pdf", side_effect=self._fake_pdf_run(tmp_path)
        ), patch(
            "power_pptx.render._pdf_to_pngs",
            side_effect=self._fake_pdf_split(tmp_path, num_pages=1),
        ), pytest.raises(ThumbnailRendererError, match="1 PNG.*2-slide deck"):
            render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, strategy="pdf")

    def it_raises_when_neither_pipeline_produces_pngs(self, tmp_path, two_slide_prs):
        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice",
            side_effect=_fake_soffice_run(tmp_path, num_slides=0),
        ), patch(
            "power_pptx.render._run_soffice_pdf",
            side_effect=self._fake_pdf_run(tmp_path, exit_code=1, stderr=b"boom"),
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

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)
        ), patch("power_pptx.render.tempfile.TemporaryDirectory", side_effect=_spy_tmp):
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

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_fake_soffice_run(tmp_path)
        ), patch("power_pptx.render.tempfile.TemporaryDirectory", side_effect=_spy_tmp):
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

    def it_rejects_missing_folders(self, tmp_path):
        from power_pptx.render import _soffice_env

        with pytest.raises(ValueError, match="does not exist"):
            _soffice_env(tmp_path, [tmp_path / "missing"])

    def it_hands_the_environment_to_soffice(self, tmp_path, two_slide_prs):
        captured = {}

        def _capture(soffice_bin, deck_path, out_dir, timeout, env=None):
            captured["env"] = env
            return _fake_soffice_run(tmp_path)(soffice_bin, deck_path, out_dir, timeout)

        with patch("power_pptx.render.shutil.which", return_value="/usr/bin/soffice"), patch(
            "power_pptx.render._run_soffice", side_effect=_capture
        ):
            render_slide_thumbnails(two_slide_prs, out_dir=tmp_path, font_dirs=[self.FONTS])

        assert captured["env"]["FONTCONFIG_FILE"].endswith("fonts.conf")
