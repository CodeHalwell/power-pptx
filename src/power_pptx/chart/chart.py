"""Chart-related objects such as Chart and ChartTitle."""

from __future__ import annotations

from collections.abc import Sequence

from power_pptx.chart.axis import CategoryAxis, DateAxis, ValueAxis
from power_pptx.chart.legend import Legend
from power_pptx.chart.plot import PlotFactory, PlotTypeInspector
from power_pptx.chart.series import SeriesCollection
from power_pptx.chart.xmlwriter import SeriesXmlRewriterFactory
from power_pptx.dml.chtfmt import ChartFormat
from power_pptx.shared import ElementProxy, PartElementProxy
from power_pptx.text.text import Font, TextFrame
from power_pptx.util import lazyproperty


class Chart(PartElementProxy):
    """A chart object."""

    def __init__(self, chartSpace, chart_part):
        super(Chart, self).__init__(chartSpace, chart_part)
        self._chartSpace = chartSpace

    @property
    def category_axis(self):
        """
        The category axis of this chart. In the case of an XY or Bubble
        chart, this is the X axis. Raises |ValueError| if no category
        axis is defined (as is the case for a pie chart, for example).
        """
        catAx_lst = self._chartSpace.catAx_lst
        if catAx_lst:
            return CategoryAxis(catAx_lst[0])

        dateAx_lst = self._chartSpace.dateAx_lst
        if dateAx_lst:
            return DateAxis(dateAx_lst[0])

        valAx_lst = self._chartSpace.valAx_lst
        if valAx_lst:
            return ValueAxis(valAx_lst[0])

        raise ValueError("chart has no category axis")

    @property
    def chart_style(self):
        """
        Read/write integer index of chart style used to format this chart.
        Range is from 1 to 48. Value is |None| if no explicit style has been
        assigned, in which case the default chart style is used. Assigning
        |None| causes any explicit setting to be removed. The integer index
        corresponds to the style's position in the chart style gallery in the
        PowerPoint UI.
        """
        style = self._chartSpace.style
        if style is None:
            return None
        return style.val

    @chart_style.setter
    def chart_style(self, value):
        self._chartSpace._remove_style()
        if value is None:
            return
        self._chartSpace._add_style(val=value)

    def apply_quick_layout(self, layout, **overrides):
        """Apply a "quick layout" preset to this chart.

        `layout` is either the name of a built-in preset (see
        :func:`power_pptx.chart.quick_layouts.layout_names`) or a dict spec.
        Any keyword arguments are merged on top of the resolved preset and
        override the named-layout values where they collide — e.g.::

            chart.apply_quick_layout("title_legend_right", title_text="Q4 ARR")
        """
        from power_pptx.chart.quick_layouts import apply_quick_layout

        apply_quick_layout(self, layout, **overrides)

    def apply_palette(self, palette):
        """Recolor every series in this chart from a palette of solid colors.

        `palette` is either the name of a built-in preset (see
        :func:`power_pptx.chart.palettes.palette_names`) or an iterable of
        color-likes — :class:`power_pptx.dml.color.RGBColor`, hex strings (with or
        without leading ``'#'``), or 3-tuples of ints in ``0-255``. Colors are
        applied in order; if the chart has more series than colors, the
        palette wraps.

        This is independent of :attr:`chart_style`: it sets the per-series
        ``spPr`` solid-fill foreground color directly, so it overrides the
        theme-derived colors that ``chart_style`` resolves to but leaves the
        ``chart_style`` value itself untouched.
        """
        from power_pptx.chart.palettes import resolve_palette

        colors = resolve_palette(palette)
        for idx, series in enumerate(self.series):
            fill = series.format.fill
            fill.solid()
            fill.fore_color.rgb = colors[idx % len(colors)]

    def color_by_category(self, palette):
        """Recolor every *data point* (category) instead of every series.

        Useful for stacked-bar / stacked-column charts where you want each
        category segment within a stack to read as a discrete color. Also
        works for single-series column/bar charts (each bar gets its own
        color).

        `palette` accepts the same forms as :meth:`apply_palette`: a
        named preset, or an iterable of color-likes.

        For each series, the palette is walked in order across the
        category points, wrapping when there are more categories than
        colors. The palette is the same for every series so a given
        category index resolves to the same color across the whole chart.
        """
        from power_pptx.chart.palettes import resolve_palette

        colors = resolve_palette(palette)
        for series in self.series:
            try:
                points = series.points
            except AttributeError:
                continue
            for cat_idx, point in enumerate(points):
                fill = point.format.fill
                fill.solid()
                fill.fore_color.rgb = colors[cat_idx % len(colors)]

    @property
    def chart_title(self):
        """A |ChartTitle| object providing access to title properties.

        Calling this property is destructive in the sense it adds a chart
        title element (`c:title`) to the chart XML if one is not already
        present. Use :attr:`has_title` to test for presence of a chart title
        non-destructively.
        """
        return ChartTitle(self._element.get_or_add_title())

    @property
    def text_color(self):
        """Write-only facade — read is unsupported.

        Charts inherit text colour from theme slot ``tx1`` (which defaults
        to black on a light theme).  On a dark deck that means manually
        threading the same colour through ``chart.font.color``,
        ``chart.legend.font.color``, ``chart.chart_title.text_frame``
        runs, and every plot's ``data_labels.font.color`` — the most
        common copy-paste in dark-deck authoring.

        Assigning ``chart.text_color = "#FFFFFF"`` (or an
        :class:`~power_pptx.dml.color.RGBColor` / ``(r, g, b)`` tuple)
        walks all four locations and pins them.  Read is unsupported (no
        canonical "single" text colour); read individual fonts instead.
        """
        raise AttributeError(
            "chart.text_color is write-only; read individual fonts "
            "(chart.font.color, chart.legend.font.color, …) instead."
        )

    @text_color.setter
    def text_color(self, value):
        from power_pptx.dml.color import RGBColor

        if isinstance(value, str):
            rgb = RGBColor.from_string(value.lstrip("#"))
        elif isinstance(value, tuple) and len(value) == 3:
            rgb = RGBColor(*value)
        elif isinstance(value, RGBColor):
            rgb = value
        else:
            raise TypeError(
                "text_color must be RGBColor, '#RRGGBB' string, or (r, g, b) "
                f"tuple; got {type(value).__name__}"
            )

        # 1. Chart-wide default text properties (c:chartSpace/c:txPr).
        self.font.color.rgb = rgb

        # 2. Legend font — only when one is present, so the read doesn't
        # silently materialise a legend element.
        if self.has_legend:
            self.legend.font.color.rgb = rgb

        # 3. Chart title — only when one is present.
        if self.has_title:
            for paragraph in self.chart_title.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.font.color.rgb = rgb

        # 4. Per-plot data labels — only on plots that already have them.
        for plot in self.plots:
            if plot.has_data_labels:
                plot.data_labels.font.color.rgb = rgb

    @property
    def chart_type(self):
        """Member of :ref:`XlChartType` enumeration specifying type of this chart.

        If the chart has two plots, for example, a line plot overlayed on a bar plot,
        the type reported is for the first (back-most) plot. Read-only.
        """
        first_plot = self.plots[0]
        return PlotTypeInspector.chart_type(first_plot)

    @lazyproperty
    def font(self):
        """Font object controlling text format defaults for this chart."""
        defRPr = self._chartSpace.get_or_add_txPr().p_lst[0].get_or_add_pPr().get_or_add_defRPr()
        return Font(defRPr)

    @property
    def has_legend(self):
        """
        Read/write boolean, |True| if the chart has a legend. Assigning
        |True| causes a legend to be added to the chart if it doesn't already
        have one. Assigning False removes any existing legend definition
        along with any existing legend settings.
        """
        return self._chartSpace.chart.has_legend

    @has_legend.setter
    def has_legend(self, value):
        self._chartSpace.chart.has_legend = bool(value)

    @property
    def has_title(self):
        """Read/write boolean, specifying whether this chart has a title.

        Assigning |True| causes a title to be added if not already present.
        Assigning |False| removes any existing title along with its text and
        settings.
        """
        title = self._chartSpace.chart.title
        if title is None:
            return False
        return True

    @has_title.setter
    def has_title(self, value):
        chart = self._chartSpace.chart
        if bool(value) is False:
            chart._remove_title()
            autoTitleDeleted = chart.get_or_add_autoTitleDeleted()
            autoTitleDeleted.val = True
            return
        chart.get_or_add_title()

    @property
    def legend(self):
        """
        A |Legend| object providing access to the properties of the legend
        for this chart.
        """
        legend_elm = self._chartSpace.chart.legend
        if legend_elm is None:
            return None
        return Legend(legend_elm)

    @lazyproperty
    def plots(self):
        """
        The sequence of plots in this chart. A plot, called a *chart group*
        in the Microsoft API, is a distinct sequence of one or more series
        depicted in a particular charting type. For example, a chart having
        a series plotted as a line overlaid on three series plotted as
        columns would have two plots; the first corresponding to the three
        column series and the second to the line series. Plots are sequenced
        in the order drawn, i.e. back-most to front-most. Supports *len()*,
        membership (e.g. ``p in plots``), iteration, slicing, and indexed
        access (e.g. ``plot = plots[i]``).
        """
        plotArea = self._chartSpace.chart.plotArea
        return _Plots(plotArea, self)

    def replace_data(self, chart_data):
        """
        Use the categories and series values in the |ChartData| object
        *chart_data* to replace those in the XML and Excel worksheet for this
        chart.
        """
        rewriter = SeriesXmlRewriterFactory(self.chart_type, chart_data)
        rewriter.replace_series_data(self._chartSpace)
        self._workbook.update_from_xlsx_blob(chart_data.xlsx_blob)

    @lazyproperty
    def series(self):
        """
        A |SeriesCollection| object containing all the series in this
        chart. When the chart has multiple plots, all the series for the
        first plot appear before all those for the second, and so on. Series
        within a plot have an explicit ordering and appear in that sequence.
        """
        return SeriesCollection(self._chartSpace.plotArea)

    @property
    def value_axis(self):
        """
        The |ValueAxis| object providing access to properties of the value
        axis of this chart. Raises |ValueError| if the chart has no value
        axis.
        """
        valAx_lst = self._chartSpace.valAx_lst
        if not valAx_lst:
            raise ValueError("chart has no value axis")

        idx = 1 if len(valAx_lst) > 1 else 0
        return ValueAxis(valAx_lst[idx])

    @property
    def _workbook(self):
        """
        The |ChartWorkbook| object providing access to the Excel source data
        for this chart.
        """
        return self.part.chart_workbook


class ChartTitle(ElementProxy):
    """Provides properties for manipulating a chart title."""

    # This shares functionality with AxisTitle, which could be factored out
    # into a base class, perhaps power_pptx.chart.shared.BaseTitle. I suspect they
    # actually differ in certain fuller behaviors, but at present they're
    # essentially identical.

    def __init__(self, title):
        super(ChartTitle, self).__init__(title)
        self._title = title

    @lazyproperty
    def format(self):
        """|ChartFormat| object providing access to line and fill formatting.

        Return the |ChartFormat| object providing shape formatting properties
        for this chart title, such as its line color and fill.
        """
        return ChartFormat(self._title)

    @property
    def has_text_frame(self):
        """Read/write Boolean specifying whether this title has a text frame.

        Return |True| if this chart title has a text frame, and |False|
        otherwise. Assigning |True| causes a text frame to be added if not
        already present. Assigning |False| causes any existing text frame to
        be removed along with its text and formatting.
        """
        if self._title.tx_rich is None:
            return False
        return True

    @has_text_frame.setter
    def has_text_frame(self, value):
        if bool(value) is False:
            self._title._remove_tx()
            return
        self._title.get_or_add_tx_rich()

    @property
    def text_frame(self):
        """|TextFrame| instance for this chart title.

        Return a |TextFrame| instance allowing read/write access to the text
        of this chart title and its text formatting properties. Accessing this
        property is destructive in the sense it adds a text frame if one is
        not present. Use :attr:`has_text_frame` to test for the presence of
        a text frame non-destructively.
        """
        rich = self._title.get_or_add_tx_rich()
        return TextFrame(rich, self)


class _Plots(Sequence):
    """
    The sequence of plots in a chart, such as a bar plot or a line plot. Most
    charts have only a single plot. The concept is necessary when two chart
    types are displayed in a single set of axes, like a bar plot with
    a superimposed line plot.
    """

    def __init__(self, plotArea, chart):
        super(_Plots, self).__init__()
        self._plotArea = plotArea
        self._chart = chart

    def __getitem__(self, index):
        xCharts = self._plotArea.xCharts
        if isinstance(index, slice):
            plots = [PlotFactory(xChart, self._chart) for xChart in xCharts]
            return plots[index]
        else:
            xChart = xCharts[index]
            return PlotFactory(xChart, self._chart)

    def __len__(self):
        return len(self._plotArea.xCharts)
