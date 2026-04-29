"""Showcase 06 — Tables with custom borders and brand styling.

Demonstrates the post-fork ``Cell.borders`` API on top of the
inherited table primitives.
"""

from __future__ import annotations

from pathlib import Path

from power_pptx import Presentation
from power_pptx.dml.color import RGBColor
from power_pptx.util import Inches, Pt

from _lint import lint_or_die

HERE = Path(__file__).parent

NEUTRAL = RGBColor(0x0F, 0x17, 0x2A)
PRIMARY = RGBColor(0x4F, 0x46, 0xE5)
SURFACE = RGBColor(0xF8, 0xFA, 0xFC)
ROW_ALT = RGBColor(0xF1, 0xF5, 0xF9)
MUTED = RGBColor(0x64, 0x74, 0x8B)
POSITIVE = RGBColor(0x10, 0xB9, 0x81)
NEGATIVE = RGBColor(0xEF, 0x44, 0x44)


def build(out_path: Path) -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _slide_title(slide, "Run-rate scorecard")

    headers = ("Metric", "FY25", "FY26", "Δ YoY", "Notes")
    rows = [
        ("ARR ($M)",       "110",  "182",  "+65%",  "Outpaces plan by 12 points"),
        ("NDR",            "118%", "131%", "+13pp", "Driven by enterprise expand"),
        ("Gross retention","94%",  "97%",  "+3pp",  "Churn down across all tiers"),
        ("CAC payback",    "11 mo", "8 mo", "−3 mo", "Sales efficiency improved"),
        ("Logo count",     "412",  "604",  "+47%",  "EU contributed 38% of net-new"),
    ]

    table_shape = slide.shapes.add_table(
        rows=len(rows) + 1, cols=len(headers),
        left=Inches(0.6), top=Inches(1.6),
        width=Inches(12.1), height=Inches(4.8),
    )
    table = table_shape.table

    table.columns[0].width = Inches(2.6)
    table.columns[1].width = Inches(1.6)
    table.columns[2].width = Inches(1.6)
    table.columns[3].width = Inches(1.6)
    table.columns[4].width = Inches(4.7)

    for c, label in enumerate(headers):
        cell = table.cell(0, c)
        cell.text = label
        _style_header(cell)

    for r, row in enumerate(rows, start=1):
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            cell.text = value
            _style_body(cell, alt=(r % 2 == 0))
            if c == 3:
                _color_delta(cell, value)

    lint_or_die(prs)
    prs.save(out_path)
    return prs


def _slide_title(slide, text: str) -> None:
    box = slide.shapes.add_textbox(
        Inches(0.6), Inches(0.4), Inches(12), Inches(1.0),
    )
    tf = box.text_frame
    tf.word_wrap = True
    tf.text = text
    tf.fit_text(font_family="Inter", max_size=32, bold=True)
    tf.paragraphs[0].font.color.rgb = NEUTRAL


def _style_header(cell) -> None:
    cell.fill.solid()
    cell.fill.fore_color.rgb = PRIMARY
    p = cell.text_frame.paragraphs[0]
    p.font.name = "Inter"
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    cell.margin_left = cell.margin_right = Pt(10)
    cell.margin_top = cell.margin_bottom = Pt(8)
    # Strong bottom rule under the header band.
    cell.borders.bottom.color.rgb = NEUTRAL
    cell.borders.bottom.width = Pt(1.5)


def _style_body(cell, *, alt: bool) -> None:
    cell.fill.solid()
    cell.fill.fore_color.rgb = ROW_ALT if alt else SURFACE
    p = cell.text_frame.paragraphs[0]
    p.font.name = "Inter"
    p.font.size = Pt(13)
    p.font.color.rgb = NEUTRAL
    cell.margin_left = cell.margin_right = Pt(10)
    cell.margin_top = cell.margin_bottom = Pt(6)
    cell.borders.bottom.color.rgb = RGBColor(0xE2, 0xE8, 0xF0)
    cell.borders.bottom.width = Pt(0.5)


def _color_delta(cell, value: str) -> None:
    p = cell.text_frame.paragraphs[0]
    p.font.bold = True
    if value.startswith(("-", "−")):
        # CAC payback: a negative number is good.
        p.font.color.rgb = POSITIVE if "mo" in value else NEGATIVE
    elif value.startswith("+"):
        p.font.color.rgb = POSITIVE
    else:
        p.font.color.rgb = MUTED


if __name__ == "__main__":
    out = HERE / "_out" / "06_tables.pptx"
    out.parent.mkdir(exist_ok=True)
    build(out)
    print(f"wrote {out}")
