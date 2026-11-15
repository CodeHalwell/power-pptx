"""Unit tests for ``from_html`` argument checks (no browser needed)."""

from __future__ import annotations

import re

import pytest

from power_pptx.compose import from_html


class DescribeFromHtmlArguments:
    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"fit": "fill"}, "fit must be 'contain', 'cover', or 'stretch'"),
            ({"fit": "fill", "mode": "native"}, "fit must be 'contain', 'cover', or 'stretch'"),
            ({"mode": "native"}, "mode must be 'capture' or 'hybrid'"),
            (
                {"mode": "hybrid", "fit": "cover"},
                "hybrid mode requires fit='contain' and a section selector",
            ),
            (
                {"mode": "hybrid", "selector": None},
                "hybrid mode requires fit='contain' and a section selector",
            ),
        ],
    )
    def it_rejects_an_invalid_option_before_rendering(self, kwargs, message):
        with pytest.raises(ValueError, match=f"^{re.escape(message)}$"):
            from_html("<section data-slide></section>", **kwargs)
