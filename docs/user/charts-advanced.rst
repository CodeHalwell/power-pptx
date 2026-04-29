.. _charts-advanced:

Charts: palettes, quick layouts, per-series fills
==================================================

The chart helpers below stack on top of the existing chart API; nothing
here replaces ``chart_style`` or the underlying series formatting — they
just make common operations one line each.

Chart palettes
--------------

``Chart.apply_palette(palette)`` recolors every series in declaration
order from a named built-in or an iterable of color-likes (``RGBColor``,
hex strings with or without ``#``, or ``(r, g, b)`` triples).  Palettes
wrap when the chart has more series than colors::

    chart.apply_palette("modern")
    chart.apply_palette(["#4F9DFF", "#7FCFA1", "#F7B500"])

Six built-ins ship in ``power_pptx.chart.palettes``:
``modern``, ``classic``, ``editorial``, ``vibrant``,
``monochrome_blue``, and ``monochrome_warm``.  ``palette_names()`` and
``resolve_palette()`` are also exported for callers that want to share
the same color set with non-chart shapes.

The ``chart_style`` integer is left untouched, so the palette overrides
only the per-series fill without rewriting the rest of the style.

Quick layouts
-------------

``Chart.apply_quick_layout(layout)`` toggles title / legend / axis-title
/ gridline visibility in opinionated combinations.  Ten built-in
presets ship in ``power_pptx.chart.quick_layouts``::

    chart.apply_quick_layout("title_legend_right")
    chart.apply_quick_layout("title_legend_bottom")
    chart.apply_quick_layout("title_axes_legend_right")
    chart.apply_quick_layout("minimal")

Custom layouts can be supplied as a dict spec.  Missing keys leave the
chart untouched so layouts compose cleanly, and charts without
category/value axes (e.g. pie) silently skip the corresponding keys.

Per-series gradient and pattern fills
-------------------------------------

``chart.series[i].format.fill`` is a regular |FillFormat|, so all four
gradient kinds and ``MSO_PATTERN_TYPE`` patterns work per-series with no
chart-specific shim::

    fill = chart.series[0].format.fill
    fill.gradient(kind="linear")
    fill.gradient_stops.replace([(0.0, "#0F2D6B"), (1.0, "#4F9DFF")])

    chart.series[1].format.fill.patterned()
    chart.series[1].format.fill.pattern = MSO_PATTERN_TYPE.WIDE_DOWNWARD_DIAGONAL
