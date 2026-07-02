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

    def it_removes_bevelT_on_NONE_preset_write(self):
        # ``BevelPreset.NONE`` means "no bevel"; its token "none" is invalid per
        # ST_BevelPresetType and would trigger a PowerPoint repair, so assigning
        # it must remove the whole <a:bevelT> element, not write prst="none".
        spPr = element("p:spPr/a:sp3d/a:bevelT{prst=circle,w=50800}")
        td = ThreeDFormat(spPr)
        td.bevel_top.preset = BevelPreset.NONE
        assert spPr.sp3d.bevelT is None
        assert td.bevel_top.preset is None

    def it_removes_bevelT_when_the_raw_NONE_enum_value_is_passed(self):
        # A caller round-tripping through the enum's *value* (e.g. from JSON /
        # config) passes ``BevelPreset.NONE.value`` (an int), not the singleton.
        # The guard must still treat it as "no bevel" — otherwise the int is
        # coerced straight back into the invalid ``prst="none"`` token.
        spPr = element("p:spPr/a:sp3d/a:bevelT{prst=circle}")
        td = ThreeDFormat(spPr)
        td.bevel_top.preset = BevelPreset.NONE.value  # type: ignore[assignment]
        assert spPr.sp3d.bevelT is None

    def it_is_a_noop_to_write_NONE_bevel_preset_when_absent(self):
        # Assigning NONE with no existing 3-D must not fabricate an sp3d/bevelT.
        spPr = element("p:spPr")
        td = ThreeDFormat(spPr)
        td.bevel_top.preset = BevelPreset.NONE
        assert spPr.sp3d is None
        assert td._element.xml == xml("p:spPr")

    def it_keeps_bevelT_dimensions_on_None_preset_write(self):
        # Python ``None`` (distinct from ``BevelPreset.NONE``) only clears the
        # preset attribute, preserving any explicit bevel dimensions.
        spPr = element("p:spPr/a:sp3d/a:bevelT{prst=circle,w=50800}")
        td = ThreeDFormat(spPr)
        td.bevel_top.preset = None
        assert spPr.sp3d.bevelT is not None
        assert spPr.sp3d.bevelT.prst is None
        assert spPr.sp3d.bevelT.w == Emu(50800)

    def it_removes_bevelB_on_NONE_preset_write(self):
        spPr = element("p:spPr/a:sp3d/a:bevelB{prst=slope}")
        td = ThreeDFormat(spPr)
        td.bevel_bottom.preset = BevelPreset.NONE
        assert spPr.sp3d.bevelB is None

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

    def it_clears_preset_material_on_NONE_write(self):
        # ``PresetMaterial.NONE``'s token "none" is invalid per
        # ST_PresetMaterialType and would trigger a PowerPoint repair, so
        # assigning it clears the attribute instead of writing prstMaterial="none".
        spPr = element("p:spPr/a:sp3d{prstMaterial=metal}")
        td = ThreeDFormat(spPr)
        td.preset_material = PresetMaterial.NONE
        assert spPr.sp3d.prstMaterial is None
        assert td.preset_material is None

    def it_clears_preset_material_when_the_raw_NONE_enum_value_is_passed(self):
        # ``PresetMaterial.NONE.value`` (an int, e.g. from JSON / config) must
        # clear the attribute too, not fall through and coerce the int back into
        # the invalid ``prstMaterial="none"`` token.
        spPr = element("p:spPr/a:sp3d{prstMaterial=metal}")
        td = ThreeDFormat(spPr)
        td.preset_material = PresetMaterial.NONE.value  # type: ignore[assignment]
        assert spPr.sp3d.prstMaterial is None

    def it_is_a_noop_to_write_NONE_material_when_absent(self):
        spPr = element("p:spPr")
        td = ThreeDFormat(spPr)
        td.preset_material = PresetMaterial.NONE
        assert spPr.sp3d is None
        assert td._element.xml == xml("p:spPr")

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

    def it_supports_direct_extrusion_color_assignment(self):
        # Docs show ``three_d.extrusion_color = RGBColor(...)``; the property
        # must accept that in addition to ``.rgb =``.
        from power_pptx.dml.color import RGBColor

        spPr = element("p:spPr")
        td = ThreeDFormat(spPr)
        td.extrusion_color = RGBColor(0x12, 0x1E, 0x4D)
        assert td.extrusion_color.rgb == RGBColor(0x12, 0x1E, 0x4D)

    def it_supports_direct_contour_color_assignment(self):
        from power_pptx.dml.color import RGBColor

        spPr = element("p:spPr")
        td = ThreeDFormat(spPr)
        td.contour_color = RGBColor(0xFF, 0xFF, 0xFF)
        assert td.contour_color.rgb == RGBColor(0xFF, 0xFF, 0xFF)

    # ------------------------------------------------------------------
    # scene3d defaults (PowerPoint compatibility)
    # ------------------------------------------------------------------

    def it_populates_scene3d_with_camera_and_lightRig(self):
        # An empty <a:scene3d> beside <a:sp3d> makes PowerPoint flag the deck
        # as broken; the creating path must populate the required children.
        spPr = element("p:spPr")
        td = ThreeDFormat(spPr)
        td.bevel_top.preset = BevelPreset.SOFT_ROUND
        scene3d = spPr.scene3d
        assert scene3d is not None
        assert scene3d.camera is not None
        assert scene3d.camera.prst == "orthographicFront"
        assert scene3d.lightRig is not None
        assert scene3d.lightRig.rig == "threePt"
        assert scene3d.lightRig.dir == "t"

    def it_does_not_duplicate_existing_scene3d_children(self):
        # Re-entering the creating path (a second 3-D property write) must not
        # append a second camera/lightRig.
        spPr = element("p:spPr")
        td = ThreeDFormat(spPr)
        td.bevel_top.preset = BevelPreset.SOFT_ROUND
        td.extrusion_height = Pt(6)
        scene3d = spPr.scene3d
        assert len(scene3d.findall("{http://schemas.openxmlformats.org/drawingml/2006/main}camera")) == 1
        assert len(scene3d.findall("{http://schemas.openxmlformats.org/drawingml/2006/main}lightRig")) == 1

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
        bevel = _BevelFormat(peek=lambda: None, ensure=lambda: None, remove=lambda: None)
        assert bevel.preset is None
        assert bevel.width is None
        assert bevel.height is None

    def it_clears_preset_on_None_write_when_element_exists(self):
        spPr = element("p:spPr/a:sp3d/a:bevelT{prst=circle}")
        bevel_elm = spPr.sp3d.bevelT
        bevel = _BevelFormat(peek=lambda: bevel_elm, ensure=lambda: bevel_elm, remove=lambda: None)
        bevel.preset = None
        assert bevel_elm.prst is None

    def it_calls_remove_on_NONE_preset_write(self):
        calls = []
        bevel = _BevelFormat(
            peek=lambda: None, ensure=lambda: None, remove=lambda: calls.append(True)
        )
        bevel.preset = BevelPreset.NONE
        assert calls == [True]
