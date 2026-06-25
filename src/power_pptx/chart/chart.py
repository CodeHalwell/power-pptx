"""Chart-related objects such as Chart and ChartTitle."""

from __future__ import annotations

import warnings
from collections.abc import Sequence

from power_pptx.chart.axis import CategoryAxis, DateAxis, ValueAxis
from power_pptx.chart.legend import Legend
from power_pptx.chart.plot import PlotFactory, PlotTypeInspector
from power_pptx.chart.series import SeriesCollection
from power_pptx.chart.xmlwriter import SeriesXmlRewriterFactory
from power_pptx.dml.chtfmt import ChartFormat
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.shared import ElementProxy, PartElementProxy
from power_pptx.text.text import Font, TextFrame
from power_pptx.util import lazyproperty

_SINGLE_SERIES_CHART_TYPES = frozenset(
    {
        XL_CHART_TYPE.PIE,
        XL_CHART_TYPE.PIE_EXPLODED,
        XL_CHART_TYPE.PIE_OF_PIE,
        XL_CHART_TYPE.BAR_OF_PIE,
        XL_CHART_TYPE.THREE_D_PIE,
        XL_CHART_TYPE.THREE_D_PIE_EXPLODED,
        XL_CHART_TYPE.DOUGHNUT,
        XL_CHART_TYPE.DOUGHNUT_EXPLODED,
    }
)

# Chart types where the user-visible colour is the line stroke
# (``c:spPr/a:ln/a:solidFill``), not the per-series fill.  Setting only
# the fill on these — as ``apply_palette`` used to do — leaves the
# rendered line at the default Office palette colour, silently no-op'ing
# the recolour.  Membership picks up every variant of LINE and
# XY_SCATTER that draws lines.
_LINE_STROKE_CHART_TYPES = frozenset(
    {
        XL_CHART_TYPE.LINE,
        XL_CHART_TYPE.LINE_MARKERS,
        XL_CHART_TYPE.LINE_MARKERS_STACKED,
        XL_CHART_TYPE.LINE_MARKERS_STACKED_100,
        XL_CHART_TYPE.LINE_STACKED,
        XL_CHART_TYPE.LINE_STACKED_100,
        XL_CHART_TYPE.THREE_D_LINE,
        XL_CHART_TYPE.XY_SCATTER_LINES,
        XL_CHART_TYPE.XY_SCATTER_LINES_NO_MARKERS,
        XL_CHART_TYPE.XY_SCATTER_SMOOTH,
        XL_CHART_TYPE.XY_SCATTER_SMOOTH_NO_MARKERS,
    }
)


class Chart(PartElementProxy):
    """A chart object."""

    # Set by ``GraphicFrame.chart`` so callers can navigate back to the
    # parent shape without keeping the ``add_chart`` return value
    # around.  Lives on the class so mocks spec'd against ``Chart``
    # (e.g. ``instance_mock(request, Chart)``) see it; the per-instance
    # write in ``GraphicFrame.chart`` shadows the class default.
    _parent_shape = None

    def __init__(self, chartSpace, chart_part):
        super(Chart, self).__init__(chartSpace, chart_part)
        self._chartSpace = chartSpace

    @property
    def shape(self):
        """The :class:`GraphicFrame` shape that contains this chart.

        Raises :class:`ValueError` when the chart was reached via a path
        that did not flow through a graphic frame (e.g. constructed
        directly from a chart part).  In normal use — chart returned by
        ``slide.shapes.add_chart(...).chart`` or by iterating
        ``slide.shapes`` — the parent shape is cached on first access.

        This is the canonical accessor for animating, measuring, or
        styling a chart's parent shape; reach for it instead of
        ``chart.element.getparent().getparent()`` or keeping the
        ``add_chart`` return value separately.
        """
        if self._parent_shape is None:
            raise ValueError(
                "chart.shape is unavailable on this Chart: it was not "
                "reached through GraphicFrame.chart. Hold onto the "
                "shape returned by slide.shapes.add_chart(...) (which "
                "is the GraphicFrame), or fetch the chart through "
                "slide.shapes[i].chart, to get a usable .shape ref."
            )
        return self._parent_shape

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

        Pie and doughnut charts have a single series, so per-series colors
        recolour every slice the same. Calling this on a pie/doughnut emits a
        ``UserWarning`` and routes through :meth:`color_by_category`, which is
        almost always what was meant. Use :meth:`recolour` for explicit control.
        """
        if self._is_single_series_chart():
            warnings.warn(
                "apply_palette() is series-level; pie and doughnut charts have "
                "a single series, so per-slice recolouring needs "
                "color_by_category(). Routing through it for you. Call "
                "chart.recolour(palette) to silence this, or "
                "chart.color_by_category(palette) to be explicit.",
                UserWarning,
                stacklevel=2,
            )
            self.color_by_category(palette)
            return
        from power_pptx.chart.palettes import resolve_palette

        colors = resolve_palette(palette)
        is_line_stroke = self._is_line_stroke_chart()
        for idx, series in enumerate(self.series):
            color = colors[idx % len(colors)]
            fill = series.format.fill
            fill.solid()
            fill.fore_color.rgb = color
            # For LINE / scatter-with-lines variants the user-visible
            # colour is the line stroke, not the fill — also pin
            # ``series.format.line.color.rgb`` so the recolour shows up
            # in PowerPoint and LibreOffice.
            if is_line_stroke:
                series.format.line.color.rgb = color

    def _is_single_series_chart(self):
        """True for chart types where one series renders as N slices/bars.

        Pie / doughnut variants conceptually have a single series whose
        points are the user-visible coloured regions. ``apply_palette`` —
        being series-level — therefore can't recolour them per-slice, and
        callers almost always want per-point colouring instead.

        ``IndexError`` is caught alongside the type-detection errors
        because ``self.chart_type`` walks ``self.plots[0]``, which
        raises ``IndexError`` on a chart with no plot element (rare
        but possible for partially-constructed chart parts).
        """
        try:
            return self.chart_type in _SINGLE_SERIES_CHART_TYPES
        except (NotImplementedError, KeyError, AttributeError, IndexError):
            return False

    def _is_line_stroke_chart(self):
        """True for chart types where the visible colour is the line stroke.

        LINE / LINE_MARKERS / XY_SCATTER_LINES and friends render the
        series as a stroked path; the fill colour set by ``apply_palette``
        alone has no visible effect.  ``apply_palette`` keys off this to
        also set ``series.format.line.color.rgb``.  See
        :meth:`_is_single_series_chart` for the rationale on the
        ``IndexError`` branch.
        """
        try:
            return self.chart_type in _LINE_STROKE_CHART_TYPES
        except (NotImplementedError, KeyError, AttributeError, IndexError):
            return False

    def recolour(self, palette, *, by="auto"):
        """Recolour the chart from `palette`, auto-dispatching by chart type.

        This is the recommended single entry point for chart recolouring;
        it picks between :meth:`apply_palette` (series-level) and
        :meth:`color_by_category` (point-level) so callers don't have to
        remember which is right for their chart type.

        ``by``:

        * ``"auto"`` (default) — point-level for pie / doughnut, otherwise
          series-level. Matches user intent in nearly every case.
        * ``"series"`` — force series-level (same as
          :meth:`apply_palette`).
        * ``"category"`` — force point-level (same as
          :meth:`color_by_category`).

        `palette` accepts the same forms as :meth:`apply_palette`.
        """
        if by not in ("auto", "series", "category"):
            raise ValueError(f"by must be 'auto', 'series', or 'category'; got {by!r}")
        if by == "category" or (by == "auto" and self._is_single_series_chart()):
            self.color_by_category(palette)
        else:
            # Skip the soft-warning route in apply_palette for the explicit
            # series path — caller asked for it, no second-guessing.
            from power_pptx.chart.palettes import resolve_palette

            colors = resolve_palette(palette)
            is_line_stroke = self._is_line_stroke_chart()
            for idx, series in enumerate(self.series):
                color = colors[idx % len(colors)]
                fill = series.format.fill
                fill.solid()
                fill.fore_color.rgb = color
                if is_line_stroke:
                    series.format.line.color.rgb = color

    # US-spelling alias kept stable.
    recolor = recolour

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
        from power_pptx._color import coerce_color

        try:
            rgb = coerce_color(value)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "text_color must be RGBColor, 6-digit hex string with or "
                "without '#', or (r, g, b) tuple; got "
                f"{type(value).__name__}: {exc}"
            ) from exc

        # 1. Chart-wide default text properties (c:chartSpace/c:txPr).
        self.font.color.rgb = rgb

        # 2. Legend font — only when one is present, so the read doesn't
        # silently materialise a legend element.
        if self.has_legend:
            self.legend.font.color.rgb = rgb

        # 3. Chart title — only when both the title element and its
        # rich-text frame already exist.  Reading
        # ``chart_title.text_frame`` would otherwise materialise a
        # ``<c:tx><c:rich>...</c:rich></c:tx>`` subtree on a title that's
        # currently empty / inheriting, which is a side-effect callers
        # don't expect from a colour-setting facade.
        if self.has_title:
            chart_title = self.chart_title
            if chart_title.has_text_frame:
                for paragraph in chart_title.text_frame.paragraphs:
                    for run in paragraph.runs:
                        run.font.color.rgb = rgb

        # 4. Per-plot data labels — only on plots that already have them.
        for plot in self.plots:
            if plot.has_data_labels:
                plot.data_labels.font.color.rgb = rgb

    @property
    def line_color(self):
        """Write-only facade — read is unsupported.

        On a dark deck the default axis lines and gridlines render as
        dim grey on a dark background and look broken. Pinning each
        axis line + gridline takes 4–6 separate writes; assigning
        ``chart.line_color = "#3a3e5f"`` walks them all and skips the
        ones that don't apply to this chart type (e.g. pie / doughnut
        have no axes).

        The set covered:

        * ``category_axis.format.line``
        * ``value_axis.format.line``
        * ``category_axis.major_gridlines.format.line`` (if present)
        * ``value_axis.major_gridlines.format.line`` (if present)

        Materialisation is deliberately conservative: gridlines aren't
        created if absent (no surprise change of chart appearance), and
        on chart types without axes the property is a no-op rather than
        raising.
        """
        raise AttributeError(
            "chart.line_color is write-only; read individual format.line "
            "objects (chart.category_axis.format.line.color, …) instead."
        )

    @line_color.setter
    def line_color(self, value):
        from power_pptx._color import coerce_color

        try:
            rgb = coerce_color(value)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "line_color must be RGBColor, 6-digit hex string with or "
                "without '#', or (r, g, b) tuple; got "
                f"{type(value).__name__}: {exc}"
            ) from exc

        for axis_attr in ("category_axis", "value_axis"):
            try:
                axis = getattr(self, axis_attr)
            except ValueError:
                # Pie / doughnut etc. — no axis of this kind. Skip silently.
                continue
            axis.format.line.color.rgb = rgb
            if axis.has_major_gridlines:
                axis.major_gridlines.format.line.color.rgb = rgb

    def apply_dark_theme(self, *, text="#FFFFFF", line="#3A3E5F"):
        """One-call dark-theme styling for the chart.

        Equivalent to::

            chart.text_color = text
            chart.line_color = line

        Pins every text-bearing element to ``text`` and every axis line
        + gridline to ``line``. Both arguments accept any colour-like
        value (``RGBColor``, hex string, ``(r, g, b)`` tuple).

        This is a deliberately small, opinionated convenience; for full
        control reach for ``text_color`` and ``line_color`` directly, or
        style each location explicitly.
        """
        self.text_color = text
        self.line_color = line

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
    def secondary_value_axis(self):
        """A |ValueAxis| for the chart's secondary (right-hand) value axis.

        Accessing this property is *destructive*: if the chart has only a
        single value axis it adds a secondary value axis (plus a hidden
        secondary category axis it crosses), then re-points the front-most
        plot — ``chart.plots[1]`` in a two-plot combo chart — onto the new
        axes so that plot is measured against the secondary scale. If a
        secondary value axis already exists it is returned unchanged.

        Newly-allocated axis ids stay within the signed-int32 range
        (``1..2**31-1``); ids at or above ``2**31`` make PowerPoint flag the
        file for repair.

        Raises |ValueError| if the chart type has no value axis (e.g. a pie
        chart).
        """
        plotArea = self._chartSpace.plotArea
        if not plotArea.xpath("c:valAx"):
            raise ValueError("chart has no value axis")
        valAx = plotArea.add_secondary_value_axis()
        return ValueAxis(valAx)

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
