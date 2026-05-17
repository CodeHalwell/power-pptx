"""Shared brand identity for the playground decks.

A warmer, editorial-leaning palette and a serif heading pairing so the
playground decks read differently from the cooler indigo/cyan of
``examples/showcase``.
"""

from __future__ import annotations

from power_pptx.design.tokens import DesignTokens

# Sunset-on-paper identity: warm coral primary, deep navy text, cream
# surface. Picked to look distinct from the existing showcase palette.
#
# Exported as both a raw dict (``SUNSET_DICT``) and a built ``DesignTokens``
# (``SUNSET``).  ``from_spec`` consumes the dict form (see
# ``05_from_spec_declarative.py``); the imperative recipes take the
# built object — so keeping both keeps one source of truth.
SUNSET_DICT = {
    "palette": {
        "primary":    "#E04E39",   # coral
        "accent":     "#F4B860",   # amber
        "neutral":    "#0B132B",   # near-black navy
        "muted":      "#5C677D",   # cool slate
        "surface":    "#FBF5EC",   # cream
        "background": "#FFFFFF",
        "on_primary": "#FFFFFF",
        "positive":   "#2E8B57",   # forest
        "negative":   "#C0392B",   # brick
    },
    "typography": {
        "heading": {"family": "DejaVu Serif", "size": 44.0, "bold": True},
        "body":    {"family": "DejaVu Sans",  "size": 18.0},
        "caption": {"family": "DejaVu Sans",  "size": 11.0, "italic": True},
        "mono":    {"family": "DejaVu Sans Mono", "size": 14.0},
    },
    "shadows": {
        "card": {"blur": 22.0, "distance": 6.0, "alpha": 0.16},
        "soft": {"blur": 40.0, "distance": 12.0, "alpha": 0.08},
    },
    "radii":    {"card": 16.0, "button": 8.0, "pill": 999.0},
    "spacings": {"xs": 4.0, "sm": 8.0, "md": 16.0, "lg": 32.0, "xl": 48.0},
}

SUNSET = DesignTokens.from_dict(SUNSET_DICT)

# Chart-friendly version of the palette: stays inside SUNSET's accents
# but adds enough hues for 5–6 series without losing distinguishability.
SUNSET_CHART_PALETTE = [
    "#E04E39",   # coral (primary)
    "#F4B860",   # amber
    "#2E8B57",   # forest
    "#4A7C8C",   # slate-teal
    "#9B5DE5",   # plum
    "#C0392B",   # brick
]

# A second palette used by 02_charts to A/B two looks in one deck.
MIDNIGHT_CHART_PALETTE = [
    "#0B132B",
    "#1C2541",
    "#3A506B",
    "#5BC0BE",
    "#6FFFE9",
    "#9FB7B9",
]
