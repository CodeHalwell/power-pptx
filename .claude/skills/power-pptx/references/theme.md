# Themes (Phase 6 + 7)

`Presentation.theme` returns a `Theme` proxy that's both readable and
writable. Theme parts are loaded as a typed `ThemePart(XmlPart)` so
writes round-trip on save.

## Reading the palette

```python
from pptx.enum.dml import MSO_THEME_COLOR

accent1 = prs.theme.colors[MSO_THEME_COLOR.ACCENT_1]    # → RGBColor
accent2 = prs.theme.colors[MSO_THEME_COLOR.ACCENT_2]
bg1     = prs.theme.colors[MSO_THEME_COLOR.BACKGROUND_1]    # canonical lt1
text1   = prs.theme.colors[MSO_THEME_COLOR.TEXT_1]          # canonical dk1
hyper   = prs.theme.colors[MSO_THEME_COLOR.HYPERLINK]
follow  = prs.theme.colors[MSO_THEME_COLOR.FOLLOWED_HYPERLINK]
```

The six accent slots, the dk1/dk2/lt1/lt2 background slots, and the
hyperlink slots are addressable.

## Reading fonts

```python
major = prs.theme.fonts.major     # heading font (str)
minor = prs.theme.fonts.minor     # body font  (str)
```

## Writing the palette

```python
from pptx.dml.color import RGBColor

prs.theme.colors[MSO_THEME_COLOR.ACCENT_1] = RGBColor(0x4F, 0x9D, 0xFF)
prs.theme.colors[MSO_THEME_COLOR.ACCENT_2] = RGBColor(0x10, 0xB9, 0x81)
```

Alias slots (`BACKGROUND_1` / `BACKGROUND_2` / `TEXT_1` / `TEXT_2`)
resolve to their canonical `lt1` / `lt2` / `dk1` / `dk2` target.

## Writing fonts

```python
prs.theme.fonts.major = "Inter"
prs.theme.fonts.minor = "Inter"
```

Rewrites the `<a:majorFont>/<a:minorFont>/<a:latin typeface=…/>`
typeface.

## Bulk-copy from another theme

```python
brand = Presentation("brand.potx")
prs.theme.apply(brand.theme)        # copies palette + major/minor fonts
```

## Theme-aware color resolution

`pptx.inherit.resolve_color` returns the effective `RGBColor` for any
`ColorFormat` (or the lazy proxy on `Font.color` / `LineFormat.color`).
Explicit RGB values are returned as-is, scheme colors resolve through
the theme, and unset colors return `None` without mutating XML:

```python
from pptx.inherit import resolve_color

rgb = resolve_color(run.font.color, theme=prs.theme)
if rgb is None:
    print("inherits from layout/master")
else:
    print("effective color:", rgb)
```

`brightness` is honoured by blending toward white or black, mirroring
PowerPoint's `lumMod` / `lumOff` model.

> ⚠ Full placeholder-walking (`slide → layout → master`) is *not*
> implemented; this resolver covers the 80% case (theme-color lookup)
> without touching XML.

## End-to-end: rebrand a deck

```python
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_THEME_COLOR

prs = Presentation("input.pptx")

# Punchy palette
prs.theme.colors[MSO_THEME_COLOR.ACCENT_1] = RGBColor(0xFF, 0x66, 0x00)
prs.theme.colors[MSO_THEME_COLOR.ACCENT_2] = RGBColor(0x12, 0x1E, 0x4D)
prs.theme.colors[MSO_THEME_COLOR.HYPERLINK] = RGBColor(0x12, 0x1E, 0x4D)

# Inter everywhere
prs.theme.fonts.major = "Inter"
prs.theme.fonts.minor = "Inter"

prs.save("rebranded.pptx")
```

Anything in the deck that referenced `accent1` / `accent2` /
`majorFont` / `minorFont` will pick up the new values automatically.
