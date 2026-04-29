# Configuration file for the Sphinx documentation builder.
#
# Originally created for python-pptx by Steve Canny in 2012; updated for
# the power-pptx fork in 2026.

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(".."))

from power_pptx import __version__  # noqa: E402

# -- Project information -----------------------------------------------------

project = "power-pptx"
copyright = "2012, 2013, Steve Canny; 2026, Daniel Halwell"
author = "Daniel Halwell"

version = __version__
release = __version__


# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx.ext.todo",
    "sphinx.ext.coverage",
]

templates_path = ["_templates"]
source_suffix = ".rst"
master_doc = "index"
exclude_patterns = [".build", "_build"]
pygments_style = "sphinx"

# -- Autodoc options ---------------------------------------------------------

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_member_order = "bysource"
autodoc_typehints = "description"

# -- Intersphinx -------------------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# -- Substitutions used across the documentation -----------------------------

rst_epilog = """
.. |pp| replace:: power-pptx

.. |str| replace:: :class:`str`
.. |int| replace:: :class:`int`
.. |float| replace:: :class:`float`
.. |list| replace:: :class:`list`
.. |bool| replace:: :class:`bool`
.. |bytes| replace:: :class:`bytes`
.. |True| replace:: :class:`True`
.. |False| replace:: :class:`False`
.. |None| replace:: :class:`None`
.. |datetime| replace:: :class:`datetime.datetime`

.. |AttributeError| replace:: :exc:`AttributeError`
.. |KeyError| replace:: :exc:`KeyError`
.. |TypeError| replace:: :exc:`TypeError`
.. |ValueError| replace:: :exc:`ValueError`
.. |NotImplementedError| replace:: :exc:`NotImplementedError`
.. |InvalidXmlError| replace:: :exc:`InvalidXmlError`

.. |ActionSetting| replace:: :class:`.ActionSetting`
.. |Adjustment| replace:: :class:`.Adjustment`
.. |AdjustmentCollection| replace:: :class:`.AdjustmentCollection`
.. |AreaSeries| replace:: :class:`.AreaSeries`
.. |Axis| replace:: :class:`.Axis`
.. |AxisTitle| replace:: :class:`.AxisTitle`
.. |_Background| replace:: :class:`._Background`
.. |BarPlot| replace:: :class:`.BarPlot`
.. |BarSeries| replace:: :class:`.BarSeries`
.. |_BaseMaster| replace:: :class:`._BaseMaster`
.. |BasePlaceholder| replace:: :class:`.BasePlaceholder`
.. |_BasePlot| replace:: :class:`._BasePlot`
.. |BaseFileSystem| replace:: :class:`BaseFileSystem`
.. |BaseShape| replace:: :class:`.BaseShape`
.. |BaseSlidePart| replace:: :class:`.BaseSlidePart`
.. |BlurFormat| replace:: :class:`.BlurFormat`
.. |Borders| replace:: :class:`.Borders`
.. |_Borders| replace:: :class:`._Borders`
.. |BubbleChartData| replace:: :class:`.BubbleChartData`
.. |BubblePlot| replace:: :class:`.BubblePlot`
.. |BubblePoints| replace:: :class:`.BubblePoints`
.. |BubbleSeries| replace:: :class:`.BubbleSeries`
.. |BubbleSeriesData| replace:: :class:`.BubbleSeriesData`
.. |category.Categories| replace:: :class:`~.category.Categories`
.. |data.Categories| replace:: :class:`~.data.Categories`
.. |category.Category| replace:: :class:`~.category.Category`
.. |data.Category| replace:: :class:`~.data.Category`
.. |CategoryAxis| replace:: :class:`.CategoryAxis`
.. |CategoryChartData| replace:: :class:`.CategoryChartData`
.. |CategoryLevel| replace:: :class:`.CategoryLevel`
.. |CategoryPoints| replace:: :class:`.CategoryPoints`
.. |_Cell| replace:: :class:`_Cell`
.. |Chart| replace:: :class:`.Chart`
.. |ChartData| replace:: :class:`.ChartData`
.. |ChartFormat| replace:: :class:`.ChartFormat`
.. |ChartPart| replace:: :class:`.ChartPart`
.. |ChartTitle| replace:: :class:`.ChartTitle`
.. |ChartXmlWriter| replace:: :class:`.ChartXmlWriter`
.. |ColorFormat| replace:: :class:`.ColorFormat`
.. |_Column| replace:: :class:`_Column`
.. |_ColumnCollection| replace:: :class:`_ColumnCollection`
.. |Connector| replace:: :class:`.Connector`
.. |CoreProperties| replace:: :class:`.CoreProperties`
.. |DataLabel| replace:: :class:`.DataLabel`
.. |DataLabels| replace:: :class:`.DataLabels`
.. |DateAxis| replace:: :class:`.DateAxis`
.. |DesignTokens| replace:: :class:`.DesignTokens`
.. |Emu| replace:: :class:`.Emu`
.. |FillFormat| replace:: :class:`.FillFormat`
.. |Font| replace:: :class:`.Font`
.. |FreeformBuilder| replace:: :class:`.FreeformBuilder`
.. |GlowFormat| replace:: :class:`.GlowFormat`
.. |GradientStops| replace:: :class:`.GradientStops`
.. |GraphicFrame| replace:: :class:`.GraphicFrame`
.. |GroupShape| replace:: :class:`.GroupShape`
.. |GroupShapes| replace:: :class:`.GroupShapes`
.. |_Hyperlink| replace:: :class:`._Hyperlink`
.. |Hyperlink| replace:: :class:`.Hyperlink`
.. |Image| replace:: :class:`.Image`
.. |ImagePart| replace:: :class:`.ImagePart`
.. |Inches| replace:: :class:`.Inches`
.. |LayoutPlaceholder| replace:: :class:`.LayoutPlaceholder`
.. |LayoutPlaceholders| replace:: :class:`.LayoutPlaceholders`
.. |LayoutShapes| replace:: :class:`.LayoutShapes`
.. |Legend| replace:: :class:`.Legend`
.. |Length| replace:: :class:`.Length`
.. |LineFormat| replace:: :class:`.LineFormat`
.. |LineEndFormat| replace:: :class:`.LineEndFormat`
.. |LineSeries| replace:: :class:`.LineSeries`
.. |_LineSegment| replace:: :class:`._LineSegment`
.. |MajorGridlines| replace:: :class:`.MajorGridlines`
.. |Marker| replace:: :class:`.Marker`
.. |MasterPlaceholder| replace:: :class:`.MasterPlaceholder`
.. |MasterPlaceholders| replace:: :class:`.MasterPlaceholders`
.. |MasterShapes| replace:: :class:`.MasterShapes`
.. |_MediaFormat| replace:: :class:`._MediaFormat`
.. |NotesMaster| replace:: :class:`.NotesMaster`
.. |NotesSlide| replace:: :class:`.NotesSlide`
.. |NotesSlidePlaceholders| replace:: :class:`.NotesSlidePlaceholders`
.. |NotesSlideShapes| replace:: :class:`.NotesSlideShapes`
.. |_Paragraph| replace:: :class:`_Paragraph`
.. |OpcPackage| replace:: :class:`.OpcPackage`
.. |Package| replace:: :class:`Package`
.. |PackURI| replace:: :class:`.PackURI`
.. |Part| replace:: :class:`Part`
.. |PartTypeSpec| replace:: :class:`PartTypeSpec`
.. |Picture| replace:: :class:`.Picture`
.. |PictureEffects| replace:: :class:`.PictureEffects`
.. |PieSeries| replace:: :class:`.PieSeries`
.. |_PlaceholderFormat| replace:: :class:`._PlaceholderFormat`
.. |PlaceholderGraphicFrame| replace:: :class:`.PlaceholderGraphicFrame`
.. |PlaceholderPicture| replace:: :class:`.PlaceholderPicture`
.. |Plots| replace:: :class:`.Plots`
.. |Point| replace:: :class:`.Point`
.. |Presentation| replace:: :class:`~power_pptx.presentation.Presentation`
.. |Pt| replace:: :class:`.Pt`
.. |RadarSeries| replace:: :class:`.RadarSeries`
.. |ReflectionFormat| replace:: :class:`.ReflectionFormat`
.. |_Relationship| replace:: :class:`._Relationship`
.. |_Relationships| replace:: :class:`_Relationships`
.. |RGBColor| replace:: :class:`.RGBColor`
.. |_Row| replace:: :class:`_Row`
.. |_RowCollection| replace:: :class:`_RowCollection`
.. |_Run| replace:: :class:`_Run`
.. |Series| replace:: :class:`.Series`
.. |SeriesCollection| replace:: :class:`.SeriesCollection`
.. |ShadowFormat| replace:: :class:`.ShadowFormat`
.. |Shape| replace:: :class:`.Shape`
.. |ShapeCollection| replace:: :class:`.ShapeCollection`
.. |ShapeStyle| replace:: :class:`.ShapeStyle`
.. |Slide| replace:: :class:`.Slide`
.. |SlideLintReport| replace:: :class:`.SlideLintReport`
.. |SmartArtShape| replace:: :class:`.SmartArtShape`
.. |SlideShapes| replace:: :class:`.SlideShapes`
.. |SlidePlaceholders| replace:: :class:`.SlidePlaceholders`
.. |SlideMasterPart| replace:: :class:`.SlideMasterPart`
.. |SlideLayoutPart| replace:: :class:`.SlideLayoutPart`
.. |SoftEdgeFormat| replace:: :class:`.SoftEdgeFormat`
.. |Slides| replace:: :class:`.Slides`
.. |SlideAnimations| replace:: :class:`.SlideAnimations`
.. |SlideLayout| replace:: :class:`.SlideLayout`
.. |SlideLayouts| replace:: :class:`.SlideLayouts`
.. |SlideMaster| replace:: :class:`.SlideMaster`
.. |SlideMasters| replace:: :class:`.SlideMasters`
.. |SlideTransition| replace:: :class:`.SlideTransition`
.. |SmartArtCollection| replace:: :class:`.SmartArtCollection`
.. |Table| replace:: :class:`Table`
.. |TextFrame| replace:: :class:`.TextFrame`
.. |Theme| replace:: :class:`.Theme`
.. |ThreeDFormat| replace:: :class:`.ThreeDFormat`
.. |TickLabels| replace:: :class:`.TickLabels`
.. |ValueAxis| replace:: :class:`.ValueAxis`
.. |XyChartData| replace:: :class:`.XyChartData`
.. |XyPoints| replace:: :class:`.XyPoints`
.. |XySeries| replace:: :class:`.XySeries`
.. |XySeriesData| replace:: :class:`.XySeriesData`
.. |WorkbookWriter| replace:: :class:`.WorkbookWriter`
.. |ZipFileSystem| replace:: :class:`ZipFileSystem`
.. |DirectoryFileSystem| replace:: :class:`DirectoryFileSystem`
.. |FileSystem| replace:: :class:`FileSystem`
.. |Collection| replace:: :class:`Collection`
.. |DrawingOperations| replace:: :class:`.DrawingOperations`
"""


# -- HTML output -------------------------------------------------------------

html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "navigation_depth": 3,
    "collapse_navigation": False,
    "style_external_links": True,
}
html_static_path = ["_static"]
html_title = f"power-pptx {release}"
html_short_title = "power-pptx"
htmlhelp_basename = "power-pptxdoc"


# -- LaTeX output ------------------------------------------------------------

latex_documents = [
    ("index", "power-pptx.tex", "power-pptx Documentation", author, "manual"),
]


# -- Manual page output ------------------------------------------------------

man_pages = [("index", "power-pptx", "power-pptx Documentation", [author], 1)]


# -- Texinfo output ----------------------------------------------------------

texinfo_documents = [
    (
        "index",
        "power-pptx",
        "power-pptx Documentation",
        author,
        "power-pptx",
        "Create, read, and update PowerPoint 2007+ (.pptx) files from Python.",
        "Miscellaneous",
    ),
]
