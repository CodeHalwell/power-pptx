# Improvement plan v2 — surface coverage

A candid follow-on to `IMPROVEMENT_PLAN.md`, written after a
top-to-bottom audit of the codebase at v2.5.0. Where the first plan
focused on footguns the existing API hands to authors, this one
focuses on the *surface area* that's still missing — features that
are in the OOXML schema, that PowerPoint renders natively, and that
users currently have to reach for raw XML (or for a different tool)
to use.

The audit covered: visual effects, animations, transitions, charts,
tables, object grouping, collision detection, text styling, HTML
embedding, and a long tail of cross-cutting ergonomics.

The over-arching theme: **the foundations are strong but the surface
is narrow**. The Phase 3 effect tree, the Phase 5 animation timeline,
and the Phase 4 transition catalog each have ~50% of their schema
exposed. The chart catalog is missing the "go to Excel for this"
chart types (waterfall, funnel, treemap, sunburst, box-and-whisker).
The text-styling surface is missing the run-property knobs that
separate "looks branded" from "looks generated." Closing each of
these is mostly mechanical — schema is wired up, classes are already
registered, the public proxy just isn't there yet.

Items already on `IMPROVEMENT_PLAN.md` are excluded.

Effort × impact tags use the convention `[low/high]` = small change,
big payoff; `[high/med]` = sizeable change, moderate payoff.

---

## P0 — closes a category, mostly mechanical

### V1. Visual effects: fill out the proxy layer

`CT_InnerShadowEffect`, `CT_PresetShadowEffect`, and
`CT_FillOverlayEffect` all round-trip in `oxml/dml/effect.py`, but
none of them have a high-level facade. The pattern from
`ShadowFormat` / `GlowFormat` is well-established and can be
duplicated for each.

- **`shape.inner_shadow`** — mirrors `shape.shadow`. `[low/high]`
- **`shape.preset_shadow`** with an enum for the 20 PowerPoint
  shadow gallery presets (`<a:prstShdw prst="shdw1"|…>`).
  `[low/high]`
- **`shape.fill_overlay`** with `MSO_BLEND_MODE` (overlay, multiply,
  screen, darken, lighten). Unlocks blend-mode compositing without
  raster work. `[med/high]`
- **Reflection — fill out the schema attributes.** The current
  proxy exposes 5 of 14 `<a:reflection>` attributes; missing
  `sx/sy`, `kx/ky`, `algn`, `rotWithShape`, `stPos/endPos`,
  `fadeDir`. The 5 we have aren't enough to match a designer-built
  reflection. `[low/med]`
- **Theme `effectStyleLst` reader/writer.** Masters carry inherited
  fill/line/effect "style sets"; nothing reads or applies them.
  Pairs naturally with the existing `theme.py` work. Without this,
  per-shape effect state can't inherit from a brand theme.
  `[med/high]`

### V2. Picture: artistic filters and corrections

`PictureEffects` exposes brightness, contrast, recolor, and duotone.
Missing the artistic-filter family that PowerPoint surfaces under
*Format Picture → Picture Effects*:

- `picture.effects.apply_artistic("pencil_sketch" | "chalk_sketch"
  | "glow_edges" | "photocopy" | "glass" | "paint_strokes" |
  "marker" | "mosaic_bubbles" | "light_screen" | "watercolor" |
  "cement" | "texturizer")`. `[med/high]`
- `picture.effects.exposure`, `.saturation`, `.sharpen`. The
  underlying `<a:lum>`/`<a:alphaModFix>` siblings are addressable;
  no high-level path. `[low/med]`

### V3. 3D: scene camera and light rig

`shape.three_d` covers `<a:bevelT>`, `<a:bevelB>`, and `<a:sp3d>`.
Missing the part of the schema that controls how the 3D shape is
*viewed*:

- `three_d.camera = Camera(rig="orthographic" | "perspective",
  rotation=(x, y, z))` for `<a:scene3d><a:camera>`. `[med/med]`
- `three_d.light_rig = LightRig(kind="three_pt" | "rim" |
  "sunrise" | …, direction=…)` for `<a:scene3d><a:lightRig>`.
  Without this you can't reproduce any of the PowerPoint UI's 3D
  presets. `[med/med]`
- `three_d.contour` — post-extrusion edge color/width.
  Schema-supported, no API. `[low/med]`

---

## P1 — animations: the gallery is too narrow

The 2.4.0 animation API has 8 entrance, 3 emphasis, and 6 exit
presets. The PowerPoint gallery has 22 / 30+ / 18+ respectively. As
long as `power_pptx.animation` stays experimental (per
`IMPROVEMENT_PLAN.md` #1), this isn't catastrophic — but the moment
the playback bug is fixed, the gallery gap becomes the next
limiting factor.

### A1. Entrance presets — close the gallery gap

Current: Appear, Fade, Fly In, Float In, Wipe, Zoom, Wheel, Random
Bars. Missing the high-frequency UI presets, all of which are known
`presetID`s in the timing tree:

- `Bounce`, `Compress`, `Expand`, `Stretch`, `Spinner`, `Boomerang`,
  `Drop`, `Curve Up`, `Spiral In`, `Peek In`, `Swivel`. `[low/high]`

### A2. Emphasis presets — the data-deck blocker

Current: Pulse, Spin, Teeter. Missing the ones a value-changing KPI
actually needs:

- `Color Wave`, `Brush On Color`, `Fill Color`, `Grow/Shrink`,
  `Transparency`, `Color Pulse`, `Bold Reveal`, `Blink`, `Darken`,
  `Lighten`. `[med/high]`
- **`animColor` standalone.** Distinct from the preset emphasis;
  lets a series bar tween from grey to brand color. Schema-ready,
  no proxy. `[med/high]`

### A3. Animation properties currently unreachable

- **`auto_reverse=True`** on every preset call — schema-ready,
  not exposed. `[low/med]`
- **`repeat_count=N` / `repeat_until_click`** — same. `[low/med]`
- **Easing curves** (`accel`, `decel` on `<p:cTn>`) — every preset
  accepts a `delay` but no `ease="in"|"out"|"in_out"`. `[low/med]`
- **After-effect dim-to-color** — `<p:cTn> animEffect filter="dim"`
  so a bullet greys out after its turn. Single most-requested
  "build slide" feature. `[med/high]`

### A4. Triggers beyond `ON_CLICK` / `WITH_PREVIOUS` /
`AFTER_PREVIOUS`

- **`Trigger.ON_CLICK_OF(other_shape)`** — click-on-specific-shape;
  one extra `<p:tgtEl><p:spTgt spid=…/>` write. `[low/high]`
- **Bookmark / hyperlink trigger** — schema-ready, no API.
  `[med/low]`

### A5. Direction-aware presets

`Entrance.fly_in()` is hard-coded to 4 cardinal directions.
PowerPoint supports 8 (corners) and arbitrary degree rotation. Add
a `direction=Direction.TOP_LEFT` kwarg. `[low/med]`

### A6. Motion-path gallery

Current: line, custom, diagonal, circle, arc, zigzag, spiral. Round
out the PowerPoint preset path gallery with:

- **`MotionPath.bezier`** — arbitrary control points. `[low/med]`
- **`MotionPath.figure_eight`** and **`MotionPath.heart`** —
  named-preset coverage to match the UI. `[low/med]`

### A7. Animation sound

`<p:sndAc><p:stSnd>` rounds-trips today on PowerPoint-authored
decks but is read-only. Add `entrance.sound = "applause" | path`.
`[low/med]`

---

## P2 — transitions: direction is the headline gap

### T1. `transition.direction`

`MSO_TRANSITION_TYPE.PUSH / WIPE / COVER / STRIPS / BLINDS / WHEEL`
all support a direction parameter in PowerPoint and in the XML, but
the API has no `direction` setter. Buried as raw attribute access
today. The PowerPoint UI defaults to "From Bottom" for several of
these — without the setter, generated decks can't even match what
the UI ships as default.

`[low/high]`

### T2. PowerPoint 2013+ / 2016+ transitions

`MSO_TRANSITION_TYPE` covers 26 transitions. Missing: `Honeycomb`,
`Cube`, `Rotate`, `Drape`, `Curtains`, `Wind`, `Prestige`,
`Fracture`, `Crush`, `Peel Off`, `Page Curl`, `FlipDown`, `FlipUp`,
`Glitter`, `Origami`, `Shuttle`, `Flash`. All `p15:` extensions;
they round-trip already, just need enum entries. `[med/med]`

### T3. Transition sound

`<p:sndAc><p:stSnd>` on a slide-level transition; schema ready, API
absent. `[low/low]`

---

## P3 — charts: close the "go to Excel for this" gap

The 2.5.0 chart catalog is solid for the standard line/bar/pie/area
family, but five chart types people leave the library to draw
elsewhere are all native `<c:*Chart>` elements that PowerPoint 2016+
renders. Each is a new `XL_CHART_TYPE` entry plus a `PlotFactory`
handler.

### C1. Chart types

- **`WATERFALL`** — change-from / total breakdown. `[med/high]`
- **`FUNNEL`** — conversion / pipeline. `[med/high]`
- **`TREEMAP`** — hierarchical size + color. `[med/high]`
- **`SUNBURST`** — nested ring / multi-level breakdown. `[med/high]`
- **`BOX_AND_WHISKER`** — distribution / quartile. `[med/high]`
- **`HISTOGRAM` / `PARETO`** — frequency. `[med/high]`

### C2. Series-level features

- **`series.trendlines.add(kind, show_equation=, show_r2=)`** —
  `<c:trendline>`. `[med/high]`
- **`series.error_bars.fixed(...)` / `.percentage(...)` /
  `.stdev(...)` / `.custom(plus, minus)`** — `<c:errBars>`. The
  single most-asked-for feature for scientific decks. `[med/high]`
- **`series.axis_group = SECONDARY`** or
  **`chart.secondary_value_axis`** — current path is XML
  traversal. `[low/high]`
- **`series.highlight_point(idx, color=...)`** — shortcut for the
  per-point format dance the "highlight one outlier" pattern needs.
  `[low/med]`

### C3. Plot-level features

- **`DoughnutPlot.hole_size`** — `<c:holeSize>` (10–90%).
  `[low/med]`
- **`LinePlot.smooth`** — `<c:smoothing val="1"/>`. `[low/med]`
- **High-low lines, drop lines, up/down bars** on stock/line plots.
  Schema ready. `[low/med]`
- **Log-scale value axis** — `<c:logBase>`. `[low/med]`
- **`axis.tick_label_rotation`** — `<c:txPr><a:bodyPr rot=…/>`.
  `[low/med]`

### C4. Locale-aware number formatting

`chart.set_locale("fr_FR")` for thousand separators / decimal marks
/ currency in axes and data labels. Currently the format is
hardcoded to en-US. `[med/med]`

### C5. Data-label data-table footer

`plot.data_labels.show_data_table = True`, with
`data_table_legend_keys` and `data_table_include_headers`. The
flag is in the schema; the proxy doesn't expose it. `[low/med]`

### C6. Sparklines

A `Cell.add_sparkline(...)` (line / column / win-loss) and a
slide-level `slide.shapes.add_sparkline(...)` for in-card micro
charts. Sparklines aren't a real OOXML chart type — they're a
simplified line render — so this is a higher-effort item, but it
slots cleanly next to the chart catalog. `[high/med]`

---

## P4 — tables: the gallery + cell-content gap

### TB1. Table-style gallery

PowerPoint ships ~70 named built-in styles (*Light Grid – Accent 1*,
*Dark List*, etc.). `table.style = "Light Grid – Accent 1"` is the
headline missing UX. Currently borders are manual cell-by-cell.
`[med/high]`

### TB2. Cell-level ergonomics

- **`cell.text_rotation`** — `<a:bodyPr rot=…>` shortcut. Matrix
  headers and 90°-rotated column-header patterns need this.
  `[low/high]`
- **`cell.vertical_align`** — currently routed via
  `cell.text_frame.vertical_anchor`. An alias on the cell itself
  matches the Excel/Word convention. `[low/med]`
- **`cell.add_image()`, `cell.add_table()`, `cell.add_chart()`** —
  cells today only hold a `text_frame`. `[high/high]`

### TB3. Table-level features

- **`table.auto_fit_columns()`** — measure-driven sizing; pairs
  with `TextFitter`. `[med/med]`
- **Conditional cell formatting.** Declarative rule:
  `cell.format_if(value > 100, fill="red")`. Nothing today.
  `[high/med]`
- **`table.first_row_pattern` / `last_row_pattern` /
  `column_banding`** — `<a:tblPr firstRow="1">` etc. is in the
  schema; no Python ergonomics. `[low/med]`

---

## P5 — object grouping

The group surface is the smallest and most under-specified part of
the shape API. Each item below is mechanical.

- **`group.ungroup()`** — promote children to parent, preserving
  z-order. Common UI affordance, missing. `[low/high]`
- **`group.bbox` / `group.extent`** — tight bounding box; needed
  for alignment, distribution, and lint. `[low/high]`
- **`group.move(dx, dy)`** — translate the whole group atomically.
  Currently you have to walk children. `[low/high]`
- **`group.fill`, `group.line`** — `<p:grpSpPr>` does support
  fill/line; the API doesn't expose them, so you can't tint a
  whole group. `[low/med]`
- **`group.rotate(deg)` / `group.scale(sx, sy)`** — geometry
  transforms on the group rather than the children. `[med/med]`
- **`group.shapes_recursive()`** — nested group of groups is
  allowed but no traversal helpers. Makes lint and layout fragile.
  `[low/med]`

---

## P6 — collision detection

The 2.2.0 scoring + bleed-aware geometry covered the "duplicate
rectangle" and "shadow runs off-slide" cases. The next tier is
softer signals.

- **Text-overlapping-non-text detector.** Today `ShapeCollision`
  doesn't distinguish "text bbox over visual content" from "card
  under badge." A text frame running into an adjacent chart is
  the most common real overflow. `[med/high]`
- **Alignment-hint detector.** Find shapes "almost aligned" with
  each other (4 shapes at `x=1.0"`, 1 at `x=1.002"`) and propose
  snapping. Distinct from `OffGridDrift`, which assumes an
  existing grid. `[med/high]`
- **Distribution irregularity.** Five cards horizontally with gaps
  `[12, 12, 13, 12, 11]` — flag the odd gap. `[low/med]`
- **Padding-aware "tight spacing" warning.** Two shapes 0.02"
  apart trigger nothing today, but visually they're cramped.
  `[low/med]`
- **Cluster grouping in the report.** Roll all collisions in the
  same region into one issue; today the same KPI card array logs
  N×N pairs. `[med/med]`
- **Cross-slide consistency lint** at the `prs.lint()` level —
  flag when 80% of slides use `#FF6600` and 1 slide uses
  `#FF6601`. `[med/high]`
- **`report.diff(baseline)`** — return only newly-introduced
  issues. CI hookable. `[med/high]`
- **`report.to_json()` / `report.to_sarif()`** — machine-readable
  lint for dashboards and LLM auto-fix loops. SARIF would slot
  directly into GitHub code-scanning. `[low/high]`

---

## P7 — text styles: the run-property surface

`<a:rPr>` is the richest surface that's least exposed. Each item
below is a one- or two-line proxy on `Font` or `_Paragraph`.

### TX1. Text effects

- **`Font.shadow`, `Font.glow`, `Font.outline`** — text-effect
  properties that PowerPoint's UI surfaces prominently and that
  round-trip today. Nothing reads or writes them. `[low/high]`
- **Gradient text fill** — `<a:gradFill>` inside `<a:rPr>`. The
  "white→accent gradient on a hero title" combination is a
  designer staple and currently impossible without raw XML.
  `[med/high]`

### TX2. Run properties

- **`Font.letter_spacing`** (= tracking) — `<a:rPr spc="100">`.
  `[low/high]`
- **`Font.baseline_shift`, `.superscript`, `.subscript`** —
  `<a:rPr baseline="…">`. `[low/med]`
- **`Font.all_caps`, `.small_caps`** — `<a:rPr cap="all"|"small">`.
  Eyebrows + section labels constantly need this. `[low/high]`
- **Underline styles.** `MSO_TEXT_UNDERLINE_TYPE` is missing
  `DOUBLE_LINE`, `WAVY`, `DOTTED`; `<a:uFill>` color sub-element
  is also unreachable. `[low/med]`
- **Strikethrough double variant** — `<a:rPr strike="dblStrike">`.
  `[low/low]`
- **Per-run language tag** — `<a:rPr lang="…">`. `language_id`
  exists at frame level only; mixed-script decks need per-run.
  `[low/med]`

### TX3. Paragraph properties

- **RTL paragraph direction** — `<a:pPr rtl="1">`. Required for
  Hebrew / Arabic / Farsi. `[low/high]`
- **Tab stops** — `<a:pPr><a:tabLst>`. `[med/med]`
- **Numbered list `start_at`** — `<a:buAutoNum startAt=…>`. One
  attribute miss. `[low/low]`
- **Image bullets** — bullet glyph via embedded image; common for
  branded check-mark bullets. `[med/med]`
- **Per-level multi-list templates** — define level 0/1/2 bullets
  once on the textframe; today every paragraph repeats. `[med/med]`

### TX4. TextFrame properties

- **Multi-column textframe** — `<a:bodyPr numCol="2"
  spcCol="…">`. `[low/med]`
- **Drop-cap helper** — pure layout helper on top of paragraph
  indent + first-run size. `[med/low]`

---

## P8 — HTML / figure embedding

`add_html_figure` screenshots via Playwright. The screenshot path
is fragile; several quality knobs would harden it.

- **CSS / JS / theme-mode controls on `add_html_figure`** —
  `prefers_color_scheme="dark"`, `wait_for_selector=`,
  `js_eval=`, `device_pixel_ratio=`. `[low/high]`
- **HTML→native-shape converter.** `from_html(html)` parses
  headings as titles, `<ul>` as bullets, `<table>` as a real
  power-pptx table, `<img>` as a picture, `<pre>` as a
  `code_slide`. This is the markdown-to-deck bridge LLM workflows
  want, and it removes the dependency on the screenshot path
  entirely. `[high/high]`
- **Multi-slide HTML splitter.** Split on `<hr>`, `<h1>`, or
  `<section>`; one HTML doc → N slides. Pairs with the converter.
  `[med/med]`

---

## P9 — cross-cutting / meta

### M1. Slide-level surface

- **Sections API** — `prs.sections` is missing.
  `<p:sectionLst>` is in the schema; large decks (50+ slides)
  need section ergonomics for the outline pane. `[med/high]`
- **Slide reorder / move helpers** — `prs.slides.move(from, to)`,
  `prs.slides.reorder([…])`. Today this is XML manipulation.
  `[low/high]`
- **`Slide.notes` first-class API** — speaker-notes round-trip
  today only via the placeholder; LLM "deck + notes" workflows
  need a `slide.notes = "…"` setter. `[low/high]`
- **`slide.background.image(path)` / `.gradient(...)`** — schema
  lives, no high-level path. `[low/high]`
- **Recipe slide wrapper with named anchors** — already on
  `IMPROVEMENT_PLAN.md` #9, but worth re-stating here: recipes
  returning a `RecipeSlide` exposing `title_zone`, `body_zone`,
  `footer_zone`, `eyebrow_zone` is the cleanest fix and unblocks
  a lot of "address shapes by index" code. `[med/high]`

### M2. Theme + design tokens

- **`prs.theme.to_dark_mode()`** — invert palette while
  preserving WCAG contrast. Single-call dark-mode toggle.
  `[med/high]`
- **`DesignTokens.from_seed("#3B82F6", harmony="triadic")`** —
  palette generator from a seed color. Brand-onboarding friction
  reducer. `[low/high]`
- **`tokens.validate_color_blindness("deuteranopia"|…)`** —
  flag confusable pairs. Pairs with the existing lint surface.
  `[med/high]`
- **`prs.theme.save_thmx(path)`** — write the theme out as a
  standalone Office theme file for distribution. `[med/med]`

### M3. Spec authoring + LLM-friendly errors

- **JSON Schema export** — `power_pptx.spec.json_schema()` so
  IDEs autocomplete and lint specs before building. Big
  LLM-authoring win. `[low/high]`
- **Did-you-mean for unknown spec keys.** `from_spec` already
  rejects them (2.5.0); raise a `ValueError` with the closest
  match name (Levenshtein over the known schema). Pure DX.
  `[low/high]`
- **LLM-friendly error messages.** All `power_pptx.exc` errors
  should include: (1) what went wrong, (2) why it matters,
  (3) a concrete code example of the fix. Makes errors
  recoverable for an LLM in a single follow-up turn. `[med/high]`

### M4. Accessibility

- **`shape.alt_text`, `slide.reading_order`, `prs.audit_accessibility()`.**
  Currently silent on a11y; legally required in some sectors.
  `[med/high]`
- **`prs.preflight()`** — rolls up lint + accessibility + size
  + missing-fonts + low-res-image into one report for
  production handoff. `[med/high]`

### M5. Media handling

- **Embedded font subsetting.** Current approach embeds full
  fonts; subset to glyphs in use, often 80% file-size reduction.
  `[high/med]`
- **`prs.compress_images(max_dim=1920, quality=85)`** — similar
  to PowerPoint's *Compress Pictures*. Decks generated from
  photo libraries balloon to 100MB+ today. `[med/high]`
- **Animated GIF first-class support** — recognize MIME, embed
  as media rather than a static image. `[low/med]`
- **Video ergonomic insert** — `slide.shapes.add_video(path,
  left, top, width, height)` instead of the current low-level
  media-part dance. `[low/high]`

### M6. CLI + plugins

- **CLI** — `power-pptx new`, `power-pptx lint`, `power-pptx
  render-thumbs`. The library is Python-only today; a thin CLI
  on top makes it scriptable from CI / Make. `[med/high]`
- **Plugin / extension API** — `@power_pptx.register_recipe`,
  `@power_pptx.register_lint_rule`,
  `@power_pptx.register_chart_palette`. Lets brands ship their
  own design system without forking. `[med/high]`

### M7. Validation + diff

- **OOXML schema validation pre-save** — `xmlschema` (optional
  dep) over the part tree to catch malformed output before
  write. Would have caught the `<c:legendPos val="r"/>`
  regression in 2.1.1. `[med/high]`
- **`compare_decks(prs1, prs2)`** — slide-by-slide diff
  (added/removed/changed; color/font/text deltas). Pairs with
  version-control workflows. `[high/med]`

### M8. Internationalization

- **Locale-aware chart number formatting** — see C4. Reused
  across charts and tables. `[med/high]`
- **CJK / mixed-script font fallback chains** on
  `TypographyToken` — `fallback_fonts=["Noto Sans CJK", …]`.
  Cleanly fixes the "title looks fine; body is squares"
  pattern. `[med/med]`

---

## Suggested release plan

This plan sequences the gaps by closing-a-category leverage, then
by mechanical-vs-design effort. Each release is meant to be a
coherent narrative, not a kitchen sink.

| Release | Scope                                                                                                         |
|---------|---------------------------------------------------------------------------------------------------------------|
| 2.6.0   | V1 (effect proxy fill-out: inner shadow, preset shadow, fill overlay, reflection completeness, effectStyleLst). |
| 2.7.0   | C1 + C2 + C3 (chart catalog + trendlines + error bars + secondary axis + plot-level toggles).                  |
| 2.8.0   | TX1–TX4 (text styling: shadow/glow/outline, gradient text, run properties, RTL, tab stops, multi-column).      |
| 2.9.0   | A1–A7 + T1–T3 (animation gallery + transition direction + 2013/2016 transition coverage). Gated on the P0 playback fix. |
| 2.10.0  | TB1–TB3 (table style gallery + nested cell content + conditional formatting + auto-fit).                       |
| 2.11.0  | P5 (groups: ungroup, bbox, move, fill/line, transforms, recursive traversal).                                  |
| 2.12.0  | P6 (lint extensions) + P8 (HTML→native shapes) + M3 (spec JSON Schema + did-you-mean).                          |
| 2.13.0  | M1 (sections, reorder, notes, background) + M2 (theme dark mode, palette generator) + M4 (accessibility).      |
| 2.14.0  | M5 (font subsetting, image compression, video) + M6 (CLI + plugin API) + M7 (schema validation + deck diff).   |

If only one release can ship next, **2.6.0 (effects)** has the
highest leverage: it closes the visual-effects category and
unblocks the brand-deck use case that currently requires raw XML
escapes. **2.7.0 (charts)** is a close second and removes the
most visible "go to Excel" gap.

If only one *item* can ship next, it's **C2 secondary value axis
ergonomics** — every dual-axis chart currently requires XML
traversal, and dual-axis charts are the single most-requested
feature on internal Slack channels and on the upstream issue
tracker.

---

## Method note

This punch list was assembled by:

1. Reading every file in `src/power_pptx/dml/`,
   `src/power_pptx/animation.py`, `src/power_pptx/lint.py`,
   `src/power_pptx/table.py`, `src/power_pptx/text/`,
   `src/power_pptx/chart/`, and `src/power_pptx/design/`.
2. Cross-referencing the OOXML schema for each surface against
   the public proxy, looking for round-tripping XML elements
   that have no Python accessor.
3. Cross-referencing the PowerPoint UI gallery (entrance presets,
   transition catalog, table styles, chart types) against the
   `MSO_*` enums.
4. Walking the public surface for asymmetries (e.g. group has
   no `bbox` while every other shape does, `Font` has
   `language_id` but not per-run `lang`).

Items already on `IMPROVEMENT_PLAN.md` were excluded. Items
shipped per `HISTORY.rst` were excluded. Items where the schema
itself doesn't support the request (full SmartArt creation,
pixel-accurate rendering, a `.ppt` writer) were excluded — they're
rejected in `ROADMAP.md`'s *Out of scope* section and the rejection
still holds.
