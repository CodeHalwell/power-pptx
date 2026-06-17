"""Design-system torture: DesignTokens, the ShapeStyle facade, Grid and Stack
layout primitives (dense placement), shadow tokens, and every slide recipe.
"""

from __future__ import annotations

from _util import blank, deck

from power_pptx.design.layout import Grid, Stack
from power_pptx.design.recipes import (
    bullet_slide,
    kpi_slide,
    quote_slide,
    title_slide,
)
from power_pptx.design.tokens import DesignTokens
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.util import Pt

TOKENS = DesignTokens.from_dict({
    "palette": {
        "primary": "#4F9DFF",
        "accent": "#FF6600",
        "neutral": "#1F2937",
        "muted": "#6B7280",
        "surface": "#F8FAFC",
        "background": "#FFFFFF",
        "on_primary": "#FFFFFF",
        "positive": "#10B981",
        "negative": "#EF4444",
    },
    "typography": {
        "heading": {"family": "Inter", "size": 44.0, "bold": True},
        "body": {"family": "Inter", "size": 18.0},
        "caption": {"family": "Inter", "size": 12.0, "italic": True},
    },
    "shadows": {"card": {"blur": 18.0, "distance": 4.0, "alpha": 0.18}},
    "radii": {"card": 12.0, "button": 6.0},
    "spacings": {"sm": 8.0, "md": 16.0, "lg": 32.0},
})


def build():
    prs = deck()

    # --- Grid: 12x6 dense placement of cards -----------------------------
    s = blank(prs)
    grid = Grid(s, cols=12, rows=6, gutter=Pt(10), margin=Pt(36))
    placements = [
        (0, 0, 6, 2), (6, 0, 6, 2),
        (0, 2, 4, 2), (4, 2, 4, 2), (8, 2, 4, 2),
        (0, 4, 12, 2),
    ]
    for i, (c, r, cs, rs) in enumerate(placements):
        card = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, 0, 0, Pt(10), Pt(10))
        grid.place(card, col=c, row=r, col_span=cs, row_span=rs)
        # token-resolving style facade
        card.style.fill = TOKENS.palette["primary"] if i % 2 else TOKENS.palette["surface"]
        card.style.shadow = TOKENS.shadows["card"]
        card.style.text_color = (TOKENS.palette["on_primary"]
                                 if i % 2 else TOKENS.palette["neutral"])
        card.style.font = TOKENS.typography["body"]
        card.text_frame.text = f"grid cell {i}"

    # --- Grid.cell() to compute a box without placing --------------------
    box = grid.cell(col=0, row=0, col_span=12, row_span=1)
    assert box is not None

    # --- Stack: vertical then horizontal ---------------------------------
    s = blank(prs)
    vstack = Stack(direction="vertical", gap=Pt(10),
                   left=Pt(48), top=Pt(48), width=Pt(380))
    for h, label in [(Pt(60), "title"), (Pt(28), "subtitle"), (Pt(220), "body")]:
        shp = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Pt(10), Pt(10))
        vstack.place(shp, height=h)
        shp.style.fill = TOKENS.palette["surface"]
        shp.text_frame.text = label
    vstack.reset()

    hstack = Stack(direction="horizontal", gap=Pt(12),
                   left=Pt(460), top=Pt(48), width=Pt(440))
    for label in ["one", "two", "three"]:
        shp = s.shapes.add_shape(MSO_SHAPE.OVAL, 0, 0, Pt(10), Pt(10))
        hstack.place(shp, width=Pt(130), height=Pt(130))
        shp.style.fill = TOKENS.palette["accent"]
        shp.text_frame.text = label

    # --- clear an effect via style facade --------------------------------
    s = blank(prs)
    card = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Pt(48), Pt(48),
                              Pt(300), Pt(180))
    card.style.fill = TOKENS.palette["primary"]
    card.style.shadow = TOKENS.shadows["card"]
    card.style.shadow = None  # clear
    card.text_frame.text = "shadow cleared"

    # --- Recipes (these create their own slides on prs) ------------------
    title_slide(prs, title="Design System", subtitle="Recipes pass",
                tokens=TOKENS, transition="fade")
    kpi_slide(prs, title="Run-rate metrics", kpis=[
        {"label": "ARR", "value": "$182M", "delta": +0.27},
        {"label": "NDR", "value": "131%", "delta": +0.03},
        {"label": "CAC payback", "value": "8 mo", "delta": -0.10},
    ], tokens=TOKENS)
    bullet_slide(prs, title="Customer impact", bullets=[
        "Two flagship customers shipped this week.",
        "NPS improved 8 points QoQ.",
        "EU expansion ahead of plan.",
    ], tokens=TOKENS)
    quote_slide(prs, quote="The new dashboards saved my team a week per sprint.",
                attribution="Director of Eng", tokens=TOKENS)

    return prs


if __name__ == "__main__":
    build().save("_out/09_design_system_torture.pptx")
