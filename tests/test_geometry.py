"""Unit tests for :mod:`power_pptx.geometry`."""

from __future__ import annotations

import pytest

from power_pptx import BBox, Presentation
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.util import Emu, Inches, Pt


@pytest.fixture
def slide():
    prs = Presentation()
    return prs.slides.add_slide(prs.slide_layouts[6])


class DescribeBBox:
    def it_constructs_from_inches(self):
        bb = BBox.from_inches(1, 2, 4, 3)
        assert bb.left == Inches(1)
        assert bb.top == Inches(2)
        assert bb.width == Inches(4)
        assert bb.height == Inches(3)

    def it_constructs_from_emu(self):
        bb = BBox.from_emu(100, 200, 300, 400)
        assert (bb.left, bb.top, bb.width, bb.height) == (100, 200, 300, 400)

    def it_unpacks_to_l_t_w_h(self):
        bb = BBox.from_inches(1, 2, 4, 3)
        l, t, w, h = bb
        assert l == bb.left
        assert t == bb.top
        assert w == bb.width
        assert h == bb.height

    def it_exposes_right_and_bottom(self):
        bb = BBox.from_inches(1, 2, 4, 3)
        assert bb.right == Inches(5)
        assert bb.bottom == Inches(5)

    def it_exposes_centres(self):
        bb = BBox.from_inches(0, 0, 4, 4)
        assert bb.cx == Inches(2)
        assert bb.cy == Inches(2)

    def it_insets_uniformly(self):
        bb = BBox.from_inches(0, 0, 10, 10)
        inner = bb.inset(all=Inches(1))
        assert (inner.left, inner.top, inner.width, inner.height) == (
            Inches(1), Inches(1), Inches(8), Inches(8),
        )

    def it_insets_per_edge(self):
        bb = BBox.from_inches(0, 0, 10, 10)
        inner = bb.inset(left=Inches(1), top=Inches(2), right=Inches(3), bottom=Inches(4))
        assert inner.left == Inches(1)
        assert inner.top == Inches(2)
        # width = 10 - 1 - 3 = 6, height = 10 - 2 - 4 = 4
        assert int(inner.width) == int(Inches(6))
        assert int(inner.height) == int(Inches(4))

    def it_splits_horizontally(self):
        bb = BBox.from_inches(0, 0, 6, 2)
        cols = bb.split_h([1, 1, 1])
        assert len(cols) == 3
        assert int(cols[0].width) == int(Inches(2))
        assert int(cols[1].left) == int(Inches(2))
        assert int(cols[2].left) == int(Inches(4))

    def it_splits_with_gap(self):
        bb = BBox.from_inches(0, 0, 6, 2)
        cols = bb.split_h([1, 1], gap=Inches(0.5))
        # remaining = 6 - 0.5 = 5.5 -> each col 2.75
        assert int(cols[0].width) == int(Inches(2.75))
        assert int(cols[1].left) == int(Inches(3.25))

    def it_splits_vertically(self):
        bb = BBox.from_inches(0, 0, 4, 6)
        rows = bb.split_v([1, 2])
        # total ratio 3 -> 2" + 4"
        assert int(rows[0].height) == int(Inches(2))
        assert int(rows[1].height) == int(Inches(4))

    def it_grids(self):
        bb = BBox.from_inches(0, 0, 6, 4)
        cells = bb.grid(3, 2)
        assert len(cells) == 6

    def it_detects_intersections(self):
        a = BBox.from_inches(0, 0, 4, 4)
        b = BBox.from_inches(2, 2, 4, 4)
        c = BBox.from_inches(10, 10, 1, 1)
        assert a.intersects(b)
        assert not a.intersects(c)
        inter = a.intersection(b)
        assert int(inter.width) == int(Inches(2))

    def it_unions(self):
        a = BBox.from_inches(0, 0, 4, 4)
        b = BBox.from_inches(2, 2, 4, 4)
        u = a.union(b)
        assert u.left == 0
        assert u.right == Inches(6)

    def it_contains(self):
        outer = BBox.from_inches(0, 0, 10, 10)
        inner = BBox.from_inches(1, 1, 2, 2)
        assert outer.contains(inner)
        assert not inner.contains(outer)

    def it_rejects_negative_dimensions(self):
        with pytest.raises(ValueError):
            BBox.from_inches(0, 0, -1, 1)

    def it_applies_to_shape(self, slide):
        rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(1), Inches(1))
        bb = BBox.from_inches(2, 3, 4, 5)
        bb.apply_to(rect)
        assert rect.left == Inches(2)
        assert rect.width == Inches(4)

    def it_constructs_from_shape(self, slide):
        rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(2), Inches(3), Inches(4))
        bb = BBox.from_shape(rect)
        assert bb.left == Inches(1)
        assert bb.right == Inches(4)
        assert bb.bottom == Inches(6)

    def it_constructs_from_slide(self, slide):
        bb = BBox.from_slide(slide)
        assert bb.left == 0
        assert bb.width == Inches(10)
        assert bb.height == Inches(7.5)


class DescribeShapeBboxProperty:
    def it_returns_a_bbox(self, slide):
        rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(2), Inches(3), Inches(4))
        assert isinstance(rect.bbox, BBox)
        assert rect.bbox.left == Inches(1)


class DescribeSplitPreservesSpan:
    def it_splits_h_into_segments_summing_to_full_width(self):
        # The naive `int(round(span * r / total))` approach would drift
        # by ±1 EMU on uneven ratios with high segment counts.
        bb = BBox.from_inches(0, 0, 7, 1)
        cols = bb.split_h([1, 1, 1, 1, 1, 1, 1])
        assert sum(int(c.width) for c in cols) == int(bb.width)
        # Each consecutive box also starts exactly where the previous ends.
        for prev, curr in zip(cols, cols[1:]):
            assert int(prev.right) == int(curr.left)

    def it_splits_v_into_segments_summing_to_full_height(self):
        bb = BBox.from_inches(0, 0, 1, 7)
        rows = bb.split_v([2, 3, 5])
        assert sum(int(r.height) for r in rows) == int(bb.height)

    def it_splits_with_gap_preserving_total_layout_span(self):
        bb = BBox.from_inches(0, 0, 10, 1)
        gap = int(Pt(7))   # awkward odd number to stress rounding
        cols = bb.split_h([1, 1, 1], gap=gap)
        total = sum(int(c.width) for c in cols) + gap * (len(cols) - 1)
        assert total == int(bb.width)


class DescribeIntersectsTouching:
    def it_does_not_treat_edge_touching_as_intersection(self):
        # The docstring promises touching edges do NOT intersect.
        a = BBox.from_inches(0, 0, 2, 2)
        b = BBox.from_inches(2, 0, 2, 2)   # shares right/left edge
        assert not a.intersects(b)
        c = BBox.from_inches(0, 2, 2, 2)   # shares top/bottom edge
        assert not a.intersects(c)
        d = BBox.from_inches(2, 2, 2, 2)   # corner touch
        assert not a.intersects(d)
