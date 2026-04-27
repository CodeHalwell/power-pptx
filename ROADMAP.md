# python-pptx-next Roadmap

This roadmap describes the planned evolution of `python-pptx-next` from
its 1.0.2 fork point through a hypothetical 2.0. It is a living document:
priorities are listed in order, but ship dates are deliberately not given
because each milestone is gated on the previous one and on community
feedback.

## North star

**Make it possible to generate genuinely beautiful PowerPoint
presentations from Python — animations, transitions, modern visual
effects, real theme support — without leaving the library and without
sacrificing the round-trip fidelity that makes `python-pptx` valuable
today.**

The OOXML element tree already supports almost everything modern users
want (effects, transitions, animations, themes); the work is to grow the
public API up to meet it, then layer a thin "design system" on top so the
*default* output looks good.

## Guiding principles

1. **Drop-in compatibility within 1.x.** `import pptx` keeps working.
   Existing scripts produce byte-identical or visually-identical output.
   Breaking changes are batched and held for a clearly-flagged 2.0.
2. **OOXML faithful by default.** Every new feature maps to a real
   element in the schema; we do not invent semantics PowerPoint won't
   render.
3. **Round-trip safety is a release blocker.** A deck authored in
   PowerPoint, opened, mutated, and saved must not lose data. Every new
   feature ships with a round-trip regression test.
4. **High-level helpers are additive.** They sit on top of the low-level
   API; they never replace it.
5. **No corporate dependencies.** Pure Python on top of `lxml`, `Pillow`,
   `XlsxWriter`. No hosted services, no telemetry, no auth.
6. **Read should never mutate.** Getter properties are idempotent. Where
   the upstream library got this wrong, we fix it (with deprecation
   warnings where behavior actually changes).

## Versioning

| Range | Meaning |
|---|---|
| `1.1.x` | First active-fork release. Bug fixes only. No new API. |
| `1.2.x` – `1.9.x` | New features, additive only. No removals. |
| `2.0.0` | Breaking changes, deprecation removals, API cleanups. |

Pre-release builds use `.devN`/`.aN`/`.bN` suffixes and publish to PyPI
under the same distribution name.

## Out of scope

These items have been considered and explicitly deferred or rejected, so
contributors don't burn time prototyping them:

- **Full SmartArt creation.** The layout algorithms are proprietary and
  non-trivial to reverse-engineer. We *will* support text substitution
  inside an existing template's SmartArt (see Phase 7).
- **A separate pure-Python distribution (`python-pptx-mini`).** `lxml`
  is reliably available on every modern serverless runtime via manylinux
  wheels; the maintenance cost of a parallel distribution is not
  justified.
- **A pixel-accurate rendering engine.** The text-fit estimator (Phase 5)
  uses Pillow font metrics for "good enough" auto-fit; we do not aim to
  replicate PowerPoint's renderer.
- **Live integration with the PowerPoint application** (COM, AppleScript,
  Office.js). This library manipulates files on disk; it does not drive
  a running PowerPoint instance.
- **`.ppt` (legacy binary format) support.** Out of scope, same as
  upstream.

---

## Phase 1 — Hygiene and bug fixes (target: 1.1.0)  *— SHIPPED*

No new public API. Cleans up known issues that would otherwise compound
as we add features on top.

- [x] **Non-mutating color getters.** `Font.color` (`text/text.py:305-310`)
  and `LineFormat.color` (`dml/line.py:21-33`) currently call
  `self.fill.solid()` on read, silently severing theme inheritance. Fix
  by adding a non-mutating read path that returns the inherited color
  when no explicit fill is set, and only mutating on assignment. Add a
  deprecation note for the old behavior in the docstring.
- [x] **`max_shape_id` caching at the element level.** `CT_GroupShape`
  (`oxml/shapes/groupshape.py:150-163`) does an `xpath('//@id')` scan on
  every shape add, giving O(N²) over a slide. Cache the max at the
  group-shape level and invalidate on child mutation. Default fast path,
  no `turbo_add_enabled` collision risk. Keep `turbo_add_enabled` as a
  deprecated no-op for one minor version.
- [x] **`PERCENT_40` typo fix** (`enum/dml.py:253`). Currently spelled
  `ERCENT_40`. Add `PERCENT_40` as the canonical name and keep
  `ERCENT_40` as a back-compat alias with a `DeprecationWarning`.
- [x] **Drop Python 3.8.** EOL October 2024. Require 3.9+; bump
  `requires-python` and `pyright`'s `pythonVersion` accordingly.
- [x] **CI on GitHub Actions.** Replace dead `.travis.yml` with a workflow
  matrix across the supported Python versions.
- [x] **Issues & governance.** `GOVERNANCE.md`, `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, an issue-template, a PR-template.
- [x] **Round-trip test harness.** Generate a deck → open in `python-pptx`
  → save → diff XML. Used by every later phase.

**Done when:** all 1.0.2 user code runs unchanged, the regression
harness is green, and the CI matrix passes on 3.9–3.13.

## Phase 2 — Layout integrity and JSON authoring (target: 1.2.0)

The first thing people notice about an auto-generated deck is bad
geometry: shapes overlap when they shouldn't, text spills out of its
container, things sit slightly off the slide. This phase makes "the
deck physically lays out correctly" a property the library can detect
and (where safe) repair, and exposes a JSON entry point so LLM-driven
generators can route straight into the linter without rewriting
boilerplate.

### [x] Linter

A read-only inspector that reports geometric and typographic issues on
a slide or whole deck.

```python
report = slide.lint()                  # SlideLintReport
report.issues                          # list[LintIssue]
report.has_errors                      # bool
report.summary()                       # human-readable string

deck_report = prs.lint()               # DeckLintReport, slide-by-slide
```

Initial issue types:

- `TextOverflow(shape, ratio)` — measured text extent exceeds the
  text-frame extent. Uses Pillow `ImageDraw.textbbox` with the run's
  font metrics; respects margins, vertical anchor, line spacing, and
  `auto_size`. Builds on the existing `TextFitter` in `text/layout.py`.
- `ShapeCollision(a, b, intersection_area, intersection_pct)` — two
  shapes' bounding boxes overlap and the overlap is not declared
  intentional (see relationship model below).
- `OffSlide(shape, side)` — shape is wholly or partly outside the slide
  bounds.
- `TextTooSmall(shape, point_size)` — body text below a configurable
  minimum (default 9pt; warning, not error).
- (stretch) `LowContrast(shape, ratio)` — text-on-fill contrast below
  WCAG 2.1 AA. Requires resolving theme colors, so depends on the
  Phase 5 theme reader; ships in 1.5.x or later.

### Relationship model — declaring intentional overlaps

Without intent markers, every shadow, badge, and layered card trips
the collision detector. Three escape hatches:

1. **Group-implicit.** Shapes inside the same `<p:grpSp>` are treated
   as cooperating. Putting a badge and its underlying card in a group
   silences collisions between them.
2. **Explicit pairwise.** `shape_a.allow_overlap_with(shape_b)`. Stored
   on the shape's `<a:extLst>` under a private namespace
   (`urn:python-pptx-next:lint`) so it round-trips through PowerPoint
   without losing the marker.
3. **Layer hints.** `shape.layer = "badge"`,
   `shape.layer_above = "card"`. Asserts a deliberate z-order
   relationship; the linter treats overlaps consistent with the layer
   declaration as intentional and inconsistent ones as errors.

In JSON specs (below), all three are expressible as fields on a shape
entry, so an LLM can declare its intent at generation time.

### [x] Auto-fix

Some issues can be repaired without designer judgment; some can't.

- **`TextOverflow` → autofit.** Apply `MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE`
  using a Pillow-driven sizing pass, respecting a configurable minimum
  font size. If the minimum is hit and text still overflows, downgrade
  to a `TextOverflow` warning.
- **`OffSlide` → nudge.** Translate the shape so it sits inside the
  slide. Logs an info-level note; never silent.
- **`ShapeCollision` → not auto-fixable.** Nudging shapes apart almost
  always breaks the design. Reported only.

```python
report.auto_fix()                      # mutates; returns list of fixes
report.auto_fix(dry_run=True)          # preview; no mutation
```

### Validation hooks

```python
prs.lint_on_save = "off"               # default, no checks at save
prs.lint_on_save = "warn"              # log via stdlib logging
prs.lint_on_save = "raise"             # raise LintError on save
```

Off by default to preserve drop-in compatibility with 1.0.2 user code.

### JSON authoring

A single entry point for generator scripts (LLM or otherwise):

```python
from pptx import Presentation
from pptx.compose import from_spec

prs = from_spec({
    "theme": {"palette": "modern_blue", "fonts": "inter"},
    "slides": [
        {
            "layout": "title",
            "title": "Q4 Review",
            "subtitle": "April 2026",
            "transition": "morph",
        },
        {
            "layout": "kpi_grid",
            "title": "Run-rate metrics",
            "kpis": [
                {"label": "ARR", "value": "$182M", "delta": +0.27},
                {"label": "NDR", "value": "131%", "delta": +0.03},
            ],
        },
        {
            "layout": "bullets",
            "title": "Customer impact",
            "bullets": [
                "Two flagship customers shipped this week.",
                "NPS improved 8 points QoQ.",
            ],
        },
    ],
    "lint": "raise",                   # fail loudly on bad output
})
```

Schema is JSON-schema-validated before construction. Layout names
resolve to Phase 8 design recipes when those exist; in 1.2.0 they map
to a small built-in set of layouts using the host presentation's
master.

### What's deliberately *not* in this phase

- Theme palette resolution (Phase 5).
- The full `pptx.design.recipes` library (Phase 8). 1.2.0 ships with
  ~5 hand-rolled layouts so `from_spec` is useful immediately.
- Live re-layout on edit. The linter inspects; it does not maintain a
  constraint graph.

### Done when

A 20-slide deck generated from a JSON spec by an LLM is run through
the linter and produces zero `error`-severity issues, and the same
linter applied to a hand-built deck flags every one of a curated set
of "real-world LLM mistakes" (text overflow, shapes off-slide, charts
stacked under titles).

---

## Phase 3 — Visual effects (target: 1.3.0)

The single highest-impact *visual* feature. The OOXML element classes
are already wired up at `oxml/shapes/shared.py:395`; we just need real
children.

- [x] **`ShadowFormat`, expanded.** `dml/effect.py:6-42` now exposes
  `blur_radius`, `distance`, `direction`, and `color` (`ColorFormat`, supports
  theme + RGB) in addition to the existing `inherit` property. All reads are
  non-mutating; the `<a:effectLst>`/`<a:outerShdw>` hierarchy is created lazily
  on first write. (`style`/`preset` enum attributes deferred — complex variant
  handling; `size`/skew attrs deferred to a follow-up.)
- [x] **New `GlowFormat`, `SoftEdgeFormat`** with a parallel non-mutating API.
  Surfaced as `shape.glow` (radius, color) and `shape.soft_edges` (radius).
  `ReflectionFormat` and `BlurFormat` are deferred to a follow-up.
- [x] **OOXML element classes.** New `oxml/dml/effect.py` with `CT_EffectList`,
  `CT_OuterShadowEffect`, `CT_GlowEffect`, `CT_SoftEdgesEffect`. Remaining
  variants (`CT_InnerShadowEffect`, `CT_ReflectionEffect`, `CT_BlurEffect`)
  deferred to a follow-up.
- [x] **Inheritance semantics.** Reading a property on a shape with no
  explicit value returns `None`. (Theme-walking is deferred to Phase 5.)
- [x] **`RGBColor.alpha` / per-color transparency.** Adds `<a:alpha>`
  emission inside any `ColorFormat` consumer. Unlocks "glassy card"
  looks. Surfaced as `color_format.alpha` (read/write float in
  `[0.0, 1.0]`, defaulting to fully opaque); also available on the
  `_LazyColorFormat` proxy returned by `Font.color` / `LineFormat.color`,
  with the same non-mutating read semantics.
- [x] **`Font.fill`.** Tiny addition: `Font` already has access to `rPr`,
  but no public `fill`. Add it. Unblocks gradient-text and patterned
  text titles. *(Already present upstream as `Font.fill`, kept and
  documented.)*

**Done when:** a user can compose a card-style shape with custom outer
shadow + soft edge + alpha-tinted fill in five lines of Python and
PowerPoint renders it identically to a card built in the UI.

## Phase 4 — Tables and transitions (target: 1.4.0)

Two unrelated medium-effort wins, packaged together because each is
small.

- [x] **`Cell.borders`.** Today border styling requires manual XML
  injection of `<a:lnL>`, `<a:lnR>`, `<a:lnT>`, `<a:lnB>` under
  `<a:tcPr>`. Add a `Borders` value object exposing
  `cell.borders.left/right/top/bottom/diagonal_down/diagonal_up`,
  each a `LineFormat`. Add convenience: `Borders.all(...)`,
  `Borders.outer(...)`, `Borders.none()`. Fixes the single most-asked-for
  table feature.
- [x] **`Slide.transition`.** `<p:transition>` is now wired up via
  `CT_SlideTransition` and exposed as `slide.transition` (a
  `SlideTransition` proxy). Initial scope:
  - `transition.kind = MSO_TRANSITION.MORPH` — `MSO_TRANSITION_TYPE`
    enum covering 25+ kinds, including `p14:` extension transitions
    (Morph, Vortex, Conveyor, Switch, Gallery, Fly Through). The
    `p14` namespace was added to `oxml/ns.py`.
  - `transition.duration` (ms; reads/writes `p14:dur`, falls back to
    mapping the legacy `spd` bucket on read).
  - `transition.advance_on_click` (writes `advClick="0"|"1"`).
  - `transition.advance_after` (ms; writes `advTm`).
  - `transition.clear()` removes the `<p:transition>` element entirely.
  - Reads on an unset transition return `None` and never mutate XML,
    keeping theme inheritance intact.
  - Direction attributes and the `Presentation.set_transition(...)`
    deck-wide helper are deferred to a follow-up.
- [x] **Run-level internal hyperlinks.** `run.hyperlink.target_slide =
  deck.slides[7]` writes a relationship-based action instead of a URI.
  Single XML attribute swap; missing today.

**Done when:** a deck can be authored with per-cell zebra-striped
borders and a Morph transition between two title slides.

## Phase 5 — Animations (target: 1.5.0)

The single most-requested feature. Largest design surface in this
roadmap. We ship the **preset subset only** — the full timing tree is
expressive enough to break PowerPoint, and 90% of users want one of a
dozen entrance presets.

- [x] **`pptx.animation` module.** New top-level public module with
  `Entrance`, `Exit`, `Emphasis`, and `SlideAnimations` classes.
  Accessible via `slide.animations`.
- [x] **Trigger model.** `Trigger.ON_CLICK` /
  `Trigger.WITH_PREVIOUS` / `Trigger.AFTER_PREVIOUS`, with `delay`.
  Implemented in `pptx/enum/animation.py` as `PP_ANIM_TRIGGER`;
  `Trigger` alias exported from `pptx.animation`.
- [x] **Entrance presets.** 8 presets: Appear, Fade, Fly In (4
  directions), Float In, Wipe, Zoom, Wheel, Random Bars. Each maps
  to a known `presetID` in the `<p:par>/<p:cTn>` tree.
- [x] **Emphasis presets.** Pulse, Spin, Teeter — using `<p:animScale>`,
  `<p:animRot>` behaviors.
- [x] **Exit presets.** Disappear, Fade, Fly Out, Float Out, Wipe, Zoom
  (mirror of entrance with `presetClass="exit"` and `transition="out"`).
- [x] **Round-trip preservation.** New effects are appended to the
  existing timing tree without touching any pre-existing `<p:par>` nodes;
  PowerPoint-authored animations survive a read-modify-write cycle intact.
- **Motion paths.** `MotionPath.line(shape, dx, dy, duration)` and
  `MotionPath.custom(shape, svg_path_d, duration)` — deferred to follow-up.
- **Sequencing.** `with slide.animations.sequence(start=...): ...`
  context manager — deferred to follow-up.
- **By-paragraph animation.** For text frames: `Entrance.fade(text_frame,
  by_paragraph=True)` — deferred to follow-up.

**Done when:** a generated 10-slide deck with on-click bullet reveals
plays in PowerPoint identically to one assembled in the UI, and a deck
authored in PowerPoint with custom animations is round-tripped without
loss.

## Phase 6 — Theme, picture effects, advanced fills (target: 1.6.0)

- [x] **Read-only theme API.** `prs.theme.colors[MSO_THEME_COLOR.ACCENT_1]`
  resolves to `RGBColor`; `prs.theme.fonts.major` / `.minor` return font
  names. New `pptx/theme.py` module (`Theme`, `ThemeColors`, `ThemeFonts`)
  on top of the expanded `oxml/theme.py`. Wired into `Presentation.theme`
  and `SlideMasterPart.theme`.
- **Theme-aware inheritance** for effect/color getters from Phase 2.
  When a property has no explicit value, the getter walks
  `slide → layout → master → theme` and returns the resolved value (or
  `None` if nothing matches). Deferred to follow-up.
- **Picture effects.** `Picture.transparency`, `.brightness`,
  `.contrast`, `.recolor` (grayscale, sepia, washout, duotone). Maps to
  `<a:lum>`, `<a:alphaModFix>`, `<a:duotone>`, `<a:biLevel>`,
  `<a:grayscl>` inside `<a:blip>`.
- **Native SVG in `add_picture`.** Embed both an SVG `<asvg:svgBlip>`
  and a PNG fallback (modern PowerPoint requires both); rasterize via
  `cairosvg` for the fallback. New optional dependency.
- **Radial / rectangular / path-shape gradients.** `FillFormat.gradient`
  takes a `kind` argument; `GradientStops` becomes mutable
  (`append`, `replace`, `__delitem__`).
- [x] **Line ends, caps, joins, compound lines.** `line.head_end`,
  `line.tail_end` (each a `LineEndFormat` exposing `.type`, `.width`,
  `.length`), `line.cap` (`MSO_LINE_CAP`), `line.compound`
  (`MSO_LINE_COMPOUND`), and `line.join` (`MSO_LINE_JOIN`, mapping to
  `<a:round/>` / `<a:bevel/>` / `<a:miter/>`). Reads are non-mutating;
  setting an end attribute lazily creates `<a:ln>`/`<a:headEnd>` and
  clearing the last attribute drops the end element again so theme
  inheritance is preserved.
- **Text fit estimator.** Pillow-driven measurement so
  `TextFrame.fit_text` works without requiring a `font_file=` argument
  in the common case.

**Done when:** a generated deck honors a brand color palette read from
the theme, recolors photos to match it, and embeds vector logos at
print resolution.

## Phase 7 — Slide composition and theme writer (target: 1.7.0)

Solves "I want to merge decks" — the JSON entry point already shipped
in Phase 2, but cross-presentation operations are the remaining piece.

- **`pptx.compose` package** (extending the module introduced in
  Phase 2 for `from_spec`).
- **`import_slide(other_slide, *, merge_master='dedupe' | 'clone')`.**
  Clones a slide from another presentation, including its layout
  reference, with master-deduplication and image-rename collision
  handling. Closes the upstream issues that today force users into
  Aspose/Spire.
- **`apply_template(potx_or_pptx)`.** Re-points slides at masters/layouts
  imported from a `.potx` or `.pptx`.
- **Theme writer.** Now that we have read-only theme + composition
  primitives, expose `prs.theme.colors[MSO_THEME_COLOR.ACCENT_1] =
  RGBColor(...)` and `prs.theme.apply(other_theme)`.

**Done when:** `Presentation.import_slide(prs2.slides[3])` produces a
result indistinguishable from drag-and-drop in PowerPoint, and a brand
theme can be swapped in from a `.potx` in one call.

## Phase 8 — 3D, SmartArt text substitution (target: 1.8.0)

- **3D primitives.** Bevels (`a:bevelT`/`a:bevelB`) and extrusion
  (`a:sp3d`) under a new `shape.three_d` accessor. The `<a:scene3d>`
  / `<a:sp3d>` slots are already reserved at
  `oxml/shapes/shared.py:368-369`.
- **SmartArt text substitution.** `slide.smart_art[0].set_text(['NY',
  'CA', 'TX'])` rewrites the text-list inside an *existing*
  `diagrams/data1.xml` without touching the layout. Bounded scope —
  full SmartArt creation remains explicitly out.

**Done when:** a corporate org-chart template can be re-populated with
fresh names entirely from Python, and a "card" shape can render with
bevel + soft shadow in three lines.

## Phase 9 — Design system layer (target: 1.9.0)

The piece that turns the low-level API into something where the
*default* output looks good. Nothing here adds new XML — it's all on
top of the foundations from earlier phases.

- **`pptx.design.tokens.DesignTokens`.** Palette, typography, radii,
  shadows, spacings. Sources:
  - `DesignTokens.from_yaml('brand.yml')`
  - `DesignTokens.from_pptx('template.pptx')` (extracts from `theme.xml`)
  - hand-built dict.
- **`shape.style`.** Token-resolving facade: `shape.style.fill =
  tokens.palette['primary']`, `shape.style.shadow = tokens.shadows
  ['card']`. Internally fans out to `fill`, `shadow`, etc.
- **`pptx.design.layout`.** `Grid(slide, cols=12, gutter=Pt(12))`,
  `Stack(direction='vertical', gap=Pt(8))` — build-time layout helpers
  that compute `left`/`top`/`width`/`height` so users don't eyeball EMUs.
- **`pptx.design.recipes`.** Opinionated parameterized slide
  constructors: `TitleSlide`, `BulletSlide`, `KPISlide`, `QuoteSlide`,
  `ImageHero`. Each consumes tokens, places shapes, sets text, applies
  effects, optionally adds animation/transition.
- **A small published "starter pack"** — 2–3 example token sets
  (Modern, Classic, Editorial) with matching screenshots. Lives in
  `examples/` so it doesn't bloat the package itself.

**Done when:** a user can `pip install python-pptx-next`, copy 30 lines
from the README, and produce a deck that wouldn't look out of place in
a series-A pitch.

## Phase 10 — Stretch / community (target: 1.10.0+)

Items that are valuable but not on the critical path:

- Chart palette presets independent of `chart_style`.
- Per-series chart fills (gradient/pattern) via `ChartFormat`.
- Chart "quick layouts" (mirroring PowerPoint's gallery).
- Additional motion-path presets.
- A slide-thumbnail renderer (likely shells out to LibreOffice headless;
  optional dependency).
- Documentation site rebuild.

---

## Phase 11 — 2.0.0 (the breaking-changes release)

Everything that's been accumulating deprecation warnings through 1.x
gets removed:

- `ShadowFormat.inherit` — replaced by reading individual properties
  for `None`. Removed.
- `ERCENT_40` typo alias — removed.
- `turbo_add_enabled` no-op — removed.
- `Font.color` mutating-on-read fallback (kept under a deprecation flag
  in 1.x for users who depended on the old behavior) — removed.
- `RGBColor.from_string("3C2F80")` (no `#`) deprecated in favor of
  `RGBColor.from_hex("#3C2F80")` — old method removed.
- Drop Python versions that hit EOL during 1.x.

No new features in 2.0; it's a cleanup release. New features land in
2.1.

---

## How to follow / contribute

- **Issues**: GitHub issue tracker on the fork repository.
- **Roadmap discussion**: each phase gets a tracking meta-issue once the
  previous phase is in beta.
- **PR scope**: small. Each public API surface from the phases above
  should be its own PR with tests, docs, and a HISTORY entry.
- **What we say no to**: features that require non-trivial new
  dependencies, features that don't round-trip cleanly, and anything in
  the "out of scope" list above without a strong new argument.

This document will be updated each release with what actually shipped
and what slipped. The dates are deliberately absent; the order is the
commitment.
