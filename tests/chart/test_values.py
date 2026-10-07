# pyright: reportPrivateUsage=false

"""Unit-test suite for `power_pptx.chart._values` module."""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from power_pptx.chart._values import plottable_values


class _Series:
    """The only thing the helper asks of a series is its name."""

    def __init__(self, name):
        self.name = name


class DescribePlottableValues:
    def it_returns_the_values_it_was_given_when_nothing_needs_changing(self):
        values = (1, 2.5, None, -3, 0, True)

        assert plottable_values(_Series("S"), values, "value") is values

    @pytest.mark.parametrize(
        "nan",
        [float("nan"), math.nan, Decimal("NaN"), -float("nan")],
    )
    def it_turns_a_NaN_into_a_gap(self, nan):
        values = [1.0, nan, 3.0]

        assert plottable_values(_Series("S"), values, "value") == [1.0, None, 3.0]

    def it_does_not_modify_the_sequence_it_was_given(self):
        values = [1.0, float("nan"), 3.0]

        plottable_values(_Series("S"), values, "value")

        assert math.isnan(values[1])

    def it_treats_NaN_exactly_like_None(self):
        values = (float("nan"), None, 1.0, float("nan"))

        assert plottable_values(_Series("S"), values, "value") == [None, None, 1.0, None]

    def it_recognises_the_NaN_of_numpy(self):
        np = pytest.importorskip("numpy")

        values = [np.float64("nan"), np.float32("nan"), np.nan, np.float64(2.0)]

        assert plottable_values(_Series("S"), values, "value") == [None, None, None, 2.0]

    @pytest.mark.parametrize(
        ("bad", "word"),
        [
            (float("inf"), "infinite"),
            (float("-inf"), "infinite"),
            (Decimal("Infinity"), "infinite"),
            (Decimal("-Infinity"), "infinite"),
        ],
    )
    def but_it_refuses_an_infinite_value(self, bad, word):
        with pytest.raises(ValueError, match=word):
            plottable_values(_Series("S"), [1.0, bad], "value")

    def it_names_the_series_the_point_index_and_the_value_kind_when_it_refuses(self):
        with pytest.raises(ValueError) as e:
            plottable_values(_Series("Revenue"), [1.0, 2.0, float("-inf")], "Y value")

        message = str(e.value)
        assert "series 'Revenue'" in message
        assert "point index 2" in message
        assert "Y value" in message
        assert "-inf" in message

    def it_reports_the_first_infinite_value(self):
        with pytest.raises(ValueError, match="point index 1"):
            plottable_values(_Series("S"), [1.0, float("inf"), float("inf")], "value")

    def it_refuses_an_infinite_value_even_next_to_a_NaN(self):
        with pytest.raises(ValueError, match="point index 2"):
            plottable_values(_Series("S"), [float("nan"), 1.0, float("inf")], "value")

    def it_does_not_mistake_a_string_for_a_number(self):
        # -- `float("nan")` and `float("inf")` parse these, but a string is not a data value --
        values = ["nan", "inf", "1.5"]

        assert plottable_values(_Series("S"), values, "value") is values

    def it_leaves_alone_values_it_cannot_convert_to_a_float(self):
        marker = object()
        values = [marker, None, 2]

        assert plottable_values(_Series("S"), values, "value") is values

    def it_copes_with_integers_too_large_for_a_float(self):
        values = [10**400, 1]

        assert plottable_values(_Series("S"), values, "value") is values
