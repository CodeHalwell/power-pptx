# Improvement plan

This is a candid, prioritized punch list for `power-pptx`, written
from the perspective of someone who has just used the library — and
the bundled Claude skill — to generate ten Fortune-500-style decks
end-to-end. Items are grouped by severity so you can triage.

The over-arching theme: the library's foundations (linting,
recipes, charts, tables, transitions, theming) are strong. The
remaining weaknesses are concentrated in **animations** (currently
broken in PowerPoint), **color-input ergonomics**, and **a handful
of API asymmetries** that turn into recurring footguns for both
humans and LLM-driven authoring.

Anywhere in this document where I write "the skill," I mean
`.claude/skills/power-pptx/` — the bundled Anthropic Skill that
guides Claude when generating decks.

---

## P0 — broken in the wild, fix or mark experimental

### 1. Animation playback in PowerPoint

The 2.4.0 timing XML round-trips fine, the introspection API reads
back what was written, and LibreOffice converts to PDF cleanly.
But in PowerPoint slideshow mode, animated shapes sit at 10–15%
opacity for several seconds and then snap to fully visible all at
once. This was reported with a diagnostic deck that ruled out the
missing `<p:cTn nodeType="mainSeq">` wrapper; the cause is
elsewhere.

**Confirmed at-deck level**: a `.pptx` containing entrance
animations on a slide that also has a Morph transition can
trigger PowerPoint's "Repair?" dialog on open
(`10_marketing_campaign.pptx` in the example suite reproduced
this). The example decks in `examples/real_world/` have had all
`Entrance.*` calls stripped as a workaround.

**Action plan**:

1. **Get a known-good reference.** Author the simplest possible
   auto-playing fade sequence in PowerPoint by hand (one slide,
   two shapes, both fade in on slide entry). Save it.
2. **Diff the timing XML** against `power-pptx`'s output for the
   equivalent effect. The structural delta is the bug.
3. Likely candidates worth checking:
   - Missing `<p:bldLst>` sibling to `<p:tnLst>` under
     `CT_SlideTiming`. Real PowerPoint output may always include
     the build list.
   - Missing `<p:nextCondLst>` / `<p:prevCondLst>` on click-step
     `<p:cTn>` elements. Their absence may stop the timeline
     advancing past step 1.
   - `nodeType` being on the inner `<p:cTn>` rather than the
     outer wrapper — making each top-level `<p:par>` a
     `clickEffect` / `afterEffect` in its own right.
4. **Fixture-based regression test.** Once the structural fix
   is in, freeze the timing XML for a canonical 3-effect fade
   sequence as a test fixture. Any future change that diverges
   from the fixture either updates it intentionally or fails CI.
5. **Until fixed**: mark `power_pptx.animation` as experimental
   in its module docstring, in `references/animations.md`, and
   on the public docs page. Currently a user has no signal that
   the output won't play.

---

## P1 — silent footguns

### 2. `set_transition` should not clobber per-slide overrides

Calling `prs.set_transition(kind=...)` after a per-slide
`slide.transition.kind = MSO_TRANSITION_TYPE.MORPH` overwrites
the per-slide value silently. The reference doc warns about it
in prose but the API itself invites the mistake.

**Action**: change `set_transition` to skip slides that already
have an explicit kind set, with a `force=True` opt-in to
overwrite. Or: emit a `UserWarning` on overwrite. Update the
skill's `references/transitions.md` to lead with the new
default.

### 3. `apply_quick_layout` enum-vs-string mismatch

`references/charts.md` shows `"legend_position": "bottom"` as a
string, but the implementation requires
`XL_LEGEND_POSITION.RIGHT` and crashes on the string form
(`ValueError: 'right' is not a valid XL_LEGEND_POSITION`).

**Action**: accept the lowercase string at the boundary,
mapped to the enum internally. Keep the enum form working too.
Update the skill so generated code uses whichever form is
canonical.

### 4. `auto_fix()` should handle TextOverflow

This is the most common runtime issue when generating decks
from dynamic input — and the linter detects it but won't act
on it. `report.auto_fix()` only handles `OffSlide`.

**Action**: add a tier that bumps `auto_size =
TEXT_TO_FIT_SHAPE` (or shrinks via
`TextFitter.best_fit_font_size`) for overflowing frames. This
is the single biggest improvement to the lint-or-die pattern,
and the one most directly relevant to runtime-supplied text.
Update the skill to lean on it explicitly.

---

## P2 — API ergonomics

### 5. Canonical color coercion at every public boundary

Right now:

| Surface                                     | Accepts                                  |
|---------------------------------------------|------------------------------------------|
| `tokens.palette["primary"]`                 | returns `RGBColor`                       |
| `chart.apply_palette([...])`                | hex strings, `RGBColor`, tuples          |
| `shape.fill.fore_color.rgb = ...`           | `RGBColor` only                          |
| `fill.linear_gradient("#ABC", "#DEF")`      | hex strings                              |
| `RGBColor.from_string("ABC")`               | raw 6-digit hex (no `#`)                 |
| `RGBColor.from_hex("#ABC")`                 | hex with or without `#`                  |

Every example deck I wrote needed a `hex_rgb` shim that handled
both. This is a category of bug, not a one-off.

**Action**: introduce `power_pptx._color._coerce(value) ->
RGBColor` that accepts hex (with or without `#`), `RGBColor`,
3-tuple. Route every public color-accepting setter through it,
so `shape.fill.fore_color.rgb = "#06D6FE"` works the same as
`= RGBColor(...)`. Document the supported "color-like" types in
one place. `RGBColor.from_string` should emit
`DeprecationWarning` (already in the docstring, but only as
prose).

### 6. `gradient()` and `linear_gradient()` parameter parity

`linear_gradient("#A", "#B", angle=90)` works.
`gradient(kind="linear", angle=90)` doesn't — `gradient()`
takes no `angle` and you have to set `gradient_angle`
afterward.

**Action**: add `angle=` to `gradient()` for symmetry. Both
should accept the same color-like inputs (see #5).

### 7. `chart.shape` accessor

Today, animating or measuring the chart's parent shape
requires keeping the `add_chart` return value separately,
because `chart.element.getparent().getparent()` is
`None` / awkward.

**Action**: expose `chart.shape` (or `chart.parent_shape`).
This also removes a class of LLM-generated bug — the skill
currently teaches `slide.shapes.add_chart(...).chart`, which
loses the shape ref.

### 8. `text_frame.set_paragraph_defaults(...)`

Every paragraph in a card body needs `font.name`,
`font.size`, `font.color.rgb` set explicitly. There's no
"set the default for all paragraphs in this text frame."
Branded decks repeat the same six lines per paragraph
hundreds of times — the single most tedious thing about
generating styled content.

**Action**: add
`text_frame.set_paragraph_defaults(font=Font(...),
color=..., size=...)` that fills any unspecified per-run
properties at save time. Leaves explicit overrides
untouched.

### 9. Recipe-returned slide should expose anchors

Recipes use the Blank layout, so `slide.shapes.title is
None`, and you must address shapes by index to add a footer
or page number on top of a `kpi_slide`.

**Action**: have recipes return a thin slide wrapper that
exposes named anchors: `slide.title_shape`,
`slide.body_zone`, `slide.footer_zone`. Recipes compose
cleanly with custom add-ons; the skill's recipe section can
drop the "address shapes by index" caveat.

---

## P3 — linter quality of life

### 10. `OffGridDrift` default tolerance

`Inches(0.6)` divider vs `Inches(0.62)` eyebrow lights up a
warning on basically every section header. Raise default
tolerance to ~0.05" or only flag when ≥2 shapes share the
same near-miss.

### 11. `TextOverflow` heuristic on small badges

A 1.3"×0.32" "MOST POPULAR" pill at 9pt got flagged as 1.5×
overflow when it visually fits. Special-case short
single-line strings (≤ ~20 chars) — the 0.55×pt char-width
approximation is too conservative there.

### 12. `ShapeCollision` for designed-overlap groups

Cards-with-color-bands, badges-over-cards,
eyebrow-over-rectangle headers all surface as collisions.
`shape.lint_group` works but is tedious.

**Action**: add slide-level
`slide.lint_group_overlaps([s1, s2, ...])` or auto-suppress
when the smaller shape is fully contained inside the larger
AND has a higher z-order (a layered-design pattern).

---

## P4 — docs, skill, and infrastructure

### 13. Add a "common pitfalls" page

Cover the issues above (color coercion, transition
ordering, recipe → blank layout, `chart.element` is `None`,
animation experimental status). Most of these landed
example-deck authors in the source code, not the docs.

### 14. Update the bundled skill

The skill (`.claude/skills/power-pptx/`) is the most
direct lever for improving AI-driven authoring. Specific
edits:

- **`SKILL.md`** — add a `## House rules` entry: "Do not
  generate `power_pptx.animation` calls until the playback
  bug is resolved. Use slide transitions instead — those
  round-trip and play correctly."
- **`references/animations.md`** — top of file: a
  big yellow "Experimental" callout linking to the bug
  report. Until fixed, examples should be marked "may not
  play in PowerPoint."
- **`references/charts.md`** — fix the legend-position
  example to use `XL_LEGEND_POSITION.RIGHT`, and add a
  note that the dict accepts the enum (until #3 is shipped).
- **`references/transitions.md`** — promote the
  "Correct order" warning from a prose paragraph to a
  callout at the top, with a code example showing
  set_transition followed by per-slide override.
- **Common pitfalls section in `SKILL.md`** — add:
  - "Use `RGBColor.from_hex(value)`, not
    `from_string(value)`. The latter does not strip `#` and
    is slated for removal in a future major release."
  - "Cards holding more than ~5 lines of body text should
    set `text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE`
    immediately after writing the text. The lint heuristic
    is conservative and will otherwise raise."
  - "When you need to animate or measure a chart's parent
    shape, keep the `slide.shapes.add_chart(...)` return
    value, not just `.chart`."
  - "Pricing-card / badge text in shapes ≤ 0.5" tall must
    set `auto_size = TEXT_TO_FIT_SHAPE` to avoid the
    `TextOverflow` lint."
- **Add a `references/real-world-decks.md`** — a short
  "what good looks like" reference pointing at
  `examples/real_world/`, summarising the patterns each
  deck demonstrates (cover, KPI dashboard, table with
  conditional fills, multi-stage timeline, etc.).

### 15. Mark deprecations more loudly

`RGBColor.from_string`'s docstring still references a
removal target ("removed in 2.0") that the project has
already passed (currently at 2.4.0), and the function is
the path most snippets reach for. Two fixes ship together:

1. Update the docstring to reference a future major release
   (or drop the specific version), so it stops misleading
   readers.
2. Add a `DeprecationWarning` on call so users get a runtime
   nudge, not just a docstring.

### 16. CI hygiene for `examples/`

- Run `pyflakes` (or `ruff check --select F`) over
  `examples/` in CI. The PR #25 review caught seven unused
  imports across the new examples that all three review
  bots flagged sequentially — automation would have
  fixed them at PR-open time.
- Run `examples/real_world/build_all.py` in CI. Those
  decks are already a strong combined smoke test for the
  design / charts / lint paths and a green build is a
  public signal the surface didn't regress.

### 17. `chart.shape`-style "look here for the Pythonic ref" annotations

Several of the issues above (chart shape, recipe
anchors, color coercion) trace back to a public surface
that doesn't make the right path obvious. As fixes ship,
update the corresponding `references/*.md` so the
*shortest* idiomatic snippet is the *first* one.
LLM-generated code reproduces whatever shows up first
in the docs.

---

## Suggested release plan

| Release | Scope                                                                                       |
|---------|---------------------------------------------------------------------------------------------|
| 2.4.1   | P0 — animations playback fix or "experimental" docs flag. CI: pyflakes on examples/.        |
| 2.5.0   | P1 (set_transition, apply_quick_layout, auto_fix overflow). Skill updates from #14.         |
| 2.6.0   | P2 (color coercion, gradient parity, chart.shape, paragraph defaults, recipe anchors).      |
| 2.7.0   | P3 lint tuning + #15 deprecation warnings + common-pitfalls page + real-world skill ref.    |

If only one of these can ship in the next release, it should be
**P0**. Animations being broken in the most common target
environment is a feature-shaped trap.

If only one ergonomic fix can ship next to that, it should be
**#5 (color coercion)**. It removes the largest category of
silent bug from both human and LLM authoring, and unblocks
half of the smaller items.
