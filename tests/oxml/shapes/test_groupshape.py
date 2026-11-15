"""Unit-test suite for `power_pptx.oxml.shapes.groupshape` module."""

from __future__ import annotations

import pytest

from power_pptx.oxml.shapes.autoshape import CT_Shape
from power_pptx.oxml.shapes.graphfrm import CT_GraphicalObjectFrame
from power_pptx.oxml.shapes.groupshape import CT_GroupShape
from power_pptx.oxml.shapes.picture import CT_Picture

from ...unitutil.cxml import element, xml
from ...unitutil.mock import call, class_mock, instance_mock, method_mock, property_mock


class DescribeCT_GroupShape(object):
    """Unit-test suite for `power_pptx.oxml.shapes.groupshape.CT_GroupShape` objects."""

    def it_can_add_a_graphicFrame_element_containing_a_table(self, add_table_fixt):
        spTree, id_, name, rows, cols, x, y, cx, cy = add_table_fixt[:9]
        new_table_graphicFrame_ = add_table_fixt[9]
        insert_element_before_, graphicFrame_ = add_table_fixt[10:]

        graphicFrame = spTree.add_table(id_, name, rows, cols, x, y, cx, cy)

        new_table_graphicFrame_.assert_called_once_with(id_, name, rows, cols, x, y, cx, cy)
        insert_element_before_.assert_called_once_with(spTree, graphicFrame_, "p:extLst")
        assert graphicFrame is graphicFrame_

    def it_can_add_a_grpSp_element(self, add_grpSp_fixture):
        spTree, expected_grpSp_xml, expected_xml = add_grpSp_fixture

        grpSp = spTree.add_grpSp()

        assert grpSp.xml == expected_grpSp_xml
        assert spTree.xml == expected_xml

    def it_can_add_a_pic_element_representing_a_picture(self, add_pic_fixt):
        spTree, id_, name, desc, rId, x, y, cx, cy = add_pic_fixt[:9]
        CT_Picture_, insert_element_before_, pic_ = add_pic_fixt[9:]

        pic = spTree.add_pic(id_, name, desc, rId, x, y, cx, cy)

        CT_Picture_.new_pic.assert_called_once_with(id_, name, desc, rId, x, y, cx, cy)
        insert_element_before_.assert_called_once_with(spTree, pic_, "p:extLst")
        assert pic is pic_

    def it_can_add_an_sp_element_for_a_placeholder(self, add_placeholder_fixt):
        spTree, id_, name, ph_type, orient, sz, idx = add_placeholder_fixt[:7]
        CT_Shape_, insert_element_before_, sp_ = add_placeholder_fixt[7:]

        sp = spTree.add_placeholder(id_, name, ph_type, orient, sz, idx)

        CT_Shape_.new_placeholder_sp.assert_called_once_with(id_, name, ph_type, orient, sz, idx)
        insert_element_before_.assert_called_once_with(spTree, sp_, "p:extLst")
        assert sp is sp_

    def it_can_add_an_sp_element_for_an_autoshape(self, add_autoshape_fixt):
        spTree, id_, name, prst, x, y, cx, cy = add_autoshape_fixt[:8]
        CT_Shape_, insert_element_before_, sp_ = add_autoshape_fixt[8:]

        sp = spTree.add_autoshape(id_, name, prst, x, y, cx, cy)

        CT_Shape_.new_autoshape_sp.assert_called_once_with(id_, name, prst, x, y, cx, cy)
        insert_element_before_.assert_called_once_with(spTree, sp_, "p:extLst")
        assert sp is sp_

    def it_can_add_a_textbox_sp_element(self, add_textbox_fixt):
        spTree, id_, name, x, y, cx, cy, CT_Shape_ = add_textbox_fixt[:8]
        insert_element_before_, sp_ = add_textbox_fixt[8:]

        sp = spTree.add_textbox(id_, name, x, y, cx, cy)

        CT_Shape_.new_textbox_sp.assert_called_once_with(id_, name, x, y, cx, cy)
        insert_element_before_.assert_called_once_with(spTree, sp_, "p:extLst")
        assert sp is sp_

    def it_can_recalculate_its_pos_and_size(self, recalc_fixture):
        xSp, expected_xml, parent_sp, calls = recalc_fixture

        xSp.recalculate_extents()

        assert xSp.xml == expected_xml
        assert parent_sp.recalculate_extents.call_args_list == calls

    def it_calculates_its_child_extents_to_help(self, child_exts_fixture):
        xSp, expected_values = child_exts_fixture
        x, y, cx, cy = xSp._child_extents
        assert (x, y, cx, cy) == expected_values

    # fixtures ---------------------------------------------

    @pytest.fixture
    def add_autoshape_fixt(self, spTree, CT_Shape_, insert_element_before_, sp_):
        id_, name, prst = 42, "name", "prst"
        x, y, cx, cy = 9, 8, 7, 6
        return (
            spTree,
            id_,
            name,
            prst,
            x,
            y,
            cx,
            cy,
            CT_Shape_,
            insert_element_before_,
            sp_,
        )

    @pytest.fixture
    def add_grpSp_fixture(self):
        spTree = element("p:spTree{a:b=c,r:s=t}")
        expected_grpSp_xml = (
            # ---can't get the namespaces right with cxml, using full text--
            '<p:grpSp xmlns:p="http://schemas.openxmlformats.org/presentatio'
            'nml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawi'
            'ngml/2006/main" xmlns:r="http://schemas.openxmlformats.org/offi'
            'ceDocument/2006/relationships">\n  <p:nvGrpSpPr>\n    <p:cNvPr '
            'id="1" name="Group 0"/>\n    <p:cNvGrpSpPr/>\n    <p:nvPr/>\n  '
            '</p:nvGrpSpPr>\n  <p:grpSpPr>\n    <a:xfrm>\n      <a:off x="0"'
            ' y="0"/>\n      <a:ext cx="0" cy="0"/>\n      <a:chOff x="0" y='
            '"0"/>\n      <a:chExt cx="0" cy="0"/>\n    </a:xfrm>\n  </p:grp'
            "SpPr>\n</p:grpSp>\n"
        )
        expected_xml = xml(
            "p:spTree{a:b=c,r:s=t}/p:grpSp/(p:nvGrpSpPr/(p:cNvPr{id=1,name=G"
            "roup 0},p:cNvGrpSpPr,p:nvPr),p:grpSpPr/a:xfrm/(a:off{x=0,y=0},a"
            ":ext{cx=0,cy=0},a:chOff{x=0,y=0},a:chExt{cx=0,cy=0}))"
        )
        return spTree, expected_grpSp_xml, expected_xml

    @pytest.fixture
    def add_pic_fixt(self, spTree, CT_Picture_, insert_element_before_, pic_):
        id_, name, desc, rId = 42, "name", "desc", "rId6"
        x, y, cx, cy = 6, 7, 8, 9
        return (
            spTree,
            id_,
            name,
            desc,
            rId,
            x,
            y,
            cx,
            cy,
            CT_Picture_,
            insert_element_before_,
            pic_,
        )

    @pytest.fixture
    def add_placeholder_fixt(self, spTree, CT_Shape_, insert_element_before_, sp_):
        id_, name, ph_type = 42, "name", "type"
        orient, sz, idx = "orient", "sz", 24
        return (
            spTree,
            id_,
            name,
            ph_type,
            orient,
            sz,
            idx,
            CT_Shape_,
            insert_element_before_,
            sp_,
        )

    @pytest.fixture
    def add_table_fixt(
        self, spTree, CT_GraphicalObjectFrame_, insert_element_before_, graphicFrame_
    ):
        id_, name, rows, cols = 42, "name", 12, 23
        x, y, cx, cy = 5, 4, 3, 2
        new_table_graphicFrame_ = CT_GraphicalObjectFrame_.new_table_graphicFrame
        return (
            spTree,
            id_,
            name,
            rows,
            cols,
            x,
            y,
            cx,
            cy,
            new_table_graphicFrame_,
            insert_element_before_,
            graphicFrame_,
        )

    @pytest.fixture
    def add_textbox_fixt(self, spTree, CT_Shape_, insert_element_before_, sp_):
        id_, name = 42, "name"
        x, y, cx, cy = 3, 4, 5, 6
        return (spTree, id_, name, x, y, cx, cy, CT_Shape_, insert_element_before_, sp_)

    @pytest.fixture(
        params=[
            ("p:grpSp", (0, 0, 0, 0)),
            (
                "p:grpSp/p:sp/p:spPr/a:xfrm/(a:off{x=1,y=2},a:ext{cx=3,cy=4})",
                (1, 2, 3, 4),
            ),
            (
                "p:grpSp/(p:sp/p:spPr/a:xfrm/(a:off{x=1,y=2},a:ext{cx=3,cy=4}),p:sp"
                "/p:spPr/a:xfrm/(a:off{x=10,y=20},a:ext{cx=30,cy=40}))",
                (1, 2, 39, 58),
            ),
            (
                "p:grpSp/(p:sp/p:spPr/a:xfrm/(a:off{x=100,y=50},a:ext{cx=25,cy=25})"
                ",p:sp/p:spPr/a:xfrm/(a:off{x=50,y=100},a:ext{cx=25,cy=25}),p:sp/p:"
                "spPr/a:xfrm/(a:off{x=150,y=75},a:ext{cx=25,cy=25}))",
                (50, 50, 125, 75),
            ),
        ]
    )
    def child_exts_fixture(self, request):
        xSp_cxml, expected_values = request.param
        xSp = element(xSp_cxml)
        return xSp, expected_values

    @pytest.fixture(
        params=[
            ("p:spTree", None, [], "p:spTree"),
            (
                "p:grpSp/p:grpSpPr/a:xfrm",
                (1, 2, 3, 4),
                [call()],
                "p:grpSp/p:grpSpPr/a:xfrm/(a:off{x=1,y=2},a:ext{cx=3,cy=4},a:chOff{"
                "x=1,y=2},a:chExt{cx=3,cy=4})",
            ),
        ]
    )
    def recalc_fixture(self, request, _child_extents_prop_, getparent_, grpSp_):
        xSp_cxml, extents, calls, expected_cxml = request.param
        xSp = element(xSp_cxml)

        _child_extents_prop_.return_value = extents
        expected_xml = xml(expected_cxml)
        getparent_.return_value = parent_sp = grpSp_
        return xSp, expected_xml, parent_sp, calls

    # fixture components -----------------------------------

    @pytest.fixture
    def _child_extents_prop_(self, request):
        return property_mock(request, CT_GroupShape, "_child_extents")

    @pytest.fixture
    def CT_GraphicalObjectFrame_(self, request, graphicFrame_):
        CT_GraphicalObjectFrame_ = class_mock(
            request, "power_pptx.oxml.shapes.groupshape.CT_GraphicalObjectFrame"
        )
        CT_GraphicalObjectFrame_.new_table_graphicFrame.return_value = graphicFrame_
        return CT_GraphicalObjectFrame_

    @pytest.fixture
    def CT_Picture_(self, request, pic_):
        CT_Picture_ = class_mock(request, "power_pptx.oxml.shapes.groupshape.CT_Picture")
        CT_Picture_.new_pic.return_value = pic_
        return CT_Picture_

    @pytest.fixture
    def CT_Shape_(self, request, sp_):
        CT_Shape_ = class_mock(request, "power_pptx.oxml.shapes.groupshape.CT_Shape")
        CT_Shape_.new_autoshape_sp.return_value = sp_
        CT_Shape_.new_placeholder_sp.return_value = sp_
        CT_Shape_.new_textbox_sp.return_value = sp_
        return CT_Shape_

    @pytest.fixture
    def getparent_(self, request):
        return method_mock(request, CT_GroupShape, "getparent")

    @pytest.fixture
    def graphicFrame_(self, request):
        return instance_mock(request, CT_GraphicalObjectFrame)

    @pytest.fixture
    def grpSp_(self, request):
        return instance_mock(request, CT_GroupShape)

    @pytest.fixture
    def insert_element_before_(self, request):
        return method_mock(request, CT_GroupShape, "insert_element_before")

    @pytest.fixture
    def pic_(self, request):
        return instance_mock(request, CT_Picture)

    @pytest.fixture
    def sp_(self, request):
        return instance_mock(request, CT_Shape)

    @pytest.fixture
    def spTree(self):
        return element("p:spTree")


# ---------------------------------------------------------------------------
# Shape-id allocation: the cached cursor must notice shapes added behind its back
# ---------------------------------------------------------------------------


def _slide_with_shapes(n=2):
    from power_pptx import Presentation
    from power_pptx.enum.shapes import MSO_SHAPE
    from power_pptx.util import Inches

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    for i in range(n):
        slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(i), Inches(1), Inches(1), Inches(1))
    return prs, slide


def _add_rect(shapes):
    from power_pptx.enum.shapes import MSO_SHAPE
    from power_pptx.util import Inches

    return shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(1), Inches(1))


def _all_ids(slide):
    return [int(v) for v in slide.shapes._spTree.xpath("//@id") if v.isdigit()]


def _foreign_shape(id_):
    """A shape element with id `id_` that did not come through the allocator."""
    return element(
        "p:sp/(p:nvSpPr/(p:cNvPr{id=%d,name=Copy},p:cNvSpPr,p:nvPr),"
        "p:spPr/a:xfrm/(a:off{x=0,y=0},a:ext{cx=914400,cy=914400}))" % id_
    )


class DescribeCT_GroupShapeIdAllocation:
    """`allocate_shape_id()` never hands out an id already used on the slide."""

    def it_notices_a_shape_appended_by_the_deepcopy_idiom(self):
        # Regression: the common copy idiom `spTree.append(deepcopy(elm))` after
        # any API add produced ids like [2, 3, 3].
        import copy

        prs, slide = _slide_with_shapes(1)
        other = prs.slides.add_slide(prs.slide_layouts[6])
        _add_rect(other.shapes)
        source = _add_rect(other.shapes)  # -- id 3 on the other slide

        slide.shapes._spTree.append(copy.deepcopy(source._element))
        added = _add_rect(slide.shapes)

        ids = [shape.shape_id for shape in slide.shapes]
        assert ids == [2, 3, 4]
        assert added.shape_id == 4

    @pytest.mark.parametrize("where", ["start", "after_grpSpPr", "end", "before_extLst"])
    def it_notices_a_shape_put_at_either_end_of_the_tree(self, where):
        prs, slide = _slide_with_shapes(3)
        spTree = slide.shapes._spTree
        stranger = _foreign_shape(500)
        if where == "end":
            spTree.append(stranger)
        elif where == "before_extLst":
            spTree.append(element("p:extLst"))
            spTree.insert_element_before(stranger, "p:extLst")
        else:
            spTree.insert(2, stranger)  # -- right after nvGrpSpPr and grpSpPr

        assert _add_rect(slide.shapes).shape_id == 501

    def it_notices_several_shapes_appended_at_once(self):
        prs, slide = _slide_with_shapes(2)
        spTree = slide.shapes._spTree
        for id_ in (40, 41, 90, 42):
            spTree.append(_foreign_shape(id_))

        assert _add_rect(slide.shapes).shape_id == 91

    def it_notices_more_new_shapes_than_it_follows_one_by_one(self):
        prs, slide = _slide_with_shapes(2)
        spTree = slide.shapes._spTree
        for id_ in range(100, 130):
            spTree.append(_foreign_shape(id_))

        assert _add_rect(slide.shapes).shape_id == 130

    def it_notices_shapes_that_replaced_the_ones_it_remembered(self):
        prs, slide = _slide_with_shapes(3)
        spTree = slide.shapes._spTree
        for sp in spTree.xpath("p:sp"):
            spTree.remove(sp)
        spTree.append(_foreign_shape(77))

        assert _add_rect(slide.shapes).shape_id == 78

    def it_notices_a_shape_appended_to_the_group_it_adds_to(self):
        prs, slide = _slide_with_shapes(1)
        group = slide.shapes.add_group_shape()
        _add_rect(group.shapes)
        group._element.append(_foreign_shape(300))

        assert _add_rect(group.shapes).shape_id == 301

    def it_notices_a_top_level_arrival_when_adding_to_a_group(self):
        prs, slide = _slide_with_shapes(1)
        group = slide.shapes.add_group_shape()
        _add_rect(group.shapes)
        slide.shapes._spTree.append(_foreign_shape(300))

        assert _add_rect(group.shapes).shape_id == 301

    def it_notices_a_group_arriving_with_shapes_inside(self):
        import copy

        prs, slide = _slide_with_shapes(1)
        group = slide.shapes.add_group_shape()
        for _ in range(3):
            _add_rect(group.shapes)
        clone = copy.deepcopy(group._element)
        for i, cNvPr in enumerate(clone.xpath(".//p:cNvPr")):
            cNvPr.set("id", str(200 + i))
        slide.shapes._spTree.append(clone)

        assert _add_rect(slide.shapes).shape_id == 204

    def it_never_hands_out_the_same_id_twice(self):
        # Even before the shape it was reserved for is inserted, and even when
        # the shape that held the highest id is deleted again.
        prs, slide = _slide_with_shapes(2)
        spTree = slide.shapes._spTree
        reserved = spTree.allocate_shape_id()
        assert spTree.allocate_shape_id() == reserved + 1

        last = slide.shapes[-1]
        last_id = last.shape_id
        spTree.remove(last._element)
        assert _add_rect(slide.shapes).shape_id > reserved + 1 > last_id

    def but_it_still_rescans_after_invalidate_shape_id_cache(self):
        prs, slide = _slide_with_shapes(4)
        spTree = slide.shapes._spTree
        middle = slide.shapes[1]._element
        middle.addnext(_foreign_shape(900))  # -- in the middle: not seen locally

        spTree.invalidate_shape_id_cache()

        assert _add_rect(slide.shapes).shape_id == 901

    def it_keeps_api_ids_clear_of_every_id_already_present(self):
        prs, slide = _slide_with_shapes(3)
        spTree = slide.shapes._spTree
        group = slide.shapes.add_group_shape()
        _add_rect(group.shapes)
        for step in range(40):
            present = set(_all_ids(slide))
            kind = step % 4
            if kind == 0:
                spTree.append(_foreign_shape(1000 + 10 * step))
            elif kind == 1:
                group._element.append(_foreign_shape(1000 + 10 * step))
            else:
                shapes = group.shapes if kind == 2 else slide.shapes
                assert _add_rect(shapes).shape_id not in present
        ids = _all_ids(slide)
        assert len(ids) == len(set(ids))

    def it_does_not_rescan_or_walk_the_slide_on_ordinary_adds(self, monkeypatch):
        # Adding 2,000 shapes to one slide took ~0.2 s; the self-check must not
        # make that quadratic. In steady state it re-reads no shape at all.
        from power_pptx.oxml.shapes import groupshape

        prs, slide = _slide_with_shapes(0)
        _add_rect(slide.shapes)  # -- primes the cache: the one full scan
        calls = {"rescan": 0, "inspect": 0}
        rescan, inspect = CT_GroupShape._rescan_ids, groupshape._max_id_in

        def counting_rescan(self, root, floor):
            calls["rescan"] += 1
            return rescan(self, root, floor)

        def counting_inspect(elm):
            calls["inspect"] += 1
            return inspect(elm)

        monkeypatch.setattr(CT_GroupShape, "_rescan_ids", counting_rescan)
        monkeypatch.setattr(groupshape, "_max_id_in", counting_inspect)
        group = slide.shapes.add_group_shape()
        for _ in range(300):
            _add_rect(slide.shapes)
            _add_rect(group.shapes)

        assert calls == {"rescan": 0, "inspect": 1}  # -- the new group, once
