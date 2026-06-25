"""Series-level analytics: trendlines and error bars.

These objects wrap the ``<c:trendline>`` and ``<c:errBars>`` children of a
``<c:ser>`` element and expose an Excel-like authoring API on chart series.
"""

from __future__ import annotations

from collections.abc import Sequence

from power_pptx.enum.chart import (
    XL_ERROR_BAR_INCLUDE,
    XL_ERROR_BAR_TYPE,
    XL_TRENDLINE_TYPE,
)
from power_pptx.oxml import parse_xml
from power_pptx.oxml.ns import nsdecls

# -- map of the short-name strings accepted at the API boundary to the
# -- corresponding enum member, so callers can pass e.g. "linear" or
# -- "movingAvg" without importing the enum.
_TRENDLINE_ALIASES = {
    "linear": XL_TRENDLINE_TYPE.LINEAR,
    "exp": XL_TRENDLINE_TYPE.EXPONENTIAL,
    "exponential": XL_TRENDLINE_TYPE.EXPONENTIAL,
    "log": XL_TRENDLINE_TYPE.LOGARITHMIC,
    "logarithmic": XL_TRENDLINE_TYPE.LOGARITHMIC,
    "movingavg": XL_TRENDLINE_TYPE.MOVING_AVERAGE,
    "moving_average": XL_TRENDLINE_TYPE.MOVING_AVERAGE,
    "poly": XL_TRENDLINE_TYPE.POLYNOMIAL,
    "polynomial": XL_TRENDLINE_TYPE.POLYNOMIAL,
    "power": XL_TRENDLINE_TYPE.POWER,
}

_ERR_DIRECTION_ALIASES = {
    "both": XL_ERROR_BAR_TYPE.BOTH,
    "plus": XL_ERROR_BAR_TYPE.PLUS,
    "minus": XL_ERROR_BAR_TYPE.MINUS,
}


def _resolve_trendline_type(kind):
    """Return the `XL_TRENDLINE_TYPE` member for *kind*.

    *kind* may already be an enum member, or one of the short-name strings
    such as ``"linear"`` / ``"movingAvg"`` / ``"poly"``.
    """
    if isinstance(kind, XL_TRENDLINE_TYPE):
        return kind
    try:
        return _TRENDLINE_ALIASES[str(kind).lower()]
    except KeyError:
        raise ValueError(
            "trendline kind must be one of %r or an XL_TRENDLINE_TYPE member; got %r"
            % (sorted(set(_TRENDLINE_ALIASES)), kind)
        )


def _resolve_err_direction(direction):
    """Return the `XL_ERROR_BAR_TYPE` member for *direction*."""
    if isinstance(direction, XL_ERROR_BAR_TYPE):
        return direction
    try:
        return _ERR_DIRECTION_ALIASES[str(direction).lower()]
    except KeyError:
        raise ValueError(
            "error-bar direction must be 'both', 'plus', or 'minus' (or an "
            "XL_ERROR_BAR_TYPE member); got %r" % (direction,)
        )


class Trendline(object):
    """A single ``<c:trendline>`` fitted to a chart series."""

    def __init__(self, trendline):
        self._element = trendline
        self._trendline = trendline

    @property
    def trendline_type(self):
        """Member of :ref:`XL_TRENDLINE_TYPE` for this trendline's curve."""
        return self._trendline.trendlineType.val

    @property
    def show_equation(self):
        """Read/write bool: whether the fitted equation is displayed."""
        dispEq = self._trendline.dispEq
        if dispEq is None:
            return False
        return bool(dispEq.val)

    @show_equation.setter
    def show_equation(self, value):
        if bool(value):
            self._trendline.get_or_add_dispEq().val = True
        else:
            self._trendline._remove_dispEq()

    @property
    def show_r_squared(self):
        """Read/write bool: whether the R-squared value is displayed."""
        dispRSqr = self._trendline.dispRSqr
        if dispRSqr is None:
            return False
        return bool(dispRSqr.val)

    @show_r_squared.setter
    def show_r_squared(self, value):
        if bool(value):
            self._trendline.get_or_add_dispRSqr().val = True
        else:
            self._trendline._remove_dispRSqr()

    @property
    def name(self):
        """Read/write str: the legend label for this trendline, or |None|."""
        name = self._trendline.name
        if name is None:
            return None
        return name.text

    @name.setter
    def name(self, value):
        if value is None:
            self._trendline._remove_name()
            return
        self._trendline.get_or_add_name().text = str(value)

    @property
    def order(self):
        """Read/write int: polynomial order (2-6), or |None| if unset."""
        order = self._trendline.order
        if order is None:
            return None
        return order.val

    @order.setter
    def order(self, value):
        if value is None:
            self._trendline._remove_order()
            return
        self._trendline.get_or_add_order().val = int(value)

    @property
    def period(self):
        """Read/write int: moving-average period (>=2), or |None| if unset."""
        period = self._trendline.period
        if period is None:
            return None
        return period.val

    @period.setter
    def period(self, value):
        if value is None:
            self._trendline._remove_period()
            return
        self._trendline.get_or_add_period().val = int(value)

    @property
    def forward(self):
        """Read/write float: forward projection in periods, or |None|."""
        forward = self._trendline.forward
        if forward is None:
            return None
        return forward.val

    @forward.setter
    def forward(self, value):
        if value is None:
            self._trendline._remove_forward()
            return
        self._trendline.get_or_add_forward().val = float(value)

    @property
    def backward(self):
        """Read/write float: backward projection in periods, or |None|."""
        backward = self._trendline.backward
        if backward is None:
            return None
        return backward.val

    @backward.setter
    def backward(self, value):
        if value is None:
            self._trendline._remove_backward()
            return
        self._trendline.get_or_add_backward().val = float(value)


class Trendlines(Sequence):
    """The collection of ``<c:trendline>`` elements for a series.

    Supports ``len()``, iteration, indexed access, and ``.add(...)``.
    """

    def __init__(self, ser):
        self._element = ser
        self._ser = ser

    def __getitem__(self, index):
        trendlines = self._ser.trendline_lst
        if isinstance(index, slice):
            return [Trendline(t) for t in trendlines[index]]
        return Trendline(trendlines[index])

    def __len__(self):
        return len(self._ser.trendline_lst)

    def add(
        self,
        kind=XL_TRENDLINE_TYPE.LINEAR,
        *,
        show_equation=False,
        show_r_squared=False,
        name=None,
        order=None,
        period=None,
        forward=None,
        backward=None,
    ):
        """Add and return a new |Trendline| of the given *kind*.

        *kind* accepts an :class:`XL_TRENDLINE_TYPE` member or a short-name
        string (``"linear"``, ``"exp"``, ``"log"``, ``"movingAvg"``,
        ``"poly"``, ``"power"``). *order* applies to polynomial trendlines,
        *period* to moving-average trendlines. *forward* / *backward* project
        the curve that many periods past the data.
        """
        trendline_type = _resolve_trendline_type(kind)
        trendline = self._ser._add_trendline()
        # -- write the `val` attribute explicitly (even for the schema default
        # -- "linear") so the emitted XML matches Excel/PowerPoint output and
        # -- is unambiguous to readers.
        trendline.trendlineType.set("val", trendline_type.xml_value)

        proxy = Trendline(trendline)
        if name is not None:
            proxy.name = name
        if order is not None:
            proxy.order = order
        if period is not None:
            proxy.period = period
        if forward is not None:
            proxy.forward = forward
        if backward is not None:
            proxy.backward = backward
        # -- dispRSqr / dispEq come late in the schema, set after order/period
        if show_r_squared:
            proxy.show_r_squared = True
        if show_equation:
            proxy.show_equation = True
        return proxy


class ErrorBars(object):
    """The ``<c:errBars>`` element for a series, with Excel-style constructors.

    The collection is materialised lazily — the underlying ``<c:errBars>``
    element is only created when one of the constructor methods (``fixed``,
    ``percentage``, ``standard_deviation``, ``standard_error``, ``custom``) is
    called. Calling a constructor a second time replaces the prior settings.
    """

    def __init__(self, ser):
        self._element = ser
        self._ser = ser

    @property
    def exists(self):
        """True if an ``<c:errBars>`` element is present on this series."""
        return self._ser.errBars is not None

    @property
    def error_bar_type(self):
        """The :ref:`XL_ERROR_BAR_TYPE` direction, or |None| if no error bars."""
        errBars = self._ser.errBars
        if errBars is None or errBars.errBarType is None:
            return None
        return errBars.errBarType.val

    @property
    def include_type(self):
        """The :ref:`XL_ERROR_BAR_INCLUDE` value-type, or |None|."""
        errBars = self._ser.errBars
        if errBars is None or errBars.errValType is None:
            return None
        return errBars.errValType.val

    @property
    def value(self):
        """The numeric error amount (fixed/percentage/stdDev), or |None|."""
        errBars = self._ser.errBars
        if errBars is None or errBars.val is None:
            return None
        return float(errBars.val.get("val"))

    def remove(self):
        """Remove any error bars present on this series."""
        self._ser._remove_errBars()

    # -- Excel-mirroring constructors -----------------------------------

    def fixed(self, value, *, direction="both"):
        """Set fixed-value error bars of magnitude *value*."""
        return self._configure(XL_ERROR_BAR_INCLUDE.FIXED_VALUE, direction, value=value)

    def percentage(self, pct, *, direction="both"):
        """Set percentage error bars of *pct* percent of each value."""
        return self._configure(XL_ERROR_BAR_INCLUDE.PERCENTAGE, direction, value=pct)

    def standard_deviation(self, n=1, *, direction="both"):
        """Set error bars of *n* standard deviations."""
        return self._configure(XL_ERROR_BAR_INCLUDE.STANDARD_DEVIATION, direction, value=n)

    def standard_error(self, *, direction="both"):
        """Set standard-error error bars (no numeric amount)."""
        return self._configure(XL_ERROR_BAR_INCLUDE.STANDARD_ERROR, direction, value=None)

    def custom(self, plus, minus, *, direction="both"):
        """Set custom error bars from per-point *plus* / *minus* sequences.

        *plus* and *minus* are sequences of floats, one per data point.
        """
        errBars = self._reset_errBars(direction)
        errBars.get_or_add_errValType().set("val", XL_ERROR_BAR_INCLUDE.CUSTOM.xml_value)
        errBars.append(self._num_data_source("c:plus", plus))
        errBars.append(self._num_data_source("c:minus", minus))
        return self

    # -- internals ------------------------------------------------------

    def _configure(self, include_type, direction, *, value):
        errBars = self._reset_errBars(direction)
        errBars.get_or_add_errValType().set("val", include_type.xml_value)
        if value is not None:
            val = parse_xml('<c:val %s val="%s"/>' % (nsdecls("c"), float(value)))
            errBars.append(val)
        return self

    def _reset_errBars(self, direction):
        """Return a fresh ``<c:errBars>`` element with *direction* applied.

        Any pre-existing error bars are removed first so repeated constructor
        calls don't accumulate stale ``plus`` / ``minus`` / ``val`` children.
        """
        self._ser._remove_errBars()
        errBars = self._ser.get_or_add_errBars()
        errBars.get_or_add_errBarType().set("val", _resolve_err_direction(direction).xml_value)
        return errBars

    @staticmethod
    def _num_data_source(tag, values):
        """Return a ``<c:plus>`` or ``<c:minus>`` numeric-literal data source."""
        seq = list(values)
        pts = "".join(
            '<c:pt idx="%d"><c:v>%s</c:v></c:pt>' % (i, float(v))
            for i, v in enumerate(seq)
            if v is not None
        )
        xml = (
            "<%s %s>"
            "<c:numLit>"
            "<c:formatCode>General</c:formatCode>"
            '<c:ptCount val="%d"/>'
            "%s"
            "</c:numLit>"
            "</%s>"
        ) % (tag, nsdecls("c"), len(seq), pts, tag)
        return parse_xml(xml)
