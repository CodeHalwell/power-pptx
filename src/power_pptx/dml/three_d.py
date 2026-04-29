"""3-D shape formatting objects such as |ThreeDFormat|."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from power_pptx.dml.color import ColorFormat
from power_pptx.enum.dml import BevelPreset, PresetMaterial

if TYPE_CHECKING:
    from power_pptx.dml.color import RGBColor
    from power_pptx.enum.dml import MSO_COLOR_TYPE, MSO_THEME_COLOR
    from power_pptx.oxml.dml.three_d import CT_Bevel, CT_ContourColor, CT_ExtrusionColor, CT_Shape3D
    from power_pptx.oxml.shapes.shared import CT_ShapeProperties
    from power_pptx.util import Length


class _LazyThreeDColorFormat:
    """Non-mutating |ColorFormat| proxy for a 3-D colour slot (extrusion or contour).

    Reads return the appropriate "no color" sentinels when the parent element does not exist.
    Writes lazily create the element hierarchy.
    """

    def __init__(
        self,
        peek: Callable[[], CT_ExtrusionColor | CT_ContourColor | None],
        ensure: Callable[[], CT_ExtrusionColor | CT_ContourColor],
    ):
        self._peek = peek
        self._ensure = ensure

    @property
    def type(self) -> MSO_COLOR_TYPE | None:
        cf = self._existing_cf()
        return cf.type if cf is not None else None

    @property
    def rgb(self) -> RGBColor | None:
        cf = self._existing_cf()
        return cf.rgb if cf is not None else None

    @rgb.setter
    def rgb(self, value: RGBColor) -> None:
        self._ensure_cf().rgb = value

    @property
    def theme_color(self) -> MSO_THEME_COLOR:
        from power_pptx.enum.dml import MSO_THEME_COLOR

        cf = self._existing_cf()
        return cf.theme_color if cf is not None else MSO_THEME_COLOR.NOT_THEME_COLOR

    @theme_color.setter
    def theme_color(self, value: MSO_THEME_COLOR) -> None:
        self._ensure_cf().theme_color = value

    def _existing_cf(self) -> ColorFormat | None:
        el = self._peek()
        return None if el is None else ColorFormat.from_colorchoice_parent(el)

    def _ensure_cf(self) -> ColorFormat:
        return ColorFormat.from_colorchoice_parent(self._ensure())


class _BevelFormat:
    """Provides access to the bevel on one face (top or bottom) of a 3-D shape.

    All reads are non-mutating: when the bevel element is absent, ``preset`` returns ``None``
    and the dimension properties return ``None``.  Writing any property lazily creates the bevel
    element (and its ``<a:sp3d>`` parent if required).
    """

    def __init__(
        self,
        peek: Callable[[], CT_Bevel | None],
        ensure: Callable[[], CT_Bevel],
    ) -> None:
        self._peek = peek
        self._ensure = ensure

    @property
    def preset(self) -> BevelPreset | None:
        """Bevel preset (|BevelPreset| member), or ``None`` if not explicitly set."""
        bevel = self._peek()
        return None if bevel is None else bevel.prst

    @preset.setter
    def preset(self, value: BevelPreset | None) -> None:
        if value is None:
            bevel = self._peek()
            if bevel is not None:
                bevel.prst = None  # type: ignore[assignment]
        else:
            self._ensure().prst = value  # type: ignore[assignment]

    @property
    def width(self) -> Length | None:
        """Bevel width in EMU, or ``None`` if not explicitly set."""
        bevel = self._peek()
        return None if bevel is None else bevel.w

    @width.setter
    def width(self, value: Length | None) -> None:
        if value is None:
            bevel = self._peek()
            if bevel is not None:
                bevel.w = None  # type: ignore[assignment]
        else:
            self._ensure().w = value  # type: ignore[assignment]

    @property
    def height(self) -> Length | None:
        """Bevel height in EMU, or ``None`` if not explicitly set."""
        bevel = self._peek()
        return None if bevel is None else bevel.h

    @height.setter
    def height(self, value: Length | None) -> None:
        if value is None:
            bevel = self._peek()
            if bevel is not None:
                bevel.h = None  # type: ignore[assignment]
        else:
            self._ensure().h = value  # type: ignore[assignment]


class ThreeDFormat:
    """Provides access to 3-D formatting properties on a shape.

    All property reads are non-mutating: when no 3-D elements are present in the XML the
    properties return ``None``.  Writing any property lazily creates the required
    ``<a:scene3d>`` and/or ``<a:sp3d>`` elements.

    Obtain an instance from :attr:`power_pptx.shapes.base.BaseShape.three_d`.

    Example::

        from power_pptx.enum.dml import BevelPreset, PresetMaterial
        from power_pptx.util import Pt

        shape.three_d.bevel_top.preset = BevelPreset.CIRCLE
        shape.three_d.bevel_top.width = Pt(4)
        shape.three_d.extrusion_height = Pt(6)
        shape.three_d.preset_material = PresetMaterial.MATTE
    """

    def __init__(self, spPr: CT_ShapeProperties) -> None:
        self._element = spPr

    # ------------------------------------------------------------------
    # Top bevel
    # ------------------------------------------------------------------

    @property
    def bevel_top(self) -> _BevelFormat:
        """``_BevelFormat`` providing access to the top-face bevel.

        Always returned (non-mutating reads return ``None`` when no bevel is set).
        """
        return _BevelFormat(
            peek=self._peek_bevelT,
            ensure=self._get_or_add_bevelT,
        )

    # ------------------------------------------------------------------
    # Bottom bevel
    # ------------------------------------------------------------------

    @property
    def bevel_bottom(self) -> _BevelFormat:
        """``_BevelFormat`` providing access to the bottom-face bevel.

        Always returned (non-mutating reads return ``None`` when no bevel is set).
        """
        return _BevelFormat(
            peek=self._peek_bevelB,
            ensure=self._get_or_add_bevelB,
        )

    # ------------------------------------------------------------------
    # Extrusion
    # ------------------------------------------------------------------

    @property
    def extrusion_height(self) -> Length | None:
        """Extrusion depth in EMU, or ``None`` if not explicitly set."""
        sp3d = self._sp3d
        return None if sp3d is None else sp3d.extrusionH

    @extrusion_height.setter
    def extrusion_height(self, value: Length | None) -> None:
        if value is None:
            sp3d = self._sp3d
            if sp3d is not None:
                sp3d.extrusionH = None  # type: ignore[assignment]
        else:
            self._get_or_add_sp3d().extrusionH = value  # type: ignore[assignment]

    @property
    def extrusion_color(self) -> _LazyThreeDColorFormat:
        """Non-mutating color accessor for the extrusion color.

        Reading any sub-property on a shape with no 3-D extrusion color returns the appropriate
        "no color" sentinel without touching the XML.  Writing creates the hierarchy lazily.
        """
        return _LazyThreeDColorFormat(
            peek=self._peek_extrusionClr,
            ensure=self._get_or_add_extrusionClr,
        )

    # ------------------------------------------------------------------
    # Contour
    # ------------------------------------------------------------------

    @property
    def contour_width(self) -> Length | None:
        """Contour (edge) width in EMU, or ``None`` if not explicitly set."""
        sp3d = self._sp3d
        return None if sp3d is None else sp3d.contourW

    @contour_width.setter
    def contour_width(self, value: Length | None) -> None:
        if value is None:
            sp3d = self._sp3d
            if sp3d is not None:
                sp3d.contourW = None  # type: ignore[assignment]
        else:
            self._get_or_add_sp3d().contourW = value  # type: ignore[assignment]

    @property
    def contour_color(self) -> _LazyThreeDColorFormat:
        """Non-mutating color accessor for the contour (edge) color.

        Reading any sub-property on a shape with no contour color returns the appropriate
        "no color" sentinel without touching the XML.  Writing creates the hierarchy lazily.
        """
        return _LazyThreeDColorFormat(
            peek=self._peek_contourClr,
            ensure=self._get_or_add_contourClr,
        )

    # ------------------------------------------------------------------
    # Preset material
    # ------------------------------------------------------------------

    @property
    def preset_material(self) -> PresetMaterial | None:
        """Surface material preset (|PresetMaterial| member), or ``None`` if not set."""
        sp3d = self._sp3d
        return None if sp3d is None else sp3d.prstMaterial

    @preset_material.setter
    def preset_material(self, value: PresetMaterial | None) -> None:
        if value is None:
            sp3d = self._sp3d
            if sp3d is not None:
                sp3d.prstMaterial = None  # type: ignore[assignment]
        else:
            self._get_or_add_sp3d().prstMaterial = value  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @property
    def _sp3d(self) -> CT_Shape3D | None:
        return self._element.sp3d

    def _get_or_add_sp3d(self) -> CT_Shape3D:
        """Return the ``<a:sp3d>`` element, creating scene3d + sp3d pair if absent."""
        sp3d = self._element.sp3d
        if sp3d is None:
            # scene3d must precede sp3d; ensure both are present
            self._element.get_or_add_scene3d()
            sp3d = self._element.get_or_add_sp3d()
        return sp3d

    def _peek_bevelT(self) -> CT_Bevel | None:
        sp3d = self._sp3d
        return None if sp3d is None else sp3d.bevelT

    def _get_or_add_bevelT(self) -> CT_Bevel:
        return self._get_or_add_sp3d().get_or_add_bevelT()

    def _peek_bevelB(self) -> CT_Bevel | None:
        sp3d = self._sp3d
        return None if sp3d is None else sp3d.bevelB

    def _get_or_add_bevelB(self) -> CT_Bevel:
        return self._get_or_add_sp3d().get_or_add_bevelB()

    def _peek_extrusionClr(self) -> CT_ExtrusionColor | None:
        sp3d = self._sp3d
        return None if sp3d is None else sp3d.extrusionClr

    def _get_or_add_extrusionClr(self) -> CT_ExtrusionColor:
        return self._get_or_add_sp3d().get_or_add_extrusionClr()

    def _peek_contourClr(self) -> CT_ContourColor | None:
        sp3d = self._sp3d
        return None if sp3d is None else sp3d.contourClr

    def _get_or_add_contourClr(self) -> CT_ContourColor:
        return self._get_or_add_sp3d().get_or_add_contourClr()
