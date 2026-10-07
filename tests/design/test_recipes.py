"""Unit-test suite for :mod:`power_pptx.design.recipes`."""

from __future__ import annotations

import math
import os
import re

import pytest

from power_pptx import Presentation
from power_pptx.design.recipes import (
    bullet_slide,
    chart_slide,
    code_slide,
    comparison_slide,
    image_hero_slide,
    kpi_slide,
    quote_slide,
    section_divider,
    table_slide,
    timeline_slide,
    title_slide,
)
from power_pptx.design.tokens import DesignTokens
from power_pptx.dml.color import RGBColor
from power_pptx.enum.shapes import MSO_SHAPE_TYPE
from power_pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from power_pptx.util import Emu, Inches, Pt

_TEST_IMAGE = os.path.join(os.path.dirname(__file__), "..", "test_files", "monty-truth.png")


@pytest.fixture
def prs():
    return Presentation()


@pytest.fixture
def tokens():
    return DesignTokens.from_dict(
        {
            "palette": {
                "primary": "#3C2F80",
                "neutral": "#222222",
                "muted": "#777777",
                "surface": "#F4F2FB",
                "on_primary": "#FFFFFF",
                "positive": "#00853E",
                "negative": "#B00020",
            },
            "typography": {
                "heading": {"family": "Inter", "size": Pt(36), "bold": True},
                "body": {"family": "Inter", "size": Pt(16)},
            },
            "shadows": {
                "card": {
                    "blur_radius": Pt(8),
                    "distance": Pt(2),
                    "direction": 90.0,
                    "color": RGBColor(0, 0, 0),
                    "alpha": 0.2,
                },
            },
        }
    )


def _runs(slide):
    out = []
    for sh in slide.shapes:
        if not sh.has_text_frame:
            continue
        for p in sh.text_frame.paragraphs:
            for r in p.runs:
                out.append(r)
    return out


def _paragraph_texts(slide):
    return [p.text for sh in slide.shapes if sh.has_text_frame for p in sh.text_frame.paragraphs]


def _presentation(aspect):
    """Return a fresh Presentation at the ``"4:3"`` (default) or ``"16:9"`` size."""
    prs = Presentation()
    if aspect == "16:9":
        prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    return prs


def _lint_problems(slide):
    """ERROR and WARNING lint issues on *slide*, rendered as strings."""
    return [str(issue) for issue in slide.lint(min_severity="warning").issues]


def _extents(shape):
    """Return ``(left, top, right, bottom)`` of *shape* in EMU."""
    left, top = int(shape.left), int(shape.top)
    return left, top, left + int(shape.width), top + int(shape.height)


class DescribeTitleSlide:
    def it_appends_a_slide_to_the_presentation(self, prs):
        before = len(prs.slides)
        slide = title_slide(prs, title="Hello")
        assert len(prs.slides) == before + 1
        assert slide is prs.slides[-1]

    def it_writes_the_title_text(self, prs):
        slide = title_slide(prs, title="Q4 Review")
        assert any("Q4 Review" in t for t in _paragraph_texts(slide))

    def it_writes_the_subtitle_when_provided(self, prs):
        slide = title_slide(prs, title="T", subtitle="April 2026")
        assert any("April 2026" in t for t in _paragraph_texts(slide))

    def it_omits_the_subtitle_when_not_provided(self, prs):
        slide = title_slide(prs, title="T")
        # exactly one textbox: the title
        textboxes = [s for s in slide.shapes if s.has_text_frame]
        assert len(textboxes) == 1

    def it_applies_the_token_palette_to_the_title(self, prs, tokens):
        slide = title_slide(prs, title="Hi", tokens=tokens)
        runs = _runs(slide)
        assert runs[0].font.color.rgb == RGBColor(0x3C, 0x2F, 0x80)
        assert runs[0].font.name == "Inter"

    def it_centers_the_title(self, prs):
        slide = title_slide(prs, title="Hi")
        title_para = next(
            p for s in slide.shapes if s.has_text_frame for p in s.text_frame.paragraphs
        )
        assert title_para.alignment == PP_ALIGN.CENTER

    def it_applies_an_optional_transition(self, prs):
        from power_pptx.enum.presentation import MSO_TRANSITION_TYPE

        slide = title_slide(prs, title="Hi", transition="morph")
        assert slide.transition.kind == MSO_TRANSITION_TYPE.MORPH

    def it_raises_on_unknown_transition(self, prs):
        with pytest.raises(ValueError):
            title_slide(prs, title="Hi", transition="not_a_transition")


class DescribeBulletSlide:
    def it_writes_one_paragraph_per_bullet_plus_title(self, prs):
        slide = bullet_slide(prs, title="T", bullets=["a", "b", "c"])
        body_box = [s for s in slide.shapes if s.has_text_frame][1]
        # 3 bullets => 3 paragraphs
        assert len(body_box.text_frame.paragraphs) == 3

    def it_prefixes_a_bullet_glyph(self, prs):
        slide = bullet_slide(prs, title="T", bullets=["alpha"])
        assert any("•" in t and "alpha" in t for t in _paragraph_texts(slide))

    def it_applies_token_typography_to_bullets(self, prs, tokens):
        slide = bullet_slide(prs, title="T", bullets=["x"], tokens=tokens)
        runs = _runs(slide)
        # last run is the bullet
        assert runs[-1].font.name == "Inter"
        assert runs[-1].font.size == Pt(16)


class DescribeKpiSlide:
    def it_renders_one_card_per_kpi(self, prs):
        slide = kpi_slide(
            prs,
            title="Metrics",
            kpis=[
                {"label": "ARR", "value": "$182M", "delta": +0.27},
                {"label": "NDR", "value": "131%", "delta": -0.03},
            ],
        )
        cards = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE]
        assert len(cards) == 2

    def it_writes_label_value_and_delta_text(self, prs):
        slide = kpi_slide(
            prs,
            title="Metrics",
            kpis=[{"label": "ARR", "value": "$182M", "delta": +0.27}],
        )
        texts = " ".join(_paragraph_texts(slide))
        assert "ARR" in texts
        assert "$182M" in texts
        assert "27%" in texts

    def it_handles_zero_kpis(self, prs):
        slide = kpi_slide(prs, title="None today", kpis=[])
        # only the title remains
        textboxes = [s for s in slide.shapes if s.has_text_frame]
        assert len(textboxes) == 1

    def it_tints_positive_and_negative_deltas_differently(self, prs, tokens):
        slide = kpi_slide(
            prs,
            title="Metrics",
            kpis=[
                {"label": "Up", "value": "1", "delta": +0.1},
                {"label": "Down", "value": "1", "delta": -0.1},
            ],
            tokens=tokens,
        )
        delta_runs = [
            run
            for sh in slide.shapes
            if sh.has_text_frame
            for p in sh.text_frame.paragraphs
            for run in p.runs
            if "%" in run.text
        ]
        colors = {run.font.color.rgb for run in delta_runs}
        assert RGBColor(0x00, 0x85, 0x3E) in colors
        assert RGBColor(0xB0, 0x00, 0x20) in colors

    def it_treats_fraction_deltas_as_percentages(self, prs):
        slide = kpi_slide(
            prs,
            title="m",
            kpis=[{"label": "L", "value": "v", "delta": 0.27}],
        )
        texts = " ".join(_paragraph_texts(slide))
        assert "+27%" in texts

    def it_renders_large_numeric_deltas_as_raw_values(self, prs):
        # The pre-fix behaviour multiplied by 100, turning ``14`` into
        # ``+1400%``.  Auto-detect now formats ``|delta| > 1`` as the raw
        # number with one decimal so callers can pass percentage points
        # directly without surprise.
        slide = kpi_slide(
            prs,
            title="m",
            kpis=[{"label": "L", "value": "v", "delta": 14.0}],
        )
        texts = " ".join(_paragraph_texts(slide))
        assert "+14.0" in texts
        assert "1400%" not in texts

    def it_uses_delta_text_verbatim(self, prs):
        slide = kpi_slide(
            prs,
            title="m",
            kpis=[{"label": "L", "value": "v", "delta_text": "+8 pts"}],
        )
        texts = " ".join(_paragraph_texts(slide))
        assert "+8 pts" in texts

    def it_renders_string_delta_verbatim(self, prs):
        slide = kpi_slide(
            prs,
            title="m",
            kpis=[{"label": "L", "value": "v", "delta": "−$2.3M"}],
        )
        texts = " ".join(_paragraph_texts(slide))
        assert "−$2.3M" in texts

    def it_applies_the_card_shadow_token(self, prs, tokens):
        slide = kpi_slide(
            prs,
            title="Metrics",
            kpis=[{"label": "ARR", "value": "$182M"}],
            tokens=tokens,
        )
        card = next(s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE)
        assert card.shadow.blur_radius == Pt(8)
        assert card.shadow.distance == Pt(2)


class DescribeQuoteSlide:
    def it_wraps_the_quote_in_curly_quotes(self, prs):
        slide = quote_slide(prs, quote="Hello world")
        texts = _paragraph_texts(slide)
        assert any("“Hello world”" in t for t in texts)

    def it_renders_the_attribution_when_provided(self, prs):
        slide = quote_slide(prs, quote="Q", attribution="Ada")
        texts = _paragraph_texts(slide)
        assert any("Ada" in t for t in texts)

    def it_omits_the_attribution_when_missing(self, prs):
        slide = quote_slide(prs, quote="Q")
        textboxes = [s for s in slide.shapes if s.has_text_frame]
        assert len(textboxes) == 1

    def it_does_not_double_an_existing_attribution_dash(self, prs):
        # Callers who already wrote ``"— Ada Lovelace"`` shouldn't end up
        # with ``"— — Ada Lovelace"`` in the rendered slide.
        slide = quote_slide(prs, quote="Q", attribution="— Ada Lovelace")
        texts = _paragraph_texts(slide)
        assert any(t == "— Ada Lovelace" for t in texts)
        assert not any("— — Ada Lovelace" in t for t in texts)

    def it_strips_a_leading_hyphen_or_endash(self, prs):
        slide = quote_slide(prs, quote="Q", attribution="- Ada")
        texts = _paragraph_texts(slide)
        assert any(t == "— Ada" for t in texts)


class DescribeImageHeroSlide:
    def it_adds_a_picture_at_full_slide_extent(self, prs):
        slide = image_hero_slide(prs, title="Demo", image=_TEST_IMAGE)
        pics = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
        assert len(pics) == 1
        assert pics[0].left == 0
        assert pics[0].top == 0
        assert pics[0].width == prs.slide_width
        assert pics[0].height == prs.slide_height

    def it_renders_the_caption_when_provided(self, prs):
        slide = image_hero_slide(prs, title="T", image=_TEST_IMAGE, caption="A short caption")
        assert any("A short caption" in t for t in _paragraph_texts(slide))

    def it_uses_the_token_primary_color_for_the_band(self, prs, tokens):
        slide = image_hero_slide(prs, title="T", image=_TEST_IMAGE, tokens=tokens)
        bands = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE]
        assert bands
        assert bands[0].fill.fore_color.rgb == RGBColor(0x3C, 0x2F, 0x80)


class DescribeSectionDivider:
    def it_appends_a_divider_slide(self, prs):
        before = len(prs.slides)
        section_divider(prs, title="Part Two")
        assert len(prs.slides) == before + 1

    def it_renders_eyebrow_when_provided(self, prs):
        slide = section_divider(prs, title="X", eyebrow="PART TWO")
        assert any("PART TWO" in t for t in _paragraph_texts(slide))

    def it_renders_progress_dots(self, prs):
        slide = section_divider(prs, title="X", progress=(3, 7))
        # 1 backdrop rectangle + 7 dots = 8 auto-shapes
        autoshapes = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE]
        assert len(autoshapes) == 1 + 7

    def it_rejects_invalid_progress(self, prs):
        with pytest.raises(ValueError, match="progress must be"):
            section_divider(prs, title="X", progress=(8, 7))


class DescribeChartSlide:
    def it_appends_a_slide_with_a_chart(self, prs):
        slide = chart_slide(
            prs,
            title="Revenue",
            chart_type="line",
            categories=["Q1", "Q2", "Q3"],
            series=[{"name": "Rev", "values": [10, 20, 30]}],
        )
        graphic_frames = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.CHART]
        assert len(graphic_frames) == 1

    def it_supports_known_chart_types(self, prs):
        for kind in ("line", "bar", "column", "pie", "area"):
            slide = chart_slide(
                prs,
                title="x",
                chart_type=kind,
                categories=["A", "B"],
                series=[{"name": "S", "values": [1, 2]}],
            )
            assert any(s.shape_type == MSO_SHAPE_TYPE.CHART for s in slide.shapes)

    def it_accepts_every_chart_type_its_docstring_lists(self, prs):
        # The docstring once promised "scatter", which the recipe rejects.
        intro = chart_slide.__doc__.split("*categories*")[0]
        documented = re.findall(r'``"([a-z_]+)"``', intro)
        assert {"line", "bar", "column", "pie", "area", "line_markers", "doughnut"} <= set(
            documented
        )
        for kind in documented:
            slide = chart_slide(
                prs,
                title="x",
                chart_type=kind,
                categories=["A", "B"],
                series=[{"name": "S", "values": [1, 2]}],
            )
            assert any(s.shape_type == MSO_SHAPE_TYPE.CHART for s in slide.shapes), kind

    def it_points_to_xy_chart_data_instead_of_listing_scatter_as_a_type(self):
        assert '"scatter"' not in chart_slide.__doc__
        assert "XyChartData" in chart_slide.__doc__

    def it_rejects_unknown_chart_types(self, prs):
        with pytest.raises(ValueError, match="Unknown chart_type"):
            chart_slide(
                prs,
                title="x",
                chart_type="radar",
                categories=["A"],
                series=[{"name": "S", "values": [1]}],
            )


class DescribeTableSlide:
    def it_appends_a_slide_with_a_table(self, prs):
        slide = table_slide(
            prs,
            title="T",
            columns=["A", "B"],
            rows=[["1", "2"], ["3", "4"]],
        )
        tables = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE]
        assert len(tables) == 1
        # 2 data rows + 1 header = 3 rows
        assert len(tables[0].table.rows) == 3
        assert len(tables[0].table.columns) == 2

    def it_uses_token_palette_for_header(self, prs, tokens):
        slide = table_slide(
            prs,
            title="T",
            columns=["A"],
            rows=[["1"]],
            tokens=tokens,
        )
        table = next(s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE).table
        header_cell = table.cell(0, 0)
        assert header_cell.fill.fore_color.rgb == RGBColor(0x3C, 0x2F, 0x80)

    def it_rejects_zero_columns(self, prs):
        with pytest.raises(ValueError, match="at least one column"):
            table_slide(prs, title="T", columns=[], rows=[])


class DescribeCodeSlide:
    def it_appends_a_panel_with_code_text(self, prs):
        slide = code_slide(prs, title="C", code="x = 1\ny = 2")
        texts = " ".join(_paragraph_texts(slide))
        assert "x = 1" in texts
        assert "y = 2" in texts

    def it_uses_a_monospace_font(self, prs):
        slide = code_slide(prs, title="C", code="x = 1")
        # Find the code run (not the title) and verify the font name
        # is a monospace family.
        code_runs = []
        for sh in slide.shapes:
            if not sh.has_text_frame:
                continue
            for p in sh.text_frame.paragraphs:
                for r in p.runs:
                    if r.text == "x = 1":
                        code_runs.append(r)
        assert code_runs
        assert (
            "Consolas" in (code_runs[0].font.name or "")
            or "Cascadia" in (code_runs[0].font.name or "")
            or "monospace" in (code_runs[0].font.name or "")
        )


def _code_box(slide):
    """The text box ``code_slide`` puts the code in: the last shape that holds any text."""
    return next(
        s for s in reversed(list(slide.shapes)) if s.has_text_frame and s.text_frame.text.strip()
    )


def _code_sizes(slide):
    return {r.font.size.pt for p in _code_box(slide).text_frame.paragraphs for r in p.runs}


_CODE_30 = "\n".join(
    f"def f{i}(x):  # {i}" if i % 2 == 0 else f"    return x * {i}" for i in range(30)
)


class DescribeCodeSlideFit:
    """Code is set in one real monospace face and shrunk to fit its panel."""

    def it_names_a_single_monospace_typeface(self, prs):
        # OOXML ``a:latin typeface`` holds one family name; a CSS-style stack makes
        # PowerPoint and LibreOffice fall back to a proportional face.
        slide = code_slide(prs, title="C", code="x = 1\ny = 2")
        names = {r.font.name for p in _code_box(slide).text_frame.paragraphs for r in p.runs}
        assert names == {"Consolas"}

    def it_keeps_that_name_when_highlighting(self, prs):
        pytest.importorskip("pygments")
        slide = code_slide(prs, title="C", code="def f(x):\n    return x", language="python")
        names = {r.font.name for p in _code_box(slide).text_frame.paragraphs for r in p.runs}
        assert names == {"Consolas"}

    def it_keeps_the_token_size_for_a_short_snippet(self, prs):
        slide = code_slide(prs, title="C", code="x = 1\ny = 2\nprint(x + y)")
        assert _code_sizes(slide) == {14.0}

    @pytest.mark.parametrize("aspect", ["4:3", "16:9"])
    @pytest.mark.parametrize("n_lines", [12, 20, 24, 30, 32])
    def it_shrinks_a_long_snippet_until_it_fits_its_panel(self, aspect, n_lines):
        code = "\n".join(f"line_{i} = compute({i})  # step {i}" for i in range(n_lines))
        slide = code_slide(_presentation(aspect), title="Example", code=code)
        box = _code_box(slide)
        (size,) = _code_sizes(slide)
        assert 9 <= size <= 14
        assert _estimated_text_height_pt(box) <= _inner_height_pt(box)
        if n_lines > 20:
            assert size < 14

    @pytest.mark.parametrize("aspect", ["4:3", "16:9"])
    def it_keeps_the_code_inside_the_panel_and_the_panel_on_the_slide(self, aspect):
        prs = _presentation(aspect)
        slide = code_slide(prs, title="Example", code=_CODE_30)
        box = _code_box(slide)
        panel = next(
            s
            for s in slide.shapes
            if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and s.width > box.width
        )
        b_left, b_top, b_right, b_bottom = _extents(box)
        p_left, p_top, p_right, p_bottom = _extents(panel)
        assert p_left <= b_left
        assert p_top <= b_top
        assert b_right <= p_right
        assert b_bottom <= p_bottom
        assert p_bottom <= int(prs.slide_height) - int(Inches(0.5))
        assert _lint_problems(slide) == []

    def it_counts_a_wrapped_long_line_against_the_height(self, prs):
        # Fourteen 150-character lines wrap to two lines each on a 4:3 slide, so
        # they need as much height as twenty-eight short ones.
        code = "\n".join("x" * 150 for _ in range(14))
        slide = code_slide(prs, title="Wide", code=code)
        box = _code_box(slide)
        (size,) = _code_sizes(slide)
        assert size < 14
        assert _estimated_text_height_pt(box) <= _inner_height_pt(box)

    def it_asks_the_renderer_to_shrink_as_a_fallback(self, prs):
        slide = code_slide(prs, title="C", code=_CODE_30)
        assert _code_box(slide).text_frame.auto_size == MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        assert _code_box(slide).text_frame.word_wrap is True

    def it_holds_blank_lines_to_the_code_size(self, prs):
        # An empty paragraph takes its height from a:endParaRPr; left alone it would
        # fall back to the 18 pt default and blow the fit.
        slide = code_slide(prs, title="C", code="\n\n".join(f"x{i} = {i}" for i in range(12)))
        (size,) = _code_sizes(slide)
        assert size == 12  # 23 lines including the blank ones: shrunk, but not to the floor
        for paragraph in _code_box(slide).text_frame.paragraphs:
            end = paragraph._p.endParaRPr
            assert end is not None
            assert end.get("sz") == str(int(size * 100))

    def it_expands_tabs_so_indentation_cannot_outgrow_the_fit(self, prs):
        slide = code_slide(prs, title="C", code="if x:\n\treturn 1")
        texts = [p.text for p in _code_box(slide).text_frame.paragraphs]
        assert texts == ["if x:", "    return 1"]

    @staticmethod
    def _contrast_with_panel(slide):
        from power_pptx.lint import _contrast_ratio

        box = _code_box(slide)
        panel = next(
            s
            for s in slide.shapes
            if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and s.width > box.width
        )
        text = box.text_frame.paragraphs[0].runs[0].font.color.rgb
        return _contrast_ratio(text, panel.fill.fore_color.rgb)

    def it_reads_against_the_default_panel_when_there_are_no_tokens(self, prs):
        # The token-less panel is dark; the code must not be dark-on-dark.
        slide = code_slide(prs, title="C", code="x = 1")
        assert self._contrast_with_panel(slide) >= 4.5

    def it_reads_against_a_dark_panel_whose_neutral_is_dark_too(self, prs):
        # Tokens with a neutral but no surface fall back to the dark panel as well.
        tokens = DesignTokens.from_dict({"palette": {"neutral": "#222222"}})
        slide = code_slide(prs, title="C", code="x = 1", tokens=tokens)
        assert self._contrast_with_panel(slide) >= 4.5

    def it_keeps_a_neutral_that_already_reads_on_the_surface(self, prs):
        tokens = DesignTokens.from_dict(
            {"palette": {"neutral": "#222222", "surface": "#F4F2FB", "primary": "#3C2F80"}}
        )
        slide = code_slide(prs, title="C", code="x = 1", tokens=tokens)
        run = _code_box(slide).text_frame.paragraphs[0].runs[0]
        assert run.font.color.rgb == RGBColor(0x22, 0x22, 0x22)

    def it_keeps_punctuation_legible_when_highlighting_on_the_default_panel(self, prs):
        pytest.importorskip("pygments")
        from power_pptx.lint import _contrast_ratio

        slide = code_slide(prs, title="C", code="f(x)", language="python")
        box = _code_box(slide)
        panel = next(
            s
            for s in slide.shapes
            if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and s.width > box.width
        )
        backdrop = panel.fill.fore_color.rgb
        runs = box.text_frame.paragraphs[0].runs
        assert [r.text for r in runs][:2] == ["f", "("]
        assert all(
            _contrast_ratio(r.font.color.rgb, backdrop) >= 4.5 for r in runs if r.text == "("
        )

    def it_refuses_a_snippet_that_cannot_fit_on_one_slide(self, prs):
        code = "\n".join(f"x{i} = {i}" for i in range(80))
        with pytest.raises(ValueError, match="split"):
            code_slide(prs, title="Too long", code=code)
        assert len(prs.slides) == 0

    def it_says_how_many_lines_do_fit(self, prs):
        with pytest.raises(ValueError, match=r"about \d+ lines"):
            code_slide(prs, title="Too long", code="\n".join("x" for _ in range(80)))

    def it_fits_a_highlighted_snippet_too(self, prs):
        pytest.importorskip("pygments")
        slide = code_slide(prs, title="C", code=_CODE_30, language="python")
        box = _code_box(slide)
        assert len(_code_sizes(slide)) == 1
        assert _estimated_text_height_pt(box) <= _inner_height_pt(box)


class DescribeTimelineSlide:
    def it_renders_one_marker_per_milestone(self, prs):
        slide = timeline_slide(
            prs,
            title="T",
            milestones=[
                {"date": "Q1", "label": "Spec", "done": True},
                {"date": "Q2", "label": "Build"},
                {"date": "Q3", "label": "Ship"},
            ],
        )
        # 1 rail + 3 dots = 4 auto-shapes
        autoshapes = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE]
        assert len(autoshapes) == 4

    def it_tints_done_milestones_with_positive_color(self, prs, tokens):
        slide = timeline_slide(
            prs,
            title="T",
            milestones=[{"date": "Q1", "label": "Spec", "done": True}],
            tokens=tokens,
        )
        # Find the milestone dot (small oval).
        ovals = [
            s
            for s in slide.shapes
            if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and s.height < 914400
        ]
        assert any(o.fill.fore_color.rgb == RGBColor(0x00, 0x85, 0x3E) for o in ovals)

    def it_rejects_empty_milestones(self, prs):
        with pytest.raises(ValueError, match="at least one"):
            timeline_slide(prs, title="T", milestones=[])


_ROADMAP = [
    {
        "date": f"2026-0{i + 1}",
        "label": f"Milestone {i + 1}: ship the integration layer",
        "done": i < 2,
    }
    for i in range(8)
]


def _estimated_text_height_pt(shape):
    """Linter-style height estimate: 0.55 em per character, 1.2 line pitch."""
    tf = shape.text_frame
    size = tf.paragraphs[0].runs[0].font.size.pt
    inner_w = (int(shape.width) - int(tf.margin_left) - int(tf.margin_right)) / 12700
    per_line = max(1.0, inner_w / (0.55 * size))
    lines = sum(max(1, math.ceil(len(p.text) / per_line)) for p in tf.paragraphs)
    return lines * size * 1.2


def _inner_height_pt(shape):
    tf = shape.text_frame
    return (int(shape.height) - int(tf.margin_top) - int(tf.margin_bottom)) / 12700


class DescribeTimelineSlideLayout:
    """The recipe's own output is physically correct on every slide size."""

    @pytest.mark.parametrize("aspect", ["4:3", "16:9"])
    @pytest.mark.parametrize("n", range(1, 9))
    def it_lints_clean_for_one_to_eight_milestones(self, aspect, n):
        slide = timeline_slide(_presentation(aspect), title="Roadmap", milestones=_ROADMAP[:n])
        assert _lint_problems(slide) == []

    @pytest.mark.parametrize("aspect", ["4:3", "16:9"])
    @pytest.mark.parametrize("n", [2, 5, 8])
    def it_lints_clean_with_token_typography(self, aspect, n, tokens):
        slide = timeline_slide(
            _presentation(aspect), title="Roadmap", milestones=_ROADMAP[:n], tokens=tokens
        )
        assert _lint_problems(slide) == []

    @pytest.mark.parametrize("aspect", ["4:3", "16:9"])
    @pytest.mark.parametrize("n", [1, 2, 3, 5, 8])
    def it_keeps_every_shape_inside_the_slide_margins(self, aspect, n):
        prs = _presentation(aspect)
        slide = timeline_slide(prs, title="Roadmap", milestones=_ROADMAP[:n])
        margin = int(Inches(0.6))
        for shape in slide.shapes:
            left, _top, right, _bottom = _extents(shape)
            assert left >= margin - 2, shape.name
            assert right <= int(prs.slide_width) - margin + 2, shape.name

    @pytest.mark.parametrize("aspect", ["4:3", "16:9"])
    def it_keeps_text_clear_of_the_rail_and_dots(self, aspect):
        slide = timeline_slide(_presentation(aspect), title="Roadmap", milestones=_ROADMAP[:5])
        dots = [
            s
            for s in slide.shapes
            if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and s.width == s.height
        ]
        assert len(dots) == 5
        band_top = min(_extents(d)[1] for d in dots)
        band_bottom = max(_extents(d)[3] for d in dots)
        text_boxes = [s for s in slide.shapes if s.has_text_frame and s.text_frame.text]
        assert len(text_boxes) == 1 + 2 * 5  # title + a date and a label per milestone
        for box in text_boxes:
            _left, top, _right, bottom = _extents(box)
            assert bottom <= band_top or top >= band_bottom, box.text_frame.text

    @pytest.mark.parametrize("aspect", ["4:3", "16:9"])
    def it_spaces_the_dots_evenly_and_symmetrically(self, aspect):
        prs = _presentation(aspect)
        slide = timeline_slide(prs, title="Roadmap", milestones=_ROADMAP[:6])
        dots = [
            s
            for s in slide.shapes
            if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and s.width == s.height
        ]
        centres = [int(d.left) + int(d.width) // 2 for d in dots]
        steps = [b - a for a, b in zip(centres, centres[1:])]
        assert max(steps) - min(steps) <= 2
        assert abs(centres[0] - (int(prs.slide_width) - centres[-1])) <= 2

    @pytest.mark.parametrize("n", [3, 8])
    def it_fits_milestone_text_inside_its_boxes_under_large_token_typography(self, n, tokens):
        # The deck's 16 pt body size must not be dropped into 0.3 in / 0.7 in boxes
        # unchecked: the recipe bakes a size at which the text actually fits.
        slide = timeline_slide(
            _presentation("4:3"), title="Roadmap", milestones=_ROADMAP[:n], tokens=tokens
        )
        boxes = [s for s in slide.shapes if s.has_text_frame and s.text_frame.text][1:]
        assert len(boxes) == 2 * n
        for box in boxes:
            size = box.text_frame.paragraphs[0].runs[0].font.size.pt
            assert size >= 9, box.text_frame.text
            assert _estimated_text_height_pt(box) <= _inner_height_pt(box), box.text_frame.text

    def it_still_flags_a_label_dragged_onto_the_rail(self):
        # The dot/rail overlap is allowed pair-by-pair, not by tagging the whole
        # timeline as one group, so a genuine collision stays visible to lint.
        slide = timeline_slide(_presentation("4:3"), title="Roadmap", milestones=_ROADMAP[:3])
        assert {s.lint_group for s in slide.shapes} == {None}
        label = next(
            s for s in slide.shapes if s.has_text_frame and "Milestone 2" in s.text_frame.text
        )
        rail = next(
            s
            for s in slide.shapes
            if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and s.height < s.width // 10
        )
        label.top = Emu(int(rail.top) - int(label.height) // 2)
        assert any("ShapeCollision" in p for p in _lint_problems(slide))

    def it_passes_lint_raise_through_from_spec(self):
        # The original repro: four OffSlide errors on a 16:9 three-milestone timeline.
        from power_pptx.compose import from_spec

        prs = from_spec(
            {
                "slide_size": "16:9",
                "slides": [
                    {
                        "layout": "timeline",
                        "title": "R",
                        "milestones": [
                            {"date": "Q1", "label": "Kickoff"},
                            {"date": "Q2", "label": "Beta"},
                            {"date": "Q3", "label": "GA"},
                        ],
                    }
                ],
                "lint": "raise",
            }
        )
        assert len(prs.slides) == 1

    @pytest.mark.parametrize("aspect", ["4:3", "16:9"])
    def it_fits_exactly_as_many_milestones_as_it_says_it_can(self, aspect):
        many = [{"date": f"D{i}", "label": f"M{i}"} for i in range(80)]
        prs = _presentation(aspect)
        with pytest.raises(ValueError, match=r"at most (\d+) fit") as excinfo:
            timeline_slide(prs, title="Roadmap", milestones=many)
        assert len(prs.slides) == 0  # a refused call leaves no stray slide behind
        capacity = int(re.search(r"at most (\d+) fit", str(excinfo.value)).group(1))
        assert capacity >= 12  # a dozen milestones is a realistic roadmap
        slide = timeline_slide(prs, title="Roadmap", milestones=many[:capacity])
        assert _lint_problems(slide) == []
        with pytest.raises(ValueError, match="at most"):
            timeline_slide(prs, title="Roadmap", milestones=many[: capacity + 1])


class DescribeComparisonSlide:
    def it_renders_left_and_right_columns_with_matched_rows(self, prs):
        slide = comparison_slide(
            prs,
            title="X",
            left_heading="Old",
            right_heading="New",
            rows=[
                {"left": "L1", "right": "R1"},
                {"left": "L2", "right": "R2"},
            ],
        )
        texts = " ".join(_paragraph_texts(slide))
        for needle in ("Old", "New", "L1", "R1", "L2", "R2"):
            assert needle in texts


class DescribeComparisonSlideHeadings:
    """The heading bands are a fixed 0.6 in tall, so the heading type is fitted to them."""

    _LONG_LEFT = "Build the platform in-house with our own engineering teams"
    _LONG_RIGHT = "Buy a managed platform from an established vendor"

    @staticmethod
    def _slide(aspect, left, right, tokens):
        return comparison_slide(
            _presentation(aspect),
            title="Build vs buy",
            left_heading=left,
            right_heading=right,
            rows=[{"left": f"Left {i}", "right": f"Right {i}"} for i in range(4)],
            tokens=tokens,
        )

    @staticmethod
    def _band(slide, heading):
        return next(s for s in slide.shapes if s.has_text_frame and s.text_frame.text == heading)

    @classmethod
    def _size_pt(cls, slide, heading):
        return cls._band(slide, heading).text_frame.paragraphs[0].runs[0].font.size.pt

    @pytest.mark.parametrize("aspect", ["4:3", "16:9"])
    @pytest.mark.parametrize("preset", ["modern_light", "corporate_navy"])
    def it_lints_clean_with_headings_that_need_more_than_one_line(self, aspect, preset):
        tokens = DesignTokens.from_preset(preset)
        slide = self._slide(aspect, self._LONG_LEFT, self._LONG_RIGHT, tokens)
        assert _lint_problems(slide) == []

    @pytest.mark.parametrize("aspect", ["4:3", "16:9"])
    def it_shrinks_the_deck_heading_size_only_as_far_as_the_longer_heading_needs(self, aspect):
        tokens = DesignTokens.from_preset("modern_light")  # headings are 32 pt
        slide = self._slide(aspect, self._LONG_LEFT, "Buy", tokens)
        sizes = {self._size_pt(slide, h) for h in (self._LONG_LEFT, "Buy")}
        assert len(sizes) == 1  # the two bands read as one system
        (size,) = sizes
        assert 9 <= size < 20  # shrunk, but two lines of it still use the band

    def it_never_enlarges_a_heading_that_already_fits(self):
        tokens = DesignTokens.from_dict(
            {"typography": {"heading": {"family": "Inter", "size": Pt(16), "bold": True}}}
        )
        slide = self._slide("4:3", "Build in-house", "Buy from vendor", tokens)
        assert self._size_pt(slide, "Build in-house") == 16
        assert self._size_pt(slide, "Buy from vendor") == 16

    def it_keeps_the_default_heading_size_without_tokens(self):
        slide = self._slide("4:3", "Old", "New", None)
        assert self._size_pt(slide, "Old") == 18
        assert _lint_problems(slide) == []

    def but_leaves_autofit_as_the_last_defence_for_a_heading_no_size_can_fit(self):
        tokens = DesignTokens.from_preset("modern_light")
        absurd = "a heading that rambles on and on " * 12
        slide = self._slide("4:3", absurd, "Buy", tokens)
        band = self._band(slide, absurd)
        assert self._size_pt(slide, absurd) == 9  # the legibility floor, never below
        assert band.text_frame.auto_size == MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE


class DescribeChartSlidePolish:
    """`chart_slide` controls for legend / smooth / data_labels / palette."""

    def it_disables_the_legend_when_asked(self, prs):
        chart_slide(
            prs,
            title="x",
            chart_type="line",
            categories=["A", "B"],
            series=[{"name": "S", "values": [1, 2]}],
            legend=False,
        )
        gframe = next(s for s in prs.slides[-1].shapes if s.shape_type == MSO_SHAPE_TYPE.CHART)
        assert gframe.chart.has_legend is False

    def it_smooths_a_line_chart(self, prs):
        chart_slide(
            prs,
            title="x",
            chart_type="line",
            categories=["A", "B"],
            series=[{"name": "S", "values": [1, 2]}],
            smooth=True,
        )
        gframe = next(s for s in prs.slides[-1].shapes if s.shape_type == MSO_SHAPE_TYPE.CHART)
        assert all(s.smooth for s in gframe.chart.series)

    def it_applies_a_named_palette(self, prs):
        chart_slide(
            prs,
            title="x",
            chart_type="column",
            categories=["A", "B"],
            series=[{"name": "S1", "values": [1, 2]}, {"name": "S2", "values": [3, 4]}],
            chart_palette="modern",
        )
        # Palette application is best-effort but mustn't blow up.
        assert any(s.shape_type == MSO_SHAPE_TYPE.CHART for s in prs.slides[-1].shapes)

    def it_derives_a_chart_palette_from_tokens(self, prs, tokens):
        # No explicit chart_palette → recipe walks tokens.palette and
        # paints every series.
        chart_slide(
            prs,
            title="x",
            chart_type="column",
            categories=["A", "B"],
            series=[{"name": "S1", "values": [1, 2]}, {"name": "S2", "values": [3, 4]}],
            tokens=tokens,
        )
        gframe = next(s for s in prs.slides[-1].shapes if s.shape_type == MSO_SHAPE_TYPE.CHART)
        # Verify each series has a solid spPr fill (i.e. palette was
        # actually applied — the default chart style leaves the spPr
        # absent and series pull their colours from the theme).
        from power_pptx.enum.dml import MSO_FILL_TYPE

        fills = [s.format.fill.type for s in gframe.chart.series]
        assert all(f == MSO_FILL_TYPE.SOLID for f in fills)


class DescribeTableSlidePolish:
    """`table_slide` controls for widths, aligns, totals."""

    def it_applies_explicit_column_width_fractions(self, prs):
        slide = table_slide(
            prs,
            title="t",
            columns=["A", "B", "C"],
            rows=[["1", "2", "3"]],
            widths=[0.5, 0.25, 0.25],
        )
        table = next(s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE).table
        cols = list(table.columns)
        # Col 0 should be ~2x wider than col 1.
        ratio = int(cols[0].width) / int(cols[1].width)
        assert 1.8 < ratio < 2.2

    def it_right_aligns_numeric_columns(self, prs):
        slide = table_slide(
            prs,
            title="t",
            columns=["Region", "Revenue"],
            rows=[["NA", "$10"]],
            aligns=["left", "right"],
        )
        table = next(s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE).table
        revenue_para = table.cell(1, 1).text_frame.paragraphs[0]
        assert revenue_para.alignment == PP_ALIGN.RIGHT

    def it_renders_a_totals_row(self, prs):
        slide = table_slide(
            prs,
            title="t",
            columns=["Region", "Q1", "Q2"],
            rows=[["NA", "10", "20"], ["EU", "5", "15"]],
            totals={"label": "Total", "values": [15, 35]},
        )
        table = next(s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE).table
        # Header + 2 data rows + 1 totals row = 4 rows.
        assert len(table.rows) == 4
        footer = table.cell(3, 0).text_frame.text
        assert "Total" in footer
        assert "15" in table.cell(3, 1).text_frame.text
        assert "35" in table.cell(3, 2).text_frame.text

    def it_accepts_explicit_totals_row(self, prs):
        slide = table_slide(
            prs,
            title="t",
            columns=["A", "B"],
            rows=[["1", "2"]],
            totals={"row": ["Sum", "X"]},
        )
        table = next(s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE).table
        assert "Sum" in table.cell(2, 0).text_frame.text
        assert "X" in table.cell(2, 1).text_frame.text

    def it_rejects_a_misshapen_explicit_totals_row(self, prs):
        with pytest.raises(ValueError, match="totals.row"):
            table_slide(
                prs,
                title="t",
                columns=["A", "B"],
                rows=[["1", "2"]],
                totals={"row": ["only-one"]},
            )

    def it_rejects_unknown_align(self, prs):
        with pytest.raises(ValueError, match="align"):
            table_slide(
                prs,
                title="t",
                columns=["A"],
                rows=[["1"]],
                aligns=["middle"],
            )


def _table_frame(slide):
    return next(s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE)


def _column_widths(slide):
    return [int(c.width) for c in _table_frame(slide).table.columns]


class DescribeTableSlideColumnWidths:
    """`widths=` may name fewer columns than the table has."""

    def it_splits_the_remaining_width_evenly_over_unspecified_columns(self, prs):
        slide = table_slide(
            prs,
            title="t",
            columns=["A", "B", "C", "D"],
            rows=[["1", "2", "3", "4"]],
            widths=[0.25, 0.25],
        )
        widths = _column_widths(slide)
        quarter = int(_table_frame(slide).width) / 4
        assert all(abs(w - quarter) <= 2 for w in widths), widths

    def it_keeps_specified_fractions_when_columns_are_unspecified(self, prs):
        slide = table_slide(
            prs,
            title="t",
            columns=["A", "B", "C"],
            rows=[["1", "2", "3"]],
            widths=[0.5],
        )
        widths = _column_widths(slide)
        total = int(_table_frame(slide).width)
        assert abs(widths[0] - total / 2) <= 2
        assert abs(widths[1] - total / 4) <= 2
        assert abs(widths[2] - total / 4) <= 2

    def it_splits_what_absolute_lengths_leave_over(self, prs):
        slide = table_slide(
            prs,
            title="t",
            columns=["A", "B", "C", "D"],
            rows=[["1", "2", "3", "4"]],
            widths=[Inches(1), Inches(2)],
        )
        widths = _column_widths(slide)
        assert widths[:2] == [int(Inches(1)), int(Inches(2))]
        leftover = (int(_table_frame(slide).width) - int(Inches(3))) / 2
        assert all(abs(w - leftover) <= 2 for w in widths[2:])

    def it_fills_the_table_width_exactly(self, prs):
        slide = table_slide(
            prs,
            title="t",
            columns=["A", "B", "C", "D", "E", "F", "G"],
            rows=[["1"] * 7],
            widths=[0.1, 0.1, 0.1],
        )
        assert sum(_column_widths(slide)) == int(_table_frame(slide).width)

    def it_still_rescales_fractions_that_name_every_column(self, prs):
        slide = table_slide(
            prs,
            title="t",
            columns=["A", "B", "C"],
            rows=[["1", "2", "3"]],
            widths=[1, 1, 2],
        )
        widths = _column_widths(slide)
        assert abs(sum(widths) - int(_table_frame(slide).width)) <= 3
        assert abs(widths[2] / widths[0] - 2.0) < 0.01

    @pytest.mark.parametrize("widths", [[0.6, 0.6], [Inches(5), Inches(5)]])
    def it_rejects_widths_that_leave_no_room_for_the_rest(self, prs, widths):
        with pytest.raises(ValueError, match="no room"):
            table_slide(
                prs,
                title="t",
                columns=["A", "B", "C"],
                rows=[["1", "2", "3"]],
                widths=widths,
            )

    def but_it_does_not_leave_a_stray_slide_behind_when_it_raises(self, prs):
        with pytest.raises(ValueError):
            table_slide(
                prs,
                title="t",
                columns=["A", "B", "C"],
                rows=[["1", "2", "3"]],
                widths=[0.6, 0.6],
            )
        assert len(prs.slides) == 0


class DescribeTableSlideTotals:
    def it_rejects_more_totals_values_than_value_columns(self, prs):
        # Column 0 holds the label, so two columns leave room for one value.
        with pytest.raises(ValueError, match=r"totals\.values"):
            table_slide(
                prs,
                title="t",
                columns=["A", "B"],
                rows=[["1", "2"]],
                totals={"label": "Tot", "values": [10, 20, 30]},
            )

    def it_rejects_a_value_per_column_because_the_label_takes_one(self, prs):
        with pytest.raises(ValueError, match=r"totals\.values"):
            table_slide(
                prs,
                title="t",
                columns=["A", "B"],
                rows=[["1", "2"]],
                totals={"values": [10, 20]},
            )

    def it_still_right_aligns_fewer_values_than_columns(self, prs):
        slide = table_slide(
            prs,
            title="t",
            columns=["A", "B", "C", "D"],
            rows=[["1", "2", "3", "4"]],
            totals={"label": "Total", "values": [7, 9]},
        )
        table = _table_frame(slide).table
        assert [table.cell(2, c).text for c in range(4)] == ["Total", "", "7", "9"]


def _cell_margins(cell):
    top = cell.margin_top if cell.margin_top is not None else Inches(0.05)
    bottom = cell.margin_bottom if cell.margin_bottom is not None else Inches(0.05)
    return int(top) + int(bottom)


def _table_rows_big_enough_for_their_text(slide):
    """Return a description of every row too short for its text, or ``[]``."""
    table = _table_frame(slide).table
    problems = []
    for r, row in enumerate(table.rows):
        for c in range(len(table.columns)):
            cell = table.cell(r, c)
            size = cell.text_frame.paragraphs[0].runs[0].font.size
            need = int(size * 1.2) + _cell_margins(cell)
            if int(row.height) < need - 2:
                problems.append(f"row {r}: {Emu(row.height).pt:.1f}pt < {Emu(need).pt:.1f}pt")
    return problems


class DescribeTableSlideRowHeights:
    """Rows never get shorter than the text inside them."""

    @pytest.mark.parametrize("aspect", ["4:3", "16:9"])
    @pytest.mark.parametrize("n", [5, 12, 20, 26])
    def it_keeps_every_row_tall_enough_for_its_text(self, aspect, n):
        slide = table_slide(
            _presentation(aspect),
            title="Regional results",
            columns=["Region", "Revenue"],
            rows=[[f"Region {i}", f"${i}M"] for i in range(n)],
            totals={"label": "Total", "values": ["$1B"]},
        )
        assert _table_rows_big_enough_for_their_text(slide) == []

    def it_shrinks_the_text_and_keeps_the_table_on_the_slide(self):
        prs = _presentation("4:3")
        slide = table_slide(
            prs,
            title="t",
            columns=["Region", "Revenue"],
            rows=[[f"Region {i}", i] for i in range(20)],
        )
        frame = _table_frame(slide)
        sizes = {
            cell.text_frame.paragraphs[0].runs[0].font.size.pt
            for row in frame.table.rows
            for cell in row.cells
        }
        assert max(sizes) < 14  # the 14 pt header shrank too
        assert min(sizes) >= 9
        assert int(frame.top) + int(frame.height) <= int(prs.slide_height) - int(Inches(0.5))
        assert sum(int(r.height) for r in frame.table.rows) <= int(frame.height) + 3
        assert _lint_problems(slide) == []

    def it_centres_cell_text_vertically(self, prs):
        # Cells take their vertical alignment from a:tcPr, not the cell's text body.
        slide = table_slide(prs, title="t", columns=["A", "B"], rows=[["1", "2"]])
        table = _table_frame(slide).table
        assert all(
            cell.vertical_anchor == MSO_ANCHOR.MIDDLE for row in table.rows for cell in row.cells
        )

    def it_leaves_a_short_table_exactly_as_it_was(self, prs):
        slide = table_slide(
            prs,
            title="t",
            columns=["A", "B"],
            rows=[["1", "2"], ["3", "4"]],
            totals={"row": ["s", "t"]},
        )
        table = _table_frame(slide).table
        assert table.cell(0, 0).text_frame.paragraphs[0].runs[0].font.size == Pt(14)
        assert table.cell(1, 0).text_frame.paragraphs[0].runs[0].font.size == Pt(13)
        assert table.cell(3, 0).text_frame.paragraphs[0].runs[0].font.size == Pt(13)
        assert all("marT" not in cell._tc.xml for row in table.rows for cell in row.cells)

    @staticmethod
    def _sizes(slide):
        table = _table_frame(slide).table
        return {
            cell.text_frame.paragraphs[0].runs[0].font.size.pt
            for row in table.rows
            for cell in row.cells
        }

    def it_keeps_the_default_margins_while_they_fit(self, prs):
        # The 5.4 in frame gives each of 16 rows 24.3 pt: room for the 14 pt header
        # (16.8 pt of text + 7.2 pt of margin).
        slide = table_slide(
            prs, title="t", columns=["A", "B"], rows=[[f"r{i}", i] for i in range(15)]
        )
        table = _table_frame(slide).table
        assert self._sizes(slide) == {14.0, 13.0}
        assert all("marT" not in cell._tc.xml for row in table.rows for cell in row.cells)

    def it_tightens_the_cell_margins_before_it_touches_the_font(self, prs):
        # 18 rows leave 21.6 pt each: too little for the default margins, but plenty
        # once they drop to 2.88 pt.  The text keeps its size.
        slide = table_slide(
            prs, title="t", columns=["A", "B"], rows=[[f"r{i}", i] for i in range(17)]
        )
        table = _table_frame(slide).table
        assert self._sizes(slide) == {14.0, 13.0}
        assert all("marT" in cell._tc.xml for row in table.rows for cell in row.cells)
        assert _table_rows_big_enough_for_their_text(slide) == []

    def it_fits_big_token_typography_by_shrinking_it(self, tokens):
        slide = table_slide(
            _presentation("16:9"),
            title="t",
            columns=["Region", "Revenue"],
            rows=[[f"Region {i}", i] for i in range(20)],
            tokens=tokens,
        )
        assert _table_rows_big_enough_for_their_text(slide) == []

    def it_refuses_a_table_that_cannot_fit_on_one_slide(self, prs):
        with pytest.raises(ValueError, match="split"):
            table_slide(
                prs,
                title="t",
                columns=["A", "B"],
                rows=[[f"r{i}", i] for i in range(80)],
            )
        assert len(prs.slides) == 0

    def it_says_how_many_rows_do_fit(self, prs):
        with pytest.raises(ValueError, match=r"at most \d+ data rows"):
            table_slide(prs, title="t", columns=["A"], rows=[[i] for i in range(80)])

    def it_accepts_the_largest_table_it_says_will_fit(self, prs):
        with pytest.raises(ValueError) as excinfo:
            table_slide(prs, title="t", columns=["A"], rows=[[i] for i in range(80)])
        found = re.search(r"at most (\d+) data rows", str(excinfo.value))
        assert found is not None
        capacity = int(found.group(1))
        slide = table_slide(prs, title="t", columns=["A"], rows=[[i] for i in range(capacity)])
        assert _table_rows_big_enough_for_their_text(slide) == []
        with pytest.raises(ValueError, match="split"):
            table_slide(prs, title="t", columns=["A"], rows=[[i] for i in range(capacity + 1)])


class DescribeIsMarkupString:
    """`_is_markup_string` correctly recognises inline SVG/HTML."""

    def it_recognises_inline_svg_with_xmlns_url(self):
        from power_pptx.design.recipes import _is_markup_string

        # The previous implementation broke on the "/" inside the xmlns URL.
        markup = '<svg xmlns="http://www.w3.org/2000/svg"><circle r="5"/></svg>'
        assert _is_markup_string(markup) is True

    def it_recognises_xml_declarations(self):
        from power_pptx.design.recipes import _is_markup_string

        assert _is_markup_string('<?xml version="1.0"?><svg>...</svg>') is True

    def it_recognises_html_documents(self):
        from power_pptx.design.recipes import _is_markup_string

        assert _is_markup_string("<html><body>...</body></html>") is True

    def it_rejects_filesystem_paths(self):
        from power_pptx.design.recipes import _is_markup_string

        assert _is_markup_string("/tmp/foo.png") is False
        assert _is_markup_string("charts/foo.svg") is False

    def it_rejects_non_string_inputs(self):
        from power_pptx.design.recipes import _is_markup_string

        assert _is_markup_string(42) is False
        assert _is_markup_string(b"<svg/>") is False
        assert _is_markup_string("") is False


class DescribeIsMarkupStringAdditional:
    """Additional cases that motivated the second pass on `_is_markup_string`."""

    def it_recognises_a_closing_tag(self):
        from power_pptx.design.recipes import _is_markup_string

        # `</tagname>` starts with `<` then `/` then a letter — markup.
        assert _is_markup_string("</svg>") is True

    def it_recognises_a_doctype_declaration(self):
        from power_pptx.design.recipes import _is_markup_string

        assert _is_markup_string("<!DOCTYPE html>") is True

    def it_recognises_an_xml_comment(self):
        from power_pptx.design.recipes import _is_markup_string

        assert _is_markup_string("<!-- comment -->") is True

    def it_falls_back_to_path_for_unrecognised_lt_prefix(self):
        from power_pptx.design.recipes import _is_markup_string

        # `<` followed by a non-letter and no recognised XML/doctype/comment
        # pattern is treated as a path (preserves docstring intent).
        assert _is_markup_string("<<<weird") is False
        assert _is_markup_string("<1file") is False


def _width_for(chars, size_pt, *, em=0.55):
    """Box width in EMU that holds exactly *chars* characters at *size_pt*."""
    return int(chars * em * size_pt * 12700) + 1


class DescribeTextMeasurement:
    """The font-independent fit model the recipes use to size their text."""

    def it_counts_one_line_for_short_or_empty_text(self):
        from power_pptx.design.recipes import _wrapped_line_count

        assert _wrapped_line_count("", _width_for(10, 10), 10) == 1
        assert _wrapped_line_count("short", _width_for(10, 10), 10) == 1

    def it_starts_a_new_line_at_every_explicit_break(self):
        from power_pptx.design.recipes import _wrapped_line_count

        width = _width_for(40, 10)
        assert _wrapped_line_count("a\nb\n\nc", width, 10) == 4
        assert _wrapped_line_count("a\vb", width, 10) == 2

    def it_wraps_greedily_at_spaces(self):
        from power_pptx.design.recipes import _wrapped_line_count

        # Ten characters per line: "aaaa bbbb" fills one line, "cccc" spills over.
        assert _wrapped_line_count("aaaa bbbb cccc", _width_for(10, 10), 10) == 2

    def it_breaks_a_word_wider_than_the_box(self):
        from power_pptx.design.recipes import _wrapped_line_count

        assert _wrapped_line_count("x" * 25, _width_for(10, 10), 10) == 3
        # ... and starts it on a fresh line when something precedes it.
        assert _wrapped_line_count("ab " + "x" * 25, _width_for(10, 10), 10) == 4

    def it_does_not_wrap_for_trailing_whitespace(self):
        from power_pptx.design.recipes import _wrapped_line_count

        assert _wrapped_line_count("0123456789" + " " * 12, _width_for(10, 10), 10) == 1

    def it_counts_monospace_indentation_and_tabs(self):
        from power_pptx.design.recipes import _wrapped_line_count

        width = _width_for(10, 10, em=0.6)
        # Four columns of indent plus "return" fill the ten-column line exactly ...
        assert _wrapped_line_count("    return", width, 10, mono=True) == 1
        # ... so whatever follows it wraps; a tab counts as four columns.
        assert _wrapped_line_count("    return x", width, 10, mono=True) == 2
        assert _wrapped_line_count("\treturn", width, 10, mono=True) == 1
        assert _wrapped_line_count("\treturn x", width, 10, mono=True) == 2

    def it_widens_bold_text(self):
        from power_pptx.design.recipes import _wrapped_line_count

        width = _width_for(20, 10)
        text = "0123456789 0123456789"  # 21 characters
        assert _wrapped_line_count(text, width, 10) == 2
        assert _wrapped_line_count("0123456789 012345678", width, 10) == 1
        assert _wrapped_line_count("0123456789 012345678", width, 10, bold=True) == 2

    def it_prices_each_line_at_one_point_two_times_the_size(self):
        from power_pptx.design.recipes import _text_height

        assert _text_height("a\nb\nc", _width_for(10, 10), 10) == int(3 * 10 * 1.2 * 12700)

    def it_keeps_the_requested_size_when_the_text_fits(self):
        from power_pptx.design.recipes import _fit_font_size

        assert _fit_font_size("hello", _width_for(20, 14), int(Inches(1)), max_pt=14) == 14

    def it_steps_down_a_point_at_a_time_until_the_text_fits(self):
        from power_pptx.design.recipes import _fit_font_size, _text_height

        text = "one two three four five six seven eight nine ten"
        width, height = int(Inches(1.5)), int(Inches(0.6))
        size = _fit_font_size(text, width, height, max_pt=20)
        assert size is not None
        assert size < 20
        assert _text_height(text, width, size) <= height
        assert _text_height(text, width, size + 1) > height

    def it_reports_none_when_even_the_floor_overflows(self):
        from power_pptx.design.recipes import _fit_font_size

        assert _fit_font_size("word " * 200, int(Inches(1)), int(Inches(0.5)), max_pt=14) is None

    def it_never_enlarges_text_already_below_the_floor(self):
        from power_pptx.design.recipes import _fit_font_size

        assert _fit_font_size("tiny", int(Inches(2)), int(Inches(1)), max_pt=7) == 7

    def it_resizes_a_token_to_the_tightest_text_in_a_row(self):
        from dataclasses import replace

        from power_pptx.design.recipes import _fit_token, _typography

        token = _typography(None, "body", default_size=Pt(16))
        width, height = int(Inches(1.4)), int(Inches(0.45))
        fitted = _fit_token(token, ["ok", "a rather longer label that must wrap"], width, height)
        alone = _fit_token(token, ["ok"], width, height)
        assert alone.size == Pt(16)  # a text that fits leaves the size alone
        assert Pt(9) <= fitted.size < Pt(16)
        assert replace(fitted, size=token.size) == token  # only the size changes

    def it_pins_a_hopeless_text_to_the_legibility_floor(self):
        from power_pptx.design.recipes import _fit_token, _typography

        token = _typography(None, "body", default_size=Pt(16))
        fitted = _fit_token(token, ["word " * 400], int(Inches(1)), int(Inches(0.4)))
        assert fitted.size == Pt(9)


def _pygments_available():
    try:
        import pygments  # noqa: F401
    except ImportError:
        return False
    return True


def _schema_violations(prs):
    """Return the ISO-29500 schema violations of *prs* once saved (skips if unavailable)."""
    import io

    from tests.schema.oxml_schema_validator import (
        iter_schema_violations,
        schema_validation_available,
    )

    if not schema_validation_available():
        pytest.skip("schema validation unavailable")
    buf = io.BytesIO()
    prs.save(buf)
    return list(iter_schema_violations(buf.getvalue()))


class DescribeRecipeSchemaValidity:
    """Whatever geometry the recipes work out, the XML they emit stays valid."""

    @pytest.mark.parametrize("aspect", ["4:3", "16:9"])
    def it_validates_timelines_and_tables(self, aspect, tokens):
        prs = _presentation(aspect)
        for n in (1, 2, 8):
            timeline_slide(prs, title="Roadmap", milestones=_ROADMAP[:n], tokens=tokens)
        # Roomy, compact-margin and shrunk-font tables, with and without partial widths.
        table_slide(prs, title="Short", columns=["A", "B"], rows=[["1", "2"]])
        table_slide(
            prs,
            title="Compact margins",
            columns=["A", "B", "C", "D"],
            rows=[[i] * 4 for i in range(17)],
            widths=[0.4, 0.2],
            totals={"label": "Sum", "values": [1, 2]},
        )
        table_slide(prs, title="Shrunk", columns=["A", "B"], rows=[[i, i] for i in range(24)])
        assert _schema_violations(prs) == []

    def it_validates_code_slides_including_blank_lines_and_end_marks(self):
        prs = _presentation("4:3")
        code_slide(prs, title="Plain", code="\n\n".join(f"x{i} = {i}" for i in range(12)))
        code_slide(prs, title="Short", code="x = 1")
        if _pygments_available():
            code_slide(prs, title="Highlighted", code=_CODE_30, language="python")
        assert _schema_violations(prs) == []

    def it_validates_an_inline_svg_figure_slide(self):
        from unittest.mock import patch

        from power_pptx.design.recipes import figure_slide

        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"><circle r="2"/></svg>'
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000d4944415478da63fcffff3f0300070602ffa39d9aed0000000049454e44ae426082"
        )
        prs = _presentation("4:3")
        with patch("power_pptx._svg.rasterize_svg", return_value=png):
            figure_slide(prs, title="Diagram", figure=svg, caption="Source: x")
        assert _schema_violations(prs) == []

    def it_round_trips_a_tight_table_a_timeline_and_a_code_slide(self):
        from tests.integration.round_trip import assert_round_trip

        prs = _presentation("4:3")
        timeline_slide(prs, title="Roadmap", milestones=_ROADMAP[:5])
        table_slide(prs, title="Shrunk", columns=["A", "B"], rows=[[i, i] for i in range(24)])
        code_slide(prs, title="Code", code=_CODE_30)
        assert_round_trip(prs)


_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f0300070602ffa39d9aed0000000049454e44ae426082"
)
_FIGURE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20">'
    '<rect width="40" height="20"/></svg>'
)


def _every_recipe(prs, tokens):
    """Build one slide with each recipe from realistic content; return ``{name: slide}``."""
    from unittest.mock import patch

    from power_pptx.design.recipes import figure_slide

    slides = {}
    slides["title"] = title_slide(
        prs,
        title="Quarterly Business Review: Platform, Growth and Operations",
        subtitle="April 2026 — prepared for the executive leadership team",
        tokens=tokens,
    )
    slides["bullets"] = bullet_slide(
        prs,
        title="Highlights",
        bullets=[
            f"Bullet {i}: we shipped a thing and it was good for customers." for i in range(8)
        ],
        tokens=tokens,
    )
    slides["kpi"] = kpi_slide(
        prs,
        title="Run-rate metrics",
        kpis=[
            {"label": "Annual recurring revenue", "value": "$182.4M", "delta": 0.27},
            {"label": "Net dollar retention", "value": "131%", "delta": 0.03},
            {"label": "Gross margin", "value": "78.2%", "delta": -0.012},
            {"label": "Customers", "value": "12,480", "delta_text": "+1,204"},
        ],
        tokens=tokens,
    )
    slides["quote"] = quote_slide(
        prs,
        quote="The best way to predict the future is to invent it.",
        attribution="Alan Kay",
        tokens=tokens,
    )
    slides["image_hero"] = image_hero_slide(
        prs, title="Q4 2026", image=_TEST_IMAGE, caption="Our year in review", tokens=tokens
    )
    slides["section"] = section_divider(
        prs, title="Part Two: Operating Model", eyebrow="PART TWO", progress=(2, 5), tokens=tokens
    )
    slides["chart"] = chart_slide(
        prs,
        title="Revenue by quarter",
        chart_type="column",
        categories=["Q1", "Q2", "Q3", "Q4"],
        series=[
            {"name": "ARR", "values": [82, 110, 132, 150]},
            {"name": "Costs", "values": [60, 70, 80, 90]},
        ],
        tokens=tokens,
    )
    slides["table"] = table_slide(
        prs,
        title="Regional results",
        columns=["Region", "Revenue", "Growth", "Margin"],
        rows=[[f"Region {i}", f"${i * 10}M", f"{i}%", f"{70 + i}%"] for i in range(12)],
        totals={"label": "Total", "values": ["$660M", "", "75%"]},
        tokens=tokens,
    )
    slides["code"] = code_slide(
        prs,
        title="Example",
        code="\n".join(f"def f{i}(x):\n    return x * {i}  # comment" for i in range(10)),
        language="python",
        tokens=tokens,
    )
    slides["timeline"] = timeline_slide(
        prs,
        title="Roadmap",
        milestones=[
            {"date": f"2026-0{i + 1}", "label": f"Milestone {i + 1}: ship the layer", "done": i < 2}
            for i in range(6)
        ],
        tokens=tokens,
    )
    slides["comparison"] = comparison_slide(
        prs,
        title="Build vs buy",
        left_heading="Build in-house",
        right_heading="Buy from vendor",
        rows=[
            {"left": f"Left point {i} with detail", "right": f"Right point {i}"} for i in range(5)
        ],
        tokens=tokens,
    )
    with patch("power_pptx._svg.rasterize_svg", return_value=_TINY_PNG):
        slides["figure"] = figure_slide(
            prs,
            title="Architecture",
            figure=_FIGURE_SVG,
            caption="Source: internal",
            tokens=tokens,
        )
    return slides


_TOKEN_SETS = ["none", "fixture", "modern_light", "modern_dark", "corporate_navy", "vibrant"]
# The presets whose own ``on_primary`` / ``primary`` pair is under WCAG AA (4.41:1 and 3.55:1;
# the others are 5.7:1 and above).  ``comparison_slide`` draws that pair on a shape the linter
# can read, so for these two the sweep tolerates LowContrast — a property of the palette data,
# not of any recipe's geometry — and holds everything else to zero.
_PALETTE_BELOW_AA = ("modern_dark", "vibrant")


class DescribeEveryRecipeIsPhysicallyCorrect:
    """The project's own acceptance rule: a recipe's default output lints clean and is valid."""

    @staticmethod
    def _tokens(name, fixture_tokens):
        if name == "none":
            return None
        if name == "fixture":
            return fixture_tokens
        return DesignTokens.from_preset(name)

    def it_builds_one_slide_per_public_recipe(self):
        # A recipe added to ``__all__`` without a line in ``_every_recipe`` escapes the sweep.
        from power_pptx.design import recipes

        built = _every_recipe(_presentation("4:3"), None)
        assert len(built) == len(recipes.__all__)

    @pytest.mark.parametrize("aspect", ["4:3", "16:9"])
    @pytest.mark.parametrize("token_set", _TOKEN_SETS)
    def it_lints_clean_on_both_aspect_ratios(self, aspect, token_set, tokens):
        prs = _presentation(aspect)
        slides = _every_recipe(prs, self._tokens(token_set, tokens))
        problems = {name: _lint_problems(slide) for name, slide in slides.items()}
        if token_set in _PALETTE_BELOW_AA:
            problems = {
                name: [p for p in found if "LowContrast" not in p]
                for name, found in problems.items()
            }
        assert {name: p for name, p in problems.items() if p} == {}

    @pytest.mark.parametrize("aspect", ["4:3", "16:9"])
    @pytest.mark.parametrize("token_set", ["none", "modern_light", "modern_dark"])
    def it_validates_against_the_schema(self, aspect, token_set, tokens):
        prs = _presentation(aspect)
        _every_recipe(prs, self._tokens(token_set, tokens))
        assert _schema_violations(prs) == []
