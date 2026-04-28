# 3D primitives (Phase 8)

`shape.three_d` exposes bevels (`<a:bevelT>` / `<a:bevelB>`) and
extrusion (`<a:sp3d>`), backed by `CT_Shape3D` and `CT_Scene3D` element
classes in `pptx.oxml.dml.three_d`.

## Bevels

```python
from pptx.util import Pt
from pptx.enum.dml import BevelPreset

three_d = card.three_d

# Top bevel
three_d.bevel_top.preset = BevelPreset.SOFT_ROUND
three_d.bevel_top.width  = Pt(6)
three_d.bevel_top.height = Pt(3)

# Bottom bevel (less common)
three_d.bevel_bottom.preset = BevelPreset.ANGLE
three_d.bevel_bottom.width  = Pt(2)
three_d.bevel_bottom.height = Pt(1)
```

`BevelPreset` covers the standard PowerPoint set: `RELAXED_INSET`,
`CIRCLE`, `SLOPE`, `CROSS`, `ANGLE`, `SOFT_ROUND`, `CONVEX`, `COOL_SLANT`,
`DIVOT`, `RIBLET`, `HARD_EDGE`, `ART_DECO`.

## Extrusion

```python
from pptx.dml.color import RGBColor

three_d.extrusion_height = Pt(20)
three_d.extrusion_color  = RGBColor(0x12, 0x1E, 0x4D)
```

## Contour

```python
three_d.contour_width = Pt(1)
three_d.contour_color = RGBColor(0xFF, 0xFF, 0xFF)
```

## Material preset

Material affects how the surface reacts to scene lighting:

```python
from pptx.enum.dml import PresetMaterial

three_d.preset_material = PresetMaterial.METAL
# Other options: MATTE, PLASTIC, METAL, WARM_MATTE, TRANSLUCENT_POWDER,
# POWDER, DARK_EDGE, SOFT_EDGE, CLEAR, FLAT, SOFT_METAL
```

## End-to-end: a beveled badge

```python
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.dml import BevelPreset, PresetMaterial
from pptx.dml.color import RGBColor

prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[6])

badge = slide.shapes.add_shape(
    MSO_SHAPE.OVAL,
    Inches(5.5), Inches(3.0), Inches(2.0), Inches(2.0),
)
badge.fill.solid()
badge.fill.fore_color.rgb = RGBColor(0xFF, 0xC1, 0x07)
badge.line.fill.background()

td = badge.three_d
td.bevel_top.preset = BevelPreset.SOFT_ROUND
td.bevel_top.width  = Pt(8)
td.bevel_top.height = Pt(4)
td.preset_material  = PresetMaterial.METAL

# Combine with a soft shadow for depth
badge.shadow.blur_radius = Pt(12)
badge.shadow.distance    = Pt(4)
badge.shadow.direction   = 90.0
badge.shadow.color.alpha = 0.3

prs.save("badge.pptx")
```

## Round-trip

The `<a:scene3d>` and `<a:sp3d>` slots were already reserved in the
upstream `oxml/shapes/shared.py`; this proxy just gives them a public
read/write face. PowerPoint-authored 3D round-trips cleanly even if
you don't touch the proxy.
