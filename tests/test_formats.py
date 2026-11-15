"""Unit tests for :mod:`power_pptx.formats`."""

from __future__ import annotations

import pytest

from power_pptx import formats as fmt


class DescribeCurrency:
    @pytest.mark.parametrize(
        ("symbol", "decimals", "expected"),
        [
            ("$", 0, '"$"#,##0'),
            ("$", 2, '"$"#,##0.00'),
            ("£", 0, '"£"#,##0'),
            ("EUR ", 0, '"EUR "#,##0'),
        ],
    )
    def it_emits_excel_currency_format(self, symbol, decimals, expected):
        assert fmt.currency(symbol, decimals=decimals) == expected

    def it_rejects_negative_decimals(self):
        with pytest.raises(ValueError, match="decimals must be"):
            fmt.currency(decimals=-1)


class DescribePercent:
    @pytest.mark.parametrize(
        ("decimals", "expected"),
        [(0, "0%"), (1, "0.0%"), (3, "0.000%")],
    )
    def it_emits_excel_percent_format(self, decimals, expected):
        assert fmt.percent(decimals=decimals) == expected


class DescribeDecimal:
    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            ({"decimals": 0}, "#,##0"),
            ({"decimals": 2}, "#,##0.00"),
            ({"decimals": 0, "thousands_sep": False}, "0"),
            ({"decimals": 3, "thousands_sep": False}, "0.000"),
        ],
    )
    def it_emits_a_fixed_decimal_format(self, kwargs, expected):
        assert fmt.decimal(**kwargs) == expected


class DescribeScientific:
    @pytest.mark.parametrize(
        ("decimals", "expected"),
        [(0, "0E+00"), (2, "0.00E+00")],
    )
    def it_emits_excel_scientific_format(self, decimals, expected):
        assert fmt.scientific(decimals=decimals) == expected


class DescribeDate:
    def it_lowercases_known_tokens(self):
        assert fmt.date("YYYY-MM-DD") == "yyyy-MM-dd"

    def it_preserves_uppercase_M_for_months(self):
        # Excel's "M" vs "m" distinguishes month vs minute. Date()
        # leaves capital M alone so users don't accidentally render
        # minutes when they mean months.
        out = fmt.date("MMM YYYY")
        assert "MMM" in out
        assert out.startswith("MMM ")

    def it_passes_through_unknown_text_verbatim(self):
        assert fmt.date("YYYY 'Q'Q") == "yyyy 'Q'Q"


class DescribeThousands:
    def it_returns_the_canonical_integer_format(self):
        assert fmt.thousands() == "#,##0"
