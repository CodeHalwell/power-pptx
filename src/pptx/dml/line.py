"""DrawingML objects related to line formatting."""

from __future__ import annotations

from pptx.dml.color import _LazyColorFormat
from pptx.dml.fill import FillFormat
from pptx.enum.dml import MSO_LINE_JOIN_STYLE
from pptx.oxml.ns import qn
from pptx.util import Emu, lazyproperty


_JOIN_TAG = {
    MSO_LINE_JOIN_STYLE.ROUND: "a:round",
    MSO_LINE_JOIN_STYLE.BEVEL: "a:bevel",
    MSO_LINE_JOIN_STYLE.MITER: "a:miter",
}
_JOIN_FROM_TAG = {qn(tag): join for join, tag in _JOIN_TAG.items()}


class LineEndFormat(object):
    """Provides access to one end (head or tail) of a stroked line.

    Wraps an ``<a:headEnd>`` or ``<a:tailEnd>`` element. The element is
    created lazily; assigning |None| to a property removes the corresponding
    attribute, and removing the last attribute drops the element entirely so
    inheritance is not silently broken.
    """

    def __init__(self, line_format, end_tag):
        # `end_tag` is "headEnd" or "tailEnd"
        self._line_format = line_format
        self._end_tag = end_tag

    @property
    def type(self):
        """Arrowhead type as :ref:`MsoLineEndType`, or |None| if not set."""
        end = self._end
        if end is None:
            return None
        return end.type

    @type.setter
    def type(self, value):
        self._set_attr("type", value)

    @property
    def width(self):
        """Arrowhead width as :ref:`MsoLineEndSize`, or |None| if not set."""
        end = self._end
        if end is None:
            return None
        return end.w

    @width.setter
    def width(self, value):
        self._set_attr("w", value)

    @property
    def length(self):
        """Arrowhead length as :ref:`MsoLineEndSize`, or |None| if not set."""
        end = self._end
        if end is None:
            return None
        return end.len

    @length.setter
    def length(self, value):
        self._set_attr("len", value)

    @property
    def _end(self):
        ln = self._line_format._ln
        if ln is None:
            return None
        return getattr(ln, self._end_tag)

    def _set_attr(self, attr_name, value):
        if value is None:
            end = self._end
            if end is None:
                return
            end.attrib.pop(attr_name, None)
            if not end.attrib:
                ln = self._line_format._ln
                if ln is not None:
                    getattr(ln, "_remove_%s" % self._end_tag)()
            return
        ln = self._line_format._get_or_add_ln()
        end = getattr(ln, "get_or_add_%s" % self._end_tag)()
        setattr(end, attr_name, value)


class LineFormat(object):
    """Provides access to line properties such as color, style, and width.

    A LineFormat object is typically accessed via the ``.line`` property of
    a shape such as |Shape| or |Picture|.
    """

    def __init__(self, parent):
        super(LineFormat, self).__init__()
        self._parent = parent

    @lazyproperty
    def color(self):
        """The color settings for this line; a shortcut for ``line.fill.fore_color``.

        Reads are non-mutating: when no explicit ``<a:ln>`` element exists or its
        fill is not solid, accessing color properties returns the "no explicit
        color" sentinel (preserving theme inheritance) instead of injecting line
        and fill XML. The line element and a solid fill are only created when
        ``rgb`` or ``theme_color`` is assigned.
        """
        return _LazyColorFormat(peek_fill=self._peek_fill, ensure_fill=lambda: self.fill)

    def _peek_fill(self):
        """Return |FillFormat| for the current ``<a:ln>`` element, or |None|.

        Read-only: never injects an ``<a:ln>`` element if one is not already
        present.
        """
        ln = self._ln
        if ln is None:
            return None
        return FillFormat.from_fill_parent(ln)

    @property
    def dash_style(self):
        """Return value indicating line style.

        Returns a member of :ref:`MsoLineDashStyle` indicating line style, or
        |None| if no explicit value has been set. When no explicit value has
        been set, the line dash style is inherited from the style hierarchy.

        Assigning |None| removes any existing explicitly-defined dash style.
        """
        ln = self._ln
        if ln is None:
            return None
        return ln.prstDash_val

    @dash_style.setter
    def dash_style(self, dash_style):
        if dash_style is None:
            ln = self._ln
            if ln is None:
                return
            ln._remove_prstDash()
            ln._remove_custDash()
            return
        ln = self._get_or_add_ln()
        ln.prstDash_val = dash_style

    @lazyproperty
    def fill(self):
        """
        |FillFormat| instance for this line, providing access to fill
        properties such as foreground color.
        """
        ln = self._get_or_add_ln()
        return FillFormat.from_fill_parent(ln)

    @property
    def width(self):
        """
        The width of the line expressed as an integer number of :ref:`English
        Metric Units <EMU>`. The returned value is an instance of |Length|,
        a value class having properties such as `.inches`, `.cm`, and `.pt`
        for converting the value into convenient units.
        """
        ln = self._ln
        if ln is None:
            return Emu(0)
        return ln.w

    @width.setter
    def width(self, emu):
        if emu is None:
            emu = 0
        ln = self._get_or_add_ln()
        ln.w = emu

    @property
    def cap(self):
        """End-cap style as :ref:`MsoLineCapStyle`, or |None| if unset.

        Maps to the ``cap`` attribute on ``<a:ln>``. Reads are non-mutating:
        no ``<a:ln>`` element is created if one doesn't already exist.
        """
        ln = self._ln
        if ln is None:
            return None
        return ln.cap

    @cap.setter
    def cap(self, value):
        if value is None:
            ln = self._ln
            if ln is None:
                return
            ln.cap = None
            return
        ln = self._get_or_add_ln()
        ln.cap = value

    @property
    def compound(self):
        """Compound (multi-stroke) style as :ref:`MsoLineCompoundStyle`, or |None|.

        Maps to the ``cmpd`` attribute on ``<a:ln>``.
        """
        ln = self._ln
        if ln is None:
            return None
        return ln.cmpd

    @compound.setter
    def compound(self, value):
        if value is None:
            ln = self._ln
            if ln is None:
                return
            ln.cmpd = None
            return
        ln = self._get_or_add_ln()
        ln.cmpd = value

    @property
    def join(self):
        """Corner-join style as :ref:`MsoLineJoinStyle`, or |None| if unset.

        Returns whichever of ``<a:round/>``, ``<a:bevel/>``, or ``<a:miter/>``
        is currently a child of ``<a:ln>``. Assigning |None| removes any
        existing join element; assigning a member writes the matching
        element (replacing any other join element if present).
        """
        ln = self._ln
        if ln is None:
            return None
        join_elm = ln.eg_lineJoinProperties
        if join_elm is None:
            return None
        return _JOIN_FROM_TAG.get(join_elm.tag)

    @join.setter
    def join(self, value):
        if value is None:
            ln = self._ln
            if ln is None:
                return
            ln._remove_eg_lineJoinProperties()
            return
        if value not in _JOIN_TAG:
            raise ValueError("invalid line-join style %r" % (value,))
        ln = self._get_or_add_ln()
        ln._remove_eg_lineJoinProperties()
        # -- ZeroOrOneChoice's `_add_x` writes the child in the right slot --
        getattr(ln, "_add_%s" % _JOIN_TAG[value].split(":", 1)[1])()

    @lazyproperty
    def head_end(self):
        """:class:`LineEndFormat` for the start (head) of this line.

        Provides access to the ``<a:headEnd>`` element's ``type``, ``width``,
        and ``length`` attributes.
        """
        return LineEndFormat(self, "headEnd")

    @lazyproperty
    def tail_end(self):
        """:class:`LineEndFormat` for the end (tail) of this line.

        Provides access to the ``<a:tailEnd>`` element's ``type``, ``width``,
        and ``length`` attributes.
        """
        return LineEndFormat(self, "tailEnd")

    def _get_or_add_ln(self):
        """
        Return the ``<a:ln>`` element containing the line format properties
        in the XML.
        """
        return self._parent.get_or_add_ln()

    @property
    def _ln(self):
        return self._parent.ln
