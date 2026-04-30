"""Unit-test suite for :mod:`power_pptx.design.recipes`."""

from __future__ import annotations

import os

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
from power_pptx.enum.text import PP_ALIGN
from power_pptx.util import Pt


_TEST_IMAGE = os.path.join(
    os.path.dirname(__file__), "..", "test_files", "monty-truth.png"
)


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
    return [
        p.text
        for sh in slide.shapes
        if sh.has_text_frame
        for p in sh.text_frame.paragraphs
    ]


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
        card = next(
            s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
        )
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
        slide = image_hero_slide(
            prs, title="T", image=_TEST_IMAGE, caption="A short caption"
        )
        assert any("A short caption" in t for t in _paragraph_texts(slide))

    def it_uses_the_token_primary_color_for_the_band(self, prs, tokens):
        slide = image_hero_slide(
            prs, title="T", image=_TEST_IMAGE, tokens=tokens
        )
        bands = [
            s
            for s in slide.shapes
            if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
        ]
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
        autoshapes = [
            s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
        ]
        assert len(autoshapes) == 1 + 7

    def it_rejects_invalid_progress(self, prs):
        with pytest.raises(ValueError, match="progress must be"):
            section_divider(prs, title="X", progress=(8, 7))


class DescribeChartSlide:
    def it_appends_a_slide_with_a_chart(self, prs):
        slide = chart_slide(
            prs, title="Revenue", chart_type="line",
            categories=["Q1", "Q2", "Q3"],
            series=[{"name": "Rev", "values": [10, 20, 30]}],
        )
        graphic_frames = [
            s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.CHART
        ]
        assert len(graphic_frames) == 1

    def it_supports_known_chart_types(self, prs):
        for kind in ("line", "bar", "column", "pie", "area"):
            slide = chart_slide(
                prs, title="x", chart_type=kind,
                categories=["A", "B"],
                series=[{"name": "S", "values": [1, 2]}],
            )
            assert any(
                s.shape_type == MSO_SHAPE_TYPE.CHART for s in slide.shapes
            )

    def it_rejects_unknown_chart_types(self, prs):
        with pytest.raises(ValueError, match="Unknown chart_type"):
            chart_slide(
                prs, title="x", chart_type="radar",
                categories=["A"],
                series=[{"name": "S", "values": [1]}],
            )


class DescribeTableSlide:
    def it_appends_a_slide_with_a_table(self, prs):
        slide = table_slide(
            prs, title="T",
            columns=["A", "B"],
            rows=[["1", "2"], ["3", "4"]],
        )
        tables = [
            s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE
        ]
        assert len(tables) == 1
        # 2 data rows + 1 header = 3 rows
        assert len(tables[0].table.rows) == 3
        assert len(tables[0].table.columns) == 2

    def it_uses_token_palette_for_header(self, prs, tokens):
        slide = table_slide(
            prs, title="T",
            columns=["A"], rows=[["1"]],
            tokens=tokens,
        )
        table = next(
            s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE
        ).table
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
        assert "Consolas" in (code_runs[0].font.name or "") \
            or "Cascadia" in (code_runs[0].font.name or "") \
            or "monospace" in (code_runs[0].font.name or "")


class DescribeTimelineSlide:
    def it_renders_one_marker_per_milestone(self, prs):
        slide = timeline_slide(
            prs, title="T",
            milestones=[
                {"date": "Q1", "label": "Spec", "done": True},
                {"date": "Q2", "label": "Build"},
                {"date": "Q3", "label": "Ship"},
            ],
        )
        # 1 rail + 3 dots = 4 auto-shapes
        autoshapes = [
            s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
        ]
        assert len(autoshapes) == 4

    def it_tints_done_milestones_with_positive_color(self, prs, tokens):
        slide = timeline_slide(
            prs, title="T",
            milestones=[{"date": "Q1", "label": "Spec", "done": True}],
            tokens=tokens,
        )
        # Find the milestone dot (small oval).
        ovals = [
            s for s in slide.shapes
            if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and s.height < 914400
        ]
        assert any(
            o.fill.fore_color.rgb == RGBColor(0x00, 0x85, 0x3E)
            for o in ovals
        )

    def it_rejects_empty_milestones(self, prs):
        with pytest.raises(ValueError, match="at least one"):
            timeline_slide(prs, title="T", milestones=[])


class DescribeComparisonSlide:
    def it_renders_left_and_right_columns_with_matched_rows(self, prs):
        slide = comparison_slide(
            prs, title="X",
            left_heading="Old", right_heading="New",
            rows=[
                {"left": "L1", "right": "R1"},
                {"left": "L2", "right": "R2"},
            ],
        )
        texts = " ".join(_paragraph_texts(slide))
        for needle in ("Old", "New", "L1", "R1", "L2", "R2"):
            assert needle in texts


class DescribeChartSlidePolish:
    """`chart_slide` controls for legend / smooth / data_labels / palette."""

    def it_disables_the_legend_when_asked(self, prs):
        chart_slide(
            prs, title="x", chart_type="line",
            categories=["A", "B"],
            series=[{"name": "S", "values": [1, 2]}],
            legend=False,
        )
        gframe = next(
            s for s in prs.slides[-1].shapes
            if s.shape_type == MSO_SHAPE_TYPE.CHART
        )
        assert gframe.chart.has_legend is False

    def it_smooths_a_line_chart(self, prs):
        chart_slide(
            prs, title="x", chart_type="line",
            categories=["A", "B"],
            series=[{"name": "S", "values": [1, 2]}],
            smooth=True,
        )
        gframe = next(
            s for s in prs.slides[-1].shapes
            if s.shape_type == MSO_SHAPE_TYPE.CHART
        )
        assert all(s.smooth for s in gframe.chart.series)

    def it_applies_a_named_palette(self, prs):
        chart_slide(
            prs, title="x", chart_type="column",
            categories=["A", "B"],
            series=[{"name": "S1", "values": [1, 2]},
                    {"name": "S2", "values": [3, 4]}],
            chart_palette="modern",
        )
        # Palette application is best-effort but mustn't blow up.
        assert any(
            s.shape_type == MSO_SHAPE_TYPE.CHART for s in prs.slides[-1].shapes
        )

    def it_derives_a_chart_palette_from_tokens(self, prs, tokens):
        # No explicit chart_palette → recipe walks tokens.palette and
        # paints every series.
        chart_slide(
            prs, title="x", chart_type="column",
            categories=["A", "B"],
            series=[{"name": "S1", "values": [1, 2]},
                    {"name": "S2", "values": [3, 4]}],
            tokens=tokens,
        )
        gframe = next(
            s for s in prs.slides[-1].shapes
            if s.shape_type == MSO_SHAPE_TYPE.CHART
        )
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
            prs, title="t",
            columns=["A", "B", "C"],
            rows=[["1", "2", "3"]],
            widths=[0.5, 0.25, 0.25],
        )
        table = next(
            s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE
        ).table
        cols = list(table.columns)
        # Col 0 should be ~2x wider than col 1.
        ratio = int(cols[0].width) / int(cols[1].width)
        assert 1.8 < ratio < 2.2

    def it_right_aligns_numeric_columns(self, prs):
        slide = table_slide(
            prs, title="t",
            columns=["Region", "Revenue"],
            rows=[["NA", "$10"]],
            aligns=["left", "right"],
        )
        table = next(
            s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE
        ).table
        revenue_para = table.cell(1, 1).text_frame.paragraphs[0]
        assert revenue_para.alignment == PP_ALIGN.RIGHT

    def it_renders_a_totals_row(self, prs):
        slide = table_slide(
            prs, title="t",
            columns=["Region", "Q1", "Q2"],
            rows=[["NA", "10", "20"], ["EU", "5", "15"]],
            totals={"label": "Total", "values": [15, 35]},
        )
        table = next(
            s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE
        ).table
        # Header + 2 data rows + 1 totals row = 4 rows.
        assert len(table.rows) == 4
        footer = table.cell(3, 0).text_frame.text
        assert "Total" in footer
        assert "15" in table.cell(3, 1).text_frame.text
        assert "35" in table.cell(3, 2).text_frame.text

    def it_accepts_explicit_totals_row(self, prs):
        slide = table_slide(
            prs, title="t",
            columns=["A", "B"],
            rows=[["1", "2"]],
            totals={"row": ["Sum", "X"]},
        )
        table = next(
            s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE
        ).table
        assert "Sum" in table.cell(2, 0).text_frame.text
        assert "X" in table.cell(2, 1).text_frame.text

    def it_rejects_a_misshapen_explicit_totals_row(self, prs):
        with pytest.raises(ValueError, match="totals.row"):
            table_slide(
                prs, title="t",
                columns=["A", "B"],
                rows=[["1", "2"]],
                totals={"row": ["only-one"]},
            )

    def it_rejects_unknown_align(self, prs):
        with pytest.raises(ValueError, match="align"):
            table_slide(
                prs, title="t",
                columns=["A"], rows=[["1"]],
                aligns=["middle"],
            )


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

        assert _is_markup_string('<html><body>...</body></html>') is True

    def it_rejects_filesystem_paths(self):
        from power_pptx.design.recipes import _is_markup_string

        assert _is_markup_string('/tmp/foo.png') is False
        assert _is_markup_string('charts/foo.svg') is False

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
