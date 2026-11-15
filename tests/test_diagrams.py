"""Unit tests for :mod:`power_pptx.diagrams`."""

from __future__ import annotations

import math
import os

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
from power_pptx.text import clear_registered_fonts, measure_text, register_font_dir
from power_pptx.util import Emu, Inches, Pt


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
# Review fixes: circular label fit, node spacing, capacity errors, tree routing
# ---------------------------------------------------------------------------

_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")


@pytest.fixture
def outfit():
    """A font shipped with the tests, so label measurements are exact."""
    register_font_dir(_FONTS_DIR)
    yield "Outfit"
    clear_registered_fonts()


def _fits_inscribed_square(node, font, bold=False):
    """True when *node*'s label, at its baked size, fits the circle's text area.

    The `ellipse` preset lays text out in the rectangle inscribed in the
    ellipse (0.7071 x the diameter for a circle), less the frame's insets.
    """
    tf = node.text_frame
    side = int(node.width * math.sqrt(0.5))
    width = side - tf.margin_left - tf.margin_right
    height = side - tf.margin_top - tf.margin_bottom
    size = tf.paragraphs[0].runs[0].font.size
    try:
        measured = measure_text(
            tf.text,
            Emu(width),
            size_pt=int(size.pt),
            font_family=font,
            bold=bold,
            line_spacing=1.0,
        )
    except ValueError:  # a word is wider than the text area: it would be split
        return False
    return measured.height <= height


class DescribeCircularLabelFit:
    """Labels in circular nodes are fitted to the inscribed square, whole words only."""

    def it_fits_hub_and_spoke_labels_without_breaking_words(self, slide, outfit):
        result = hub_and_spoke(
            slide,
            BBox.from_inches(7, 1, 6, 5.5),
            centre="Platform",
            spokes=["Retrieval", "Ranking", "Serving", "Monitoring"],
            font=outfit,
        )

        # used to render "Platfor/m", "Retri/eval", "Ranki/ng", "Monito/ring"
        assert _fits_inscribed_square(result.hub, outfit, bold=True)
        for spoke in result.spokes:
            assert _fits_inscribed_square(spoke, outfit), spoke.text_frame.text

    def it_fits_cycle_labels_without_breaking_words(self, slide, outfit):
        result = cycle(
            slide,
            BBox.from_inches(0.5, 1, 6, 5.5),
            ["Plan", "Build", "Measure", "Learn"],
            font=outfit,
        )

        for card in result.cards:  # "Measure" used to render "Meas/ure"
            assert _fits_inscribed_square(card, outfit), card.text_frame.text

    def it_keeps_the_requested_size_when_the_label_fits(self, slide, outfit):
        result = cycle(
            slide, BBox.from_inches(0.5, 1, 6, 5.5), ["Plan", "Do"], font=outfit, size_pt=14
        )

        sizes = {c.text_frame.paragraphs[0].runs[0].font.size for c in result.cards}
        assert sizes == {Pt(14)}

    def it_uses_small_insets_rather_than_a_share_of_the_diameter(self, slide, outfit):
        result = cycle(slide, BBox.from_inches(0, 0, 8, 6), ["Plan", "Do", "Check"], font=outfit)

        card = result.cards[0]
        tf = card.text_frame
        # 14% + 14% insets on top of the inscribed square left 43% of the diameter
        assert tf.margin_left + tf.margin_right <= card.width * 0.05

    def it_raises_when_a_label_cannot_fit_at_the_minimum_size(self, slide, outfit):
        before = slide._element.xml

        message = r"cycle \(4 steps\): the label 'Internationalisation'"
        with pytest.raises(ValueError, match=message):
            cycle(
                slide,
                BBox.from_inches(0, 0, 3, 2),
                ["Plan", "Internationalisation", "Check", "Act"],
                font=outfit,
            )
        assert slide._element.xml == before  # nothing half-built is left behind

    def it_raises_for_a_hub_label_that_cannot_fit(self, slide, outfit):
        before = slide._element.xml

        with pytest.raises(ValueError, match="hub_and_spoke hub: the label"):
            hub_and_spoke(
                slide,
                BBox.from_inches(0, 0, 2, 2),
                centre="Internationalisation",
                spokes=["A", "B"],
                font=outfit,
            )
        assert slide._element.xml == before

    def it_lets_the_caller_lower_the_minimum(self, slide, outfit):
        result = cycle(
            slide,
            BBox.from_inches(0, 0, 3, 2),
            ["Plan", "Internationalisation", "Check", "Act"],
            font=outfit,
            min_size_pt=1,
        )

        size = result.cards[1].text_frame.paragraphs[0].runs[0].font.size
        assert Pt(1) <= size < Pt(6)


def _overlapping_pairs(nodes):
    count = 0
    for i, first in enumerate(nodes):
        for second in nodes[i + 1 :]:
            distance = math.hypot(
                first.left + first.width / 2 - second.left - second.width / 2,
                first.top + first.height / 2 - second.top - second.height / 2,
            )
            if distance < (first.width + second.width) / 2:
                count += 1
    return count


class DescribeCycleSpacing:
    @pytest.mark.parametrize("count", [11, 12, 16, 20])
    def it_shrinks_the_nodes_so_neighbours_do_not_overlap(self, slide, count):
        region = BBox.from_inches(1, 1, 11, 5.5)

        result = cycle(slide, region, [str(i) for i in range(count)])

        # a fixed diameter made every node overlap its neighbours from 11 steps
        assert _overlapping_pairs(result.cards) == 0
        for card in result.cards:
            assert card.left >= region.left
            assert card.top >= region.top
            assert card.left + card.width <= region.right
            assert card.top + card.height <= region.bottom

    @pytest.mark.parametrize("count", [1, 2, 3, 4, 8])
    def it_keeps_the_usual_diameter_up_to_eight_steps(self, slide, count):
        result = cycle(slide, BBox.from_inches(1, 1, 11, 5.5), [str(i) for i in range(count)])

        assert {card.width for card in result.cards} == {int(Inches(5.5) * 0.22)}

    def it_rejects_more_steps_than_can_carry_a_label(self, slide):
        before = slide._element.xml

        with pytest.raises(ValueError, match=r"cycle \(40 steps\)"):
            cycle(slide, BBox.from_inches(1, 1, 11, 5.5), [f"Step {i}" for i in range(40)])
        assert slide._element.xml == before


class DescribePipelineCapacity:
    """A card that cannot hold its label raises; the failed fit is no longer swallowed."""

    def it_rejects_a_vertical_pipeline_with_too_many_steps(self, slide):
        before = slide._element.xml

        # 20 steps used to yield 0.117in-tall cards still carrying 14pt labels
        with pytest.raises(ValueError, match=r"vertical_pipeline \(20 steps\): the label 'Step 0'"):
            vertical_pipeline(
                slide, BBox.from_inches(1, 1, 11, 5.5), [f"Step {i}" for i in range(20)]
            )
        assert slide._element.xml == before

    def it_rejects_a_horizontal_pipeline_with_too_many_steps(self, slide):
        before = slide._element.xml

        # 60 steps used to yield 0.019in-wide cards
        with pytest.raises(ValueError, match=r"horizontal_pipeline \(60 steps\)"):
            horizontal_pipeline(
                slide, BBox.from_inches(1, 1, 11, 5.5), [f"Step {i}" for i in range(60)]
            )
        assert slide._element.xml == before

    def it_rejects_a_bbox_with_no_room_for_a_card_even_without_labels(self, slide):
        before = slide._element.xml

        with pytest.raises(ValueError, match="leaves no room for this card"):
            horizontal_pipeline(slide, BBox(Inches(1), Inches(1), Inches(5), Emu(0)), ["", ""])
        assert slide._element.xml == before

    def it_shrinks_labels_that_can_still_fit(self, slide, outfit):
        result = horizontal_pipeline(
            slide, BBox.from_inches(1, 1, 11, 2), ["Classification"] * 8, font=outfit
        )

        sizes = {c.text_frame.paragraphs[0].runs[0].font.size for c in result.cards}
        assert len(sizes) == 1
        assert Pt(6) <= sizes.pop() < Pt(14)

    def it_lets_the_caller_lower_the_minimum(self, slide, outfit):
        steps = [f"Step {i}" for i in range(14)]
        region = BBox.from_inches(1, 1, 6, 5.5)

        with pytest.raises(ValueError):
            vertical_pipeline(slide, region, steps, font=outfit)
        result = vertical_pipeline(slide, region, steps, font=outfit, min_size_pt=1)

        assert len(result.cards) == 14


def _overlaps(first, second, tolerance=2):
    return (
        first[0] < second[2] - tolerance
        and second[0] < first[2] - tolerance
        and first[1] < second[3] - tolerance
        and second[1] < first[3] - tolerance
    )


class DescribeDecisionTreeRouting:
    def it_routes_child_arrows_clear_of_every_child_card(self, slide):
        result = decision_tree(
            slide,
            BBox.from_inches(1, 1, 11, 5.5),
            root="Is it urgent?",
            branches=[
                {"label": "Yes", "children": ["Page on-call", "Open incident", "Notify exec"]},
                {"label": "No", "children": ["Backlog", "Triage weekly", "Close"]},
            ],
        )

        leaves = [
            (b.left, b.top, b.left + b.width, b.top + b.height)
            for b in result.branches
            if b.text_frame.text not in ("Yes", "No")
        ]
        assert len(leaves) == 6
        for arrow in result.arrows:
            segment = (
                min(arrow.begin_x, arrow.end_x),
                min(arrow.begin_y, arrow.end_y),
                max(arrow.begin_x, arrow.end_x),
                max(arrow.begin_y, arrow.end_y),
            )
            # a zero-thickness line still "overlaps" a card it passes through
            segment = (segment[0] - 1, segment[1] - 1, segment[2] + 1, segment[3] + 1)
            # each branch-to-child arrow used to run straight down through
            # the children above its own
            assert not [leaf for leaf in leaves if _overlaps(segment, leaf)]

    def it_links_each_child_with_a_rail_and_a_short_arrow(self, slide):
        result = decision_tree(
            slide,
            BBox.from_inches(1, 1, 11, 5.5),
            root="Q?",
            branches=[{"label": "Yes", "children": ["a", "b", "c"]}, "No"],
        )

        # per branch: root arrow, then (with children) a rail and one arrow each
        assert len(result.arrows) == (1 + 1 + 3) + 1
        branch, children = result.branches[0], result.branches[1:4]
        rail, stubs = result.arrows[1], result.arrows[2:5]
        assert rail.begin_x == rail.end_x < children[0].left
        assert rail.begin_y == branch.top + branch.height
        for stub, child in zip(stubs, children):
            assert stub.begin_x == rail.begin_x
            assert stub.begin_y == stub.end_y == child.top + child.height // 2
            assert stub.end_x <= child.left

    def it_rejects_children_that_cannot_hold_their_labels(self, slide):
        before = slide._element.xml

        with pytest.raises(ValueError, match=r"decision_tree \(30 children\)"):
            decision_tree(
                slide,
                BBox.from_inches(1, 1, 11, 5.5),
                root="Q?",
                branches=[{"label": "B", "children": [f"leaf {j}" for j in range(30)]}],
            )
        assert slide._element.xml == before


class DescribeDecisionTreeInputs:
    def it_rejects_an_empty_branch_list(self, slide):
        before = slide._element.xml

        with pytest.raises(ValueError, match="branches must be non-empty"):
            decision_tree(slide, BBox.from_inches(1, 1, 8, 5), root="Q?", branches=[])
        assert slide._element.xml == before

    def it_rejects_a_branch_that_is_neither_text_nor_a_dict(self, slide):
        before = slide._element.xml

        with pytest.raises(TypeError, match="branches items must be str or dict; got int"):
            decision_tree(slide, BBox.from_inches(1, 1, 8, 5), root="Q?", branches=["Yes", 5])
        # the root card was already on the slide; it is removed again
        assert slide._element.xml == before

    def it_reads_child_labels_from_text_or_a_dict(self, slide):
        result = decision_tree(
            slide,
            BBox.from_inches(1, 1, 11, 5.5),
            root="Q?",
            branches=[{"label": "B", "children": ["text", {"label": "dict"}, {"other": 1}]}],
        )

        assert [b.text_frame.text for b in result.branches] == ["B", "text", "dict", ""]

    def it_gives_a_childless_branch_its_whole_column(self, slide):
        result = decision_tree(
            slide,
            BBox.from_inches(1, 1, 11, 5.5),
            root="Q?",
            branches=[{"label": "A"}, {"label": "B", "children": ["c"]}],
        )

        a, b = result.branches[:2]
        assert a.top == b.top
        assert a.height > b.height
        # A: root arrow only; B: root arrow, rail, one child arrow
        assert len(result.arrows) == 1 + 3


class DescribeHubAndSpokeStyling:
    def it_styles_the_hub_and_each_spoke(self, slide, outfit):
        from power_pptx._color import coerce_color
        from power_pptx.enum.text import MSO_VERTICAL_ANCHOR, PP_PARAGRAPH_ALIGNMENT

        result = hub_and_spoke(
            slide,
            BBox.from_inches(0, 0, 8, 6),
            centre="Core",
            spokes=["A", {"label": "B", "fill": "#EEEEEE", "text_color": "#112233"}],
            font=outfit,
            accent="#0B5CFF",
            fill="#FFFFFF",
            text_color="#0D0D0D",
            hub_text_color="#FAFAFA",
        )

        hub_run = result.hub.text_frame.paragraphs[0].runs[0]
        assert result.hub.fill.fore_color.rgb == coerce_color("#0B5CFF")
        assert (hub_run.font.name, hub_run.font.bold) == ("Outfit", True)
        assert hub_run.font.color.rgb == coerce_color("#FAFAFA")
        a, b = result.spokes
        assert [s.fill.fore_color.rgb for s in (a, b)] == [
            coerce_color("#FFFFFF"),
            coerce_color("#EEEEEE"),
        ]
        assert [s.line.color.rgb for s in (a, b)] == [coerce_color("#0B5CFF")] * 2
        runs = [s.text_frame.paragraphs[0].runs[0] for s in (a, b)]
        assert [r.font.color.rgb for r in runs] == [
            coerce_color("#0D0D0D"),
            coerce_color("#112233"),
        ]
        assert {r.font.name for r in runs} == {"Outfit"}
        for node in (result.hub, a, b):
            assert node.text_frame.vertical_anchor == MSO_VERTICAL_ANCHOR.MIDDLE
            assert node.text_frame.paragraphs[0].alignment == PP_PARAGRAPH_ALIGNMENT.CENTER

    def it_points_each_arrow_from_the_hub_edge_to_the_spoke_edge(self, slide):
        result = hub_and_spoke(
            slide, BBox.from_inches(0, 0, 8, 6), centre="Core", spokes=["A", "B", "C"]
        )

        hub = result.hub
        hub_r = hub.width / 2
        hub_c = (hub.left + hub_r, hub.top + hub_r)
        for spoke, arrow in zip(result.spokes, result.arrows):
            spoke_r = spoke.width / 2
            spoke_c = (spoke.left + spoke_r, spoke.top + spoke_r)
            begin, end = (arrow.begin_x, arrow.begin_y), (arrow.end_x, arrow.end_y)
            assert hub_r < math.dist(begin, hub_c) < hub_r + Pt(3)
            assert spoke_r < math.dist(end, spoke_c) < spoke_r + Pt(3)


class DescribeComparisonColumnsInputs:
    def it_rejects_an_empty_column_list(self, slide):
        with pytest.raises(ValueError, match="columns must be non-empty"):
            comparison_columns(slide, BBox.from_inches(0, 0, 8, 4), columns=[])

    def it_takes_a_bare_string_as_a_title_over_an_empty_body(self, slide):
        result = comparison_columns(
            slide,
            BBox.from_inches(0, 0, 8, 4),
            columns=["Only a title", {"title": "T", "body": ["a", "b"]}, {"body": "c"}],
        )

        assert [h.text_frame.text for h in result.headers] == ["Only a title", "T", ""]
        assert [c.text_frame.text for c in result.columns] == ["", "a\nb", "c"]

    @pytest.mark.parametrize(("gap", "expected"), [(None, Pt(12)), (int(Inches(1)), Inches(1))])
    def it_spaces_the_columns_by_the_gap(self, slide, gap, expected):
        result = comparison_columns(
            slide, BBox.from_inches(0, 0, 8, 4), columns=["a", "b"], gap=gap
        )

        first, second = result.headers
        assert second.left - (first.left + first.width) == pytest.approx(expected, abs=2)

    def it_names_the_body_font_when_one_is_given(self, slide, outfit):
        result = comparison_columns(
            slide,
            BBox.from_inches(0, 0, 8, 4),
            columns=[{"title": "T", "body": "text"}],
            font=outfit,
        )

        assert result.columns[0].text_frame.paragraphs[0].runs[0].font.name == "Outfit"

    def it_keeps_the_body_size_when_the_fit_fails(self, slide, monkeypatch):
        from power_pptx.text.text import TextFrame

        def fail(self, *args, **kwargs):
            raise ValueError("cannot fit")

        monkeypatch.setattr(TextFrame, "fit_text", fail)

        result = comparison_columns(
            slide,
            BBox.from_inches(0, 0, 8, 4),
            columns=[{"title": "T", "body": "text"}],
            body_size_pt=12,
        )

        assert result.columns[0].text_frame.paragraphs[0].runs[0].font.size == Pt(12)


class DescribeDiagramDeckRoundTrip:
    def _deck(self):
        prs = Presentation()
        region = BBox.from_inches(0.5, 0.5, 9, 6.5)
        for build in (
            lambda s: cycle(s, region, [f"Step {i}" for i in range(12)]),
            lambda s: hub_and_spoke(s, region, centre="Platform", spokes=["A", "B", "C"]),
            lambda s: decision_tree(
                s, region, root="Q?", branches=[{"label": "Yes", "children": ["a", "b"]}, "No"]
            ),
        ):
            build(prs.slides.add_slide(prs.slide_layouts[6]))
        return prs

    def it_round_trips_and_validates(self):
        import io

        from power_pptx.validation import iter_schema_violations
        from tests.integration.round_trip import assert_round_trip

        assert_round_trip(self._deck)
        buf = io.BytesIO()
        self._deck().save(buf)
        assert list(iter_schema_violations(buf.getvalue())) == []
