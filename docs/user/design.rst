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
            "title": {"family": "Inter", "size": 44, "bold": True},
            "body":  {"family": "Inter", "size": 18},
        },
        "shadows": {
            "card": {"blur": 18, "distance": 4, "alpha": 0.18},
        },
    })

Other constructors:

* :py:meth:`DesignTokens.from_yaml('brand.yml') <power_pptx.design.tokens.DesignTokens.from_yaml>`
  — optional ``pyyaml`` dependency.
* :py:meth:`DesignTokens.from_pptx('template.pptx') <power_pptx.design.tokens.DesignTokens.from_pptx>`
  — extracts the six accent slots, ``dk1`` / ``dk2`` / ``lt1`` / ``lt2``,
  the hyperlink slots, and major/minor fonts.
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

``cols`` and ``rows`` are counts: they must be integers ``>= 1``, and a float
such as ``cols=2.5`` or a ``bool`` raises :class:`ValueError` instead of being
truncated.  A stack's ``width=`` / ``height=`` are the default size of each of
its cells, so a row of equal cards needs no per-call size, and a size given to
``next()`` / ``place()`` overrides it for that one cell::

    row = Stack(direction="horizontal", gap=Pt(12), left=Pt(48), top=Pt(400),
                width=Pt(200), height=Pt(120))
    row.place(card_a)
    row.place(card_b)
    row.place(card_c, width=Pt(320))        # this one is wider

A stack needs a width and a height from one place or the other; ``next()``
raises :class:`TypeError` naming the one that is missing.

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
rendered geometry doesn't depend on the host template's master.

Recipes that size themselves or refuse
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``table_slide``, ``code_slide``, ``timeline_slide`` and ``figure_slide`` take
content of unpredictable size, so they measure it before placing it and either
fit it on the slide (4:3 or 16:9) or raise :class:`ValueError` saying what to
change; a rejected call adds no slide to the deck.

* ``table_slide`` — ``widths`` may name fewer columns than the table has: the
  named columns keep exactly the width asked for and the rest share what
  remains (widths that leave nothing for them raise).  ``totals["values"]``
  takes at most one value fewer than there are columns, since column 0 holds
  the label.  When there are too many rows for their text the cell margins
  tighten first, then the font shrinks a point at a time (never below 9 pt);
  past that the recipe raises and says how many data rows fit, so split the
  table.  Cells are assumed to hold one line of text.
* ``code_slide`` — set in ``Consolas`` (one family name: OOXML takes no CSS
  font stack) at 14 pt, shrunk until the code, wrapped lines included, fits its
  panel (floor 9 pt, about 32 lines), otherwise it raises.  Tabs become four
  spaces, and the text colour is chosen to read on the panel.
* ``timeline_slide`` — every box stays inside the slide margins and clear of
  the rail for any number of milestones, and the deck's body size is shrunk (to
  9 pt at most) until each date and label fits its box.
* ``figure_slide`` — takes an inline SVG string or bytes as well as a path;
  the PNG companion PowerPoint requires is drawn with ``cairosvg``, and
  :class:`~power_pptx._svg.CairoSvgUnavailable` is raised without it.
  ``chart_slide`` plots categories against values (``line``, ``line_markers``,
  ``bar``, ``column``, ``pie``, ``doughnut``, ``area``); build an XY scatter
  with ``XyChartData`` instead.

Cards and ring diagrams
~~~~~~~~~~~~~~~~~~~~~~~

The shape-level cards lay their insides out from their own size and raise
:class:`ValueError`, naming the size needed, when the content cannot fit:
``add_kpi_card`` derives its value / label / delta rows from ``height`` (the
default 1.9 in matches ``kpi_slide``; below about 1.3 in the rows would hang
under the card), and ``add_article_card`` caps its type at 16 pt / 11 pt
whatever the tokens' ``heading`` / ``body`` sizes are, grows its title box for
a long title and places the blurb beneath it.

``power_pptx.diagrams.hub_and_spoke`` and ``cycle`` put their nodes on a ring
touching the edge of the box's shorter side.  The nodes keep their default size
for up to about eight of them and beyond that shrink together until no two
overlap and the arrows have room to show.  Only the overlaps they mean — each
arrow with the shapes it joins — are declared, so ``slide.lint()`` reports
nodes that really collide.

Starter pack
------------

``examples/starter_pack/`` ships three example token sets — *modern*,
*classic*, and *editorial* — each exporting both a raw ``SPEC`` dict and
a ready-to-use ``TOKENS``.  Run::

    python -m examples.starter_pack.build_preview

to render one preview deck per set under
``examples/starter_pack/_out/``.
