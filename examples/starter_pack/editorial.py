"""Editorial — high-contrast charcoal with a single warm accent.

Suited to keynote-style decks where the words are doing the work and
the design needs to stay out of the way.
"""

from __future__ import annotations

from pptx.design.tokens import DesignTokens
from pptx.util import Pt

SPEC = {
    "palette": {
        "primary":     "#111111",
        "neutral":     "#222222",
        "muted":       "#999999",
        "surface":     "#FAFAFA",
        "on_primary":  "#FFFFFF",
        "accent":      "#D7263D",
        "positive":    "#1B998B",
        "negative":    "#D7263D",
    },
    "typography": {
        "heading": {"family": "Playfair Display", "size": Pt(46), "bold": True},
        "body":    {"family": "Source Sans Pro",  "size": Pt(17)},
    },
    "radii": {
        "sm": Pt(0),
        "md": Pt(0),
        "lg": Pt(0),
    },
    "spacings": {
        "xs": Pt(4),
        "sm": Pt(12),
        "md": Pt(24),
        "lg": Pt(48),
    },
    "shadows": {
        "card": {
            "blur_radius": Pt(0),
            "distance":    Pt(0),
            "direction":   90.0,
            "color":       "#111111",
            "alpha":       0.0,
        },
    },
}

TOKENS = DesignTokens.from_dict(SPEC)
