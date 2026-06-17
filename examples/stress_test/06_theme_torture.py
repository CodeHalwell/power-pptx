"""Theme torture: read every addressable slot, rewrite the whole palette and
both fonts, apply a theme from a second deck, and resolve scheme colors.
"""

from __future__ import annotations

import io

from _util import blank, deck

from power_pptx import Presentation
from power_pptx.dml.color import RGBColor
from power_pptx.enum.dml import MSO_THEME_COLOR
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.inherit import resolve_color
from power_pptx.util import Inches

SLOTS = [
    MSO_THEME_COLOR.ACCENT_1, MSO_THEME_COLOR.ACCENT_2, MSO_THEME_COLOR.ACCENT_3,
    MSO_THEME_COLOR.ACCENT_4, MSO_THEME_COLOR.ACCENT_5, MSO_THEME_COLOR.ACCENT_6,
    MSO_THEME_COLOR.BACKGROUND_1, MSO_THEME_COLOR.BACKGROUND_2,
    MSO_THEME_COLOR.TEXT_1, MSO_THEME_COLOR.TEXT_2,
    MSO_THEME_COLOR.HYPERLINK, MSO_THEME_COLOR.FOLLOWED_HYPERLINK,
]

NEW_PALETTE = {
    MSO_THEME_COLOR.ACCENT_1: RGBColor(0xFF, 0x66, 0x00),
    MSO_THEME_COLOR.ACCENT_2: RGBColor(0x12, 0x1E, 0x4D),
    MSO_THEME_COLOR.ACCENT_3: RGBColor(0x10, 0xB9, 0x81),
    MSO_THEME_COLOR.ACCENT_4: RGBColor(0xF5, 0x9E, 0x0B),
    MSO_THEME_COLOR.ACCENT_5: RGBColor(0x8B, 0x5C, 0xF6),
    MSO_THEME_COLOR.ACCENT_6: RGBColor(0xEC, 0x48, 0x99),
    MSO_THEME_COLOR.HYPERLINK: RGBColor(0x12, 0x1E, 0x4D),
}


def build():
    prs = deck()

    # --- read every slot (should not raise) ------------------------------
    s = blank(prs)
    tb = s.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(12), Inches(6.5))
    tf = tb.text_frame
    tf.word_wrap = True
    lines = []
    for slot in SLOTS:
        try:
            rgb = prs.theme.colors[slot]
            lines.append(f"{slot}: {rgb}")
        except Exception as exc:  # surface but keep going
            lines.append(f"{slot}: ERROR {exc!r}")
    lines.append(f"major font: {prs.theme.fonts.major}")
    lines.append(f"minor font: {prs.theme.fonts.minor}")
    tf.text = "\n".join(lines)

    # --- write the palette + fonts ---------------------------------------
    for slot, rgb in NEW_PALETTE.items():
        prs.theme.colors[slot] = rgb
    prs.theme.fonts.major = "Inter"
    prs.theme.fonts.minor = "Inter"
    # verify writes stuck
    assert prs.theme.colors[MSO_THEME_COLOR.ACCENT_1] == RGBColor(0xFF, 0x66, 0x00)
    assert prs.theme.fonts.major == "Inter"

    # --- shapes referencing scheme colors to exercise resolution ---------
    s = blank(prs)
    for i, slot in enumerate(SLOTS[:6]):
        card = s.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(0.6 + (i % 3) * 4.3), Inches(0.8 + (i // 3) * 3.0),
            Inches(3.8), Inches(2.4),
        )
        card.fill.solid()
        card.fill.fore_color.theme_color = slot
        card.line.fill.background()
        rgb = resolve_color(card.fill.fore_color, theme=prs.theme)
        card.text_frame.text = f"{slot}\n-> {rgb}"

    # --- apply a theme from a second in-memory deck ----------------------
    other = Presentation()
    other.theme.colors[MSO_THEME_COLOR.ACCENT_1] = RGBColor(0x00, 0x88, 0x88)
    other.theme.fonts.major = "Georgia"
    buf = io.BytesIO()
    other.save(buf)
    buf.seek(0)
    brand = Presentation(buf)
    prs.theme.apply(brand.theme)
    assert prs.theme.colors[MSO_THEME_COLOR.ACCENT_1] == RGBColor(0x00, 0x88, 0x88)

    return prs


if __name__ == "__main__":
    build().save("_out/06_theme_torture.pptx")
