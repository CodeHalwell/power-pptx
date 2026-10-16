# Visual review — 16 October 2026

Reviewed by the code agent using rendered PNGs. Eight modern decks / 32 slides
were inspected in contact sheets, with full-size inspection of dense charts,
code, tables, large headlines, and revised pages. Output came from saved PPTX
files rendered through LibreOffice → PDF → Poppler at 96 DPI. HTML sources were
captured with Chromium at 2× density. This is a dated review of these sources,
not an automatic appearance approval for future builds.

| Deck | Slides inspected | Findings and final disposition |
| --- | --- | --- |
| Forma | 1–4 | Fixed the cover's accidental third headline line and collision with body copy. Removed inherited card shadows where a flat treatment was intended. Dashboard, workflow, and pricing table read cleanly. |
| Relay | 1–4 | Shortened the code-side explanation to keep its intended line rhythm. Checked dark chart axes/legend, code spacing, routed arrows, and status/progress components. |
| Fieldwork | 1–4 | Checked serif display type, line-art SVG fallback, quote rhythm, and timeline alignment. Darkened the orange numerals for contrast. |
| Lumen | 1–4 | Fixed cover wrapping; shortened long headings. Checked the vector confidence band and axis labels, native annotations, transparent browser panel, and imported slide. |
| Current | 1–4 | Used self-contained Plotly HTML capture when Kaleido's file URL was blocked by this environment. Shortened the revenue headline and darkened colored labels. Checked cash-flow labels, native doughnut, and merged table. |
| Aster | 1–4 | Kept the gradient decoration inside the section bounds; added breathing room beside the headline. Checked glass, gradient text, network diagram, and lower card copy. |
| Daily | 1–4 | Fixed duplicate inline SVG gradient IDs so the second bottle keeps its peach color. Checked intentional packshot cropping, rotated assets, storefront, and launch cards. |
| Offgrid | 1–4 | Checked oversized type, agenda rows, clipped card corners, SVG star, and fully drawn procedural canvas. No accidental clipping found. |

All eight decks pass schema validation, canonical package round-trip, reopen,
lint, image checks, and complete 4-page rendering. Final gallery lint has no
errors or warnings. DejaVu font availability remains an explicit prerequisite
for the editable decks. Captured HTML is static imagery; its visible text is
preserved in notes and alt text rather than native editable text.

For all 12 fully captured slides, normalized mean absolute channel differences
between browser reference and saved-PPTX rendering are approximately 0.2–0.6%,
below the builder's 1.5% threshold. This measures capture/render fidelity, not
aesthetic quality.

## Broader feature review

All 14 existing stress decks / 142 slides built, validated, round-tripped,
reopened, and rendered. All pages were inspected in contact sheets. The changed
hub diagrams and corrected pie labels were re-rendered and inspected separately.
They exercise effects, gradients, patterns, chart types/layouts, tables/merges,
diagrams, themes, transitions, 3D, picture filters, SVG, multilingual text,
freeform shapes, groups, media markup, and cross-deck composition.

This review found and repaired two library issues:

- Hub-and-spoke diagrams packed nodes into the hub and routed diagonal
  connectors through rectangular edges. Nodes now use the outer region with
  visible gaps and connectors follow circular radii. Regression coverage checks
  containment and separation for 1–24 spokes, radial connectors, and invalid
  sizes before mutation.
- Contrast lint compared transparent text boxes straight through dark cards
  to the slide background. It now respects containing cards and paint order,
  and skips unresolved backgrounds. Six regressions cover contrasting labels,
  gradients, transparency, partial overlap, pictures, and read-only inspection.

The stress suite's pie example also now uses actual percentage labels, so
values such as 30 display as 30%, rather than 3000%.

The broad fixtures include deliberately tiny/off-canvas content, legacy styling,
and font fallback probes. Some circular labels wrap awkwardly where their
requested Inter font is unavailable. LibreOffice renders several 3D/effect
variants similarly; static pages do not verify animation, transition, video,
OLE, or Microsoft PowerPoint playback. Those probes remain QA material; the
eight modern decks above are the presentation design references.

## Validation

- 4,286 pytest tests passed; 973 acceptance scenarios / 2,914 steps passed.
- Repository-wide Ruff correctness checks, maintained-module/gallery Ruff,
  example Pyflakes, scoped Pyright, and all 11 release-gate tests passed.
- Both skill mirrors match. Workflow YAML parses and `git diff --check` is clean.
- Wheel/sdist build and metadata checks pass; the bundled skill includes both
  modern design and content embedding guidance.
- A new CI job builds and renders the modern gallery and uploads its previews
  for review. That remote workflow has been configured, not executed here.
