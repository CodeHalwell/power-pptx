"""Unit tests for :mod:`power_pptx.diagrams`."""

from __future__ import annotations

import pytest

from power_pptx import BBox, Presentation
from power_pptx.util import Pt
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

    def it_fits_long_labels_inside_the_node(self, slide):
        # A label longer than the circle can show at the requested size must
        # be shrunk by the fit_text pre-flight rather than wrapped/clipped.
        result = cycle(
            slide, BBox.from_inches(3, 2, 4, 2.5),
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
            slide, BBox.from_inches(3, 1.5, 5, 4),
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

    def it_inherits_fill_and_text_color_on_leaf_nodes(self, slide):
        # Regression: leaf (child) nodes used to hardcode a light fill,
        # producing invisible light-on-light text on dark decks.  They must
        # now inherit ``fill`` / ``text_color`` from the recipe.
        from power_pptx._color import coerce_color

        result = decision_tree(
            slide, BBox.from_inches(0, 0, 11, 5),
            root="Request",
            branches=[{"label": "Cache miss", "children": ["Compute", "Store"]}],
            fill="#141A23", text_color="#E6EDF3",
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
            slide, BBox.from_inches(0, 0, 11, 5),
            root="Request",
            branches=[{"label": "Branch", "children": ["Leaf"]}],
            fill="#141A23", text_color="#E6EDF3",
            leaf_fill="#222C3A", leaf_text_color="#FFD166",
        )
        leaf = next(b for b in result.branches if b.text_frame.text == "Leaf")
        assert leaf.fill.fore_color.rgb == coerce_color("#222C3A")
        assert leaf.text_frame.paragraphs[0].runs[0].font.color.rgb == coerce_color("#FFD166")


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
