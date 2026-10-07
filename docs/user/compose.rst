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
        "tokens": {"preset": "modern_light"},
        "slides": [
            {"layout": "title", "title": "Q4 Review",
             "subtitle": "April 2026", "transition": "morph"},
            {"layout": "kpi", "title": "Run-rate metrics",
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

``"tokens"`` takes a built-in preset (``{"preset": "modern_light"}``; the
others are ``corporate_navy``, ``modern_dark`` and ``vibrant``), a YAML brand
file (``{"yaml": "brand.yml"}``), an inline token dict, or a
:class:`~power_pptx.design.tokens.DesignTokens` instance.  A preset or YAML
base takes an ``"overrides"`` mapping for per-deck tweaks and nothing else
beside it (a ``"palette"`` next to a ``"preset"`` raises instead of being
dropped), and ``"theme"`` is an alias for ``"tokens"`` with the same shapes.
Lengths in an inline dict follow the token unit rule: a float is points, a
``Pt(...)`` is taken as is, and a bare int is EMU — so a bare ``36`` for a
font size, or ``8`` for a radius, is rejected as far too small, with an error
naming the token (``tokens.typography.heading.size``).  A slide may carry its
own ``"tokens"``, which replace the deck-level ones for that slide
(``"tokens": null`` opts the slide out).

The ``"lint"`` field accepts ``"off"`` (the default), ``"warn"``, or
``"raise"``, and acts only on error-severity issues.  Decks that were not
built from a spec get the same gate from ``prs.lint_on_save`` — see
:ref:`lint-on-save`.

What ``from_spec`` validates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each slide is checked before it is built, and every failure is a
:class:`ValueError` that names the slide (``slides[3]``) or the field
(``slides[3].kpis``):

* **Unknown keys are rejected on every layout**, with a did-you-mean hint
  (``subtitlz`` suggests ``subtitle``).  That includes the placeholder
  layouts, which used to drop whatever they did not read.  Besides
  ``title``, ``transition`` and ``shapes`` they read:

  .. list-table::
     :header-rows: 1
     :widths: 35 65

     * - Layout
       - Also reads
     * - ``title``
       - ``subtitle``
     * - ``bullets``
       - ``bullets``
     * - ``section``
       - ``subtitle`` or ``text``
     * - ``two_column``, ``comparison_layout``
       - ``left`` / ``right`` (or ``content_left`` / ``content_right``)
     * - ``kpi_grid``
       - ``kpis``; the cards are at most 2.2 in wide and share the slide's
         width when there are too many for one row
     * - ``picture``
       - ``image`` (inserted into the picture placeholder) and ``caption``
     * - ``title_only``, ``blank``, ``caption``, a template's own layout name
       - nothing more

  A template's own layout name (``"Title Slide"``) fills only the title;
  the alias (``"title"``) also fills the subtitle.

* **Values must have the right shape.**  Each slide is a mapping and
  ``layout`` a string.  Text fields (``title``, ``subtitle``, ``text``,
  ``left``, ``right``, ``caption``, ``quote``, ``attribution``, ``code``,
  ``chart_type``, …) are strings; YAML reads ``subtitle: 2026`` as a number,
  so quote it.  List fields are lists of the right thing: ``kpis``,
  ``milestones``, ``series`` and the rows of a ``comparison`` are lists of
  mappings, the ``rows`` of a ``table`` are lists of lists, and ``bullets``,
  ``categories``, ``columns``, ``widths``, ``aligns`` and each series'
  ``values`` are lists.  ``image`` is a file path or a binary file,
  ``progress`` a ``[current, total]`` pair and ``totals`` a mapping.

* **null is not a value.**  An optional field given as null (YAML's
  ``bullets:`` with nothing after it) is treated as not given; a required key
  given as null (``title:``) is reported as missing.

* **A bare string is not a one-item list.**  ``bullets: "one line"`` raises
  instead of being iterated per character, as it once was.

Variables
~~~~~~~~~

``"vars"`` (and the ``vars=`` argument) fill ``{{name}}`` — or ``{{a.b}}``
into nested mappings — in every string of the spec, and an unknown name
raises :class:`KeyError`.  A slide's ``"code"`` field is the one exception:
it is shown exactly as written, so a ``code`` slide can display a Jinja,
Handlebars or Go template (``Hello {{ user.name }}!``) without it being read
as a variable.  Other fields have no escape syntax.

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
