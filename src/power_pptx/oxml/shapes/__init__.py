"""Base shape-related objects such as BaseShape."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing_extensions import TypeAlias

    from power_pptx.oxml.shapes.autoshape import CT_Shape
    from power_pptx.oxml.shapes.connector import CT_Connector
    from power_pptx.oxml.shapes.graphfrm import CT_GraphicalObjectFrame
    from power_pptx.oxml.shapes.groupshape import CT_GroupShape
    from power_pptx.oxml.shapes.picture import CT_Picture


ShapeElement: TypeAlias = (
    "CT_Connector | CT_GraphicalObjectFrame |  CT_GroupShape | CT_Picture | CT_Shape"
)
