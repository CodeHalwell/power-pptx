"""Non-finite numbers in chart series data.

`None` in a series means "no value for this point" and is left out of the chart XML and written
as a blank worksheet cell.  NaN, which is how pandas and numpy mark a missing value, means the
same thing and is treated the same way.  Infinity is not a value a chart can plot and is not a
gap either, so it is refused with an error that says where it is.

Both writers that read a series, `power_pptx.chart.xmlwriter` (the chart XML) and
`power_pptx.chart.xlsx` (the embedded workbook), pass what they read through
:func:`plottable_values`, so they agree.
"""

from __future__ import annotations

import math
from typing import Any, Sequence


def _non_finite_kind(value: Any) -> str | None:
    """``"nan"`` or ``"inf"`` when `value` is a number that is NaN or infinite, else |None|."""
    # -- `float("nan")` parses a string, but a string is not a data value --
    if value is None or isinstance(value, (str, bytes)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if math.isnan(number):
        return "nan"
    if math.isinf(number):
        return "inf"
    return None


def plottable_values(series: Any, values: Sequence[Any], label: str) -> Sequence[Any]:
    """`values` of `series` with each NaN turned into |None|, the "no value" marker.

    `label` says which of the series' values these are ("value", "X value", "Y value" or
    "bubble size"), for the error message.  Raises |ValueError| naming the series, the point
    index and `label` for the first infinite value.

    `values` itself is returned, not a copy, when there is nothing to change.
    """
    cleaned: list[Any] | None = None
    for idx, value in enumerate(values):
        kind = _non_finite_kind(value)
        if kind is None:
            continue
        if kind == "inf":
            raise ValueError(
                "series %r, point index %d: %s is infinite (%r), which cannot be plotted; use a "
                "finite number, or None (or NaN) to leave a gap" % (series.name, idx, label, value)
            )
        if cleaned is None:
            cleaned = list(values)
        cleaned[idx] = None
    return values if cleaned is None else cleaned
