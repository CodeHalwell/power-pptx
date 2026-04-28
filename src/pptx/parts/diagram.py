"""Diagram part objects for SmartArt diagrams."""

from __future__ import annotations

from pptx.opc.package import XmlPart


class DiagramDataPart(XmlPart):
    """Part wrapping a ``diagrams/data#.xml`` file (SmartArt data model).

    Content-type:
        ``application/vnd.openxmlformats-officedocument.drawingml.diagramData+xml``
    """


class DiagramLayoutPart(XmlPart):
    """Part wrapping a ``diagrams/layout#.xml`` file (SmartArt layout definition).

    Content-type:
        ``application/vnd.openxmlformats-officedocument.drawingml.diagramLayout+xml``
    """


class DiagramStylePart(XmlPart):
    """Part wrapping a ``diagrams/quickStyle#.xml`` file (SmartArt quick-style).

    Content-type:
        ``application/vnd.openxmlformats-officedocument.drawingml.diagramStyle+xml``
    """


class DiagramColorsPart(XmlPart):
    """Part wrapping a ``diagrams/colors#.xml`` file (SmartArt color style).

    Content-type:
        ``application/vnd.openxmlformats-officedocument.drawingml.diagramColors+xml``
    """
