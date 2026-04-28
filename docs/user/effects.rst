.. _effects:

Visual effects
==============

Every shape in |pp| exposes a small family of effect proxies that read and
write the underlying ``<a:effectLst>`` and related elements. Reads never
mutate the XML — accessing an unset property returns |None| so theme
inheritance is preserved.

Shadow, glow, soft edges, blur, reflection
------------------------------------------

::

    from pptx.util import Pt
    from pptx.dml.color import RGBColor

    shadow = shape.shadow
    shadow.blur_radius = Pt(8)
    shadow.distance = Pt(4)
    shadow.direction = 90.0      # degrees, pointing down
    shadow.color.rgb = RGBColor(0x00, 0x00, 0x00)
    shadow.color.alpha = 0.35    # 35% opacity

    shape.glow.radius = Pt(6)
    shape.glow.color.rgb = RGBColor(0x4F, 0x9D, 0xFF)

    shape.soft_edges.radius = Pt(3)

    shape.blur.radius = Pt(4)
    shape.blur.grow = True

    shape.reflection.blur_radius = Pt(2)
    shape.reflection.distance = Pt(1)
    shape.reflection.start_alpha = 0.5
    shape.reflection.end_alpha = 0.0

Setting every explicit property to |None| drops the corresponding XML
element again so the shape inherits the master/theme value.

Alpha and gradient fills
------------------------

``ColorFormat.alpha`` is a read/write float in ``[0.0, 1.0]`` and is also
available on the lazy-color proxy returned by ``Font.color`` and
``LineFormat.color``.

The gradient fill helper accepts a kind argument and exposes mutable
stops::

    fill = shape.fill
    fill.gradient(kind="radial")
    fill.gradient_kind  # → "radial"

    stops = fill.gradient_stops
    stops.replace([
        (0.0, "#0F2D6B"),
        (0.55, RGBColor(0x4F, 0x9D, 0xFF)),
        (1.0, (255, 255, 255)),
    ])

Picture effects
---------------

Pictures gain a dedicated ``effects`` accessor that wraps the OOXML
``<a:blip>`` filters::

    pic = slide.shapes.add_picture("hero.jpg", Inches(0), Inches(0))
    pic.effects.transparency = 0.2
    pic.effects.brightness = 0.1
    pic.effects.contrast = 0.05
    pic.effects.set_duotone(RGBColor(0x12, 0x1E, 0x4D), "#A8C0FF")

``set_duotone`` accepts |RGBColor|, hex strings (with or without ``#``),
or RGB 3-tuples.

Native SVG
----------

``slide.shapes.add_svg_picture(path, left, top)`` embeds both the SVG and
a PNG fallback inside the same ``<a:blip>``.  Provide ``png_fallback=`` to
supply a hand-rasterised file, or install ``cairosvg`` to have it
generated automatically.

Line ends, caps, joins, compound lines
--------------------------------------

::

    from pptx.enum.dml import (
        MSO_LINE_CAP_STYLE,
        MSO_LINE_COMPOUND_STYLE,
        MSO_LINE_JOIN_STYLE,
    )

    line = shape.line
    line.head_end.type = "TRIANGLE"
    line.tail_end.length = "LARGE"
    line.cap = MSO_LINE_CAP_STYLE.ROUND
    line.compound = MSO_LINE_COMPOUND_STYLE.DOUBLE
    line.join = MSO_LINE_JOIN_STYLE.BEVEL
