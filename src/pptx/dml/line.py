"""DrawingML objects related to line formatting."""

from __future__ import annotations

from pptx.dml.color import _LazyColorFormat
from pptx.dml.fill import FillFormat
from pptx.util import Emu, lazyproperty


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

    def _get_or_add_ln(self):
        """
        Return the ``<a:ln>`` element containing the line format properties
        in the XML.
        """
        return self._parent.get_or_add_ln()

    @property
    def _ln(self):
        return self._parent.ln
