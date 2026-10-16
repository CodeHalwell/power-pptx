# Visual review — 16 October 2026

The code agent inspected all nine saved-PPTX renders in contact sheets, with
full-resolution checks of hybrid artwork, rich headlines, the native table,
and browser figure labels. All 32 modern gallery slides were also rebuilt,
rendered, and inspected again, including Current's browser-exported SVG Sankey.

## Findings and corrections

* Northstar / components: the initial LIVE WORKSPACE badge wrapped in Office.
  Components now save measured line breaks and disable additional wrapping.
  Final headings, card copy, metrics, and the native chart are readable and
  contained. One OffGridDrift warning remains for the badge label's intentional
  padding; sibling collision checks remain active.
* Orbit / annotated HTML: headings and body copy are editable without duplicate
  text behind them. Rich runs and blank lines survive save/reopen. The initial
  artwork capture clipped its shadow; a padded outer capture wrapper now
  contains the complete effect. The chart has an editable workbook. Table
  cells, bold statuses, fills, and borders stay editable. Explicit absent borders
  and shared-edge reconciliation remove default lines and preserve HTML row rules.
* Signal / browser figures: Sankey and treemap SVGs include browser PNG fallbacks;
  the retention plot uses high density PNG. Fonts, labels, colors, and bounds
  are legible. Real-browser regressions verify explicit export dimensions override
  an existing figure layout without mutating it.

Orbit's normalized browser/render mean pixel errors were 1.41%, 2.83%, and
1.24%. They are advisory: native text rasterizes differently, and the native
chart intentionally uses its own minimal style. Images and references are saved.

## Validation

All three decks pass packaged XSD/package checks, canonical save/reopen checks,
explicit-font availability, layout error checks, and every-page LibreOffice
PDF/PNG rendering. Bundles include PPTX, PDF, PNGs, contact sheets, manifests,
references/differences, and local galleries.

* 4,340 pytest tests and 973 acceptance scenarios / 2,914 steps passed.
* Maintained-module Ruff, repository-wide correctness checks, scoped Pyright,
  example Pyflakes, workflow YAML, and all 11 release-gate tests passed.
* The 31-page documentation site builds; the new RST guide parses cleanly.
* Wheel and sdist build. A separately installed wheel, outside the checkout,
  imported hybrid HTML, used packaged XSD/JS, exported browser SVG with correctly
  sized PNG fallback, and successfully ran the installed review CLI.
* Skill mirrors and specification/schema copies match. CI includes hybrid/browser
  and review tests, and retains the new nine-slide gallery alongside the original
  32. The configured remote CI has not been executed from this environment.

The installed batch command also reviewed all 14 feature stress decks / 142
slides. All automated checks pass. Two formerly empty transition-demo pages
now have explanatory labels; their revised renders were inspected. These are
feature probes, rather than design references. Static images do not verify
animations, transitions, video/OLE, or Microsoft PowerPoint playback.

Generated manifests leave visual review pending for downstream reviewers.
This file records the inspection actually performed for this change.
