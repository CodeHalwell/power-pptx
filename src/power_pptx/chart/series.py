"""Series-related objects."""

from __future__ import annotations

import copy
from collections.abc import Sequence

from power_pptx.chart.analytics import ErrorBars, Trendlines
from power_pptx.chart.datalabel import DataLabels
from power_pptx.chart.marker import Marker
from power_pptx.chart.point import BubblePoints, CategoryPoints, XyPoints
from power_pptx.dml.chtfmt import ChartFormat
from power_pptx.oxml.ns import qn
from power_pptx.util import lazyproperty


class _BaseSeries(object):
    """
    Base class for |BarSeries| and other series classes.
    """

    def __init__(self, ser):
        super(_BaseSeries, self).__init__()
        self._element = ser
        self._ser = ser

    @lazyproperty
    def format(self):
        """
        The |ChartFormat| instance for this series, providing access to shape
        properties such as fill and line.
        """
        return ChartFormat(self._ser)

    @property
    def index(self):
        """
        The zero-based integer index of this series as reported in its
        `c:ser/c:idx` element.
        """
        return self._element.idx.val

    @property
    def name(self):
        """
        The string label given to this series, appears as the title of the
        column for this series in the Excel worksheet. It also appears as the
        label for this series in the legend.
        """
        names = self._element.xpath("./c:tx//c:pt/c:v/text()")
        name = names[0] if names else ""
        return name


class _BaseCategorySeries(_BaseSeries):
    """Base class for |BarSeries| and other category chart series classes."""

    @lazyproperty
    def data_labels(self):
        """|DataLabels| object controlling data labels for this series."""
        return DataLabels(self._ser.get_or_add_dLbls())

    @lazyproperty
    def points(self):
        """
        The |CategoryPoints| object providing access to individual data
        points in this series.
        """
        return CategoryPoints(self._ser)

    @property
    def values(self):
        """
        Read-only. A sequence containing the float values for this series, in
        the order they appear on the chart.
        """

        def iter_values():
            val = self._element.val
            if val is None:
                return
            for idx in range(val.ptCount_val):
                yield val.pt_v(idx)

        return tuple(iter_values())


class _MarkerMixin(object):
    """
    Mixin class providing `.marker` property for line-type chart series. The
    line-type charts are Line, XY, and Radar.
    """

    @lazyproperty
    def marker(self):
        """
        The |Marker| instance for this series, providing access to data point
        marker properties such as fill and line. Setting these properties
        determines the appearance of markers for all points in this series
        that are not overridden by settings at the point level.
        """
        return Marker(self._ser)


class _AnalyticsMixin(object):
    """Mixin adding ``trendlines`` and ``error_bars`` to a series.

    Only mixed into the series types whose schema complexType permits
    ``<c:trendline>`` / ``<c:errBars>`` children (bar, line, scatter, area,
    bubble). Pie and radar series do not allow them.
    """

    @lazyproperty
    def trendlines(self):
        """The |Trendlines| collection for this series.

        Supports ``len()``, iteration, indexed access, and
        ``.add(kind, ...)`` to fit a new analytical trendline.
        """
        return Trendlines(self._ser)

    @lazyproperty
    def error_bars(self):
        """The |ErrorBars| object for this series.

        Provides Excel-style constructors: ``fixed(value)``,
        ``percentage(pct)``, ``standard_deviation(n)``, ``standard_error()``,
        and ``custom(plus, minus)``.
        """
        return ErrorBars(self._ser)

    @property
    def axis_group(self):
        """Read/write ``"primary"`` or ``"secondary"`` axis group.

        Assigning ``"secondary"`` moves this series, and only this series,
        onto the secondary value axis, creating that axis (and a hidden
        secondary category axis it crosses) if necessary::

            chart.series[1].axis_group = "secondary"
            chart.secondary_value_axis.maximum_scale = 100

        A series is measured against the axes of the plot (chart group) it
        belongs to, so a series that shares its plot with others is first
        split off into a plot of its own, of the same kind and placed in
        front. A later series of the same kind joins that plot rather than
        getting another. A series that is alone in its plot takes the plot
        with it.

        ``chart.series`` lists series plot by plot, so a series that changes
        plot changes position in it: after ``chart.series[0].axis_group =
        "secondary"`` on a two-series chart, ``chart.series[0]`` is the
        *other* series. Keep a reference to the series rather than indexing
        again. Its name, ``index`` and formatting are untouched.

        The newly-allocated axis ids stay within the signed-int32 range so
        PowerPoint never flags the file for repair. Assigning ``"primary"``
        is only valid while the series is already on the primary axis (moving
        back is unsupported).
        """
        plotArea = self._ser.xpath("ancestor::c:plotArea")[0]
        secondary = plotArea.secondary_value_axis
        if secondary is None:
            return "primary"
        secondary_id = secondary.xpath("c:axId")[0].get("val")
        xChart = self._ser.getparent()
        ax_ids = {a.get("val") for a in xChart.xpath("c:axId")}
        return "secondary" if secondary_id in ax_ids else "primary"

    @axis_group.setter
    def axis_group(self, value):
        if value not in ("primary", "secondary"):
            raise ValueError("axis_group must be 'primary' or 'secondary', got %r" % (value,))
        if value == "primary":
            if self.axis_group == "secondary":
                raise ValueError("moving a series back to the primary axis group is not supported")
            return
        if self.axis_group == "secondary":
            return
        ser = self._ser
        plotArea = ser.xpath("ancestor::c:plotArea")[0]
        secondary = plotArea.secondary_value_axis
        xChart = ser.getparent()
        if len(xChart.xpath("c:ser")) > 1:
            # -- The axes belong to the plot, not the series, so re-pointing a
            # -- plot this series shares would drag its siblings along. Give
            # -- the series a plot it does not share: one already on the
            # -- secondary axes if there is a like one, else a new one.
            like_plot = _like_plot_on_axis(xChart, secondary)
            if like_plot is not None:
                like_plot.xpath("c:ser")[-1].addnext(ser)
                return
            xChart = _split_into_own_plot(ser)
        if secondary is None:
            # Move THIS series' plot (not just the front-most one) onto the new
            # secondary axis — critical for combo charts with multiple plots.
            plotArea.add_secondary_value_axis(xChart)
            return
        # -- a secondary axis already exists; re-point this series' plot onto
        # -- the secondary axis ids.
        val2_id = secondary.xpath("c:axId")[0].get("val")
        cross2_id = secondary.xpath("c:crossAx")[0].get("val")
        ax_ids = xChart.xpath("c:axId")
        if len(ax_ids) >= 2:
            ax_ids[0].set("val", str(cross2_id))
            ax_ids[1].set("val", str(val2_id))


#: The children of an xChart element that decide how its series are laid out
#: against each other. Two plots that agree on these can share their series.
_PLOT_KIND_TAGS = frozenset(
    qn(tag) for tag in ("c:barDir", "c:grouping", "c:scatterStyle", "c:radarStyle")
)


def _plot_kind(xChart):
    """A hashable description of what kind of plot `xChart` is."""
    return (
        xChart.tag,
        tuple((child.tag, child.get("val")) for child in xChart if child.tag in _PLOT_KIND_TAGS),
    )


def _like_plot_on_axis(xChart, valAx):
    """The plot of the same kind as `xChart` measured against `valAx`, or |None|.

    `valAx` may be |None| (no such axis yet), in which case there is none.
    """
    if valAx is None:
        return None
    axis_id = valAx.xpath("c:axId")[0].get("val")
    kind = _plot_kind(xChart)
    for other in xChart.getparent().iter_xCharts():
        if other is xChart or _plot_kind(other) != kind:
            continue
        if axis_id in other.xpath("c:axId/@val") and other.xpath("c:ser"):
            return other
    return None


def _split_into_own_plot(ser):
    """Move `ser` out of the plot it shares into a new one, and return that plot.

    The new plot is a copy of the old one — same kind, grouping, gap width,
    data-label defaults and, for now, the same axes — holding only `ser`. It
    goes directly after the plot it came from, so it draws in front of it and
    every plot still precedes the axes as the schema requires.
    """
    xChart = ser.getparent()
    # -- the series sit between the plot's leading properties (`c:barDir`,
    # -- `c:grouping`, ...) and its trailing ones (`c:dLbls`, `c:axId`, ...);
    # -- the copy must keep that position, which the schema prescribes
    position = xChart.index(xChart.xpath("c:ser")[0])
    new_xChart = copy.deepcopy(xChart)
    for copied_ser in new_xChart.xpath("c:ser"):
        new_xChart.remove(copied_ser)
    # -- inserting the original element (not a copy) keeps `Series` proxies
    # -- already handed out pointing at a live element; lxml detaches it from
    # -- the old plot as part of the move
    new_xChart.insert(position, ser)
    xChart.addnext(new_xChart)
    return new_xChart


class AreaSeries(_BaseCategorySeries, _AnalyticsMixin):
    """
    A data point series belonging to an area plot.
    """


class BarSeries(_BaseCategorySeries, _AnalyticsMixin):
    """A data point series belonging to a bar plot."""

    @property
    def invert_if_negative(self):
        """
        |True| if a point having a value less than zero should appear with a
        fill different than those with a positive value. |False| if the fill
        should be the same regardless of the bar's value. When |True|, a bar
        with a solid fill appears with white fill; in a bar with gradient
        fill, the direction of the gradient is reversed, e.g. dark -> light
        instead of light -> dark. The term "invert" here should be understood
        to mean "invert the *direction* of the *fill gradient*".
        """
        invertIfNegative = self._element.invertIfNegative
        if invertIfNegative is None:
            return True
        return invertIfNegative.val

    @invert_if_negative.setter
    def invert_if_negative(self, value):
        invertIfNegative = self._element.get_or_add_invertIfNegative()
        invertIfNegative.val = value


class LineSeries(_BaseCategorySeries, _MarkerMixin, _AnalyticsMixin):
    """
    A data point series belonging to a line plot.
    """

    @property
    def smooth(self):
        """
        Read/write boolean specifying whether to use curve smoothing to
        form the line connecting the data points in this series into
        a continuous curve. If |False|, a series of straight line segments
        are used to connect the points.
        """
        smooth = self._element.smooth
        if smooth is None:
            return True
        return smooth.val

    @smooth.setter
    def smooth(self, value):
        self._element.get_or_add_smooth().val = value


class PieSeries(_BaseCategorySeries):
    """
    A data point series belonging to a pie plot.
    """


class RadarSeries(_BaseCategorySeries, _MarkerMixin):
    """
    A data point series belonging to a radar plot.
    """


class XySeries(_BaseSeries, _MarkerMixin, _AnalyticsMixin):
    """
    A data point series belonging to an XY (scatter) plot.
    """

    def iter_values(self):
        """
        Generate each float Y value in this series, in the order they appear
        on the chart. A value of `None` represents a missing Y value
        (corresponding to a blank Excel cell).
        """
        yVal = self._element.yVal
        if yVal is None:
            return

        for idx in range(yVal.ptCount_val):
            yield yVal.pt_v(idx)

    @lazyproperty
    def points(self):
        """
        The |XyPoints| object providing access to individual data points in
        this series.
        """
        return XyPoints(self._ser)

    @property
    def values(self):
        """
        Read-only. A sequence containing the float values for this series, in
        the order they appear on the chart.
        """
        return tuple(self.iter_values())


class BubbleSeries(XySeries):
    """
    A data point series belonging to a bubble plot.
    """

    @lazyproperty
    def points(self):
        """
        The |BubblePoints| object providing access to individual data point
        objects used to discover and adjust the formatting and data labels of
        a data point.
        """
        return BubblePoints(self._ser)


class SeriesCollection(Sequence):
    """
    A sequence of |Series| objects.
    """

    def __init__(self, parent_elm):
        # *parent_elm* can be either a c:plotArea or xChart element
        super(SeriesCollection, self).__init__()
        self._element = parent_elm

    def __getitem__(self, index):
        ser = self._element.sers[index]
        return _SeriesFactory(ser)

    def __len__(self):
        return len(self._element.sers)


def _SeriesFactory(ser):
    """
    Return an instance of the appropriate subclass of _BaseSeries based on the
    xChart element *ser* appears in.
    """
    xChart_tag = ser.getparent().tag

    try:
        SeriesCls = {
            qn("c:areaChart"): AreaSeries,
            qn("c:barChart"): BarSeries,
            qn("c:bubbleChart"): BubbleSeries,
            qn("c:doughnutChart"): PieSeries,
            qn("c:lineChart"): LineSeries,
            qn("c:pieChart"): PieSeries,
            qn("c:radarChart"): RadarSeries,
            qn("c:scatterChart"): XySeries,
        }[xChart_tag]
    except KeyError:
        raise NotImplementedError("series class for %s not yet implemented" % xChart_tag)

    return SeriesCls(ser)
