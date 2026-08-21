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

    from power_pptx.util import Pt
    from power_pptx.dml.color import RGBColor

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

Removing a shadow: ``shadow.clear()``
-------------------------------------

Restoring inheritance is not the same as having no shadow.  An auto
shape created by ``shapes.add_shape()`` carries a ``<p:style>`` with
``<a:effectRef idx="2"/>``, which resolves against the theme's effect
styles — a soft drop shadow in most themes.  Clearing only the explicit
properties leaves that inherited shadow rendering, which reads as a
phantom shadow nobody asked for.

``ShadowFormat.clear()`` is the guaranteed-flat form::

    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, *box)
    card.shadow.clear()

It drops every explicit shadow element (outer, inner, preset), writes
the empty ``<a:effectLst/>`` that overrides inherited effects, and
re-points ``<a:effectRef>`` at the theme's empty slot (``idx="0"``).
Non-shadow effects already on the shape — glow, soft edges, blur,
reflection — are preserved.  It is idempotent, and a no-op on shapes
with no ``<p:style>`` (text boxes, pictures, placeholders).

.. note::
   The deprecated ``shadow.inherit = False`` does *not* do this.  It writes
   the empty ``<a:effectLst/>`` and nothing else, so that ``inherit = True``
   can put the shape back exactly as it found it — the original
   ``effectRef`` index is not recoverable once overwritten.  An inherited
   theme shadow therefore survives it; use ``shadow.clear()``.

Corner radius in points
-----------------------

A rounded rectangle stores its corner radius as ``adjustments[0]``, a
fraction of the shorter side — so the same value means a different
radius on every differently-sized shape.  ``Shape.corner_radius`` reads
and writes it as a real length instead::

    card.corner_radius = Pt(6)
    card.corner_radius.pt    # -> 6.0

Defined for ``ROUNDED_RECTANGLE``, ``ROUND_1_RECTANGLE``,
``ROUND_2_SAME_RECTANGLE`` and ``ROUND_2_DIAG_RECTANGLE``; raises
|ValueError| for any other geometry, for a shape with no extents yet,
and when the radius exceeds half the shorter side (the maximum a preset
rounded rectangle can express).

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

    from power_pptx.enum.dml import (
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
