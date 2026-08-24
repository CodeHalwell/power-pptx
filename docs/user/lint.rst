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

The :func:`power_pptx.compose.from_spec` entry point also accepts a
deck-level ``"lint": "warn" | "raise"`` field that walks every slide
and surfaces issues for you, and any presentation — however it was
built — can be checked at save time with
:ref:`lint-on-save`.

Issue types
-----------

* :class:`power_pptx.lint.TextOverflow` — estimated text extent exceeds the
  text-frame extent.  The current implementation uses a fast
  character/line-count heuristic (default character width of
  ``0.55 × pt``, line height of ``1.2 × pt``) and respects text-frame
  margins; shapes with ``auto_size`` set to ``TEXT_TO_FIT_SHAPE`` or
  ``SHAPE_TO_FIT_TEXT`` are skipped because they cannot overflow by
  definition.
* :class:`power_pptx.lint.OffSlide` — a shape is wholly or partly outside the
  slide bounds.
* :class:`power_pptx.lint.ShapeCollision` — two shapes' bounding boxes overlap
  significantly.  See :ref:`lint-groups` for the three ways to declare that an
  overlap is intentional.
* :class:`power_pptx.lint.MinFontSize` — a text run is below the configured
  legibility threshold (default 9pt).
* :class:`power_pptx.lint.OffGridDrift` — a shape's left or top edge is
  slightly off a dominant column/row that several other shapes hit cleanly.
  Auto-fixable: :meth:`SlideLintReport.auto_fix` snaps the drifted edge onto
  the grid.
* :class:`power_pptx.lint.LowContrast` — text and resolved background fill
  have a WCAG contrast ratio below 4.5:1.  Resolves only solid RGB fills
  (theme colors and gradients are skipped silently to avoid false
  positives).
* :class:`power_pptx.lint.ZOrderAnomaly` — a filled shape is drawn above a
  shape it visually contains, hiding the inner shape at render time.
* :class:`power_pptx.lint.LayerOrderViolation` — a shape declares
  ``layer_above = "..."`` but is drawn *below* a shape in that layer, so it
  will be hidden at render time.  Severity ERROR, because the declaration
  records what the author meant and the drawing order is what failed to
  deliver it.  Auto-fixable: :meth:`SlideLintReport.auto_fix` restacks the
  declaring shape.  See :ref:`lint-groups`.
* :class:`power_pptx.lint.MasterPlaceholderCollision` — a non-placeholder
  shape sits at exactly the position of a layout placeholder it should
  likely have inherited from instead of redrawing.

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

* ``OffSlide`` — clamps the shape on-slide.  A shape larger than the
  slide is shrunk first (translation alone can never fix that), then
  nudged inside the bounds.  A shape that triggered several ``OffSlide``
  issues (left *and* right, say) is clamped once, not twice.
* ``OffGridDrift`` — snaps the drifted edge onto the dominant grid line.
* ``TextOverflow`` — flips the offending text frame to
  ``MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE`` so PowerPoint shrinks the runs at
  render time.  Non-destructive: the text is preserved verbatim, only the
  render-time sizing changes.  For a size baked into the XML before save,
  use ``text_frame.fit_text(...)`` instead, which measures with real
  Pillow font metrics.
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
move a shape by several EMU when the inferred grid is wrong.

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

All three forms are stored in the shape's ``p:cNvPr`` element — group tags
as a custom-namespaced attribute, allowances and layer names in the
``extLst`` extension point sanctioned by OOXML for exactly this.  They
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
