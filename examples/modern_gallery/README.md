# Modern slide gallery

Eight fictional brands, eight decks, 32 slides. These examples explore the
visual language of web products: strong type, bento dashboards, dark developer
tools, editorial whitespace, scientific plots, commerce UI, glass, and posters.
They use real power-pptx APIs and include their HTML/SVG sources.

| Deck | Approach | Features |
| --- | --- | --- |
| Forma | Editable native | Cards, shadow, native column chart, KPI component, pipeline, pricing table |
| Relay | Editable native | Dark chart, gradient, code, status pill, progress bar, arrows |
| Fieldwork | Editable native + SVG | Serif display type, vector art, quote, timeline |
| Lumen | Hybrid | Matplotlib SVG confidence band, HTML panel, native text, cross-deck import |
| Current | Hybrid | Plotly browser SVG Sankey, native doughnut and merged table |
| Aster | Captured HTML | Glass, radial gradients, layered interface, SVG network |
| Daily | Captured HTML | SVG packaging, rotations, drop shadows, asymmetric CSS grid |
| Offgrid | Captured HTML | Large display type, clip paths, SVG star, scripted canvas |

The first five decks keep their main text editable. Native charts/tables retain
their data. Embedded artwork is a picture. The last three decks contain one
static browser capture per slide; their text is copied into notes and picture
alt text, but their visible content is not editable as PowerPoint text.

## Reproduce from the repository root

Use a source checkout that exposes `power_pptx.compose.from_html` (these examples
use APIs newer than the original 2.12.0 PyPI release):

```bash
python -m pip install -e '.[embedding]' -r requirements-test.txt matplotlib plotly
python -m playwright install --with-deps chromium
# Install LibreOffice Impress, Poppler, and the DejaVu Sans/Serif/Mono fonts.
# Ubuntu: sudo apt-get install libreoffice-impress poppler-utils fonts-dejavu-core
python examples/modern_gallery/build.py --render --out-dir /tmp/modern-gallery
```

For an existing Chromium installation, add `--browser-path /path/to/chromium`.
To refine one deck, add `--deck 01-forma` (repeat for several decks).
Without `--render`, only the structural checks run. The HTML files under `html/`
are self-contained and need no CDN or external images. Current builds its Plotly
HTML with inline JavaScript. Kaleido is not needed: this also supports managed
browsers that disallow Kaleido's local `file://` page.

Open the output's `index.html` for every slide preview and PPTX downloads.
`manifest.json` records schema, canonical package round-trip, lint, image, and
render checks. `*-audit.md` explains lint/font advisories. Contact sheets and
individual PNGs support visual review. For HTML decks the builder compares every
render to its browser capture, allowing 1.5% mean absolute channel error after
resizing. This catches material rendering changes; it does not measure design
quality. `REVIEW.md` starts as **pending** so a new build never claims a reviewer
has approved its appearance.

The schema validator ships in the installed package; no test checkout is needed.
Generated output is ignored by git. Native typography requires the named fonts on the machine
opening the deck; the examples do not embed fonts.

## Broad feature probes

The existing stress suite exercises 14 decks / 142 slides, including effects,
all transition kinds, chart layouts, tables, diagrams, 3D, multilingual text,
picture filters, groups, media markup, and composition. To validate and render
**every** slide with labeled contact sheets:

```bash
python examples/modern_gallery/stress.py --render --out-dir /tmp/pptx-stress
```

Use `--deck 04` to inspect one area. These probes include deliberately tiny or
clipped content and renderer limitations; they are QA fixtures. The modern
gallery is the design reference. Static LibreOffice output does not establish
Microsoft PowerPoint transition, animation, media, or 3D playback fidelity.

## Review before delivery

Render the saved deck, inspect every slide, and enlarge charts, dense tables,
and large headlines. Check hierarchy, actual wrapping, padding, contrast,
cropping, diagram spacing, and consistency with the source. Re-render any changed
deck. Preserve the intended headline breaks by adjusting type size, box width,
or copy, instead of relying on shrinking the entire slide. Keep business content
editable where practical; use HTML and SVG for visuals that benefit from them.

See the bundled skill's `modern-slide-design.md` and `content-embedding.md` for
the complete authoring guidance.
