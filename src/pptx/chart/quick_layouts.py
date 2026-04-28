"""Named chart "quick layouts" mirroring PowerPoint's gallery.

PowerPoint's *Chart Design → Quick Layout* gallery exposes 10-11 named
layout presets that toggle title / legend / axis-title / gridline
visibility in opinionated combinations.  Replicating *every* layout from
the gallery requires a couple of features we don't yet model (data
labels positioned inside bars, "best fit" pie labels), so this module
ships the subset that maps cleanly onto the existing high-level API:
title, legend (with position), axis titles, and gridlines.

Public surface::

    from pptx.chart.quick_layouts import (
        apply_quick_layout, layout_names, QUICK_LAYOUTS,
    )

    chart.apply_quick_layout("title_legend_right")     # convenience method on Chart
    apply_quick_layout(chart, "title_legend_right")    # functional form

A layout spec is a plain dict with any of the keys below.  Missing keys
mean "don't touch this property" so two layouts can be composed by
calling ``apply_quick_layout`` twice.

==============================  ==========================================
``has_title``                   bool — toggle the chart title.
``title_text``                  str  — set chart title text (forces ``has_title=True``).
``has_legend``                  bool — toggle the legend.
``legend_position``             ``XL_LEGEND_POSITION`` member — legend slot.
``legend_in_layout``            bool — whether the legend overlaps the plot area.
``has_category_axis_title``     bool — toggle the category-axis title.
``category_axis_title_text``    str  — set category-axis title text.
``has_value_axis_title``        bool — toggle the value-axis title.
``value_axis_title_text``       str  — set value-axis title text.
``has_major_gridlines``         bool — value-axis major gridlines.
``has_minor_gridlines``         bool — value-axis minor gridlines.
==============================  ==========================================

Charts without a category axis (e.g. pie charts) silently skip the
category-axis keys; same for value-axis keys on charts without a value
axis.  This matches how PowerPoint's gallery degrades.
"""

from __future__ import annotations

from typing import Any, Mapping

from pptx.enum.chart import XL_LEGEND_POSITION

QUICK_LAYOUTS: dict[str, dict[str, Any]] = {
    # --- Layouts 1-3 from the gallery: title + variations on legend slot --
    "title_legend_right": {
        "has_title": True,
        "has_legend": True,
        "legend_position": XL_LEGEND_POSITION.RIGHT,
        "legend_in_layout": False,
        "has_major_gridlines": True,
        "has_minor_gridlines": False,
    },
    "title_legend_bottom": {
        "has_title": True,
        "has_legend": True,
        "legend_position": XL_LEGEND_POSITION.BOTTOM,
        "legend_in_layout": False,
        "has_major_gridlines": True,
        "has_minor_gridlines": False,
    },
    "title_legend_top": {
        "has_title": True,
        "has_legend": True,
        "legend_position": XL_LEGEND_POSITION.TOP,
        "legend_in_layout": False,
        "has_major_gridlines": True,
        "has_minor_gridlines": False,
    },
    "title_legend_left": {
        "has_title": True,
        "has_legend": True,
        "legend_position": XL_LEGEND_POSITION.LEFT,
        "legend_in_layout": False,
        "has_major_gridlines": True,
        "has_minor_gridlines": False,
    },
    "title_no_legend": {
        "has_title": True,
        "has_legend": False,
        "has_major_gridlines": True,
        "has_minor_gridlines": False,
    },
    "no_title_no_legend": {
        "has_title": False,
        "has_legend": False,
        "has_major_gridlines": True,
        "has_minor_gridlines": False,
    },
    # --- Layouts with axis titles -----------------------------------------
    "title_axes_legend_right": {
        "has_title": True,
        "has_legend": True,
        "legend_position": XL_LEGEND_POSITION.RIGHT,
        "legend_in_layout": False,
        "has_category_axis_title": True,
        "has_value_axis_title": True,
        "has_major_gridlines": True,
        "has_minor_gridlines": False,
    },
    "title_axes_legend_bottom": {
        "has_title": True,
        "has_legend": True,
        "legend_position": XL_LEGEND_POSITION.BOTTOM,
        "legend_in_layout": False,
        "has_category_axis_title": True,
        "has_value_axis_title": True,
        "has_major_gridlines": True,
        "has_minor_gridlines": False,
    },
    # --- Minimal / dense -------------------------------------------------
    "minimal": {
        "has_title": False,
        "has_legend": False,
        "has_major_gridlines": False,
        "has_minor_gridlines": False,
    },
    "dense": {
        "has_title": True,
        "has_legend": True,
        "legend_position": XL_LEGEND_POSITION.RIGHT,
        "legend_in_layout": False,
        "has_major_gridlines": True,
        "has_minor_gridlines": True,
    },
}


def layout_names() -> tuple[str, ...]:
    """Return the names of the built-in quick layouts, in declaration order."""
    return tuple(QUICK_LAYOUTS.keys())


def apply_quick_layout(chart, layout) -> None:
    """Apply a quick-layout preset to `chart`.

    `layout` is either the name of a built-in preset (see
    :func:`layout_names`) or a dict in the spec format described in the
    module docstring.  Missing spec keys are left untouched on the chart,
    so layouts can be composed.  Charts that lack a category or value
    axis silently skip the corresponding axis keys.
    """
    spec = _resolve_layout(layout)
    _apply_title(chart, spec)
    _apply_legend(chart, spec)
    _apply_category_axis(chart, spec)
    _apply_value_axis(chart, spec)


def _resolve_layout(layout) -> dict[str, Any]:
    if isinstance(layout, Mapping):
        return dict(layout)
    if isinstance(layout, str):
        try:
            return dict(QUICK_LAYOUTS[layout])
        except KeyError:
            raise ValueError(
                "unknown quick layout %r; choose from %r" % (layout, layout_names())
            )
    raise TypeError(
        "layout must be a name or spec mapping, got %s" % type(layout).__name__
    )


def _apply_title(chart, spec: Mapping[str, Any]) -> None:
    title_text = spec.get("title_text")
    if title_text is not None:
        chart.has_title = True
        chart.chart_title.text_frame.text = title_text
    elif "has_title" in spec:
        chart.has_title = bool(spec["has_title"])


def _apply_legend(chart, spec: Mapping[str, Any]) -> None:
    if "has_legend" in spec:
        chart.has_legend = bool(spec["has_legend"])

    if not chart.has_legend:
        # Don't touch position/in_layout when the legend is off — those
        # writes would silently re-add a legend element.
        return

    legend = chart.legend
    if "legend_position" in spec:
        legend.position = spec["legend_position"]
    if "legend_in_layout" in spec:
        legend.include_in_layout = bool(spec["legend_in_layout"])


def _apply_category_axis(chart, spec: Mapping[str, Any]) -> None:
    cat_keys = (
        "has_category_axis_title",
        "category_axis_title_text",
    )
    if not any(k in spec for k in cat_keys):
        return
    try:
        axis = chart.category_axis
    except (ValueError, NotImplementedError):
        # Pie/doughnut charts have no category axis — nothing to do.
        return
    title_text = spec.get("category_axis_title_text")
    if title_text is not None:
        axis.has_title = True
        axis.axis_title.text_frame.text = title_text
    elif "has_category_axis_title" in spec:
        axis.has_title = bool(spec["has_category_axis_title"])


def _apply_value_axis(chart, spec: Mapping[str, Any]) -> None:
    val_keys = (
        "has_value_axis_title",
        "value_axis_title_text",
        "has_major_gridlines",
        "has_minor_gridlines",
    )
    if not any(k in spec for k in val_keys):
        return
    try:
        axis = chart.value_axis
    except (ValueError, NotImplementedError):
        return
    title_text = spec.get("value_axis_title_text")
    if title_text is not None:
        axis.has_title = True
        axis.axis_title.text_frame.text = title_text
    elif "has_value_axis_title" in spec:
        axis.has_title = bool(spec["has_value_axis_title"])
    if "has_major_gridlines" in spec:
        axis.has_major_gridlines = bool(spec["has_major_gridlines"])
    if "has_minor_gridlines" in spec:
        axis.has_minor_gridlines = bool(spec["has_minor_gridlines"])
