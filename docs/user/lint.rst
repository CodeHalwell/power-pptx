.. _lint:

Layout linter
=============

|pp| includes a read-only inspector that reports geometric and typographic
issues on a slide or whole deck.  It is designed for scripts that
generate slides programmatically — most usefully for LLM-driven
generators that occasionally produce overflowing text or off-slide
shapes.

Running the linter
------------------

::

    report = slide.lint()
    report.issues          # list[LintIssue]
    report.has_errors      # bool
    print(report.summary())

    deck_report = prs.lint()       # slide-by-slide

Issue types
-----------

* :class:`pptx.lint.TextOverflow` — measured text extent exceeds the
  text-frame extent.  Uses Pillow font metrics and respects margins,
  vertical anchor, line spacing, and ``auto_size``.
* :class:`pptx.lint.OffSlide` — a shape is wholly or partly outside the
  slide bounds.
* :class:`pptx.lint.ShapeCollision` — two shapes overlap and the overlap
  is not declared intentional through the relationship model below.

Declaring intentional overlaps
------------------------------

Three escape hatches keep deliberate layered designs (badges, shadows)
from tripping the collision detector:

1. **Group-implicit** — shapes inside the same ``<p:grpSp>`` cooperate.
2. **Explicit pairwise** — ``shape_a.allow_overlap_with(shape_b)``.  The
   marker is stored under a private namespace so it round-trips.
3. **Layer hints** — ``shape.layer = "badge"`` and
   ``shape.layer_above = "card"``.

Auto-fix
--------

Some issues can be repaired without designer judgment::

    fixes = report.auto_fix()              # mutates
    preview = report.auto_fix(dry_run=True)

* ``TextOverflow`` is repaired by applying autofit (``TEXT_TO_FIT_SHAPE``)
  with a configurable minimum font size; if the floor is hit the issue
  is downgraded to a warning.
* ``OffSlide`` is repaired by translating the shape inside the slide.
* ``ShapeCollision`` is reported only — auto-nudging usually breaks the
  design.

Save-time hooks
---------------

::

    prs.lint_on_save = "off"     # default; preserves drop-in compat
    prs.lint_on_save = "warn"    # log via the stdlib `logging` module
    prs.lint_on_save = "raise"   # raise LintError on save
