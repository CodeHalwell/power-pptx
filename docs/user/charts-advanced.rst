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

Custom layouts can be supplied as a dict spec with flat keys (there are
no nested ``"category_axis"`` / ``"value_axis"`` sections; the gridline
keys apply to the value axis)::

    chart.apply_quick_layout({
        "has_title": True,
        "title_text": "ARR ($M)",
        "legend_position": "bottom",
        "has_major_gridlines": True,
    })

The valid keys are ``has_title``, ``title_text``, ``has_legend``,
``legend_position``, ``legend_in_layout``, ``has_category_axis_title``,
``category_axis_title_text``, ``has_value_axis_title``,
``value_axis_title_text``, ``has_major_gridlines`` and
``has_minor_gridlines``.  Any other key raises before the chart is
changed — :class:`ValueError` in a dict spec, :class:`TypeError` as a
keyword override — and the message suggests the closest valid key.

Missing keys leave the chart untouched so layouts compose cleanly, and
charts without category/value axes (e.g. pie) silently skip the
corresponding keys.

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
