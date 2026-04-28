# Layout linter (Phase 2)

Programmatic decks tend to ship the same handful of bugs over and
over: text spilling out of its container, shapes off-slide, layered
elements that aren't intended overlaps. The linter is built for
exactly that use case — it's especially useful when feeding decks
generated from LLM output or arbitrary user input.

## Run on a slide

```python
report = slide.lint()
report.issues          # list[LintIssue]
report.has_errors      # bool
print(report.summary())
```

For a whole deck, iterate the slides yourself:

```python
all_issues = []
for slide in prs.slides:
    all_issues.extend(slide.lint().issues)
```

`from_spec` (see `compose.md`) accepts a deck-level
``"lint": "warn" | "raise"`` field that walks every slide for you.

## Issue types

```python
from pptx.lint import TextOverflow, OffSlide, ShapeCollision

for issue in report.issues:
    if isinstance(issue, TextOverflow):
        print("overflow", issue.shapes[0].name, "ratio", issue.ratio)
    elif isinstance(issue, OffSlide):
        print("off-slide", issue.shapes[0].name, "side", issue.side)
    elif isinstance(issue, ShapeCollision):
        a, b = issue.shapes
        print("collision", a.name, b.name,
              "intersection_pct", issue.intersection_pct)
```

Every issue carries a `severity` (`LintSeverity.ERROR` / `WARNING` /
`INFO`), a `code` string, a `message`, and a `shapes` tuple of the
shapes it implicates.

`TextOverflow` uses Pillow font metrics and respects margins, vertical
anchor, line spacing, and `auto_size`.

## Auto-fix

```python
fixes = report.auto_fix()                  # mutates; returns list[str]
preview = report.auto_fix(dry_run=True)    # no mutation; returns list[str]
```

What's currently fixable:

- **`OffSlide`** → translates the shape so it sits inside the slide
  bounds. Returns a one-line description of each nudge.
- **`TextOverflow`** → reported only. Auto-fitting requires designer
  judgment on font size vs content; do it manually with
  ``text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE``.
- **`ShapeCollision`** → reported only. Auto-nudging would almost
  always break the design.

## Save-time hooks (via `from_spec`)

If you build the deck through `pptx.compose.from_spec`, the spec dict
accepts a top-level ``"lint"`` field:

```python
from pptx.compose import from_spec

prs = from_spec({
    "slides": [...],
    "lint": "raise",          # also "warn" or "off" (default)
})
```

`"warn"` logs every issue through stdlib `logging`; `"raise"` raises
`pptx.exc.LintError` if any error-severity issue is found.

## Recommended pattern for generators

```python
from pptx.exc import LintError

prs = build_deck_from_user_input(...)

# 1. Auto-fix what we can, slide by slide
for slide in prs.slides:
    report = slide.lint()
    report.auto_fix()

# 2. Re-run and bail on any remaining errors
remaining = []
for slide in prs.slides:
    remaining.extend(i for i in slide.lint().issues
                     if getattr(i, "severity", None) == "error")
if remaining:
    raise LintError("; ".join(str(i) for i in remaining))

prs.save("out.pptx")
```
