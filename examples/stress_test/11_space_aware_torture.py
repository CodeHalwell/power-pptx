"""Space-aware torture: the headline feature under stress. Huge text in tiny
boxes, multilingual + emoji + CJK + RTL strings, fit_text at extremes, every
auto_size flag, and deliberate overflow / off-slide shapes the linter must
catch (and auto_fix where it can).
"""

from __future__ import annotations

from _util import SLIDE_W, blank, deck

from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import MSO_AUTO_SIZE
from power_pptx.util import Inches

LONG = ("Quarterly business review with an unusually long headline that should "
        "be shrunk to fit by the pre-flight font measurement pass instead of "
        "overflowing the fixed container it has been placed inside of. ") * 2

MULTILINGUAL = [
    "English: The quick brown fox",
    "Español: El veloz murciélago hindú",
    "中文: 快速的棕色狐狸跳过懒狗这是一个相当长的中文字符串用来测试换行",
    "日本語: 速い茶色のキツネが怠惰な犬を飛び越えるテスト用の長い文字列",
    "العربية: الثعلب البني السريع يقفز",
    "Emoji: 🚀📊✅🔥💡🎯📈🧪🛰️🧬",
    "Math: ∑∫√∞≠≤≥±×÷∂∇ℵ",
]


def build():
    prs = deck()

    # --- Slide 1: fit_text shrinks a huge headline into a fixed box ------
    s = blank(prs)
    box = s.shapes.add_textbox(Inches(0.6), Inches(0.5), Inches(12), Inches(1.4))
    tf = box.text_frame
    tf.word_wrap = True
    tf.text = LONG
    tf.fit_text(font_family="Inter", max_size=44, bold=True)

    body = s.shapes.add_textbox(Inches(0.6), Inches(2.2), Inches(12), Inches(4.8))
    tf = body.text_frame
    tf.word_wrap = True
    tf.text = LONG * 3
    tf.fit_text(font_family="Inter", max_size=24)

    # --- Slide 2: multilingual / emoji / CJK in fitted boxes ------------
    s = blank(prs)
    for i, line in enumerate(MULTILINGUAL):
        box = s.shapes.add_textbox(Inches(0.5), Inches(0.4 + i * 0.95),
                                   Inches(12.3), Inches(0.85))
        tf = box.text_frame
        tf.word_wrap = True
        tf.text = line
        tf.fit_text(font_family="Inter", max_size=28)

    # --- Slide 3: every auto_size flag -----------------------------------
    s = blank(prs)
    flags = [MSO_AUTO_SIZE.NONE, MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE,
             MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT]
    for i, flag in enumerate(flags):
        card = s.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                  Inches(0.5 + i * 4.3), Inches(1),
                                  Inches(4), Inches(2.5))
        card.fill.solid()
        card.fill.fore_color.rgb = (0x4F, 0x9D, 0xFF)
        tf = card.text_frame
        tf.word_wrap = True
        tf.text = ("Auto-size demonstration text that is somewhat long "
                   "for the box it is in. ") * 2
        tf.auto_size = flag
        assert tf.auto_size == flag

    # --- Slide 4: tiny boxes that should overflow (linter must flag) -----
    s = blank(prs)
    for i in range(4):
        box = s.shapes.add_textbox(Inches(0.6 + i * 3.1), Inches(3),
                                   Inches(1.0), Inches(0.4))
        tf = box.text_frame
        tf.word_wrap = True
        tf.text = "This text is far too large for this tiny container"
        # intentionally NOT fitted — exercise the linter's overflow detection
        tf.auto_size = MSO_AUTO_SIZE.NONE

    # --- Slide 5: off-slide shapes that auto_fix() must nudge back -------
    s = blank(prs)
    for i in range(3):
        c = s.shapes.add_shape(MSO_SHAPE.OVAL,
                               SLIDE_W - Inches(0.4), Inches(0.5 + i * 2.0),
                               Inches(2.5), Inches(1.5))
        c.fill.solid()
        c.fill.fore_color.rgb = (0x10, 0xB9, 0x81)
        c.text_frame.text = "off right edge"
    # shape pushed off the bottom
    d = s.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                           Inches(1), Inches(7.0), Inches(3), Inches(2))
    d.fill.solid()
    d.fill.fore_color.rgb = (0xEF, 0x44, 0x44)

    return prs


if __name__ == "__main__":
    build().save("_out/11_space_aware_torture.pptx")
