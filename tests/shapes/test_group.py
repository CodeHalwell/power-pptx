"""Test suite for power_pptx.shapes.group module."""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx.dml.color import RGBColor
from power_pptx.dml.effect import ShadowFormat
from power_pptx.enum.dml import MSO_FILL
from power_pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
from power_pptx.shapes.group import GroupShape
from power_pptx.shapes.shapetree import GroupShapes
from power_pptx.util import Emu, Inches, Pt

from ..unitutil.cxml import element
from ..unitutil.mock import class_mock, initializer_mock, instance_mock


class DescribeGroupShape(object):
    def it_raises_on_access_click_action(self, click_action_fixture):
        group = click_action_fixture
        with pytest.raises(TypeError):
            group.click_action

    def it_provides_access_to_its_shadow(self, ShadowFormat_, shadow_):
        grpSp = element("p:grpSp/p:grpSpPr")
        grpSpPr = grpSp.xpath("//p:grpSpPr")[0]
        ShadowFormat_.return_value = shadow_
        group_shape = GroupShape(grpSp, None)

        shadow = group_shape.shadow

        ShadowFormat_.assert_called_once_with(grpSpPr)
        assert shadow is shadow_

    def it_knows_its_shape_type(self, shape_type_fixture):
        group = shape_type_fixture
        assert group.shape_type == MSO_SHAPE_TYPE.GROUP

    def it_provides_access_to_its_sub_shapes(self, shapes_fixture):
        group, GroupShapes_init_, grpSp = shapes_fixture

        shapes = group.shapes

        GroupShapes_init_.assert_called_once_with(shapes, grpSp, group)
        assert isinstance(shapes, GroupShapes)

    # fixtures -------------------------------------------------------

    @pytest.fixture
    def click_action_fixture(self):
        return GroupShape(None, None)

    @pytest.fixture
    def shape_type_fixture(self):
        return GroupShape(None, None)

    @pytest.fixture
    def shapes_fixture(self, GroupShapes_init_):
        grpSp = element("p:grpSp")
        group = GroupShape(grpSp, None)
        return group, GroupShapes_init_, grpSp

    # fixture components ---------------------------------------------

    @pytest.fixture
    def GroupShapes_init_(self, request):
        return initializer_mock(request, GroupShapes, autospec=True)

    @pytest.fixture
    def shadow_(self, request):
        return instance_mock(request, ShadowFormat)

    @pytest.fixture
    def ShadowFormat_(self, request):
        return class_mock(request, "power_pptx.shapes.group.ShadowFormat")


class DescribeGroupShapeSurface(object):
    """Behavioral tests for the group ergonomics (fill, move, walk, ungroup).

    These exercise real shape trees built through the public API rather than
    isolated cxml fixtures, because the behavior depends on child geometry and
    re-parenting.
    """

    def it_provides_access_to_its_fill(self, group):
        group.fill.solid()
        group.fill.fore_color.rgb = RGBColor(0x1F, 0x4E, 0x79)

        assert group.fill.type == MSO_FILL.SOLID
        assert group.fill.fore_color.rgb == RGBColor(0x1F, 0x4E, 0x79)

    def it_moves_the_whole_group_by_an_offset(self, group):
        left, top = int(group.left), int(group.top)

        result = group.move(Inches(0.5), Inches(-0.25))

        assert result is group
        assert int(group.left) == left + Inches(0.5)
        assert int(group.top) == top - Inches(0.25)

    def it_walks_descendant_shapes_recursively(self, group):
        nested = group.shapes.add_group_shape()
        nested.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(4), Inches(3), Inches(1), Inches(1))

        walked = list(group.walk())

        # two leaf rects from `group`, the nested group, and its one leaf rect
        assert len(walked) == 4
        groups = [s for s in walked if s.shape_type == MSO_SHAPE_TYPE.GROUP]
        leaves = [s for s in walked if s.shape_type != MSO_SHAPE_TYPE.GROUP]
        assert len(groups) == 1
        assert len(leaves) == 3

    def it_fits_its_extent_to_its_children(self, group):
        # Perturb the group's stored offset/extent so it no longer matches its
        # members, then prove fit_to_children() shrink-wraps back to them.
        grpSp = group._element  # noqa: SLF001
        grpSp.x = Emu(int(grpSp.x) + Inches(2))
        grpSp.cx = Emu(int(grpSp.cx) + Inches(3))

        group.fit_to_children()

        # children span 1in..5in horizontally and 1in..3in vertically
        assert int(group.left) == Inches(1)
        assert int(group.top) == Inches(1)
        assert int(group.width) == Inches(4)
        assert int(group.height) == Inches(2)

    def it_moves_durably_across_recalculation(self, group):
        # A move must survive a later recalculate_extents() (triggered here by
        # adding a shape) — it shifts the members + chOff, not just `off`.
        first = list(group.shapes)[0]
        left0 = int(first.left)

        group.move(Inches(2), 0)
        group.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6), Inches(1), Inches(1), Inches(1))

        assert int(list(group.shapes)[0].left) == left0 + Inches(2)

    def it_exposes_inner_and_preset_shadow_over_grpSpPr(self, group):
        # BaseShape routes these through spPr; a group has grpSpPr, so without
        # the override they'd raise AttributeError (PR #39 review).
        from power_pptx.dml.effect import InnerShadowFormat, PresetShadowFormat

        assert isinstance(group.inner_shadow, InnerShadowFormat)
        assert isinstance(group.preset_shadow, PresetShadowFormat)
        group.inner_shadow.blur_radius = Pt(3)
        group.preset_shadow.preset = "shdw5"
        assert int(group.inner_shadow.blur_radius) == Pt(3)
        assert group.preset_shadow.preset is not None

    def it_raises_NotImplementedError_for_three_d(self, group):
        # `p:grpSpPr` legally holds `a:scene3d` but not `a:sp3d`, so routing
        # the ThreeDFormat facade at it would emit schema-invalid XML; the
        # inherited spPr-based accessor raised a bare AttributeError instead.
        with pytest.raises(NotImplementedError):
            group.three_d

    def it_ungroups_preserving_child_geometry(self, slide, group):
        before = [(int(s.left), int(s.top), int(s.width), int(s.height)) for s in group.shapes]

        promoted = group.ungroup()

        after = [(int(s.left), int(s.top), int(s.width), int(s.height)) for s in promoted]
        assert after == before
        # group is gone; its two rects are now direct slide shapes
        assert all(s.shape_type != MSO_SHAPE_TYPE.GROUP for s in slide.shapes)
        assert len(list(slide.shapes)) == 2

    def it_ungroups_a_scaled_group_correctly(self, slide, group):
        group.fit_to_children()
        grpSp = group._element  # noqa: SLF001
        grpSp.cx = Emu(int(grpSp.cx) * 2)
        grpSp.cy = Emu(int(grpSp.cy) * 2)
        off_x, off_y = int(group.left), int(group.top)
        ch_x, ch_y = int(grpSp.chOff.x), int(grpSp.chOff.y)

        promoted = group.ungroup()

        first = promoted[0]
        assert int(first.left) == off_x + (Inches(1) - ch_x) * 2
        assert int(first.top) == off_y + (Inches(1) - ch_y) * 2
        assert int(first.width) == Inches(2) * 2
        assert int(first.height) == Inches(1) * 2

    def it_raises_when_ungrouping_a_rotated_group(self, group):
        group.rotation = 30.0

        with pytest.raises(ValueError, match="rotated or flipped"):
            group.ungroup()

    @pytest.mark.parametrize("flip", ["flipH", "flipV"])
    def it_raises_when_ungrouping_a_flipped_group(self, group, flip):
        group._element.grpSpPr.xfrm.set(flip, "1")  # noqa: SLF001

        with pytest.raises(ValueError, match="rotated or flipped"):
            group.ungroup()

    def it_raises_when_ungrouping_a_group_outside_any_shape_tree(self, group):
        grpSp = group._element  # noqa: SLF001
        grpSp.getparent().remove(grpSp)

        with pytest.raises(ValueError, match="not in a shape tree"):
            group.ungroup()

    def it_ungroups_a_nested_group_into_the_group_holding_it(self, slide):
        outer = slide.shapes.add_group_shape()
        outer.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(1), Inches(1))
        inner = outer.shapes.add_group_shape()
        inner.shapes.add_shape(MSO_SHAPE.OVAL, Inches(2), Inches(2), Inches(1), Inches(1))
        inner.shapes.add_shape(MSO_SHAPE.OVAL, Inches(4), Inches(3), Inches(2), Inches(1))
        outer.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(7), Inches(5), Inches(1), Inches(1))

        promoted = inner.ungroup()

        members = list(outer.shapes)
        assert [s.name for s in members] == [
            "Rectangle 2",
            "Oval 4",
            "Oval 5",
            "Rectangle 6",
        ]
        assert [s.shape_id for s in promoted] == [5, 6]
        assert [(int(s.left), int(s.top), int(s.width), int(s.height)) for s in promoted] == [
            (Inches(2), Inches(2), Inches(1), Inches(1)),
            (Inches(4), Inches(3), Inches(2), Inches(1)),
        ]

    def it_ungroups_an_empty_group_by_removing_it(self, slide):
        group = slide.shapes.add_group_shape()

        assert group.ungroup() == []
        assert len(slide.shapes) == 0

    def it_ungroups_without_scaling_when_the_child_extent_is_zero(self, slide, group):
        grpSp = group._element  # noqa: SLF001
        grpSp.chOff.x, grpSp.chOff.y = Emu(Inches(1)), Emu(Inches(1))
        grpSp.chExt.cx, grpSp.chExt.cy = Emu(0), Emu(0)
        grpSp.x, grpSp.y = Emu(Inches(3)), Emu(Inches(2))
        grpSp.cx, grpSp.cy = Emu(Inches(8)), Emu(Inches(8))

        promoted = group.ungroup()

        # -- children at (1, 1) and (4, 2) in child space; scale 1 when chExt is 0 --
        assert [(int(s.left), int(s.top), int(s.width), int(s.height)) for s in promoted] == [
            (Inches(3), Inches(2), Inches(2), Inches(1)),
            (Inches(6), Inches(3), Inches(1), Inches(1)),
        ]

    def it_purges_the_animations_of_a_group_it_ungroups(self, slide, group):
        # The group's id disappears with it, so an effect that targeted the
        # group would be left pointing at a shape that no longer exists.
        from power_pptx.animation import Entrance

        member = list(group.shapes)[0]
        Entrance.fade(slide, group)
        Entrance.fade(slide, member)
        group_id = group.shape_id

        group.ungroup()

        targets = {int(spid) for spid in slide._element.xpath("p:timing//p:spTgt/@spid")}
        live = {int(i) for i in slide._element.xpath("p:cSld/p:spTree//p:cNvPr/@id")}
        assert group_id not in live
        # -- the effect on the member shape, which is still there, is kept --
        assert targets == {member.shape_id}
        assert [entry.shape_id for entry in slide.animations] == [member.shape_id]

    def it_drops_the_timing_tree_when_ungrouping_removes_its_only_animation(self, slide, group):
        from power_pptx.animation import Entrance

        Entrance.fade(slide, group)

        group.ungroup()

        assert slide._element.xpath("p:timing") == []

    def it_can_add_a_table_to_the_group(self, slide):
        group = slide.shapes.add_group_shape()

        gf = group.shapes.add_table(2, 3, Inches(1), Inches(1), Inches(4), Inches(1.5))

        assert gf.has_table
        assert gf.shape_type == MSO_SHAPE_TYPE.TABLE
        # the group's extent grows to bound the new table
        assert int(group.width) == Inches(4)
        assert int(group.height) == Inches(1.5)
        assert list(group.shapes)[0].shape_type == MSO_SHAPE_TYPE.TABLE

    def it_can_add_a_movie_to_the_group(self, slide):
        from ..unitutil.file import absjoin, test_file_dir

        group = slide.shapes.add_group_shape()

        movie = group.shapes.add_movie(
            absjoin(test_file_dir, "dummy.mp4"),
            Inches(1),
            Inches(1),
            Inches(4),
            Inches(3),
            poster_frame_image=absjoin(test_file_dir, "monty-truth.png"),
            mime_type="video/mp4",
        )

        assert movie.shape_type == MSO_SHAPE_TYPE.MEDIA
        # video play-controls timing is registered on the enclosing slide
        assert slide._element.xpath(".//p:timing//p:video")

    # fixtures -------------------------------------------------------

    @pytest.fixture
    def slide(self):
        prs = Presentation()
        return prs.slides.add_slide(prs.slide_layouts[6])

    @pytest.fixture
    def group(self, slide):
        grp = slide.shapes.add_group_shape()
        grp.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1))
        grp.shapes.add_shape(MSO_SHAPE.OVAL, Inches(4), Inches(2), Inches(1), Inches(1))
        return grp
