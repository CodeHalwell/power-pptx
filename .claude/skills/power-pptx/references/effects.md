# Fills and visual effects (Phase 3 + Phase 6)

**This is the canonical reference for fills, colour alpha, gradients,
and effects.** Other files link here rather than repeat it.

Every shape in `power-pptx` exposes non-mutating effect proxies. Reads
return `None` when nothing is set; writes lazily create the underlying
`<a:effectLst>` / `<a:ln>` element.

Contents: outer shadow · removing a shadow · glow · soft edges · blur ·
reflection · the card look · corner radius · alpha-tinted fills ·
gradient fills · line ends/caps/joins.

## Outer shadow

```python
from power_pptx.util import Pt
from power_pptx.dml.color import RGBColor

shadow = card.shadow
shadow.blur_radius = Pt(8)
shadow.distance    = Pt(4)
shadow.direction   = 90.0          # degrees, 90 = down
shadow.color.rgb   = RGBColor(0, 0, 0)
shadow.color.alpha = 0.35          # 35% opacity
```

To restore inheritance, assign `None` to each property — the
`<a:outerShdw>` element is dropped when the last attribute goes away.

### Removing a shadow entirely: `shadow.clear()`

Restoring inheritance is **not** the same as having no shadow. Auto
shapes created by `add_shape` carry a `<p:style>` with
`<a:effectRef idx="2"/>`, which resolves against the theme's effect
styles — a soft drop shadow in most themes. Clear the explicit
properties and that inherited shadow is what you're left with: the
"phantom shadow I never asked for".

```python
card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, *box)
card.shadow.clear()          # flat card, guaranteed
```

`clear()` drops every explicit shadow element (outer, inner, preset),
writes the empty `<a:effectLst/>` that overrides inherited effects, and
re-points `<a:effectRef>` at the theme's empty slot (`idx="0"`). Other
effects written on the shape — glow, soft edges, blur, reflection — are
kept. Theme-derived ones are not: `effectRef` names one whole entry in
the theme's effect-style list, so if a custom theme pairs its shadow
with a glow, that glow goes too — re-apply it explicitly on the shape.
Stock Office themes reference shadow-only styles, so this rarely bites.
It's idempotent and safe on shapes that never had a shadow, including
text boxes and pictures (which have no `<p:style>` to re-point). On a
shape imported with an `<a:effectDag>` (an effect tree rather than a
flat list) the shadow nodes are pruned from that tree instead — the two
are mutually exclusive in the schema, so writing a list alongside one
would produce a deck PowerPoint offers to repair.

> ⚠ `shadow.inherit` (read or write) emits a `DeprecationWarning` in
> 1.1+. Read individual properties for `None`; use `clear()` to remove.
> `inherit = False` only writes the empty `<a:effectLst/>` — it stays
> symmetric with `inherit = True` and so cannot touch the theme effect
> reference. It does **not** remove an inherited shadow; `clear()` does.

## Glow

```python
card.glow.radius   = Pt(6)
card.glow.color.rgb = RGBColor(0x4F, 0x9D, 0xFF)
```

## Soft edges

```python
card.soft_edges.radius = Pt(3)
```

## Blur

```python
card.blur.radius = Pt(4)
card.blur.grow   = True            # grow with the shape
```

## Reflection

```python
card.reflection.blur_radius = Pt(2)
card.reflection.distance    = Pt(1)
card.reflection.start_alpha = 0.5
card.reflection.end_alpha   = 0.0
```

## Combining for a "card" look

```python
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.util import Inches, Pt
from power_pptx.dml.color import RGBColor

card = slide.shapes.add_shape(
    MSO_SHAPE.ROUNDED_RECTANGLE,
    Inches(1), Inches(1.5), Inches(4), Inches(2.5),
)
card.fill.solid()
card.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
card.line.fill.background()                       # no border

card.corner_radius      = Pt(6)                   # not adjustments[0]

card.shadow.blur_radius = Pt(18)
card.shadow.distance    = Pt(4)
card.shadow.direction   = 90.0
card.shadow.color.rgb   = RGBColor(0, 0, 0)
card.shadow.color.alpha = 0.18

card.soft_edges.radius  = Pt(1)
```

For a **flat** card, swap the four shadow lines for `card.shadow.clear()`
— see above; assigning `None` to them is not equivalent.

### Corner radius in points

`shape.corner_radius` reads and writes a rounded rectangle's radius as a
length, converting to and from the fraction-of-the-shorter-side that
OOXML stores in `adjustments[0]`:

```python
card.corner_radius = Pt(6)
card.corner_radius.pt        # -> 6.0
```

Defined for `ROUNDED_RECTANGLE`, `ROUND_1_RECTANGLE`,
`ROUND_2_SAME_RECTANGLE`, and `ROUND_2_DIAG_RECTANGLE` (the two-radius
geometries keep their second corner pair on `adjustments[1]`). Raises
rather than silently clipping when the radius exceeds half the shorter
side.

## Alpha-tinted fills

```python
card.fill.solid()
card.fill.fore_color.rgb   = RGBColor(0x4F, 0x9D, 0xFF)
card.fill.fore_color.alpha = 0.55                 # glassy
```

`alpha` is also available on the lazy proxy returned by `Font.color`
and `LineFormat.color`:

```python
title_run.font.color.rgb   = RGBColor(0x1F, 0x29, 0x37)
title_run.font.color.alpha = 0.9
```

## Gradient fills

The two-liner most decks want — a multi-stop linear gradient at an
angle:

```python
bar.fill.linear_gradient("#06D6FE", "#B14AED", angle=90)   # top→bottom
bar.fill.linear_gradient(
    [("#06D6FE", 0.0), ("#FFFFFF", 0.5), ("#B14AED", 1.0)],
    angle=45,
)
```

`angle` follows the OOXML convention: `0` is left→right, `90` is
top→bottom, `180` is right→left, `270` is bottom→top.

### Other kinds, and mutable stops

```python
fill = card.fill
fill.gradient(kind="radial")          # also "linear", "rectangular", "shape"
fill.gradient_kind                    # → "radial"

stops = fill.gradient_stops
stops.replace([
    (0.0,  "#0F2D6B"),                # hex with or without leading '#'
    (0.55, RGBColor(0x4F, 0x9D, 0xFF)),
    (1.0,  (255, 255, 255)),          # plain RGB tuple also accepted
])

# Add or remove individual stops
stops.append(0.85, "#A8C0FF")
del stops[1]
```

OOXML enforces a 2-stop minimum; the helper raises if you try to drop
below that.

## Line ends, caps, joins, compound lines

```python
from power_pptx.enum.dml import (
    MSO_LINE_CAP_STYLE,
    MSO_LINE_COMPOUND_STYLE,
    MSO_LINE_JOIN_STYLE,
    MSO_LINE_END_TYPE,
    MSO_LINE_END_SIZE,
)

line = arrow.line
line.head_end.type   = MSO_LINE_END_TYPE.TRIANGLE
line.head_end.width  = MSO_LINE_END_SIZE.MEDIUM
line.head_end.length = MSO_LINE_END_SIZE.LARGE
line.tail_end.type   = MSO_LINE_END_TYPE.OVAL
line.cap             = MSO_LINE_CAP_STYLE.ROUND
line.compound        = MSO_LINE_COMPOUND_STYLE.DOUBLE
line.join            = MSO_LINE_JOIN_STYLE.BEVEL
```

Reads on an unset attribute return `None` — assigning `None` clears
just that attribute. When the last attribute on a head/tail end goes
away the `<a:headEnd>` / `<a:tailEnd>` element is dropped so theme
inheritance is preserved.

## Reading effects without mutating

Always safe to inspect:

```python
if card.shadow.blur_radius is None:
    print("no explicit shadow")
else:
    print("blur:", card.shadow.blur_radius.pt)
```

No `<a:effectLst>` is written by the read.

## Inner & preset shadows

Besides `shape.shadow` (outer), shapes expose two sibling shadow effects:

```python
shape.inner_shadow.blur_radius = Pt(4)    # shadow cast INTO the shape
shape.inner_shadow.distance = Pt(3)
shape.inner_shadow.direction = 45.0
shape.inner_shadow.color.rgb = "112233"

shape.preset_shadow.preset = "shdw5"      # or MSO_PRESET_SHADOW.SHADOW_5
shape.preset_shadow.color.rgb = "aabbcc"  # one of shdw1..shdw20
```

A colour child and the required `prst` are written automatically, so
geometry-only shadows stay schema-valid.
