# pyright: reportPrivateUsage=false

"""Unit-test suite for `power_pptx.chart.quick_layouts`."""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx.chart.data import CategoryChartData
from power_pptx.chart.quick_layouts import (
    _VALID_SPEC_KEYS,
    QUICK_LAYOUTS,
    apply_quick_layout,
    layout_names,
)
from power_pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from power_pptx.util import Inches


def _make_column_chart(series=("S1", "S2")):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    data = CategoryChartData()
    data.categories = ["A", "B", "C"]
    for name in series:
        data.add_series(name, (1, 2, 3))
    gframe = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(1),
        Inches(1),
        Inches(6),
        Inches(4),
        data,
    )
    return gframe.chart


def _make_pie_chart():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    data = CategoryChartData()
    data.categories = ["A", "B"]
    data.add_series("S1", (1, 2))
    gframe = slide.shapes.add_chart(
        XL_CHART_TYPE.PIE, Inches(1), Inches(1), Inches(6), Inches(4), data
    )
    return gframe.chart


class DescribeApplyQuickLayout:
    def it_applies_a_named_layout_with_legend_on_the_right(self):
        chart = _make_column_chart()

        apply_quick_layout(chart, "title_legend_right")

        assert chart.has_title is True
        assert chart.has_legend is True
        assert chart.legend.position == XL_LEGEND_POSITION.RIGHT
        assert chart.value_axis.has_major_gridlines is True
        assert chart.value_axis.has_minor_gridlines is False

    def it_applies_minimal_layout(self):
        chart = _make_column_chart()

        apply_quick_layout(chart, "minimal")

        assert chart.has_title is False
        assert chart.has_legend is False
        assert chart.value_axis.has_major_gridlines is False
        assert chart.value_axis.has_minor_gridlines is False

    def it_applies_dense_layout_with_minor_gridlines(self):
        chart = _make_column_chart()

        apply_quick_layout(chart, "dense")

        assert chart.has_title is True
        assert chart.has_legend is True
        assert chart.value_axis.has_major_gridlines is True
        assert chart.value_axis.has_minor_gridlines is True

    def it_can_set_title_text_via_spec(self):
        chart = _make_column_chart()

        apply_quick_layout(chart, {"title_text": "Q4 Revenue"})

        assert chart.has_title is True
        assert chart.chart_title.text_frame.text == "Q4 Revenue"

    def it_can_set_axis_titles_via_spec(self):
        chart = _make_column_chart()

        apply_quick_layout(
            chart,
            {
                "category_axis_title_text": "Quarter",
                "value_axis_title_text": "Revenue (USD)",
            },
        )

        assert chart.category_axis.has_title is True
        assert chart.category_axis.axis_title.text_frame.text == "Quarter"
        assert chart.value_axis.has_title is True
        assert chart.value_axis.axis_title.text_frame.text == "Revenue (USD)"

    def it_supports_composition(self):
        chart = _make_column_chart()

        apply_quick_layout(chart, "title_legend_right")
        apply_quick_layout(chart, {"has_minor_gridlines": True})

        assert chart.has_legend is True  # preserved from first layout
        assert chart.legend.position == XL_LEGEND_POSITION.RIGHT
        assert chart.value_axis.has_minor_gridlines is True

    def it_silently_skips_axis_keys_on_pie_charts(self):
        chart = _make_pie_chart()

        # Pie has no value/category axis; the call should still succeed.
        apply_quick_layout(chart, "title_axes_legend_right")

        assert chart.has_title is True
        assert chart.has_legend is True

    def it_does_not_touch_legend_position_when_legend_is_off(self):
        chart = _make_column_chart()
        chart.has_legend = False

        # `title_no_legend` doesn't set legend_position; legend should stay off.
        apply_quick_layout(chart, "title_no_legend")

        assert chart.has_legend is False
        assert chart.legend is None

    def it_raises_for_unknown_layout_name(self):
        chart = _make_column_chart()

        with pytest.raises(ValueError, match="unknown quick layout"):
            apply_quick_layout(chart, "not_a_real_layout")

    def it_raises_for_invalid_layout_type(self):
        chart = _make_column_chart()

        with pytest.raises(TypeError, match="must be a name or spec"):
            apply_quick_layout(chart, 42)

    def it_is_exposed_as_a_method_on_Chart(self):
        chart = _make_column_chart()

        chart.apply_quick_layout("title_legend_bottom")

        assert chart.legend.position == XL_LEGEND_POSITION.BOTTOM

    def it_accepts_legend_position_as_lowercase_string(self):
        # Regression for IMPROVEMENT_PLAN.md item 3: ``legend_position``
        # used to require the enum and crashed on the lowercase string
        # form that the reference docs documented.
        chart = _make_column_chart()

        apply_quick_layout(chart, {"has_legend": True, "legend_position": "bottom"})

        assert chart.legend.position == XL_LEGEND_POSITION.BOTTOM

    def it_rejects_unknown_legend_position_strings(self):
        chart = _make_column_chart()

        with pytest.raises(ValueError, match="legend_position string must be one of"):
            apply_quick_layout(chart, {"has_legend": True, "legend_position": "diagonal"})

    def it_accepts_legend_position_as_integer_value(self):
        # Regression for codex review on PR #27: ``legend.position``
        # historically accepted both enum members and their integer
        # values (via ``XL_LEGEND_POSITION.to_xml``).  Config-driven
        # layouts that serialise enum values as ints must keep working.
        chart = _make_column_chart()

        apply_quick_layout(
            chart,
            {"has_legend": True, "legend_position": int(XL_LEGEND_POSITION.BOTTOM)},
        )

        assert chart.legend.position == XL_LEGEND_POSITION.BOTTOM

    def it_rejects_out_of_range_legend_position_integers(self):
        chart = _make_column_chart()

        with pytest.raises(ValueError, match="not a valid XL_LEGEND_POSITION"):
            apply_quick_layout(chart, {"has_legend": True, "legend_position": 99999})


class DescribeQuickLayoutSpecKeys:
    """A dict spec is validated like keyword overrides are: a stray key is an error."""

    def it_rejects_an_unknown_key_in_a_dict_spec(self):
        chart = _make_column_chart()

        with pytest.raises(TypeError, match="totally_bogus_key"):
            apply_quick_layout(chart, {"has_title": True, "totally_bogus_key": 1})

    def it_rejects_an_unknown_key_through_the_Chart_method(self):
        chart = _make_column_chart()

        with pytest.raises(TypeError, match="totally_bogus_key"):
            chart.apply_quick_layout({"has_title": True, "totally_bogus_key": 1})

    def it_names_every_unknown_key_and_lists_the_valid_ones(self):
        chart = _make_column_chart()

        with pytest.raises(TypeError) as e:
            apply_quick_layout(chart, {"bogus_b": 1, "has_title": True, "bogus_a": 2})

        message = str(e.value)
        assert "['bogus_a', 'bogus_b']" in message
        for key in _VALID_SPEC_KEYS:
            assert key in message

    def it_changes_nothing_on_the_chart_when_a_key_is_unknown(self):
        chart = _make_column_chart()
        chart.has_title = False
        chart.has_legend = False

        with pytest.raises(TypeError):
            apply_quick_layout(
                chart, {"has_title": True, "has_legend": True, "totally_bogus_key": 1}
            )

        assert chart.has_title is False
        assert chart.has_legend is False

    @pytest.mark.parametrize("key", ["category_axis", "value_axis"])
    def it_rejects_the_nested_axis_specs_it_never_read(self, key):
        # -- charts.md used to show {"value_axis": {"has_major_gridlines": False}}; the applier
        # -- never looked at it, so the call silently did nothing --
        chart = _make_column_chart()
        chart.value_axis.has_major_gridlines = True

        with pytest.raises(TypeError, match=key) as e:
            apply_quick_layout(chart, {key: {"has_major_gridlines": False}})

        assert "nested" in str(e.value)
        assert "has_major_gridlines" in str(e.value)
        assert chart.value_axis.has_major_gridlines is True

    def it_rejects_a_non_string_key(self):
        chart = _make_column_chart()

        with pytest.raises(TypeError, match="unknown quick-layout spec key"):
            apply_quick_layout(chart, {1: "x"})

    @pytest.mark.parametrize("key", sorted(_VALID_SPEC_KEYS))
    def it_accepts_every_documented_key(self, key):
        values = {
            "has_title": True,
            "title_text": "Q4",
            "has_legend": True,
            "legend_position": "bottom",
            "legend_in_layout": False,
            "has_category_axis_title": True,
            "category_axis_title_text": "Quarter",
            "has_value_axis_title": True,
            "value_axis_title_text": "Revenue",
            "has_major_gridlines": False,
            "has_minor_gridlines": True,
        }
        assert set(values) == _VALID_SPEC_KEYS
        chart = _make_column_chart()

        apply_quick_layout(chart, {key: values[key]})

    def it_applies_the_flat_keys_the_docs_show(self):
        chart = _make_column_chart()
        chart.value_axis.has_major_gridlines = True

        apply_quick_layout(
            chart,
            {
                "has_title": True,
                "title_text": "ARR ($M)",
                "has_legend": True,
                "legend_position": "bottom",
                "has_major_gridlines": False,
            },
        )

        assert chart.chart_title.text_frame.text == "ARR ($M)"
        assert chart.legend.position == XL_LEGEND_POSITION.BOTTOM
        assert chart.value_axis.has_major_gridlines is False

    def it_still_rejects_an_unknown_override_with_the_same_error_type(self):
        chart = _make_column_chart()

        with pytest.raises(TypeError, match="unknown quick-layout override"):
            apply_quick_layout(chart, "minimal", totally_bogus_key=1)

    def it_checks_the_overrides_of_a_dict_spec_too(self):
        chart = _make_column_chart()

        with pytest.raises(TypeError, match="totally_bogus_key"):
            apply_quick_layout(chart, {"has_title": True}, totally_bogus_key=1)

    def it_keeps_every_built_in_preset_within_the_valid_keys(self):
        for name, spec in QUICK_LAYOUTS.items():
            assert set(spec) <= _VALID_SPEC_KEYS, name


class DescribeLayoutNames:
    def it_returns_all_built_in_names(self):
        names = layout_names()
        assert isinstance(names, tuple)
        assert set(names) == set(QUICK_LAYOUTS.keys())

    def it_preserves_declaration_order(self):
        # Make sure the declaration-order contract is testable; first
        # entry should be the most generic preset.
        assert layout_names()[0] == "title_legend_right"
