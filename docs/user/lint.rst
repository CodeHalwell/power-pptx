.. _lint:

Layout linter
=============

|pp| includes a read-only inspector that reports geometric and typographic
issues on a slide.  It is designed for scripts that generate slides
programmatically — most usefully for LLM-driven generators that
occasionally produce overflowing text or off-slide shapes.

Running the linter
------------------

::

    report = slide.lint()
    report.issues          # list[LintIssue]
    report.has_errors      # bool
    print(report.summary())

For a whole deck, iterate the slides yourself::

    all_issues = []
    for slide in prs.slides:
        all_issues.extend(slide.lint().issues)

or call :func:`power_pptx.audit() <power_pptx.audit.audit>`, which adds
checks the slide linter does not make — pictures that are broken or larger
than ``size_warn_bytes``, slides
with nothing but decoration on them, and fonts outside a conservative list of
commonly installed ones (each reported once per slide; theme references such
as ``+mn-lt`` count as the theme font they stand for)::

    from power_pptx import audit

    report = audit(prs)
    report.has_errors
    print(report.markdown())       # also .to_dict() and .to_json()

:func:`power_pptx.accessibility.audit_accessibility` is the same kind of
report for screen-reader problems: a picture with no alt text, or only the
file name ``add_picture`` fills in (an ERROR, placeholders included); a slide
with no title; and text whose contrast against its fill is below 4.5:1, judged
as ``LowContrast`` judges it.  Like ``slide.lint()``, neither audit changes
the deck.

The :func:`power_pptx.compose.from_spec` entry point also accepts a
deck-level ``"lint": "warn" | "raise"`` field that walks every slide
and surfaces issues for you, and any presentation — however it was
built — can be checked at save time with
:ref:`lint-on-save`.

Issue types
-----------

* :class:`power_pptx.lint.TextOverflow` — text does not fit its text frame.
  The text is laid out with the same Pillow font metrics
  :meth:`TextFrame.fit_text <power_pptx.text.text.TextFrame.fit_text>` uses:
  every run at its effective size and typeface (run, then paragraph, then the
  placeholder and master it inherits from), wrapped inside the frame's
  margins where ``fit_text`` breaks lines (at spaces, after hyphens and
  dashes, between East Asian characters, at the slashes of a long path) and
  stacked at its line and paragraph spacing.  Text in groups and
  table cells is checked too (except a cell whose text is rotated or
  stacked), and a frame ``fit_text`` has sized is never flagged.  When a typeface is not installed the engine's fallback metrics
  are used, without a warning, and the issue's ``estimated`` is ``True``.

  A fixed-size frame (``MSO_AUTO_SIZE.NONE`` or no setting) that overflows
  is an ERROR.  A frame set to ``SHAPE_TO_FIT_TEXT`` (what ``add_textbox``
  and ``add_text`` create) or ``TEXT_TO_FIT_SHAPE``, and a table row shorter
  than its text, are a WARNING: |pp| only writes the auto-size flag, so the
  stored geometry is stale, but a renderer repairs it when the deck is
  opened or the text edited.  ``ratio``, ``dimension``, ``overflow_pt`` and
  ``auto_size`` describe the overflow; for a table row, ``row`` and ``col``
  name the cell with the most text.
* :class:`power_pptx.lint.OffSlide` — a shape is wholly or partly outside the
  slide bounds.  A rotated shape is judged by the area its rotated frame
  covers, and a ``SHAPE_TO_FIT_TEXT`` shape by the box it grows into (down
  from a top anchor, up from a bottom anchor, both ways from the middle).
* :class:`power_pptx.lint.ShapeCollision` — two shapes' bounding boxes overlap
  significantly (again the rotated, grown boxes).  A connector collides only
  with what its line runs into.  See :ref:`lint-groups` for the three ways to
  declare that an overlap is intentional.
* :class:`power_pptx.lint.MinFontSize` — a text run is below the configured
  legibility threshold (default 9pt).
* :class:`power_pptx.lint.OffGridDrift` — a shape's left or top edge is
  slightly off a dominant column/row that several other shapes hit cleanly.
  A shape whose right or bottom edge sits on a grid line (bars on a shared
  baseline) is aligned there on purpose and not flagged.  Auto-fixable with
  ``auto_fix(fix_grid_drift=True)``, which snaps the drifted edge onto the
  grid.
* :class:`power_pptx.lint.LowContrast` — text and the colour painted behind
  it (the shape's own fill, a filled card drawn beneath it, or the slide's
  background) have a WCAG contrast ratio below 4.5:1.  Only an explicit RGB
  text colour on a solid RGB backdrop is judged; theme colours, gradients,
  translucent fills, pictures and partial covers are skipped rather than
  guessed at.
* :class:`power_pptx.lint.ZOrderAnomaly` — a shape with a fully opaque fill
  is drawn above a shape it visually contains, hiding the inner shape at
  render time.  A translucent fill hides nothing, and the declarations in
  :ref:`lint-groups` mark the stacking as intended.
* :class:`power_pptx.lint.LayerOrderViolation` — a shape declares
  ``layer_above = "..."`` but is drawn *below* a shape in that layer, so it
  will be hidden at render time.  Severity ERROR, because the declaration
  records what the author meant and the drawing order is what failed to
  deliver it.  Auto-fixable:
  :meth:`~power_pptx.lint.SlideLintReport.auto_fix` restacks the declaring
  shape.  See :ref:`lint-groups`.
* :class:`power_pptx.lint.MasterPlaceholderCollision` — a non-placeholder
  shape sits at exactly the position of a layout placeholder it should
  likely have inherited from instead of redrawing.
* :class:`power_pptx.lint.InvalidGeometry` — a shape's stored width or height
  is negative.  Severity ERROR: negative extents are schema-invalid, so
  PowerPoint reports the file as needing repair.  The shape is left out of
  the other geometric checks.
* :class:`power_pptx.lint.RaggedEdge` — a filled panel stops short of the
  bottom edge the panels beside it share, with nothing beneath it (side-by-side
  cards of different heights).  Severity WARNING.

``slide.lint(include_effect_bleed=True)`` also widens each shape by its
shadow's blur before the off-slide and collision checks, and reports what
only the shadow causes as ``OffSlideShadow`` and ``ShapeCollisionShadow``, so
those can be silenced separately with ``shape.lint_skip``.

Each issue carries a ``severity`` (:class:`~power_pptx.lint.LintSeverity`),
a ``code`` string, a human-readable ``message``, and a ``shapes``
tuple of the shapes it implicates.

Auto-fix
--------

Some issues can be repaired without designer judgment::

    fixes = report.auto_fix()              # mutates; returns list[str]
    preview = report.auto_fix(dry_run=True)

After a non-dry-run call, ``report.issues`` is refreshed to reflect the
post-fix state, so the residual punch list is just ``report.issues``
rather than a second ``slide.lint()`` call.

Currently auto-fixable:

* ``OffSlide`` — moves the shape so the area it covers (rotated, and grown
  to its text) is on the slide.  A shape larger than the slide is shrunk
  first (translation alone can never fix that): a picture or a group
  proportionally, so the image is not distorted and the group's members are
  not squashed; anything else along the axis that is too long.  A shape that
  triggered several ``OffSlide`` issues (left *and* right, say) is clamped
  once, not twice.
* ``OffGridDrift`` — only with ``auto_fix(fix_grid_drift=True)``: snaps the
  drifted edge onto the dominant grid line.  Off by default, as in
  :meth:`Slide.tidy <power_pptx.slide.Slide.tidy>`.
* ``TextOverflow`` — makes the text fit, the way the frame's own auto-size
  setting asks.  A frame with no setting, or ``TEXT_TO_FIT_SHAPE``, is set
  to shrink text with the font scale that fits stored on it (the values
  PowerPoint stores when it shrinks text itself — the bare flag would
  shrink nothing until the text was next edited); a ``SHAPE_TO_FIT_TEXT``
  shape is resized to its text; a frame set to ``NONE`` keeps that setting
  and has its font sizes reduced in place, as ``fit_text`` does; a table
  row is grown to its text.  The text is always preserved verbatim.  Text
  that would have to shrink below a quarter of its size is left alone and
  stays in the report.
* ``LayerOrderViolation`` — restacks the shape that declared
  ``layer_above`` so it sits immediately after the layer it named.  This
  is the one collision-adjacent fix that needs no designer judgment: the
  author already stated which shape belongs on top, and the fix only
  makes the drawing order agree.  Geometry is never touched.

Not auto-fixable:

* ``ShapeCollision`` — nudging shapes apart almost always breaks the
  design.  If the overlap is deliberate, declare it (see
  :ref:`lint-groups`) rather than moving anything.
* ``LowContrast``, ``MinFontSize``, ``ZOrderAnomaly``,
  ``MasterPlaceholderCollision`` — require designer judgment.

:meth:`Slide.tidy <power_pptx.slide.Slide.tidy>` is the one-call wrapper around lint-then-fix, with the
flags most decks want by default::

    slide.tidy()                            # the usual case
    slide.tidy(fix_grid_drift=True)         # opt into grid snapping
    slide.tidy(fix_layer_order=False)       # leave z-order alone

``fix_offslide``, ``fix_overflow`` and ``fix_layer_order`` default to
``True``; ``fix_grid_drift`` defaults to ``False``, because the snap can
pull a shape off an alignment the author meant when the inferred grid is
wrong.

``slide.lint()`` never changes the slide, and ``disable=[...]`` /
``min_severity=...`` skip the rules they exclude rather than computing and
discarding them, so they also make linting faster.

.. _lint-groups:

Declaring an intentional overlap
--------------------------------

A bare collision check is unusable on decks with intentional layering: a
KPI card with an accent bar and an overlaid badge generates a handful of
"collision" warnings every time you stamp it.  Deliberate layering looks
exactly like a copy-paste bug when all you have is a pair of bounding
boxes, so the linter has to be *told* what you meant.

There are three ways to tell it, from widest to narrowest:

.. list-table::
   :header-rows: 1
   :widths: 20 20 60

   * - Mechanism
     - Scope
     - Reach for it when
   * - ``lint_group``
     - n-ary, symmetric
     - Several shapes form one visual cluster and any of them may overlap
       any other.
   * - ``allow_overlap_with``
     - one pair
     - Exactly one overlap is meant to be legal and you want everything
       else still policed.
   * - ``layer`` / ``layer_above``
     - directional
     - The stacking *order* is part of the design and you want it
       enforced, not merely tolerated.

Groups: ``lint_group``
~~~~~~~~~~~~~~~~~~~~~~

Shapes that share the same non-empty ``lint_group`` may all overlap each
other; shapes with no group, or in different groups, still warn.  This is
the right tool for a recipe that stamps a cluster of shapes together::

    # 1. Tag directly
    card.lint_group = "kpi-card-1"

    # 2. Batch
    slide.lint_group("kpi-card-1", card, accent_bar, label_box, value_box)

    # 3. Auto-named batch — returns the generated name
    name = slide.lint_group_overlaps(card, accent_bar, label_box, value_box)

    # 4. Context manager — auto-tags every shape added in the block
    with slide.design_group("kpi-card-1"):
        slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, ...)   # card
        slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, ...)   # accent
        slide.shapes.add_textbox(...)                       # label
        slide.shapes.add_textbox(...)                       # value

The ``design_group`` form is recommended for slide-recipe helpers like
``add_kpi_card(...)``: wrap the helper body and every shape it creates
inherits the group automatically.  Nested ``design_group`` calls are
honored (innermost name wins), and an explicit ``shape.lint_group =
"..."`` inside the block is never overwritten.

A shape name with a dotted prefix is grouped implicitly, so naming shapes
``"card.bg"`` / ``"card.title"`` groups them under ``"card"`` with no
extra calls.  Set ``shape.lint_group = ""`` to opt a dotted name out.

Pairs: ``allow_overlap_with``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A group is a blunt instrument: tag four shapes and you have licensed all
six overlaps between them, including the one that really would be a bug.
An allowance licenses exactly one pair and leaves every other overlap on
the slide policed::

    from power_pptx.enum.shapes import MSO_SHAPE
    from power_pptx.util import Inches

    card = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.5),
        Inches(3.4), Inches(2.0))
    badge = slide.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(3.6), Inches(1.2), Inches(1.0), Inches(0.6))

    badge.allow_overlap_with(card)     # this pair, and only this pair

The declaration is one-sided to write but read symmetrically: it takes
only one of the pair to vouch for the overlap, so calling it on either
shape is equivalent and calling it on both is harmless.  Allowances
accumulate, so repeated calls add rather than replace::

    badge.disallow_overlap_with(card)   # revoke this pair
    badge.overlap_allowances            # frozenset[int] of shape ids
    badge.overlap_allowances = ()       # clear the lot

Revoking an allowance that was never granted is a no-op, so defensive
clearing is safe.  Note that ``disallow_overlap_with`` only clears the
record held on *this* shape — if the pair was vouched for from the other
side too, the overlap stays suppressed until that one is revoked as well.

Group members (shapes inside a ``GroupShape``) have no usable shape id and
cannot take part in a pairwise allowance; use a shared ``lint_group``
for those.

Layers: ``layer`` / ``layer_above``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Groups and allowances only ever *silence* a warning.  Layer hints are the
only form that also asserts a direction — and therefore the only one that
can fail::

    card.layer = "card"
    badge.layer_above = "card"

``badge`` now claims to be painted on top of every overlapping shape whose
``layer`` is ``"card"``.  Where the drawing order agrees, the overlap is
treated as intentional and stays out of the report.  Where it *disagrees*
— ``badge`` comes earlier in the shape tree and is therefore painted
underneath — you get a :class:`~power_pptx.lint.LayerOrderViolation` at
ERROR severity, plus the ``ShapeCollision`` that was never licensed,
because the declaration is taken as what you meant and the z-order is
reported as the bug::

    report = slide.lint()
    report.has_errors                  # True
    report.auto_fix()
    # ["Restacked 'Delta badge' above 'KPI card' to honour layer_above='card'."]

Unlike ``lint_group``, a layer name describes a stratum of the design
rather than one cluster, so any number of unrelated shapes may share it —
every card on the slide can be ``layer = "card"`` and one
``layer_above = "card"`` badge is checked against all of them.  Only
overlapping pairs are considered: a layer declaration between shapes that
never touch is inert, not wrong.  Assign ``None`` to either attribute to
clear it.

Where the declarations live
~~~~~~~~~~~~~~~~~~~~~~~~~~~

All three forms are stored under the shape's ``p:cNvPr/a:extLst/a:ext``,
the extension point OOXML sanctions for exactly this.  A custom-namespaced
*attribute* on ``cNvPr`` would violate ``CT_NonVisualDrawingProps`` — which
declares no ``xsd:anyAttribute`` — and trigger PowerPoint's "repaired and
removed" prompt on open; group tags were written that way before 2.1.1 and
are still *read* from it, but nothing writes it any more.  They
round-trip through |pp| save/load and PowerPoint leaves them alone, so
they have no visual or semantic effect on the deck; they are metadata for
the linter only.

Related but different: ``shape.lint_skip = {"MinFontSize"}`` silences a
*rule* on a shape, rather than declaring that a particular overlap was
intended.

.. _lint-on-save:

Linting on save
---------------

Every presentation carries a ``lint_on_save`` switch, whatever built it::

    prs.lint_on_save = "off"      # default — no checks, no cost
    prs.lint_on_save = "warn"     # log error-severity issues, still write
    prs.lint_on_save = "raise"    # raise LintError instead of writing

    prs.save("out.pptx")

Only **error**-severity issues count; warnings and info never trigger it.
The lint pass runs *before* anything is written, so ``"raise"`` never
leaves a bad file on disk — it raises
:class:`power_pptx.exc.LintError` naming the offending slide indexes.
``"warn"`` logs each issue through stdlib :mod:`logging` on the
``power_pptx.presentation`` logger and writes the file anyway.

The default is ``"off"`` so existing code is unaffected and pays nothing.
Any other value raises ``ValueError``.  The setting lives on the in-memory
|Presentation| object only — it is not stored in the ``.pptx`` file, so a
deck re-opened from disk starts out at ``"off"`` again.

This is the same gate as the ``"lint"`` field of
:func:`power_pptx.compose.from_spec`, available to decks that were not
built from a spec.

Recommended pattern for generators
----------------------------------

::

    prs = build_deck_from_user_input(...)

    # 1. Auto-fix what we can, slide by slide
    for slide in prs.slides:
        slide.tidy()

    # 2. Refuse to write a deck with errors left in it
    prs.lint_on_save = "raise"
    prs.save("out.pptx")           # raises LintError if anything remains

When building through :func:`power_pptx.compose.from_spec`, the
``"lint": "raise"`` field on the spec dict is the equivalent of step 2.


.. _lint-cli:

From the command line
---------------------

``power-pptx lint`` checks saved decks without any Python, which is what
a CI job needs when one step builds the decks and another has to gate
them.  It runs :meth:`Slide.lint() <power_pptx.slide.Slide.lint>` on every
slide of every deck it is given::

    power-pptx lint deck.pptx
    power-pptx lint build/*.pptx --fail-on warning

The default report is grouped by slide, with the slide's title when it has
one, and only the slides that have something to report::

    deck.pptx: 2 issues on 2 of 3 slides (1 error, 1 warning)

      Slide 1: Quarterly review
        error    OffSlide        Shape 'Runaway' extends beyond the right edge of the slide.

      Slide 3 (hidden)
        warning  ShapeCollision  Shapes 'Card A' and 'Card B' overlap (33% of ...

Hidden slides are linted like any other and marked as such.

Exit status
~~~~~~~~~~~

=====  ===================================================================
``0``  No issue at or above the ``--fail-on`` level.
``1``  At least one issue at or above the ``--fail-on`` level.
``2``  A usage error, or a deck that could not be read (or, with
       ``--fix``, written).
=====  ===================================================================

``--fail-on`` is ``error`` (the default), ``warning`` or ``never``.
Informational issues never fail a run.  A deck that cannot be read makes the
run exit ``2`` even with ``--fail-on never``; the decks that could be read
are reported all the same, and the reason goes to standard error.

``--min-severity info|warning|error`` leaves the lower issues out of the
report, and out of the exit status too.

Machine-readable reports
~~~~~~~~~~~~~~~~~~~~~~~~

``--format json`` writes one JSON document for the whole run::

    power-pptx lint deck.pptx --format json > lint.json

It holds a ``decks`` list, the total ``issue_count`` and ``counts`` by
severity, and the ``min_severity``, ``fail_on`` and ``exit_code`` of the run.
Each deck has its ``path``, its counts and a ``slides`` list in which every
entry is that slide's :meth:`SlideLintReport.to_dict()
<power_pptx.lint.SlideLintReport.to_dict>` plus ``index``, ``number``,
``title`` and ``hidden``.  A deck that could not be read is just
``{"path": ..., "error": ...}``.

``--format sarif`` writes SARIF 2.1.0, the format GitHub code scanning
uploads::

    power-pptx lint build/*.pptx --format sarif > lint.sarif

Each deck is one run, made by :func:`power_pptx.lint.lint_report_to_sarif`
and tagged with the deck's path (in ``automationDetails.id`` and
``properties.deck``) so that the runs of several decks stay apart.

Fixing as well
~~~~~~~~~~~~~~

``--fix`` applies the safe automatic fixes of :meth:`Slide.tidy()
<power_pptx.slide.Slide.tidy>` -- clamping off-slide shapes, making
overflowing text fit, restacking contradicted layers -- and then reports
what is left; the exit status is judged on that too.  It needs to be told
where to write the result (``--output PATH``, or ``-o PATH``), and never
overwrites the input unless asked to::

    power-pptx lint deck.pptx --fix --output tidied.pptx
    power-pptx lint build/*.pptx --fix --output tidied/      # a directory
    power-pptx lint deck.pptx --fix --in-place               # overwrite the deck

``--output`` names a directory when several decks are given, when it ends
with a path separator or when it is an existing directory; each deck keeps
its file name there.  An ``--output`` that would land on one of the inputs
is refused, as is a run that would write two decks of the same name to one
directory -- before any deck is opened, so nothing is half done.
``--in-place`` rewrites a deck only when a fix changed it.  A deck is written
to a temporary file and moved into place, so an existing file is never left
half-written.
