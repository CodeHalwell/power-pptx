"""Tests for the figure-embedding adapters in `power_pptx.design.figures`.

The adapters delegate to optional third-party libraries (Plotly, Kaleido,
Matplotlib, Playwright); these tests stub those dependencies so the
suite runs without them and exercises the adapter wiring rather than
the renderers themselves.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

from power_pptx import Presentation
from power_pptx.design.figures import (
    FigureBackendUnavailable,
    add_html_figure,
    add_matplotlib_figure,
    add_plotly_figure,
    add_svg_figure,
)
from power_pptx.design.recipes import figure_slide
from power_pptx.enum.shapes import MSO_SHAPE_TYPE
from power_pptx.util import Inches


@pytest.fixture
def slide():
    prs = Presentation()
    return prs.slides.add_slide(prs.slide_layouts[6])


# A minimal valid PNG (1×1 transparent) so add_picture's image-format
# detection succeeds without pulling Pillow into the test path.
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfc\xff\xff?\x03\x00\x07\x06"
    b"\x02\xff\xa3\x9d\x9a\xed\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _FakePlotlyFigure:
    """Stand-in for plotly.graph_objects.Figure that captures to_image args."""

    def __init__(self, blob=_TINY_PNG):
        self._blob = blob
        self.to_image_calls = []

    def to_image(self, **kwargs):
        self.to_image_calls.append(kwargs)
        return self._blob


class DescribeAddPlotlyFigure:
    def it_routes_a_plotly_figure_to_add_picture_when_format_is_png(self, slide):
        fig = _FakePlotlyFigure()
        before = len(list(slide.shapes))
        add_plotly_figure(
            slide, fig,
            Inches(1), Inches(1), Inches(4), Inches(3),
            format="png",
        )
        # Exactly one new shape — the embedded picture.
        after = list(slide.shapes)
        assert len(after) == before + 1
        assert after[-1].shape_type == MSO_SHAPE_TYPE.PICTURE
        # Plotly's renderer was asked for PNG.
        assert fig.to_image_calls
        assert fig.to_image_calls[0]["format"] == "png"

    def it_picks_png_in_auto_when_cairosvg_is_missing(self, slide):
        fig = _FakePlotlyFigure()
        # Force the cairosvg-import sniff to fail by removing the
        # module from sys.modules and shadowing it with an importer
        # that always raises.
        import builtins

        real_import = builtins.__import__

        def _no_cairosvg(name, *args, **kwargs):
            if name == "cairosvg":
                raise ImportError("simulated missing cairosvg")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_no_cairosvg):
            add_plotly_figure(slide, fig, Inches(1), Inches(1), Inches(4), Inches(3))
        assert fig.to_image_calls[0]["format"] == "png"

    def it_rejects_non_plotly_objects(self, slide):
        with pytest.raises(TypeError, match="Plotly Figure"):
            add_plotly_figure(slide, object(), Inches(1), Inches(1))

    def it_wraps_kaleido_failures_in_FigureBackendUnavailable(self, slide):
        broken = MagicMock()
        broken.to_image.side_effect = RuntimeError(
            "kaleido binary not found"
        )
        with pytest.raises(FigureBackendUnavailable, match="kaleido"):
            add_plotly_figure(
                slide, broken,
                Inches(1), Inches(1), Inches(4), Inches(3),
                format="png",
            )


class _FakeMatplotlibFigure:
    def __init__(self, blob=_TINY_PNG):
        self._blob = blob
        self.savefig_calls = []

    def savefig(self, buf, *, format, **kwargs):
        self.savefig_calls.append((format, kwargs))
        buf.write(self._blob if format == "png" else _STUB_SVG)


_STUB_SVG = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
    b'<rect width="10" height="10" fill="red"/></svg>'
)


class DescribeAddMatplotlibFigure:
    def it_renders_via_savefig_and_embeds(self, slide):
        fig = _FakeMatplotlibFigure()
        before = len(list(slide.shapes))
        add_matplotlib_figure(
            slide, fig, Inches(1), Inches(1), Inches(4), Inches(3),
            format="png",
        )
        after = list(slide.shapes)
        assert len(after) == before + 1
        assert after[-1].shape_type == MSO_SHAPE_TYPE.PICTURE
        assert fig.savefig_calls[0][0] == "png"

    def it_rejects_non_matplotlib_objects(self, slide):
        with pytest.raises(TypeError, match="Matplotlib Figure"):
            add_matplotlib_figure(slide, object(), Inches(1), Inches(1))


class DescribeAddSvgFigure:
    def it_delegates_to_add_svg_picture_with_explicit_png_fallback(self, slide):
        # Bypass cairosvg by passing png_fallback explicitly.
        before = len(list(slide.shapes))
        add_svg_figure(
            slide, _STUB_SVG,
            Inches(1), Inches(1), Inches(4), Inches(3),
            png_fallback=_TINY_PNG,
        )
        after = list(slide.shapes)
        assert len(after) == before + 1
        assert after[-1].shape_type == MSO_SHAPE_TYPE.PICTURE


class DescribeAddHtmlFigure:
    def it_raises_clearly_when_playwright_is_missing(self, slide):
        import builtins

        real_import = builtins.__import__

        def _no_playwright(name, *args, **kwargs):
            if name.startswith("playwright"):
                raise ImportError("simulated missing playwright")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_no_playwright):
            with pytest.raises(FigureBackendUnavailable, match="playwright"):
                add_html_figure(slide, "<h1>hi</h1>", Inches(1), Inches(1))


class DescribeFigureSlideDispatch:
    def it_dispatches_a_plotly_figure(self):
        prs = Presentation()
        fig = _FakePlotlyFigure()
        slide = figure_slide(prs, title="Plot", figure=fig, figure_format="png")
        pictures = [
            s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE
        ]
        assert len(pictures) == 1

    def it_dispatches_a_matplotlib_figure(self):
        prs = Presentation()
        fig = _FakeMatplotlibFigure()
        slide = figure_slide(prs, title="Plot", figure=fig, figure_format="png")
        pictures = [
            s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE
        ]
        assert len(pictures) == 1

    def it_dispatches_inline_svg_bytes(self):
        prs = Presentation()
        # Pass png_fallback via add_svg_figure can't be threaded
        # through figure_slide; instead, this path needs cairosvg.
        # Mock the rasteriser so we don't depend on cairosvg.
        with patch(
            "power_pptx._svg.rasterize_svg", return_value=_TINY_PNG,
        ):
            slide = figure_slide(prs, title="SVG", figure=_STUB_SVG)
        pictures = [
            s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE
        ]
        assert len(pictures) == 1

    def it_renders_a_caption_when_provided(self):
        prs = Presentation()
        fig = _FakePlotlyFigure()
        slide = figure_slide(
            prs, title="Plot", figure=fig, figure_format="png",
            caption="Source: internal data",
        )
        texts = [
            p.text
            for sh in slide.shapes
            if sh.has_text_frame
            for p in sh.text_frame.paragraphs
        ]
        assert any("Source" in t for t in texts)

    def it_rejects_unrecognisable_figures(self):
        prs = Presentation()
        with pytest.raises(TypeError, match="dispatch"):
            figure_slide(prs, title="x", figure=12345)
