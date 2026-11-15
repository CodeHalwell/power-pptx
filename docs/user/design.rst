.. _design:

Design system layer
===================

The :mod:`power_pptx.design` package turns the low-level API into something
where the *default* output looks good. Nothing here adds new XML — it's
all built on top of the foundations from earlier phases.

Design tokens
-------------

:class:`power_pptx.design.tokens.DesignTokens` is a source-agnostic container
for brand tokens — palette, typography, radii, shadows, and spacings::

    from power_pptx.design.tokens import DesignTokens

    tokens = DesignTokens.from_dict({
        "palette": {
            "primary":   "#4F9DFF",
            "neutral":   "#1F2937",
            "positive":  "#10B981",
            "negative":  "#EF4444",
            "on_primary": "#FFFFFF",
        },
        "typography": {
            # Recipes look up "heading" and "body".
            "heading": {"family": "Inter", "size": 44, "bold": True},
            "body":    {"family": "Inter", "size": 18},
        },
        "shadows": {
            "card": {"blur_radius": 18, "distance": 4, "alpha": 0.18},
        },
        "radii":    {"card": 12},
        "spacings": {"sm": 8, "md": 16, "lg": 32},
    })

Length-valued fields — typography ``size``, ``radii``, ``spacings`` and a
shadow's ``blur_radius`` / ``distance`` — accept a
:class:`~power_pptx.util.Length` (``Pt(8)``, ``Emu(101600)``,
``Inches(0.1)``), which is kept exactly, or a bare number, which is read
as **points**. ``44`` and ``44.0`` mean the same thing, so a brand spec
loaded from JSON or YAML behaves like the dict above. For backward
compatibility a bare *integer* of 12700 or more (one point in EMU) is
still read as EMU, which is what every bare integer used to mean.

Token keys are checked. A typography token takes ``family`` (required),
``size``, ``bold``, ``italic`` and ``color``; a shadow token takes
``blur_radius`` (``blur`` is accepted as an alias), ``distance``,
``direction``, ``color`` and ``alpha``. Any other key raises
:class:`ValueError` with a did-you-mean hint rather than being dropped,
and the message names the token (``typography.heading.size: ...``).

Other constructors:

* :py:meth:`DesignTokens.from_yaml('brand.yml') <power_pptx.design.tokens.DesignTokens.from_yaml>`
  — optional ``pyyaml`` dependency.
* :py:meth:`DesignTokens.from_pptx('template.pptx') <power_pptx.design.tokens.DesignTokens.from_pptx>`
  — extracts the six accent slots, ``dk1`` / ``dk2`` / ``lt1`` / ``lt2``,
  the hyperlink slots, and major/minor fonts. Accepts a path (``str`` or
  :class:`pathlib.Path`), an open binary file, or a ``Presentation``.
* ``tokens.merge(other_tokens)`` layers an override set on top of a base.

Token-resolving shape style
---------------------------

Every shape exposes a :class:`.ShapeStyle` facade that fans assignments
out to the low-level proxies::

    shape.style.fill        = tokens.palette["primary"]
    shape.style.line        = tokens.palette["primary"]
    shape.style.shadow      = tokens.shadows["card"]
    shape.style.text_color  = tokens.palette["on_primary"]
    shape.style.font        = tokens.typography["body"]

Partial ``ShadowToken`` assignments leave unset fields untouched, so
overrides are non-destructive; ``shape.style.shadow = None`` clears the
effect.

Layout primitives
-----------------

``power_pptx.design.layout`` provides build-time geometry helpers — no XML is
read or mutated until you call ``place()``::

    from power_pptx.design.layout import Grid, Stack
    from power_pptx.util import Pt

    grid = Grid(slide, cols=12, rows=6, gutter=Pt(12))
    grid.place(card1, col=0, row=0, col_span=6, row_span=4)
    grid.place(card2, col=6, row=0, col_span=6, row_span=4)

    stack = Stack(direction="vertical", gap=Pt(8),
                  left=Pt(48), top=Pt(48))
    stack.place(title,  width=Pt(600), height=Pt(64))
    stack.place(body,   width=Pt(600), height=Pt(200))

Slide recipes
-------------

``power_pptx.design.recipes`` ships opinionated parameterized slide
constructors.  Each takes the host |Presentation|, the recipe-specific
content kwargs, an optional |DesignTokens|, and an optional
``transition=`` name::

    from power_pptx.design.recipes import (
        title_slide, bullet_slide, kpi_slide,
        quote_slide, image_hero_slide,
    )

    title_slide(prs, title="Q4 Review", subtitle="April 2026",
                tokens=tokens, transition="morph")
    bullet_slide(prs, title="Customer impact",
                 bullets=["Two flagship customers shipped this week.",
                          "NPS improved 8 points QoQ."],
                 tokens=tokens)
    kpi_slide(prs, title="Run-rate metrics",
              kpis=[{"label": "ARR", "value": "$182M", "delta": +0.27},
                    {"label": "NDR", "value": "131%",  "delta": +0.03}],
              tokens=tokens)

Recipes use the ``Blank`` layout and place every shape themselves so the
rendered geometry doesn't depend on the host template's master.  A
template without a layout named ``Blank`` gets the layout with the fewest
placeholders, and the placeholders it brings are removed.

The module also provides ``section_divider``, ``chart_slide``,
``table_slide``, ``code_slide``, ``timeline_slide``, ``comparison_slide``
and ``figure_slide``.  All recipes follow the same rules:

* **They fit their content.**  Where the text is known at build time,
  the fitting font size is measured and written into the slide rather
  than left to an autofit flag (which PowerPoint applies only once the
  text is edited).  Nothing is set below 9pt.
* **They fail loudly.**  Content that cannot fit at 9pt raises
  :class:`ValueError` saying how many items fit — at most 9 KPI cards on a
  10" slide (12 on 13.33"), 15 timeline milestones (21), 21 comparison
  rows, about 20 single-line table rows.  ``code_slide`` instead keeps
  the lines that fit and adds a ``… (+N more lines)`` marker; pass
  ``overflow="raise"`` to raise.
* **They validate items.**  ``kpis``, ``milestones``, comparison ``rows``
  and chart ``series`` dicts must use the documented keys; a typo raises
  with a did-you-mean hint instead of rendering a blank card.
* **Their text is readable.**  Text that would fall below 4.5:1 against
  the card, band or panel it sits on is darkened or lightened, keeping
  its hue, until it meets the ratio.

``table_slide(widths=...)`` reads bare numbers as relative weights
(``[50, 25, 25]`` and ``[0.5, 0.25, 0.25]`` are the same) and |Length|
values as exact widths.  ``code_slide`` writes a single installed
monospace family (or the ``font=`` you pass) and picks text and syntax
colours from the panel's brightness.  ``figure_slide`` keeps a figure's
aspect ratio by default (``fit="contain"``; also ``"cover"`` and
``"stretch"``) and accepts raw image bytes and binary file objects.

Starter pack
------------

``examples/starter_pack/`` ships three example token sets — *modern*,
*classic*, and *editorial* — each exporting both a raw ``SPEC`` dict and
a ready-to-use ``TOKENS``.  Run::

    python -m examples.starter_pack.build_preview

to render one preview deck per set under
``examples/starter_pack/_out/``.
