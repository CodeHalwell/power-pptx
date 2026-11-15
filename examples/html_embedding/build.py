"""Build faithful HTML and native/hybrid versions of the same two-slide design."""

from __future__ import annotations

import argparse
from pathlib import Path

from power_pptx import BBox, Presentation, add_svg_figure, audit
from power_pptx.compose import from_html
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.util import Emu, Inches, Pt

HERE = Path(__file__).parent

# deck.html lays each slide out on a 1280 px wide canvas.
SLIDE_WIDTH, SLIDE_HEIGHT = Inches(40 / 3), Inches(7.5)
CANVAS_WIDTH_PX = 1280

CARDS = [
    (
        "Native objects",
        "Editable text, tables, and charts for content that needs to change.",
    ),
    ("SVG assets", "Sharp diagrams and logos with a PNG companion for previews."),
    (
        "HTML capture",
        "Faithful browser styling for complex visuals and static slide designs.",
    ),
]


def build_native():
    """An explicit native reconstruction of deck.html, rather than a CSS converter."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_WIDTH, SLIDE_HEIGHT

    for index in range(2):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        _page_frame(slide, index)
        if index == 0:
            _structure_slide(slide)
        else:
            _embedding_slide(slide)
        slide.tidy()
    return prs


def box(x, y, width, height):
    """The slide-space bounds of a box measured in deck.html's CSS pixels."""
    return BBox(
        *(Emu(round(value * SLIDE_WIDTH / CANVAS_WIDTH_PX)) for value in (x, y, width, height))
    )


def text(slide, bounds, value, size, *, bold=False, color="#183D36"):
    """A text box at CSS-pixel *bounds*, *size* given in CSS px like the HTML."""
    shape = slide.shapes.add_text(
        box(*bounds),
        text=value,
        size_pt=size * 0.75,
        font="DejaVu Sans",
        bold=bold,
        color=color,
        align="left", anchor="top", margin_pt=0,
    )
    for paragraph in shape.text_frame.paragraphs:
        paragraph.line_spacing = 1.14 if bold else 1.45
    return shape


def _page_frame(slide, index):
    """Background, eyebrow, footer and page number shared by both slides."""
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = "#F4F1E7"
    eyebrow = "STUDIO / FIELD NOTES" if index == 0 else "DESIGN THE HANDOFF"
    text(slide, (64, 60, 1000, 32), eyebrow, 18, color="#42685D")
    footer = "HTML → POWERPOINT" if index == 0 else "NATIVE + VECTOR + CAPTURED"
    text(slide, (64, 656, 1000, 24), footer, 16, color="#42685D")
    text(slide, (1120, 656, 120, 24), f"0{index + 1} / 02", 16, color="#42685D")


def _structure_slide(slide):
    """Slide 1: headline and body copy beside the SVG diagram."""
    text(
        slide, (64, 132, 750, 216), "Good slides start\nwith good structure.", 64, bold=True
    )
    text(
        slide,
        (64, 388, 690, 180),
        "Keep the visual decisions that make an HTML design work: a clear hierarchy, "
        "generous spacing, and one idea per slide.",
        27,
        color="#42685D",
    )
    picture = add_svg_figure(slide, HERE / "diagram.svg", *box(844, 152, 360, 400))
    picture.alt_text = "HTML design becomes layout and hierarchy, then PowerPoint slides."


def _embedding_slide(slide):
    """Slide 2: headline over three numbered cards, one per kind of embedding."""
    text(slide, (64, 132, 1100, 200), "Choose the right\nkind of embedding.", 58, bold=True)
    for number, (heading, body) in enumerate(CARDS):
        x = 64 + number * 408
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, *box(x, 350, 336, 264))
        card.fill_hex("#FFFFFF").line_hex("#CBD6CA", weight_pt=0.75)
        card.shadow.clear()
        card.corner_radius = Pt(15)
        label = text(slide, (x + 28, 378, 280, 30), f"0{number + 1}", 18, color="#42685D")
        title = text(slide, (x + 28, 426, 290, 44), heading, 28, bold=True)
        copy = text(slide, (x + 28, 480, 280, 110), body, 22, color="#42685D")
        slide.lint_group_overlaps(card, label, title, copy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=HERE / "_out")
    parser.add_argument("--browser-path")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    captured = from_html(HERE / "deck.html", browser_path=args.browser_path)
    captured.save(args.out_dir / "html-captured.pptx")
    for index, slide in enumerate(captured.slides):
        (args.out_dir / f"html-reference-{index + 1}.png").write_bytes(slide.shapes[0].image.blob)
    native = build_native()
    native.save(args.out_dir / "native-hybrid.pptx")
    print(audit(native).markdown())
    print(f"Wrote both decks and HTML references to {args.out_dir}")


if __name__ == "__main__":
    main()
