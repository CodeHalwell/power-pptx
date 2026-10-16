"""Readable minimums and intentional line composition are distinct from basic fit."""

from pathlib import Path

import pytest

from power_pptx import Presentation
from power_pptx.text.layout import TextFitter
from power_pptx.text.measurement import measure_text
from power_pptx.util import Inches, Pt

FONT = str(Path(__file__).parents[1] / "test_files" / "calibriz.ttf")


def test_single_line_constraint_shrinks_without_changing_source_text():
    text = "A long headline for a deliberately narrow region"
    size = TextFitter.best_fit_font_size(
        text,
        (Inches(4), Inches(2)),
        48,
        FONT,
        min_size=12,
        max_lines=1,
    )
    measured = measure_text(text, Inches(4), size_pt=size, font_file=FONT)
    assert len(measured.lines) == 1
    assert 12 <= size < 48


def test_preserve_breaks_keeps_the_authored_two_line_composition():
    text = "A deliberately long first line\nA short second line"
    size = TextFitter.best_fit_font_size(
        text,
        (Inches(3), Inches(2)),
        40,
        FONT,
        preserve_breaks=True,
    )
    assert measure_text(text, Inches(3), size_pt=size, font_file=FONT).lines == tuple(
        text.splitlines()
    )


def test_failed_minimum_or_line_budget_never_changes_xml():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(1), Inches(0.25))
    box.text = "A long headline\nWith two authored lines"
    before = box.element.xml
    for options in ({"min_size": 24}, {"max_lines": 1}, {"min_size": 18, "max_lines": 2}):
        with pytest.raises(ValueError, match="fit_text"):
            box.text_frame.fit_text(max_size=32, font_file=FONT, **options)
        assert box.element.xml == before


def test_line_spacing_is_measured_and_applied():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(2))
    box.text = "One\nTwo\nThree"
    size = box.text_frame.fit_text(max_size=36, font_file=FONT, line_spacing=1.6, min_size=12)
    assert size <= 28
    assert all(p.line_spacing == pytest.approx(1.6) for p in box.text_frame.paragraphs)


@pytest.mark.parametrize(
    "options",
    [
        {"min_size": 0},
        {"min_size": 19},
        {"max_lines": 0},
        {"max_lines": 1.5},
        {"line_spacing": 0},
        {"line_spacing": float("nan")},
    ],
)
def test_invalid_constraints_fail_before_mutation(options):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    shape = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    shape.text = "Hello"
    before = shape.element.xml
    with pytest.raises(ValueError):
        shape.text_frame.fit_text(font_file=FONT, **options)
    assert shape.element.xml == before


def test_measurement_preserves_blank_and_soft_breaks():
    result = measure_text("One\v\nThree\n", Inches(5), size_pt=18, font_file=FONT)
    assert result.lines == ("One", "", "Three", "")
    assert result.height >= Pt(18 * 1.2 * 4) - 1
    assert result.used_fallback is False
