"""Unit tests for :mod:`power_pptx._textstyle`."""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx._textstyle import apply_text_style
from power_pptx.dml.color import RGBColor
from power_pptx.enum.text import MSO_VERTICAL_ANCHOR, PP_PARAGRAPH_ALIGNMENT
from power_pptx.util import Inches, Pt


@pytest.fixture
def tf():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(2))
    frame = box.text_frame
    frame.text = "Hello\nWorld"
    frame.paragraphs[1].add_run().text = " again"
    return frame


def _fonts(tf):
    return [run.font for paragraph in tf.paragraphs for run in paragraph.runs]


class DescribeApplyTextStyle:
    def it_leaves_the_formatting_alone_when_given_nothing(self, tf):
        word_wrap = tf.word_wrap

        apply_text_style(tf)

        assert tf.text == "Hello\nWorld again"
        assert tf.word_wrap is word_wrap
        assert tf.vertical_anchor is None
        assert {p.alignment for p in tf.paragraphs} == {None}
        for font in _fonts(tf):
            assert (font.name, font.size, font.bold, font.italic) == (None, None, None, None)
        # reading a run's font gives it an (empty) <a:rPr>; nothing is set on it
        assert "<a:rPr/>" in tf._txBody.xml

    def it_styles_every_run_of_every_paragraph(self, tf):
        apply_text_style(
            tf, font="Arial", size_pt=11, bold=True, italic=False, color="#1F2937"
        )

        fonts = _fonts(tf)
        assert len(fonts) == 3
        for font in fonts:
            assert (font.name, font.size, font.bold, font.italic) == ("Arial", Pt(11), True, False)
            assert font.color.rgb == RGBColor(0x1F, 0x29, 0x37)

    def it_changes_only_the_attributes_it_is_given(self, tf):
        apply_text_style(tf, font="Arial", bold=True)

        apply_text_style(tf, size_pt=Pt(9))

        for font in _fonts(tf):
            assert (font.name, font.size, font.bold, font.italic) == ("Arial", Pt(9), True, None)

    def it_sets_the_frame_options(self, tf):
        apply_text_style(tf, word_wrap=False, anchor="Bottom", align="centre")

        assert tf.word_wrap is False
        assert tf.vertical_anchor == MSO_VERTICAL_ANCHOR.BOTTOM
        assert [p.alignment for p in tf.paragraphs] == [PP_PARAGRAPH_ALIGNMENT.CENTER] * 2

    @pytest.mark.parametrize(
        ("margin", "expected"),
        [
            (4, (Pt(4), Pt(4), Pt(4), Pt(4))),
            ((1, 2, 3, Pt(4)), (Pt(1), Pt(2), Pt(3), Pt(4))),
        ],
    )
    def it_sets_the_margins_from_a_scalar_or_a_sequence(self, tf, margin, expected):
        apply_text_style(tf, margin=margin)

        assert (tf.margin_top, tf.margin_right, tf.margin_bottom, tf.margin_left) == expected

    @pytest.mark.parametrize("paragraph_defaults", [True, False])
    def it_writes_paragraph_defaults_only_when_asked(self, tf, paragraph_defaults):
        apply_text_style(
            tf, font="Arial", size_pt=12, bold=False, italic=True, color=(1, 2, 3),
            paragraph_defaults=paragraph_defaults,
        )

        for paragraph in tf.paragraphs:
            font = paragraph.font
            if paragraph_defaults:
                assert (font.name, font.size, font.bold, font.italic) == (
                    "Arial", Pt(12), False, True
                )
                assert font.color.rgb == RGBColor(1, 2, 3)
            else:
                assert (font.name, font.size, font.bold, font.italic) == (None, None, None, None)

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"align": "middle"}, "align must be one of"),
            ({"anchor": "left"}, "anchor must be one of"),
            ({"margin": (1, 2)}, "margin tuple must have 4 elements"),
            ({"color": "not-a-colour"}, "color hex string must be 6 digits"),
        ],
    )
    def it_rejects_values_it_cannot_coerce_before_touching_a_run(self, tf, kwargs, message):
        with pytest.raises(ValueError, match=message):
            apply_text_style(tf, bold=True, **kwargs)

        assert {font.bold for font in _fonts(tf)} == {None}
