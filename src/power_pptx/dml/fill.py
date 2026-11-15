"""DrawingML objects related to fill."""

from __future__ import annotations

import copy
import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from power_pptx.dml.color import ColorFormat, RGBColor
from power_pptx.enum.dml import MSO_FILL, MSO_THEME_COLOR
from power_pptx.oxml.dml.fill import (
    CT_BlipFillProperties,
    CT_GradientFillProperties,
    CT_GroupFillProperties,
    CT_NoFillProperties,
    CT_PatternFillProperties,
    CT_SolidColorFillProperties,
)
from power_pptx.oxml.xmlchemy import BaseOxmlElement
from power_pptx.shared import ElementProxy
from power_pptx.util import lazyproperty

if TYPE_CHECKING:
    from power_pptx.enum.dml import MSO_FILL_TYPE
    from power_pptx.oxml.xmlchemy import BaseOxmlElement


def _validated_angle(angle: Any) -> float:
    """Return `angle` as a finite float number of degrees, or raise.

    Raises |TypeError| / |ValueError| the way ``float()`` does for something
    that is not a number, and |ValueError| for NaN or infinity.
    """
    degrees = float(angle)
    if not math.isfinite(degrees):
        raise ValueError("gradient angle must be a finite number of degrees, got %r" % (angle,))
    return degrees


def _validated_stop_position(position: Any) -> float:
    """Return `position` as a float in ``[0.0, 1.0]``, or raise |ValueError|.

    The comparison is written so that NaN, which compares false to
    everything, is rejected along with out-of-range values.
    """
    value = float(position)
    if not 0.0 <= value <= 1.0:
        raise ValueError("gradient stop position must be in range 0.0 to 1.0, got %r" % (position,))
    return value


def _looks_like_color_value(value: Any) -> bool:
    """True when *value* is plausibly a single colour rather than a stop list."""
    if isinstance(value, (str, RGBColor)):
        return True
    # 3-tuple of ints is an RGB triple, not a (color, position) pair.
    return isinstance(value, tuple) and len(value) == 3 and all(isinstance(v, int) for v in value)


def _normalize_stop_input(stops: Any):
    """Yield ``(color, position)`` tuples from a flexible stops sequence.

    Accepts:

    * iterable of ``(color, position)`` 2-tuples (positions are taken
      verbatim).
    * iterable of bare colours (positions are spread evenly across
      ``[0.0, 1.0]``).
    """
    seq = list(stops)
    if not seq:
        return
    # Decide whether items are (color, position) pairs or bare colours.
    pair_form = all(
        isinstance(item, tuple)
        and len(item) == 2
        and isinstance(item[1], (int, float))
        and not (isinstance(item, tuple) and all(isinstance(v, int) for v in item))
        for item in seq
    )
    # Special-case: an RGB 3-tuple of ints would otherwise be confused
    # with (color, position).  Treat any item that's a 3-int-tuple as a
    # bare RGB triple regardless.
    if any(
        isinstance(item, tuple) and len(item) == 3 and all(isinstance(v, int) for v in item)
        for item in seq
    ):
        pair_form = False
    if pair_form:
        for color, position in seq:
            yield color, float(position)
    else:
        n = len(seq)
        if n == 1:
            yield seq[0], 0.0
            return
        for i, color in enumerate(seq):
            yield color, i / (n - 1)


class FillFormat(object):
    """Provides access to the current fill properties.

    Also provides methods to change the fill type.
    """

    def __init__(self, eg_fill_properties_parent: BaseOxmlElement, fill_obj: _Fill):
        super(FillFormat, self).__init__()
        self._xPr = eg_fill_properties_parent
        self._fill = fill_obj

    @classmethod
    def from_fill_parent(cls, eg_fillProperties_parent: BaseOxmlElement) -> FillFormat:
        """
        Return a |FillFormat| instance initialized to the settings contained
        in *eg_fillProperties_parent*, which must be an element having
        EG_FillProperties in its child element sequence in the XML schema.
        """
        fill_elm = eg_fillProperties_parent.eg_fillProperties
        fill = _Fill(fill_elm)
        fill_format = cls(eg_fillProperties_parent, fill)
        return fill_format

    @property
    def back_color(self):
        """Return a |ColorFormat| object representing background color.

        This property is only applicable to pattern fills and lines.
        """
        return self._fill.back_color

    def background(self):
        """
        Sets the fill type to noFill, i.e. transparent.
        """
        noFill = self._xPr.get_or_change_to_noFill()
        self._fill = _NoFill(noFill)

    @property
    def fore_color(self):
        """
        Return a |ColorFormat| instance representing the foreground color of
        this fill.
        """
        return self._fill.fore_color

    _GRADIENT_KINDS = ("linear", "radial", "rectangular", "shape")

    def gradient(self, kind: str = "linear", *, angle: float | None = None):
        """Sets the fill type to gradient.

        If the fill is not already a gradient, a default gradient is added.
        The default gradient corresponds to the default in the built-in
        PowerPoint "White" template. This gradient is linear at angle
        90-degrees (upward), with two stops. The first stop is Accent-1 with
        tint 100%, shade 100%, and satMod 130%. The second stop is Accent-1
        with tint 50%, shade 100%, and satMod 350%.

        `kind` selects the gradient shape:

        * ``"linear"`` (default) — straight-line gradient parameterized by
          angle (the historical behavior).
        * ``"radial"`` — circular gradient (`<a:path path="circle"/>`).
        * ``"rectangular"`` — rectangular gradient (`<a:path path="rect"/>`).
        * ``"shape"`` — gradient that follows the bounding shape of its
          container (`<a:path path="shape"/>`).

        When called on an existing gradient with a different kind, the
        gradient stops are preserved; only the path/lin shading element is
        swapped out. Invalid `kind` values raise ``ValueError`` *before*
        any fill mutation, leaving the existing fill untouched.

        The optional ``angle`` keyword sets ``gradient_angle`` after the
        fill has been initialized — symmetric with
        :meth:`linear_gradient`'s ``angle=`` parameter, and measured the
        same way (counter-clockwise; see :attr:`gradient_angle`).  Only
        meaningful for ``kind="linear"``; passing it with a non-linear
        ``kind`` is a :class:`ValueError`.
        """
        if kind not in self._GRADIENT_KINDS:
            raise ValueError(
                "gradient kind must be one of %r; got %r" % (self._GRADIENT_KINDS, kind)
            )
        if angle is not None and kind != "linear":
            raise ValueError("angle= is only valid for kind='linear'; got kind=%r" % kind)
        if angle is not None:
            angle = _validated_angle(angle)
        gradFill = self._xPr.get_or_change_to_gradFill()
        if kind != "linear":
            gradFill.change_to_kind(kind)
        elif gradFill.path is not None:
            # convert an existing radial/rectangular/shape gradient back to linear
            gradFill.change_to_kind("linear")
        self._fill = _GradFill(gradFill)
        if angle is not None:
            self.gradient_angle = angle

    @property
    def gradient_angle(self):
        """Angle in float degrees of line of a linear gradient.

        Read/Write. May be |None|, indicating the angle should be inherited
        from the style hierarchy.

        The angle is measured **counter-clockwise** from the direction
        pointing right, as angles are in trigonometry, and names the
        direction in which the gradient runs from its first stop to its
        last::

              0    →   left-to-right   (first stop on the left)
              90   →   bottom-to-top   (first stop at the bottom)
              180  →   right-to-left   (first stop on the right)
              270  →   top-to-bottom   (first stop at the top)

        This is the opposite sense to the ``ang`` attribute stored in the
        XML, which counts clockwise: ``gradient_angle = 90`` is written as
        ``ang="16200000"`` (270 degrees) and ``gradient_angle = 270`` as
        ``ang="5400000"`` (90 degrees). For a gradient that runs down the
        shape use ``270`` (or ``-90``).

        Raises |TypeError| when the fill type is not
        MSO_FILL_TYPE.GRADIENT. Raises |ValueError| for a non-linear
        gradient (e.g. a radial gradient).
        """
        if self.type != MSO_FILL.GRADIENT:
            raise TypeError("Fill is not of type MSO_FILL_TYPE.GRADIENT")
        return self._fill.gradient_angle

    @gradient_angle.setter
    def gradient_angle(self, value):
        if self.type != MSO_FILL.GRADIENT:
            raise TypeError("Fill is not of type MSO_FILL_TYPE.GRADIENT")
        self._fill.gradient_angle = value

    def linear_gradient(
        self,
        stops,
        end=None,
        *,
        angle: float = 0.0,
    ) -> None:
        """Apply a linear gradient with two-or-more colour stops in one call.

        Two equivalent input shapes are accepted:

        * ``fill.linear_gradient("#06D6FE", "#B14AED", angle=90)`` —
          two-stop short form: pass *start* as ``stops`` and *end* as
          *end*; the stops are placed at positions ``0.0`` and ``1.0``.
        * ``fill.linear_gradient([("#06D6FE", 0.0), ("#FFFFFF", 0.5),
          ("#B14AED", 1.0)], angle=45)`` — explicit list of
          ``(color, position)`` pairs (or just colors, in which case
          positions are spread evenly across ``[0.0, 1.0]``).

        *angle* is measured counter-clockwise, as :attr:`gradient_angle`
        is: ``0`` runs left-to-right, ``90`` bottom-to-top, ``180``
        right-to-left and ``270`` top-to-bottom, the first stop being where
        the gradient starts.  So ``linear_gradient(a, b, angle=270)`` puts
        *a* at the top and *b* at the bottom, and ``angle=90`` the reverse.

        Each colour may be an :class:`~power_pptx.dml.color.RGBColor`,
        a 6-digit hex string (with or without leading ``#``), or a
        3-tuple of ints.  3-digit hex shorthand (``"#FFF"``) is **not**
        accepted — write the full 6-digit form.

        This is a convenience wrapper over the lower-level
        :meth:`gradient` + :attr:`gradient_stops` API; reach for that
        for fine-grained stop manipulation.

        Every stop and the angle are checked before the fill is changed, so
        a call that raises leaves the existing fill as it was.
        """
        if end is not None:
            # Two-positional-argument form.
            pairs: list[tuple[Any, float]] = [(stops, 0.0), (end, 1.0)]
        elif _looks_like_color_value(stops):
            raise TypeError(
                "linear_gradient takes a list of stops or two positional "
                "colors (start, end); got a single colour. Pass an end colour."
            )
        else:
            pairs = list(_normalize_stop_input(stops))

        if len(pairs) < 2:
            raise ValueError("linear_gradient requires at least two stops")

        # Settle every value before the fill is touched: `gradient()` below
        # replaces whatever fill the shape had, which a bad stop or angle must
        # not be allowed to do.  ``replace`` expects ``(position, color)``
        # while we built ``(color, position)`` to match the public API; flip
        # the tuples here.
        angle = _validated_angle(angle)
        entries = [
            (
                _validated_stop_position(position),
                None if color is None else _GradientStops._coerce_rgb(color),
            )
            for color, position in pairs
        ]

        self.gradient("linear")
        self.gradient_stops.replace(entries)
        self.gradient_angle = angle

    @property
    def gradient_kind(self):
        """One of ``"linear" | "radial" | "rectangular" | "shape" | None``.

        Raises |TypeError| when fill is not gradient (call `fill.gradient()`
        first). Returns |None| when the gradient inherits its shading
        element from the style hierarchy.
        """
        if self.type != MSO_FILL.GRADIENT:
            raise TypeError("Fill is not of type MSO_FILL_TYPE.GRADIENT")
        return self._fill.gradient_kind

    @property
    def gradient_stops(self):
        """|GradientStops| object providing access to stops of this gradient.

        Raises |TypeError| when fill is not gradient (call `fill.gradient()`
        first). Each stop represents a color between which the gradient
        smoothly transitions.
        """
        if self.type != MSO_FILL.GRADIENT:
            raise TypeError("Fill is not of type MSO_FILL_TYPE.GRADIENT")
        return self._fill.gradient_stops

    @property
    def pattern(self):
        """Return member of :ref:`MsoPatternType` indicating fill pattern.

        Raises |TypeError| when fill is not patterned (call
        `fill.patterned()` first). Returns |None| if no pattern has been set;
        PowerPoint may display the default `PERCENT_5` pattern in this case.
        Assigning |None| will remove any explicit pattern setting, although
        relying on the default behavior is discouraged and may produce
        rendering differences across client applications.
        """
        return self._fill.pattern

    @pattern.setter
    def pattern(self, pattern_type):
        self._fill.pattern = pattern_type

    def patterned(self):
        """Selects the pattern fill type.

        Note that calling this method does not by itself set a foreground or
        background color of the pattern. Rather it enables subsequent
        assignments to properties like fore_color to set the pattern and
        colors.
        """
        pattFill = self._xPr.get_or_change_to_pattFill()
        self._fill = _PattFill(pattFill)

    def solid(self):
        """
        Sets the fill type to solid, i.e. a solid color. Note that calling
        this method does not set a color or by itself cause the shape to
        appear with a solid color fill; rather it enables subsequent
        assignments to properties like fore_color to set the color.
        """
        solidFill = self._xPr.get_or_change_to_solidFill()
        self._fill = _SolidFill(solidFill)

    @property
    def type(self) -> MSO_FILL_TYPE:
        """The type of this fill, e.g. `MSO_FILL_TYPE.SOLID`."""
        return self._fill.type


class _Fill(object):
    """
    Object factory for fill object of class matching fill element, such as
    _SolidFill for ``<a:solidFill>``; also serves as the base class for all
    fill classes
    """

    def __new__(cls, xFill):
        if xFill is None:
            fill_cls = _NoneFill
        elif isinstance(xFill, CT_BlipFillProperties):
            fill_cls = _BlipFill
        elif isinstance(xFill, CT_GradientFillProperties):
            fill_cls = _GradFill
        elif isinstance(xFill, CT_GroupFillProperties):
            fill_cls = _GrpFill
        elif isinstance(xFill, CT_NoFillProperties):
            fill_cls = _NoFill
        elif isinstance(xFill, CT_PatternFillProperties):
            fill_cls = _PattFill
        elif isinstance(xFill, CT_SolidColorFillProperties):
            fill_cls = _SolidFill
        else:
            fill_cls = _Fill
        return super(_Fill, cls).__new__(fill_cls)

    @property
    def back_color(self):
        """Raise TypeError for types that do not override this property."""
        tmpl = "fill type %s has no background color, call .patterned() first"
        raise TypeError(tmpl % self.__class__.__name__)

    @property
    def fore_color(self):
        """Raise TypeError for types that do not override this property."""
        tmpl = "fill type %s has no foreground color, call .solid() or .patterned() first"
        raise TypeError(tmpl % self.__class__.__name__)

    @property
    def pattern(self):
        """Raise TypeError for fills that do not override this property."""
        tmpl = "fill type %s has no pattern, call .patterned() first"
        raise TypeError(tmpl % self.__class__.__name__)

    @property
    def type(self) -> MSO_FILL_TYPE:  # pragma: no cover
        raise NotImplementedError(
            f".type property must be implemented on {self.__class__.__name__}"
        )


class _BlipFill(_Fill):
    @property
    def type(self):
        return MSO_FILL.PICTURE


class _GradFill(_Fill):
    """Proxies an `a:gradFill` element."""

    _PATH_KINDS = {"circle": "radial", "rect": "rectangular", "shape": "shape"}

    def __init__(self, gradFill):
        self._element = self._gradFill = gradFill

    @property
    def gradient_kind(self):
        """One of ``"linear" | "radial" | "rectangular" | "shape" | None``.

        Returns ``None`` when the gradient inherits its shading element from
        the style hierarchy (no `<a:lin>` or `<a:path>` child is present).
        """
        path = self._gradFill.path
        if path is not None:
            return self._PATH_KINDS.get(path.path)
        if self._gradFill.lin is not None:
            return "linear"
        return None

    @property
    def gradient_angle(self):
        """Angle in float degrees of line of a linear gradient.

        Read/Write. May be |None|, indicating the angle is inherited from the
        style hierarchy. An angle of 0.0 corresponds to a left-to-right
        gradient. Increasing angles represent counter-clockwise rotation of
        the line, for example 90.0 represents a bottom-to-top gradient and
        270.0 a top-to-bottom one. Raises |TypeError| when the fill type is
        not MSO_FILL_TYPE.GRADIENT. Raises |ValueError| for a non-linear
        gradient (e.g. a radial gradient).
        """
        # ---case 1: gradient path is explicit, but not linear---
        path = self._gradFill.path
        if path is not None:
            raise ValueError("not a linear gradient")

        # ---case 2: gradient path is inherited (no a:lin OR a:path)---
        lin = self._gradFill.lin
        if lin is None:
            return None

        # ---case 3: gradient path is explicitly linear---
        # The angle is stored in XML as a clockwise angle (y grows downward,
        # so 90 degrees points down the shape). The API has always reported
        # the counter-clockwise angle from horizontal-pointing-right, the
        # trigonometric convention, and existing decks depend on that, so
        # the two are converted here. An `a:lin` without an `ang` attribute
        # (e.g. the default `<a:lin scaled="0"/>` gradient) renders at the
        # effective angle 0.
        clockwise_angle = lin.ang
        if clockwise_angle is None or clockwise_angle == 0.0:
            return 0.0
        return 360.0 - clockwise_angle

    @gradient_angle.setter
    def gradient_angle(self, value):
        lin = self._gradFill.lin
        if lin is None:
            raise ValueError("not a linear gradient")
        lin.ang = 360.0 - value

    @lazyproperty
    def gradient_stops(self):
        """|_GradientStops| object providing access to gradient colors.

        Each stop represents a color between which the gradient smoothly
        transitions.
        """
        return _GradientStops(self._gradFill.get_or_add_gsLst())

    @property
    def type(self):
        return MSO_FILL.GRADIENT


class _GrpFill(_Fill):
    @property
    def type(self):
        return MSO_FILL.GROUP


class _NoFill(_Fill):
    @property
    def type(self):
        return MSO_FILL.BACKGROUND


class _NoneFill(_Fill):
    @property
    def type(self):
        return None


class _PattFill(_Fill):
    """Provides access to patterned fill properties."""

    def __init__(self, pattFill):
        super(_PattFill, self).__init__()
        self._element = self._pattFill = pattFill

    @lazyproperty
    def back_color(self):
        """Return |ColorFormat| object that controls background color."""
        bgClr = self._pattFill.get_or_add_bgClr()
        return ColorFormat.from_colorchoice_parent(bgClr)

    @lazyproperty
    def fore_color(self):
        """Return |ColorFormat| object that controls foreground color."""
        fgClr = self._pattFill.get_or_add_fgClr()
        return ColorFormat.from_colorchoice_parent(fgClr)

    @property
    def pattern(self):
        """Return member of :ref:`MsoPatternType` indicating fill pattern.

        Returns |None| if no pattern has been set; PowerPoint may display the
        default `PERCENT_5` pattern in this case. Assigning |None| will
        remove any explicit pattern setting.
        """
        return self._pattFill.prst

    @pattern.setter
    def pattern(self, pattern_type):
        self._pattFill.prst = pattern_type

    @property
    def type(self):
        return MSO_FILL.PATTERNED


class _SolidFill(_Fill):
    """Provides access to fill properties such as color for solid fills."""

    def __init__(self, solidFill):
        super(_SolidFill, self).__init__()
        self._solidFill = solidFill

    @lazyproperty
    def fore_color(self):
        """Return |ColorFormat| object controlling fill color."""
        return ColorFormat.from_colorchoice_parent(self._solidFill)

    @property
    def type(self):
        return MSO_FILL.SOLID


class _GradientStops(Sequence):
    """Collection of |GradientStop| objects defining gradient colors.

    A gradient must have a minimum of two stops, but can have as many more
    than that as required to achieve the desired effect (three is perhaps
    most common). Stops are sequenced in the order they are transitioned
    through.

    The collection is mutable: stops can be added with :meth:`append`,
    removed with ``del stops[i]``, and the entire stop sequence can be
    swapped out with :meth:`replace`. The OOXML schema requires at least
    two `<a:gs>` children, so :meth:`__delitem__` raises when removing a
    stop would leave fewer than two.
    """

    _MIN_STOP_COUNT = 2

    def __init__(self, gsLst):
        self._gsLst = gsLst

    def __delitem__(self, idx):
        gs_children = self._gs_children
        if len(gs_children) - 1 < self._MIN_STOP_COUNT:
            raise ValueError(
                "a gradient must have at least %d stops; cannot delete" % self._MIN_STOP_COUNT
            )
        target = gs_children[idx]
        self._gsLst.remove(target)

    def __getitem__(self, idx):
        return _GradientStop(self._gs_children[idx])

    def __len__(self):
        return len(self._gs_children)

    def append(self, position, color=None):
        """Append a new stop at `position` with `color`.

        `position` is a float in ``[0.0, 1.0]``. `color` may be:

        * |None| (default): a placeholder ``schemeClr accent1`` color is
          written; mutate ``returned_stop.color`` to refine it.
        * an :class:`~power_pptx.dml.color.RGBColor` instance.
        * a 3-tuple of integers in ``[0, 255]``.
        * a hex string like ``"3C2F80"`` (with or without leading ``#``).

        Returns the newly-added :class:`_GradientStop`. Raises, without
        adding anything, when `position` is out of range or `color` is not
        a colour.
        """
        # -- settle both values first: an `<a:gs>` created and then abandoned
        # -- has neither its required `pos` nor its required colour
        position = _validated_stop_position(position)
        rgb = None if color is None else self._coerce_rgb(color)
        gs = self._gsLst._add_gs()
        gs.pos = position
        stop = _GradientStop(gs)
        if rgb is None:
            # Default placeholder color so the emitted `<a:gs>` is valid OOXML
            # (the schema requires a color choice child). Callers can mutate
            # the returned stop's `.color` afterwards.
            stop.color.theme_color = MSO_THEME_COLOR.ACCENT_1
        else:
            stop.color.rgb = rgb
        return stop

    def replace(self, stops):
        """Replace all stops with the entries in `stops`.

        Each entry is either a 2-tuple ``(position, color)`` (where `color`
        follows the same rules as :meth:`append`) or an existing
        :class:`_GradientStop` — including stops whose color is a theme,
        scheme, system, or preset color. Existing-stop entries are deep-
        copied as-is so non-RGB color choices round-trip without loss.

        The new sequence must contain at least 2 entries. The replacement
        is atomic: if any entry is invalid — a malformed tuple, a position
        outside ``[0.0, 1.0]``, something that is not a colour — the
        existing stops are left untouched.
        """
        stops = list(stops)
        if len(stops) < self._MIN_STOP_COUNT:
            raise ValueError("a gradient must have at least %d stops" % self._MIN_STOP_COUNT)

        # Pre-validate every entry so a failure (bad color, malformed tuple,
        # out-of-range position) raises *before* we touch the existing stops.
        validated = []
        for entry in stops:
            if isinstance(entry, _GradientStop):
                validated.append(("copy", entry._gs))
                continue
            try:
                position, color = entry
            except (TypeError, ValueError) as e:
                raise TypeError(
                    "replace() entries must be (position, color) tuples or "
                    "_GradientStop instances; got %r" % (entry,)
                ) from e
            position = _validated_stop_position(position)
            if color is not None:
                color = self._coerce_rgb(color)
            validated.append(("new", position, color))

        # Mutate only after all entries are validated.
        for gs in self._gs_children:
            self._gsLst.remove(gs)
        for entry in validated:
            if entry[0] == "copy":
                self._gsLst.append(copy.deepcopy(entry[1]))
            else:
                _, position, color = entry
                self.append(position, color)

    @property
    def _gs_children(self):
        return list(self._gsLst.gs_lst)

    @staticmethod
    def _coerce_rgb(color):
        """Return `color` as an |RGBColor|, by the rules every colour setter uses.

        Raises |ValueError| for a malformed colour (a hex string that is not
        six digits, a channel outside 0-255) and |TypeError| for something
        that is not a colour at all.
        """
        from power_pptx._color import coerce_color

        return coerce_color(color)


class _GradientStop(ElementProxy):
    """A single gradient stop.

    A gradient stop defines a color and a position.
    """

    def __init__(self, gs):
        super(_GradientStop, self).__init__(gs)
        self._gs = gs

    @lazyproperty
    def color(self):
        """Return |ColorFormat| object controlling stop color."""
        return ColorFormat.from_colorchoice_parent(self._gs)

    @property
    def position(self):
        """Location of stop in gradient path as float between 0.0 and 1.0.

        The value represents a percentage, where 0.0 (0%) represents the
        start of the path and 1.0 (100%) represents the end of the path. For
        a linear gradient, these would represent opposing extents of the
        filled area.
        """
        return self._gs.pos

    @position.setter
    def position(self, value):
        self._gs.pos = float(value)
