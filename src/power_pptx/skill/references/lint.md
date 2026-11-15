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

`RaggedEdge` (WARNING) flags a filled rounded-rectangle panel (at least
0.5" tall, so badges and pills are ignored) that ends more than 1.5pt above
the bottom of its own row, with nothing placed in the gap. Its row is the
panels beside it, at most 1" away, whose tops are level with the top of the
stack it ends; each row is judged on its own. `gap_emu` is the shortfall.
Panels nested in another panel are ignored. Native components avoid it with
`Column(fill_last=True)` or `grow`.

Every issue carries a `severity` (`LintSeverity.ERROR` / `WARNING` /
`INFO`), a `code` string, a `message`, and a `shapes` tuple of the
shapes it implicates.

`TextOverflow` lays the text out with the same Pillow font metrics
`fit_text` uses: every run at its effective size and typeface (run, then
paragraph, then the placeholder / master it inherits from), wrapped inside
the frame's margins where `fit_text` breaks lines (at spaces, after hyphens
and dashes, between East Asian characters, at the slashes of a long path)
and stacked at its line and paragraph spacing. Text in
groups and table cells is checked too, and a frame `fit_text` has sized is
never flagged. `issue.ratio` is how many times the frame the text needs,
`issue.dimension` is `"height"` (or `"width"` for a line that cannot wrap),
`issue.overflow_pt` how far it runs past, and `issue.auto_size` the frame's
setting. When a typeface is not installed the engine's fallback metrics are
used — no warning is emitted — and `issue.estimated` is `True`.

Severity follows who can repair the overflow:

- a fixed-size frame (`MSO_AUTO_SIZE.NONE`, or no setting) is an
  **ERROR** — the text spills in every renderer;
- a `SHAPE_TO_FIT_TEXT` frame (what `add_textbox` / `add_text` create), a
  `TEXT_TO_FIT_SHAPE` frame whose stored font scale is not enough, and a
  table row shorter than its text are **WARNING**s — a renderer resizes
  them when the deck is opened or the text edited, so
  `lint_on_save="raise"` does not reject them.

`power-pptx` only writes the auto-size flag, so a `SHAPE_TO_FIT_TEXT`
shape is checked by `OffSlide` and `ShapeCollision` at the size it will
grow to (down from a top anchor, up from a bottom anchor, both ways from
the middle). A box that grows off the slide is an `OffSlide` **ERROR**.

Geometry is what a viewer sees: a rotated shape is checked by the area its
rotated frame covers, and a connector by the line it is drawn along (it
collides with a shape only if the line runs into it). A shape with a
negative width or height is reported as `InvalidGeometry` (ERROR; such a
file needs repair in PowerPoint) and left out of the other checks.

`ZOrderAnomaly` only fires for a fully opaque fill (a translucent scrim
hides nothing), and the declarations below that mark an overlap as
intended — a shared `lint_group`, an allowance, a consistent layer pair —
mark the stacking as intended too.

## Auto-fix

```python
fixes = report.auto_fix()                  # mutates; returns list[str]
preview = report.auto_fix(dry_run=True)    # no mutation; returns list[str]
```

What's currently fixable:

- **`OffSlide`** → moves the shape so the area it covers (rotated, and
  grown to its text) sits inside the slide. A shape larger than the slide
  is shrunk first: a picture or group proportionally, anything else along
  the axis that is too long. Returns a one-line description of each nudge.
- **`TextOverflow`** → makes the text fit, the way the frame's own setting
  asks. The text itself is never changed:
  - no setting, or `TEXT_TO_FIT_SHAPE` → set to `TEXT_TO_FIT_SHAPE` with
    the font scale (and line-spacing reduction) that fits, the values
    PowerPoint stores when it shrinks text itself;
  - `SHAPE_TO_FIT_TEXT` → the shape is resized to its text;
  - `NONE` → the setting is kept and the font sizes are reduced in place,
    as `fit_text` does;
  - a table row → grown to its text.

  Text that would have to shrink below a quarter of its size is left
  alone and stays in the report.
- **`OffGridDrift`** → only with `report.auto_fix(fix_grid_drift=True)`:
  snaps the drifted edge onto the dominant grid line. Off by default
  (as in `tidy()`), because an inferred grid can be wrong. Shapes whose
  right or bottom edge already sits on a grid line — bars on a shared
  baseline — are never flagged.
- **`LayerOrderViolation`** → restacks the shape that declared
  `layer_above` so the drawing order matches what you declared.
  Geometry is untouched.

Reported only, never auto-fixed:

- **`ShapeCollision`** → auto-nudging would almost always break the
  design. Declare the overlap instead — see below.
- **`LowContrast`**, **`MinFontSize`**, **`ZOrderAnomaly`**,
  **`MasterPlaceholderCollision`**, **`RaggedEdge`** → need designer
  judgment.

`slide.tidy()` is the one-call wrapper: it lints, then applies the safe
subset (`fix_offslide`, `fix_overflow`, `fix_layer_order` on by default;
`fix_grid_drift` off).

`slide.lint()`, `audit(prs)` and `audit_accessibility(prs)` never change
the deck. `lint(disable=[...])` and `lint(min_severity=...)` skip the
rules they rule out instead of computing and discarding them, so they
also make linting faster.

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
one from another slide raises `ValueError`. Use `shape.delete()` rather
than removing the element by hand — it purges allowances naming the
deleted shape, which matters because ids get recycled and a stale one
would later match an unrelated shape. Allowances are keyed on
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
detector-specific field (`OffSlide.side`, `TextOverflow.ratio` /
`overflow_pt` / `auto_size`, the `ShapeCollision` scoring, …):

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

Flags: `MissingAltText` (pictures = error, including pictures inserted
into a placeholder; alt text that is only a file name — what
`add_picture` fills in — counts as missing), `LowContrast` (below WCAG AA
4.5:1, judged exactly as the linter judges it), `NoSlideTitle` (no title
landmark for navigation).

## Command line: `power-pptx lint`

Checks saved decks without writing Python — for a CI job that gates
decks another job built. It runs `slide.lint()` on every slide:

```bash
power-pptx lint deck.pptx                         # report grouped by slide
power-pptx lint build/*.pptx --fail-on warning    # stricter gate
power-pptx lint deck.pptx --min-severity warning  # hide info-level issues
power-pptx lint deck.pptx --format json           # one JSON document
power-pptx lint deck.pptx --format sarif > lint.sarif   # code scanning
power-pptx lint deck.pptx --fix --output tidied.pptx    # slide.tidy(), then report
power-pptx lint deck.pptx --fix --in-place        # overwrite (opt-in only)
```

| Exit | Meaning |
|---|---|
| `0` | no issue at or above `--fail-on` |
| `1` | at least one issue at or above `--fail-on` |
| `2` | usage error, or a deck that could not be read or written |

- `--fail-on {error,warning,never}`, default `error`. Info-level
  issues never fail the run. An unreadable deck exits `2` even with
  `never`; the decks that could be read are still reported.
- `--min-severity {info,warning,error}` drops lower issues from the
  report *and* from the exit-status decision.
- `--format json`: `{"decks": [...], "counts", "exit_code", ...}`; each
  slide entry is that slide's `report.to_dict()` plus `index`, `number`,
  `title`, `hidden` (and `fixes` with `--fix`). An unreadable deck is
  `{"path", "error"}`.
- `--format sarif`: the linter's own `lint_report_to_sarif` output, one
  run per deck, each run tagged with the deck's path
  (`automationDetails.id`, `properties.deck`).
- `--fix` applies `slide.tidy()` (and only that — collisions, contrast
  and the like still need you) and needs `--output PATH` or
  `--in-place`; it never overwrites the input otherwise. With several
  decks (or a path ending in `/`, or an existing directory) `--output`
  is a directory. The report and exit status describe what is *left*
  after fixing. `--in-place` rewrites a deck only if a fix changed it.
- Hidden slides are linted too, and marked `(hidden)` in the report.
