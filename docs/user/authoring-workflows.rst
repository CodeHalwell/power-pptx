Modern authoring workflows
==========================

Start from a strong visual direction: a product interface, editorial layout,
or styled HTML document. Preserve its hierarchy, whitespace, and visual rhythm.
``examples/authoring_workflows/`` builds three decks and reviews all nine slides
using the installed APIs described below. The bundled skill's
``references/authoring-workflows.md`` provides the complete annotation contract
and guidance for coding agents.

Measured native components
--------------------------

Use components when text, cards, and charts need to stay editable::

    from power_pptx import Presentation, BBox
    from power_pptx.design import Card, Column, MetricTile, Row, TextBlock
    from power_pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    Column([
        TextBlock("A calmer operating rhythm.", font="DejaVu Sans",
                  size_pt=34, min_size_pt=30, max_lines=1, bold=True),
        Row([
            MetricTile("94%", "Adoption", font="DejaVu Sans"),
            Card([TextBlock("Make the next move clear.", font="DejaVu Sans")]),
        ], gap=Pt(18), height=Inches(3)),
    ], gap=Pt(24)).render(slide, BBox.from_inches(.65, .6, 12, 6), strict_fonts=True)

Rows distribute flexible width using ``grow`` weights; fixed widths win and
badges have intrinsic widths. Columns measure natural heights, then distribute
spare height to children with ``grow``. Padding takes a length, a vertical/
horizontal pair, or four lengths in CSS order. Lengths are EMU (use ``Pt`` or
``Inches``); font sizes are integer points. Fixed child height reserves space
and enables text shrinking within its declared minimum and line budget.

Trees are preflighted before creating shapes. Impossible layouts raise
``LayoutOverflowError``. Names must be unique; component instances cannot be
shared or cyclic. ``result.shapes`` gives all objects and ``result["name"]``
returns a named component's first shape. Background overlap is declared only
with descendants, preserving sibling collision checks. Measured text lines
are saved explicitly so Office does not introduce extra wrapping.

Use ``NativeContent(builder, height=Inches(2))`` for a chart/table/custom slot.
The callable receives ``(slide, bbox)``; its own mutations and errors are outside
tree preflight. Design tokens supply palette aliases and a default body font.

``TextBlock`` also takes ``letter_spacing`` (a length), ``weight`` (``"medium"``,
``600``, …) and ``case="upper"|"lower"``. All three are part of preflight
measurement, so a tracked label that no longer fits raises. Weights other than
regular and bold are measured with their own face and written by its legacy
family name (``"Inter Medium"``), which is how PowerPoint selects them.

A column that a row stretches past its content leaves the spare height under
its last child, so side-by-side cards end at different heights. Preflight warns
with ``LayoutWarning`` (also in ``result.warnings``). ``Column(fill_last=True)``
or ``grow`` on the last child fixes it, and ``slide.lint()`` reports the same
problem on any slide as ``RaggedEdge``.

``DataTable(rows, columns=[...], max_lines=1, truncate=True)`` is a native table
whose row heights are measured from its text. With ``truncate=True``, cells that
exceed ``max_lines`` end in an ellipsis instead of raising.

Bundled fonts
-------------

Register a project's font folder once and measurement, ``strict_fonts=True``,
``render_slides`` and ``power-pptx review`` all use it, with nothing installed
system-wide::

    from power_pptx.text import register_font_dir
    register_font_dir("assets/fonts")   # or POWER_PPTX_FONT_DIRS=assets/fonts

``register_font_family("Inter", regular=..., bold=..., weights={"medium": ...})``
maps explicit files per style. ``power-pptx review --font-dir assets/fonts`` and
``render_slides(prs, font_dirs=[...])`` pass extra folders to LibreOffice for
that run only.

Reproducible builds
-------------------

With ``SOURCE_DATE_EPOCH`` set, saved decks are byte-identical across builds of
the same input. Zip entry times, default core properties and embedded chart
workbook dates all use the pinned time.

Typography constraints
----------------------

``text_frame.fit_text`` accepts ``min_size``, ``max_lines``,
``preserve_breaks``, and ``line_spacing``. A failed fit leaves formatting
unchanged. ``preserve_breaks=True`` forbids additional wrapping, preserving
authored lines and blank lines. ``power_pptx.text.measure_text`` returns
read-only measured lines, dimensions, size, font path, and fallback status.
Use installed fonts with ``strict=True``; metric files do not embed fonts in
the presentation. See the text API reference for complete signatures.

Annotated HTML to editable slides
---------------------------------

``from_html("brief.html", mode="hybrid", reference_dir="browser-reference")``
captures unmarked CSS as a base image, removes annotated regions from it,
and recreates those regions as foreground layers. The default mode remains
full-slide capture. Hybrid requires contain fitting and installed native fonts.

* ``data-pptx="text"`` creates editable text with browser-measured breaks,
  rich runs, basic fonts, color/opacity, underline, alignment, and padding.
* ``data-pptx="chart"`` requires ``data-pptx-chart`` JSON with a type,
  categories, and named series. Supported types are column, bar, line, area,
  pie, and doughnut. Native styling is minimal; data is editable in a workbook.
* ``data-pptx="table"`` belongs on a table and creates editable cells, merges,
  row/column dimensions, basic fonts, fills, padding, and borders.
* ``data-pptx="capture"`` captures a complex visual as an independent PNG.

Annotations belong on slide descendants, cannot nest, and must stay inside
the section. Native regions are ordered by numeric z-index and DOM order;
arbitrary CSS stacking contexts and occlusion are not reconstructed. Keep
unmarked elements behind annotated foreground content. Put text backgrounds
and decoration on unmarked parents. Transforms, RTL/vertical text, letter
spacing, gradient/shadow text, superscripts, and text-transform require capture.
Use separate regions for mixed font sizes. Table cell text is plain; rich cell
runs, captions, nested tables, and complex table decoration need capture or
manual native construction.

Capture regions use their border box. Annotate an outer wrapper with enough
padding to contain shadows, filters, and other visual overflow.

For example::

    <div data-pptx="chart" data-pptx-chart='{"type":"column",
      "categories":["Q1","Q2"],
      "series":[{"name":"Revenue","values":[12,26]}],
      "colors":["#6554E8"]}'>
      <!-- Render the chart here for the original browser reference. -->
    </div>

The chart JSON does not render the browser view. Source chart visuals must
already exist if references are needed. ``font_map`` allows deliberate face
substitution; inspect wrapping after substitution. Web fonts available to
Chromium are not necessarily installed desktop fonts. Reference PNGs retain
the original browser appearance for saved-slide comparison.

Reliable figure export
----------------------

``add_plotly_figure(..., backend="browser", format="svg")`` uses self-contained
Plotly.js, waits for plot readiness, and embeds SVG with a browser PNG fallback.
It requires Plotly plus ``power-pptx[html]`` and Chromium, without CairoSVG or
Kaleido. ``backend="auto"`` tries Kaleido then the browser; ``"kaleido"``
disables fallback. Explicit pixel dimensions override the figure layout and
capture density does not alter physical browser-export dimensions.
``figure_slide(..., plotly_options={"backend": "browser"})`` forwards options.
Matplotlib continues to export through its own SVG/PNG renderer.

Installed review workflow
-------------------------

Install LibreOffice separately, plus Poppler or the PDFium review extra::

    pip install 'power-pptx[embedding,review]'
    python -m playwright install chromium
    power-pptx review deck.pptx --out-dir review
    power-pptx review brief.html --mode hybrid --out-dir review
    power-pptx review one.pptx two.pptx --out-dir batch

Inputs can be PPTX, HTML, JSON, or YAML. HTML automatically retains original
browser references; ``--ready`` waits for application readiness. Optional
``--reference-html`` or ``--reference-dir`` compare rendered slides with
browser views or naturally sorted PNGs. Exactly one reference per slide and
matching aspect ratios are required. ``--max-error .02`` makes normalized
mean pixel error a gate; comparisons are otherwise advisory.

Each output contains the PPTX, PDF, every slide PNG, contact sheets, gallery,
``manifest.json``, and ``REVIEW.md``. Validation covers bundled XSD/package
checks, round-trip fidelity, layout audit, and explicit native font availability.
No test checkout is needed. Missing fonts warn by default; ``--font-policy error``
fails on them. Theme/implicit font availability is outside this inventory.
``--font-dir assets/fonts`` (repeatable) registers a font folder for these checks
and hands it to LibreOffice, so previews use the real face instead of a fallback.
``--fail-on-warnings`` also gates audit warnings. Failures return a nonzero exit
and keep available diagnostics; batches continue and create aggregate navigation.
Only current-run pages enter the manifest, even when old files remain on disk.

Python callers can use ``validate_presentation(prs)`` from
``power_pptx.validation`` and ``review_presentation(prs, out_dir="review")``
from ``power_pptx.review``. Input files are preserved. Review output cannot
overwrite its own input presentation.

Inspect every saved-PPTX render for wrapping, clipping, contrast, composition,
and native chart/table appearance; use full resolution for small type. Record
findings in ``REVIEW.md``. Automated reports deliberately mark visual review
pending. Pixel differences and structural success do not certify appearance or
Microsoft PowerPoint playback.
