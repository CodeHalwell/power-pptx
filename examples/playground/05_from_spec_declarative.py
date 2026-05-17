"""Playground 05 — Declarative authoring with ``from_spec``.

A short five-slide deck built almost entirely from a single dict spec,
demonstrating ``power_pptx.compose.from_spec`` with built-in recipes,
deck-wide theme tokens, lint-as-spec-field, and per-slide transitions.

Companion to the imperative decks in this folder — useful to compare
"spec-driven, no Python boilerplate" against "direct shape construction".

Per the recipes' contract, this deck uses the SUNSET tokens declared in
``_brand.py``. ``from_spec`` accepts the same ``DesignTokens`` object
under ``theme.tokens``.
"""

from __future__ import annotations

from pathlib import Path

from power_pptx.compose import from_spec

from _brand import SUNSET_DICT

HERE = Path(__file__).parent

# `from_spec` reads the top-level "tokens" key and resolves it via
# `DesignTokens.from_dict`. It does NOT accept a `DesignTokens` instance
# directly (or a `theme` key — that's docs drift; see IMPROVEMENTS.md #8).
# We import the same SUNSET_DICT that ``_brand.py`` uses to build the
# ``DesignTokens`` for the imperative decks, so both paths share one
# source of truth.


SPEC = {
    "tokens": SUNSET_DICT,
    "slides": [
        {
            # The recipe-backed names are suffixed with _recipe; plain
            # "title" / "bullets" use the placeholder layouts and ignore
            # the token palette. See IMPROVEMENTS.md #9.
            "layout": "title_recipe",
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
            "layout": "bullets_recipe",
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
    # `from_spec` builds against the default 4:3 blank template — there
    # is no "slide_size" spec field. We deliberately leave this deck
    # 4:3 so the recipes' computed geometry isn't mid-air-rescaled.
    # See IMPROVEMENTS.md #10 for what happens if you resize after the
    # fact: the recipes lay out shapes against the *original* canvas
    # and the result has a wide right margin / overlapping title.
    prs = from_spec(SPEC)
    prs.save(out_path)
    return prs


if __name__ == "__main__":
    out = HERE / "_out" / "05_from_spec_declarative.pptx"
    out.parent.mkdir(exist_ok=True)
    build(out)
    print(f"wrote {out}")
