"""Unit tests for :mod:`power_pptx.design.components`."""

from __future__ import annotations

import math
import re

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
        assert pill.label.text_frame.paragraphs[0].runs[0].text == "LIVE"

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
# Geometry: a component's inner layout follows its own size
# ---------------------------------------------------------------------------

_PRESETS = ["corporate_navy", "modern_dark", "modern_light", "vibrant"]


def _extents(shape):
    left, top = int(shape.left), int(shape.top)
    return left, top, left + int(shape.width), top + int(shape.height)


def _lint_problems(slide):
    return [str(issue) for issue in slide.lint(min_severity="warning").issues]


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


def _inside(inner, outer, slack=2):
    il, it, ir, ib = _extents(inner)
    ol, ot, orr, ob = _extents(outer)
    return il >= ol - slack and it >= ot - slack and ir <= orr + slack and ib <= ob + slack


class DescribeKpiCardLayout:
    """The value / label / delta rows are derived from the card's height."""

    @staticmethod
    def _card(slide, height, *, delta=True, tokens=None, width=2.5):
        return add_kpi_card(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(width),
            height=Inches(height),
            label="Net dollar retention",
            value="131%",
            delta={"delta": 0.03} if delta else None,
            tokens=tokens,
        )

    @pytest.mark.parametrize("delta", [False, True])
    @pytest.mark.parametrize("height", [1.3, 1.5, 1.9, 2.5, 3.5])
    def it_keeps_every_inner_box_inside_the_card(self, slide, height, delta):
        kpi = self._card(slide, height, delta=delta)
        boxes = [kpi.value_box, kpi.label_box] + ([kpi.delta_box] if delta else [])
        for box in boxes:
            assert _inside(box, kpi.card), (height, box.text_frame.text)

    @pytest.mark.parametrize("height", [1.3, 1.5, 1.9, 2.5])
    def it_stacks_the_rows_without_overlap(self, slide, height):
        kpi = self._card(slide, height)
        value, label, delta = (_extents(b) for b in (kpi.value_box, kpi.label_box, kpi.delta_box))
        assert value[3] <= label[1] + 1
        assert label[3] <= delta[1] + 1

    @pytest.mark.parametrize("height", [1.3, 1.5, 1.9])
    def it_gives_each_row_room_for_its_text(self, slide, height):
        kpi = self._card(slide, height)
        for box in (kpi.value_box, kpi.label_box, kpi.delta_box):
            size = box.text_frame.paragraphs[0].runs[0].font.size.pt
            assert size * 1.2 * 12700 + 2 * 45720 <= int(box.height) + 2, box.text_frame.text

    def it_keeps_the_legacy_rows_at_the_default_height(self, slide):
        kpi = self._card(slide, 1.9)
        top = int(Inches(1))
        assert int(kpi.value_box.top) == top + int(Inches(0.25))
        assert int(kpi.value_box.height) == int(Inches(0.85))
        assert int(kpi.label_box.top) == top + int(Inches(1.10))
        assert int(kpi.label_box.height) == int(Inches(0.4))
        assert int(kpi.delta_box.top) == top + int(Inches(1.50))
        assert int(kpi.delta_box.height) == int(Inches(0.35))

    def it_lays_the_rows_out_alike_with_or_without_a_delta(self, slide):
        # Cards in one strip must keep their values and labels aligned.
        with_delta = self._card(slide, 1.5, delta=True)
        without = self._card(slide, 1.5, delta=False)
        assert int(with_delta.value_box.top) - int(with_delta.card.top) == int(
            without.value_box.top
        ) - int(without.card.top)
        assert int(with_delta.label_box.top) - int(with_delta.card.top) == int(
            without.label_box.top
        ) - int(without.card.top)

    def it_centres_the_rows_in_a_tall_card(self, slide):
        kpi = self._card(slide, 3.5)
        extra = int(Inches(3.5)) - int(Inches(1.9))
        assert int(kpi.value_box.top) - int(kpi.card.top) == int(Inches(0.25)) + extra // 2

    def it_raises_instead_of_hanging_text_below_the_card(self, slide):
        with pytest.raises(ValueError, match=r"at least \d\.\d\d in"):
            self._card(slide, 1.2)
        assert len(slide.shapes) == 0

    def it_names_a_height_that_does_work(self, slide):
        with pytest.raises(ValueError) as excinfo:
            self._card(slide, 1.0)
        found = re.search(r"at least (\d\.\d\d) in", str(excinfo.value))
        assert found is not None
        minimum = float(found.group(1))
        kpi = self._card(slide, minimum)
        for box in (kpi.value_box, kpi.label_box, kpi.delta_box):
            assert _inside(box, kpi.card)
        with pytest.raises(ValueError):
            self._card(slide, minimum - 0.05)

    def it_needs_more_height_for_larger_token_typography(self, slide):
        tokens = DesignTokens.from_preset("modern_light")  # 32 pt value
        with pytest.raises(ValueError, match="at least"):
            self._card(slide, 1.3, tokens=tokens)
        kpi = self._card(slide, 1.9, tokens=tokens)
        assert _inside(kpi.value_box, kpi.card)

    def it_lints_clean_in_a_stat_strip(self, slide):
        add_stat_strip(
            slide,
            left=Inches(0.5),
            top=Inches(1),
            width=Inches(9),
            height=Inches(1.5),
            items=[
                {"label": "ARR", "value": "$182M", "delta": 0.27},
                {"label": "NDR", "value": "131%"},
                {"label": "CAC payback", "value": "8 mo", "delta_text": "-2 mo"},
                {"label": "Logos", "value": "412"},
            ],
        )
        assert _lint_problems(slide) == []


class DescribeArticleCardLayout:
    """Title, blurb and CTA are placed from the card's size, not the deck's."""

    @staticmethod
    def _card(slide, *, title="Q4 customer wins", blurb="Two flagship rollouts shipped.", **kw):
        kw.setdefault("height", Inches(3))
        kw.setdefault("cta_text", "Read more")
        return add_article_card(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(4),
            title=title,
            blurb=blurb,
            **kw,
        )

    @pytest.mark.parametrize("preset", _PRESETS)
    def it_scales_the_inner_type_to_the_card_not_to_the_deck(self, slide, preset):
        # Every preset backfills a 32 pt heading and a 16 pt body.
        card = self._card(slide, tokens=DesignTokens.from_preset(preset))
        assert card.title_box.text_frame.paragraphs[0].runs[0].font.size <= Pt(16)
        assert card.blurb_box.text_frame.paragraphs[0].runs[0].font.size <= Pt(11)

    def it_does_not_enlarge_a_token_smaller_than_the_default(self, slide):
        tokens = DesignTokens.from_dict(
            {"typography": {"heading": {"family": "Inter", "size": Pt(13), "bold": True}}}
        )
        card = self._card(slide, tokens=tokens)
        assert card.title_box.text_frame.paragraphs[0].runs[0].font.size == Pt(13)

    @pytest.mark.parametrize("preset", _PRESETS)
    @pytest.mark.parametrize(
        "title",
        [
            "Q4 wins",
            "A fairly long article headline for the card",
            "An extremely long article headline that keeps going and going and going on past "
            "any sensible two lines of text",
        ],
    )
    def it_keeps_title_blurb_and_cta_apart_and_inside_the_card(self, slide, preset, title):
        card = self._card(
            slide,
            title=title,
            blurb="Five-month rollout, 30% lift in qualified leads. " * 2,
            height=Inches(3.6),
            tokens=DesignTokens.from_preset(preset),
        )
        title_box, blurb_box = card.title_box, card.blurb_box
        cta_box = card.cta.pill
        for box in (title_box, blurb_box, cta_box):
            assert _inside(box, card.card), box.name
        assert _extents(title_box)[3] <= _extents(blurb_box)[1] + 1
        assert _extents(blurb_box)[3] <= _extents(cta_box)[1] + 1
        for box in (title_box, blurb_box):
            assert _estimated_text_height_pt(box) <= _inner_height_pt(box) + 0.5, box.name
        assert _lint_problems(slide) == []

    def it_leaves_the_one_line_title_layout_as_it_was(self, slide):
        card = self._card(slide)
        assert int(card.title_box.height) == int(Inches(0.5))
        assert int(card.blurb_box.top) == (
            int(Inches(1)) + int(Inches(0.25)) + int(Inches(0.5)) + int(Inches(0.05))
        )
        assert int(card.blurb_box.height) == (
            int(Inches(3))
            - 2 * int(Inches(0.25))
            - int(Inches(0.5))
            - int(Inches(0.35))
            - int(Inches(0.1))
        )

    def it_grows_the_title_box_and_pushes_the_blurb_down_for_a_longer_title(self, slide):
        short = self._card(slide)
        long = add_article_card(
            slide,
            left=Inches(6),
            top=Inches(1),
            width=Inches(4),
            height=Inches(3),
            title="A fairly long article headline for the card",
            blurb="Two flagship rollouts shipped.",
            cta_text="Read more",
        )
        assert int(long.title_box.height) > int(short.title_box.height)
        assert int(long.blurb_box.top) > int(short.blurb_box.top)

    def it_shrinks_a_long_blurb_to_its_box(self, slide):
        # About 420 characters: too many for the box at 11 pt, fine at 9 pt.
        card = self._card(slide, blurb="Words of the blurb. " * 21, height=Inches(3.2))
        run = card.blurb_box.text_frame.paragraphs[0].runs[0]
        assert Pt(9) <= run.font.size < Pt(11)
        assert _estimated_text_height_pt(card.blurb_box) <= _inner_height_pt(card.blurb_box)

    def it_works_without_a_cta_or_a_blurb(self, slide):
        card = add_article_card(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(4),
            height=Inches(1.6),
            title="Just a headline",
        )
        assert card.cta is None
        assert int(card.blurb_box.height) >= 0
        assert _inside(card.blurb_box, card.card)

    @pytest.mark.parametrize("height", [0.3, 0.8, 1.0, 1.2])
    def it_rejects_a_card_too_short_for_its_content(self, slide, height):
        with pytest.raises(ValueError, match=r"at least \d\.\d\d in"):
            self._card(slide, height=Inches(height))
        assert len(slide.shapes) == 0

    def it_names_a_height_that_does_work(self, slide):
        with pytest.raises(ValueError) as excinfo:
            self._card(slide, height=Inches(1.0))
        found = re.search(r"at least (\d\.\d\d) in", str(excinfo.value))
        assert found is not None
        minimum = float(found.group(1))
        card = self._card(slide, height=Inches(minimum))
        assert int(card.blurb_box.height) > 0
        assert _inside(card.blurb_box, card.card)
        assert _lint_problems(slide) == []
        with pytest.raises(ValueError):
            self._card(slide, height=Inches(minimum - 0.05))

    def it_never_emits_a_negative_extent(self):
        # a:ext cx / cy below zero is schema-invalid and has PowerPoint offer to repair.
        for tenths in range(2, 36):
            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            try:
                self._card(slide, height=Inches(tenths / 10))
            except ValueError:
                assert len(slide.shapes) == 0
                continue
            for shape in slide.shapes:
                assert int(shape.width) >= 0
                assert int(shape.height) >= 0

    def it_validates_against_the_schema_at_the_smallest_sizes(self):
        import io

        from tests.schema.oxml_schema_validator import (
            iter_schema_violations,
            schema_validation_available,
        )

        if not schema_validation_available():
            pytest.skip("schema validation unavailable")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        for i, height in enumerate((1.8, 2.0, 3.0)):
            add_article_card(
                slide,
                left=Inches(0.3 + 3.1 * i),
                top=Inches(1),
                width=Inches(3),
                height=Inches(height),
                title="Q4 wins",
                blurb="Short blurb.",
                cta_text="Read",
            )
        add_kpi_card(
            slide,
            left=Inches(1),
            top=Inches(4.5),
            width=Inches(2.5),
            height=Inches(1.4),
            label="ARR",
            value="$1M",
            delta={"delta": 0.1},
        )
        buf = io.BytesIO()
        prs.save(buf)
        assert list(iter_schema_violations(buf.getvalue())) == []

    def it_keeps_the_cta_inside_a_narrow_card(self, slide):
        card = add_article_card(
            slide,
            left=Inches(1),
            top=Inches(1),
            width=Inches(1.4),
            height=Inches(3),
            title="Wins",
            blurb="Short.",
            cta_text="Read more",
        )
        assert _inside(card.cta.pill, card.card)

    def it_rejects_a_card_too_narrow_to_hold_text(self, slide):
        with pytest.raises(ValueError, match=r"at least \d\.\d\d in wide"):
            add_article_card(
                slide,
                left=Inches(1),
                top=Inches(1),
                width=Inches(0.6),
                height=Inches(3),
                title="Wins",
            )
        assert len(slide.shapes) == 0
