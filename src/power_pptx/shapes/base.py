"""Base shape-related objects such as BaseShape."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from power_pptx.action import ActionSetting
from power_pptx.dml.effect import (
    BlurFormat,
    GlowFormat,
    InnerShadowFormat,
    PresetShadowFormat,
    ReflectionFormat,
    ShadowFormat,
    SoftEdgeFormat,
)
from power_pptx.dml.three_d import ThreeDFormat
from power_pptx.shared import ElementProxy
from power_pptx.util import _coerce_emu, lazyproperty

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
        self._element.cy = _coerce_emu(value)

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
        self._element.x = _coerce_emu(value)

    @property
    def name(self) -> str:
        """Name of this shape, e.g. 'Picture 7'."""
        return self._element.shape_name

    @name.setter
    def name(self, value: str):
        self._element._nvXxPr.cNvPr.name = value  # pyright: ignore[reportPrivateUsage]

    @property
    def alt_text(self) -> str:
        """Accessibility description (alt text) for this shape.

        Read/write ``str``.  Maps to the ``descr`` attribute of the
        shape's ``<p:cNvPr>`` element — the OOXML-sanctioned alt-text
        slot that screen readers announce and that PowerPoint surfaces
        in its *Alt Text* pane.  Reading returns ``""`` when no
        description has been set.

        Example::

            picture.alt_text = "Bar chart of Q3 revenue by region."

        Assigning ``""`` (or ``None``) clears the description.
        """
        cNvPr = self._element._nvXxPr.cNvPr  # pyright: ignore[reportPrivateUsage]
        return cNvPr.get("descr") or ""

    @alt_text.setter
    def alt_text(self, value: str | None):
        cNvPr = self._element._nvXxPr.cNvPr  # pyright: ignore[reportPrivateUsage]
        if value is None or value == "":
            if "descr" in cNvPr.attrib:
                del cNvPr.attrib["descr"]
            return
        if not isinstance(value, str):
            raise TypeError(f"alt_text must be a string or None; got {type(value).__name__}")
        cNvPr.set("descr", value)

    @property
    def title_text(self) -> str:
        """Accessibility title for this shape.

        Read/write ``str``.  Maps to the ``title`` attribute of the
        shape's ``<p:cNvPr>`` element — a short one-line label that
        complements the longer :attr:`alt_text` description.  Reading
        returns ``""`` when no title has been set; assigning ``""`` (or
        ``None``) clears it.
        """
        cNvPr = self._element._nvXxPr.cNvPr  # pyright: ignore[reportPrivateUsage]
        return cNvPr.get("title") or ""

    @title_text.setter
    def title_text(self, value: str | None):
        cNvPr = self._element._nvXxPr.cNvPr  # pyright: ignore[reportPrivateUsage]
        if value is None or value == "":
            if "title" in cNvPr.attrib:
                del cNvPr.attrib["title"]
            return
        if not isinstance(value, str):
            raise TypeError(f"title_text must be a string or None; got {type(value).__name__}")
        cNvPr.set("title", value)

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
    def shadow(self) -> ShadowFormat | None:
        """|ShadowFormat| object providing access to shadow for this shape.

        For ordinary shapes (autoshapes, pictures, group shapes, connectors)
        a |ShadowFormat| facade is always returned, even when no shadow is
        explicitly defined — its individual properties return ``None`` in
        that case.

        :class:`~power_pptx.shapes.graphfrm.GraphicFrame` returns ``None``
        instead of a facade: charts and tables expose effects at
        content-specific locations that the unified |ShadowFormat| API
        doesn't apply to.  Callers that probe ``shape.shadow`` across every
        shape on a slide should branch on ``if shape.shadow is None`` to
        skip GraphicFrames cleanly.
        """
        return ShadowFormat(self._element.spPr)

    @lazyproperty
    def inner_shadow(self) -> InnerShadowFormat:
        """|InnerShadowFormat| object providing access to the inner-shadow effect.

        An |InnerShadowFormat| facade is always returned, even when no inner
        shadow is explicitly defined — its individual properties
        (``blur_radius``, ``distance``, ``direction``, ``color``) return
        ``None`` in that case.
        """
        return InnerShadowFormat(self._element.spPr)

    @lazyproperty
    def preset_shadow(self) -> PresetShadowFormat:
        """|PresetShadowFormat| object providing access to the preset-shadow effect.

        A |PresetShadowFormat| facade is always returned, even when no preset
        shadow is explicitly defined — ``preset`` returns ``None`` in that
        case.  Assign ``preset_shadow.preset`` an :class:`MSO_PRESET_SHADOW`
        member or a ``"shdw1".."shdw20"`` string to apply one.
        """
        return PresetShadowFormat(self._element.spPr)

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
        if not isinstance(value, str):
            raise ValueError("lint_group must be a string, an empty string, or None")
        # Empty string is the explicit "no group" sentinel — overrides
        # any implicit name-prefix group the linter would otherwise
        # infer from a dotted shape name.  Persist it verbatim rather
        # than clearing so the override round-trips.
        _write_lint_group(cNvPr, value)

    def animate(
        self,
        *,
        entry: str | None = None,
        exit: str | None = None,
        emphasis: str | None = None,
        trigger: str = "on_click",
        delay_ms: int = 0,
        duration_ms: int = 500,
        direction: str | None = None,
    ) -> None:
        """Add a constrained-subset animation to this shape.

        A small façade over the full :mod:`power_pptx.animation` API for
        the five most common cases. Heavy animation use is rarely
        appropriate in a professional deck, so the surface is
        deliberately narrow:

        Pass exactly one of ``entry``, ``exit``, or ``emphasis``.
        Recognised presets:

        * ``entry``: ``"fade"``, ``"appear"``, ``"fly_in"``,
          ``"float_in"``, ``"wipe"``, ``"zoom"``, ``"wheel"``,
          ``"random_bars"``.
        * ``exit``: ``"fade"``, ``"disappear"``, ``"fly_out"``,
          ``"float_out"``, ``"wipe"``, ``"zoom"``, ``"wheel"``,
          ``"random_bars"``.
        * ``emphasis``: ``"pulse"``, ``"spin"``, ``"teeter"``.

        ``trigger`` is one of ``"on_click"``, ``"with_previous"``,
        ``"after_previous"``. ``delay_ms`` and ``duration_ms`` are
        OOXML milliseconds. ``direction`` is consumed by ``fly_in`` /
        ``fly_out`` / ``wipe`` (``"left"``, ``"right"``, ``"top"``,
        ``"bottom"``); ignored otherwise.

        For animation types not covered here, drop down to
        :class:`power_pptx.animation.Entrance` /
        :class:`~power_pptx.animation.Exit` /
        :class:`~power_pptx.animation.Emphasis` directly.
        """
        kinds_set = sum(1 for v in (entry, exit, emphasis) if v is not None)
        if kinds_set != 1:
            raise ValueError(
                "Pass exactly one of entry=, exit=, emphasis=; "
                f"got entry={entry!r}, exit={exit!r}, emphasis={emphasis!r}"
            )

        from power_pptx.animation import Emphasis, Entrance, Exit
        from power_pptx.enum.animation import PP_ANIM_TRIGGER

        try:
            slide = self.part.slide  # type: ignore[attr-defined]
        except AttributeError as exc:
            raise ValueError(
                "shape.animate() requires the shape to be on a slide"
            ) from exc

        trigger_map = {
            "on_click": PP_ANIM_TRIGGER.ON_CLICK,
            "with_previous": PP_ANIM_TRIGGER.WITH_PREVIOUS,
            "after_previous": PP_ANIM_TRIGGER.AFTER_PREVIOUS,
        }
        if trigger not in trigger_map:
            raise ValueError(
                f"trigger must be one of {sorted(trigger_map)}; got {trigger!r}"
            )
        trig = trigger_map[trigger]

        common_kwargs = {"trigger": trig, "delay": int(delay_ms)}

        def _call(facade_method, preset, *, supports_direction=False):
            kwargs = dict(common_kwargs)
            if preset != "appear" and preset != "disappear":
                kwargs["duration"] = int(duration_ms)
            if supports_direction and direction is not None:
                kwargs["direction"] = direction
            facade_method(slide, self, **kwargs)

        if entry is not None:
            preset = entry
            method = getattr(Entrance, preset, None)
            if method is None:
                raise ValueError(f"unknown entry preset: {preset!r}")
            _call(method, preset, supports_direction=preset in ("fly_in", "wipe"))
        elif exit is not None:
            preset = exit
            method = getattr(Exit, preset, None)
            if method is None:
                raise ValueError(f"unknown exit preset: {preset!r}")
            _call(method, preset, supports_direction=preset in ("fly_out", "wipe"))
        else:  # emphasis
            preset = emphasis  # type: ignore[assignment]
            method = getattr(Emphasis, preset, None)
            if method is None:
                raise ValueError(f"unknown emphasis preset: {preset!r}")
            _call(method, preset)

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
        # Validate each code: must be a non-empty trimmed string with no
        # commas (the on-disk form is comma-joined, so a comma in a code
        # would corrupt the round-trip).  Trim whitespace so callers
        # don't have to be precious about formatting.
        codes: set[str] = set()
        for raw in value:
            if not isinstance(raw, str):
                raise TypeError(
                    "lint_skip codes must be strings; got "
                    f"{type(raw).__name__}"
                )
            code = raw.strip()
            if not code:
                raise ValueError("lint_skip codes must be non-empty strings")
            if "," in code:
                raise ValueError(
                    f"lint_skip code {raw!r} contains ',', which is reserved "
                    "as the on-disk separator"
                )
            codes.add(code)
        cNvPr = self._element._nvXxPr.cNvPr  # pyright: ignore[reportPrivateUsage]
        _write_lint_skip(cNvPr, frozenset(codes))

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
        self._element.y = _coerce_emu(value)

    @property
    def width(self) -> Length:
        """Distance between left and right extents of this shape.

        Read/write. Expressed in English Metric Units (EMU).
        """
        return self._element.cx

    @width.setter
    def width(self, value: Length):
        self._element.cx = _coerce_emu(value)

    @property
    def bbox(self):
        """Return the shape's geometry as an immutable :class:`BBox`.

        ``shape.bbox`` is a snapshot — mutating the shape afterwards
        does not update the box.  Use :meth:`BBox.apply_to` to push a
        new box back onto the shape.

        Example::

            from power_pptx import BBox

            inner = shape.bbox.inset(all=Inches(0.2))
            slide.shapes.add_textbox(*inner)
        """
        from power_pptx.geometry import BBox

        return BBox.from_shape(self)

    def fill_hex(self, hex_color: "str | None") -> "BaseShape":
        """Set a solid fill from a hex string (``"#RRGGBB"`` or ``"RRGGBB"``).

        Convenience for the three-line ``shape.fill.solid();
        shape.fill.fore_color.rgb = RGBColor(...)`` dance.  Returns
        ``self`` so calls can be chained.

        Example::

            slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *box).fill_hex("#0B5CFF")

        Pass ``None`` to clear the fill (the shape inherits from its
        theme afterwards).  Hex strings, ``RGBColor`` instances, and
        ``(r, g, b)`` tuples are all accepted.
        """
        from power_pptx._color import coerce_color

        if hex_color is None:
            # ``fill.background()`` produces a transparent (no-fill)
            # solid; the closest thing to "clear" without ripping the
            # element out wholesale.
            try:
                self.fill.background()  # type: ignore[attr-defined]
            except AttributeError as exc:
                raise AttributeError(
                    f"{type(self).__name__} does not support fill"
                ) from exc
            return self
        try:
            fill = self.fill  # type: ignore[attr-defined]
        except AttributeError as exc:
            raise AttributeError(
                f"{type(self).__name__} does not support fill"
            ) from exc
        fill.solid()
        fill.fore_color.rgb = coerce_color(hex_color)
        return self

    def line_hex(
        self,
        hex_color: "str | None",
        *,
        weight_pt: float | None = None,
    ) -> "BaseShape":
        """Set the line stroke from a hex string (``"#RRGGBB"``).

        Optional ``weight_pt`` sets the stroke width in points.  Returns
        ``self`` so calls can be chained.

        Example::

            slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *box).line_hex(
                "#0D0D0D", weight_pt=1.25,
            )
        """
        from power_pptx._color import coerce_color
        from power_pptx.util import Pt

        try:
            line = self.line  # type: ignore[attr-defined]
        except AttributeError as exc:
            raise AttributeError(
                f"{type(self).__name__} does not support line"
            ) from exc
        if hex_color is None:
            line.fill.background()
        else:
            line.color.rgb = coerce_color(hex_color)
        if weight_pt is not None:
            line.width = Pt(float(weight_pt))
        return self

    def set_text_preserving_format(self, new_text: str) -> "BaseShape":
        """Replace all text in this shape with ``new_text``, keeping run formatting.

        Captures the first run's character properties (``<a:rPr>``) and
        the first paragraph's properties (``<a:pPr>``), rebuilds the
        text body to hold ``new_text`` (one paragraph per ``\\n``), then
        re-applies those properties to every new run and paragraph.

        Font face / size / colour / bold / italic on that first run are
        preserved verbatim — useful when overwriting a templated
        placeholder (e.g. ``"<TITLE>"``) without losing the designer's
        font choices.

        Example::

            shape.set_text_preserving_format("Q4 revenue overview")

        Raises :class:`ValueError` if the shape has no text frame.
        """
        if not getattr(self, "has_text_frame", False):
            raise ValueError(
                f"shape {self.name!r} has no text frame; can't replace text"
            )
        tf = self.text_frame  # type: ignore[attr-defined]

        from copy import deepcopy

        rPr_template = None
        pPr_template = None
        first_para = tf.paragraphs[0] if tf.paragraphs else None
        if first_para is not None:
            pPr = first_para._p.pPr  # type: ignore[attr-defined]
            if pPr is not None:
                pPr_template = deepcopy(pPr)
            if first_para.runs:
                rPr = first_para.runs[0]._r.rPr  # type: ignore[attr-defined]
                if rPr is not None:
                    rPr_template = deepcopy(rPr)

        # Rebuild the body using the high-level text setter; this gives
        # us one paragraph per "\n" with a single run per paragraph.
        tf.text = new_text if new_text else ""

        for para in tf.paragraphs:
            p_elm = para._p  # type: ignore[attr-defined]
            if pPr_template is not None:
                existing_pPr = p_elm.pPr
                if existing_pPr is not None:
                    p_elm._remove_pPr()
                p_elm._insert_pPr(deepcopy(pPr_template))
            if rPr_template is not None:
                for run in para.runs:
                    r_elm = run._r  # type: ignore[attr-defined]
                    if r_elm.rPr is not None:
                        r_elm._remove_rPr()
                    r_elm._insert_rPr(deepcopy(rPr_template))
        return self


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
