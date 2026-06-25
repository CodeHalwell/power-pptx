"""Series-related objects."""

from __future__ import annotations

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

        A series shares the value axis of the plot (chart group) it belongs
        to. Assigning ``"secondary"`` moves this series' whole plot onto a
        secondary value axis, creating that axis (and a hidden secondary
        category axis it crosses) if necessary. The newly-allocated axis ids
        stay within the signed-int32 range so PowerPoint never flags the file
        for repair. Assigning ``"primary"`` is only valid while the series is
        already on the primary axis (moving back is unsupported).
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
        plotArea = self._ser.xpath("ancestor::c:plotArea")[0]
        secondary = plotArea.secondary_value_axis
        if secondary is None:
            # Move THIS series' plot (not just the front-most one) onto the new
            # secondary axis — critical for combo charts with multiple plots.
            plotArea.add_secondary_value_axis(self._ser.getparent())
            return
        # -- a secondary axis already exists; re-point this series' plot onto
        # -- the secondary axis ids.
        val2_id = secondary.xpath("c:axId")[0].get("val")
        cross2_id = secondary.xpath("c:crossAx")[0].get("val")
        ax_ids = self._ser.getparent().xpath("c:axId")
        if len(ax_ids) >= 2:
            ax_ids[0].set("val", str(cross2_id))
            ax_ids[1].set("val", str(val2_id))


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
