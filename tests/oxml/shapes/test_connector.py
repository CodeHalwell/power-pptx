"""Unit-test suite for `power_pptx.oxml.shapes.connector` module."""

from __future__ import annotations

import pytest

from power_pptx.oxml.shapes.connector import CT_Connector


class DescribeCT_Connector(object):
    """Unit-test suite for `power_pptx.oxml.shapes.connector.CT_Connector` objects."""

    @pytest.mark.parametrize(
        "name", ['Link "A"', "R&D", "Q<4> results", 'it\'s 100% & "done"', "tabbed\tname"]
    )
    def it_escapes_the_name_of_a_new_cxnSp(self, name):
        cxnSp = CT_Connector.new_cxnSp(9, name, "line", 1, 2, 3, 4, False, False)
        assert cxnSp.xpath("p:nvCxnSpPr/p:cNvPr")[0].get("name") == name
