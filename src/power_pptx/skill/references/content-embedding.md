# Styled HTML and SVG → PowerPoint

For visual direction, typography, varied web-style compositions, and the
required all-slide review pass, also read `modern-slide-design.md`. The
repository's `examples/modern_gallery/` provides eight complete examples.

For `from_html(..., mode="hybrid")`, native `Row` / `Column` / `Card` components,
Plotly browser export, and the installed review command, read
`authoring-workflows.md`. The annotated contract lets selected text, charts,
and tables remain editable while preserving complex CSS in captures.

Use a good HTML design as the visual specification. Its spacing, type
hierarchy, color relationships, and composition are valuable even when
the final slide needs editable PowerPoint objects. Preserve those choices
instead of replacing the design with a generic title-and-bullets recipe.

## Choose the output that serves the user

| Need | Workflow | Result |
|---|---|---|
| Editable business content | Read the HTML layout and rebuild text, cards, tables, and charts with native APIs | Editable objects, selectable text |
| Exact browser appearance | `power_pptx.compose.from_html` | One static picture per HTML section; text copied to notes |
| Editable text plus complex visuals | Native text/layout + `add_svg_figure` / `add_html_figure` for illustrations | Editable text with embedded assets |
| Sharp scalable diagrams or logos | `add_svg_figure` / `slide.shapes.add_svg_picture` | Embedded SVG with a raster companion |

When a user asks to recreate an HTML design as slides, prefer native or
hybrid construction if editability matters. Use full-slide capture when
static visual fidelity is the goal. Describe the resulting editability;
an SVG picture is still a picture, rather than a collection of native shapes.
The library does not translate arbitrary HTML/CSS into editable DrawingML.

## Install the optional renderers

```bash
pip install 'power-pptx[embedding]'  # HTML + SVG fallbacks
python -m playwright install chromium
# On a clean Linux CI runner:
python -m playwright install --with-deps chromium
```

`[html]` and `[svg]` are also available separately. All renderer imports are
lazy; ordinary deck authoring does not require a browser. Use
`browser_path="/path/to/chromium"` or `POWER_PPTX_CHROMIUM` to select an
existing Chromium executable. `FigureBackendUnavailable` reports missing
Playwright / Chromium with an install hint.

These are synchronous APIs. In an async app/agent, call them in a worker
with `await asyncio.to_thread(from_html, ...)` instead of running the
Playwright sync API inside the active event loop.

These composition/capture additions are new in this source tree. For an
older pinned package, check that `power_pptx.compose.from_html` is available
before using it; install this source or an updated release as needed.

## Prepare HTML as slide-sized sections

Use a fixed canvas matching the deck, usually 1280 × 720 CSS pixels for
16:9. Use one semantic section per slide, visible in normal DOM flow:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Arial, sans-serif; }
    [data-slide] {
      width: 1280px; height: 720px; padding: 64px;
      background: #102030; color: #ffffff;
    }
    h1 { font-size: 64px; margin: 0 0 32px; }
    p { font-size: 28px; line-height: 1.4; }
  </style>
</head>
<body>
  <section data-slide data-title="A clear visual idea">
    <h1>A clear visual idea</h1><p>One argument, one slide.</p>
  </section>
  <section data-slide data-title="Supporting evidence">
    <h1>Supporting evidence</h1><p>Keep the hierarchy and generous spacing.</p>
  </section>
</body>
</html>
```

Keep assets under the HTML file's directory (e.g. `assets/logo.svg`,
`fonts/brand.woff2`, `style.css`). Local file inputs are served temporarily
on localhost so relative CSS, image, and font URLs resolve. Files outside
that asset root are not served; move shared assets under it. Inline markup
should use self-contained data URLs or explicit absolute resource URLs.
Remote resources still require network access.

For an existing long webpage, reorganize its content into slide sections
before composing. `full_page=True` captures a long image; it does not
paginate a webpage into slides. Framework-specific hidden slides need to
be made visible in a capture/export stylesheet.

## Faithful HTML deck in one call

```python
from pathlib import Path
from power_pptx.compose import from_html

prs = from_html(
    Path("deck.html"),
    selector="[data-slide]",       # DOM order becomes slide order
    slide_size="16:9",
    viewport=(1280, 720),
    device_scale_factor=2,         # 2560 × 1440 captures; same slide geometry
    fit="contain",                # preserve proportions
    check_overflow=True,
    include_notes=True,
)
prs.save("deck.pptx")
```

Sections become static PNG pictures. Visible text is copied to speaker
notes and picture alt text; `data-title`, `aria-label`, or the first
heading names each picture. Notes and alt text help preserve content but
do not make the slide's text selectable/editable or replace a full
accessibility review. Native overlays can be added to `prs.slides[i]`.

The browser waits for document loading, image decoding and web fonts,
then captures with CSS animations disabled and carets hidden. For
asynchronous charts, expose an explicit ready flag in the page and pass
`wait_for_function="window.deckReady === true"`. Default `wait_until="load"`
avoids waiting forever on analytics/streaming connections; request
`"networkidle"` explicitly only when appropriate. Supply `timeout_ms` to
bound each browser operation and resource-readiness wait.

The overflow check detects scroll content larger than each section's
container. It does not prove text legibility, detect every overlapping
child or validate pixels inside canvas/embedded images. Review captures.

## Capture just a diagram, chart, or card

```python
from pathlib import Path
from power_pptx import Presentation, BBox, add_html_figure

prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[6])
picture = add_html_figure(
    slide, Path("diagram.html"), *BBox.from_inches(1, 1.5, 8, 4.5),
    selector="#architecture", viewport=(1280, 720),
    wait_for_function="window.diagramReady === true",
    fit="contain", omit_background=True,
)
picture.alt_text = "Request flow from clients through the gateway to services."
```

The selector must resolve to exactly one visible element. Include padding
inside its bounds if shadows or labels extend beyond the main graphic.
`contain` preserves proportions with spare space; `cover` crops to fill
the requested box; `stretch` deliberately changes proportions. When
geometry is omitted, one CSS pixel maps to 1/96 inch, independent of
capture density. Transparency preserves a transparent HTML background;
explicit CSS background colors remain visible.

For JSON authoring, a `figure` slide can use an HTML path or markup plus
`html_options={"selector": "#architecture", "viewport": [1280, 720]}`.
The same options work with `design.recipes.figure_slide`.

## Embed SVG as a vector asset

```python
from power_pptx import add_svg_figure, BBox

svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 240">
  <rect x="1" y="1" width="638" height="238" rx="24" fill="#0b5cff"/>
  <path d="M140 120 H500 M460 80 L500 120 L460 160"
        fill="none" stroke="white" stroke-width="12"/>
</svg>'''
picture = add_svg_figure(slide, svg, *BBox.from_inches(1, 2, 8, 3))
picture.alt_text = "A left-to-right flow arrow inside a rounded blue panel."
```

Inputs may be Unicode markup, UTF-8 bytes, a path, or a binary stream.
The SVG root must be valid XML; an HTML document containing an inline SVG
is captured as HTML. Identical SVG media are shared across slide occurrences.
Modern Office uses the SVG; older Office and some preview tools use the PNG
fallback. Test both paths. Pass `png_fallback="diagram-high-res.png"` when
you already have a browser-rendered companion; otherwise CairoSVG creates it.

Use self-contained SVG with an explicit `viewBox` and embedded images.
Replace external references with data URLs and convert font-dependent labels
to paths when portability is essential. Text-as-paths is vector artwork,
not editable/searchable text; native text overlays are often better.
Keep source and target aspect ratios equal when specifying both dimensions.
SVG `foreignObject`, scripts, web fonts, and complex CSS filters are not
portable across Office and CairoSVG. For those visuals capture the containing
HTML element with Chromium. Supplying a PNG fallback does not repair an SVG
that modern Office chooses to render incorrectly.

## Recreate the HTML design with editable native content

1. Inspect the HTML and a browser screenshot. Extract palette, font families,
   weights, line heights, radii, grid/gaps, and the hierarchy of each section.
2. Set the deck's real dimensions first. Use browser-computed element bounds
   relative to the section, rather than copying viewport/scroll coordinates.
3. Map those rectangles to `BBox`; rebuild headings/body as text frames,
   cards as shapes, and tabular/chart data as native tables/charts. Translate
   CSS colors and font sizes to the design-token layer where useful.
4. Embed diagrams/logos with SVG or HTML capture when native reconstruction
   would lose their visual quality. Keep key labels and business data native.
   Capture only the graphic's selector, or remove its native-text counterparts
   from the HTML capture first, so native overlays do not duplicate visible text.
5. Mark intentional card/label overlaps with `lint_group_overlaps` or
   `allow_overlap_with`, fit native text using installed font metrics, and
   run `slide.tidy()` / `audit(prs)`.
6. Render the saved deck and compare it with the HTML reference. Correct
   line wrapping, alignment, font fallback, clipping, and spacing before delivery.

At 1280 CSS pixels → 13 1/3 inches, 64px CSS type becomes 48pt native type.
For another canvas width, compute the scale from the actual slide size:

```python
from power_pptx import BBox
from power_pptx.util import Emu, Pt

emu_per_css_px = prs.slide_width / 1280
def css_box(x, y, width, height):
    # x/y have already had the HTML section's origin subtracted.
    return BBox(*(Emu(round(v * emu_per_css_px)) for v in (x, y, width, height)))

def css_font(px):
    return Pt(px * emu_per_css_px / 12700)
```

Use a single uniform scale when canvas and slide aspect ratios match.
If they differ, reflow the source layout or preserve proportions with
padding instead of stretching text. The example in `examples/html_embedding/`
builds both a faithful HTML deck and a native/hybrid companion for comparison.

Account for CSS padding once: if a textbox uses measured content bounds,
set `add_text(..., margin_pt=0, align="left", anchor="top")` instead of
retaining PowerPoint's default insets. Map CSS line height to paragraph
`line_spacing`, and set paragraph font defaults as well as run styling
when inherited styles affect the result. Preserve deliberate line breaks
and compare the actual font metrics before adjusting a box to force a fit.
