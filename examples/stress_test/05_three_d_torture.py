"""3D torture: every bevel preset, extrusion, contour, every material preset,
combined with shadows. Verifies scene3d defaults round-trip cleanly.
"""

from __future__ import annotations

from _util import blank, deck, save

from power_pptx.dml.color import RGBColor
from power_pptx.enum.dml import BevelPreset, PresetMaterial
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.util import Inches, Pt


def build():
    prs = deck()

    # --- Every bevel preset on a grid of badges --------------------------
    presets = [
        BevelPreset.RELAXED_INSET, BevelPreset.CIRCLE, BevelPreset.SLOPE,
        BevelPreset.CROSS, BevelPreset.ANGLE, BevelPreset.SOFT_ROUND,
        BevelPreset.CONVEX, BevelPreset.COOL_SLANT, BevelPreset.DIVOT,
        BevelPreset.RIBLET, BevelPreset.HARD_EDGE, BevelPreset.ART_DECO,
    ]
    s = blank(prs)
    for i, preset in enumerate(presets):
        col, row = i % 4, i // 4
        badge = s.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(0.6 + col * 3.1), Inches(0.7 + row * 2.2),
            Inches(2.7), Inches(1.8),
        )
        badge.fill.solid()
        badge.fill.fore_color.rgb = RGBColor(0xFF, 0xC1, 0x07)
        badge.line.fill.background()
        td = badge.three_d
        td.bevel_top.preset = preset
        td.bevel_top.width = Pt(8)
        td.bevel_top.height = Pt(4)
        badge.text_frame.text = preset.name if hasattr(preset, "name") else str(preset)

    # --- Every material preset on extruded ovals -------------------------
    materials = [
        PresetMaterial.MATTE, PresetMaterial.PLASTIC, PresetMaterial.METAL,
        PresetMaterial.WARM_MATTE, PresetMaterial.TRANSLUCENT_POWDER,
        PresetMaterial.POWDER, PresetMaterial.DK_EDGE, PresetMaterial.SOFT_EDGE,
        PresetMaterial.CLEAR, PresetMaterial.FLAT, PresetMaterial.SOFT_METAL,
    ]
    s = blank(prs)
    for i, mat in enumerate(materials):
        col, row = i % 4, i // 4
        badge = s.shapes.add_shape(
            MSO_SHAPE.OVAL,
            Inches(0.6 + col * 3.1), Inches(0.7 + row * 2.2),
            Inches(2.7), Inches(1.8),
        )
        badge.fill.solid()
        badge.fill.fore_color.rgb = RGBColor(0x4F, 0x9D, 0xFF)
        badge.line.fill.background()
        td = badge.three_d
        td.bevel_top.preset = BevelPreset.CIRCLE
        td.bevel_top.width = Pt(6)
        td.bevel_top.height = Pt(3)
        td.extrusion_height = Pt(16)
        td.extrusion_color = RGBColor(0x12, 0x1E, 0x4D)
        td.preset_material = mat
        badge.text_frame.text = mat.name if hasattr(mat, "name") else str(mat)

    # --- Contour + bottom bevel + shadow combo ---------------------------
    s = blank(prs)
    card = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                              Inches(4), Inches(2), Inches(5), Inches(3.5))
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor(0x10, 0xB9, 0x81)
    card.line.fill.background()
    td = card.three_d
    td.bevel_top.preset = BevelPreset.SOFT_ROUND
    td.bevel_top.width = Pt(10)
    td.bevel_top.height = Pt(6)
    td.bevel_bottom.preset = BevelPreset.ANGLE
    td.bevel_bottom.width = Pt(4)
    td.bevel_bottom.height = Pt(2)
    td.extrusion_height = Pt(24)
    td.extrusion_color = RGBColor(0x06, 0x5F, 0x46)
    td.contour_width = Pt(1.5)
    td.contour_color = RGBColor(0xFF, 0xFF, 0xFF)
    td.preset_material = PresetMaterial.METAL
    card.shadow.blur_radius = Pt(20)
    card.shadow.distance = Pt(6)
    card.shadow.color.alpha = 0.3
    card.text_frame.text = "full 3D combo"

    # --- read-back contour color proxy without mutation ------------------
    assert card.three_d.contour_color.rgb == RGBColor(0xFF, 0xFF, 0xFF)

    return prs


if __name__ == "__main__":
    save(build(), "05_three_d_torture.pptx")
