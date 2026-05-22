"""Initialization module for power-pptx package."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import power_pptx.exc as exceptions
from power_pptx.api import Presentation
from power_pptx.audit import AuditReport, audit
from power_pptx.geometry import BBox
from power_pptx.design.components import (
    ArticleCard,
    Gauge,
    KpiCard,
    ProgressBar,
    StatStrip,
    StatusPill,
    add_article_card,
    add_gauge,
    add_kpi_card,
    add_progress_bar,
    add_stat_strip,
    add_status_pill,
)
from power_pptx.design.figures import (
    FigureBackendUnavailable,
    add_html_figure,
    add_matplotlib_figure,
    add_plotly_figure,
    add_svg_figure,
)
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

__version__ = "2.7.0"

sys.modules["power_pptx.exceptions"] = exceptions
del sys

__all__ = [
    "Presentation",
    # First-class rectangular region value object (immutable, splattable
    # into add_shape / add_textbox / add_picture).
    "BBox",
    # One-call deck audit (lint + picture + empty-slide + font + size).
    "audit",
    "AuditReport",
    # Figure adapters — embed Plotly / Matplotlib / SVG / HTML output as
    # slide pictures. Third-party deps are imported lazily on first call.
    "add_plotly_figure",
    "add_matplotlib_figure",
    "add_svg_figure",
    "add_html_figure",
    "FigureBackendUnavailable",
    # Shape-level building blocks built on the design tokens.
    "add_kpi_card",
    "add_progress_bar",
    "add_gauge",
    "add_status_pill",
    "add_stat_strip",
    "add_article_card",
    "KpiCard",
    "ProgressBar",
    "Gauge",
    "StatusPill",
    "StatStrip",
    "ArticleCard",
]

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
