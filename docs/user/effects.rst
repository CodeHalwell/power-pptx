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

Lengths may be floats, so arithmetic such as ``Pt(8) / 2`` works; the
value is rounded to whole EMU.  The same holds for the 3-D lengths
(``three_d.bevel_top.width``, ``extrusion_height``, ``contour_width``)
and ``line.width``.  A value a setter rejects — a negative radius, an
alpha above 1.0, a string — raises without touching the shape.

Setting every explicit property to |None| drops the corresponding XML
element again so the shape inherits the master/theme value.  For the
effects that carry a colour (outer and inner shadow, glow) that includes
the colour, if you set one::

    shadow.blur_radius = None
    shadow.distance = None
    shadow.direction = None
    shadow.color = None

When that removes the last effect on the shape, the ``<a:effectLst>``
goes too; an empty ``<a:effectLst/>`` would keep overriding the theme.
A preset shadow is defined by its preset and is removed with
``shape.preset_shadow.preset = None``.

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
Non-shadow effects written on the shape itself — glow, soft edges, blur,
reflection — are preserved.  Theme-derived effects are not:
``<a:effectRef>`` references one whole entry in the theme's effect-style
list, so a custom theme pairing its shadow with a glow loses the glow as
well; re-apply it explicitly on the shape if you need it.  (Stock Office
themes reference shadow-only styles.)  It is idempotent, and a no-op on
shapes with no ``<p:style>`` (text boxes, pictures, placeholders).

A shape whose effects are expressed as an ``<a:effectDag>`` has its
shadow nodes pruned from that tree instead.  ``<a:effectLst>`` and
``<a:effectDag>`` are the two arms of one ``EG_EffectProperties``
choice, so adding a sibling list would make the deck schema-invalid and
leave the DAG's own shadow rendering.

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

Reads report the radius as rendered.  These geometries pin their
adjustment with ``pin 0 adj 50000``, so a shape carrying an out-of-range
value — set through ``adjustments[0]`` or authored in another tool —
draws at the nearest legal radius and reads back as that.

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

``replace()`` validates every entry first — position in ``[0.0, 1.0]``,
a real colour — and leaves the existing stops alone if any is rejected.

A linear gradient takes an angle, either through
``fill.linear_gradient(start, end, angle=...)`` or
``fill.gradient_angle``.  The angle is measured **counter-clockwise**,
as in trigonometry, and gives the direction the gradient runs from its
first stop to its last:

=========  ==============  ======================
angle      runs            first colour is at the
=========  ==============  ======================
``0``      left to right   left
``90``     bottom to top   bottom
``180``    right to left   right
``270``    top to bottom   top
=========  ==============  ======================

::

    shape.fill.linear_gradient("#06D6FE", "#B14AED", angle=270)  # top to bottom

This is the reverse of the ``ang`` attribute stored in the XML, which
counts clockwise: ``angle=90`` is written as ``ang="16200000"`` (270
degrees).

Picture effects
---------------

Pictures gain a dedicated ``effects`` accessor that wraps the OOXML
``<a:blip>`` filters::

    pic = slide.shapes.add_picture("hero.jpg", Inches(0), Inches(0))
    pic.effects.transparency = 0.2
    pic.effects.brightness = 0.1
    pic.effects.contrast = 0.05
    pic.effects.set_duotone(RGBColor(0x12, 0x1E, 0x4D), "#A8C0FF")

``set_duotone`` accepts |RGBColor|, 6-digit hex strings (with or without
``#``), or RGB 3-tuples.  Anything else — ``"#FFF"``, ``"red"``,
``(300, 0, 0)`` — raises and leaves the picture's current recolour in
place.

``pic.effects.recolor`` selects a preset: ``"grayscale"``, ``"sepia"``,
``"washout"``, ``"black_and_white"`` or ``"duotone"``; ``None`` clears
it.  ``"washout"`` is PowerPoint's Washout, a fixed brightness/contrast
pair (``<a:lum bright="70000" contrast="-70000"/>``), so it reads back
through ``brightness`` and ``contrast`` and is replaced by assigning
either.  ``"black_and_white"`` is the hard two-tone split
(``<a:biLevel>``) that earlier releases wrote for ``"washout"``.

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
