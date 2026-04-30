.. :changelog:

Release History
---------------

This project was forked from `scanny/python-pptx`_ at version 1.0.2.
Releases prior to 1.1.0 are upstream history, preserved here verbatim and
attributed to Steve Canny and the original contributors. Releases from
1.1.0 onward are made under the ``power-pptx`` distribution name on
PyPI. Starting with 2.0.0 the importable package name is ``power_pptx``
to avoid a top-level namespace collision when ``python-pptx`` (which
installs the ``pptx`` import name) is also present in the environment.

.. _`scanny/python-pptx`: https://github.com/scanny/python-pptx


2.4.0 (2026-04-30)
++++++++++++++++++

Animation ergonomics, gradient/alpha discoverability, recipe bug fixes,
and a bundled Claude skill.  All additive; nothing removed.

New APIs
~~~~~~~~

- ``slide.animations.group()`` — context manager that animates every
  effect added in the block as a single visual cluster (first effect
  ``AFTER_PREVIOUS``; subsequent ones default to ``WITH_PREVIOUS``).
  Use this for sub-shapes that belong to the same card/row/panel.
  Drastically reduces the per-slide timing-tree size — and the
  perceived lag — relative to the same effects added independently.

- ``SlideAnimations`` is now iterable, supports ``len()``, and exposes
  ``clear()``.  Iteration yields read-only ``AnimationEntry`` views
  with ``kind``, ``preset``, ``trigger``, ``shape_id``, ``shape``,
  ``duration``, ``delay``, and a ``remove()`` method.  Useful for
  re-animating, copying animations between slides, and debugging why
  something didn't fire.  ``purge_orphans`` is unchanged.

- ``fill.linear_gradient(start, end, angle=...)`` (and a multi-stop
  list form) — one-line gradient helper that wraps ``gradient()`` +
  ``gradient_stops`` for the 90% case.  ``gradient_angle``'s docstring
  now spells out the OOXML convention (``0`` left→right, ``90``
  top→bottom, ``180`` right→left, ``270`` bottom→top).

- ``DesignTokens.with_overrides(...)`` now accepts nested-dict input
  in addition to dotted keys (``{"palette": {"primary": "#FF6600"}}``
  is equivalent to ``{"palette.primary": "#FF6600"}``).  Mixed input
  is allowed.

Bundled Claude skill
~~~~~~~~~~~~~~~~~~~~

- The ``power-pptx`` Claude Code skill (``SKILL.md`` + reference docs)
  ships inside the package at ``power_pptx/skill/``.  Install it with
  ``python -m power_pptx.skill install`` (or the ``power-pptx-skill``
  console script).  Pip-installing power-pptx is now sufficient to
  make the skill available wherever the library runs.

Recipe bug fixes
~~~~~~~~~~~~~~~~

- ``figure_slide`` correctly routes inline SVG markup that contains a
  namespace URL (``xmlns="http://..."``) to the SVG embedder rather
  than mis-classifying it as a file path and raising
  ``FileNotFoundError``.

- ``code_slide``'s Pygments highlighting renders ``Token.Operator``
  and ``Token.Punctuation`` in the same colour as plain code text,
  so member-access dots (``optimiser.zero_grad``) stay legible on
  light-surface themes (previously they faded into the background).

``from_spec`` ergonomics
~~~~~~~~~~~~~~~~~~~~~~~~

- Recipe layouts now reject unknown spec keys (``ValueError``) instead
  of silently dropping them.  Catches typos like ``"subtitlz"`` or
  ``"millestones"`` that previously yielded a slide missing the
  intended content.

- ``"comparison"`` is now an unambiguous alias for the comparison
  recipe.  Use ``"comparison_layout"`` to opt in to the
  placeholder-based layout from the underlying template.


2.3.0 (2026-04-29)
++++++++++++++++++

Two P0 fixes, six new recipes, a meaningful lint-noise reduction,
and figure-embedding adapters for Plotly / Matplotlib / HTML.  All
changes are additive; no existing API was removed.

P0 fixes
~~~~~~~~

- ``render_slide_thumbnails`` no longer silently drops slides 2..N
  on stock LibreOffice 7+ (whose ``--convert-to png`` filter only
  emits the first slide).  When the PNG path under-produces, the
  renderer transparently falls back to ``--convert-to pdf`` plus a
  per-page split via ``pdftoppm`` (Poppler) or ``pypdfium2``.  New
  ``strategy="auto" | "png" | "pdf"`` and ``dpi=`` knobs.
- ``SlideAnimations.add(kind, preset, shape, **kwargs)`` is now a
  documented entry point — the class was publicly exported but had
  no polymorphic ``add()`` method, leaving data-driven callers to
  build their own dispatcher.

API ergonomics
~~~~~~~~~~~~~~

- ``MotionPath.svg(slide, shape, "M 0 0 H 100 V 100", viewbox=...)``
  accepts standard SVG path syntax (M/m L/l H/h V/v C/c Q/q Z/z) and
  maps coordinates into OOXML's unit-square space.  ``MotionPath.custom``
  remains the OOXML-syntax escape hatch.
- ``kpi_slide`` delta auto-detects fraction-vs-raw: ``0.27`` →
  ``+27%``, ``14.0`` → ``+14.0`` (was silently ``+1400%``).  String
  ``delta`` and the new ``delta_text`` field pass through verbatim.
- ``quote_slide`` strips a leading hyphen / en-dash / em-dash from
  ``attribution`` so callers who already wrote ``"— Person"`` don't
  get ``"— — Person"``.
- Every recipe docstring now lists the palette / typography /
  shadow / radii slots it consumes — no more grepping the source.

Six new recipes
~~~~~~~~~~~~~~~

- ``section_divider`` — full-bleed cover with an optional eyebrow
  caption and ``progress=(3, 7)`` row of progress dots.
- ``chart_slide`` — line / line_markers / bar / column / pie /
  doughnut / area, with ``chart_palette=`` (named preset, colour
  list, or token-derived in palette priority order), plus
  ``legend=`` / ``smooth=`` / ``data_labels=`` toggles.
- ``table_slide`` — header band + banded rows; ``widths=`` (fractions
  or absolute Lengths), per-column ``aligns=``, optional
  ``totals=`` footer row.
- ``code_slide`` — monospace panel with optional Pygments syntax
  highlighting.
- ``timeline_slide`` — horizontal rail with alternating-side
  date / label pairs and ``done`` marker tinting.
- ``comparison_slide`` — matched two-column L/R rows.
- ``figure_slide`` — embed a Plotly Figure, Matplotlib Figure, SVG
  blob, HTML snippet, or image path; dispatches by type.

Lint signal-to-noise
~~~~~~~~~~~~~~~~~~~~

- Implicit name-prefix grouping: shapes named ``card.bg`` /
  ``card.label`` are auto-grouped under ``card`` so the linter
  treats the pair as one logical unit without per-shape tagging.
  ``shape.lint_group = ""`` opts a shape out of the implicit group.
- ``ShapeCollision`` ``kind="matched"`` reclassified ERROR → INFO.
  Identical bounds are almost always intentional layering (badge
  + number, button + label); the kind is preserved on the issue
  for callers who really want to filter on it.
- ``slide.lint(disable=["ShapeCollision"], min_severity="warning")``
  filters issues at the lint level rather than after the fact.
- ``auto_fix()`` now also clamps shape *size* when the shape is
  larger than the slide — translation alone could never converge,
  so the previous fixer was a silent no-op for oversize shapes.
  Multiple OffSlide issues on the same shape coalesce into one fix.
- ``SlideLintReport.fingerprints()`` returns 12-char content
  digests suitable for CI baselining — re-runs after layout
  changes only surface newly-introduced issues.

Design system
~~~~~~~~~~~~~

- ``DesignTokens.from_preset("modern_light" | "modern_dark" |
  "corporate_navy" | "vibrant")`` ships ready-to-use token sets so
  callers don't have to invent a brand from scratch.
- ``tokens.with_overrides({"palette.primary": "#FF6600",
  "typography.heading.size": Pt(40)})`` layers dotted-path tweaks
  onto a base set without forking it.
- ``kpi_slide`` and ``code_slide`` now apply ``shadows.card`` and
  ``radii.md`` via a shared ``_apply_card_styling`` helper, so the
  card-style backdrops actually reflect the design system instead
  of relying on hard-coded defaults.

compose.from_spec
~~~~~~~~~~~~~~~~~

- Recipe dispatch: layouts ``kpi`` / ``chart`` / ``table`` / ``code`` /
  ``timeline`` / ``comparison`` / ``quote`` / ``image_hero`` /
  ``section_divider`` / ``figure`` / ``title_recipe`` /
  ``bullets_recipe`` route to the matching ``recipes`` function.
  Legacy placeholder layouts (``title``, ``bullets``, ``two_column``,
  …) keep working for branded-template flows.
- ``tokens`` spec key accepts presets, YAML paths, inline dicts, or
  ``{"preset": name, "overrides": {...}}``.
- ``vars`` spec key + ``{{name}}`` interpolation across every
  string in the spec, including dotted paths into nested mappings.
  Unknown names raise rather than silently rendering as the
  literal placeholder.
- ``compose.from_yaml(path, vars={...})``: direct YAML entry point.

Figure embedding
~~~~~~~~~~~~~~~~

New ``power_pptx.design.figures`` module with optional-dep adapters:

- ``add_plotly_figure(slide, fig, ...)`` — renders via
  ``fig.to_image()`` (needs ``plotly + kaleido``); SVG when
  ``cairosvg`` is present, PNG otherwise.
- ``add_matplotlib_figure(slide, fig, ...)`` — renders via
  ``fig.savefig()`` (needs ``matplotlib``); same SVG / PNG split.
- ``add_svg_figure(slide, svg, ...)`` — wraps the existing
  ``add_svg_picture`` so every figure kind shares one entry shape.
- ``add_html_figure(slide, html, ...)`` — proxy for HTML
  embedding (PowerPoint has no native HTML surface): screenshots
  the rendered DOM via headless Chromium (needs ``playwright`` +
  ``playwright install chromium``).

Each adapter imports its dependency lazily and raises
``FigureBackendUnavailable`` (subclass of ``ImportError``) naming
the install command when the dep is missing.

Tooling
~~~~~~~

- New ``release-on-version-bump.yml`` workflow auto-creates a
  ``vX.Y.Z`` tag and a GitHub release when a merge to ``master``
  changes ``power_pptx.__version__`` to a value with no matching
  tag.  Chains into the existing ``publish.yml`` for PyPI upload.


2.2.0 (2026-04-29)
++++++++++++++++++

Two additive lint detector changes scoped from the post-2.1.1
follow-up — both signal-to-noise improvements on layered production
decks.  No behavior change for existing callers: the new
classification surfaces extra fields on existing issues, and the new
geometry mode is opt-in.

ShapeCollision now scores
~~~~~~~~~~~~~~~~~~~~~~~~~

``ShapeCollision`` issues carry a ``score: float`` in ``[0.0, 1.0]``
and a ``kind: str`` in ``{"incidental", "partial", "matched"}``,
emitted alongside the pre-existing ``intersection_area`` /
``intersection_pct`` / ``groups`` fields.

- ``incidental`` — small shape fully inside a larger one (the
  card-on-panel pattern).  Severity drops to ``INFO``.
- ``partial`` — partial overlap, neither contains the other.
  Severity stays ``WARNING``.
- ``matched`` — near-identical bbox (within 5% on each axis) and
  heavy overlap (>80%).  Severity raised to ``ERROR`` — almost
  certainly a duplicate or copy-paste bug.

The score combines containment (pulls toward incidental), size ratio
(closer to 1.0 pulls up), and overlap percentage (pulls up).
``lint_group`` suppression still runs *before* scoring — a tagged
group is intentional by definition and never scores.

The classification is also surfaced in ``report.summary()``: each
``ShapeCollision`` line now carries ``[kind=…, score=…]`` so readers
can spot the genuine bugs without re-running the detector.

Effect-bleed-aware geometry (opt-in)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``slide.lint(...)`` and ``lint_slide(slide, ...)`` accept a new
``include_effect_bleed: bool = False`` keyword argument.  When
``True``, the ``OffSlide`` and ``ShapeCollision`` detectors widen
each shape's bbox by its shadow's blur radius before checking
geometry — catching the case where a panel's raw bbox sits inside the
slide but its shadow visually bleeds past the edge.

Bleed-only triggers (where the raw bbox stays clean and only the
inflated bbox crosses the boundary) are emitted as
``OffSlideShadow`` / ``ShapeCollisionShadow`` subclasses, so callers
can opt out specifically via ``shape.lint_skip = {"OffSlideShadow"}``
without silencing real geometry warnings.

The inflation model is the simple one in this release — each side
extended by ``blur_radius / 2``.  Directional projection
(``distance × direction``) and other effects (glow, soft-edges,
reflection) are TODOs for a follow-up.  ``GraphicFrame.shadow ==
None`` (added in 2.1.1) is handled gracefully — the helper falls
back to the raw bbox.

Default behavior is unchanged; existing decks see no new warnings
unless they opt in to ``include_effect_bleed=True``.


2.1.1 (2026-04-29)
++++++++++++++++++

Bug fixes and ergonomic improvements.

OOXML correctness
~~~~~~~~~~~~~~~~~

Both items below address the "PowerPoint found a problem with content.
Repaired and removed it" prompt on open.

- ``chart.legend.position = XL_LEGEND_POSITION.RIGHT`` now writes
  ``<c:legendPos val="r"/>`` explicitly.  ``CT_LegendPos.val`` is an
  ``OptionalAttribute`` whose setter strips the attribute when the
  assigned value matches the OOXML default ("r"), producing a bare
  ``<c:legendPos/>`` element that PowerPoint's strict parser rejects.
  PowerPoint then "repairs" the chart by deleting it.  The bug only
  manifested for the default position — every other legend position
  wrote correctly because they didn't trip the strip-on-default branch.

- Fix the same "Repaired and removed it" prompt on decks that used
  ``shape.lint_group``, ``slide.lint_group(...)``, or
  ``slide.design_group(...)``.  The 2.1.0 implementation stored the
  group name as a custom-namespaced *attribute* on each shape's
  ``p:cNvPr`` element.  ``CT_NonVisualDrawingProps`` has no
  ``xsd:anyAttribute`` in the OOXML schema, so PowerPoint's strict
  validator (notably on macOS) flagged every tagged shape as malformed
  and stripped its non-visual properties on open.

  Lint metadata now lives in an ``a:extLst/a:ext`` extension element
  under ``cNvPr``, the schema-sanctioned mechanism PowerPoint preserves
  verbatim.  Decks saved with 2.1.0 are read transparently — the legacy
  attribute is migrated to the new layout the next time the value is
  written.

Ergonomic improvements
~~~~~~~~~~~~~~~~~~~~~~

- ``GraphicFrame.shadow`` now returns ``None`` (previously raised
  ``NotImplementedError``).  Probing every shape on a slide for shadow
  info no longer needs a ``try/except`` wrapper; ``if shape.shadow is
  None`` is the supported "no facade available" check.

- ``SlideLintReport.auto_fix()`` now refreshes ``report.issues`` after
  applying fixes, so the residual punch list is just ``report.issues``
  rather than a second ``slide.lint()`` call.  Skipped on
  ``dry_run=True`` (nothing changed on the slide).

- ``Chart.text_color = "#FFFFFF"`` (or ``RGBColor`` / ``(r, g, b)``
  tuple) now pins the colour across ``chart.font``,
  ``chart.legend.font`` (when present), ``chart.chart_title`` runs
  (when present), and every plot's ``data_labels.font`` (when
  enabled) — the most common copy-paste in dark-deck authoring.
  Write-only; read individual fonts directly.

- ``ShapeCollision.groups`` exposes the ``lint_group`` tag of each
  colliding shape as a ``(group_a, group_b)`` tuple.  Lets callers
  triage "intentional overlap I forgot to tag" (one or both ``None``)
  vs. "genuine layout bug" (different non-``None`` tags) at a glance
  in ``report.summary()``.

- ``shape.lint_skip = {"MinFontSize", …}`` opts an individual shape
  out of named lint checks — the natural counterpart to ``lint_group``
  for "I know this one's fine; stop warning."  Cross-shape issues
  (``ShapeCollision``, ``ZOrderAnomaly``) are only suppressed when
  *both* shapes opt out.  Persists alongside ``lint_group`` in the
  ``cNvPr/extLst/ext`` extension block.


2.1.0 (2026-04-29)
++++++++++++++++++

Feature release.  No breaking changes; everything from 2.0.0 continues
to work unchanged.  Headline additions span the linter, tables, charts,
animations, and the theme.

Lint
~~~~

- ``shape.lint_group`` / ``slide.lint_group(name, *shapes)`` /
  ``slide.design_group(name)`` context manager — the cheapest fix for
  the noisiest part of the linter.  Shapes that share a non-empty
  ``lint_group`` are allowed to overlap without producing a
  :class:`~power_pptx.lint.ShapeCollision` warning, so intentional
  layering (KPI cards, accent bars, overlaid labels) no longer drowns
  out real signal.  The tag is stored as a custom-namespaced attribute
  on ``p:cNvPr`` and round-trips through power-pptx save/load.

- Five new lint checks:

  * :class:`~power_pptx.lint.MinFontSize` — flags any text run below the
    legibility threshold (default 9pt).
  * :class:`~power_pptx.lint.OffGridDrift` — detects shapes whose left
    or top edge is slightly off a column/row grid that several other
    shapes hit cleanly.
  * :class:`~power_pptx.lint.LowContrast` — computes the WCAG contrast
    ratio between text and resolved-background fill, warns below 4.5:1.
    Resolves only solid RGB fills (theme colors and gradients are
    skipped silently, so the check is noise-free by construction).
  * :class:`~power_pptx.lint.ZOrderAnomaly` — finds filled shapes drawn
    above shapes they visually contain (the inner shape would be
    hidden at render time).
  * :class:`~power_pptx.lint.MasterPlaceholderCollision` — flags a
    non-placeholder shape sitting at exactly the position of a layout
    placeholder it should likely have inherited from instead.

- ``SlideLintReport.auto_fix()`` now also snaps ``OffGridDrift``
  offenders onto the dominant grid line — the Tier-3 auto-fix from the
  hierarchy.

Tables
~~~~~~

- ``row.borders`` / ``col.borders`` shorthand — apply ``left`` /
  ``right`` / ``top`` / ``bottom`` / ``outer`` borders to every cell in
  a row or column with a single call.  Mirrors the existing per-cell
  ``cell.borders``.

- ``Table.banded_rows`` / ``Table.banded_cols`` — friendlier aliases
  for ``horz_banding`` / ``vert_banding`` that match PowerPoint's UI
  vocabulary.

- ``Table.fit_to_box(...)`` — for runtime-driven tables: walks every
  populated cell, computes the per-cell best-fit font size against the
  cell's own width and row height (margins respected), and applies the
  smallest of those uniformly so the grid reads as one coherent size.

- ``cell.text_frame.fit_text`` now measures against the cell's own
  ``width`` / ``height`` (it was measuring against the whole table
  before, giving meaningless results).  ``_Cell.width`` / ``height``
  properties are exposed for the same reason.

Charts
~~~~~~

- ``apply_quick_layout`` accepts keyword overrides on top of named
  presets::

      chart.apply_quick_layout("title_legend_right", title_text="Q4 ARR")
      chart.apply_quick_layout(
          "title_axes_legend_bottom",
          value_axis_title_text="Revenue (£m)",
          has_major_gridlines=False,
      )

- ``Chart.color_by_category(palette)`` recolors each *data point*
  instead of each series — the helper for stacked-bar / stacked-column
  charts where you want each category segment to read as a discrete
  color.

- ``GraphicFrame.render_to_png(...)`` renders the parent slide via
  headless LibreOffice and crops to the frame's bbox, so a chart or
  table can be exported as a standalone PNG without taking the whole
  slide.  Reuses the existing :func:`~power_pptx.render.render_slide_thumbnail`
  infrastructure; requires Pillow (already a dependency) and
  ``soffice`` on PATH.

Animations
~~~~~~~~~~

- ``slide.animations.typewriter([s1, s2, s3], delay_between_ms=200)``
  one-line replacement for the manual ``with sequence(): for s ...``
  loop.  Defaults to the ``"wipe"`` preset; any entrance preset can be
  passed.

- Easing curves on :meth:`SlideAnimations.add_entrance` (and friends):
  pass ``easing="ease_in"`` / ``"ease_out"`` / ``"ease_in_out"`` /
  ``"linear"`` for a preset, or ``easing=(accel, decel)`` for an
  explicit ``<p:cTn>``-level acceleration / deceleration pair.

- ``BaseShape.delete()`` — removes the shape *and* purges any orphan
  animation entries that targeted it.  Equivalent to the manual
  ``shape._element.getparent().remove(shape._element)`` idiom but with
  the cleanup pass that the manual idiom misses.
  ``slide.animations.purge_orphans()`` is exposed publicly for callers
  that delete shapes by other means.

Theme
~~~~~

- ``Theme.apply(other, rebind_shape_colors=True, presentation=prs)`` —
  re-skinning a deck no longer leaves orphan literal colors.  Every
  shape whose hardcoded RGB matches a slot in the *old* (pre-swap)
  palette is rewritten to point at that theme slot.  Returns the
  number of color references rebound.

- ``Theme.embed_font(presentation, path, typeface=..., weight=...)`` —
  bundles a TTF/OTF into the deck under ``/ppt/fonts/`` and registers
  it in ``<p:embeddedFontLst>`` so the deck travels with its font and
  doesn't fall back to Calibri on the customer's machine.  The font is
  embedded unobfuscated (content type ``application/x-fontdata``);
  PowerPoint 2007+ accepts this form.  The fully-obfuscated form per
  ECMA-376 §15.2.13 is on the roadmap.

- ``Slide.color_variant`` — per-slide light / dark variant via
  ``<p:clrMapOvr>``.  ``slide.color_variant = "dark"`` swaps
  ``bg`` / ``tx`` mappings without changing the deck theme;
  ``"light"`` (the default) restores master inheritance.
  ``Slide.set_clr_map_override(...)`` for arbitrary attribute remappings.

Bug fixes
~~~~~~~~~

- ``power_pptx.text.layout.TextFitter`` no longer raises when text
  genuinely cannot fit at any point size; the predicate now treats
  unfittable input as "doesn't fit" so :meth:`best_fit_font_size`
  returns ``None`` cleanly.  Surfaces with ``cell.text_frame.fit_text``
  on tiny cells with very long text.

- ``tests/text/test_fonts.py`` resets the ``FontFiles`` class-level
  cache in its ``find_fixture`` so the suite is order-independent.

Tests
~~~~~

3,140 passing (up from 3,087 in 2.0.0): 53 new tests across lint,
tables, charts, animations, and theme.


2.0.0 (2026-04-29)
++++++++++++++++++

Breaking change: the importable package was renamed from ``pptx`` to
``power_pptx`` so that ``power-pptx`` and ``python-pptx`` can be
installed side-by-side without colliding on the top-level ``pptx``
module.  Update imports accordingly::

    # before (1.x)
    from pptx import Presentation
    from pptx.util import Inches

    # after (2.0+)
    from power_pptx import Presentation
    from power_pptx.util import Inches

No public API behavior changed in this release; everything that used to
live under ``pptx.*`` now lives under ``power_pptx.*`` with identical
signatures.  The PyPI distribution name (``power-pptx``) is unchanged.


1.1.0 (2026-04-28)
++++++++++++++++++

This is the inaugural release under the ``power-pptx`` distribution name
on PyPI.  It is a drop-in replacement for ``python-pptx`` 1.0.2:
``import power_pptx`` continues to work and existing user code is unaffected.
It bundles every feature from Phases 1 through 10 of the fork's roadmap —
visual effects, animations, transitions, theme reader/writer, JSON
authoring, the layout linter, design tokens and slide recipes, chart
palettes and quick layouts, slide thumbnails, and more.

The Sphinx documentation has also been rebuilt: every new module ships
with a user-guide chapter and an API-reference page, the substitution
table covers every public class added by the fork, and Read-the-Docs
builds now fail on Sphinx warnings.

The full per-phase changelog follows; the project changes summary is
collected near the end under "Project changes".

Phase 9 — design-system layer
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``power_pptx.design.tokens.DesignTokens``: source-agnostic container for
  brand tokens — ``palette`` (str → ``RGBColor``), ``typography``
  (``TypographyToken`` with ``family``/``size``/``bold``/``italic``/
  ``color``), ``radii`` and ``spacings`` (str → ``Length``), and
  ``shadows`` (``ShadowToken``).  Constructors: ``from_dict``,
  ``from_yaml`` (optional ``pyyaml``), and ``from_pptx`` (extracts
  accent palette + major/minor fonts from a deck's theme).
  ``DesignTokens.merge(other)`` layers an override token set on top of
  a base.

- ``shape.style``: token-resolving ``ShapeStyle`` facade exposed on
  every shape.  Setters fan out to the low-level proxies::

      shape.style.fill   = tokens.palette["primary"]
      shape.style.line   = tokens.palette["primary"]
      shape.style.shadow = tokens.shadows["card"]
      shape.style.font   = tokens.typography["body"]
      shape.style.text_color = tokens.palette["neutral"]

  ``ShadowToken`` assignment leaves unset fields untouched so partial
  tokens are non-destructive; ``None`` clears the corresponding effect.

- ``power_pptx.design.recipes``: opinionated parameterized slide
  constructors.  Five recipes are included — ``title_slide``,
  ``bullet_slide``, ``kpi_slide``, ``quote_slide``, and
  ``image_hero_slide`` — each taking the host ``Presentation``, the
  recipe-specific content kwargs (e.g. ``title=``, ``bullets=``,
  ``kpis=``), an optional ``DesignTokens`` for palette/typography
  resolution, and an optional ``transition=`` name.  Recipes use the
  ``Blank`` layout and place every shape themselves so the rendered
  geometry doesn't depend on the host template's master.  ``kpi_slide``
  honors ``palette["positive"]`` / ``palette["negative"]`` when
  tinting deltas (falling back to green/red), and applies
  ``tokens.shadows["card"]`` to each card when present.

- A starter pack of three example token sets — ``modern``, ``classic``,
  and ``editorial`` — lives at ``examples/starter_pack/``.  Each
  module exports both a ``SPEC`` dict (suitable for serialising) and
  a ready-to-use ``TOKENS`` (a built ``DesignTokens``).
  ``examples/starter_pack/build_preview.py`` renders a comparison
  deck per set into ``examples/starter_pack/_out/`` (gitignored).

Phase 10 — additional motion-path presets
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``power_pptx.animation.MotionPath`` gains five new convenience constructors
  alongside the existing ``line`` / ``custom``: ``diagonal``,
  ``circle`` (closed cubic-bezier loop with a ``clockwise`` flag),
  ``arc`` (quadratic-bezier hop with a configurable ``height``
  fraction), ``zigzag`` (configurable ``segments`` / ``amplitude``),
  and ``spiral`` (configurable ``turns`` and direction).  All
  normalize EMU inputs against the slide's dimensions and route
  through ``slide.animations.add_motion``, so they honor the Phase 5
  trigger model and round-trip cleanly.

Phase 10 — chart palette presets
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``Chart.apply_palette(palette)`` recolors every series in a chart
  from a named built-in preset or an iterable of color-likes,
  independently of ``chart_style``.  Series are recolored in
  declaration order; palettes wrap when the chart has more series
  than colors.

- New module ``power_pptx.chart.palettes`` exposes ``CHART_PALETTES`` (six
  built-in palettes — ``modern``, ``classic``, ``editorial``,
  ``vibrant``, ``monochrome_blue``, ``monochrome_warm``),
  ``palette_names()``, and ``resolve_palette()`` for callers that want
  to share the same color set with non-chart shapes.

- Per-series gradient and pattern fills work out of the box through
  ``chart.series[i].format.fill`` (a regular ``FillFormat``) — locked
  in with regression tests covering the four gradient kinds and
  ``MSO_PATTERN_TYPE`` patterns.

Phase 6 — theme-aware color inheritance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- New ``power_pptx.inherit.resolve_color(color_format, theme=...)`` returns
  the effective ``RGBColor`` for any ``ColorFormat`` (including the
  ``_LazyColorFormat`` proxy returned by ``Font.color`` /
  ``LineFormat.color``).  Explicit RGB colors are returned as-is,
  scheme colors resolve through ``theme.colors[…]``, and unset colors
  return ``None`` without mutating XML.  ``brightness`` is applied by
  blending the resolved RGB toward white or black, mirroring
  PowerPoint's ``lumMod`` / ``lumOff`` model.

Phase 6 — native SVG in ``add_picture``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- New ``slide.shapes.add_svg_picture(svg_file, left, top, width=None,
  height=None, *, png_fallback=None)`` embeds both an
  ``<asvg:svgBlip>`` (Office 2016+ SVG extension) and a PNG fallback
  inside the same ``<a:blip>``.  When ``png_fallback`` is omitted the
  SVG is rasterised through the optional ``cairosvg`` dependency; a
  clear ``CairoSvgUnavailable`` error guides callers to install it or
  supply their own fallback.  ``image/svg+xml`` is registered as a
  first-class image content type so SVG parts round-trip cleanly.

Phase 7 — ``power_pptx.compose`` package
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``power_pptx.compose`` is now a real package re-exporting ``from_spec``,
  ``import_slide``, and ``apply_template`` from a single import path::

      from power_pptx.compose import from_spec, import_slide, apply_template

  The implementations live in private submodules
  (``power_pptx.compose.from_spec``, ``power_pptx._slide_importer``,
  ``power_pptx._template_applier``).  Existing imports (``from power_pptx.compose
  import from_spec``) are unchanged.

Phase 10 — chart quick layouts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``Chart.apply_quick_layout(layout)`` toggles title / legend /
  axis-title / gridline visibility in opinionated combinations.  Ten
  built-in presets ship in ``power_pptx.chart.quick_layouts``
  (``title_legend_right``, ``title_legend_bottom``,
  ``title_legend_top``, ``title_legend_left``, ``title_no_legend``,
  ``no_title_no_legend``, ``title_axes_legend_right``,
  ``title_axes_legend_bottom``, ``minimal``, ``dense``); custom layouts
  can be supplied as a dict spec.

Phase 10 — slide-thumbnail renderer
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- New ``power_pptx.render`` module with
  ``render_slide_thumbnails(prs, ...)`` and
  ``render_slide_thumbnail(slide, ...)``, plus convenience methods
  ``Presentation.render_thumbnails()`` and ``Slide.render_thumbnail()``.
  Drives a headless ``soffice --headless --convert-to png`` shell-out
  to rasterise slides; supports custom binary path
  (``soffice_bin=`` or ``POWER_PPTX_SOFFICE`` env var), per-slide
  selection (``slide_indexes=``), bytes-or-paths return
  (``return_bytes=True``), custom output directory, and a configurable
  timeout.  Raises ``ThumbnailRendererUnavailable`` with an install
  hint when ``soffice`` isn't on PATH and ``ThumbnailRendererError``
  on conversion failure.

Phase 6 — text-fit estimator on Linux / minimal runtimes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``TextFrame.fit_text()`` now works on Linux and on runtimes without
  the requested font installed.  ``FontFiles._font_directories()``
  enumerates ``/usr/share/fonts``, ``/usr/local/share/fonts``,
  ``/usr/share/fonts/truetype``, ``~/.fonts``, and
  ``~/.local/share/fonts``; unrecognised platforms now return an empty
  directory list instead of raising ``OSError``.  When no matching
  system font can be located, ``_best_fit_font_size`` falls back to
  ``ImageFont.load_default(size=...)`` (Pillow ≥10.1, with a graceful
  fallback to the unsized bitmap default on older Pillow), so a call
  with no ``font_file=`` argument produces a usable estimate rather
  than a ``KeyError``.  Malformed font files encountered during the
  directory scan are skipped silently.


Phase 8 — 3D primitives and SmartArt text substitution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``shape.three_d`` accessor: ``ThreeDFormat`` facade exposing
  ``bevel_top``/``bevel_bottom`` (``_BevelFormat`` with ``preset``,
  ``width``, ``height``), ``extrusion_height``, ``extrusion_color``,
  ``contour_width``, ``contour_color``, and ``preset_material``.
  Backed by ``CT_Shape3D`` and ``CT_Scene3D`` element classes in
  ``power_pptx.oxml.dml.three_d``.  ``BevelPreset`` and ``PresetMaterial``
  enumerations added to ``power_pptx.enum.dml``.

- ``slide.smart_art``: ``SmartArtCollection`` providing indexed and
  iterable access to SmartArt graphics on a slide.  Each item is a
  ``SmartArtShape`` with:

  - ``texts`` property — ordered list of node text strings.
  - ``set_text(values, *, strict=True)`` — replaces node text in
    document order without touching layout, style, or colour parts.

  ``DiagramDataPart`` and sibling part classes registered so SmartArt
  ``diagrams/data#.xml``, ``layout#``, ``quickStyle#``, and ``colors#``
  parts are handled as typed ``XmlPart`` subclasses.


Phase 7 — slide composition
~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``Presentation.import_slide(source_slide, merge_master='dedupe'|'clone')``:
  clones a slide from any ``Presentation`` into the receiver.  Copies
  the slide part and all its dependencies (images, charts, media,
  notes, SmartArt diagram parts, …).  Master/layout/theme parts are
  either deduped against existing masters (``'dedupe'``) or always
  cloned fresh (``'clone'``).  Slide IDs and partnames are guaranteed
  collision-free.

- ``Presentation.apply_template(path_or_stream)``: re-points every
  slide's layout/master/theme at masters from a ``.potx`` or ``.pptx``
  template.  Slide content is preserved.  Layout matching: name → type
  → first layout.  Unreferenced old masters/layouts/themes are dropped
  from the saved package.


Project changes
~~~~~~~~~~~~~~~

- Renamed the PyPI distribution from ``python-pptx-next`` to
  ``power-pptx``. The importable package remains ``pptx``.
- Repository moved to ``codehalwell/power-pptx``.
- Original ``LICENSE`` (MIT, Steve Canny, 2013) preserved verbatim;
  fork copyright added on a second line per MIT requirements.
- Dropped the vestigial ``pyparsing`` line from ``requirements.txt``;
  it was not in ``pyproject.toml`` runtime deps and is not imported
  anywhere in ``src/pptx/``.
- Added Python 3.13 to the supported-versions classifier list.
- Dropped Python 3.8 (EOL October 2024). Minimum supported version is
  now 3.9, matching ``pyright``'s configured ``pythonVersion``.

Documentation
~~~~~~~~~~~~~

- Sphinx config rebuilt for ``power-pptx``: switched to the
  ``sphinx-rtd-theme``, removed dead upstream-specific hacks, refreshed
  the substitution table, and turned on ``fail_on_warning`` for
  Read-the-Docs builds.
- New user-guide chapters: visual effects, animations, slide
  transitions, layout linter, JSON authoring + cross-presentation
  composition, themes, design-system layer, advanced charts (palettes
  / quick layouts / per-series fills), and slide thumbnails.
- New API reference pages: ``power_pptx.animation``, ``power_pptx.lint``,
  ``power_pptx.compose``, ``power_pptx.theme`` (plus ``power_pptx.inherit.resolve_color``),
  ``power_pptx.design`` (tokens, style, layout, recipes), ``power_pptx.render``,
  ``power_pptx.smart_art``, plus enum pages for ``MSO_LINE_CAP_STYLE``,
  ``MSO_LINE_COMPOUND_STYLE``, ``MSO_LINE_JOIN_STYLE``,
  ``MSO_LINE_END_TYPE``, ``MSO_LINE_END_SIZE``, ``MSO_TRANSITION_TYPE``,
  and ``PP_ANIM_TRIGGER``.
- ``ShadowFormat`` and the ``DrawingML`` reference page surface the
  full Phase 3/6 effect family (``GlowFormat``, ``SoftEdgeFormat``,
  ``BlurFormat``, ``ReflectionFormat``, ``LineEndFormat``,
  ``PictureEffects``).

Deprecations (scheduled for removal in 2.0)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``ShadowFormat.inherit`` now emits a ``DeprecationWarning`` on both
  read and write. Read individual properties (``blur_radius``,
  ``distance``, ``direction``, ``color``) for ``None`` instead.  The
  ``inherit`` property is scheduled for removal in 2.0.
- ``MSO_PATTERN_TYPE.ERCENT_40`` is now an aliased member of
  ``PERCENT_40`` and emits a ``DeprecationWarning`` on access.
- ``shapes.turbo_add_enabled`` setter remains a no-op and emits a
  ``DeprecationWarning`` (shape-id allocation is now always O(1)).

New API
~~~~~~~

- Radial / rectangular / shape-path gradients (Phase 6): ``FillFormat.gradient``
  now accepts a ``kind`` argument.  ``fill.gradient(kind="radial")`` writes a
  ``<a:path path="circle"/>`` shading element; ``"rectangular"`` writes
  ``"rect"``; ``"shape"`` follows the bounding shape.  ``fill.gradient_kind``
  reports the resolved value (``"linear"``/``"radial"``/``"rectangular"``/
  ``"shape"``/``None``).  Switching kinds preserves existing gradient stops.
  ``GradientStops`` is now mutable: ``stops.append(position, color)``,
  ``stops.replace([(pos, color), ...])``, and ``del stops[i]`` (the OOXML
  2-stop minimum is enforced).  ``color`` accepts ``RGBColor``, hex strings
  (with or without leading ``#``), 3-tuples, or ``None`` (placeholder
  ``schemeClr accent1`` color).
- ``power_pptx.design.layout`` (Phase 9): build-time geometry helpers that compute
  ``Box(left, top, width, height)`` rectangles so callers don't eyeball EMUs.
  ``Grid(slide, cols=12, rows=6, gutter=Pt(12), margin=Inches(0.5))`` allocates
  rectangles via ``grid.cell(col=, row=, col_span=, row_span=)`` or applies
  them directly with ``grid.place(shape, ...)``.  ``Stack(direction="vertical"
  | "horizontal", gap=Pt(8), left=, top=, width=, height=)`` walks a running
  cursor via ``stack.next(width=, height=)`` / ``stack.place(shape, ...)``;
  ``stack.reset()`` rewinds.  Pure geometry — no XML is read or mutated until
  the caller invokes a ``place()``.
- ``MotionPath`` (Phase 5): convenience class for adding motion-path
  animations.  ``MotionPath.line(slide, shape, dx, dy)`` accepts EMU
  deltas (typically built with ``Inches(...)``/``Pt(...)``) and
  normalizes them against the slide's dimensions before emitting the
  motion-path attribute, so the *absolute* travel distance is preserved
  across slide sizes.  ``MotionPath.custom(slide, shape, path_str)``
  passes an OOXML motion-path expression through verbatim.  Both
  delegate to ``SlideAnimations.add_motion`` and inherit the trigger /
  delay / duration model from the rest of Phase 5.
- ``SlideAnimations.sequence()`` (Phase 5): context manager that
  groups the contained ``Entrance``/``Exit``/``Emphasis``/``MotionPath``
  effects into a single click-driven chain.  Inside the block, the
  first effect (whose ``trigger`` was not explicitly supplied) fires on
  ``Trigger.ON_CLICK`` (or whatever ``start=`` is passed) and every
  subsequent effect defaults to ``Trigger.AFTER_PREVIOUS``, producing
  effects that play one after another.  Explicit per-call triggers
  still override the sequence default; sequences cannot be nested.
- ``Entrance.fade(slide, text_frame, by_paragraph=True)`` (Phase 5):
  by-paragraph entrance animations.  Accepts a ``TextFrame`` or any
  shape with a ``text_frame``; emits one entrance effect per paragraph,
  each targeting ``<p:txEl>/<p:pRg st=N end=N/>`` so PowerPoint reveals
  paragraphs one at a time.  The first paragraph fires on the supplied
  trigger and subsequent paragraphs on ``Trigger.AFTER_PREVIOUS``.
  Available presets: ``appear``, ``fade``, ``wipe``, ``zoom``, ``wheel``,
  ``random_bars``.  The ``by_paragraph=`` keyword is also exposed on
  ``SlideAnimations.add_entrance`` for advanced use.
- ``Theme`` writer (Phase 7): ``prs.theme`` is now read/write.
  ``theme.colors[MSO_THEME_COLOR.ACCENT_1] = RGBColor(0xFF, 0x66, 0x00)``
  rewrites the requested ``clrScheme`` slot with a fresh ``<a:srgbClr>``;
  alias slots (``BACKGROUND_1``/``BACKGROUND_2``/``TEXT_1``/``TEXT_2``)
  resolve to their canonical ``lt1``/``lt2``/``dk1``/``dk2`` target.
  ``theme.fonts.major = "Inter"`` and ``theme.fonts.minor = "Inter"``
  rewrite the ``<a:majorFont>/<a:minorFont>/<a:latin typeface=…/>``
  typeface.  ``theme.apply(other_prs.theme)`` bulk-copies the palette
  and font pair.  ``theme.name`` is now writable.  Themes are loaded
  via a typed ``ThemePart(XmlPart)`` so writes round-trip on save.
- ``Cell.borders`` (Phase 4): per-edge line formatting on table cells.
  ``cell.borders.left``/``.right``/``.top``/``.bottom``/``.diagonal_down``/
  ``.diagonal_up`` each return a ``LineFormat``. Convenience helpers
  ``cell.borders.all(width=, color=)``, ``cell.borders.outer(...)``, and
  ``cell.borders.none()`` apply or clear border settings across multiple
  edges in one call. Backed by the OOXML ``a:lnL/lnR/lnT/lnB/lnTlToBr/
  lnBlToTr`` children of ``a:tcPr``.
- ``run.hyperlink.target_slide`` (Phase 4): assign a ``Slide`` to make
  a text run an internal hyperlink. Writes a relationship-based
  ``ppaction://hlinksldjump`` action; assigning ``None`` clears it. The
  symmetric getter resolves the relationship back to the target slide,
  mirroring ``Shape.click_action.target_slide``.
- ``ColorFormat.alpha`` (Phase 3): per-color transparency. Read/write
  float in ``[0.0, 1.0]`` (``1.0`` is fully opaque, the default; ``0.0``
  is fully transparent). Maps to the ``<a:alpha>`` child of any
  ``<a:srgbClr>``/``<a:schemeClr>``/etc. Available on the lazy proxy
  returned by ``Font.color`` and ``LineFormat.color`` with the same
  non-mutating read semantics as the rest of that proxy.
- ``LineFormat`` line-style additions (Phase 6): ``line.cap``
  (``MSO_LINE_CAP``: ``FLAT``/``ROUND``/``SQUARE``), ``line.compound``
  (``MSO_LINE_COMPOUND``: single, double, thick-thin, thin-thick,
  triple), ``line.join`` (``MSO_LINE_JOIN``: round/bevel/miter mapping
  to the ``<a:round/>``/``<a:bevel/>``/``<a:miter/>`` children), plus
  ``line.head_end`` and ``line.tail_end`` ``LineEndFormat`` proxies
  exposing ``.type`` (``MSO_LINE_END_TYPE``), ``.width`` and
  ``.length`` (``MSO_LINE_END_SIZE``). All reads are non-mutating;
  clearing the last attribute on a head/tail end drops the element so
  theme inheritance is preserved.
- ``Slide.transition`` (Phase 4): a ``SlideTransition`` proxy exposing
  ``.kind`` (``MSO_TRANSITION_TYPE``, including PowerPoint 2010+
  ``p14`` extension transitions like ``MORPH``, ``CONVEYOR``,
  ``VORTEX``), ``.duration`` (milliseconds, via ``p14:dur`` with
  fallback mapping for the legacy ``spd`` bucket), ``.advance_on_click``
  and ``.advance_after``. Reads on a slide with no explicit
  ``<p:transition>`` return ``None`` and never mutate; ``.clear()``
  removes the element entirely.
- ``Presentation.set_transition`` (Phase 4): deck-wide convenience that
  applies the same transition (or partial update) to every slide in a
  single call. Accepts ``kind``, ``duration``, ``advance_on_click``,
  and ``advance_after``; unspecified arguments are left untouched on
  each slide so callers can bump the duration without disturbing the
  kind. Passing ``kind=None`` removes the ``<p:transition>`` element
  on every slide.
- ``BaseShape.blur`` and ``BaseShape.reflection`` (Phase 3): two
  additional non-mutating effect proxies. ``shape.blur`` exposes
  ``.radius`` (EMU) and ``.grow``; ``shape.reflection`` exposes
  ``.blur_radius``, ``.distance``, ``.direction``, ``.start_alpha``,
  and ``.end_alpha``. Reads on a shape with no explicit effect return
  ``None`` and never mutate the XML; the underlying ``<a:blur>`` /
  ``<a:reflection>`` element is created on first write and dropped
  again when the last explicit attribute is cleared, preserving theme
  inheritance.
- New OOXML element classes ``CT_BlurEffect``, ``CT_InnerShadowEffect``,
  and ``CT_ReflectionEffect`` (Phase 3) registered for ``<a:blur>``,
  ``<a:innerShdw>``, and ``<a:reflection>`` so PowerPoint-authored
  effects round-trip without loss even when no high-level proxy is
  used.


1.0.2 (2024-08-07)
++++++++++++++++++

- fix: #1003 restore read-only enum members

1.0.1 (2024-08-05)
++++++++++++++++++

- fix: #1000 add py.typed


1.0.0 (2024-08-03)
++++++++++++++++++

- fix: #929 raises on JPEG with image/jpg MIME-type
- fix: #943 remove mention of a Px Length subtype
- fix: #972 next-slide-id fails in rare cases
- fix: #990 do not require strict timestamps for Zip
- Add type annotations


0.6.23 (2023-11-02)
+++++++++++++++++++

- fix: #912 Pillow<=9.5 constraint entails security vulnerability


0.6.22 (2023-08-28)
+++++++++++++++++++

- Add #909 Add imgW, imgH params to `shapes.add_ole_object()`
- fix: #754 _Relationships.items() raises
- fix: #758 quote in autoshape name must be escaped
- fix: #746 update Python 3.x support in docs
- fix: #748 setup's `license` should be short string
- fix: #762 AttributeError: module 'collections' has no attribute 'abc'
       (Windows Python 3.10+)


0.6.21 (2021-09-20)
+++++++++++++++++++

- Fix #741 _DirPkgReader must implement .__contains__()


0.6.20 (2021-09-14)
+++++++++++++++++++

- Fix #206 accommodate NULL target-references in relationships.
- Fix #223 escape image filename that appears as literal in XML.
- Fix #517 option to display chart categories/values in reverse order.
- Major refactoring of ancient package loading code.


0.6.19 (2021-05-17)
+++++++++++++++++++

- Add shapes.add_ole_object(), allowing arbitrary Excel or other binary file to be
  embedded as a shape on a slide. The OLE object is represented as an icon.


0.6.18 (2019-05-02)
+++++++++++++++++++

- .text property getters encode line-break as a vertical-tab (VT, '\v', ASCII 11/x0B).
  This is consistent with PowerPoint's copy/paste behavior and allows like-breaks (soft
  carriage-return) to be distinguished from paragraph boundary. Previously, a line-break
  was encoded as a newline ('\n') and was not distinguishable from a paragraph boundary.

  .text properties include Shape.text, _Cell.text, TextFrame.text, _Paragraph.text and
  _Run.text.

- .text property setters accept vertical-tab character and place a line-break element in
  that location. All other control characters other than horizontal-tab ('\t') and
  newline ('\n') in range \x00-\x1F are accepted and escaped with plain-text like
  "_x001B" for ESC (ASCII 27).

  Previously a control character other than tab or newline in an assigned string would
  trigger an exception related to invalid XML character.


0.6.17 (2018-12-16)
+++++++++++++++++++

- Add SlideLayouts.remove() - Delete unused slide-layout
- Add SlideLayout.used_by_slides - Get slides based on this slide-layout
- Add SlideLayouts.index() - Get index of slide-layout in master
- Add SlideLayouts.get_by_name() - Get slide-layout by its str name


0.6.16 (2018-11-09)
+++++++++++++++++++

- Feature #395 DataLabels.show_* properties, e.g. .show_percentage
- Feature #453 Chart data tolerates None for labels


0.6.15 (2018-09-24)
+++++++++++++++++++

- Fix #436 ValueAxis._cross_xAx fails on c:dateAxis


0.6.14 (2018-09-24)
+++++++++++++++++++

- Add _Cell.merge()
- Add _Cell.split()
- Add _Cell.__eq__()
- Add _Cell.is_merge_origin
- Add _Cell.is_spanned
- Add _Cell.span_height
- Add _Cell.span_width
- Add _Cell.text getter
- Add Table.iter_cells()
- Move power_pptx.shapes.table module to power_pptx.table
- Add user documentation 'Working with tables'


0.6.13 (2018-09-10)
+++++++++++++++++++

- Add Chart.font
- Fix #293 Can't hide title of single-series Chart
- Fix shape.width value is not type Emu
- Fix add a:defRPr with c:rich (fixes some font inheritance breakage)


0.6.12 (2018-08-11)
+++++++++++++++++++

- Add Picture.auto_shape_type
- Remove Python 2.6 testing from build
- Update dependencies to avoid vulnerable Pillow version
- Fix #260, #301, #382, #401
- Add _Paragraph.add_line_break()
- Add Connector.line


0.6.11 (2018-07-25)
+++++++++++++++++++

- Add gradient fill.
- Add experimental "turbo-add" option for producing large shape-count slides.


0.6.10 (2018-06-11)
+++++++++++++++++++

- Add `shape.shadow` property to autoshape, connector, picture, and group
  shape, returning a `ShadowFormat` object.
- Add `ShadowFormat` object with read/write (boolean) `.inherit` property.
- Fix #328 add support for 26+ series in a chart


0.6.9 (2018-05-08)
++++++++++++++++++

- Add `Picture.crop_x` setters, allowing picture cropping values to be set,
  in addition to interrogated.
- Add `Slide.background` and `SlideMaster.background`, allowing the
  background fill to be set for an individual slide or for all slides based
  on a slide master.
- Add option `shapes` parameter to `Shapes.add_group_shape`, allowing a group
  shape to be formed from a number of existing shapes.
- Improve efficiency of `Shapes._next_shape_id` property to improve
  performance on high shape-count slides.


0.6.8 (2018-04-18)
++++++++++++++++++

- Add `GroupShape`, providing properties specific to a group shape, including
  its `shapes` property.
- Add `GroupShapes`, providing access to shapes contained in a group shape.
- Add `SlideShapes.add_group_shape()`, allowing a group shape to be added to
  a slide.
- Add `GroupShapes.add_group_shape()`, allowing a group shape to be added to
  a group shape, enabling recursive, multi-level groups.
- Add support for adding jump-to-named-slide behavior to shape and run
  hyperlinks.


0.6.7 (2017-10-30)
++++++++++++++++++

- Add `SlideShapes.build_freeform()`, allowing freeform shapes (such as maps)
  to be specified and added to a slide.
- Add support for patterned fills.
- Add `LineFormat.dash_style` to allow interrogation and setting of dashed
  line styles.


0.6.6 (2017-06-17)
++++++++++++++++++

- Add `SlideShapes.add_movie()`, allowing video media to be added to a slide.

- fix #190 Accommodate non-conforming part names having '00' index segment.
- fix #273 Accommodate non-conforming part names having no index segment.
- fix #277 ASCII/Unicode error on non-ASCII multi-level category names
- fix #279 BaseShape.id warning appearing on placeholder access.


0.6.5 (2017-03-21)
++++++++++++++++++

- #267 compensate for non-conforming PowerPoint behavior on c:overlay element

- compensate for non-conforming (to spec) PowerPoint behavior related to
  c:dLbl/c:tx that results in "can't save" error when explicit data labels
  are added to bubbles on a bubble chart.


0.6.4 (2017-03-17)
++++++++++++++++++

- add Chart.chart_title and ChartTitle object
- #263 Use Number type to test for numeric category


0.6.3 (2017-02-28)
++++++++++++++++++

- add DataLabel.font
- add Axis.axis_title


0.6.2 (2017-01-03)
++++++++++++++++++

- add support for NotesSlide (slide notes, aka. notes page)
- add support for arbitrary series ordering in XML
- add Plot.categories providing access to hierarchical categories in an
  existing chart.
- add support for date axes on category charts, including writing a dateAx
  element for the category axis when ChartData categories are date or
  datetime.

**BACKWARD INCOMPATIBILITIES:**

Some changes were made to the boilerplate XML used to create new charts. This
was done to more closely adhere to the settings PowerPoint uses when creating
a chart using the UI. This may result in some appearance changes in charts
after upgrading. In particular:

* Chart.has_legend now defaults to True for Line charts.
* Plot.vary_by_categories now defaults to False for Line charts.


0.6.1 (2016-10-09)
++++++++++++++++++

- add Connector shape type


0.6.0 (2016-08-18)
++++++++++++++++++

- add XY chart types
- add Bubble chart types
- add Radar chart types
- add Area chart types
- add Doughnut chart types
- add Series.points and Point
- add Point.data_label
- add DataLabel.text_frame
- add DataLabel.position
- add Axis.major_gridlines
- add ChartFormat with .fill and .line
- add Axis.format (fill and line formatting)
- add ValueAxis.crosses and .crosses_at
- add Point.format (fill and line formatting)
- add Slide.slide_id
- add Slides.get() (by slide id)
- add Font.language_id
- support blank (None) data points in created charts
- add Series.marker
- add Point.marker
- add Marker.format, .style, and .size


0.5.8 (2015-11-27)
++++++++++++++++++

- add Shape.click_action (hyperlink on shape)
- fix: #128 Chart cat and ser names not escaped
- fix: #153 shapes.title raises on no title shape
- fix: #170 remove seek(0) from Image.from_file()


0.5.7 (2015-01-17)
++++++++++++++++++

- add PicturePlaceholder with .insert_picture() method
- add TablePlaceholder with .insert_table() method
- add ChartPlaceholder with .insert_chart() method
- add Picture.image property, returning Image object
- add Picture.crop_left, .crop_top, .crop_right, and .crop_bottom
- add Shape.placeholder_format and PlaceholderFormat object

**BACKWARD INCOMPATIBILITIES:**

Shape.shape_type is now unconditionally `MSO_SHAPE_TYPE.PLACEHOLDER` for all
placeholder shapes. Previously, some placeholder shapes reported
`MSO_SHAPE_TYPE.AUTO_SHAPE`, `MSO_SHAPE_TYPE.CHART`,
`MSO_SHAPE_TYPE.PICTURE`, or `MSO_SHAPE_TYPE.TABLE` for that property.


0.5.6 (2014-12-06)
++++++++++++++++++

- fix #138 - UnicodeDecodeError in setup.py on Windows 7 Python 3.4


0.5.5 (2014-11-17)
++++++++++++++++++

- feature #51 - add Python 3 support


0.5.4 (2014-11-15)
++++++++++++++++++

- feature #43 - image native size in shapes.add_picture() is now calculated
  based on DPI attribute in image file, if present, defaulting to 72 dpi.
- feature #113 - Add Paragraph.space_before, Paragraph.space_after, and
  Paragraph.line_spacing


0.5.3 (2014-11-09)
++++++++++++++++++

- add experimental feature TextFrame.fit_text()


0.5.2 (2014-10-26)
++++++++++++++++++

- fix #127 - Shape.text_frame fails on shape having no txBody


0.5.1 (2014-09-22)
++++++++++++++++++

- feature #120 - add Shape.rotation
- feature #97 - add Font.underline
- issue #117 - add BMP image support
- issue #95 - add BaseShape.name setter
- issue #107 - all .text properties should return unicode, not str
- feature #106 - add .text getters to Shape, TextFrame, and Paragraph

- Rename Shape.textframe to Shape.text_frame.
  **Shape.textframe property (by that name) is deprecated.**


0.5.0 (2014-09-13)
++++++++++++++++++

- Add support for creating and manipulating bar, column, line, and pie charts
- Major refactoring of XML layer (oxml)
- Rationalized graphical object shape access
  **Note backward incompatibilities below**

**BACKWARD INCOMPATIBILITIES:**

A table is no longer treated as a shape. Rather it is a graphical object
contained in a GraphicFrame shape, as are Chart and SmartArt objects.

Example::

    table = shapes.add_table(...)

    # becomes

    graphic_frame = shapes.add_table(...)
    table = graphic_frame.table

    # or

    table = shapes.add_table(...).table

As the enclosing shape, the id, name, shape type, position, and size are
attributes of the enclosing GraphicFrame object.

The contents of a GraphicFrame shape can be identified using three available
properties on a shape: has_table, has_chart, and has_smart_art. The enclosed
graphical object is obtained using the properties GraphicFrame.table and
GraphicFrame.chart. SmartArt is not yet supported. Accessing one of these
properties on a GraphicFrame not containing the corresponding object raises
an exception.


0.4.2 (2014-04-29)
++++++++++++++++++

- fix: issue #88 -- raises on supported image file having uppercase extension
- fix: issue #89 -- raises on add_slide() where non-contiguous existing ids


0.4.1 (2014-04-29)
++++++++++++++++++

- Rename Presentation.slidemasters to Presentation.slide_masters.
  Presentation.slidemasters property is deprecated.
- Rename Presentation.slidelayouts to Presentation.slide_layouts.
  Presentation.slidelayouts property is deprecated.
- Rename SlideMaster.slidelayouts to SlideMaster.slide_layouts.
  SlideMaster.slidelayouts property is deprecated.
- Rename SlideLayout.slidemaster to SlideLayout.slide_master.
  SlideLayout.slidemaster property is deprecated.
- Rename Slide.slidelayout to Slide.slide_layout. Slide.slidelayout property
  is deprecated.
- Add SlideMaster.shapes to access shapes on slide master.
- Add SlideMaster.placeholders to access placeholder shapes on slide master.
- Add _MasterPlaceholder class.
- Add _LayoutPlaceholder class with position and size inheritable from master
  placeholder.
- Add _SlidePlaceholder class with position and size inheritable from layout
  placeholder.
- Add Table.left, top, width, and height read/write properties.
- Add rudimentary GroupShape with left, top, width, and height properties.
- Add rudimentary Connector with left, top, width, and height properties.
- Add TextFrame.auto_size property.
- Add Presentation.slide_width and .slide_height read/write properties.
- Add LineFormat class providing access to read and change line color and
  width.
- Add AutoShape.line
- Add Picture.line

- Rationalize enumerations. **Note backward incompatibilities below**

**BACKWARD INCOMPATIBILITIES:**

The following enumerations were moved/renamed during the rationalization of
enumerations:

- ``power_pptx.enum.MSO_COLOR_TYPE`` --> ``power_pptx.enum.dml.MSO_COLOR_TYPE``
- ``power_pptx.enum.MSO_FILL`` --> ``power_pptx.enum.dml.MSO_FILL``
- ``power_pptx.enum.MSO_THEME_COLOR`` --> ``power_pptx.enum.dml.MSO_THEME_COLOR``
- ``power_pptx.constants.MSO.ANCHOR_*`` --> ``power_pptx.enum.text.MSO_ANCHOR.*``
- ``power_pptx.constants.MSO_SHAPE`` --> ``power_pptx.enum.shapes.MSO_SHAPE``
- ``power_pptx.constants.PP.ALIGN_*`` --> ``power_pptx.enum.text.PP_ALIGN.*``
- ``power_pptx.constants.MSO.{SHAPE_TYPES}`` -->
  ``power_pptx.enum.shapes.MSO_SHAPE_TYPE.*``

Documentation for all enumerations is available in the Enumerations section
of the User Guide.


0.3.2 (2014-02-07)
++++++++++++++++++

- Hotfix: issue #80 generated presentations fail to load in Keynote and other
  Apple applications


0.3.1 (2014-01-10)
++++++++++++++++++

- Hotfix: failed to load certain presentations containing images with
  uppercase extension


0.3.0 (2013-12-12)
++++++++++++++++++

- Add read/write font color property supporting RGB, theme color, and inherit
  color types
- Add font typeface and italic support
- Add text frame margins and word-wrap
- Add support for external relationships, e.g. linked spreadsheet
- Add hyperlink support for text run in shape and table cell
- Add fill color and brightness for shape and table cell, fill can also be set
  to transparent (no fill)
- Add read/write position and size properties to shape and picture
- Replace PIL dependency with Pillow
- Restructure modules to better suit size of library


0.2.6 (2013-06-22)
++++++++++++++++++

- Add read/write access to core document properties
- Hotfix to accomodate connector shapes in _AutoShapeType
- Hotfix to allow customXml parts to load when present


0.2.5 (2013-06-11)
++++++++++++++++++

- Add paragraph alignment property (left, right, centered, etc.)
- Add vertical alignment within table cell (top, middle, bottom)
- Add table cell margin properties
- Add table boolean properties: first column (row header), first row (column
  headings), last row (for e.g. totals row), last column (for e.g. row
  totals), horizontal banding, and vertical banding.
- Add support for auto shape adjustment values, e.g. change radius of corner
  rounding on rounded rectangle, position of callout arrow, etc.


0.2.4 (2013-05-16)
++++++++++++++++++

- Add support for auto shapes (e.g. polygons, flowchart symbols, etc.)


0.2.3 (2013-05-05)
++++++++++++++++++

- Add support for table shapes
- Add indentation support to textbox shapes, enabling multi-level bullets on
  bullet slides.


0.2.2 (2013-03-25)
++++++++++++++++++

- Add support for opening and saving a presentation from/to a file-like
  object.
- Refactor XML handling to use lxml objectify


0.2.1 (2013-02-25)
++++++++++++++++++

- Add support for Python 2.6
- Add images from a stream (e.g. StringIO) in addition to a path, allowing
  images retrieved from a database or network resource to be inserted without
  saving first.
- Expand text methods to accept unicode and UTF-8 encoded 8-bit strings.
- Fix potential install bug triggered by importing ``__version__`` from
  package ``__init__.py`` file.


0.2.0 (2013-02-10)
++++++++++++++++++

First non-alpha release with basic capabilities:

- open presentation/template or use built-in default template
- add slide
- set placeholder text (e.g. bullet slides)
- add picture
- add text box
