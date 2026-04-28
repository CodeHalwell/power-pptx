# Visual effects (Phase 3 + Phase 6)

Every shape in `power-pptx` exposes non-mutating effect proxies. Reads
return `None` when nothing is set; writes lazily create the underlying
`<a:effectLst>` / `<a:ln>` element.

## Outer shadow

```python
from pptx.util import Pt
from pptx.dml.color import RGBColor

shadow = card.shadow
shadow.blur_radius = Pt(8)
shadow.distance    = Pt(4)
shadow.direction   = 90.0          # degrees, 90 = down
shadow.color.rgb   = RGBColor(0, 0, 0)
shadow.color.alpha = 0.35          # 35% opacity
```

To clear, assign `None` to each property — the `<a:outerShdw>` element
is dropped when the last attribute goes away, restoring inheritance.

> ⚠ `shadow.inherit` (read or write) emits a `DeprecationWarning` in
> 1.1+. Read individual properties for `None` instead.

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
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

card = slide.shapes.add_shape(
    MSO_SHAPE.ROUNDED_RECTANGLE,
    Inches(1), Inches(1.5), Inches(4), Inches(2.5),
)
card.fill.solid()
card.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
card.line.fill.background()                       # no border

card.shadow.blur_radius = Pt(18)
card.shadow.distance    = Pt(4)
card.shadow.direction   = 90.0
card.shadow.color.rgb   = RGBColor(0, 0, 0)
card.shadow.color.alpha = 0.18

card.soft_edges.radius  = Pt(1)
```

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

## Gradient fills with kinds and mutable stops

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
from pptx.enum.dml import (
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
