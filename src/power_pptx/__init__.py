"""Initialization module for power-pptx package."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import power_pptx.exc as exceptions
from power_pptx.api import Presentation
from power_pptx.opc.constants import CONTENT_TYPE as CT
from power_pptx.opc.package import PartFactory
from power_pptx.parts.chart import ChartPart
from power_pptx.parts.coreprops import CorePropertiesPart
from power_pptx.parts.diagram import (
    DiagramColorsPart,
    DiagramDataPart,
    DiagramLayoutPart,
    DiagramStylePart,
)
from power_pptx.parts.image import ImagePart
from power_pptx.parts.media import MediaPart
from power_pptx.parts.presentation import PresentationPart
from power_pptx.parts.slide import (
    NotesMasterPart,
    NotesSlidePart,
    SlideLayoutPart,
    SlideMasterPart,
    SlidePart,
    ThemePart,
)

if TYPE_CHECKING:
    from power_pptx.opc.package import Part

__version__ = "2.1.1"

sys.modules["power_pptx.exceptions"] = exceptions
del sys

__all__ = ["Presentation"]

content_type_to_part_class_map: dict[str, type[Part]] = {
    CT.PML_PRESENTATION_MAIN: PresentationPart,
    CT.PML_PRES_MACRO_MAIN: PresentationPart,
    CT.PML_TEMPLATE_MAIN: PresentationPart,
    CT.PML_SLIDESHOW_MAIN: PresentationPart,
    CT.OPC_CORE_PROPERTIES: CorePropertiesPart,
    CT.PML_NOTES_MASTER: NotesMasterPart,
    CT.PML_NOTES_SLIDE: NotesSlidePart,
    CT.PML_SLIDE: SlidePart,
    CT.PML_SLIDE_LAYOUT: SlideLayoutPart,
    CT.PML_SLIDE_MASTER: SlideMasterPart,
    CT.OFC_THEME: ThemePart,
    CT.DML_CHART: ChartPart,
    CT.DML_DIAGRAM_DATA: DiagramDataPart,
    CT.DML_DIAGRAM_LAYOUT: DiagramLayoutPart,
    CT.DML_DIAGRAM_STYLE: DiagramStylePart,
    CT.DML_DIAGRAM_COLORS: DiagramColorsPart,
    CT.BMP: ImagePart,
    CT.GIF: ImagePart,
    CT.JPEG: ImagePart,
    CT.MS_PHOTO: ImagePart,
    CT.PNG: ImagePart,
    CT.TIFF: ImagePart,
    CT.X_EMF: ImagePart,
    CT.X_WMF: ImagePart,
    CT.ASF: MediaPart,
    CT.AVI: MediaPart,
    CT.MOV: MediaPart,
    CT.MP4: MediaPart,
    CT.MPG: MediaPart,
    CT.MS_VIDEO: MediaPart,
    CT.SWF: MediaPart,
    CT.VIDEO: MediaPart,
    CT.WMV: MediaPart,
    CT.X_MS_VIDEO: MediaPart,
    # -- accommodate "image/jpg" as an alias for "image/jpeg" --
    "image/jpg": ImagePart,
}

PartFactory.part_type_for.update(content_type_to_part_class_map)

del (
    ChartPart,
    CorePropertiesPart,
    DiagramColorsPart,
    DiagramDataPart,
    DiagramLayoutPart,
    DiagramStylePart,
    ImagePart,
    MediaPart,
    SlidePart,
    SlideLayoutPart,
    SlideMasterPart,
    ThemePart,
    PresentationPart,
    CT,
    PartFactory,
)
