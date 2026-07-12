"""GroupShape and related objects."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator

from power_pptx.dml.effect import (
    BlurFormat,
    GlowFormat,
    InnerShadowFormat,
    PresetShadowFormat,
    ReflectionFormat,
    ShadowFormat,
    SoftEdgeFormat,
)
from power_pptx.dml.fill import FillFormat
from power_pptx.enum.shapes import MSO_SHAPE_TYPE
from power_pptx.shapes.base import BaseShape
from power_pptx.util import Emu, _coerce_emu, lazyproperty

if TYPE_CHECKING:
    from power_pptx.action import ActionSetting
    from power_pptx.oxml.shapes import ShapeElement
    from power_pptx.oxml.shapes.groupshape import CT_GroupShape
    from power_pptx.shapes.shapetree import GroupShapes
    from power_pptx.types import ProvidesPart
    from power_pptx.util import Length


class GroupShape(BaseShape):
    """A shape that acts as a container for other shapes."""

    def __init__(self, grpSp: CT_GroupShape, parent: ProvidesPart):
        super().__init__(grpSp, parent)
        self._grpSp = grpSp

    @lazyproperty
    def click_action(self) -> ActionSetting:
        """Unconditionally raises `TypeError`.

        A group shape cannot have a click action or hover action.
        """
        raise TypeError("a group shape cannot have a click action")

    @property
    def has_text_frame(self) -> bool:
        """Unconditionally |False|.

        A group shape does not have a textframe and cannot itself contain text. This does not
        impact the ability of shapes contained by the group to each have their own text.
        """
        return False

    @lazyproperty
    def blur(self) -> BlurFormat:
        """|BlurFormat| object representing the Gaussian blur on this group."""
        return BlurFormat(self._grpSp.grpSpPr)

    @lazyproperty
    def glow(self) -> GlowFormat:
        """|GlowFormat| object representing glow effect for this group."""
        return GlowFormat(self._grpSp.grpSpPr)

    @lazyproperty
    def reflection(self) -> ReflectionFormat:
        """|ReflectionFormat| object representing the reflection on this group."""
        return ReflectionFormat(self._grpSp.grpSpPr)

    @lazyproperty
    def shadow(self) -> ShadowFormat:
        """|ShadowFormat| object representing shadow effect for this group.

        A |ShadowFormat| object is always returned, even when no shadow is explicitly defined on
        this group shape (i.e. when the group inherits its shadow behavior).
        """
        return ShadowFormat(self._grpSp.grpSpPr)

    @lazyproperty
    def soft_edges(self) -> SoftEdgeFormat:
        """|SoftEdgeFormat| object representing soft-edge effect for this group."""
        return SoftEdgeFormat(self._grpSp.grpSpPr)

    @lazyproperty
    def inner_shadow(self) -> InnerShadowFormat:
        """|InnerShadowFormat| for this group (over ``p:grpSpPr``).

        Overrides the |BaseShape| version, which targets ``spPr`` — a group
        exposes ``grpSpPr`` instead, so the inherited accessor would raise.
        """
        return InnerShadowFormat(self._grpSp.grpSpPr)

    @lazyproperty
    def preset_shadow(self) -> PresetShadowFormat:
        """|PresetShadowFormat| for this group (over ``p:grpSpPr``)."""
        return PresetShadowFormat(self._grpSp.grpSpPr)

    @property
    def three_d(self):
        """Unconditionally raises |NotImplementedError|.

        A group shape's ``p:grpSpPr`` legally carries ``a:scene3d`` but not
        ``a:sp3d`` (bevel / extrusion), so the |ThreeDFormat| facade — which
        writes both — cannot target it without emitting schema-invalid XML.
        Apply 3-D formatting to the member shapes instead.
        """
        raise NotImplementedError("three_d property on GroupShape not supported")

    @property
    def fill(self) -> FillFormat:
        """|FillFormat| instance for this group, providing access to fill properties.

        A group's ``p:grpSpPr`` admits a fill (but, unlike a regular shape, *not* a
        line — the OOXML schema does not allow ``a:ln`` on a group). Setting a fill
        tints the whole group; member shapes that declare their own fill are
        unaffected and paint on top. Use ``fill.solid()``, ``fill.gradient()``,
        ``fill.background()`` (transparent), etc., exactly as on an autoshape::

            group.fill.solid()
            group.fill.fore_color.rgb = "1F4E79"
        """
        return FillFormat.from_fill_parent(self._grpSp.grpSpPr)

    @property
    def shape_type(self) -> MSO_SHAPE_TYPE:
        """Member of :ref:`MsoShapeType` identifying the type of this shape.

        Unconditionally `MSO_SHAPE_TYPE.GROUP` in this case
        """
        return MSO_SHAPE_TYPE.GROUP

    @lazyproperty
    def shapes(self) -> GroupShapes:
        """|GroupShapes| object for this group.

        The |GroupShapes| object provides access to the group's member shapes and provides methods
        for adding new ones.
        """
        from power_pptx.shapes.shapetree import GroupShapes

        return GroupShapes(self._element, self)

    def move(self, dx: Length | int | float, dy: Length | int | float) -> GroupShape:
        """Translate the entire group by (*dx*, *dy*) and return self.

        *dx* and *dy* are lengths (e.g. ``Inches(1)``, ``Emu(...)``, or a bare
        EMU ``int``)::

            group.move(Inches(0.5), Inches(-0.25))

        The group's offset, its child-coordinate origin, and every member are
        shifted by the same translation. Shifting the members + ``chOff`` (not
        just the group's own ``off``) is what makes the move *durable*: a later
        ``recalculate_extents()`` — triggered by ``group.shapes.add_*`` or
        ``fit_to_children()`` — recomputes ``off`` from the member geometry, so
        a move that only touched ``off`` would silently snap back.
        """
        grpSp = self._grpSp
        edx = int(_coerce_emu(dx))
        edy = int(_coerce_emu(dy))
        # Express the translation in the group's child-coordinate space too, in
        # case the group is scaled (ext != chExt); for the common unscaled
        # group this is just (edx, edy).
        ext_cx = int(self.width) if self.width is not None else 0
        ext_cy = int(self.height) if self.height is not None else 0
        chExt = grpSp.chExt
        ch_cx, ch_cy = int(chExt.cx or 0), int(chExt.cy or 0)
        cdx = round(edx * ch_cx / ext_cx) if ext_cx else edx
        cdy = round(edy * ch_cy / ext_cy) if ext_cy else edy

        self.left = Emu((int(self.left) if self.left is not None else 0) + edx)
        self.top = Emu((int(self.top) if self.top is not None else 0) + edy)
        chOff = grpSp.chOff
        chOff.x = Emu(int(chOff.x or 0) + cdx)
        chOff.y = Emu(int(chOff.y or 0) + cdy)
        for elm in grpSp.iter_shape_elms():
            elm.x = Emu(int(elm.x or 0) + cdx)
            elm.y = Emu(int(elm.y or 0) + cdy)
        return self

    def walk(self) -> Iterator[BaseShape]:
        """Generate every descendant shape, recursing into nested groups.

        Yields shapes depth-first in document (z-order) order. Nested
        |GroupShape| objects are themselves yielded *before* their children, so
        callers that only want leaf shapes can filter with
        ``s.shape_type != MSO_SHAPE_TYPE.GROUP``. This makes whole-tree layout,
        measurement, and lint passes possible without hand-rolled recursion::

            for shape in group.walk():
                ...
        """
        for shape in self.shapes:
            yield shape
            if isinstance(shape, GroupShape):
                yield from shape.walk()

    def fit_to_children(self) -> GroupShape:
        """Shrink-wrap the group's offset/extent to tightly bound its children.

        Recalculates the group's position and size (``a:off`` / ``a:ext``) from
        the current geometry of its member shapes — the same recalculation that
        runs automatically when a shape is added through ``group.shapes.add_*``.
        Call it after moving or resizing member shapes directly so the group's
        ``bbox`` (and any lint that relies on it) stays accurate. Returns self.
        """
        self._grpSp.recalculate_extents()
        return self

    def ungroup(self) -> list[BaseShape]:
        """Dissolve the group, promoting its member shapes to the parent and return them.

        Each child is re-parented to the group's container (the slide shape tree
        or an enclosing group) with its position and size transformed from the
        group's child coordinate space into the container's space, so shapes do
        not move or resize visually. Z-order is preserved: the promoted shapes
        occupy the group's former slot. The (now empty) group element is removed.

        Raises ``ValueError`` if the group is rotated or flipped — baking such a
        transform into each child is ambiguous and unsupported; reset rotation
        and flip to zero before ungrouping.
        """
        grpSp = self._grpSp
        container = grpSp.getparent()
        if container is None:
            raise ValueError("cannot ungroup a group that is not in a shape tree")
        if self.rotation or grpSp.flipH or grpSp.flipV:
            raise ValueError(
                "ungroup() does not support a rotated or flipped group; reset "
                "rotation and flip to 0 before ungrouping"
            )

        # Group offset/extent (in the container's coordinate space) and the
        # group's own child coordinate space (chOff/chExt).
        off_x = int(self.left) if self.left is not None else 0
        off_y = int(self.top) if self.top is not None else 0
        ext_cx = int(self.width) if self.width is not None else 0
        ext_cy = int(self.height) if self.height is not None else 0
        chOff, chExt = grpSp.chOff, grpSp.chExt
        ch_x, ch_y = int(chOff.x or 0), int(chOff.y or 0)
        ch_cx, ch_cy = int(chExt.cx or 0), int(chExt.cy or 0)
        sx = (ext_cx / ch_cx) if ch_cx else 1.0
        sy = (ext_cy / ch_cy) if ch_cy else 1.0

        # Pre-compute each child's container-space geometry from its child-space
        # coords before re-parenting (so the read isn't affected by the moves).
        placements: list[tuple[ShapeElement, int, int, int, int]] = []
        for elm in grpSp.iter_shape_elms():
            cx0 = int(elm.x or 0)
            cy0 = int(elm.y or 0)
            cw = int(elm.cx or 0)
            chgt = int(elm.cy or 0)
            new_x = off_x + round((cx0 - ch_x) * sx)
            new_y = off_y + round((cy0 - ch_y) * sy)
            placements.append((elm, new_x, new_y, round(cw * sx), round(chgt * sy)))

        promoted: list[BaseShape] = []
        for elm, nx, ny, nw, nh in placements:
            grpSp.remove(elm)
            container.insert(container.index(grpSp), elm)
            elm.x, elm.y, elm.cx, elm.cy = Emu(nx), Emu(ny), Emu(nw), Emu(nh)
            promoted.append(self._parent._shape_factory(elm))  # pyright: ignore[reportAttributeAccessIssue]

        container.remove(grpSp)
        return promoted
