"""Unit-test suite for `power_pptx.dml.three_d` module."""

from __future__ import annotations

import pytest

from power_pptx.dml.three_d import ThreeDFormat, _BevelFormat
from power_pptx.enum.dml import BevelPreset, PresetMaterial
from power_pptx.util import Emu, Pt

from ..unitutil.cxml import element, xml


class DescribeThreeDFormat:
    """Unit tests for ThreeDFormat."""

    # ------------------------------------------------------------------
    # bevel_top - preset (non-mutating reads)
    # ------------------------------------------------------------------

    def it_returns_None_for_bevel_top_preset_when_no_sp3d(self):
        td = ThreeDFormat(element("p:spPr"))
        assert td.bevel_top.preset is None
        # read must not mutate XML
        assert td._element.xml == xml("p:spPr")

    def it_returns_None_for_bevel_top_preset_when_sp3d_but_no_bevelT(self):
        td = ThreeDFormat(element("p:spPr/a:sp3d"))
        assert td.bevel_top.preset is None

    def it_reads_explicit_bevel_top_preset(self):
        td = ThreeDFormat(element("p:spPr/a:sp3d/a:bevelT{prst=circle}"))
        assert td.bevel_top.preset == BevelPreset.CIRCLE

    # ------------------------------------------------------------------
    # bevel_top - width / height
    # ------------------------------------------------------------------

    def it_returns_None_for_bevel_top_width_when_absent(self):
        td = ThreeDFormat(element("p:spPr"))
        assert td.bevel_top.width is None

    def it_reads_explicit_bevel_top_width(self):
        td = ThreeDFormat(element("p:spPr/a:sp3d/a:bevelT{w=50800}"))
        assert td.bevel_top.width == Emu(50800)

    def it_returns_None_for_bevel_top_height_when_absent(self):
        td = ThreeDFormat(element("p:spPr"))
        assert td.bevel_top.height is None

    def it_reads_explicit_bevel_top_height(self):
        td = ThreeDFormat(element("p:spPr/a:sp3d/a:bevelT{h=76200}"))
        assert td.bevel_top.height == Emu(76200)

    # ------------------------------------------------------------------
    # bevel_top - writes lazily create elements
    # ------------------------------------------------------------------

    def it_creates_scene3d_and_sp3d_on_bevel_top_preset_write(self):
        spPr = element("p:spPr")
        td = ThreeDFormat(spPr)
        td.bevel_top.preset = BevelPreset.CIRCLE
        assert spPr.scene3d is not None
        assert spPr.sp3d is not None
        assert spPr.sp3d.bevelT is not None
        assert spPr.sp3d.bevelT.prst == BevelPreset.CIRCLE

    def it_creates_bevelT_on_width_write(self):
        spPr = element("p:spPr")
        td = ThreeDFormat(spPr)
        td.bevel_top.width = Pt(4)
        assert spPr.sp3d.bevelT.w == Pt(4)

    # ------------------------------------------------------------------
    # bevel_bottom
    # ------------------------------------------------------------------

    def it_returns_None_for_bevel_bottom_preset_when_no_sp3d(self):
        td = ThreeDFormat(element("p:spPr"))
        assert td.bevel_bottom.preset is None

    def it_reads_explicit_bevel_bottom_preset(self):
        td = ThreeDFormat(element("p:spPr/a:sp3d/a:bevelB{prst=slope}"))
        assert td.bevel_bottom.preset == BevelPreset.SLOPE

    def it_creates_bevelB_on_write(self):
        spPr = element("p:spPr")
        td = ThreeDFormat(spPr)
        td.bevel_bottom.preset = BevelPreset.SLOPE
        assert spPr.sp3d.bevelB.prst == BevelPreset.SLOPE

    # ------------------------------------------------------------------
    # extrusion_height
    # ------------------------------------------------------------------

    def it_returns_None_for_extrusion_height_when_absent(self):
        td = ThreeDFormat(element("p:spPr"))
        assert td.extrusion_height is None
        # non-mutating
        assert td._element.xml == xml("p:spPr")

    def it_reads_explicit_extrusion_height(self):
        td = ThreeDFormat(element("p:spPr/a:sp3d{extrusionH=76200}"))
        assert td.extrusion_height == Emu(76200)

    def it_creates_sp3d_on_extrusion_height_write(self):
        spPr = element("p:spPr")
        td = ThreeDFormat(spPr)
        td.extrusion_height = Pt(6)
        assert spPr.sp3d is not None
        assert spPr.sp3d.extrusionH == Pt(6)

    def it_clears_extrusion_height_on_None_write(self):
        spPr = element("p:spPr/a:sp3d{extrusionH=76200}")
        td = ThreeDFormat(spPr)
        td.extrusion_height = None
        assert spPr.sp3d.extrusionH is None

    # ------------------------------------------------------------------
    # preset_material
    # ------------------------------------------------------------------

    def it_returns_None_for_preset_material_when_absent(self):
        td = ThreeDFormat(element("p:spPr"))
        assert td.preset_material is None

    def it_reads_explicit_preset_material(self):
        td = ThreeDFormat(element("p:spPr/a:sp3d{prstMaterial=matte}"))
        assert td.preset_material == PresetMaterial.MATTE

    def it_creates_sp3d_on_preset_material_write(self):
        spPr = element("p:spPr")
        td = ThreeDFormat(spPr)
        td.preset_material = PresetMaterial.METAL
        assert spPr.sp3d is not None
        assert spPr.sp3d.prstMaterial == PresetMaterial.METAL

    def it_clears_preset_material_on_None_write(self):
        spPr = element("p:spPr/a:sp3d{prstMaterial=metal}")
        td = ThreeDFormat(spPr)
        td.preset_material = None
        assert spPr.sp3d.prstMaterial is None

    # ------------------------------------------------------------------
    # extrusion_color
    # ------------------------------------------------------------------

    def it_returns_None_type_for_extrusion_color_when_absent(self):
        td = ThreeDFormat(element("p:spPr"))
        assert td.extrusion_color.type is None
        assert td.extrusion_color.rgb is None
        # non-mutating
        assert td._element.xml == xml("p:spPr")

    def it_creates_extrusionClr_on_color_write(self):
        from power_pptx.dml.color import RGBColor

        spPr = element("p:spPr")
        td = ThreeDFormat(spPr)
        td.extrusion_color.rgb = RGBColor(0xFF, 0x00, 0x00)
        assert spPr.sp3d is not None
        assert spPr.sp3d.extrusionClr is not None

    # ------------------------------------------------------------------
    # contour_width / contour_color
    # ------------------------------------------------------------------

    def it_returns_None_for_contour_width_when_absent(self):
        td = ThreeDFormat(element("p:spPr"))
        assert td.contour_width is None

    def it_reads_explicit_contour_width(self):
        td = ThreeDFormat(element("p:spPr/a:sp3d{contourW=12700}"))
        assert td.contour_width == Emu(12700)

    def it_creates_sp3d_on_contour_width_write(self):
        spPr = element("p:spPr")
        td = ThreeDFormat(spPr)
        td.contour_width = Pt(1)
        assert spPr.sp3d.contourW == Pt(1)

    def it_returns_None_type_for_contour_color_when_absent(self):
        td = ThreeDFormat(element("p:spPr"))
        assert td.contour_color.type is None
        assert td._element.xml == xml("p:spPr")


class Describe_BevelFormat:
    """Unit tests for _BevelFormat."""

    def it_returns_None_for_all_props_when_element_absent(self):
        bevel = _BevelFormat(peek=lambda: None, ensure=lambda: None)
        assert bevel.preset is None
        assert bevel.width is None
        assert bevel.height is None

    def it_clears_preset_on_None_write_when_element_exists(self):
        spPr = element("p:spPr/a:sp3d/a:bevelT{prst=circle}")
        bevel_elm = spPr.sp3d.bevelT
        bevel = _BevelFormat(peek=lambda: bevel_elm, ensure=lambda: bevel_elm)
        bevel.preset = None
        assert bevel_elm.prst is None
