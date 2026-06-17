# Native-shape diagrams

`power_pptx.diagrams` builds common process/relationship diagrams out of
**native PowerPoint shapes** (no images, no SmartArt) so they render
identically in PowerPoint, Keynote, and LibreOffice and stay fully editable.
Each recipe takes a `slide`, a `BBox` to live inside, and a small content spec;
it handles equal-column widths, mid-edge arrow routing, and inset padding so
you only specify the semantics.

Every recipe is **space-aware**: labels are fitted with `fit_text` so a long
word never clips its card or circle — the same guarantee the rest of the
library makes. Each returns a small dataclass exposing the shapes it built so
you can tweak individual elements afterwards.

```python
from power_pptx import Presentation, BBox
from power_pptx.diagrams import horizontal_pipeline

prs = Presentation()
s = prs.slides.add_slide(prs.slide_layouts[6])

result = horizontal_pipeline(
    s,
    BBox.from_inches(0.5, 2.5, 12.3, 1.6),   # left, top, width, height (inches)
    steps=["Extract", "Classify", "Enrich", "Output"],
    accent="#0B5CFF",
)
# result.cards -> list[Shape], result.arrows -> list[Connector]
```

`BBox.from_inches(left, top, width, height)` is the usual way to place a
diagram; `BBox(left, top, width, height)` takes EMU.

## Pipelines

`horizontal_pipeline` and `vertical_pipeline` lay N steps in a row / column with
arrows between them.

```python
from power_pptx.diagrams import horizontal_pipeline, vertical_pipeline

horizontal_pipeline(s, bbox, steps=["A", "B", "C"], accent="#0B5CFF")
vertical_pipeline(s, bbox, steps=["A", "B", "C"])
```

`steps` items may be plain strings or dicts for per-step overrides:

```python
steps=[
    {"label": "Extract", "sublabel": "S3 → queue", "fill": "#101826", "text_color": "#E6EDF3"},
    "Classify",
]
```

Key kwargs (both pipelines): `fill`, `text_color`, `font`, `size_pt`,
`bold_labels`, `card_line`, `card_radius`, `accent`, `arrow_head`
(`"triangle"`, `"arrow"`, `"stealth"`, `"diamond"`, `"oval"`, or `"none"`),
`arrow_inset_pt`, `gap`. Returns `PipelineResult(cards, arrows)`.

## Hub and spoke

```python
from power_pptx.diagrams import hub_and_spoke

hub_and_spoke(
    s, BBox.from_inches(3, 1.5, 7, 5),
    centre="Platform",
    spokes=["Ingest", "Model", "Serve", "Observe"],
    accent="#0B5CFF",
    hub_fill="#0B5CFF", hub_text_color="#FFFFFF",
)
```

`spokes` accept the same string-or-dict form as `steps`. Other kwargs:
`fill`, `text_color`, `font`, `size_pt`, `hub_size` / `spoke_size` (relative
circle scale). Returns `HubAndSpokeResult(hub, spokes, arrows)`.

## Cycle

N cards in a circle with arrows `i → i+1`, last looping back to close the cycle.

```python
from power_pptx.diagrams import cycle

cycle(s, BBox.from_inches(3, 2, 7, 4.5),
      steps=["Plan", "Build", "Measure", "Learn"])
```

Returns `CycleResult(cards, arrows)`. Best with 3–8 steps.

## Decision tree

A root question with branch outcomes underneath; each branch may carry one level
of `children` (leaves).

```python
from power_pptx.diagrams import decision_tree

decision_tree(
    s, BBox.from_inches(0.9, 1.5, 11.5, 5.0),
    root="Request",
    branches=[
        {"label": "Cache hit",  "children": ["Return"]},
        {"label": "Cache miss", "children": ["Compute", "Store"]},
        "Reject",                      # a bare string is a childless branch
    ],
    fill="#141A23", text_color="#E6EDF3",     # branch + leaf colours
    root_fill="#5B9CFF", root_text_color="#0B0E14",
)
```

By default leaves **inherit** `fill` / `text_color` from the recipe (so a dark
deck with light text stays legible). Pass `leaf_fill` / `leaf_text_color` only
when you want the leaves styled differently from their branches:

```python
decision_tree(s, bbox, root="…", branches=[…],
              fill="#141A23", text_color="#E6EDF3",
              leaf_fill="#1E2A38", leaf_text_color="#FFD166")
```

Returns `DecisionTreeResult(root, branches, arrows)` (`branches` includes both
branch and leaf cards).

## Comparison columns

N side-by-side columns, each a header card over a body card.

```python
from power_pptx.diagrams import comparison_columns

comparison_columns(
    s, BBox.from_inches(0.5, 2, 12.3, 4.5),
    columns=[
        {"title": "Plan A", "body": ["Fast", "Cheap", "Scales to many regions"]},
        {"title": "Plan B", "body": "Single-region, lower latency"},
    ],
    header_fill="#0B5CFF", header_text_color="#FFFFFF",
)
```

`body` may be a string or a list of strings (joined with newlines). Returns
`ColumnsResult(columns, headers)`.

## Lint grouping

Diagram arrows intentionally overlap their target cards. The recipes tag each
diagram as one `lint_group` so `slide.lint()` / `audit()` don't flag the
overlaps — you get a clean lint report without suppressing real issues.
