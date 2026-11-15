"""Unit-test suite for :mod:`power_pptx.design.recipes`."""

from __future__ import annotations

import io
import os

import pytest

from power_pptx import Presentation
from power_pptx.design.recipes import (
    bullet_slide,
    chart_slide,
    code_slide,
    comparison_slide,
    figure_slide,
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
from power_pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from power_pptx.text import clear_registered_fonts, register_font_dir
from power_pptx.util import Inches, Pt
from power_pptx.validation import iter_schema_violations


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
        up, down = (run.font.color.rgb for run in delta_runs)
        # The palette's negative (#B00020) reads on the card surface and is
        # used as given.  Its positive (#00853E) is 4.3:1 there, so it is
        # darkened just enough to reach 4.5:1 — still the same green.
        assert down == RGBColor(0xB0, 0x00, 0x20)
        assert up != down
        assert up[1] > up[0]
        assert up[1] > up[2]
        assert (up[0], up[2]) <= (0x00, 0x3E)
        assert 0x70 <= up[1] <= 0x85

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
        # One real family, not a CSS-style stack ("Consolas, Menlo, monospace"
        # is a single unknown font name to PowerPoint and LibreOffice).
        assert code_runs[0].font.name in (
            "Cascadia Code",
            "Consolas",
            "Menlo",
            "DejaVu Sans Mono",
            "Liberation Mono",
            "Courier New",
        )


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


# ---------------------------------------------------------------------------
# Review fixes: readable defaults, fitting, validation, contrast
# ---------------------------------------------------------------------------

_FONTS_DIR = os.path.join(os.path.dirname(__file__), "..", "fonts")
_PRESETS = ("modern_light", "modern_dark", "corporate_navy", "vibrant")
_WIDE = (Inches(13.333), Inches(7.5))


def _luminance(rgb):
    def channel(value):
        c = value / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2])


def _contrast(rgb_a, rgb_b):
    la, lb = _luminance(rgb_a), _luminance(rgb_b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _wide(prs):
    prs.slide_width, prs.slide_height = _WIDE
    return prs


def _text_boxes(slide):
    return [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TEXT_BOX]


def _autoshapes(slide):
    return [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE]


def _schema_violations(prs):
    buf = io.BytesIO()
    prs.save(buf)
    return list(iter_schema_violations(buf.getvalue()))


@pytest.fixture
def outfit_tokens():
    """Tokens set in a font shipped with the tests, so fitted sizes are exact."""
    register_font_dir(_FONTS_DIR)
    yield DesignTokens.from_dict(
        {
            "palette": {
                "primary": "#3B5BDB",
                "neutral": "#1F2933",
                "muted": "#7B8794",
                "surface": "#F5F7FA",
                "on_primary": "#FFFFFF",
                "positive": "#0CA678",
                "negative": "#E03131",
            },
            "typography": {
                "heading": {"family": "Outfit", "size": Pt(32), "bold": True},
                "body": {"family": "Outfit", "size": Pt(16)},
            },
        }
    )
    clear_registered_fonts()


@pytest.fixture
def no_mono_fonts(monkeypatch):
    """Pretend no monospace candidate is installed: default family, 0.6em advance."""
    monkeypatch.setattr("power_pptx.text.fonts.font_is_installed", lambda *a, **k: False)
    monkeypatch.setattr("power_pptx.text.fonts.find_font_file", lambda *a, **k: None)


def _code_box(slide):
    return _text_boxes(slide)[-1]


def _code_panel(slide):
    return _autoshapes(slide)[-1]


class DescribeCodeSlideDefaults:
    """`code_slide` is readable and monospace with no tokens at all."""

    def it_is_readable_without_tokens(self, prs):
        slide = code_slide(prs, title="t", code="print(1)")

        panel_fill = _code_panel(slide).fill.fore_color.rgb
        run = _code_box(slide).text_frame.paragraphs[0].runs[0]
        # was #222222 text on a #141418 panel: 1.2:1
        assert _contrast(run.font.color.rgb, panel_fill) >= 4.5

    def it_names_the_first_installed_monospace_family(self, prs, monkeypatch):
        monkeypatch.setattr(
            "power_pptx.text.fonts.font_is_installed",
            lambda name, *a, **k: name in ("Menlo", "Courier New"),
        )
        slide = code_slide(prs, title="t", code="x = 1")

        assert _code_box(slide).text_frame.paragraphs[0].runs[0].font.name == "Menlo"

    def it_falls_back_to_one_default_family_when_none_is_installed(self, prs, no_mono_fonts):
        slide = code_slide(prs, title="t", code="x = 1")

        name = _code_box(slide).text_frame.paragraphs[0].runs[0].font.name
        assert name == "Consolas"
        assert "," not in name

    def it_flags_the_run_fixed_pitch_so_a_missing_font_stays_monospace(self, prs):
        slide = code_slide(prs, title="t", code="x = 1")

        latin = _code_box(slide).text_frame.paragraphs[0].runs[0]._r.rPr.latin
        assert latin.get("pitchFamily") == "49"

    def it_lets_the_caller_name_the_font(self, prs):
        slide = code_slide(prs, title="t", code="x = 1", font="JetBrains Mono")

        runs = [r for p in _code_box(slide).text_frame.paragraphs for r in p.runs]
        assert {r.font.name for r in runs} == {"JetBrains Mono"}

    def it_expands_tabs_so_indentation_has_a_known_width(self, prs):
        slide = code_slide(prs, title="t", code="if x:\n\treturn 1")

        assert _code_box(slide).text_frame.paragraphs[1].text == "    return 1"

    def it_produces_schema_valid_xml(self, prs):
        code_slide(prs, title="t", code="x = 1\ny = 2", language="python")

        assert _schema_violations(prs) == []


class DescribeCodeSlideColours:
    """Text and highlight colours are chosen from the panel, not a fixed dark theme."""

    @pytest.mark.parametrize("preset", [None, *_PRESETS])
    def it_keeps_every_code_colour_readable_on_the_panel(self, prs, preset):
        pytest.importorskip("pygments")
        tokens = DesignTokens.from_preset(preset) if preset else None
        code = "def train(model):\n    # go\n    return model.fit('x', 42, None)\n"

        slide = code_slide(prs, title="t", code=code, language="python", tokens=tokens)

        panel_fill = _code_panel(slide).fill.fore_color.rgb
        runs = [r for p in _code_box(slide).text_frame.paragraphs for r in p.runs]
        colours = {r.font.color.rgb for r in runs}
        assert len(colours) > 1  # it really is highlighted
        # the dark-theme set was 1.8-1.9:1 on the light presets
        assert min(_contrast(c, panel_fill) for c in colours) >= 4.5
        assert not [i for i in slide.lint().issues if i.code == "LowContrast"]

    def it_uses_the_palette_text_colour_when_it_already_reads(self, prs, tokens):
        slide = code_slide(prs, title="t", code="x = 1", tokens=tokens)

        run = _code_box(slide).text_frame.paragraphs[0].runs[0]
        assert run.font.color.rgb == RGBColor(0x22, 0x22, 0x22)  # tokens' neutral


class DescribeCodeSlideFit:
    """The snippet is fitted to the panel instead of running off the slide."""

    def _rows_fit(self, slide):
        box = _code_box(slide)
        tf = box.text_frame
        pitch = tf.paragraphs[0].line_spacing
        inner_h = box.height - tf.margin_top - tf.margin_bottom
        return len(tf.paragraphs) * pitch <= inner_h

    def it_keeps_the_default_size_when_the_snippet_fits(self, prs, no_mono_fonts):
        slide = code_slide(prs, title="t", code="x = 1\ny = 2")

        sizes = {r.font.size for p in _code_box(slide).text_frame.paragraphs for r in p.runs}
        assert sizes == {Pt(14)}

    def it_shrinks_a_long_snippet_until_every_line_fits(self, prs, no_mono_fonts):
        code = "\n".join(f"line_{i} = {i}" for i in range(30))

        slide = code_slide(prs, title="t", code=code)

        tf = _code_box(slide).text_frame
        sizes = {r.font.size for p in tf.paragraphs for r in p.runs}
        assert len(sizes) == 1
        assert Pt(9) <= sizes.pop() < Pt(14)
        assert [p.text for p in tf.paragraphs] == code.splitlines()
        assert self._rows_fit(slide)

    def it_prefers_a_size_at_which_no_line_wraps(self, prs, no_mono_fonts):
        # 100 characters need 11pt or less to stay on one row of a 10in slide.
        slide = code_slide(prs, title="t", code="x" * 100)

        box = _code_box(slide)
        size = box.text_frame.paragraphs[0].runs[0].font.size
        inner_w = box.width - box.text_frame.margin_left - box.text_frame.margin_right
        assert Pt(9) <= size < Pt(14)
        assert 100 * 0.6 * size <= inner_w

    def it_truncates_with_a_marker_when_the_snippet_cannot_fit(self, prs, no_mono_fonts):
        code = "\n".join(f"line_{i} = {i}" for i in range(60))

        slide = code_slide(prs, title="t", code=code)

        tf = _code_box(slide).text_frame
        shown = len(tf.paragraphs) - 1
        assert 0 < shown < 60
        assert tf.paragraphs[-1].text == f"… (+{60 - shown} more lines)"
        assert [p.text for p in tf.paragraphs[:-1]] == code.splitlines()[:shown]
        assert {r.font.size for p in tf.paragraphs for r in p.runs} == {Pt(9)}
        # the 60 lines used to run off the panel and the slide
        assert self._rows_fit(slide)
        assert _code_box(slide).top + _code_box(slide).height <= prs.slide_height

    def it_raises_instead_of_truncating_when_asked(self, prs, no_mono_fonts):
        code = "\n".join(f"line_{i} = {i}" for i in range(60))

        with pytest.raises(ValueError, match=r"60 lines of code do not fit.*; \d+ fit"):
            code_slide(prs, title="t", code=code, overflow="raise")
        assert len(prs.slides) == 0

    def it_rejects_an_unknown_overflow_mode(self, prs):
        with pytest.raises(ValueError, match="overflow must be"):
            code_slide(prs, title="t", code="x", overflow="clip")


def _milestones(n, long=False):
    labels = ["Private alpha with design partners", "Public beta",
              "General availability and pricing launch", "EU region",
              "SOC 2 Type II", "Marketplace", "Mobile apps", "Enterprise tier"]
    return [
        {"date": f"Q{i % 4 + 1} 2026", "label": labels[i] if long else f"Phase {i + 1}"}
        for i in range(n)
    ]


class DescribeTimelineSlideLayout:
    """Labels stay on the slide and clear of the rail for typical milestone counts."""

    @pytest.mark.parametrize("wide", [False, True])
    @pytest.mark.parametrize("n", range(1, 9))
    def it_keeps_every_shape_on_the_slide(self, prs, wide, n):
        if wide:
            _wide(prs)
        slide = timeline_slide(prs, title="Roadmap", milestones=_milestones(n))

        for shape in slide.shapes:
            assert shape.left >= 0
            assert shape.left + shape.width <= prs.slide_width
            assert shape.top >= 0
            assert shape.top + shape.height <= prs.slide_height

    @pytest.mark.parametrize("wide", [False, True])
    @pytest.mark.parametrize("n", range(2, 9))
    @pytest.mark.parametrize("long", [False, True])
    def it_lints_clean_from_two_to_eight_milestones(self, prs, wide, n, long):
        if wide:
            _wide(prs)
        slide = timeline_slide(
            prs, title="Roadmap", milestones=_milestones(n, long),
            tokens=DesignTokens.from_preset("modern_light"),
        )

        # was: OffSlide errors for 2-4 milestones (2-6 on 16:9) and
        # ShapeCollision warnings between labels, rail and markers
        assert [str(issue) for issue in slide.lint().issues] == []

    def it_builds_through_from_spec_with_lint_raise(self):
        from power_pptx.compose import from_spec

        prs = from_spec(
            {
                "lint": "raise",
                "slides": [
                    {
                        "layout": "timeline",
                        "title": "Roadmap",
                        "milestones": [
                            {"date": "Q1", "label": "Alpha"},
                            {"date": "Q2", "label": "Beta"},
                            {"date": "Q3", "label": "GA"},
                        ],
                    }
                ],
            }
        )

        assert len(prs.slides) == 1

    def it_ends_labels_above_the_rail_before_the_marker(self, prs):
        slide = timeline_slide(prs, title="Roadmap", milestones=_milestones(4, long=True))

        dots = [s for s in _autoshapes(slide) if s.width == s.height]
        boxes = _text_boxes(slide)[1:]  # [0] is the title
        assert len(dots) == len(boxes) == 4
        for i, (dot, box) in enumerate(zip(dots, boxes)):
            assert abs((box.left + box.width / 2) - (dot.left + dot.width / 2)) <= 2
            if i % 2 == 0:
                # above the rail: the box stops short of the marker and its
                # text is bottom-anchored, so extra lines grow upwards
                assert box.top + box.height < dot.top
                assert box.text_frame.vertical_anchor == MSO_ANCHOR.BOTTOM
            else:
                assert box.top > dot.top + dot.height
                assert box.text_frame.vertical_anchor == MSO_ANCHOR.TOP

    def it_puts_the_date_and_label_in_one_box_per_milestone(self, prs):
        slide = timeline_slide(
            prs, title="T", milestones=[{"date": "Q1", "label": "Alpha"}, {"label": "Beta"}]
        )

        boxes = _text_boxes(slide)[1:]
        assert [[p.text for p in b.text_frame.paragraphs] for b in boxes] == [
            ["Q1", "Alpha"],
            ["Beta"],
        ]

    def it_declares_the_markers_on_the_rail_as_one_lint_group(self, prs):
        slide = timeline_slide(prs, title="T", milestones=_milestones(3))

        groups = {s.lint_group for s in _autoshapes(slide)}
        assert len(groups) == 1
        assert None not in groups

    def it_rejects_more_milestones_than_fit(self, prs):
        with pytest.raises(ValueError, match="60 milestones do not fit.*at most 15 fit"):
            timeline_slide(prs, title="T", milestones=_milestones(8) * 7 + _milestones(4))
        assert len(prs.slides) == 0


class DescribeRecipeCapacity:
    """Too many items raise, saying how many fit, instead of writing bad geometry."""

    def it_rejects_more_kpis_than_fit_in_a_row(self, prs):
        kpis = [{"label": f"k{i}", "value": str(i)} for i in range(37)]

        # 37 KPIs used to write cx="-4943" (120+ schema violations)
        with pytest.raises(ValueError, match="37 KPIs do not fit.*at most 9 fit"):
            kpi_slide(prs, title="t", kpis=kpis)
        assert len(prs.slides) == 0

    @pytest.mark.parametrize(("wide", "most"), [(False, 9), (True, 12)])
    def it_writes_valid_positive_sizes_at_the_most_kpis_that_fit(self, prs, wide, most):
        if wide:
            _wide(prs)
        kpis = [{"label": f"k{i}", "value": f"${i}M", "delta": 0.1} for i in range(most)]

        slide = kpi_slide(prs, title="t", kpis=kpis)

        assert all(s.width > 0 and s.height > 0 for s in slide.shapes)
        assert _schema_violations(prs) == []
        with pytest.raises(ValueError, match=f"at most {most} fit"):
            kpi_slide(prs, title="t", kpis=kpis + [{"label": "x", "value": "1"}])

    def it_rejects_more_comparison_rows_than_fit(self, prs):
        rows = [{"left": f"l{i}", "right": f"r{i}"} for i in range(49)]

        # 49 rows used to write a negative cy
        with pytest.raises(ValueError, match="49 rows do not fit.*at most 21 fit"):
            comparison_slide(prs, title="t", left_heading="A", right_heading="B", rows=rows)
        assert len(prs.slides) == 0

    def it_writes_valid_positive_sizes_at_the_most_comparison_rows(self, prs):
        rows = [{"left": f"l{i}", "right": f"r{i}"} for i in range(21)]

        slide = comparison_slide(
            prs, title="t", left_heading="A", right_heading="B", rows=rows
        )

        assert all(s.width > 0 and s.height > 0 for s in slide.shapes)
        assert max(s.top + s.height for s in slide.shapes) <= prs.slide_height
        assert _schema_violations(prs) == []

    def it_rejects_a_table_with_more_rows_than_fit(self, prs):
        rows = [[f"Region {i}", f"${i}M", "ok"] for i in range(40)]

        # 40 rows used to show 15 and run the rest off the slide
        with pytest.raises(ValueError, match=r"40 rows do not fit.*; \d+ fit"):
            table_slide(prs, title="t", columns=["Region", "Revenue", "Note"], rows=rows)
        assert len(prs.slides) == 0

    def it_rejects_a_table_with_more_columns_than_fit(self, prs):
        with pytest.raises(ValueError, match="60 columns do not fit.*at most 22 fit"):
            table_slide(prs, title="t", columns=[f"c{i}" for i in range(60)], rows=[])

    def it_rejects_more_bullets_than_fit(self, prs):
        bullets = [f"Bullet number {i} with some reasonably long text" for i in range(30)]

        # 30 bullets used to be left to autofit, which shrank them to ~5pt
        with pytest.raises(ValueError, match=r"30 bullets do not fit.*; \d+ fit"):
            bullet_slide(prs, title="t", bullets=bullets)
        assert len(prs.slides) == 0

    def it_rejects_more_progress_dots_than_fit(self, prs):
        with pytest.raises(ValueError, match="200 progress dots does not fit"):
            section_divider(prs, title="t", progress=(1, 200))
        assert len(prs.slides) == 0


class DescribeBakedFit:
    """Known text is measured and its fitting size written, not left to autofit."""

    def it_bakes_a_fitting_size_into_a_long_title(self, prs, outfit_tokens):
        title = "A title long enough that it cannot sit on one line at its token size " * 2

        slide = title_slide(prs, title=title, tokens=outfit_tokens)

        run = _runs(slide)[0]
        assert Pt(9) <= run.font.size < Pt(32)

    def it_leaves_a_title_that_fits_at_its_token_size(self, prs, outfit_tokens):
        slide = title_slide(prs, title="Q4 Review", tokens=outfit_tokens)

        assert _runs(slide)[0].font.size == Pt(32)

    def it_shrinks_bullets_to_fit_but_never_below_nine_points(self, prs, outfit_tokens):
        bullets = [f"Bullet number {i} with some text" for i in range(16)]

        slide = bullet_slide(prs, title="t", bullets=bullets, tokens=outfit_tokens)

        body = _text_boxes(slide)[-1]
        sizes = {r.font.size for p in body.text_frame.paragraphs for r in p.runs}
        assert len(sizes) == 1
        size = sizes.pop()
        assert Pt(9) <= size < Pt(16)
        # the paragraphs, at the baked size and spacing, fit the body box
        gap = body.text_frame.paragraphs[0].space_after
        inner_h = body.height - body.text_frame.margin_top - body.text_frame.margin_bottom
        assert 16 * (size * 1.26 + gap) <= inner_h

    def it_keeps_the_body_size_for_a_short_bullet_list(self, prs, outfit_tokens):
        slide = bullet_slide(prs, title="t", bullets=["One", "Two"], tokens=outfit_tokens)

        body = _text_boxes(slide)[-1]
        assert {r.font.size for p in body.text_frame.paragraphs for r in p.runs} == {Pt(16)}
        assert body.text_frame.paragraphs[0].space_after == Pt(6)

    def it_sets_one_value_size_across_a_kpi_row(self, prs, outfit_tokens):
        _wide(prs)
        kpis = [{"label": f"Metric {i}", "value": f"${i * 37}M"} for i in range(8)]

        slide = kpi_slide(prs, title="t", kpis=kpis, tokens=outfit_tokens)

        value_sizes = {
            r.font.size
            for r in _runs(slide)
            if r.text.startswith("$")
        }
        # "$0M" fits larger than "$259M"; the row uses the smaller for all
        assert len(value_sizes) == 1
        assert Pt(9) <= value_sizes.pop() < Pt(32)

    def it_sets_one_row_size_across_a_comparison(self, prs, outfit_tokens):
        rows = [{"left": f"Old way number {i} which is slow", "right": f"New {i}"}
                for i in range(16)]

        slide = comparison_slide(
            prs, title="t", left_heading="Before", right_heading="After", rows=rows,
            tokens=outfit_tokens,
        )

        row_sizes = {
            r.font.size for r in _runs(slide) if r.text.startswith(("Old way", "New "))
        }
        assert len(row_sizes) == 1
        assert Pt(9) <= row_sizes.pop() < Pt(16)

    def it_fits_a_twenty_row_table_inside_the_slide(self, prs, outfit_tokens):
        rows = [[f"Region {i}", f"${i}M", "ok"] for i in range(18)]

        slide = table_slide(
            prs, title="t", columns=["Region", "Revenue", "Note"], rows=rows,
            tokens=outfit_tokens,
        )

        frame = next(s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE)
        table = frame.table
        sizes = {
            r.font.size
            for row in table.rows
            for cell in row.cells
            for p in cell.text_frame.paragraphs
            for r in p.runs
        }
        assert min(sizes) >= Pt(9)
        assert max(sizes) < Pt(16)
        heights = [row.height for row in table.rows]
        assert frame.top + sum(heights) <= prs.slide_height - Inches(0.5) + 19
        # each row is tall enough for a line of its text plus the cell insets
        line = max(sizes) * 1.26
        assert min(heights) >= line + Inches(0.1) - 19

    def it_gives_wrapping_rows_the_height_their_text_needs(self, prs, outfit_tokens):
        long_note = "a longer note that has to wrap in a narrow column " * 2
        rows = [["A", long_note], ["B", "ok"], ["C", "ok"], ["D", "ok"], ["E", "ok"]]

        slide = table_slide(
            prs, title="t", columns=["Key", "Note"], rows=rows, widths=[3, 1],
            tokens=outfit_tokens,
        )

        table = next(s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE).table
        heights = [row.height for row in table.rows]
        assert heights[1] > heights[2] == heights[3]


class DescribeTableSlideWidths:
    """`widths` reads bare numbers as weights and Length values as exact widths."""

    def _widths(self, prs, widths, n_cols=3):
        slide = table_slide(
            prs, title="t", columns=list("ABCDE")[:n_cols], rows=[["1"] * n_cols],
            widths=widths,
        )
        table = next(s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE).table
        return [int(c.width) for c in table.columns]

    @pytest.mark.parametrize(
        "widths",
        [[50, 25, 25], [0.5, 0.25, 0.25], [2, 1, 1], [10, 5, 5], [4572000, 2286000, 2286000]],
    )
    def it_reads_bare_numbers_as_relative_weights(self, prs, widths):
        table_w = int(prs.slide_width - Inches(1.2))

        cols = self._widths(prs, widths)

        # [50, 25, 25] used to be 50, 25 and 25 EMU: an invisible table
        assert sum(cols) == table_w
        assert cols[0] == pytest.approx(table_w / 2, abs=2)
        assert cols[1] == pytest.approx(table_w / 4, abs=2)
        assert cols[2] == pytest.approx(table_w / 4, abs=2)

    def it_reads_five_three_two_as_weights_too(self, prs):
        table_w = int(prs.slide_width - Inches(1.2))

        cols = self._widths(prs, [5, 3, 2])

        # used to be 1 EMU / 5.28in / 3.52in
        assert cols == pytest.approx([table_w * 0.5, table_w * 0.3, table_w * 0.2], abs=2)

    def it_splits_the_remainder_between_unspecified_columns(self, prs):
        table_w = int(prs.slide_width - Inches(1.2))

        cols = self._widths(prs, [0.5, 0.25])

        # used to be 5.87in / 2.93in / 0
        assert cols == pytest.approx([table_w / 2, table_w / 4, table_w / 4], abs=2)
        assert self._widths(prs, [0.5]) == pytest.approx(
            [table_w / 2, table_w / 4, table_w / 4], abs=2
        )

    def it_keeps_length_values_exact_and_shares_the_rest_by_weight(self, prs):
        table_w = int(prs.slide_width - Inches(1.2))

        cols = self._widths(prs, [Inches(2), 2, 1])

        rest = table_w - Inches(2)
        assert cols[0] == Inches(2)
        assert cols[1:] == pytest.approx([rest * 2 / 3, rest / 3], abs=2)
        assert self._widths(prs, [Inches(1), Inches(2), Inches(3)]) == [
            Inches(1), Inches(2), Inches(3)
        ]

    @pytest.mark.parametrize(
        ("widths", "message"),
        [
            ([0, 0, 0], "widths\\[0\\] must be a positive number"),
            ([1, -1, 1], "widths\\[1\\] must be a positive number"),
            ([1, "wide", 1], "widths\\[1\\] must be a positive number"),
            ([1, float("nan"), 1], "widths\\[1\\] must be a positive number"),
            ([True, 1, 1], "widths\\[0\\] must be a positive number"),
            ([1, 1, 1, 1], "4 entries for 3 columns"),
            ([0.5, 0.5], "leaves no room"),
            ([5, 3], "leaves no room"),
            ([Inches(20), 1, 1], "leave no room"),
            ([Inches(0), 1, 1], "widths\\[0\\] must be positive"),
        ],
    )
    def it_rejects_widths_that_would_hide_a_column(self, prs, widths, message):
        with pytest.raises(ValueError, match=message):
            self._widths(prs, widths)
        assert len(prs.slides) == 0

    def it_accepts_weights_through_from_spec(self):
        from power_pptx.compose import from_spec

        prs = from_spec(
            {
                "slides": [
                    {
                        "layout": "table",
                        "title": "T",
                        "columns": ["a", "b", "c"],
                        "rows": [["1", "2", "3"]],
                        "widths": [50, 25, 25],
                    }
                ]
            }
        )

        table = next(s for s in prs.slides[0].shapes if getattr(s, "has_table", False)).table
        cols = [int(c.width) for c in table.columns]
        assert cols[0] == pytest.approx(2 * cols[1], abs=2)
        assert min(cols) > Inches(1)

    def it_centres_cell_text_vertically_in_rows_taller_than_their_text(self, prs):
        slide = table_slide(prs, title="t", columns=["a", "b"], rows=[[1, 2]])

        table = next(s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE).table
        anchors = {cell.vertical_anchor for row in table.rows for cell in row.cells}
        assert anchors == {MSO_ANCHOR.MIDDLE}

    def it_rejects_a_row_with_more_values_than_columns(self, prs):
        with pytest.raises(ValueError, match="rows\\[1\\] has 3 values for 2 columns"):
            table_slide(prs, title="t", columns=["a", "b"], rows=[[1, 2], [1, 2, 3]])


def _png(tmp_path, name, size):
    from PIL import Image

    path = tmp_path / name
    Image.new("RGB", size, "#3366CC").save(path)
    return path


class DescribeFigureSlideFit:
    """Figures keep their aspect ratio by default; `fit=` chooses otherwise."""

    def _picture(self, slide):
        return next(s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE)

    def _area(self, prs):
        top = Inches(1.6)
        return Inches(0.6), top, prs.slide_width - Inches(1.2), prs.slide_height - top - Inches(0.5)

    @pytest.mark.parametrize("size", [(400, 400), (200, 800), (800, 200)])
    def it_contains_the_figure_in_the_content_area(self, prs, tmp_path, size):
        left, top, width, height = self._area(prs)

        slide = figure_slide(prs, title="t", figure=str(_png(tmp_path, "f.png", size)))

        pic = self._picture(slide)
        # a 400x400 PNG used to be stretched to 8.80in x 5.40in
        assert pic.width / pic.height == pytest.approx(size[0] / size[1], rel=1e-3)
        assert pic.left >= left
        assert pic.top >= top
        assert pic.left + pic.width <= left + width
        assert pic.top + pic.height <= top + height
        assert pic.width == width or pic.height == height
        # centred in the area
        assert pic.left + pic.width / 2 == pytest.approx(left + width / 2, abs=2)
        assert pic.top + pic.height / 2 == pytest.approx(top + height / 2, abs=2)

    def it_stretches_only_when_asked(self, prs, tmp_path):
        left, top, width, height = self._area(prs)

        slide = figure_slide(
            prs, title="t", figure=str(_png(tmp_path, "f.png", (400, 400))), fit="stretch"
        )

        pic = self._picture(slide)
        assert (pic.left, pic.top, pic.width, pic.height) == (left, top, width, height)

    def it_can_cover_the_area_by_cropping(self, prs, tmp_path):
        left, top, width, height = self._area(prs)

        slide = figure_slide(
            prs, title="t", figure=str(_png(tmp_path, "f.png", (400, 400))), fit="cover"
        )

        pic = self._picture(slide)
        assert (pic.left, pic.top, pic.width, pic.height) == (left, top, width, height)
        assert pic.crop_left == pic.crop_right == 0
        assert pic.crop_top == pic.crop_bottom
        assert pic.crop_top == pytest.approx((1 - height / width) / 2, abs=1e-5)

    def it_rejects_an_unknown_fit(self, prs, tmp_path):
        with pytest.raises(ValueError, match="fit must be one of"):
            figure_slide(prs, title="t", figure=str(_png(tmp_path, "f.png", (4, 4))), fit="zoom")
        assert len(prs.slides) == 0

    def it_accepts_raw_image_bytes(self, prs, tmp_path):
        blob = _png(tmp_path, "f.png", (400, 200)).read_bytes()

        slide = figure_slide(prs, title="t", figure=blob)  # used to raise TypeError

        pic = self._picture(slide)
        assert pic.width / pic.height == pytest.approx(2.0, rel=1e-3)

    def it_accepts_a_binary_file_like_object(self, prs, tmp_path):
        stream = io.BytesIO(_png(tmp_path, "f.png", (400, 200)).read_bytes())

        slide = figure_slide(prs, title="t", figure=stream)  # used to raise TypeError

        assert self._picture(slide).image.size == (400, 200)

    def it_still_rejects_what_it_cannot_dispatch(self, prs):
        with pytest.raises(TypeError, match="raw image bytes"):
            figure_slide(prs, title="t", figure=12345)


class DescribeItemValidation:
    """Malformed item dicts raise instead of rendering blank cards, markers and rows."""

    def it_rejects_kpi_items_with_the_wrong_keys(self, prs):
        with pytest.raises(ValueError) as exc:
            kpi_slide(prs, title="t", kpis=[{"name": "ARR", "val": "$182M"}])

        message = str(exc.value)
        assert message.startswith("kpi_slide: kpis[0]")
        assert "'val' (did you mean 'value'?)" in message
        assert "'name'" in message
        assert "missing required key(s) 'label', 'value'" in message
        assert len(prs.slides) == 0  # used to add a slide with blank cards

    def it_rejects_milestones_with_the_wrong_keys(self, prs):
        with pytest.raises(ValueError, match=r"timeline_slide: milestones\[1\].*'when'"):
            timeline_slide(
                prs, title="t",
                milestones=[{"date": "Q1", "label": "A"}, {"when": "Q2", "title": "B"}],
            )
        assert len(prs.slides) == 0

    def it_rejects_comparison_rows_with_the_wrong_keys(self, prs):
        with pytest.raises(ValueError, match=r"comparison_slide: rows\[0\].*'after'.*'before'"):
            comparison_slide(
                prs, title="t", left_heading="A", right_heading="B",
                rows=[{"before": "slow", "after": "fast"}],
            )
        assert len(prs.slides) == 0

    def it_rejects_chart_series_with_the_wrong_keys(self, prs):
        with pytest.raises(ValueError) as exc:
            chart_slide(
                prs, title="t", categories=["Q1", "Q2"],
                series=[{"label": "ARR", "data": [1, 2]}],
            )

        message = str(exc.value)
        assert message.startswith("chart_slide: series[0]")
        assert "missing required key(s) 'name', 'values'" in message
        assert len(prs.slides) == 0  # used to chart a series ('', [])

    def it_rejects_items_that_are_not_mappings(self, prs):
        with pytest.raises(ValueError, match=r"kpis\[0\] must be a mapping"):
            kpi_slide(prs, title="t", kpis=["ARR"])
        with pytest.raises(ValueError, match="kpis must be a list of mappings"):
            kpi_slide(prs, title="t", kpis={"label": "ARR", "value": "1"})

    def it_reports_bad_items_through_from_spec_with_the_slide_index(self):
        from power_pptx.compose import from_spec

        with pytest.raises(ValueError, match=r"slides\[0\]: kpi_slide: kpis\[0\]"):
            from_spec(
                {"slides": [{"layout": "kpi", "title": "T", "kpis": [{"name": "ARR"}]}]}
            )

    def it_rejects_a_bare_string_of_bullets(self, prs):
        with pytest.raises(ValueError, match="bullets must be a list of strings"):
            bullet_slide(prs, title="t", bullets="one two")

    def it_charts_none_values_as_gaps(self, prs):
        slide = chart_slide(
            prs, title="t", categories=["Q1", "Q2", "Q3"],
            series=[{"name": "ARR", "values": [1, None, 3]}],  # used to raise TypeError
        )

        chart = next(s for s in slide.shapes if s.has_chart).chart
        assert list(chart.plots[0].series[0].values) == [1.0, None, 3.0]
        assert _schema_violations(prs) == []

    def it_rejects_non_numeric_chart_values(self, prs):
        with pytest.raises(ValueError, match=r"series\[0\] 'values' must be numbers or None"):
            chart_slide(
                prs, title="t", categories=["Q1"], series=[{"name": "A", "values": ["x"]}]
            )

    def it_does_not_document_a_chart_type_it_rejects(self):
        assert "scatter" in chart_slide.__doc__  # explained, not offered
        assert '``"scatter"``' not in chart_slide.__doc__


def _text_on(slide, surface_shape):
    """Runs of the text boxes lying inside *surface_shape*, plus its own runs."""
    left, top = surface_shape.left, surface_shape.top
    right, bottom = left + surface_shape.width, top + surface_shape.height
    runs = []
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        inside = (
            shape.left >= left and shape.top >= top
            and shape.left + shape.width <= right and shape.top + shape.height <= bottom
        )
        if inside:
            runs += [r for p in shape.text_frame.paragraphs for r in p.runs if r.text]
    return runs


class DescribePresetContrast:
    """Recipe text meets 4.5:1 on the surface it is drawn on, under every preset."""

    @pytest.mark.parametrize("preset", _PRESETS)
    def it_keeps_kpi_text_readable_on_the_card(self, prs, preset):
        tokens = DesignTokens.from_preset(preset)

        slide = kpi_slide(
            prs, title="Metrics", tokens=tokens,
            kpis=[
                {"label": "ARR", "value": "$182M", "delta": 0.27},
                {"label": "Churn", "value": "2%", "delta": -0.03},
            ],
        )

        card = _autoshapes(slide)[0]
        fill = card.fill.fore_color.rgb
        runs = _text_on(slide, card)
        assert {r.text for r in runs} == {"$182M", "ARR", "+27%"}
        # label contrast used to be 2.2-3.4:1 under all four presets
        assert min(_contrast(r.font.color.rgb, fill) for r in runs) >= 4.5
        assert not [i for i in slide.lint().issues if i.code == "LowContrast"]

    @pytest.mark.parametrize("preset", _PRESETS)
    def it_keeps_the_section_divider_text_readable(self, prs, preset):
        tokens = DesignTokens.from_preset(preset)

        slide = section_divider(prs, title="Part two", eyebrow="PART TWO", tokens=tokens)

        backdrop = _autoshapes(slide)[0].fill.fore_color.rgb
        runs = [r for r in _runs(slide) if r.text]
        # vibrant and modern_dark used to be 3.55 and 4.41:1
        assert min(_contrast(r.font.color.rgb, backdrop) for r in runs) >= 4.5
        assert not [i for i in slide.lint().issues if i.code == "LowContrast"]

    @pytest.mark.parametrize("preset", _PRESETS)
    def it_keeps_comparison_headings_and_rows_readable(self, prs, preset):
        tokens = DesignTokens.from_preset(preset)

        slide = comparison_slide(
            prs, title="Cmp", left_heading="Before", right_heading="After",
            rows=[{"left": "slow", "right": "fast"}], tokens=tokens,
        )

        bands = [s for s in _autoshapes(slide) if s.text_frame.text in ("Before", "After")]
        assert len(bands) == 2
        for band in bands:
            run = band.text_frame.paragraphs[0].runs[0]
            assert _contrast(run.font.color.rgb, band.fill.fore_color.rgb) >= 4.5
        assert not [i for i in slide.lint().issues if i.code == "LowContrast"]

    @pytest.mark.parametrize("preset", _PRESETS)
    def it_keeps_table_header_and_banded_rows_readable(self, prs, preset):
        tokens = DesignTokens.from_preset(preset)

        slide = table_slide(
            prs, title="T", columns=["a", "b"], rows=[[1, 2], [3, 4]], tokens=tokens,
            totals={"label": "Total", "values": [6]},
        )

        table = next(s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TABLE).table
        for row_idx in (0, 1, 3):  # header, first banded row, totals
            cell = table.cell(row_idx, 0)
            run = cell.text_frame.paragraphs[0].runs[0]
            assert _contrast(run.font.color.rgb, cell.fill.fore_color.rgb) >= 4.5

    def it_leaves_a_palette_that_already_contrasts_untouched(self, prs, tokens):
        slide = kpi_slide(
            prs, title="Metrics", kpis=[{"label": "ARR", "value": "$182M"}], tokens=tokens
        )

        colours = {r.text: r.font.color.rgb for r in _runs(slide)}
        assert colours["$182M"] == RGBColor(0x3C, 0x2F, 0x80)  # primary, 10:1 on surface


class DescribeBlankLayoutFallback:
    """Recipes start from an empty slide even when no layout is named "Blank"."""

    def it_prefers_a_layout_without_placeholders_when_blank_is_renamed(self, prs):
        prs.slide_layouts.get_by_name("Blank").name = "Leer"

        slide = title_slide(prs, title="x")

        # used to land on the last layout, "Vertical Title and Text"
        assert slide.slide_layout.name == "Leer"
        assert len(slide.placeholders) == 0

    def it_removes_inherited_placeholders_when_every_layout_has_some(self, prs):
        layouts = prs.slide_layouts
        layouts.remove(layouts.get_by_name("Blank"))

        slide = bullet_slide(prs, title="x", bullets=["a"])

        assert len(slide.placeholders) == 0
        assert [s.shape_type for s in slide.shapes] == [MSO_SHAPE_TYPE.TEXT_BOX] * 2
        assert _schema_violations(prs) == []

    def it_still_uses_the_layout_named_blank(self, prs):
        slide = title_slide(prs, title="x")

        assert slide.slide_layout.name == "Blank"


class DescribeRecipeDeckRoundTrip:
    """Every recipe's new XML survives save -> open -> save and validates."""

    def _deck(self):
        prs = _wide(Presentation())
        tokens = DesignTokens.from_preset("modern_light")
        title_slide(prs, title="Q4 Review", subtitle="April 2026", tokens=tokens)
        bullet_slide(prs, title="Highlights", bullets=["One", "Two"], tokens=tokens)
        kpi_slide(
            prs, title="KPIs", tokens=tokens,
            kpis=[{"label": "ARR", "value": "$182M", "delta": 0.27}],
        )
        table_slide(
            prs, title="Table", columns=["a", "b"], rows=[[1, 2]], widths=[2, 1],
            totals={"label": "Total", "values": [2]}, tokens=tokens,
        )
        code_slide(prs, title="Code", code="x = 1\n" * 80, language="python", tokens=tokens)
        timeline_slide(prs, title="Roadmap", milestones=_milestones(5), tokens=tokens)
        comparison_slide(
            prs, title="Cmp", left_heading="A", right_heading="B",
            rows=[{"left": "l", "right": "r"}], tokens=tokens,
        )
        section_divider(prs, title="Part two", progress=(2, 5), tokens=tokens)
        chart_slide(
            prs, title="Chart", categories=["Q1", "Q2"],
            series=[{"name": "ARR", "values": [1, None]}], tokens=tokens,
        )
        return prs

    def it_round_trips(self):
        from tests.integration.round_trip import assert_round_trip

        assert_round_trip(self._deck)

    def it_validates_against_the_schema(self):
        assert _schema_violations(self._deck()) == []
