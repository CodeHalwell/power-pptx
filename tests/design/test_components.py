"""Unit tests for :mod:`power_pptx.design.components`."""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx.design.components import (
    ArticleCard,
    Gauge,
    KpiCard,
    ProgressBar,
    StatStrip,
    StatusPill,
    add_article_card,
    add_gauge,
    add_kpi_card,
    add_progress_bar,
    add_stat_strip,
    add_status_pill,
)
from power_pptx.design.tokens import DesignTokens
from power_pptx.dml.color import RGBColor
from power_pptx.util import Inches, Pt


@pytest.fixture
def slide():
    prs = Presentation()
    return prs.slides.add_slide(prs.slide_layouts[6])


@pytest.fixture
def tokens():
    return DesignTokens.from_dict(
        {
            "palette": {
                "primary": "#3C2F80",
                "neutral": "#222222",
                "accent": "#FF6600",
                "muted": "#777777",
                "surface": "#F5F5F8",
                "positive": "#119922",
                "negative": "#DD2233",
            }
        }
    )


class DescribeAddKpiCard:
    def it_returns_a_KpiCard_with_card_value_and_label_shapes(self, slide, tokens):
        result = add_kpi_card(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(2),
            height=Inches(2),
            label="ARR",
            value="$182M",
            tokens=tokens,
        )
        assert isinstance(result, KpiCard)
        assert result.card is not None
        assert result.value_box is not None
        assert result.label_box is not None
        # No delta dict supplied → no delta box.
        assert result.delta_box is None

    def it_renders_a_delta_when_supplied(self, slide, tokens):
        result = add_kpi_card(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(2),
            height=Inches(2),
            label="ARR",
            value="$182M",
            delta={"delta": 0.27},
            tokens=tokens,
        )
        assert result.delta_box is not None
        # The fraction 0.27 renders as "+27%".
        rendered = result.delta_box.text_frame.paragraphs[0].runs[0].text
        assert "27" in rendered

    def it_tags_constituent_shapes_with_a_lint_group(self, slide, tokens):
        result = add_kpi_card(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(2),
            height=Inches(2),
            label="ARR",
            value="$182M",
            delta={"delta": 0.27},
            tokens=tokens,
        )
        groups = {
            result.card.lint_group,
            result.value_box.lint_group,
            result.label_box.lint_group,
            result.delta_box.lint_group,
        }
        assert len(groups) == 1
        assert next(iter(groups)).startswith("kpi_card@")

    def it_works_without_tokens(self, slide):
        # Should fall back to PowerPoint defaults rather than raise.
        result = add_kpi_card(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(2),
            height=Inches(2),
            label="ARR",
            value="$182M",
        )
        assert isinstance(result, KpiCard)


class DescribeAddProgressBar:
    def it_creates_a_track_and_fill_shape(self, slide, tokens):
        bar = add_progress_bar(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(4),
            height=Inches(0.3),
            fraction=0.5,
            tokens=tokens,
        )
        assert isinstance(bar, ProgressBar)
        assert bar.track is not None
        assert bar.fill is not None

    def it_sizes_the_fill_proportional_to_fraction(self, slide, tokens):
        bar = add_progress_bar(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(4),
            height=Inches(0.3),
            fraction=0.25,
            tokens=tokens,
        )
        # 25% of 4" (allow ±1 EMU rounding tolerance).
        assert abs(int(bar.fill.width) - int(Inches(1))) <= 1
        assert int(bar.track.width) == int(Inches(4))

    def it_clamps_out_of_range_fractions(self, slide, tokens):
        bar = add_progress_bar(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(4),
            height=Inches(0.3),
            fraction=1.5,  # > 1.0 — clamp to 1.0
            tokens=tokens,
        )
        assert int(bar.fill.width) == int(Inches(4))

    def it_emits_a_zero_width_fill_at_zero_fraction(self, slide, tokens):
        bar = add_progress_bar(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(4),
            height=Inches(0.3),
            fraction=0.0,
            tokens=tokens,
        )
        # Zero fill but the shape is still emitted so callers can
        # mutate / animate it later.
        assert int(bar.fill.width) == 0

    def it_honours_explicit_fill_color(self, slide):
        bar = add_progress_bar(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(4),
            height=Inches(0.3),
            fraction=0.5,
            fill_color="#FF0000",
        )
        assert bar.fill.fill.fore_color.rgb == RGBColor(0xFF, 0x00, 0x00)

    def it_tags_track_and_fill_with_a_lint_group(self, slide, tokens):
        bar = add_progress_bar(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(4),
            height=Inches(0.3),
            fraction=0.5,
            tokens=tokens,
        )
        assert bar.track.lint_group == bar.fill.lint_group
        assert bar.track.lint_group.startswith("progress_bar@")


class DescribeAddGauge:
    def it_creates_a_track_fill_and_target_tick(self, slide, tokens):
        gauge = add_gauge(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(4),
            height=Inches(0.3),
            fraction=0.62,
            target=0.8,
            tokens=tokens,
        )
        assert isinstance(gauge, Gauge)
        assert gauge.track is not None
        assert gauge.fill is not None
        assert gauge.target_tick is not None

    def it_omits_target_tick_when_target_is_None(self, slide, tokens):
        gauge = add_gauge(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(4),
            height=Inches(0.3),
            fraction=0.5,
            tokens=tokens,
        )
        assert gauge.target_tick is None


class DescribeAddStatusPill:
    def it_returns_a_pill_and_label(self, slide, tokens):
        pill = add_status_pill(
            slide,
            left=Inches(0.5),
            top=Inches(0.5),
            width=Inches(1.2),
            height=Inches(0.35),
            text="LIVE",
            tokens=tokens,
        )
        assert isinstance(pill, StatusPill)
        assert pill.pill is not None
        assert pill.label is not None
        assert (
            pill.label.text_frame.paragraphs[0].runs[0].text == "LIVE"
        )

    def it_honours_explicit_accent(self, slide):
        pill = add_status_pill(
            slide,
            left=Inches(0.5),
            top=Inches(0.5),
            width=Inches(1.2),
            height=Inches(0.35),
            text="DRAFT",
            accent="#888888",
        )
        assert pill.pill.fill.fore_color.rgb == RGBColor(0x88, 0x88, 0x88)


class DescribeAddStatStrip:
    def it_lays_out_n_kpi_cards_across_the_strip(self, slide, tokens):
        strip = add_stat_strip(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(9),
            height=Inches(1.9),
            items=[
                {"label": "ARR", "value": "$182M"},
                {"label": "NDR", "value": "131%", "delta": +0.03},
                {"label": "CAC", "value": "8 mo"},
            ],
            tokens=tokens,
        )
        assert isinstance(strip, StatStrip)
        assert len(strip.cards) == 3
        # First card sits at the strip's left edge.
        first = strip.cards[0]
        assert int(first.card.left) == int(Inches(1))
        # Cards must not overlap each other (gutter > 0).
        last = strip.cards[-1]
        right_edge = int(last.card.left) + int(last.card.width)
        assert right_edge <= int(Inches(1) + Inches(9)) + 1  # rounding tol

    def it_returns_an_empty_strip_for_empty_items(self, slide, tokens):
        strip = add_stat_strip(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(9),
            height=Inches(1.9),
            items=[],
            tokens=tokens,
        )
        assert strip.cards == []


class DescribeAddArticleCard:
    def it_creates_card_title_and_blurb(self, slide, tokens):
        article = add_article_card(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(4),
            height=Inches(2.5),
            title="Q4 customer wins",
            blurb="Two flagship rollouts shipped this quarter.",
            tokens=tokens,
        )
        assert isinstance(article, ArticleCard)
        assert article.card is not None
        # No CTA → cta is None.
        assert article.cta is None

    def it_renders_a_cta_pill_when_cta_text_supplied(self, slide, tokens):
        article = add_article_card(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(4),
            height=Inches(2.5),
            title="Read the case study",
            blurb="Five-month rollout, 30% lift in qualified leads.",
            cta_text="Read more",
            tokens=tokens,
        )
        assert article.cta is not None
        assert isinstance(article.cta, StatusPill)


# ---------------------------------------------------------------------------
# Review fixes: card height, strip capacity, item validation, contrast
# ---------------------------------------------------------------------------


def _wcag_contrast(rgb_a, rgb_b):
    def luminance(rgb):
        def channel(value):
            c = value / 255.0
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        return 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2])

    la, lb = luminance(rgb_a), luminance(rgb_b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _kpi(slide, height, tokens=None, **kwargs):
    return add_kpi_card(
        slide,
        left=Inches(1),
        top=Inches(1),
        width=Inches(2.5),
        height=height,
        label="ARR",
        value="$182M",
        delta={"delta": 0.27},
        tokens=tokens,
        **kwargs,
    )


class DescribeAddKpiCardHeight:
    """The inner layout follows the card's `height` instead of a fixed 1.9in stack."""

    @pytest.mark.parametrize("height", [Inches(1.0), Inches(1.2), Inches(1.5)])
    def it_keeps_the_stack_inside_a_short_card(self, slide, tokens, height):
        card = _kpi(slide, height, tokens)

        bottom = card.card.top + card.card.height
        # with height=1.0in the delta box used to end 0.85in below the card
        for box in (card.value_box, card.label_box, card.delta_box):
            assert box.top >= card.card.top
            assert box.top + box.height <= bottom
        assert card.value_box.top + card.value_box.height <= card.label_box.top
        assert card.label_box.top + card.label_box.height <= card.delta_box.top

    def it_bakes_readable_sizes_into_a_short_card(self, slide, tokens):
        card = _kpi(slide, Inches(1.0), tokens)

        sizes = [
            box.text_frame.paragraphs[0].runs[0].font.size
            for box in (card.value_box, card.label_box, card.delta_box)
        ]
        assert all(size >= Pt(9) for size in sizes)
        assert sizes[0] < Pt(30)  # the value shrank to its shorter band

    @pytest.mark.parametrize("height", [Inches(1.9), Inches(2.4)])
    def it_keeps_the_established_layout_at_full_height_and_above(self, slide, tokens, height):
        card = _kpi(slide, height, tokens)

        top = card.card.top
        assert card.value_box.top - top == Inches(0.25)
        assert card.value_box.height == Inches(0.85)
        assert card.label_box.top - top == Inches(1.10)
        assert card.label_box.height == Inches(0.4)
        assert card.delta_box.top - top == Inches(1.50)
        assert card.delta_box.height == Inches(0.35)

    def it_rejects_a_card_too_short_to_read(self, slide, tokens):
        before = slide._element.xml
        with pytest.raises(ValueError, match="height 0.50in is too small.*at least 0.95in"):
            _kpi(slide, Inches(0.5), tokens)
        assert slide._element.xml == before


class DescribeAddKpiCardContrast:
    @pytest.mark.parametrize(
        "preset", ["modern_light", "modern_dark", "corporate_navy", "vibrant"]
    )
    def it_keeps_card_text_readable_under_every_preset(self, slide, preset):
        card = _kpi(slide, Inches(1.9), DesignTokens.from_preset(preset))

        fill = card.card.fill.fore_color.rgb
        for box in (card.value_box, card.label_box, card.delta_box):
            colour = box.text_frame.paragraphs[0].runs[0].font.color.rgb
            assert _wcag_contrast(colour, fill) >= 4.5
        assert not [i for i in slide.lint().issues if i.code == "LowContrast"]


class DescribeAddStatStripCapacity:
    def it_rejects_more_items_than_fit(self, slide, tokens):
        before = slide._element.xml
        items = [{"label": f"L{i}", "value": str(i)} for i in range(60)]

        # 60 items used to write negative card widths
        with pytest.raises(ValueError, match="60 items do not fit.*at most 12 fit"):
            add_stat_strip(
                slide, left=Inches(0.5), top=Inches(1.5), width=Inches(12),
                height=Inches(1.9), items=items, tokens=tokens,
            )
        assert slide._element.xml == before

    def it_lays_out_the_most_items_that_fit_with_positive_sizes(self, slide, tokens):
        items = [{"label": f"L{i}", "value": str(i)} for i in range(12)]

        strip = add_stat_strip(
            slide, left=Inches(0.5), top=Inches(1.5), width=Inches(12),
            height=Inches(1.9), items=items, tokens=tokens,
        )

        assert len(strip.cards) == 12
        assert all(card.card.width >= Inches(0.75) for card in strip.cards)

    def it_rejects_items_with_the_wrong_keys(self, slide, tokens):
        with pytest.raises(ValueError) as exc:
            add_stat_strip(
                slide, left=Inches(1), top=Inches(1), width=Inches(9), height=Inches(1.9),
                items=[{"label": "ARR", "value": "$182M"}, {"name": "NDR", "val": "131%"}],
                tokens=tokens,
            )

        message = str(exc.value)
        assert message.startswith("add_stat_strip: items[1]")
        assert "'val' (did you mean 'value'?)" in message

    def it_sets_one_value_size_across_the_strip(self, slide, tokens):
        items = [
            {"label": "Short", "value": "9"},
            {"label": "Long", "value": "$1,234,567,890"},
            {"label": "Mid", "value": "131%"},
        ]

        strip = add_stat_strip(
            slide, left=Inches(1), top=Inches(1), width=Inches(6), height=Inches(1.9),
            items=items, tokens=tokens,
        )

        sizes = {c.value_box.text_frame.paragraphs[0].runs[0].font.size for c in strip.cards}
        assert len(sizes) == 1
        assert Pt(9) <= sizes.pop() < Pt(30)
