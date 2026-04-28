.. _design:

Design system layer
===================

The :mod:`pptx.design` package turns the low-level API into something
where the *default* output looks good. Nothing here adds new XML — it's
all built on top of the foundations from earlier phases.

Design tokens
-------------

:class:`pptx.design.tokens.DesignTokens` is a source-agnostic container
for brand tokens — palette, typography, radii, shadows, and spacings::

    from pptx.design.tokens import DesignTokens

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

* :py:meth:`DesignTokens.from_yaml('brand.yml') <pptx.design.tokens.DesignTokens.from_yaml>`
  — optional ``pyyaml`` dependency.
* :py:meth:`DesignTokens.from_pptx('template.pptx') <pptx.design.tokens.DesignTokens.from_pptx>`
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

``pptx.design.layout`` provides build-time geometry helpers — no XML is
read or mutated until you call ``place()``::

    from pptx.design.layout import Grid, Stack
    from pptx.util import Pt

    grid = Grid(slide, cols=12, rows=6, gutter=Pt(12))
    grid.place(card1, col=0, row=0, col_span=6, row_span=4)
    grid.place(card2, col=6, row=0, col_span=6, row_span=4)

    stack = Stack(direction="vertical", gap=Pt(8),
                  left=Pt(48), top=Pt(48))
    stack.place(title,  width=Pt(600), height=Pt(64))
    stack.place(body,   width=Pt(600), height=Pt(200))

Slide recipes
-------------

``pptx.design.recipes`` ships opinionated parameterized slide
constructors.  Each takes the host |Presentation|, the recipe-specific
content kwargs, an optional |DesignTokens|, and an optional
``transition=`` name::

    from pptx.design.recipes import (
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

Starter pack
------------

``examples/starter_pack/`` ships three example token sets — *modern*,
*classic*, and *editorial* — each exporting both a raw ``SPEC`` dict and
a ready-to-use ``TOKENS``.  Run::

    python -m examples.starter_pack.build_preview

to render one preview deck per set under
``examples/starter_pack/_out/``.
