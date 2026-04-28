"""Modern — vivid indigo + clean Inter sans, soft surface fills.

Suited to product launches, founder updates, internal tooling reviews.
"""

from __future__ import annotations

from pptx.design.tokens import DesignTokens
from pptx.util import Pt

SPEC = {
    "palette": {
        "primary":     "#3C2F80",
        "neutral":     "#1A1A2E",
        "muted":       "#6B7280",
        "surface":     "#F4F2FB",
        "on_primary":  "#FFFFFF",
        "accent":      "#FF6B35",
        "positive":    "#00853E",
        "negative":    "#B00020",
    },
    "typography": {
        "heading": {"family": "Inter", "size": Pt(40), "bold": True},
        "body":    {"family": "Inter", "size": Pt(16)},
    },
    "radii": {
        "sm": Pt(4),
        "md": Pt(8),
        "lg": Pt(16),
    },
    "spacings": {
        "xs": Pt(4),
        "sm": Pt(8),
        "md": Pt(16),
        "lg": Pt(32),
    },
    "shadows": {
        "card": {
            "blur_radius": Pt(12),
            "distance":    Pt(3),
            "direction":   90.0,
            "color":       "#1A1A2E",
            "alpha":       0.18,
        },
    },
}

TOKENS = DesignTokens.from_dict(SPEC)
