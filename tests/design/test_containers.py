"""Containment, fitting, extension, and preflight guarantees for native layouts."""

from io import BytesIO
from pathlib import Path

import pytest

from power_pptx import BBox, Presentation
from power_pptx.design import (
    Badge,
    Card,
    Column,
    LayoutOverflowError,
    MetricTile,
    NativeContent,
    Row,
    TextBlock,
)
from power_pptx.design.tokens import DesignTokens
from power_pptx.util import Inches, Pt
from power_pptx.validation import validate_presentation

FONT = str(Path(__file__).parents[1] / "test_files" / "calibriz.ttf")


def label(value, **kwargs):
    return TextBlock(value, font_file=FONT, **kwargs)


@pytest.fixture
def slide():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    return prs.slides.add_slide(prs.slide_layouts[6])


def test_nested_cards_keep_text_editable_and_in_padded_regions(slide):
    tree = Row(
        [
            Card(
                [label("Headline", name="headline", bold=True), label("A short explanation")],
                name="card",
                padding=Pt(20),
            ),
            Card([label("Another idea"), label("Second explanation")]),
        ],
        gap=Pt(24),
    )
    box = BBox.from_inches(0.5, 1, 12, 3)
    result = tree.render(slide, box, strict_fonts=True)
    card, headline = result["card"], result["headline"]
    assert headline.left == card.left + Pt(20)
    assert headline.top == card.top + Pt(20)
    for shape in result.shapes:
        assert shape.left >= box.left
        assert shape.top >= box.top
        assert shape.left + shape.width <= box.right
        assert shape.top + shape.height <= box.bottom
    assert not [i for i in slide.lint().issues if i.severity.value == "error"]
    assert len(result.shapes) == 6
    buf = BytesIO()
    slide.part.package.presentation_part.presentation.save(buf)
    reopened = Presentation(BytesIO(buf.getvalue()))
    assert "Headline" in [s.text for s in reopened.slides[0].shapes if s.has_text_frame]
    assert result.estimated_fonts == []
    assert not validate_presentation(buf.getvalue()).has_errors


@pytest.mark.parametrize(
    "tree",
    [
        Row([label("A", width=Inches(3)), label("B", width=Inches(3))]),
        Column([label("A", height=Inches(2)), label("B", height=Inches(2))]),
        Card([label("A")], padding=Inches(2)),
        Card([label("A")], radius=Inches(5)),
        Card([label("A")], fill="invalid-color"),
        Card([label("A", name="same"), label("B", name="same")]),
        Card([label("A")], radius=float("nan")),
    ],
)
def test_invalid_layouts_fail_before_any_slide_mutation(slide, tree):
    before = slide.element.xml
    with pytest.raises(ValueError):
        tree.render(slide, BBox.from_inches(1, 1, 4, 3))
    assert slide.element.xml == before


def test_fixed_and_flexible_widths_and_grow(slide):
    result = Row(
        [
            Column([label("Fixed")], width=Inches(2), name="fixed"),
            Card(
                [label("Top"), label("Stretch", grow=1, name="stretch"), label("Bottom")],
                grow=2,
                name="right",
            ),
        ],
        gap=Inches(0.25),
    ).render(slide, BBox.from_inches(1, 1, 8, 4))
    assert result["right"].left == Inches(3.25)
    assert result["right"].width == Inches(5.75)
    assert result["stretch"].height > Inches(2)


def test_native_content_receives_its_reserved_box(slide):
    received = []

    def builder(target, box):
        received.append(box)
        target.shapes.add_text(box, text="A native extension", size_pt=18)

    result = Card([label("Title"), NativeContent(builder, height=Inches(1), name="custom")]).render(
        slide, BBox.from_inches(1, 1, 6, 3)
    )
    assert result["custom"].text == "A native extension"
    assert received[0].height == Inches(1)
    assert received[0].width == Inches(6) - Pt(36)


def test_missing_font_fails_before_mutation_in_strict_mode(slide):
    before = slide.element.xml
    with pytest.raises(ValueError, match="unavailable"):
        Card([TextBlock("Hello", font="Missing Gallery Font")]).render(
            slide, BBox.from_inches(1, 1, 6, 3), strict_fonts=True
        )
    assert slide.element.xml == before


def test_components_support_tokens_and_badge_intrinsic_width(slide):
    # Font-file injection keeps this test independent of machine font installs.
    badge = Badge("Ready")
    badge.label.font_file = FONT
    metric = MetricTile("94%", "Retention", detail="Up this quarter")
    for child in metric.children:
        child.font_file = FONT
    tokens = DesignTokens.from_dict({"palette": {"primary": "#123456", "surface": "#F1F2F3"}})
    result = Row([badge, metric], align="start").render(
        slide, BBox.from_inches(1, 1, 8, 3), tokens=tokens
    )
    assert result.shapes[0].width < Inches(1.5)
    assert result.shapes[2].fill.fore_color.rgb == tokens.palette["surface"]


def test_text_constraints_are_respected_in_component_layout(slide):
    text = label(
        "A headline that should stay on one line",
        size_pt=36,
        min_size_pt=12,
        max_lines=1,
        preserve_breaks=True,
        name="headline",
    )
    result = text.render(slide, BBox.from_inches(1, 1, 5, 1))
    size = result["headline"].text_frame.paragraphs[0].runs[0].font.size.pt
    assert 12 <= size < 36
    with pytest.raises(LayoutOverflowError):
        label("One\nTwo", max_lines=1).render(slide, BBox.from_inches(1, 3, 5, 1))


def test_cycles_and_shared_instances_are_rejected_before_mutation(slide):
    cyclic = Column([])
    cyclic.children = [cyclic]
    child = label("Hello")
    for tree in [cyclic, Row([child, child])]:
        before = slide.element.xml
        with pytest.raises(ValueError, match="cycles or reuse"):
            tree.render(slide, BBox.from_inches(1, 1, 6, 3))
        assert slide.element.xml == before


def test_intrinsic_badge_and_measured_copy_cannot_rewrap_in_office(slide):
    badge = Badge("LIVE WORKSPACE")
    badge.label.font_file = FONT
    result = Row([badge, label("A longer explanation that wraps into measured lines")]).render(
        slide, BBox.from_inches(1, 1, 5, 2)
    )
    assert all(
        s.text_frame.word_wrap is False for s in result.shapes if s.has_text_frame and s.text
    )
