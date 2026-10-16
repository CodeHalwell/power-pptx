# Modern slides: use the visual language of the web

Start from the story and a visual direction. A deck can feel like a carefully
designed product page, editorial feature, or React interface while still using
editable PowerPoint objects. A styled HTML document is an excellent reference
for its hierarchy, layout, type, colors, and spacing. Read
`content-embedding.md` for the capture and reconstruction APIs.

## Choose an approach deliberately

| Need | Approach |
| --- | --- |
| Editable numbers and narrative | Native text, charts, tables, and shapes; SVG for artwork |
| Precise CSS, complex interface, glass, canvas, or web visualization | Capture fixed-size HTML sections with `compose.from_html` |
| Rich visual plus editable story | Capture the visual's selector, then add native headings and annotations |

React/JSX needs to be compiled and rendered in a browser first. Pass the rendered
HTML or built local HTML entry point, with its assets under that directory.
Wait for a real application readiness flag; do not assume a timeout means the
application finished. Browser captures preserve a static state, including canvas
and inline SVG, rather than React components or interactive controls.

The repository's `examples/modern_gallery/` contains eight complete directions:

- **Forma:** a light product launch, bento dashboard, workflow, and pricing table.
- **Relay:** dark developer platform, code, architecture, and a native line chart.
- **Fieldwork:** restrained editorial type, organic vector art, quote, and timeline.
- **Lumen:** research narrative, vector confidence bands, hybrid network visual.
- **Current:** finance UI, cash-flow Sankey, revenue mix, editable operating plan.
- **Aster:** layered glass, luminous gradients, a contextual interface.
- **Daily:** commerce packaging, asymmetric grids, digital storefront.
- **Offgrid:** oversized type, clipped cards, SVG and canvas poster graphics.

Use these as composition references. Match the user's content, brand, and
editability needs instead of putting every deck into the same template.

## Establish the design system

1. Fix the canvas, normally 1280 × 720 CSS pixels / 13⅓ × 7½ inches.
   Keep a common safe area, such as 64px, and a small spacing scale.
2. Choose a background, text color, muted text, and one or two accents. Dark
   decks need explicit chart text, axis, and gridline colors.
3. Use one body family and at most one display family. Verify the actual fonts
   are installed before fitting native text. Use `strict=True` or a bundled font
   file for measurement. Fonts are not automatically embedded in PowerPoint.
4. Set a few type roles: display headlines, section headlines, body, and caption.
   On this canvas 64px maps to 48pt, and 24px maps to 18pt. Leave generous leading.
5. Build consistent reusable cards, pills, panels, chart containers, and footers.
   Use `BBox.columns` / `Grid` for geometry and tokens for repeated styles.

Choose a few compositions that serve different kinds of information: hero,
asymmetric dashboard, product interface, annotated chart, process, comparison,
quote, and closing statement. Alternate density and scale. An editorial page may
need only a large sentence and an illustration; a decision page may need a
compact table. Use cards when they express groups, rather than enclosing every
sentence. Reserve gradients, shadows, and glass for a clear visual purpose.

## Translate browser styling thoughtfully

- **Headlines:** native and browser wrapping differ, even with the same font.
  Measure and render at the intended size. Set deliberate line breaks, and
  adjust copy, width, or size to preserve them. `fit_text` ensures physical fit;
  it does not choose the most attractive line breaks.
- **Padding:** native text has default insets. Use `margin_pt=0` for text placed
  on a measured grid; add padding through the text's bounding box. Set vertical
  anchor and paragraph `line_spacing` explicitly.
- **Flat cards:** use `shape.shadow.clear()` before adding any chosen shadow.
  Native shapes can inherit a theme shadow even without an explicit effect.
- **Overlays:** declare a card and its actual children as intentional overlaps.
  Keep unrelated headings and neighboring cards outside that group so collision
  checks remain useful. Avoid duplicate native and captured text.
- **SVG:** give each inline SVG's gradient/mask/clip IDs unique names. Repeated
  `id="gradient"` values in one HTML document can make another visual's colors
  appear. Keep view boxes and target aspect ratios consistent. For standalone
  SVG, avoid `foreignObject`, script, and unsupported web filters.
- **Charts:** keep ticks and labels legible at slide size. Prefer direct labels
  or a short legend, thin gridlines, and clear units. For pie percentages use
  percentage labels, rather than applying `0%` to raw values such as `30`.
  Use a native chart when data editing matters; capture a browser chart when
  the visual form needs it. Scientific plots should preserve uncertainty.
- **Diagrams:** give connectors visible space. Use larger nodes or fewer labels
  before shrinking text. Even a geometrically valid 24-node diagram may be too
  dense for a presentation.

## Make visual review a delivery step

Create a representative slide first, render it, and inspect the actual output
before repeating its patterns. After building the whole deck:

1. Validate schema and save/reopen fidelity; run lint/audit.
2. Render **every slide of the saved PPTX**, with the expected slide count.
   Review contact sheets for rhythm and consistency, then inspect individual
   pages for text, charts, and details. A browser screenshot alone does not
   verify the saved PowerPoint file.
3. Check accidental wraps, clipped descendants, text over other text, padding,
   contrast, SVG fallback, crops, and diagram spacing. The HTML overflow check
   inspects the selected section, and does not certify every clipped descendant.
   The slide linter cannot inspect text inside a captured image.
4. Fix the source and re-render every affected page. Record what was inspected,
   what changed, and the renderer used. Keep automated validation separate from
   an appearance approval.
5. Deliver PPTX, useful previews, source assets, and an honest editability note.
   Test animations/media in the target PowerPoint application if requested;
   static previews cannot establish playback behavior.

The modern gallery builder automates structural validation, all-page rendering,
contact sheets, and browser/render comparison for its captured decks. Its CI
artifact is review material; a passing build never substitutes for this visual
pass. The older stress decks cover breadth and intentionally contain edge
cases, so they are not the aesthetic target.
