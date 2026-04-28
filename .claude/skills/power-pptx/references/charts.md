# Charts: palettes, quick layouts, per-series fills (Phase 10)

The chart helpers below stack on top of the existing chart API; nothing
here replaces `chart_style` or the underlying series formatting — they
just make common operations one line each.

## A baseline chart

```python
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches

prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[5])
slide.shapes.title.text = "Run-rate metrics"

data = CategoryChartData()
data.categories = ["Q1", "Q2", "Q3", "Q4"]
data.add_series("ARR", (100, 130, 155, 182))
data.add_series("NDR (%)", (115, 118, 124, 131))

chart_shape = slide.shapes.add_chart(
    XL_CHART_TYPE.COLUMN_CLUSTERED,
    Inches(1), Inches(2), Inches(11), Inches(5),
    data,
)
chart = chart_shape.chart
```

## Chart palettes

`Chart.apply_palette(palette)` recolors every series in declaration
order from a named built-in or an iterable of color-likes. Palettes
wrap when the chart has more series than colors:

```python
chart.apply_palette("modern")          # built-in
chart.apply_palette(["#4F9DFF", "#7FCFA1", "#F7B500"])

# Mix and match — any color-like works
from pptx.dml.color import RGBColor
chart.apply_palette([
    RGBColor(0x4F, 0x9D, 0xFF),
    "#7FCFA1",
    (247, 181, 0),
])
```

Six built-ins ship in `pptx.chart.palettes`:

- `modern`
- `classic`
- `editorial`
- `vibrant`
- `monochrome_blue`
- `monochrome_warm`

```python
from pptx.chart.palettes import (
    CHART_PALETTES,
    palette_names,
    resolve_palette,
)

print(palette_names())                 # → ['modern', 'classic', ...]
colors = resolve_palette("editorial")  # → list[RGBColor]
```

`resolve_palette` is also handy for sharing the same colors with
non-chart shapes.

The `chart_style` integer is left untouched, so the palette overrides
only the per-series fill without rewriting the rest of the style.

## Quick layouts

`Chart.apply_quick_layout(layout)` toggles title / legend / axis-title
/ gridline visibility in opinionated combinations. Ten built-in
presets ship in `pptx.chart.quick_layouts`:

```python
chart.apply_quick_layout("title_legend_right")
chart.apply_quick_layout("title_legend_bottom")
chart.apply_quick_layout("title_legend_top")
chart.apply_quick_layout("title_legend_left")
chart.apply_quick_layout("title_no_legend")
chart.apply_quick_layout("no_title_no_legend")
chart.apply_quick_layout("title_axes_legend_right")
chart.apply_quick_layout("title_axes_legend_bottom")
chart.apply_quick_layout("minimal")
chart.apply_quick_layout("dense")
```

Custom layouts can be supplied as a dict spec:

```python
chart.apply_quick_layout({
    "has_title":       True,
    "title_text":      "ARR ($M)",
    "has_legend":      True,
    "legend_position": "bottom",
    "category_axis":   {"has_major_gridlines": False},
    "value_axis":      {"has_major_gridlines": True,
                        "tick_labels": True},
})
```

Missing keys leave the chart untouched so layouts compose cleanly.
Charts without category/value axes (e.g. pie) silently skip the
corresponding keys.

## Per-series gradient and pattern fills

`chart.series[i].format.fill` is a regular `FillFormat`, so all four
gradient kinds and `MSO_PATTERN_TYPE` patterns work per-series with no
chart-specific shim:

```python
fill = chart.series[0].format.fill
fill.gradient(kind="linear")
fill.gradient_stops.replace([
    (0.0, "#0F2D6B"),
    (1.0, "#4F9DFF"),
])

# Patterned fill on the second series
from pptx.enum.dml import MSO_PATTERN_TYPE
pat = chart.series[1].format.fill
pat.patterned()
pat.pattern   = MSO_PATTERN_TYPE.WIDE_DOWNWARD_DIAGONAL
pat.fore_color.rgb = (0x10, 0xB9, 0x81)
pat.back_color.rgb = (0xFF, 0xFF, 0xFF)
```

## End-to-end: branded chart

```python
chart.apply_palette("modern")
chart.apply_quick_layout("title_axes_legend_bottom")

# Override the title text
chart.chart_title.text_frame.text = "ARR & NDR ($M / %)"
```
