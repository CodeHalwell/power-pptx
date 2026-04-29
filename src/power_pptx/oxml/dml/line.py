"""lxml custom element classes for DrawingML line-related XML elements."""

from __future__ import annotations

from power_pptx.enum.dml import MSO_LINE_DASH_STYLE
from power_pptx.oxml.xmlchemy import BaseOxmlElement, OptionalAttribute


class CT_PresetLineDashProperties(BaseOxmlElement):
    """`a:prstDash` custom element class"""

    val = OptionalAttribute("val", MSO_LINE_DASH_STYLE)
