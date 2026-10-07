"""Integration tests for ``anchor=`` on add_picture / add_shape / add_textbox.

The anchor keyword places the new shape relative to a container (the
slide by default, or a parent shape). It collapses the
``add → measure → reposition`` pattern that authors otherwise repeat
on every corner-anchored element (logos, watermarks, page numbers).
"""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.shapes.shapetree import (
    _compute_anchor_left_top,
    _resolve_anchor,
)
from power_pptx.util import Inches


def _slide():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    return prs, slide


class DescribeResolveAnchor:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("top-left", ("top", "left")),
            ("top-center", ("top", "center")),
            ("top-centre", ("top", "center")),
            ("top-right", ("top", "right")),
            ("middle-left", ("middle", "left")),
            ("middle-center", ("middle", "center")),
            ("middle-right", ("middle", "right")),
            ("bottom-left", ("bottom", "left")),
            ("bottom-center", ("bottom", "center")),
            ("bottom-right", ("bottom", "right")),
            ("center", ("middle", "center")),
            ("centre", ("middle", "center")),
            ("CENTER", ("middle", "center")),
            ("center-left", ("middle", "left")),  # tolerant synonym
        ],
    )
    def it_parses_valid_anchor_strings(self, raw, expected):
        assert _resolve_anchor(raw) == expected

    @pytest.mark.parametrize("bad", ["", "weird", "left-top", "top", "north-west"])
    def it_rejects_invalid_anchor_strings(self, bad):
        with pytest.raises(ValueError):
            _resolve_anchor(bad)


class DescribeComputeAnchorLeftTop:
    def it_places_top_left(self):
        # Slide 10x7.5", shape 1x0.5", margin 0.25" → top-left.
        left, top = _compute_anchor_left_top(
            "top-left",
            container_w=int(Inches(10)),
            container_h=int(Inches(7.5)),
            shape_w=int(Inches(1)),
            shape_h=int(Inches(0.5)),
            margin=int(Inches(0.25)),
        )
        assert left == int(Inches(0.25))
        assert top == int(Inches(0.25))

    def it_places_bottom_right(self):
        left, top = _compute_anchor_left_top(
            "bottom-right",
            container_w=int(Inches(10)),
            container_h=int(Inches(7.5)),
            shape_w=int(Inches(1)),
            shape_h=int(Inches(0.5)),
            margin=int(Inches(0.25)),
        )
        # Slide is 10" wide; shape 1"; right margin 0.25" → left = 8.75".
        assert left == int(Inches(10)) - int(Inches(0.25)) - int(Inches(1))
        assert top == int(Inches(7.5)) - int(Inches(0.25)) - int(Inches(0.5))

    def it_centres_on_both_axes(self):
        left, top = _compute_anchor_left_top(
            "center",
            container_w=int(Inches(10)),
            container_h=int(Inches(8)),
            shape_w=int(Inches(2)),
            shape_h=int(Inches(2)),
        )
        assert left == int(Inches(4))
        assert top == int(Inches(3))


class DescribeAnchorOnAddShape:
    def it_repositions_to_bottom_right_after_creation(self):
        prs, slide = _slide()
        prs.slide_width = Inches(10)
        prs.slide_height = Inches(7.5)
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(0),
            Inches(0),
            Inches(2),
            Inches(1),
            anchor="bottom-right",
            margin=Inches(0.25),
        )
        # Bottom-right with 0.25" margin in a 10x7.5" slide for a 2x1" shape:
        assert int(shape.left) == int(Inches(10) - Inches(0.25) - Inches(2))
        assert int(shape.top) == int(Inches(7.5) - Inches(0.25) - Inches(1))

    def it_centres_a_shape_inside_a_parent_shape_container(self):
        # A common pattern: drop a label into the centre of a card.
        # Shapes added via slide.shapes.add_* always live in the
        # slide's spTree (slide-relative coordinates); the anchor
        # helper must add the container's left/top so the new shape
        # is *visually* inside the parent shape.
        prs, slide = _slide()
        card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(1),
            Inches(1),
            Inches(4),
            Inches(2),
        )
        label = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(0),
            Inches(0),
            Inches(1),
            Inches(0.4),
            anchor="center",
            container=card,
        )
        # Label sits in the card's centre, slide-relative.
        expected_left = int(card.left) + (int(card.width) - int(Inches(1))) // 2
        expected_top = int(card.top) + (int(card.height) - int(Inches(0.4))) // 2
        assert int(label.left) == expected_left
        assert int(label.top) == expected_top

    def it_treats_a_synthetic_size_only_container_as_origin_zero(self):
        # When the container exposes only width/height (no left/top),
        # we keep the previous "container origin = (0, 0)" behaviour
        # so callers can still compute anchor positions against a
        # virtual size without contriving fake left/top.
        prs, slide = _slide()

        class _BoxLike:
            width = Inches(4)
            height = Inches(2)

        label = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(0),
            Inches(0),
            Inches(1),
            Inches(0.4),
            anchor="center",
            container=_BoxLike(),
        )
        assert int(label.left) == (int(Inches(4)) - int(Inches(1))) // 2
        assert int(label.top) == (int(Inches(2)) - int(Inches(0.4))) // 2

    def it_leaves_position_alone_when_anchor_is_none(self):
        prs, slide = _slide()
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(2),
            Inches(3),
            Inches(1),
            Inches(1),
        )
        assert int(shape.left) == int(Inches(2))
        assert int(shape.top) == int(Inches(3))

    def it_rejects_unknown_anchor_strings(self):
        prs, slide = _slide()
        with pytest.raises(ValueError):
            slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE,
                Inches(0),
                Inches(0),
                Inches(1),
                Inches(1),
                anchor="south-west",
            )


class DescribeAnchorOnAddTextbox:
    def it_anchors_a_textbox_to_top_center_of_the_slide(self):
        prs, slide = _slide()
        prs.slide_width = Inches(10)
        prs.slide_height = Inches(7.5)
        tb = slide.shapes.add_textbox(
            Inches(0),
            Inches(0),
            Inches(2),
            Inches(0.5),
            anchor="top-center",
            margin=Inches(0.5),
        )
        assert int(tb.left) == (int(Inches(10)) - int(Inches(2))) // 2
        # margin only applies on top axis, not the centred horizontal.
        assert int(tb.top) == int(Inches(0.5))


class DescribeLintGroupScope:
    def it_tags_every_shape_added_inside_with_block(self):
        prs, slide = _slide()
        with slide.shapes.lint_group_scope("progress_bar") as g:
            track = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(1),
                Inches(1),
                Inches(4),
                Inches(0.3),
            )
            fill = g.add_shape(  # using yielded handle works too
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(1),
                Inches(1),
                Inches(2),
                Inches(0.3),
            )
        assert track.lint_group == "progress_bar"
        assert fill.lint_group == "progress_bar"

    def it_does_not_retag_shapes_added_before_the_block(self):
        prs, slide = _slide()
        prior = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(0),
            Inches(0),
            Inches(1),
            Inches(1),
        )
        with slide.shapes.lint_group_scope("group-x"):
            new_shape = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE,
                Inches(2),
                Inches(2),
                Inches(1),
                Inches(1),
            )
        assert prior.lint_group is None
        assert new_shape.lint_group == "group-x"

    def it_auto_generates_a_unique_name_when_not_supplied(self):
        prs, slide = _slide()
        with slide.shapes.lint_group_scope():
            s1 = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE,
                Inches(0),
                Inches(0),
                Inches(1),
                Inches(1),
            )
            s2 = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE,
                Inches(2),
                Inches(0),
                Inches(1),
                Inches(1),
            )
        assert s1.lint_group == s2.lint_group
        assert s1.lint_group.startswith("design-group-")

    def it_auto_increments_when_a_design_group_already_exists(self):
        prs, slide = _slide()
        with slide.shapes.lint_group_scope():
            slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE,
                Inches(0),
                Inches(0),
                Inches(1),
                Inches(1),
            )
        with slide.shapes.lint_group_scope():
            second = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE,
                Inches(2),
                Inches(0),
                Inches(1),
                Inches(1),
            )
        # The second auto-named scope must pick a fresh number.
        assert second.lint_group == "design-group-2"

    def it_still_tags_when_the_block_raises(self):
        # Better to tag than leave shapes flagged as real overlaps in
        # the lint report.
        prs, slide = _slide()
        with pytest.raises(RuntimeError):
            with slide.shapes.lint_group_scope("g"):
                shape = slide.shapes.add_shape(
                    MSO_SHAPE.RECTANGLE,
                    Inches(0),
                    Inches(0),
                    Inches(1),
                    Inches(1),
                )
                raise RuntimeError("boom")
        assert shape.lint_group == "g"


class DescribeAnchorOnAddPicture:
    def it_anchors_a_picture_to_bottom_right_of_the_slide(self):
        prs, slide = _slide()
        prs.slide_width = Inches(10)
        prs.slide_height = Inches(7.5)
        pic = slide.shapes.add_picture(
            "tests/test_files/python-powered.png",
            Inches(0),
            Inches(0),
            height=Inches(0.5),
            anchor="bottom-right",
            margin=Inches(0.25),
        )
        # Picture's rendered width depends on aspect ratio; whatever it
        # is, the right edge must sit at slide_w - margin.
        assert int(pic.left + pic.width) == int(Inches(10) - Inches(0.25))
        assert int(pic.top + pic.height) == int(Inches(7.5) - Inches(0.25))
