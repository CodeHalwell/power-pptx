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
from power_pptx.lint import TextOverflow, OffSlide, ShapeCollision

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

`LayerOrderViolation` carries the declared `layer` name, and its
`shapes` tuple is `(declaring_shape, layer_shape)`.

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
  bounds (shrinking it first if it is larger than the slide). Returns a
  one-line description of each nudge.
- **`TextOverflow`** → flips the frame to
  `MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE` so PowerPoint shrinks the runs at
  render time. Non-destructive: the text is preserved verbatim.
- **`OffGridDrift`** → snaps the drifted edge onto the dominant grid
  line.
- **`LayerOrderViolation`** → restacks the shape that declared
  `layer_above` so the drawing order matches what you declared.
  Geometry is untouched.

Reported only, never auto-fixed:

- **`ShapeCollision`** → auto-nudging would almost always break the
  design. Declare the overlap instead — see below.
- **`LowContrast`**, **`MinFontSize`**, **`ZOrderAnomaly`**,
  **`MasterPlaceholderCollision`** → need designer judgment.

`slide.tidy()` is the one-call wrapper: it lints, then applies the safe
subset (`fix_offslide`, `fix_overflow`, `fix_layer_order` on by default;
`fix_grid_drift` off).

## Declaring an overlap is intentional

`ShapeCollision` is the noisiest rule, because deliberate layering —
a badge on a card, an accent bar on a panel — looks identical to a
copy-paste bug from a bounding box alone. Tell the linter what you
meant and it stops guessing. Three ways, narrowest last:

```python
# 1. Group tag — n-ary and symmetric. Everything sharing a non-empty
#    tag may overlap everything else in the tag.
card.lint_group = "kpi-1"
accent.lint_group = "kpi-1"
slide.lint_group("kpi-1", card, accent, label)     # batch form
slide.lint_group_overlaps(card, accent, label)     # auto-names the group

# 2. Pairwise allowance — licenses exactly one pair, nothing else.
badge.allow_overlap_with(card)
badge.disallow_overlap_with(card)                  # revoke
badge.overlap_allowances                           # frozenset[int] of shape ids

# 3. Layer hints — the only form that also asserts z-order.
card.layer = "card"
badge.layer_above = "card"
```

Use a **group** when several shapes form one visual cluster; a
**pairwise allowance** when only one specific overlap is meant to be
legal and you want the rest still policed; **layer hints** when the
stacking order itself matters.

An allowance may only name a shape on the **same slide**, and passing
one from another slide raises `ValueError`. Allowances are keyed on
`cNvPr/@id`, which is unique per slide but repeats across a deck — so a
borrowed id would either read as a bogus self-reference or silently
match an unrelated shape here and suppress a collision that was real.

Layer hints are the only one that can *fail*. Declaring
`layer_above = "card"` asserts this shape is painted on top of every
overlapping shape whose `layer` is `"card"`. If the shape tree says
otherwise — the shape claiming to be on top comes earlier in `spTree`
and is drawn underneath — you get a `LayerOrderViolation` (severity
ERROR), because the declaration records what you meant and the drawing
order is what failed to deliver it:

```python
report = slide.lint()
report.auto_fix()          # restacks it for you; geometry untouched
```

A shape name with a dotted prefix is grouped implicitly, so naming
shapes `"card.bg"` / `"card.title"` groups them under `"card"` with no
extra calls. Set `shape.lint_group = ""` to opt a dotted name out.

All of it lives in the shape's `cNvPr/extLst`, the OOXML-sanctioned
extension point, so it survives save/open and PowerPoint leaves it
alone. Related but different: `shape.lint_skip = {"MinFontSize"}`
silences a rule on a shape rather than declaring intent.

## Machine-readable output (for agents / CI)

`summary()` is for humans; `to_dict()` / `to_json()` are for code. Use
them to feed lint results back into an LLM auto-fix loop or a CI gate
instead of regex-parsing the summary string.

```python
report = slide.lint()
report.to_dict()    # {"has_errors", "issue_count", "issues": [...]}
report.to_json()    # same, as a JSON string (indent=2 default)
```

Each issue is self-describing — it carries `code`, `severity`,
`message`, the names of the `shapes` involved, and every
detector-specific field (`OffSlide.side`, `TextOverflow.ratio`, the
`ShapeCollision` scoring, …):

```json
{"code": "OffSlide", "severity": "error",
 "message": "Shape 'Rectangle 1' extends beyond the right edge of the slide.",
 "shapes": ["Rectangle 1"], "side": "right"}
```

The whole-deck `audit()` report has the same pair:

```python
from power_pptx import audit

data = audit(prs).to_dict()   # adds a "slide" index to every lint issue
if data["has_errors"]:
    ...                        # hand `data` straight to the model to fix
```

## Save-time hooks (via `from_spec`)

If you build the deck through `power_pptx.compose.from_spec`, the spec dict
accepts a top-level ``"lint"`` field:

```python
from power_pptx.compose import from_spec

prs = from_spec({
    "slides": [...],
    "lint": "raise",          # also "warn" or "off" (default)
})
```

`"warn"` logs every issue through stdlib `logging`; `"raise"` raises
`power_pptx.exc.LintError` if any error-severity issue is found.

## Save-time hooks (any presentation)

Every `Presentation` has a `lint_on_save` switch, whatever built it:

```python
prs = power_pptx.Presentation("deck.pptx")
prs.lint_on_save = "off"      # default — no checks, no cost
prs.lint_on_save = "warn"     # log error-severity issues, still write the file
prs.lint_on_save = "raise"    # raise LintError instead of writing the file

prs.save("out.pptx")
```

Only **error**-severity issues count; warnings and info never trigger it.
The lint pass runs *before* anything is written, so `"raise"` never leaves a
bad file on disk. `"warn"` logs on the `power_pptx.presentation` logger. The
setting lives on the in-memory object only — re-open the saved file and it is
back to `"off"`.

## Recommended pattern for generators

```python
from power_pptx.exc import LintError

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

## CI loop: SARIF export + baseline diff

`summary()` is for humans; SARIF and diff are for CI.

```python
report = slide.lint()
report.to_sarif(slide_index=0)        # SARIF v2.1.0 dict (GitHub code-scanning)
report.to_sarif_json()                # JSON string

from power_pptx.lint import lint_report_to_sarif
sarif = lint_report_to_sarif([s.lint() for s in prs.slides])   # whole deck

report.fingerprints()                 # list[str] -- the stable ids diff() uses
new_issues = current.diff(baseline)   # only issues NOT in baseline
both = current.diff_detail(baseline)  # {"added": [...], "fixed": [...]}
```

Severities map ERROR→error, WARNING→warning, INFO→note. A
moved-but-still-broken shape keeps its fingerprint, so `diff()` won't
flag it as new.

## Accessibility

```python
picture.alt_text = "Bar chart of Q3 revenue by region."   # -> <p:cNvPr descr=...>
picture.title_text = "Q3 revenue"                          # -> <p:cNvPr title=...>

from power_pptx import accessibility
report = accessibility.audit_accessibility(prs)            # read-only
if report.has_errors:                  # picture with no alt text = error
    print(report.markdown())
report.to_dict()                       # JSON-serializable for a CI gate / LLM loop
```

Flags: `MissingAltText` (pictures = error), `LowContrast` (below WCAG AA
4.5:1), `NoSlideTitle` (no title landmark for navigation).
