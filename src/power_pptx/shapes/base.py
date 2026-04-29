"""Base shape-related objects such as BaseShape."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from power_pptx.action import ActionSetting
from power_pptx.dml.effect import (
    BlurFormat,
    GlowFormat,
    ReflectionFormat,
    ShadowFormat,
    SoftEdgeFormat,
)
from power_pptx.dml.three_d import ThreeDFormat
from power_pptx.shared import ElementProxy
from power_pptx.util import lazyproperty

if TYPE_CHECKING:
    from power_pptx.design.style import ShapeStyle
    from power_pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER
    from power_pptx.oxml.shapes import ShapeElement
    from power_pptx.oxml.shapes.shared import CT_Placeholder
    from power_pptx.parts.slide import BaseSlidePart
    from power_pptx.types import ProvidesPart
    from power_pptx.util import Length


class BaseShape(object):
    """Base class for shape objects.

    Subclasses include |Shape|, |Picture|, and |GraphicFrame|.
    """

    def __init__(self, shape_elm: ShapeElement, parent: ProvidesPart):
        super().__init__()
        self._element = shape_elm
        self._parent = parent

    def __eq__(self, other: object) -> bool:
        """|True| if this shape object proxies the same element as *other*.

        Equality for proxy objects is defined as referring to the same XML element, whether or not
        they are the same proxy object instance.
        """
        if not isinstance(other, BaseShape):
            return False
        return self._element is other._element

    def __ne__(self, other: object) -> bool:
        if not isinstance(other, BaseShape):
            return True
        return self._element is not other._element

    @lazyproperty
    def click_action(self) -> ActionSetting:
        """|ActionSetting| instance providing access to click behaviors.

        Click behaviors are hyperlink-like behaviors including jumping to a hyperlink (web page)
        or to another slide in the presentation. The click action is that defined on the overall
        shape, not a run of text within the shape. An |ActionSetting| object is always returned,
        even when no click behavior is defined on the shape.
        """
        cNvPr = self._element._nvXxPr.cNvPr  # pyright: ignore[reportPrivateUsage]
        return ActionSetting(cNvPr, self)

    @property
    def element(self) -> ShapeElement:
        """`lxml` element for this shape, e.g. a CT_Shape instance.

        Note that manipulating this element improperly can produce an invalid presentation file.
        Make sure you know what you're doing if you use this to change the underlying XML.
        """
        return self._element

    @property
    def has_chart(self) -> bool:
        """|True| if this shape is a graphic frame containing a chart object.

        |False| otherwise. When |True|, the chart object can be accessed using the ``.chart``
        property.
        """
        # This implementation is unconditionally False, the True version is
        # on GraphicFrame subclass.
        return False

    @property
    def has_table(self) -> bool:
        """|True| if this shape is a graphic frame containing a table object.

        |False| otherwise. When |True|, the table object can be accessed using the ``.table``
        property.
        """
        # This implementation is unconditionally False, the True version is
        # on GraphicFrame subclass.
        return False

    @property
    def has_text_frame(self) -> bool:
        """|True| if this shape can contain text."""
        # overridden on Shape to return True. Only <p:sp> has text frame
        return False

    @property
    def height(self) -> Length:
        """Read/write. Integer distance between top and bottom extents of shape in EMUs."""
        return self._element.cy

    @height.setter
    def height(self, value: Length):
        self._element.cy = value

    @property
    def is_placeholder(self) -> bool:
        """True if this shape is a placeholder.

        A shape is a placeholder if it has a <p:ph> element.
        """
        return self._element.has_ph_elm

    @property
    def left(self) -> Length:
        """Integer distance of the left edge of this shape from the left edge of the slide.

        Read/write. Expressed in English Metric Units (EMU)
        """
        return self._element.x

    @left.setter
    def left(self, value: Length):
        self._element.x = value

    @property
    def name(self) -> str:
        """Name of this shape, e.g. 'Picture 7'."""
        return self._element.shape_name

    @name.setter
    def name(self, value: str):
        self._element._nvXxPr.cNvPr.name = value  # pyright: ignore[reportPrivateUsage]

    @property
    def part(self) -> BaseSlidePart:
        """The package part containing this shape.

        A |BaseSlidePart| subclass in this case. Access to a slide part should only be required if
        you are extending the behavior of |pp| API objects.
        """
        return cast("BaseSlidePart", self._parent.part)

    @property
    def placeholder_format(self) -> _PlaceholderFormat:
        """Provides access to placeholder-specific properties such as placeholder type.

        Raises |ValueError| on access if the shape is not a placeholder.
        """
        ph = self._element.ph
        if ph is None:
            raise ValueError("shape is not a placeholder")
        return _PlaceholderFormat(ph)

    @property
    def rotation(self) -> float:
        """Degrees of clockwise rotation.

        Read/write float. Negative values can be assigned to indicate counter-clockwise rotation,
        e.g. assigning -45.0 will change setting to 315.0.
        """
        return self._element.rot

    @rotation.setter
    def rotation(self, value: float):
        self._element.rot = value

    @lazyproperty
    def blur(self) -> BlurFormat:
        """|BlurFormat| object providing access to the Gaussian blur effect.

        Always returned, even when no blur is explicitly set.  Reading
        ``blur.radius`` returns None in that case.
        """
        return BlurFormat(self._element.spPr)

    @lazyproperty
    def glow(self) -> GlowFormat:
        """|GlowFormat| object providing access to glow effect for this shape.

        A |GlowFormat| object is always returned even when no glow is explicitly
        defined.  Reading ``glow.radius`` returns None in that case.
        """
        return GlowFormat(self._element.spPr)

    @lazyproperty
    def reflection(self) -> ReflectionFormat:
        """|ReflectionFormat| object providing access to the reflection effect.

        Always returned, even when no reflection is explicitly set.  Reads of
        the individual properties return None in that case.
        """
        return ReflectionFormat(self._element.spPr)

    @lazyproperty
    def shadow(self) -> ShadowFormat:
        """|ShadowFormat| object providing access to shadow for this shape.

        A |ShadowFormat| object is always returned, even when no shadow is
        explicitly defined on this shape (i.e. it inherits its shadow
        behavior).
        """
        return ShadowFormat(self._element.spPr)

    @lazyproperty
    def soft_edges(self) -> SoftEdgeFormat:
        """|SoftEdgeFormat| object providing access to soft-edge effect for this shape.

        A |SoftEdgeFormat| object is always returned even when no soft-edge is
        explicitly defined.  Reading ``soft_edges.radius`` returns None in that case.
        """
        return SoftEdgeFormat(self._element.spPr)

    @lazyproperty
    def style(self) -> ShapeStyle:
        """Token-resolving design-system facade for this shape.

        Returns a :class:`power_pptx.design.style.ShapeStyle` whose setters
        accept :class:`power_pptx.design.tokens` values (palette colors,
        shadow tokens, typography tokens) and fan them out into the
        shape's underlying ``fill`` / ``line`` / ``shadow`` proxies.

        Example::

            shape.style.fill = tokens.palette["primary"]
            shape.style.shadow = tokens.shadows["card"]
            shape.style.font = tokens.typography["body"]
        """
        from power_pptx.design.style import ShapeStyle

        return ShapeStyle(self)

    @lazyproperty
    def three_d(self) -> ThreeDFormat:
        """|ThreeDFormat| object providing access to 3-D formatting for this shape.

        A |ThreeDFormat| object is always returned even when no 3-D properties are
        explicitly defined.  Reading e.g. ``three_d.bevel_top.preset`` returns None in that case.

        Example::

            from power_pptx.enum.dml import BevelPreset, PresetMaterial
            from power_pptx.util import Pt

            shape.three_d.bevel_top.preset = BevelPreset.CIRCLE
            shape.three_d.bevel_top.width = Pt(4)
            shape.three_d.extrusion_height = Pt(6)
            shape.three_d.preset_material = PresetMaterial.MATTE
        """
        return ThreeDFormat(self._element.spPr)

    @property
    def shape_id(self) -> int:
        """Read-only positive integer identifying this shape.

        The id of a shape is unique among all shapes on a slide.
        """
        return self._element.shape_id

    @property
    def lint_group(self) -> str | None:
        """Group tag consulted by the layout linter to suppress same-group collisions.

        Shapes that share a non-empty ``lint_group`` may overlap without
        producing a :class:`~power_pptx.lint.ShapeCollision` warning. Shapes
        with ``lint_group is None`` (the default) and shapes belonging to
        different groups continue to warn on overlap.

        The value is round-tripped through save/load via an ``<a:ext>``
        element under the shape's ``cNvPr/extLst`` — the OOXML-sanctioned
        extension mechanism. PowerPoint preserves the element verbatim and
        does not flag it as unrecognised content.

        Example::

            card.lint_group = "kpi-card-1"
            accent_bar.lint_group = "kpi-card-1"
            # card and accent_bar may overlap without a lint warning.

        Assigning ``None`` clears the tag.
        """
        from power_pptx.lint import _read_lint_group

        cNvPr = self._element._nvXxPr.cNvPr  # pyright: ignore[reportPrivateUsage]
        return _read_lint_group(cNvPr)

    @lint_group.setter
    def lint_group(self, value: str | None) -> None:
        from power_pptx.lint import _clear_lint_group, _write_lint_group

        cNvPr = self._element._nvXxPr.cNvPr  # pyright: ignore[reportPrivateUsage]
        if value is None:
            _clear_lint_group(cNvPr)
            return
        if not isinstance(value, str) or not value:
            raise ValueError("lint_group must be a non-empty string or None")
        _write_lint_group(cNvPr, value)

    @property
    def lint_skip(self) -> frozenset[str]:
        """Lint check codes silenced on this shape.

        Per-shape opt-out for the linter: any :class:`LintIssue` whose
        ``code`` is in this set is dropped from the report when ``slide.lint()``
        is called.  Cross-shape issues (e.g. ``ShapeCollision``,
        ``ZOrderAnomaly``) are only suppressed when *both* shapes opt out —
        a one-sided opt-out keeps the warning, since the other shape may
        still want it surfaced.

        Example — silence intentional 8pt chrome::

            footer_label.lint_skip = {"MinFontSize"}
            rag_pill.lint_skip = {"MinFontSize"}

        Stored alongside ``lint_group`` in the same ``cNvPr/extLst/ext``
        block so it round-trips through save/load.  Assign ``set()`` /
        ``frozenset()`` to clear.
        """
        from power_pptx.lint import _read_lint_skip

        cNvPr = self._element._nvXxPr.cNvPr  # pyright: ignore[reportPrivateUsage]
        return _read_lint_skip(cNvPr)

    @lint_skip.setter
    def lint_skip(self, value) -> None:
        from power_pptx.lint import _write_lint_skip

        if value is None:
            value = frozenset()
        if not isinstance(value, (set, frozenset, list, tuple)):
            raise TypeError(
                "lint_skip must be a set/frozenset/list/tuple of issue "
                f"codes; got {type(value).__name__}"
            )
        codes = frozenset(str(c) for c in value)
        cNvPr = self._element._nvXxPr.cNvPr  # pyright: ignore[reportPrivateUsage]
        _write_lint_skip(cNvPr, codes)

    def delete(self) -> None:
        """Remove this shape from its slide and clean up dependent state.

        In addition to removing the shape's XML element, this purges any
        animation entries in the slide's timing tree that targeted this
        shape.  PowerPoint silently "repairs" decks with orphan timing
        references on open, but a clean tree avoids the prompt.

        Equivalent in spirit to::

            shape._element.getparent().remove(shape._element)

        but with the cleanup pass that the manual idiom misses.
        """
        # Snapshot the slide reference *before* detaching the element,
        # because once detached the parent walk would fail.
        slide = None
        try:
            slide = self.part.slide  # type: ignore[attr-defined]
        except Exception:
            slide = None

        parent = self._element.getparent()
        if parent is not None:
            parent.remove(self._element)

        if slide is not None:
            try:
                slide.animations.purge_orphans()
            except Exception:
                pass

    @property
    def shape_type(self) -> MSO_SHAPE_TYPE:
        """A member of MSO_SHAPE_TYPE classifying this shape by type.

        Like ``MSO_SHAPE_TYPE.CHART``. Must be implemented by subclasses.
        """
        raise NotImplementedError(f"{type(self).__name__} does not implement `.shape_type`")

    @property
    def top(self) -> Length:
        """Distance from the top edge of the slide to the top edge of this shape.

        Read/write. Expressed in English Metric Units (EMU)
        """
        return self._element.y

    @top.setter
    def top(self, value: Length):
        self._element.y = value

    @property
    def width(self) -> Length:
        """Distance between left and right extents of this shape.

        Read/write. Expressed in English Metric Units (EMU).
        """
        return self._element.cx

    @width.setter
    def width(self, value: Length):
        self._element.cx = value


class _PlaceholderFormat(ElementProxy):
    """Provides properties specific to placeholders, such as the placeholder type.

    Accessed via the :attr:`~.BaseShape.placeholder_format` property of a placeholder shape,
    """

    def __init__(self, element: CT_Placeholder):
        super().__init__(element)
        self._ph = element

    @property
    def element(self) -> CT_Placeholder:
        """The `p:ph` element proxied by this object."""
        return self._ph

    @property
    def idx(self) -> int:
        """Integer placeholder 'idx' attribute."""
        return self._ph.idx

    @property
    def type(self) -> PP_PLACEHOLDER:
        """Placeholder type.

        A member of the :ref:`PpPlaceholderType` enumeration, e.g. PP_PLACEHOLDER.CHART
        """
        return self._ph.type
