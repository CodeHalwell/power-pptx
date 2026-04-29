"""Shared design tokens for the showcase decks.

Centralising the palette and typography means every showcase deck
renders against a consistent identity, and the docs / thumbnails read
as one coherent suite.
"""

from __future__ import annotations

from power_pptx.design.tokens import DesignTokens

BRAND = DesignTokens.from_dict(
    {
        "palette": {
            "primary":    "#4F46E5",   # indigo
            "accent":     "#22D3EE",   # cyan
            "neutral":    "#0F172A",   # slate-900
            "muted":      "#64748B",   # slate-500
            "surface":    "#F8FAFC",   # slate-50
            "background": "#FFFFFF",
            "on_primary": "#FFFFFF",
            "positive":   "#10B981",
            "negative":   "#EF4444",
        },
        "typography": {
            # Recipes look up keys "heading" and "body". Floats = points.
            "heading": {"family": "Inter", "size": 44.0, "bold": True},
            "body":    {"family": "Inter", "size": 18.0},
            "caption": {"family": "Inter", "size": 12.0, "italic": True},
        },
        "shadows": {
            "card": {"blur": 18.0, "distance": 4.0, "alpha": 0.18},
            "soft": {"blur": 32.0, "distance": 8.0, "alpha": 0.10},
        },
        "radii":    {"card": 14.0, "button": 8.0},
        "spacings": {"sm": 8.0, "md": 16.0, "lg": 32.0, "xl": 48.0},
    }
)

CHART_PALETTE = [
    "#4F46E5",   # primary
    "#22D3EE",   # accent
    "#10B981",   # positive
    "#F59E0B",   # amber
    "#EF4444",   # negative
    "#8B5CF6",   # violet
]
