# Modern authoring workflows

Build three decks / nine slides through the public APIs, then validate and
render every page:

```bash
pip install '.[embedding,review]' plotly
python -m playwright install chromium
# Install LibreOffice and Poppler, plus the DejaVu Sans font family.
python examples/authoring_workflows/build.py --out-dir /tmp/workflows
```

Use `--browser-path /usr/bin/chromium` for an existing browser. Open
`/tmp/workflows/index.html`; inspect all slides and record findings in each
deck's `REVIEW.md`.

* Northstar: measured native rows, columns, cards, badges, metrics, typography
  constraints, and a native chart slot.
* Orbit: annotated HTML to editable rich text, chart/workbook, and table, with
  SVG/CSS artwork captured separately. Original browser views and pixel
  differences are retained; native chart styling is deliberately different.
* Signal: Sankey, line, and treemap Plotly figures exported through the browser
  backend, as SVG with PNG fallback and high density PNG.

All build and review logic uses the installed package. Nothing imports tests.
The installed `power-pptx review` command also accepts existing decks, HTML,
JSON, and YAML, singly or in batches. API and limitations are documented in
`src/power_pptx/skill/references/authoring-workflows.md`.
