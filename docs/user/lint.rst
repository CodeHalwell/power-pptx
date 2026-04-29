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
and surfaces issues for you.

Issue types
-----------

* :class:`power_pptx.lint.TextOverflow` — estimated text extent exceeds the
  text-frame extent.  The current 1.1 implementation uses a fast
  character/line-count heuristic (default character width of
  ``0.55 × pt``, line height of ``1.2 × pt``) and respects text-frame
  margins; shapes with ``auto_size`` set to ``TEXT_TO_FIT_SHAPE`` or
  ``SHAPE_TO_FIT_TEXT`` are skipped because they cannot overflow by
  definition.  A Pillow-driven measurement pass is on the roadmap.
* :class:`power_pptx.lint.OffSlide` — a shape is wholly or partly outside the
  slide bounds.
* :class:`power_pptx.lint.ShapeCollision` — two shapes' bounding boxes overlap
  significantly.

Each issue carries a ``severity`` (:class:`~power_pptx.lint.LintSeverity`),
a ``code`` string, a human-readable ``message``, and a ``shapes``
tuple of the shapes it implicates.

Auto-fix
--------

Some issues can be repaired without designer judgment::

    fixes = report.auto_fix()              # mutates; returns list[str]
    preview = report.auto_fix(dry_run=True)

Currently auto-fixable:

* ``OffSlide`` — translates the shape so it sits inside the slide
  bounds.

Not auto-fixable in 1.1:

* ``TextOverflow`` — requires designer judgment on font size vs
  content.  Use ``text_frame.fit_text(...)`` (which measures with
  Pillow font metrics and bakes a fitting size into the XML) or set
  ``text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE`` to let
  PowerPoint shrink at render time.
* ``ShapeCollision`` — auto-nudging shapes apart almost always breaks
  the design.

Recommended pattern for generators
----------------------------------

::

    from power_pptx.exc import LintError

    prs = build_deck_from_user_input(...)

    # 1. Auto-fix what we can (currently: nudge OffSlide shapes back in)
    for slide in prs.slides:
        slide.lint().auto_fix()

    # 2. Re-run and bail on any remaining errors
    remaining: list = []
    for slide in prs.slides:
        remaining.extend(
            i for i in slide.lint().issues
            if i.severity.value == "error"
        )
    if remaining:
        raise LintError("; ".join(str(i) for i in remaining))

    prs.save("out.pptx")

When building through :func:`power_pptx.compose.from_spec`, the
``"lint": "raise"`` field on the spec dict does the same thing in
fewer lines.
