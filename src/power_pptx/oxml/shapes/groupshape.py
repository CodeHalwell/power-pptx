"""lxml custom element classes for shape-tree-related XML elements."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Iterator

from lxml import etree

from power_pptx.dml.fill import CT_GradientFillProperties
from power_pptx.enum.shapes import MSO_CONNECTOR_TYPE
from power_pptx.oxml import parse_xml
from power_pptx.oxml.ns import nsdecls, qn
from power_pptx.oxml.shapes.autoshape import CT_Shape
from power_pptx.oxml.shapes.connector import CT_Connector
from power_pptx.oxml.shapes.graphfrm import CT_GraphicalObjectFrame
from power_pptx.oxml.shapes.picture import CT_Picture
from power_pptx.oxml.shapes.shared import BaseShapeElement
from power_pptx.oxml.xmlchemy import (
    BaseOxmlElement,
    Choice,
    OneAndOnlyOne,
    ZeroOrOne,
    ZeroOrOneChoice,
)
from power_pptx.util import Emu

if TYPE_CHECKING:
    from power_pptx.enum.shapes import PP_PLACEHOLDER
    from power_pptx.oxml.shapes import ShapeElement
    from power_pptx.oxml.shapes.shared import CT_Transform2D

# -- Shape-id cache ---------------------------------------------------------
#
# The largest id in use is cached on the document root so that adding a shape
# does not scan the whole slide. A cache like that is only right while every
# new id comes from it, and the long-standing idiom for copying a shape,
# `spTree.append(copy.deepcopy(other_shape._element))`, brings one in from
# outside. So before the cached value is trusted, the places where shapes get
# added are checked: the two ends of the top-level shape tree and of the group
# being added to. Each end remembers its few outermost children; any sibling
# now lying beyond them has arrived since, and is looked at for ids above the
# cached maximum. That is a few pointer hops per allocation however many
# shapes the slide holds. Only when a new arrival does carry a higher id, or
# more has changed than this can account for, is the slide scanned again.

#: every `id` attribute at or below the context element, as plain strings
_ids_in = etree.XPath(".//@id", smart_strings=False)

#: how many of the outermost children are remembered at each end of a container
_REMEMBERED_PER_END = 3

#: how many new arrivals are examined at one end before scanning instead
_MAX_NEW_PER_END = 8

#: children of a shape container that are not shapes
_NON_SHAPE_TAGS = frozenset((qn("p:nvGrpSpPr"), qn("p:grpSpPr"), qn("p:extLst")))

_SP_TREE_TAG = qn("p:spTree")
_GRP_SP_TAG = qn("p:grpSp")


class CT_GroupShape(BaseShapeElement):
    """Used for shape tree (`p:spTree`) as well as the group shape (`p:grpSp`) elements."""

    nvGrpSpPr: CT_GroupShapeNonVisual = OneAndOnlyOne(  # pyright: ignore[reportAssignmentType]
        "p:nvGrpSpPr"
    )
    grpSpPr: CT_GroupShapeProperties = OneAndOnlyOne(  # pyright: ignore[reportAssignmentType]
        "p:grpSpPr"
    )

    _shape_tags = (
        qn("p:sp"),
        qn("p:grpSp"),
        qn("p:graphicFrame"),
        qn("p:cxnSp"),
        qn("p:pic"),
        qn("p:contentPart"),
    )

    def add_autoshape(
        self, id_: int, name: str, prst: str, x: int, y: int, cx: int, cy: int
    ) -> CT_Shape:
        """Return new `p:sp` appended to the group/shapetree with specified attributes."""
        sp = CT_Shape.new_autoshape_sp(id_, name, prst, x, y, cx, cy)
        self._insert_shape(sp)
        return sp

    def add_cxnSp(
        self,
        id_: int,
        name: str,
        type_member: MSO_CONNECTOR_TYPE,
        x: int,
        y: int,
        cx: int,
        cy: int,
        flipH: bool,
        flipV: bool,
    ) -> CT_Connector:
        """Return new `p:cxnSp` appended to the group/shapetree with the specified attribues."""
        prst = MSO_CONNECTOR_TYPE.to_xml(type_member)
        cxnSp = CT_Connector.new_cxnSp(id_, name, prst, x, y, cx, cy, flipH, flipV)
        self._insert_shape(cxnSp)
        return cxnSp

    def add_freeform_sp(self, x: int, y: int, cx: int, cy: int) -> CT_Shape:
        """Append a new freeform `p:sp` with specified position and size."""
        shape_id = self._next_shape_id
        name = "Freeform %d" % (shape_id - 1,)
        sp = CT_Shape.new_freeform_sp(shape_id, name, x, y, cx, cy)
        self._insert_shape(sp)
        return sp

    def add_grpSp(self) -> CT_GroupShape:
        """Return `p:grpSp` element newly appended to this shape tree.

        The element contains no sub-shapes, is positioned at (0, 0), and has
        width and height of zero.
        """
        shape_id = self._next_shape_id
        name = "Group %d" % (shape_id - 1,)
        grpSp = CT_GroupShape.new_grpSp(shape_id, name)
        self._insert_shape(grpSp)
        return grpSp

    def add_pic(
        self, id_: int, name: str, desc: str, rId: str, x: int, y: int, cx: int, cy: int
    ) -> CT_Picture:
        """Append a `p:pic` shape to the group/shapetree having properties as specified in call."""
        pic = CT_Picture.new_pic(id_, name, desc, rId, x, y, cx, cy)
        self._insert_shape(pic)
        return pic

    def add_placeholder(
        self, id_: int, name: str, ph_type: PP_PLACEHOLDER, orient: str, sz: str, idx: int
    ) -> CT_Shape:
        """Append a newly-created placeholder `p:sp` shape having the specified properties."""
        sp = CT_Shape.new_placeholder_sp(id_, name, ph_type, orient, sz, idx)
        self._insert_shape(sp)
        return sp

    def add_table(
        self, id_: int, name: str, rows: int, cols: int, x: int, y: int, cx: int, cy: int
    ) -> CT_GraphicalObjectFrame:
        """Append a `p:graphicFrame` shape containing a table as specified in call."""
        graphicFrame = CT_GraphicalObjectFrame.new_table_graphicFrame(
            id_, name, rows, cols, x, y, cx, cy
        )
        self._insert_shape(graphicFrame)
        return graphicFrame

    def add_textbox(self, id_: int, name: str, x: int, y: int, cx: int, cy: int) -> CT_Shape:
        """Append a newly-created textbox `p:sp` shape having the specified position and size."""
        sp = CT_Shape.new_textbox_sp(id_, name, x, y, cx, cy)
        self._insert_shape(sp)
        return sp

    def _insert_shape(self, shape_elm: ShapeElement) -> None:
        """Add `shape_elm`, a shape this class has just built, as the last shape child.

        The shape carries ids that came from :meth:`allocate_shape_id`, so the
        id cache is told it is no stranger. The next allocation then finds
        nothing new at the end of this container and has nothing to examine.
        """
        self.insert_element_before(shape_elm, "p:extLst")
        ends = getattr(self.getroottree().getroot(), "_pptx_shape_id_ends", None)
        remembered = None if ends is None else ends.get(self)
        if remembered is None:
            return
        head, (anchors, beyond) = remembered
        previous = shape_elm.getprevious()
        expected_previous = (
            previous is anchors[0]
            if anchors
            else previous is None or previous.tag in _NON_SHAPE_TAGS
        )
        if not expected_previous:
            # -- not where the cache believed the end to be; say nothing and
            # -- let the next allocation examine it like any other arrival
            return
        tail = ((shape_elm,) + anchors[: _REMEMBERED_PER_END - 1], beyond)
        if not anchors:
            # -- first shape in the container: it is the start of it as well
            head = _remember_end(self, False)
        ends[self] = (head, tail)

    @property
    def chExt(self):
        """Descendent `p:grpSpPr/a:xfrm/a:chExt` element."""
        return self.grpSpPr.get_or_add_xfrm().get_or_add_chExt()

    @property
    def chOff(self):
        """Descendent `p:grpSpPr/a:xfrm/a:chOff` element."""
        return self.grpSpPr.get_or_add_xfrm().get_or_add_chOff()

    def get_or_add_xfrm(self) -> CT_Transform2D:
        """Return the `a:xfrm` grandchild element, newly-added if not present."""
        return self.grpSpPr.get_or_add_xfrm()

    def iter_ph_elms(self):
        """Generate each placeholder shape child element in document order."""
        for e in self.iter_shape_elms():
            if e.has_ph_elm:
                yield e

    def iter_shape_elms(self) -> Iterator[ShapeElement]:
        """Generate each child of this `p:spTree` element that corresponds to a shape.

        Items appear in XML document order.
        """
        for elm in self.iterchildren():
            if elm.tag in self._shape_tags:
                yield elm

    @property
    def max_shape_id(self) -> int:
        """Maximum int value assigned as @id in this slide.

        This is generally a shape-id, but ids can be assigned to other
        objects so we just check all @id values anywhere in the document
        (XML id-values have document scope).

        In practice, its minimum value is 1 because the spTree element itself
        is always assigned id="1".

        First access scans the document; the result is then cached on the
        document-root element and kept current as ids are allocated via
        :meth:`allocate_shape_id`.
        """
        return self._ensure_id_cache()

    def allocate_shape_id(self) -> int:
        """Reserve and return the next unused id for a new shape.

        Caches the running maximum on the document-root element so consecutive
        adds are O(1) instead of triggering a fresh ``//@id`` scan each call
        (which is what produced the historical O(N²) behavior over a slide).

        The cache checks itself before it is used: shapes that reached the
        start or end of the top-level shape tree, or of this group, by some
        other route (``spTree.append(copy.deepcopy(elm))``, ``spTree.insert(2,
        elm)``) are noticed and their ids taken into account, so the id
        returned is unused even then. An id is never handed out twice, whether
        or not the shape it was reserved for has been inserted yet.

        The check is deliberately local, which is what keeps it cheap. A shape
        spliced into the *middle* of a container, or into a group other than
        the one being added to, is not noticed; call
        :meth:`invalidate_shape_id_cache` after an edit like that.
        """
        cursor = self._ensure_id_cache() + 1
        self._set_id_cache(cursor)
        return cursor

    def invalidate_shape_id_cache(self) -> None:
        """Drop the cached max-shape-id; next access will re-scan ``//@id``."""
        root = self.getroottree().getroot()
        for name in ("_pptx_shape_id_cursor", "_pptx_shape_id_ends"):
            if hasattr(root, name):
                delattr(root, name)

    def _ensure_id_cache(self) -> int:
        """Return the largest id in use, from the cache when that can be trusted."""
        root = self.getroottree().getroot()
        cursor = getattr(root, "_pptx_shape_id_cursor", None)
        if cursor is not None and self._id_cache_is_current(root, cursor):
            return cursor
        return self._rescan_ids(root, floor=cursor)

    def _set_id_cache(self, value: int) -> None:
        self.getroottree().getroot()._pptx_shape_id_cursor = value

    def _rescan_ids(self, root, floor: int | None) -> int:
        """Scan the document for its largest id, cache it, and return it.

        `floor` is the value cached until now, if any. The result never drops
        below it: an id that has been handed out may belong to a shape that is
        still being built and is not in the document yet.
        """
        used_ids = (int(s) for s in self.xpath("//@id") if s.isdigit())
        cursor = max(used_ids, default=0)
        if floor is not None and floor > cursor:
            cursor = floor
        root._pptx_shape_id_cursor = cursor
        root._pptx_shape_id_ends = {
            container: _remember_ends(container) for container in self._watched_containers()
        }
        return cursor

    def _watched_containers(self) -> tuple[CT_GroupShape, ...]:
        """The containers checked for new arrivals: the top-level tree and this one."""
        if self.tag == _SP_TREE_TAG:
            return (self,)
        top = self
        parent = top.getparent()
        while parent is not None and parent.tag in (_GRP_SP_TAG, _SP_TREE_TAG):
            top, parent = parent, parent.getparent()
        return (top,) if top is self else (top, self)

    def _id_cache_is_current(self, root, cursor: int) -> bool:
        """True if no id above `cursor` has turned up where shapes get added."""
        ends = getattr(root, "_pptx_shape_id_ends", None)
        if ends is None:
            return False
        for container in self._watched_containers():
            if not _ends_still_fit(ends, container, cursor):
                return False
        return True

    @classmethod
    def new_grpSp(cls, id_: int, name: str) -> CT_GroupShape:
        """Return new "loose" `p:grpSp` element having `id_` and `name`."""
        xml = (
            "<p:grpSp %s>\n"
            "  <p:nvGrpSpPr>\n"
            '    <p:cNvPr id="%%d" name="%%s"/>\n'
            "    <p:cNvGrpSpPr/>\n"
            "    <p:nvPr/>\n"
            "  </p:nvGrpSpPr>\n"
            "  <p:grpSpPr>\n"
            "    <a:xfrm>\n"
            '      <a:off x="0" y="0"/>\n'
            '      <a:ext cx="0" cy="0"/>\n'
            '      <a:chOff x="0" y="0"/>\n'
            '      <a:chExt cx="0" cy="0"/>\n'
            "    </a:xfrm>\n"
            "  </p:grpSpPr>\n"
            "</p:grpSp>" % nsdecls("a", "p", "r")
        ) % (id_, name)
        grpSp = parse_xml(xml)
        return grpSp

    def recalculate_extents(self) -> None:
        """Adjust x, y, cx, and cy to incorporate all contained shapes.

        This would typically be called when a contained shape is added,
        removed, or its position or size updated.

        This method is recursive "upwards" since a change in a group shape
        can change the position and size of its containing group.
        """
        if not self.tag == qn("p:grpSp"):
            return

        x, y, cx, cy = self._child_extents

        self.chOff.x = self.x = x
        self.chOff.y = self.y = y
        self.chExt.cx = self.cx = cx
        self.chExt.cy = self.cy = cy
        self.getparent().recalculate_extents()

    @property
    def xfrm(self) -> CT_Transform2D | None:
        """The `a:xfrm` grandchild element or |None| if not found."""
        return self.grpSpPr.xfrm

    @property
    def _child_extents(self) -> tuple[int, int, int, int]:
        """(x, y, cx, cy) tuple representing net position and size.

        The values are formed as a composite of the contained child shapes.
        """
        child_shape_elms = list(self.iter_shape_elms())

        if not child_shape_elms:
            return Emu(0), Emu(0), Emu(0), Emu(0)

        min_x = min([xSp.x for xSp in child_shape_elms])
        min_y = min([xSp.y for xSp in child_shape_elms])
        max_x = max([(xSp.x + xSp.cx) for xSp in child_shape_elms])
        max_y = max([(xSp.y + xSp.cy) for xSp in child_shape_elms])

        x = min_x
        y = min_y
        cx = max_x - min_x
        cy = max_y - min_y

        return x, y, cx, cy

    @property
    def _next_shape_id(self) -> int:
        """Return unique shape id suitable for use with a new shape element.

        Equivalent to :meth:`allocate_shape_id`; preserved for OXML-internal
        callers (`add_freeform_sp`, `add_grpSp`).
        """
        return self.allocate_shape_id()


def _max_id_in(elm) -> int:
    """The largest numeric `id` attribute on `elm` or anything inside it, else 0."""
    return max((int(s) for s in _ids_in(elm) if s.isdigit()), default=0)


def _remember_ends(container) -> tuple:
    """What to remember about both ends of `container`: `(head, tail)`."""
    return _remember_end(container, False), _remember_end(container, True)


def _remember_end(container, from_end: bool) -> tuple:
    """What to remember about one end of `container`: `(anchors, beyond)`.

    `anchors` are its few shape-level children nearest that end, outermost
    first. `beyond` is the non-shape sibling just past the outermost one, if
    any (`p:grpSpPr` at the start, `p:extLst` at the end). It is kept only so
    that lxml need not build a new proxy for it on every check.
    """
    anchors = []
    beyond = None
    for child in container.iterchildren(reversed=from_end):
        if child.tag in _NON_SHAPE_TAGS:
            if anchors:
                break
            beyond = child
            continue
        anchors.append(child)
        if len(anchors) == _REMEMBERED_PER_END:
            break
    return tuple(anchors), beyond


def _ends_still_fit(ends: dict, container, cursor: int) -> bool:
    """True if nothing with an id above `cursor` has arrived at either end of `container`.

    `ends` maps each watched container to what is remembered about its ends.
    The entry for `container` is brought up to date when it has none yet or an
    end has changed in a way that still fits.
    """
    remembered = ends.get(container)
    if remembered is None:
        # -- first use of this group since the last scan; everything in it is
        # -- unseen, which for a group just created is nothing
        if _max_id_in(container) > cursor:
            return False
        ends[container] = _remember_ends(container)
        return True

    head, tail = remembered
    head_changed = _arrivals_fit(container, head, False, cursor)
    if head_changed is None:
        return False
    tail_changed = _arrivals_fit(container, tail, True, cursor)
    if tail_changed is None:
        return False
    if head_changed or tail_changed:
        ends[container] = (
            _remember_end(container, False) if head_changed else head,
            _remember_end(container, True) if tail_changed else tail,
        )
    return True


def _arrivals_fit(container, remembered: tuple, from_end: bool, cursor: int) -> bool | None:
    """Check what has arrived at one end of `container` since `remembered` was taken.

    Returns |False| when that end is as it was, |True| when it has changed but
    holds no id above `cursor` (so it should be remembered afresh), and |None|
    when the cached `cursor` cannot be relied on: an arrival carries a higher
    id, or the end has changed beyond what can be followed from here.
    """
    anchors = remembered[0]
    if not anchors:
        # -- no shapes were here last time, so any here now are new; look at
        # -- them all, starting from this end
        first = next(container.iterchildren(reversed=from_end), None)
        arrivals = _count_arrivals(first, not from_end, cursor, stop_at_non_shape=False)
        return None if arrivals is None else arrivals > 0

    # -- the outermost remembered child still in place marks where the known
    # -- part ends; the walk goes outward from it, away from the remembered
    # -- children: forward at the end of the container, backward at its start,
    # -- where it stops at `p:grpSpPr` (nothing precedes it but `p:nvGrpSpPr`)
    in_place = _outermost_in_place(anchors, container)
    if in_place is None:
        return None
    anchor, lost = in_place
    beyond = anchor.getnext() if from_end else anchor.getprevious()
    arrivals = _count_arrivals(beyond, from_end, cursor, stop_at_non_shape=not from_end)
    if arrivals is None:
        return None
    return lost or arrivals > 0


def _outermost_in_place(anchors: tuple, container) -> tuple | None:
    """`(anchor, lost)` for the outermost of `anchors` still in `container`, else |None|.

    `lost` is |True| when the anchors outside that one are gone: deleted or
    moved away.
    """
    for index, anchor in enumerate(anchors):
        if anchor.getparent() is container:
            return anchor, index > 0
    return None


def _count_arrivals(sibling, forward: bool, cursor: int, stop_at_non_shape: bool) -> int | None:
    """Count the shapes from `sibling` on, walking `forward` or backward.

    Children that are not shapes are stepped over, or end the walk when
    `stop_at_non_shape`. Returns |None| instead when one of the shapes carries
    an id above `cursor`, or when there are more than `_MAX_NEW_PER_END` to
    look at.
    """
    examined = 0
    while sibling is not None:
        if sibling.tag not in _NON_SHAPE_TAGS:
            if examined == _MAX_NEW_PER_END or _max_id_in(sibling) > cursor:
                return None
            examined += 1
        elif stop_at_non_shape:
            break
        sibling = sibling.getnext() if forward else sibling.getprevious()
    return examined


class CT_GroupShapeNonVisual(BaseShapeElement):
    """`p:nvGrpSpPr` element."""

    cNvPr = OneAndOnlyOne("p:cNvPr")


class CT_GroupShapeProperties(BaseOxmlElement):
    """p:grpSpPr element"""

    get_or_add_xfrm: Callable[[], CT_Transform2D]

    _tag_seq = (
        "a:xfrm",
        "a:noFill",
        "a:solidFill",
        "a:gradFill",
        "a:blipFill",
        "a:pattFill",
        "a:grpFill",
        "a:effectLst",
        "a:effectDag",
        "a:scene3d",
        "a:extLst",
    )
    xfrm: CT_Transform2D | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "a:xfrm", successors=_tag_seq[1:]
    )
    eg_fillProperties = ZeroOrOneChoice(
        (
            Choice("a:noFill"),
            Choice("a:solidFill"),
            Choice("a:gradFill"),
            Choice("a:blipFill"),
            Choice("a:pattFill"),
            Choice("a:grpFill"),
        ),
        successors=_tag_seq[7:],
    )
    effectLst = ZeroOrOne("a:effectLst", successors=_tag_seq[8:])
    del _tag_seq

    def _new_gradFill(self):
        return CT_GradientFillProperties.new_gradFill()
