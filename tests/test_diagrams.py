"""Unit tests for :mod:`power_pptx.diagrams`."""

from __future__ import annotations

import itertools
import math

import pytest

from power_pptx import BBox, Presentation
from power_pptx.diagrams import (
    comparison_columns,
    cycle,
    decision_tree,
    horizontal_pipeline,
    hub_and_spoke,
    vertical_pipeline,
)
from power_pptx.util import Inches, Pt


@pytest.fixture
def slide():
    prs = Presentation()
    return prs.slides.add_slide(prs.slide_layouts[6])


class DescribeHorizontalPipeline:
    def it_creates_one_card_per_step(self, slide):
        result = horizontal_pipeline(
            slide,
            BBox.from_inches(0, 0, 8, 1.5),
            steps=["A", "B", "C", "D"],
        )
        assert len(result.cards) == 4

    def it_creates_n_minus_one_arrows(self, slide):
        result = horizontal_pipeline(
            slide,
            BBox.from_inches(0, 0, 8, 1.5),
            steps=["A", "B", "C"],
        )
        assert len(result.arrows) == 2

    def it_accepts_dict_steps_with_per_step_colors(self, slide):
        result = horizontal_pipeline(
            slide,
            BBox.from_inches(0, 0, 8, 1.5),
            steps=[{"label": "A", "fill": "#FF0000"}, {"label": "B"}],
        )
        assert len(result.cards) == 2

    def it_raises_on_empty_steps(self, slide):
        with pytest.raises(ValueError):
            horizontal_pipeline(slide, BBox.from_inches(0, 0, 8, 1.5), steps=[])


class DescribeVerticalPipeline:
    def it_stacks_cards_vertically(self, slide):
        result = vertical_pipeline(
            slide,
            BBox.from_inches(0, 0, 4, 6),
            steps=["A", "B", "C"],
        )
        assert len(result.cards) == 3
        # Each subsequent card lives below the previous one
        assert int(result.cards[1].top) > int(result.cards[0].top)


class DescribeHubAndSpoke:
    def it_creates_hub_plus_n_spokes(self, slide):
        result = hub_and_spoke(
            slide,
            BBox.from_inches(0, 0, 8, 6),
            centre="Core",
            spokes=["A", "B", "C", "D"],
        )
        assert result.hub is not None
        assert len(result.spokes) == 4
        assert len(result.arrows) == 4


class DescribeCycle:
    def it_creates_a_loop_with_n_arrows(self, slide):
        result = cycle(
            slide,
            BBox.from_inches(0, 0, 8, 6),
            steps=["Observe", "Orient", "Decide", "Act"],
        )
        assert len(result.cards) == 4
        # Arrows count equals card count (cycle wraps around)
        assert len(result.arrows) == 4

    def it_fits_long_labels_inside_the_node(self, slide):
        # A label longer than the circle can show at the requested size must
        # be shrunk by the fit_text pre-flight rather than wrapped/clipped.
        result = cycle(
            slide,
            BBox.from_inches(3, 2, 4, 2.5),
            steps=["Retrieval", "Ingest", "Model", "Observe"],
            size_pt=14.0,
        )
        sizes = [
            int(run.font.size)
            for card in result.cards
            for para in card.text_frame.paragraphs
            for run in para.runs
            if run.font.size is not None
        ]
        assert sizes  # fit_text applied a concrete size to every run
        assert max(sizes) <= Pt(14)


class DescribeHubAndSpokeFit:
    def it_fits_long_spoke_labels(self, slide):
        result = hub_and_spoke(
            slide,
            BBox.from_inches(3, 1.5, 5, 4),
            centre="Retrieval",
            spokes=["Retrieval", "Ingest", "Observe", "Model"],
            size_pt=14.0,
        )
        for spoke in result.spokes:
            for para in spoke.text_frame.paragraphs:
                for run in para.runs:
                    if run.font.size is not None:
                        assert int(run.font.size) <= Pt(14)


class DescribeDecisionTree:
    def it_creates_a_root_plus_branches(self, slide):
        result = decision_tree(
            slide,
            BBox.from_inches(0, 0, 8, 6),
            root="Q?",
            branches=["Yes", "No"],
        )
        assert result.root is not None
        # Two branch cards, two arrows from root
        assert len(result.branches) == 2

    def it_supports_one_level_of_children(self, slide):
        result = decision_tree(
            slide,
            BBox.from_inches(0, 0, 8, 6),
            root="Q?",
            branches=[
                {"label": "Yes", "children": ["a", "b"]},
                {"label": "No", "children": ["c"]},
            ],
        )
        # 2 branches + 3 children
        assert len(result.branches) == 5

    def it_inherits_fill_and_text_color_on_leaf_nodes(self, slide):
        # Regression: leaf (child) nodes used to hardcode a light fill,
        # producing invisible light-on-light text on dark decks.  They must
        # now inherit ``fill`` / ``text_color`` from the recipe.
        from power_pptx._color import coerce_color

        result = decision_tree(
            slide,
            BBox.from_inches(0, 0, 11, 5),
            root="Request",
            branches=[{"label": "Cache miss", "children": ["Compute", "Store"]}],
            fill="#141A23",
            text_color="#E6EDF3",
        )
        leaves = [b for b in result.branches if b.text_frame.text in ("Compute", "Store")]
        assert len(leaves) == 2
        for leaf in leaves:
            assert leaf.fill.fore_color.rgb == coerce_color("#141A23")
            run = leaf.text_frame.paragraphs[0].runs[0]
            assert run.font.color.rgb == coerce_color("#E6EDF3")

    def it_allows_distinct_leaf_styling(self, slide):
        from power_pptx._color import coerce_color

        result = decision_tree(
            slide,
            BBox.from_inches(0, 0, 11, 5),
            root="Request",
            branches=[{"label": "Branch", "children": ["Leaf"]}],
            fill="#141A23",
            text_color="#E6EDF3",
            leaf_fill="#222C3A",
            leaf_text_color="#FFD166",
        )
        leaf = next(b for b in result.branches if b.text_frame.text == "Leaf")
        assert leaf.fill.fore_color.rgb == coerce_color("#222C3A")
        assert leaf.text_frame.paragraphs[0].runs[0].font.color.rgb == coerce_color("#FFD166")


class DescribeComparisonColumns:
    def it_creates_header_and_body_per_column(self, slide):
        result = comparison_columns(
            slide,
            BBox.from_inches(0, 0, 8, 4),
            columns=[
                {"title": "X", "body": "a"},
                {"title": "Y", "body": ["a", "b"]},
            ],
        )
        assert len(result.headers) == 2
        assert len(result.columns) == 2


# ---------------------------------------------------------------------------
# Ring layouts: nothing may overlap, and the linter must be able to tell
# ---------------------------------------------------------------------------

_RING_BBOXES = [
    pytest.param(BBox.from_inches(0.5, 1.5, 9.0, 5.5), id="4:3 area"),
    pytest.param(BBox.from_inches(0.6, 1.6, 12.1, 5.4), id="16:9 area"),
    pytest.param(BBox.from_inches(1, 1, 3, 3), id="small"),
]
_ROOMY_BBOXES = _RING_BBOXES[:2]


def _circle(shape):
    """Return ``(cx, cy, radius)`` of a round shape, in EMU."""
    return (
        int(shape.left) + int(shape.width) / 2,
        int(shape.top) + int(shape.height) / 2,
        int(shape.width) / 2,
    )


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _lint_problems(slide):
    return [str(issue) for issue in slide.lint(min_severity="warning").issues]


def _inside_bbox(shape, bbox, slack=2):
    return (
        int(shape.left) >= int(bbox.left) - slack
        and int(shape.top) >= int(bbox.top) - slack
        and int(shape.left) + int(shape.width) <= int(bbox.right) + slack
        and int(shape.top) + int(shape.height) <= int(bbox.bottom) + slack
    )


class DescribeHubAndSpokeGeometry:
    @pytest.mark.parametrize("bbox", _RING_BBOXES)
    @pytest.mark.parametrize("n", range(1, 13))
    def it_keeps_spokes_clear_of_the_hub_and_of_each_other(self, slide, bbox, n):
        result = hub_and_spoke(
            slide, bbox, centre="Platform", spokes=[f"Spoke {i}" for i in range(n)]
        )
        hub = _circle(result.hub)
        spokes = [_circle(s) for s in result.spokes]
        for spoke in spokes:
            assert _distance(spoke, hub) >= hub[2] + spoke[2]
        for a, b in itertools.combinations(spokes, 2):
            assert _distance(a, b) >= a[2] + b[2]
        for shape in [result.hub, *result.spokes]:
            assert _inside_bbox(shape, bbox)

    @pytest.mark.parametrize("bbox", _ROOMY_BBOXES)
    @pytest.mark.parametrize("n", range(1, 9))
    def it_lints_clean_for_a_realistic_number_of_spokes(self, slide, bbox, n):
        hub_and_spoke(slide, bbox, centre="Platform", spokes=[f"Spoke {i}" for i in range(n)])
        assert _lint_problems(slide) == []

    def it_leaves_the_arrows_room_to_show(self, slide):
        bbox = BBox.from_inches(0.5, 1.5, 9.0, 5.5)
        result = hub_and_spoke(slide, bbox, centre="Platform", spokes=list("ABCDEF"))
        hub = _circle(result.hub)
        for spoke in map(_circle, result.spokes):
            assert _distance(spoke, hub) - hub[2] - spoke[2] >= int(Inches(0.3))

    def it_keeps_the_default_node_sizes_when_they_fit(self, slide):
        bbox = BBox.from_inches(0.5, 1.5, 9.0, 5.5)
        short = int(bbox.height)
        result = hub_and_spoke(slide, bbox, centre="Core", spokes=list("ABCDEF"))
        assert int(result.spokes[0].width) == int(short * 0.2)
        assert int(result.hub.width) == int(short * 0.25 * 1.4)

    def it_shrinks_hub_and_spokes_together_when_the_ring_is_crowded(self, slide):
        bbox = BBox.from_inches(0.5, 1.5, 9.0, 5.5)
        short = int(bbox.height)
        result = hub_and_spoke(slide, bbox, centre="Core", spokes=[f"S{i}" for i in range(12)])
        assert int(result.spokes[0].width) < int(short * 0.2)
        ratio = int(result.hub.width) / int(result.spokes[0].width)
        assert abs(ratio - (0.25 * 1.4) / 0.2) < 0.01

    def it_honours_the_size_factors_it_is_given(self, slide):
        bbox = BBox.from_inches(0.5, 1.5, 9.0, 5.5)
        result = hub_and_spoke(
            slide, bbox, centre="Core", spokes=list("ABC"), hub_size=1.0, spoke_size=1.5
        )
        assert int(result.hub.width) < int(result.spokes[0].width)
        hub = _circle(result.hub)
        for spoke in map(_circle, result.spokes):
            assert _distance(spoke, hub) >= hub[2] + spoke[2]

    def it_declares_the_arrow_overlaps_pair_by_pair(self, slide):
        # Arrows touch the hub and their own spoke; a blanket group would hide any
        # other overlap too.
        bbox = BBox.from_inches(0.5, 1.5, 9.0, 5.5)
        result = hub_and_spoke(slide, bbox, centre="Core", spokes=list("ABCD"))
        assert {s.lint_group for s in slide.shapes} == {None}
        for arrow, spoke in zip(result.arrows, result.spokes):
            assert arrow.overlap_allowances == {result.hub.shape_id, spoke.shape_id}

    def it_still_flags_a_spoke_dragged_onto_the_hub(self, slide):
        bbox = BBox.from_inches(0.5, 1.5, 9.0, 5.5)
        result = hub_and_spoke(slide, bbox, centre="Core", spokes=list("ABCD"))
        spoke, hub = result.spokes[0], result.hub
        # Half over the hub's edge: a partial overlap, not a small shape wholly on a
        # larger one (which the linter takes for a badge on a card and lets through).
        spoke.left = int(hub.left) + int(hub.width) - int(spoke.width) // 2
        spoke.top = int(hub.top) + (int(hub.height) - int(spoke.height)) // 2
        assert any("ShapeCollision" in p for p in _lint_problems(slide))


class DescribeCycleGeometry:
    @pytest.mark.parametrize("bbox", _RING_BBOXES)
    @pytest.mark.parametrize("n", range(2, 17))
    def it_keeps_the_cards_apart_for_any_step_count(self, slide, bbox, n):
        result = cycle(slide, bbox, steps=[f"Step {i}" for i in range(n)])
        cards = [_circle(c) for c in result.cards]
        for a, b in itertools.combinations(cards, 2):
            assert _distance(a, b) >= a[2] + b[2]
        for shape in result.cards:
            assert _inside_bbox(shape, bbox)

    @pytest.mark.parametrize("bbox", _ROOMY_BBOXES)
    @pytest.mark.parametrize("n", range(2, 13))
    def it_lints_clean_for_up_to_twelve_steps(self, slide, bbox, n):
        cycle(slide, bbox, steps=[f"Step {i}" for i in range(n)])
        assert _lint_problems(slide) == []

    def it_keeps_the_default_card_size_for_a_handful_of_steps(self, slide):
        bbox = BBox.from_inches(0.5, 1.5, 9.0, 5.5)
        result = cycle(slide, bbox, steps=["Observe", "Orient", "Decide", "Act"])
        assert int(result.cards[0].width) == int(int(bbox.height) * 0.22)

    def it_shrinks_the_cards_when_the_ring_is_crowded(self, slide):
        bbox = BBox.from_inches(0.5, 1.5, 9.0, 5.5)
        result = cycle(slide, bbox, steps=[f"Step {i}" for i in range(12)])
        assert int(result.cards[0].width) < int(int(bbox.height) * 0.22)

    def it_leaves_the_arrows_room_to_show(self, slide):
        bbox = BBox.from_inches(0.5, 1.5, 9.0, 5.5)
        result = cycle(slide, bbox, steps=[f"Step {i}" for i in range(12)])
        cards = [_circle(c) for c in result.cards]
        for a, b in zip(cards, cards[1:] + cards[:1]):
            assert _distance(a, b) - a[2] - b[2] >= int(Inches(0.15))

    def it_declares_the_arrow_overlaps_pair_by_pair(self, slide):
        bbox = BBox.from_inches(0.5, 1.5, 9.0, 5.5)
        result = cycle(slide, bbox, steps=["A", "B", "C", "D"])
        assert {s.lint_group for s in slide.shapes} == {None}
        n = len(result.cards)
        for i, arrow in enumerate(result.arrows):
            ends = {result.cards[i].shape_id, result.cards[(i + 1) % n].shape_id}
            assert ends <= arrow.overlap_allowances

    def it_still_flags_two_cards_dragged_together(self, slide):
        bbox = BBox.from_inches(0.5, 1.5, 9.0, 5.5)
        result = cycle(slide, bbox, steps=["A", "B", "C", "D"])
        result.cards[2].left = int(result.cards[0].left) + int(Inches(0.2))
        result.cards[2].top = int(result.cards[0].top) + int(Inches(0.2))
        assert any("ShapeCollision" in p for p in _lint_problems(slide))

    def it_no_longer_promises_a_fallback_circle_it_never_drew(self):
        assert "small circle" not in cycle.__doc__


class DescribeRingDiagramSchemaValidity:
    def it_validates_and_round_trips_hub_and_spoke_and_cycle_at_many_sizes(self):
        import io

        from tests.integration.round_trip import assert_round_trip
        from tests.schema.oxml_schema_validator import (
            iter_schema_violations,
            schema_validation_available,
        )

        if not schema_validation_available():
            pytest.skip("schema validation unavailable")
        prs = Presentation()
        for n in (1, 3, 8, 12):
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            hub_and_spoke(
                slide,
                BBox.from_inches(0.5, 1.0, 9, 6),
                centre="Platform",
                spokes=[f"Spoke {i}" for i in range(n)],
            )
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            cycle(slide, BBox.from_inches(0.5, 1.0, 9, 6), steps=[f"Step {i}" for i in range(n)])
        buf = io.BytesIO()
        prs.save(buf)
        assert list(iter_schema_violations(buf.getvalue())) == []
        assert_round_trip(prs)


class DescribeCircularLabelFit:
    """Labels are fitted to the text area an ellipse really has: its inscribed rectangle."""

    @staticmethod
    def _best_size(label, diameter, *, bold, max_pt):
        from power_pptx.text.fonts import find_font_file
        from power_pptx.text.layout import TextFitter
        from power_pptx.util import Emu

        # An ellipse's text rectangle is 0.7071 of its box a side (the "il/it/ir/ib"
        # guides of the preset), and the text frame's own insets come off that.
        inscribed = diameter * math.cos(math.pi / 4)
        text_w = inscribed - 2 * (diameter * 0.14)
        text_h = inscribed - 2 * (diameter * 0.08)
        slack = 2000  # EMU: the recipe works in whole EMU, this in floats
        return TextFitter.best_fit_font_size(
            label,
            (Emu(int(text_w) + slack), Emu(int(text_h) + slack)),
            max_pt,
            find_font_file("Calibri", bold, False),
        )

    @pytest.mark.parametrize("n", [6, 12])
    def it_fits_cycle_labels_to_the_inscribed_area(self, slide, n):
        bbox = BBox.from_inches(0.5, 1.5, 9.0, 5.5)
        result = cycle(slide, bbox, steps=[f"Step {i}" for i in range(n)])
        for i, card in enumerate(result.cards):
            size = card.text_frame.paragraphs[0].runs[0].font.size.pt
            best = self._best_size(f"Step {i}", int(card.width), bold=False, max_pt=14)
            assert best is not None
            assert size <= best, (i, size, best)

    def it_fits_hub_and_spoke_labels_to_the_inscribed_area(self, slide):
        bbox = BBox.from_inches(0.5, 1.5, 9.0, 5.5)
        result = hub_and_spoke(slide, bbox, centre="Platform", spokes=[f"S{i}" for i in range(12)])
        hub_size = result.hub.text_frame.paragraphs[0].runs[0].font.size.pt
        assert hub_size <= self._best_size("Platform", int(result.hub.width), bold=True, max_pt=14)
        for i, spoke in enumerate(result.spokes):
            size = spoke.text_frame.paragraphs[0].runs[0].font.size.pt
            assert size <= self._best_size(f"S{i}", int(spoke.width), bold=False, max_pt=12)

    def it_leaves_the_render_insets_in_place_once_fitted(self, slide):
        bbox = BBox.from_inches(0.5, 1.5, 9.0, 5.5)
        result = cycle(slide, bbox, steps=["Observe", "Orient", "Decide", "Act"])
        card = result.cards[0]
        diameter = int(card.width)
        assert int(card.text_frame.margin_left) == int(diameter * 0.14)
        assert int(card.text_frame.margin_right) == int(diameter * 0.14)
        assert int(card.text_frame.margin_top) == int(diameter * 0.08)
        assert int(card.text_frame.margin_bottom) == int(diameter * 0.08)
