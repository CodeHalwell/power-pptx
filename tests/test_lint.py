"""Unit-test suite for `power_pptx.lint` — covers the lint-group feature."""

from __future__ import annotations

import io

import pytest

from power_pptx import Presentation
from power_pptx.lint import ShapeCollision, _LINT_GROUP_ATTR
from power_pptx.util import Inches


def _new_blank_slide():
    prs = Presentation()
    # Layout 6 is "Blank" in the default template.
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    return prs, slide


def _add_overlapping_rects(slide, n=3):
    """Add `n` axis-aligned rectangles, each overlapping its neighbour by ~50%."""
    shapes = []
    for i in range(n):
        s = slide.shapes.add_shape(
            1,  # MSO_SHAPE.RECTANGLE
            Inches(1 + 0.5 * i),
            Inches(1 + 0.5 * i),
            Inches(2),
            Inches(2),
        )
        shapes.append(s)
    return shapes


def _collisions(slide):
    return [i for i in slide.lint().issues if isinstance(i, ShapeCollision)]


class DescribeShapeLintGroup:
    """Per-shape ``lint_group`` property."""

    def it_defaults_to_None(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        assert s.lint_group is None

    def it_round_trips_a_string_value(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.lint_group = "kpi-card-1"
        assert s.lint_group == "kpi-card-1"

    def it_persists_through_save_and_load(self):
        prs, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.lint_group = "kpi-card-1"
        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        prs2 = Presentation(buf)
        s2 = list(prs2.slides[0].shapes)[0]
        assert s2.lint_group == "kpi-card-1"

    def it_clears_when_set_to_None(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.lint_group = "kpi-card-1"
        s.lint_group = None
        assert s.lint_group is None
        cNvPr = s._element._nvXxPr.cNvPr
        assert _LINT_GROUP_ATTR not in cNvPr.attrib

    def it_rejects_an_empty_string(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        with pytest.raises(ValueError):
            s.lint_group = ""


class DescribeSlideLintGroupBatch:
    """``slide.lint_group(name, *shapes)`` batch tagger."""

    def it_tags_all_supplied_shapes(self):
        _, slide = _new_blank_slide()
        a, b, c = _add_overlapping_rects(slide, 3)
        slide.lint_group("kpi-card-1", a, b, c)
        assert (a.lint_group, b.lint_group, c.lint_group) == (
            "kpi-card-1",
            "kpi-card-1",
            "kpi-card-1",
        )

    def it_clears_all_supplied_shapes_when_name_is_None(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        slide.lint_group("kpi", a, b)
        slide.lint_group(None, a, b)
        assert a.lint_group is None and b.lint_group is None

    def it_accepts_zero_shapes_as_a_no_op(self):
        _, slide = _new_blank_slide()
        slide.lint_group("kpi-card-1")  # must not raise


class DescribeSlideDesignGroup:
    """``slide.design_group(name)`` context manager."""

    def it_auto_tags_shapes_added_in_the_block(self):
        _, slide = _new_blank_slide()
        with slide.design_group("kpi-card-1"):
            a = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(1), Inches(1))
            b = slide.shapes.add_shape(1, Inches(0), Inches(1), Inches(1), Inches(1))
        assert (a.lint_group, b.lint_group) == ("kpi-card-1", "kpi-card-1")

    def it_does_not_tag_shapes_added_outside_the_block(self):
        _, slide = _new_blank_slide()
        outside = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(1), Inches(1))
        with slide.design_group("kpi-card-1"):
            inside = slide.shapes.add_shape(1, Inches(0), Inches(1), Inches(1), Inches(1))
        after = slide.shapes.add_shape(1, Inches(0), Inches(2), Inches(1), Inches(1))
        assert outside.lint_group is None
        assert inside.lint_group == "kpi-card-1"
        assert after.lint_group is None

    def it_uses_the_innermost_label_when_nested(self):
        _, slide = _new_blank_slide()
        with slide.design_group("outer"):
            a = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(1), Inches(1))
            with slide.design_group("inner"):
                b = slide.shapes.add_shape(1, Inches(1), Inches(0), Inches(1), Inches(1))
            c = slide.shapes.add_shape(1, Inches(2), Inches(0), Inches(1), Inches(1))
        assert (a.lint_group, b.lint_group, c.lint_group) == ("outer", "inner", "outer")

    def it_does_not_overwrite_an_explicit_pre_set_group(self):
        _, slide = _new_blank_slide()
        with slide.design_group("auto"):
            a = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(1), Inches(1))
            a.lint_group = "manual"
        assert a.lint_group == "manual"

    def it_rejects_an_empty_or_None_name(self):
        _, slide = _new_blank_slide()
        with pytest.raises(ValueError):
            with slide.design_group(""):
                pass
        with pytest.raises(ValueError):
            with slide.design_group(None):  # type: ignore[arg-type]
                pass


class DescribeCollisionGroupSuppression:
    """``ShapeCollision`` lint check honors ``lint_group``."""

    def it_suppresses_collisions_inside_a_single_group(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        # baseline: a vs b collides
        assert len(_collisions(slide)) == 1
        slide.lint_group("kpi-card-1", a, b)
        assert _collisions(slide) == []

    def it_still_warns_across_different_groups(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        slide.lint_group("card-A", a)
        slide.lint_group("card-B", b)
        assert len(_collisions(slide)) == 1

    def it_still_warns_when_only_one_shape_is_grouped(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        slide.lint_group("card-A", a)
        # b is left untagged
        assert len(_collisions(slide)) == 1

    def it_suppresses_only_the_intra_group_pair(self):
        _, slide = _new_blank_slide()
        a, b, c = _add_overlapping_rects(slide, 3)
        # All three currently collide pairwise (3 collisions).
        assert len(_collisions(slide)) == 3
        # Tag a+b together; c stays untagged.
        slide.lint_group("kpi-card-1", a, b)
        # Only a/c and b/c remain.
        remaining = _collisions(slide)
        assert len(remaining) == 2
        pairs = {tuple(sorted((i.shapes[0].name, i.shapes[1].name))) for i in remaining}
        assert pairs == {
            tuple(sorted((a.name, c.name))),
            tuple(sorted((b.name, c.name))),
        }

    def it_works_end_to_end_with_design_group(self):
        _, slide = _new_blank_slide()
        with slide.design_group("kpi-card-1"):
            slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
            slide.shapes.add_shape(1, Inches(1.5), Inches(1.5), Inches(2), Inches(2))
        assert _collisions(slide) == []
