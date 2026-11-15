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
        "slide_size": "16:9",
        "tokens": {"preset": "modern_light", "palette": {"primary": "#1D4ED8"}},
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

Layout names map either to a :ref:`design recipe <design>` or to one of the
host presentation's own layouts, whose placeholders are filled in:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Layout
     - Builds
   * - ``title``, ``bullets``, ``section``, ``two_column``,
       ``comparison_layout``, ``title_only``, ``blank``, ``caption``,
       ``picture``, ``kpi_grid``
     - The template's *Title Slide*, *Title and Content*, *Section Header*,
       *Two Content*, *Comparison*, *Title Only*, *Blank*, *Content with
       Caption* and *Picture with Caption* layouts (``kpi_grid`` draws KPI
       cards on *Title Only*).  ``two_column`` and ``comparison_layout``
       take ``left`` / ``right`` content, and ``comparison_layout`` also
       ``left_heading`` / ``right_heading``.  Any other layout name of the
       template is accepted too.
   * - ``title_recipe``, ``bullets_recipe``, ``kpi``, ``chart``, ``table``,
       ``code``, ``timeline``, ``comparison``, ``quote``, ``image_hero``,
       ``section_divider``, ``figure``
     - The matching function of ``power_pptx.design.recipes``
       (``kpi_slide``, ``chart_slide``, …); the slide's other keys are its
       keyword arguments.

When ``tokens`` are given, ``title`` and ``bullets`` use the token-styled
recipes. ``slide_size`` (1–56 inches per side) also rescales the
template's masters and layouts, so placeholder layouts fill the new size.

Legacy and recipe layouts both reject unknown fields with an error
naming the slide and suggesting corrections. For
example, ``subtitel`` on a ``title`` slide suggests ``subtitle`` instead
of silently losing the content. Named standard layouts such as
``Title Slide`` populate the same fields as their aliases. Slide entries
must be mappings and layout names must be strings.

Values are checked as well, so nothing is dropped or mangled: text fields
are strings; ``bullets`` is a list of strings or ``{"text": ..., "level":
n}`` mappings (the placeholder layouts indent by level, the styled recipe
draws a flat list); ``kpis``, ``milestones``, chart ``series`` and
comparison ``rows`` are lists of mappings; table ``rows`` may not be longer
than ``columns``; ``chart_palette`` must name a real palette or list
colours. A key the layout has nowhere to put — a ``title`` on a ``blank``
slide — is an error. ``null`` means "not given".

Errors
~~~~~~

Every problem with a spec's content raises
:class:`power_pptx.compose.SpecError`, a :class:`ValueError` subclass. Its
message starts with the location of the offending value and its ``path``
attribute carries that location alone, ready to hand back to the program
that wrote the spec::

    from power_pptx.compose import SpecError

    try:
        prs = from_spec(spec)
    except SpecError as exc:
        print(exc.path)  # "slides[2].kpis[0]"

Missing files, templates that are not presentations and failures inside a
recipe are reported the same way and chained from the original exception.
A missing optional dependency is still an :class:`ImportError`.

Tokens
~~~~~~

``tokens`` (or its alias ``theme``) is a preset (``{"preset":
"modern_light"}``), a YAML brand file (``{"yaml": "brand.yml"}``), inline
token sections (``palette``, ``typography``, ``radii``, ``shadows``,
``spacings``), a :class:`~power_pptx.design.tokens.DesignTokens`
instance, or a mix: the preset is the base, the YAML file is merged over
it, inline sections override individual slots and fields, and
``overrides`` (dotted paths or nested dicts) go on last. Unknown keys are
rejected. Bare numbers in length fields are points. A recipe slide may
carry its own ``tokens`` in the same forms, layered over the deck's;
``"tokens": null`` opts it out.

Variables
~~~~~~~~~

``"vars": {"company": "ACME"}`` (or ``from_spec(spec, vars=...)``) turns on
``{{company}}`` substitution in every string; ``{{a.b}}`` walks nested
mappings, and an unknown name raises :class:`~power_pptx.compose.SpecError`.
A spec without variables is left exactly as written, so code samples keep
their braces. In a spec that does use variables, write ``\{{`` for a
literal ``{{``, or set ``"interpolate": false`` on a slide (or the whole
spec) to switch substitution off there.

Specs from a model or a user
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Build a spec you did not write with ``safe=True``::

    prs = from_spec(spec, safe=True, base_dir="/srv/decks/job-42")

Every file the spec names — ``template``, a token ``yaml``, ``image``, a
``figure`` path — must then resolve inside *base_dir* (default: the
current working directory) after following symlinks, and HTML and Plotly
figures are captured with ``allow_network=False``, so a page can load only
``data:`` URLs and its own document directory. *base_dir* also resolves
relative paths when ``safe`` is off. ``from_yaml`` takes the same two
arguments.

An SVG figure is drawn for its PNG fallback without reading any file or URL
it refers to: only ``data:`` URLs are drawn, in safe mode or not.

Whatever ``safe`` is, a spec cannot choose the browser executable:
``browser_path`` in ``html_options`` / ``plotly_options`` is rejected. Set
``POWER_PPTX_CHROMIUM`` or pass ``browser_path=`` from Python instead.

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
       opt out.  Sizes cannot be negative, no value may exceed 56 inches
       (PowerPoint's limit) and non-finite numbers are rejected.
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
slide.  Both mistakes raise :class:`~power_pptx.compose.SpecError` locating
the bad entry.

Cross-presentation operations
-----------------------------

::

    from power_pptx import Presentation
    from power_pptx.compose import import_slide, apply_template

    src = Presentation("source.pptx")
    dst = Presentation("destination.pptx")

    # Clone a slide with its layout reference, deduping the master.
    new_slide = import_slide(dst, src.slides[3], merge_master="dedupe")

    # Re-point existing slides at masters/layouts from a .potx.
    apply_template(dst, "brand-template.potx")

Both take the destination presentation first and are the function forms of
:meth:`Presentation.import_slide() <power_pptx.presentation.Presentation.import_slide>`
and :meth:`Presentation.apply_template()
<power_pptx.presentation.Presentation.apply_template>`.

``merge_master="clone"`` keeps a fresh copy of the source master alongside
existing masters; ``"dedupe"`` (the default) reuses an equivalent master in
the destination when one is available.  Any other value raises
:class:`ValueError`.

Only the slide you name is imported.  A picture or media file the
destination already holds is reused rather than copied again.  A "jump to
slide" link on the imported slide (``shape.click_action.target_slide``) is
kept when its target is already in the destination — a same-deck import, or
a slide imported earlier into the same |Presentation| object — and removed
otherwise, so import a link's target before the slide that links to it.

``apply_template`` accepts the template as a path, a file-like object or an
open |Presentation|.  It copies the template's masters, layouts, themes and
their pictures into the deck and drops the old ones; |SlideMaster| and
|SlideLayout| objects fetched before the call belong to the replaced
masters, so read ``dst.slide_layouts`` again afterwards.  A template with no
slide master (or no layouts, when the deck has slides) raises
:class:`ValueError` and leaves the deck untouched.
