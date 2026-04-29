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
