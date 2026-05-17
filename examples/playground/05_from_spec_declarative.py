"""Playground 05 — Declarative authoring with ``from_spec``.

A short five-slide deck built almost entirely from a single dict spec,
demonstrating ``power_pptx.compose.from_spec`` with built-in recipes,
deck-wide theme tokens, lint-as-spec-field, and per-slide transitions.

Companion to the imperative decks in this folder — useful to compare
"spec-driven, no Python boilerplate" against "direct shape construction".

Per the recipes' contract, this deck uses the SUNSET tokens declared in
``_brand.py``.  ``from_spec`` accepts a ``DesignTokens`` instance, an
inline dict, a preset name, or a YAML path; this script passes the
already-built ``SUNSET`` object directly (post-IMPROVEMENTS #8).
"""

from __future__ import annotations

from pathlib import Path

from power_pptx.compose import from_spec

from _brand import SUNSET

HERE = Path(__file__).parent

# Post-IMPROVEMENTS-#8, ``from_spec`` accepts an already-built
# ``DesignTokens`` under ``tokens`` (or under the legacy ``theme`` alias
# when ``tokens`` is absent).  Sharing one ``SUNSET`` between the
# imperative recipes and ``from_spec`` keeps the brand palette in one
# source of truth — no round-tripping through ``.to_dict()``.


SPEC = {
    # 16:9 widescreen — the modern default. Post-IMPROVEMENTS-#10 this
    # is a first-class spec field; previously every from_spec deck
    # rendered at the default 4:3 canvas regardless of recipe geometry.
    "slide_size": "16:9",
    "tokens": SUNSET,
    "slides": [
        {
            # Post-IMPROVEMENTS-#9, when ``tokens`` is supplied the bare
            # alias ``title`` is automatically routed to the
            # ``title_recipe`` so the deck's palette is actually used;
            # the placeholder-only legacy path is taken only when no
            # tokens are present.
            "layout": "title",
            "title": "Generated from a dict",
            "subtitle": "Five slides, no manual layout code, lint-on-save",
            "transition": "morph",
        },
        {
            "layout": "kpi",
            "title": "Why declarative",
            "kpis": [
                {"label": "LoC / slide", "value": "~12",   "delta": -0.75},
                {"label": "Time to deck", "value": "2 min", "delta": -0.90},
                {"label": "Lint fails",   "value": "0",     "delta": -1.00},
            ],
        },
        {
            # Same auto-upgrade applies to ``bullets``.
            "layout": "bullets",
            "title": "What `from_spec` ships",
            "bullets": [
                "Recipe-backed layouts: title, bullets, kpi, quote, image_hero.",
                "Token palette + typography drive every recipe.",
                "Per-slide `transition` field.",
                "`lint: \"raise\"` rejects bad output before save.",
                "Drops to imperative shape construction when needed.",
            ],
        },
        {
            "layout": "quote",
            "quote": (
                "We replaced a 1,200-line deck builder with a 40-line spec generator "
                "and our weekly review deck stopped overflowing on the third slide."
            ),
            "attribution": "Staff Engineer, internal pilot",
        },
        {
            "layout": "title_recipe",
            "title": "Drop to Python only when you must.",
            "subtitle": "The spec covers 80% of deck shapes — and `import_slide` covers the rest.",
            "transition": "fade",
        },
    ],
    "lint": "raise",
}


def build(out_path: Path):
    prs = from_spec(SPEC)
    prs.save(out_path)
    return prs


if __name__ == "__main__":
    out = HERE / "_out" / "05_from_spec_declarative.pptx"
    out.parent.mkdir(exist_ok=True)
    build(out)
    print(f"wrote {out}")
