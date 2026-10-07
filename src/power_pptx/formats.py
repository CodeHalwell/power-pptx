"""Number-format string helpers for chart data labels and table cells.

Setting a chart data label to a currency or percentage format
otherwise requires Excel's format-string syntax verbatim::

    plot.data_labels.number_format = '"$"#,##0'

That syntax is leaky, easy to typo, and hostile to anyone who hasn't
written Excel macros. The helpers here return the right format string
for the common semantic choices and keep Excel syntax behind the
abstraction:

    from power_pptx.formats import currency, percent, date, decimal, scientific

    plot.data_labels.number_format = currency("$", decimals=0)   # "$"#,##0
    plot.data_labels.number_format = currency("£", decimals=2)   # "£"#,##0.00
    plot.data_labels.number_format = percent(decimals=1)         # 0.0%
    plot.data_labels.number_format = decimal(decimals=2)         # #,##0.00
    plot.data_labels.number_format = date("YYYY-MM-DD")          # yyyy-MM-dd
    plot.data_labels.number_format = scientific(decimals=2)      # 0.00E+00

The strings are plain ``str`` so they round-trip through
``data_labels.number_format`` exactly like a hand-written format,
and remain editable through Excel's "Format Cells" dialog.
"""

from __future__ import annotations

from typing import Final

__all__ = ("currency", "percent", "decimal", "scientific", "date", "thousands")


_DATE_TOKEN_MAP: Final[dict[str, str]] = {
    # Map common UI-style date tokens to Excel's lowercase form.
    # ``YYYY``-style is what most authoring guides write; Excel
    # canonicalises to lowercase except for ``M`` vs ``m`` (where
    # case decides "month" vs "minute"). This helper preserves that
    # distinction by leaving ``M`` / ``MM`` / ``MMM`` / ``MMMM``
    # capitalised in the output — Excel still reads them as months
    # in a date context.
    "YYYY": "yyyy",
    "YY": "yy",
    "DDDD": "dddd",
    "DDD": "ddd",
    "DD": "dd",
    "D": "d",
    "HH": "hh",
    "H": "h",
    "SS": "ss",
    "S": "s",
}


def currency(symbol: str = "$", *, decimals: int = 0) -> str:
    """Return a currency format string with `symbol` and `decimals` digits.

    `symbol` is wrapped in double quotes so multi-character codes
    (``"USD "``, ``"EUR "``) work too. ``decimals`` must be ``>= 0``.
    """
    if decimals < 0:
        raise ValueError(f"decimals must be >= 0; got {decimals}")
    if not isinstance(symbol, str):  # type: ignore[redundant-expr]
        raise TypeError(f"symbol must be str; got {type(symbol).__name__}")
    base = f'"{symbol}"#,##0'
    if decimals == 0:
        return base
    return base + "." + ("0" * decimals)


def percent(*, decimals: int = 0) -> str:
    """Return a percentage format string.

    A value of ``0.27`` renders as ``27%`` (no decimals) or ``27.0%``
    (one decimal). Excel multiplies by 100 implicitly when the
    format ends with ``%``, matching user expectation.
    """
    if decimals < 0:
        raise ValueError(f"decimals must be >= 0; got {decimals}")
    if decimals == 0:
        return "0%"
    return "0." + ("0" * decimals) + "%"


def decimal(*, decimals: int = 2, thousands_sep: bool = True) -> str:
    """Return a fixed-decimal numeric format.

    ``decimals=2, thousands_sep=True`` → ``#,##0.00``;
    ``decimals=0, thousands_sep=False`` → ``0``.
    """
    if decimals < 0:
        raise ValueError(f"decimals must be >= 0; got {decimals}")
    base = "#,##0" if thousands_sep else "0"
    if decimals == 0:
        return base
    return base + "." + ("0" * decimals)


def thousands() -> str:
    """Return ``#,##0`` — integer with thousands separator."""
    return "#,##0"


def scientific(*, decimals: int = 2) -> str:
    """Return a scientific-notation format with `decimals` digits."""
    if decimals < 0:
        raise ValueError(f"decimals must be >= 0; got {decimals}")
    if decimals == 0:
        return "0E+00"
    return "0." + ("0" * decimals) + "E+00"


def date(pattern: str = "YYYY-MM-DD") -> str:
    """Return an Excel-style date format from a UI-style `pattern`.

    Accepts the upper-case tokens authors typically write
    (``YYYY``, ``MM``, ``DD``, ``HH``, ``SS``) and lowercases them
    where Excel's parser needs lowercase. ``M`` / ``MM`` / ``MMM``
    / ``MMMM`` (month) are intentionally left capitalised — Excel
    reads them as months in a date context, while their lowercase
    form is "minutes".

    Examples::

        date()                    # "yyyy-MM-dd" (default ISO date)
        date("YYYY-MM-DD HH:SS")   # "yyyy-MM-dd hh:ss"  -- "MM" stays
                                   # capitalised so Excel reads it
                                   # as month, not minutes
        date("MMM YYYY")          # "MMM yyyy"
    """
    if not isinstance(pattern, str):  # type: ignore[redundant-expr]
        raise TypeError(f"pattern must be str; got {type(pattern).__name__}")
    out = pattern
    # Apply replacements longest-first so YYYY isn't shadowed by YY.
    for src, dst in sorted(_DATE_TOKEN_MAP.items(), key=lambda kv: -len(kv[0])):
        out = out.replace(src, dst)
    return out
