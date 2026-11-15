"""Named chart "quick layouts" mirroring PowerPoint's gallery.

PowerPoint's *Chart Design → Quick Layout* gallery exposes 10-11 named
layout presets that toggle title / legend / axis-title / gridline
visibility in opinionated combinations.  Replicating *every* layout from
the gallery requires a couple of features we don't yet model (data
labels positioned inside bars, "best fit" pie labels), so this module
ships the subset that maps cleanly onto the existing high-level API:
title, legend (with position), axis titles, and gridlines.

Public surface::

    from power_pptx.chart.quick_layouts import (
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
``legend_position``             ``XL_LEGEND_POSITION`` member *or* its
                                lowercase string name (``"right"``, ``"left"``,
                                ``"top"``, ``"bottom"``, ``"corner"``).
``legend_in_layout``            bool — whether the legend overlaps the plot area.
``has_category_axis_title``     bool — toggle the category-axis title.
``category_axis_title_text``    str  — set category-axis title text.
``has_value_axis_title``        bool — toggle the value-axis title.
``value_axis_title_text``       str  — set value-axis title text.
``has_major_gridlines``         bool — value-axis major gridlines.
``has_minor_gridlines``         bool — value-axis minor gridlines.
==============================  ==========================================

The keys are flat: there are no nested ``"category_axis"`` /
``"value_axis"`` sections, and the gridline keys always apply to the value
axis.  A key not in the table raises :class:`ValueError` (or, for a keyword
override, :class:`TypeError`) naming the closest valid keys, so a typo is
not silently ignored.

Charts without a category axis (e.g. pie charts) silently skip the
category-axis keys; same for value-axis keys on charts without a value
axis.  This matches how PowerPoint's gallery degrades.
"""

from __future__ import annotations

from typing import Any, Mapping

from power_pptx.enum.chart import XL_LEGEND_POSITION

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


def apply_quick_layout(chart, layout, **overrides) -> None:
    """Apply a quick-layout preset to `chart`.

    `layout` is either the name of a built-in preset (see
    :func:`layout_names`) or a dict in the spec format described in the
    module docstring.  Missing spec keys are left untouched on the chart,
    so layouts can be composed.  Charts that lack a category or value
    axis silently skip the corresponding axis keys.

    Any keyword arguments are merged on top of the resolved layout — they
    override the preset where they collide.  This is the pattern for
    "use this preset, but with this title"::

        apply_quick_layout(chart, "title_legend_right", title_text="Q4 ARR")
        apply_quick_layout(
            chart, "title_axes_legend_bottom",
            value_axis_title_text="Revenue (£m)",
            has_major_gridlines=False,
        )

    Unknown keys are rejected before the chart is touched: in a dict spec
    with :class:`ValueError`, as keyword overrides with :class:`TypeError`.
    The message names the closest valid keys.
    """
    spec = _resolve_layout(layout)
    if overrides:
        unknown = set(overrides) - _VALID_SPEC_KEYS
        if unknown:
            raise TypeError(_unknown_keys_message("override(s)", unknown))
        spec.update(overrides)
    _apply_title(chart, spec)
    _apply_legend(chart, spec)
    _apply_category_axis(chart, spec)
    _apply_value_axis(chart, spec)


_VALID_SPEC_KEYS = frozenset(
    {
        "has_title",
        "title_text",
        "has_legend",
        "legend_position",
        "legend_in_layout",
        "has_category_axis_title",
        "category_axis_title_text",
        "has_value_axis_title",
        "value_axis_title_text",
        "has_major_gridlines",
        "has_minor_gridlines",
    }
)


#: hints for keys people reach for that the flat spec format does not have
_KEY_HINTS = {
    "category_axis": (
        "category-axis settings are flat keys: 'has_category_axis_title', "
        "'category_axis_title_text'"
    ),
    "value_axis": (
        "value-axis settings are flat keys: 'has_value_axis_title', "
        "'value_axis_title_text', 'has_major_gridlines', 'has_minor_gridlines'"
    ),
    "legend": "legend settings are flat keys: 'has_legend', 'legend_position', 'legend_in_layout'",
    "title": "use 'has_title' and 'title_text'",
    "tick_labels": "tick labels are not part of a quick layout; set "
    "chart.value_axis.tick_labels directly",
}


def _unknown_keys_message(what: str, unknown) -> str:
    """Describe `unknown` spec keys, with the likeliest intended key for each."""
    import difflib

    parts = []
    for key in sorted(unknown, key=str):
        hint = _KEY_HINTS.get(key) if isinstance(key, str) else None
        if hint is None and isinstance(key, str):
            close = difflib.get_close_matches(key, _VALID_SPEC_KEYS, n=2)
            if close:
                hint = "did you mean %s?" % " or ".join(repr(c) for c in close)
        parts.append("%r (%s)" % (key, hint) if hint else repr(key))
    return "unknown quick-layout %s: %s. Valid keys: %s" % (
        what,
        ", ".join(parts),
        ", ".join(sorted(_VALID_SPEC_KEYS)),
    )


def _resolve_layout(layout) -> dict[str, Any]:
    if isinstance(layout, Mapping):
        spec = dict(layout)
        unknown = set(spec) - _VALID_SPEC_KEYS
        if unknown:
            raise ValueError(_unknown_keys_message("key(s)", unknown))
        return spec
    if isinstance(layout, str):
        try:
            return dict(QUICK_LAYOUTS[layout])
        except KeyError:
            raise ValueError("unknown quick layout %r; choose from %r" % (layout, layout_names()))
    raise TypeError("layout must be a name or spec mapping, got %s" % type(layout).__name__)


def _apply_title(chart, spec: Mapping[str, Any]) -> None:
    title_text = spec.get("title_text")
    if title_text is not None:
        chart.has_title = True
        chart.chart_title.text_frame.text = title_text
    elif "has_title" in spec:
        chart.has_title = bool(spec["has_title"])


_LEGEND_POSITION_NAMES = {
    "right": XL_LEGEND_POSITION.RIGHT,
    "left": XL_LEGEND_POSITION.LEFT,
    "top": XL_LEGEND_POSITION.TOP,
    "bottom": XL_LEGEND_POSITION.BOTTOM,
    "corner": XL_LEGEND_POSITION.CORNER,
}


def _coerce_legend_position(value: Any) -> XL_LEGEND_POSITION:
    """Accept an :class:`XL_LEGEND_POSITION` member, int value, or lowercase name.

    The reference docs were inconsistent about which form was canonical
    (``"bottom"`` in prose, ``XL_LEGEND_POSITION.BOTTOM`` in code).
    Accept both at the boundary, plus the historical integer form
    (``-4107`` etc.) that ``Legend.position`` already supported via
    ``XL_LEGEND_POSITION.to_xml``, so config-driven layouts that
    serialised enum values as ints keep working.  Unknown strings or
    out-of-range integers raise :class:`ValueError`.
    """
    if isinstance(value, XL_LEGEND_POSITION):
        return value
    if isinstance(value, str):
        try:
            return _LEGEND_POSITION_NAMES[value.lower()]
        except KeyError:
            raise ValueError(
                "legend_position string must be one of %s; got %r"
                % (sorted(_LEGEND_POSITION_NAMES), value)
            ) from None
    # ``bool`` is a subclass of ``int`` — guard explicitly so
    # ``legend_position=True`` doesn't silently resolve to whichever
    # member happens to have value 1.
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            return XL_LEGEND_POSITION(value)
        except ValueError:
            raise ValueError(
                "legend_position int %r is not a valid XL_LEGEND_POSITION value" % value
            ) from None
    raise TypeError(
        "legend_position must be an XL_LEGEND_POSITION member, int value, "
        "or string name (one of %s); got %r" % (sorted(_LEGEND_POSITION_NAMES), value)
    )


def _apply_legend(chart, spec: Mapping[str, Any]) -> None:
    if "has_legend" in spec:
        chart.has_legend = bool(spec["has_legend"])

    if not chart.has_legend:
        # Don't touch position/in_layout when the legend is off — those
        # writes would silently re-add a legend element.
        return

    legend = chart.legend
    if "legend_position" in spec:
        legend.position = _coerce_legend_position(spec["legend_position"])
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
