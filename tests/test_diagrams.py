"""Unit tests for :mod:`power_pptx.diagrams`."""

from __future__ import annotations

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


@pytest.fixture
def slide():
    prs = Presentation()
    return prs.slides.add_slide(prs.slide_layouts[6])


class DescribeHorizontalPipeline:
    def it_creates_one_card_per_step(self, slide):
        result = horizontal_pipeline(
            slide, BBox.from_inches(0, 0, 8, 1.5),
            steps=["A", "B", "C", "D"],
        )
        assert len(result.cards) == 4

    def it_creates_n_minus_one_arrows(self, slide):
        result = horizontal_pipeline(
            slide, BBox.from_inches(0, 0, 8, 1.5),
            steps=["A", "B", "C"],
        )
        assert len(result.arrows) == 2

    def it_accepts_dict_steps_with_per_step_colors(self, slide):
        result = horizontal_pipeline(
            slide, BBox.from_inches(0, 0, 8, 1.5),
            steps=[{"label": "A", "fill": "#FF0000"}, {"label": "B"}],
        )
        assert len(result.cards) == 2

    def it_raises_on_empty_steps(self, slide):
        with pytest.raises(ValueError):
            horizontal_pipeline(slide, BBox.from_inches(0, 0, 8, 1.5), steps=[])


class DescribeVerticalPipeline:
    def it_stacks_cards_vertically(self, slide):
        result = vertical_pipeline(
            slide, BBox.from_inches(0, 0, 4, 6),
            steps=["A", "B", "C"],
        )
        assert len(result.cards) == 3
        # Each subsequent card lives below the previous one
        assert int(result.cards[1].top) > int(result.cards[0].top)


class DescribeHubAndSpoke:
    def it_creates_hub_plus_n_spokes(self, slide):
        result = hub_and_spoke(
            slide, BBox.from_inches(0, 0, 8, 6),
            centre="Core",
            spokes=["A", "B", "C", "D"],
        )
        assert result.hub is not None
        assert len(result.spokes) == 4
        assert len(result.arrows) == 4


class DescribeCycle:
    def it_creates_a_loop_with_n_arrows(self, slide):
        result = cycle(
            slide, BBox.from_inches(0, 0, 8, 6),
            steps=["Observe", "Orient", "Decide", "Act"],
        )
        assert len(result.cards) == 4
        # Arrows count equals card count (cycle wraps around)
        assert len(result.arrows) == 4


class DescribeDecisionTree:
    def it_creates_a_root_plus_branches(self, slide):
        result = decision_tree(
            slide, BBox.from_inches(0, 0, 8, 6),
            root="Q?",
            branches=["Yes", "No"],
        )
        assert result.root is not None
        # Two branch cards, two arrows from root
        assert len(result.branches) == 2

    def it_supports_one_level_of_children(self, slide):
        result = decision_tree(
            slide, BBox.from_inches(0, 0, 8, 6),
            root="Q?",
            branches=[
                {"label": "Yes", "children": ["a", "b"]},
                {"label": "No", "children": ["c"]},
            ],
        )
        # 2 branches + 3 children
        assert len(result.branches) == 5


class DescribeComparisonColumns:
    def it_creates_header_and_body_per_column(self, slide):
        result = comparison_columns(
            slide, BBox.from_inches(0, 0, 8, 4),
            columns=[
                {"title": "X", "body": "a"},
                {"title": "Y", "body": ["a", "b"]},
            ],
        )
        assert len(result.headers) == 2
        assert len(result.columns) == 2
