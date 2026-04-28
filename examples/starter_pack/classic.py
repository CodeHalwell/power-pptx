"""Classic — navy + warm grey, conservative typography.

Suited to board updates, financial summaries, anything where dignity
beats novelty.
"""

from __future__ import annotations

from pptx.design.tokens import DesignTokens
from pptx.util import Pt

SPEC = {
    "palette": {
        "primary":     "#0B2545",
        "neutral":     "#1F2A37",
        "muted":       "#6E6A60",
        "surface":     "#F5F1E8",
        "on_primary":  "#FBFBF8",
        "accent":      "#A98C2C",
        "positive":    "#3B6E22",
        "negative":    "#8C1C13",
    },
    "typography": {
        "heading": {"family": "Cambria", "size": Pt(34), "bold": True},
        "body":    {"family": "Calibri", "size": Pt(16)},
    },
    "radii": {
        "sm": Pt(2),
        "md": Pt(4),
        "lg": Pt(6),
    },
    "spacings": {
        "xs": Pt(4),
        "sm": Pt(8),
        "md": Pt(16),
        "lg": Pt(24),
    },
    "shadows": {
        "card": {
            "blur_radius": Pt(4),
            "distance":    Pt(1),
            "direction":   90.0,
            "color":       "#0B2545",
            "alpha":       0.10,
        },
    },
}

TOKENS = DesignTokens.from_dict(SPEC)
