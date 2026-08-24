.. _compose:

Composition: from_spec, import_slide, apply_template
=====================================================

The :mod:`power_pptx.compose` package collects entry points for higher-level
authoring and cross-presentation operations.

JSON authoring
--------------

``from_spec`` is a single entry point for generator scripts (LLM or
otherwise).  The spec dict is validated for known keys and value
shapes before construction (no JSON Schema is involved)::

    from power_pptx.compose import from_spec

    prs = from_spec({
        "theme": {"palette": "modern_blue", "fonts": "inter"},
        "slides": [
            {"layout": "title", "title": "Q4 Review",
             "subtitle": "April 2026", "transition": "morph"},
            {"layout": "kpi_grid", "title": "Run-rate metrics",
             "kpis": [
                {"label": "ARR", "value": "$182M", "delta": +0.27},
                {"label": "NDR", "value": "131%",  "delta": +0.03},
             ]},
            {"layout": "bullets", "title": "Customer impact",
             "bullets": [
                "Two flagship customers shipped this week.",
                "NPS improved 8 points QoQ.",
             ]},
        ],
        "lint": "raise",
    })

Layout names map either to Phase-9 design recipes (where supplied) or to
a small built-in set of layouts using the host presentation's master.

The ``"lint"`` field accepts ``"off"`` (the default), ``"warn"``, or
``"raise"``, and acts only on error-severity issues.  Decks that were not
built from a spec get the same gate from ``prs.lint_on_save`` — see
:ref:`lint-on-save`.

.. _spec-shapes:

Free-standing shapes on a spec slide
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Layouts and recipes place their own shapes.  When you need something a
layout doesn't provide, a slide entry may carry a ``"shapes"`` list,
applied *after* the layout runs::

    prs = from_spec({
        "slides": [
            {"layout": "blank",
             "shapes": [
                {"name": "card", "shape": "rounded_rectangle",
                 "left": 1, "top": 1.4, "width": 4, "height": 2,
                 "layer": "card"},
                {"name": "badge", "shape": "oval", "text": "NEW",
                 "left": 4.4, "top": 1.0, "width": 1.2, "height": 0.8,
                 "layer_above": "card"},
             ]},
        ],
    })

Entry keys:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Key
     - Meaning
   * - ``left`` / ``top`` / ``width`` / ``height``
     - **Required.**  Plain numbers are inches (matching ``slide_size``);
       pass a :class:`~power_pptx.util.Length` such as ``Inches(1.5)`` to
       opt out.
   * - ``name``
     - The shape's name, which doubles as the handle
       ``allow_overlap_with`` resolves against.  Must be unique within
       the slide.
   * - ``shape``
     - An ``MSO_SHAPE`` member name, case- and separator-insensitive
       (``"rounded_rectangle"``, ``"Rounded Rectangle"`` and
       ``"ROUNDED-RECTANGLE"`` all land on the same member).  Defaults to
       ``"textbox"``, which adds a plain text box.
   * - ``text``
     - Text for the shape's text frame.
   * - ``lint_group`` / ``layer`` / ``layer_above`` / ``allow_overlap_with``
     - The linter's intent declarations — see below.

Unknown keys are rejected with a did-you-mean hint rather than silently
ignored, and every error names the offending entry as
``slides[i].shapes[j]``.  This is deliberately minimal — geometry, type,
text, intent.  It is not a drawing DSL; reach for the Python API when you
need fills, effects, or anything structural.

Declaring intentional overlaps in a spec
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is what makes the ``"shapes"`` list more than a convenience: a
generator — an LLM, most usefully — can declare *at generation time* that
an overlap is deliberate, so the deck it emits lints clean with no manual
tagging pass afterwards.  All three mechanisms from :ref:`lint-groups`
are spec-level fields::

    {"name": "badge", ..., "lint_group": "kpi-1"}            # n-ary tag
    {"name": "badge", ..., "allow_overlap_with": "card"}     # one pair
    {"name": "badge", ..., "allow_overlap_with": ["card", "rule"]}
    {"name": "card",  ..., "layer": "card"}                  # asserts z-order
    {"name": "badge", ..., "layer_above": "card"}

``allow_overlap_with`` names other shapes by their spec ``name``, not by
shape id — ids don't exist until the deck is built.  Resolution happens
in a second pass, after every shape on the slide exists, so a **forward
reference works**: naming a shape defined later in the same list is fine.

Names must be unique within a slide, and a reference may not cross
slides: an allowance is keyed on shape id, and ids are only unique per
slide.  Both mistakes raise :class:`ValueError` locating the bad entry.

Cross-presentation operations
-----------------------------

::

    from power_pptx import Presentation
    from power_pptx.compose import import_slide, apply_template

    src = Presentation("source.pptx")
    dst = Presentation("destination.pptx")

    # Clone a slide with its layout reference, deduping the master.
    import_slide(dst, src.slides[3], merge_master="dedupe")

    # Re-point existing slides at masters/layouts from a .potx.
    apply_template(dst, "brand-template.potx")

``merge_master="clone"`` keeps a fresh copy of the source master alongside
existing masters; ``"dedupe"`` reuses an equivalent master in the
destination when one is available.
