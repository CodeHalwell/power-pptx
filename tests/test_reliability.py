"""Regression coverage for fitting, audit and spec validation failures."""

from io import BytesIO
from itertools import combinations
from math import hypot

import pytest
from PIL import Image

from power_pptx import BBox, Presentation, audit
from power_pptx.compose import from_spec
from power_pptx.diagrams import hub_and_spoke
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import MSO_AUTO_SIZE
from power_pptx.text.layout import TextFitter
from power_pptx.util import Inches, Pt


@pytest.fixture
def slide():
    prs = Presentation()
    return prs.slides.add_slide(prs.slide_layouts[6])


@pytest.mark.parametrize("separator", ["\n", "\v", "\r\n"])
def test_fit_preserves_explicit_lines(separator):
    text = separator.join(["X"] * 10)
    size = TextFitter.best_fit_font_size(text, (Inches(8), Inches(1)), 36, None)
    assert size is not None
    assert size <= 6


@pytest.mark.parametrize("text", [" ", "\n", "\v", "\t", "X\n\n", "\nX\n"])
def test_fit_handles_blank_lines(slide, text):
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(1))
    box.text = text
    size = box.text_frame.fit_text(max_size=36)
    assert size is not None
    assert 1 <= size <= 36
    assert box.text == text
    if "X" in text:
        assert size <= 18


def test_fit_rejects_an_empty_size_range():
    with pytest.raises(ValueError, match="max_size"):
        TextFitter.best_fit_font_size("Hello", (Inches(1), Inches(1)), 0, None)


@pytest.mark.parametrize("text", ["\v".join(["X"] * 10), "X\n\n\n\n", "\n\n\n\nX"])
def test_lint_counts_soft_and_blank_lines(slide, text):
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(1))
    box.text = text
    box.text_frame.auto_size = MSO_AUTO_SIZE.NONE
    for paragraph in box.text_frame.paragraphs:
        for run in paragraph.runs:
            run.font.size = Pt(36)
    assert "TextOverflow" in {issue.code for issue in slide.lint().issues}


def _add_picture(slide, *, full_bleed=False):
    data = BytesIO()
    Image.new("RGB", (32, 24), "red").save(data, format="PNG")
    data.seek(0)
    prs = slide.part.package.presentation_part.presentation
    bounds = (
        (0, 0, prs.slide_width, prs.slide_height)
        if full_bleed
        else (Inches(1), Inches(1), Inches(2), Inches(1.5))
    )
    return slide.shapes.add_picture(data, *bounds)


@pytest.mark.parametrize("damage", ["corrupt", "empty", "missing", "zero-sized"])
def test_audit_reports_broken_pictures(slide, damage):
    picture = _add_picture(slide)
    image_part = slide.part.related_part(picture._element.blip_rId)
    if damage == "missing":
        slide.part.drop_rel(picture._element.blip_rId)
    elif damage == "zero-sized":
        picture.width = 0
    else:
        image_part._blob = b"not an image" if damage == "corrupt" else b""
    prs = slide.part.package.presentation_part.presentation
    before = slide._element.xml

    report = audit(prs)

    assert report.broken_pictures == [(0, picture)]
    assert report.to_dict()["has_errors"] is True
    assert "Broken pictures" in report.markdown()
    assert slide._element.xml == before


def test_audit_counts_full_bleed_photograph_as_content(slide):
    _add_picture(slide, full_bleed=True)
    prs = slide.part.package.presentation_part.presentation
    report = audit(prs)
    assert report.empty_slides == []
    assert report.broken_pictures == []


def test_audit_visits_nested_groups(slide):
    picture = _add_picture(slide)
    group = slide.shapes.add_group_shape([picture])
    nested = group.shapes.add_group_shape()
    text = nested.shapes.add_textbox(Inches(4), Inches(1), Inches(2), Inches(1))
    text.text = "Nested font"
    text.text_frame.paragraphs[0].runs[0].font.name = "Missing Review Font"
    picture.width = 0
    prs = slide.part.package.presentation_part.presentation

    report = audit(prs)

    assert report.broken_pictures == [(0, picture)]
    assert report.font_warnings == [(0, "Missing Review Font")]


@pytest.mark.parametrize(
    ("layout", "key", "suggestion"),
    [
        ("title", "subtitel", "subtitle"),
        ("bullets", "bulletz", "bullets"),
        ("two_column", "content_lefft", "content_left"),
    ],
)
def test_legacy_spec_rejects_unknown_fields(layout, key, suggestion):
    with pytest.raises(ValueError, match=rf"slides\[0\].*did you mean '{suggestion}'"):
        from_spec({"slides": [{"layout": layout, "title": "Test", key: "Lost content"}]})


@pytest.mark.parametrize("slide_spec", [None, 42, "title", []])
def test_spec_rejects_non_mapping_slide(slide_spec):
    with pytest.raises(ValueError, match=r"slides\[0\].*mapping"):
        from_spec({"slides": [slide_spec]})


def test_spec_rejects_non_string_layout():
    with pytest.raises(ValueError, match=r"slides\[0\].layout.*string"):
        from_spec({"slides": [{"layout": 42}]})


def test_named_standard_layout_populates_content():
    prs = from_spec({"slides": [{"layout": "Title Slide", "title": "Hi", "subtitle": "Body"}]})
    assert "Body" in [shape.text for shape in prs.slides[0].shapes if shape.has_text_frame]


@pytest.mark.parametrize(("text_color", "expected"), [("#FFFFFF", False), ("#172334", True)])
def test_contrast_uses_containing_card_in_paint_order(slide, text_color, expected):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = "#FFFFFF"
    # An earlier white card must not override the nearest dark card.
    for color in ("#FFFFFF", "#172334"):
        card = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(5), Inches(3)
        )
        card.fill_hex(color)
    text = slide.shapes.add_text(
        Inches(2),
        Inches(2),
        Inches(2),
        Inches(0.5),
        text="Card label",
        color=text_color,
        size_pt=18,
    )
    # A later card does not provide a background for earlier text.
    later = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(5), Inches(3))
    later.fill_hex("#FFFFFF")
    before = slide._element.xml

    issues = [i for i in slide.lint().issues if i.code == "LowContrast" and text in i.shapes]

    assert bool(issues) is expected
    assert slide._element.xml == before


@pytest.mark.parametrize("backdrop", ["gradient", "translucent", "partial", "picture"])
def test_contrast_skips_unresolved_card_backgrounds(slide, backdrop):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = "#FFFFFF"
    if backdrop == "picture":
        _add_picture(slide, full_bleed=True)
    else:
        card = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(5), Inches(3)
        )
        card.fill_hex("#172334")
        if backdrop == "gradient":
            card.fill.linear_gradient("#172334", "#FFFFFF")
        elif backdrop == "translucent":
            card.fill.fore_color.alpha = 0.5
        else:
            card.width = Inches(1.5)
    text = slide.shapes.add_text(
        Inches(2),
        Inches(2),
        Inches(2),
        Inches(0.5),
        text="Card label",
        color="#FFFFFF",
        size_pt=18,
    )
    before = slide._element.xml
    assert not [i for i in slide.lint().issues if i.code == "LowContrast" and text in i.shapes]
    assert slide._element.xml == before


@pytest.mark.parametrize("count", [1, 2, 6, 8, 12, 24])
def test_hub_nodes_have_visible_space_and_stay_inside_region(slide, count):
    region = BBox.from_inches(0.5, 1, 9, 5)
    diagram = hub_and_spoke(slide, region, centre="Core", spokes=[str(n) for n in range(count)])
    nodes = [diagram.hub, *diagram.spokes]
    for node in nodes:
        assert node.left >= region.left
        assert node.top >= region.top
        assert node.left + node.width <= region.right
        assert node.top + node.height <= region.bottom
    for first, second in combinations(nodes, 2):
        distance = hypot(
            first.left + first.width / 2 - second.left - second.width / 2,
            first.top + first.height / 2 - second.top - second.height / 2,
        )
        assert distance > (first.width + second.width) / 2 + Inches(0.05)


@pytest.mark.parametrize(
    "options", [{"hub_size": 0}, {"spoke_size": -1}, {"hub_size": float("inf")}, {"hub_size": 10}]
)
def test_hub_rejects_impossible_sizes_before_mutation(slide, options):
    before = slide._element.xml
    with pytest.raises(ValueError):
        hub_and_spoke(
            slide, BBox.from_inches(1, 1, 5, 5), centre="Core", spokes=["A", "B"], **options
        )
    assert slide._element.xml == before


def test_hub_connectors_follow_circular_radii(slide):
    diagram = hub_and_spoke(
        slide, BBox.from_inches(1, 1, 8, 5), centre="Core", spokes=list("ABCDEFGH")
    )
    cx = diagram.hub.left + diagram.hub.width / 2
    cy = diagram.hub.top + diagram.hub.height / 2
    for spoke, arrow in zip(diagram.spokes, diagram.arrows):
        sx = spoke.left + spoke.width / 2
        sy = spoke.top + spoke.height / 2
        for x, y in ((arrow.begin_x, arrow.begin_y), (arrow.end_x, arrow.end_y)):
            # Distance to the hub-to-spoke center line stays below one EMU.
            distance = abs((x - cx) * (sy - cy) - (y - cy) * (sx - cx)) / hypot(sx - cx, sy - cy)
            assert distance <= 1
        assert hypot(arrow.begin_x - cx, arrow.begin_y - cy) > diagram.hub.width / 2
        assert hypot(arrow.end_x - sx, arrow.end_y - sy) > spoke.width / 2
