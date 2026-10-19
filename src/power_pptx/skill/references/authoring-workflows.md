# Components, editable HTML, typography, and review

Use these APIs to carry a web-quality visual direction into slides with less
manual geometry. Pair this guide with `modern-slide-design.md` and
`content-embedding.md`. Reproducible examples: `examples/authoring_workflows/`.

## Native components

```python
from power_pptx import BBox
from power_pptx.design import Badge, Card, Column, MetricTile, Row, TextBlock
from power_pptx.util import Inches, Pt

content = Column([
    TextBlock("A calmer operating rhythm.", font="DejaVu Sans", size_pt=34,
              min_size_pt=30, max_lines=1, bold=True),
    Row([
        MetricTile("94%", "Adoption", detail="Across 18 teams", font="DejaVu Sans"),
        Card([
            Badge("LIVE", font="DejaVu Sans"),
            TextBlock("Everything in its right place.", font="DejaVu Sans",
                      size_pt=22, max_lines=2),
        ]),
    ], gap=Pt(18), height=Inches(3.2)),
], gap=Pt(24))
result = content.render(slide, BBox.from_inches(.65, .6, 12, 6), strict_fonts=True)
```

Lengths use `Inches`, `Pt`, or EMU; font sizes use integer points. `padding`
accepts one length, `(vertical, horizontal)`, or `(top, right, bottom, left)`.
Rows distribute remaining width among flexible children, weighted by `grow`
(default equal). A fixed `width` wins; badges have intrinsic width. Columns
measure natural child heights, then distribute spare height to `grow` children.
Use fixed `height` to reserve a region or to allow text to fit a smaller box.
Containers support `align="start|center|end|stretch"` and
`justify="start|center|end|space-between"`.

Trees are preflighted before creating shapes. Impossible dimensions, fonts,
duplicate names, reused nodes, and overflow raise rather than shrinking below
the minimum. `LayoutOverflowError` means revise copy, type, or region size.
Text and cards stay editable. `name=` makes `result["name"]` return that
component's first shape; `result.shapes` contains all created objects.
Container backgrounds declare intentional overlap only with descendants;
sibling collision checks remain active. Do not disable lint for an entire tree.
`estimated_fonts` identifies fallback measurements; use installed fonts and
`strict_fonts=True` for final output. Font metrics do not embed font files.

Use `NativeContent(builder, height=Inches(2))` for charts, tables, and figures.
The builder receives `(slide, bbox)` and draws inside that box. Its behavior
is outside tree preflight; validate the result and avoid side effects on failure.
Design-token palette keys work for colors; the body token supplies a default font.

## Bundled fonts that measure the same everywhere

Ship brand fonts next to the code and register the folder once, before any
measurement. No system install, Dockerfile step, or CI copy is needed, and
`strict_fonts=True` behaves the same on every machine:

```python
from pathlib import Path
from power_pptx.text import register_font_dir, register_font_family

register_font_dir(Path(__file__).parent / "assets" / "fonts")
# or, outside Python: POWER_PPTX_FONT_DIRS=assets/fonts (os.pathsep-separated)

# Optional: pin exact files when name tables don't match the deck's family
register_font_family("Inter", regular="fonts/Inter-Regular.ttf",
                     bold="fonts/Inter-Bold.ttf",
                     weights={"medium": "fonts/Inter-Medium.ttf"})
```

Registered folders and families take precedence over system fonts. Each style
is looked up separately, so a bold `TextBlock` measures with the bold file.
If a registered name is an alias (`"Brand Sans"` for Outfit files), components
write the files' own family (`"Outfit"`) into the deck. Otherwise Office, which
has never heard of the alias, would substitute a different font.
Registered folders are also handed to LibreOffice by `render_slides` and
`power-pptx review`. Avoid `TextBlock(font_file=...)` for multi-style text:
one file then measures every style.

## Tracked labels, weights, and case

```python
TextBlock("Active customers", font="Inter", size_pt=9, min_size_pt=9,
          max_lines=1, case="upper", letter_spacing=Pt(1.4), weight="semibold")
```

`letter_spacing` (a length) is included in measurement and written to every
run, so a tracked eyebrow that no longer fits raises `LayoutOverflowError`
instead of overflowing silently. `case="upper"|"lower"` transforms the text
before measuring and drawing. `weight` takes `"thin"` … `"black"` or `100`–`900`.
Regular and bold are written as the family plus the bold flag. Other weights
need their static face file (variable fonts aren't read). They are measured
with that face and written by its legacy family name, e.g. `"Inter SemiBold"`,
which is how PowerPoint selects them. Without the face, `strict_fonts=True`
raises. Otherwise the nearest regular/bold face is measured and drawn, and the
block is listed in `result.estimated_fonts`. `bold=True` with another weight is
an error.

## Bottom edges that line up

`Row([Card(...), Column([Card(...), Card(...)])])` stretches the column to the
row's height. Unless a child takes the spare height, it sits under the last
card and the two sides end at different heights. Preflight warns
(`LayoutWarning`, also listed in `result.warnings`). Fix it with
`Column([...], fill_last=True)`, or `grow=1` on the last child. `slide.lint()`
reports the same problem on any slide as `RaggedEdge`: a filled rounded panel
that ends more than 1.5pt above the panels beside it, with nothing beneath it.

## Measured tables

```python
from power_pptx.design import DataTable
DataTable([["Region", "Revenue", "Note"], ["EMEA", "£4.2m", long_note]],
          columns=[1, 1, 2], align=["left", "right", "left"],
          font="Inter", size_pt=11, max_lines=1, truncate=True, name="revenue")
```

Row heights are measured from the cell text with the header bold, so the table
never grows past its slot. `max_lines` caps each cell. With `truncate=True`,
over-long cells end in an ellipsis; without it they raise `LayoutOverflowError`.
`columns` gives relative widths. Header and body colours, fills and borders are
keyword options; the table takes its measured height at the top of its region.
For one-off text, `power_pptx.text.truncate_text(text, width, max_lines=1,
size_pt=..., font_family=...)` returns the shortened string. Like
`measure_text`, it warns when a named font is missing and raises with
`strict=True`.

## Typography without indiscriminate shrinking

```python
size = shape.text_frame.fit_text(
    font_family="DejaVu Sans", max_size=36, min_size=28,
    max_lines=2, preserve_breaks=True, line_spacing=1.15, strict=True,
)
from power_pptx.text import measure_text
metrics = measure_text("A short heading", Inches(6), size_pt=28,
                       font_family="DejaVu Sans", strict=True)
```

`preserve_breaks=True` permits only the authored lines, including blank lines;
it forbids additional wrapping. `max_lines` sets the total visual line budget.
An unsatisfiable fit raises before changing formatting. `measure_text` is
read-only and returns `lines`, dimensions, chosen size, font path, and fallback
status. Measure with the actual bold/italic style. Whole words must fit.

## Explicit HTML annotations

Keep HTML slide sections fixed at 1280 × 720, with installed native fonts.
Annotate the elements the user needs to edit:

```html
<section data-slide data-title="Team signals">
  <div class="card-background"></div>
  <h1 data-pptx="text" data-name="Headline">Momentum you can measure.</h1>
  <div data-pptx="chart" data-pptx-chart='{"type":"column",
       "categories":["Week 1","Week 2"],
       "series":[{"name":"Activation","values":[42,94]}],
       "colors":["#6554E8"]}'><!-- browser-rendered chart here --></div>
  <table data-pptx="table"><tr><th>Focus</th><th>Status</th></tr>
    <tr><td>Team rollout</td><td>Ready</td></tr></table>
  <div data-pptx="capture"><!-- complex CSS / SVG / canvas --></div>
</section>
```

```python
from power_pptx.compose import from_html
prs = from_html("brief.html", mode="hybrid", reference_dir="browser-reference")
```

Unmarked CSS becomes a base image. Annotated regions are removed from the
base, then added as foreground objects in ascending z-index and DOM order.
Annotations belong on descendants, cannot nest, and must fit inside the section.
Use this foreground-layer model deliberately; arbitrary CSS stacking contexts,
occlusion, and overlapping unmarked foreground elements are not reconstructed.
Hybrid requires `fit="contain"`. Full capture remains the default mode.

`text` preserves browser-measured line breaks, plain/rich text, font family,
size, bold, italic, RGB color/opacity, underline, alignment, and padding.
Use separate annotations for mixed font sizes. Put card backgrounds, borders,
and decoration on unmarked parent/sibling elements. Transforms, RTL/vertical
text, text-transform, letter spacing, gradient/shadow text, superscripts, and
embedded visuals require capture. Unsupported native styling fails contextually.
`font_map={"Brand Sans": "DejaVu Sans"}` permits deliberate substitution;
browser/native metrics can then differ, so inspect references. Strict installed
font checking is on by default. Web-font availability alone does not install
the native desktop face.

`chart` builds an editable chart with an embedded workbook from explicit JSON.
Supported types: column, bar, line, area, pie, doughnut. Series values must match
the categories and be finite numbers or null. Options: colors, title, legend.
It uses a minimal native chart style; HTML chart styling is not translated.
The browser region must already contain a visual for a meaningful reference.

`table` builds editable cells, merges, column/row dimensions, basic cell fonts,
fills, padding, and borders. Cell text is plain, so rich mixed runs, complex
CSS table decoration, captions, and nested tables should use capture or manual
native construction. `capture` is a static PNG region with alt text.
Capture regions use their border box; include an outer wrapper with enough
padding to contain shadows, filters, and other visual overflow.
Original views are saved by `reference_dir` for render comparisons.

## Plotly export through a real browser

```python
from power_pptx import add_plotly_figure
add_plotly_figure(slide, figure, *bbox, backend="browser", format="svg",
                  browser_path="/usr/bin/chromium", width_px=1100, height_px=400)
# figure_slide(..., plotly_options={"backend": "browser"}) also works.
```

`backend="auto"` first tries Kaleido, then falls back to Playwright when the
figure supports `to_html`. `backend="kaleido"` disables fallback. Browser export
uses self-contained Plotly.js, waits for plot readiness/fonts/images, and
produces SVG plus its browser PNG fallback, or PNG alone. No CairoSVG is needed
for browser SVG export. Install Plotly separately and `power-pptx[html]` plus
Chromium. Prefer explicit slide bounds; changing capture density does not
change the browser export's physical dimensions. Matplotlib retains its own
direct SVG/PNG exporter.

## One review command, including batch inputs

```bash
pip install 'power-pptx[embedding,review]'
python -m playwright install chromium
# Install LibreOffice separately; Poppler or the review PDFium extra rasterizes PDF.
power-pptx review deck.pptx --out-dir review
power-pptx review brief.html --mode hybrid --out-dir review
power-pptx review one.pptx two.pptx --out-dir batch
power-pptx review deck.pptx --reference-html brief.html --out-dir compare
```

PPTX, HTML, JSON, and YAML inputs are accepted. HTML inputs automatically save
their original browser references. `--ready 'window.appReady === true'` waits
for a framework app. Explicit `--reference-dir` takes naturally sorted PNGs
with exactly one page per slide. `--max-error .02` makes normalized mean pixel
error a gate; otherwise differences are advisory. Native charts can look
different from browser charts by design, so inspect them rather than setting
an arbitrary tight threshold. References must match slide aspect ratios.

Outputs: PPTX, PDF, every rendered PNG, paginated contact sheets, XSD/package
and round-trip checks, layout audit, explicit-font availability, difference
images, `manifest.json`, `index.html`, and `REVIEW.md`. XSDs ship in the package;
no repository test modules are needed. Missing explicit fonts are warnings;
use `--font-policy error` for a strict gate. Theme/implicit fonts are outside
this font inventory's scope. `--fail-on-warnings` also gates audit warnings.
Nonzero exit means an automated failure; batch processing continues and writes
an aggregate index. Reused output directories list only this run's pages.
Existing unrelated files remain, so consume the manifest instead of globbing.

Python equivalents: `power_pptx.validation.validate_presentation(prs)` and
`power_pptx.review.review_presentation(prs, out_dir="review")`.

`--font-dir assets/fonts` (repeatable; `font_dirs=` in Python) registers a
folder for the font checks and points LibreOffice at it. Without it, a font
that isn't in a system folder previews in a fallback face. This is common on
macOS, where LibreOffice's bundled fontconfig doesn't search `~/Library/Fonts`.
Folders already registered with `register_font_dir` are passed through
automatically.

## Reproducible builds

Set `SOURCE_DATE_EPOCH` (seconds since 1970) and two builds of the same input
are byte-identical. It pins zip entry times, the default package core
properties, and the created/modified dates inside embedded chart workbooks.
Use it for content-hash caching and for diffing generated decks.

**Inspect every rendered slide**, including full-resolution images where type
is small. Check wrapping, clipping, contrast, composition, native chart/table
appearance, and differences from the browser view. Record actual findings in
`REVIEW.md`; generated reports deliberately mark visual review pending.
Automated success is not a visual approval or a Microsoft PowerPoint playback
test. Avoid declaring a deck visually checked based only on a green report.
