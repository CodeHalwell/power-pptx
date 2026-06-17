"""Effects torture: shadow, glow, soft edges, blur, reflection, alpha fills,
all four gradient kinds with mutable stops, and every line end/cap/join/compound
combination — applied across many shape geometries.
"""

from __future__ import annotations

from _util import blank, deck

from power_pptx.dml.color import RGBColor
from power_pptx.enum.dml import (
    MSO_LINE_CAP_STYLE,
    MSO_LINE_COMPOUND_STYLE,
    MSO_LINE_END_SIZE,
    MSO_LINE_END_TYPE,
    MSO_LINE_JOIN_STYLE,
)
from power_pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from power_pptx.util import Inches, Pt


def build():
    prs = deck()

    # --- Slide 1: each effect in isolation on a rounded rectangle ----------
    s = blank(prs)
    effects = ["shadow", "glow", "soft_edges", "blur", "reflection", "alpha"]
    for i, eff in enumerate(effects):
        col, row = i % 3, i // 3
        card = s.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(0.6 + col * 4.3), Inches(0.8 + row * 3.0),
            Inches(3.8), Inches(2.4),
        )
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(0x4F, 0x9D, 0xFF)
        card.line.fill.background()
        if eff == "shadow":
            card.shadow.blur_radius = Pt(18)
            card.shadow.distance = Pt(6)
            card.shadow.direction = 90.0
            card.shadow.color.rgb = RGBColor(0, 0, 0)
            card.shadow.color.alpha = 0.35
        elif eff == "glow":
            card.glow.radius = Pt(12)
            card.glow.color = RGBColor(0x4F, 0x9D, 0xFF)
        elif eff == "soft_edges":
            card.soft_edges.radius = Pt(8)
        elif eff == "blur":
            card.blur.radius = Pt(6)
            card.blur.grow = True
        elif eff == "reflection":
            card.reflection.blur_radius = Pt(2)
            card.reflection.distance = Pt(2)
            card.reflection.start_alpha = 0.6
            card.reflection.end_alpha = 0.0
        elif eff == "alpha":
            card.fill.fore_color.alpha = 0.45
        card.text_frame.text = eff

    # --- Slide 2: all four gradient kinds + mutable stops ------------------
    s = blank(prs)
    for i, kind in enumerate(["linear", "radial", "rectangular", "shape"]):
        card = s.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(0.6 + (i % 2) * 6.4), Inches(0.6 + (i // 2) * 3.4),
            Inches(6.0), Inches(3.0),
        )
        fill = card.fill
        fill.gradient(kind=kind)
        assert fill.gradient_kind == kind, (kind, fill.gradient_kind)
        stops = fill.gradient_stops
        stops.replace([
            (0.0, "#0F2D6B"),
            (0.5, RGBColor(0x4F, 0x9D, 0xFF)),
            (1.0, (255, 255, 255)),
        ])
        stops.append(0.85, "#A8C0FF")
        del stops[1]
        card.line.fill.background()
        card.text_frame.text = f"gradient: {kind}"

    # --- Slide 3: line ends, caps, joins, compound on connectors ----------
    s = blank(prs)
    ends = [MSO_LINE_END_TYPE.TRIANGLE, MSO_LINE_END_TYPE.OVAL,
            MSO_LINE_END_TYPE.STEALTH, MSO_LINE_END_TYPE.DIAMOND,
            MSO_LINE_END_TYPE.ARROW]
    for i, end in enumerate(ends):
        conn = s.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT,
            Inches(1.0), Inches(0.8 + i * 1.2),
            Inches(11.0), Inches(0.8 + i * 1.2),
        )
        line = conn.line
        line.width = Pt(3)
        line.color.rgb = RGBColor(0x1F, 0x29, 0x37)
        line.head_end.type = end
        line.head_end.width = MSO_LINE_END_SIZE.LARGE
        line.head_end.length = MSO_LINE_END_SIZE.LARGE
        line.tail_end.type = MSO_LINE_END_TYPE.OVAL
        line.cap = MSO_LINE_CAP_STYLE.ROUND

    # --- Slide 4: compound + join styles on thick-bordered shapes ---------
    s = blank(prs)
    compounds = [MSO_LINE_COMPOUND_STYLE.SINGLE, MSO_LINE_COMPOUND_STYLE.DOUBLE,
                 MSO_LINE_COMPOUND_STYLE.THICK_THIN,
                 MSO_LINE_COMPOUND_STYLE.THIN_THICK,
                 MSO_LINE_COMPOUND_STYLE.TRIPLE]
    joins = [MSO_LINE_JOIN_STYLE.ROUND, MSO_LINE_JOIN_STYLE.BEVEL,
             MSO_LINE_JOIN_STYLE.MITER]
    for i, comp in enumerate(compounds):
        card = s.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(0.6 + (i % 3) * 4.3), Inches(0.8 + (i // 3) * 3.2),
            Inches(3.8), Inches(2.6),
        )
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        card.line.color.rgb = RGBColor(0x4F, 0x9D, 0xFF)
        card.line.width = Pt(6)
        card.line.compound = comp
        card.line.join = joins[i % len(joins)]
        card.text_frame.text = str(comp)

    # --- Slide 5: read-back contract — reads must not mutate --------------
    s = blank(prs)
    probe = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(5), Inches(3),
                               Inches(3), Inches(2))
    probe.fill.solid()
    probe.fill.fore_color.rgb = RGBColor(0x10, 0xB9, 0x81)
    probe.line.fill.background()
    # reads of unset effects should be None and leave no XML
    assert probe.shadow.blur_radius is None
    assert probe.glow.radius is None
    assert probe.soft_edges.radius is None
    assert probe.reflection.blur_radius is None
    probe.text_frame.text = "read-back probe"

    return prs


if __name__ == "__main__":
    build().save("_out/01_effects_torture.pptx")
