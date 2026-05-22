"""Unit tests for the new shape-level helpers — fill_hex, line_hex, add_text,
add_arrow, set_text_preserving_format, replace_with, enclosing_container,
content_bbox, find_empty_region, tidy."""

from __future__ import annotations

import pytest

from power_pptx import BBox, Presentation
from power_pptx.enum.dml import MSO_LINE_END_TYPE
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.util import Inches, Pt


@pytest.fixture
def slide():
    prs = Presentation()
    return prs.slides.add_slide(prs.slide_layouts[6])


# ---------------------------------------------------------------------------- fill/line


class DescribeFillHex:
    def it_sets_a_solid_fill_from_hex(self, slide):
        rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(2), Inches(1))
        rect.fill_hex("#0B5CFF")
        assert str(rect.fill.fore_color.rgb) == "0B5CFF"

    def it_returns_self_for_chaining(self, slide):
        rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(2), Inches(1))
        result = rect.fill_hex("#0B5CFF")
        assert result is rect

    def it_accepts_hex_without_hash(self, slide):
        rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(2), Inches(1))
        rect.fill_hex("0B5CFF")
        assert str(rect.fill.fore_color.rgb) == "0B5CFF"


class DescribeLineHex:
    def it_sets_line_color_and_width(self, slide):
        rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(2), Inches(1))
        rect.line_hex("#0D0D0D", weight_pt=2.0)
        assert str(rect.line.color.rgb) == "0D0D0D"
        assert int(rect.line.width) == int(Pt(2.0))


# ---------------------------------------------------------------------------- text


class DescribeAddText:
    def it_creates_a_textbox_with_text(self, slide):
        tx = slide.shapes.add_text(BBox.from_inches(1, 1, 4, 1), text="Hello")
        assert tx.text_frame.text == "Hello"

    def it_applies_font_styling(self, slide):
        tx = slide.shapes.add_text(
            BBox.from_inches(1, 1, 4, 1),
            text="Hi",
            font="Inter",
            size_pt=24,
            bold=True,
            color="#FF0000",
        )
        run = tx.text_frame.paragraphs[0].runs[0]
        assert run.font.name == "Inter"
        assert run.font.size == Pt(24)
        assert run.font.bold is True
        assert str(run.font.color.rgb) == "FF0000"

    def it_accepts_positional_lengths(self, slide):
        tx = slide.shapes.add_text(
            Inches(1), Inches(2), Inches(3), Inches(1),
            text="positional",
        )
        assert tx.text_frame.text == "positional"

    def it_applies_alignment_short_names(self, slide):
        from power_pptx.enum.text import PP_PARAGRAPH_ALIGNMENT

        tx = slide.shapes.add_text(BBox.from_inches(0, 0, 4, 1), text="x", align="center")
        assert tx.text_frame.paragraphs[0].alignment == PP_PARAGRAPH_ALIGNMENT.CENTER

    def it_rejects_unknown_align(self, slide):
        with pytest.raises(ValueError):
            slide.shapes.add_text(BBox.from_inches(0, 0, 4, 1), text="x", align="diagonal")


class DescribeSetTextPreservingFormat:
    def it_preserves_font_attributes_across_replacement(self, slide):
        tx = slide.shapes.add_text(
            BBox.from_inches(0, 0, 4, 1),
            text="<TITLE>",
            font="Inter",
            size_pt=18,
            bold=True,
            color="#0B5CFF",
        )
        tx.set_text_preserving_format("New title")
        run = tx.text_frame.paragraphs[0].runs[0]
        assert run.font.name == "Inter"
        assert run.font.size == Pt(18)
        assert run.font.bold is True
        assert str(run.font.color.rgb) == "0B5CFF"
        assert tx.text_frame.text == "New title"

    def it_preserves_format_across_multiple_lines(self, slide):
        tx = slide.shapes.add_text(
            BBox.from_inches(0, 0, 4, 2), text="<x>", font="Inter", size_pt=14, bold=True,
        )
        tx.set_text_preserving_format("a\nb\nc")
        assert len(tx.text_frame.paragraphs) == 3
        for para in tx.text_frame.paragraphs:
            for run in para.runs:
                assert run.font.name == "Inter"
                assert run.font.bold is True

    def it_raises_when_shape_has_no_text_frame(self, slide):
        line = slide.shapes.add_connector(
            __import__("power_pptx").util.Emu(0),
            None, None, None, None,
        ) if False else None
        # Lines have no text frame.  Use a connector if available, otherwise
        # skip with a clear assertion.
        connector_type = __import__("power_pptx.enum.shapes", fromlist=["MSO_CONNECTOR_TYPE"]).MSO_CONNECTOR_TYPE
        conn = slide.shapes.add_connector(connector_type.STRAIGHT, Inches(0), Inches(0), Inches(1), Inches(1))
        with pytest.raises(ValueError):
            conn.set_text_preserving_format("nope")


# ---------------------------------------------------------------------------- arrow


class DescribeAddArrow:
    def it_creates_a_connector_with_a_tail_arrowhead(self, slide):
        a = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1))
        b = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(5), Inches(1), Inches(2), Inches(1))
        arrow = slide.shapes.add_arrow(a, b)
        assert arrow.line.tail_end.type == MSO_LINE_END_TYPE.TRIANGLE

    def it_accepts_bbox_endpoints(self, slide):
        arrow = slide.shapes.add_arrow(
            BBox.from_inches(0, 0, 1, 1),
            BBox.from_inches(5, 0, 1, 1),
        )
        assert arrow is not None

    def it_accepts_xy_tuple_endpoints(self, slide):
        arrow = slide.shapes.add_arrow(
            (Inches(0), Inches(0)),
            (Inches(5), Inches(0)),
        )
        # Begin point is at the start tuple
        assert int(arrow.begin_x) == int(Inches(0))

    def it_rejects_unknown_route(self, slide):
        with pytest.raises(ValueError):
            slide.shapes.add_arrow((Inches(0), Inches(0)), (Inches(5), Inches(0)), route="zigzag")


# ---------------------------------------------------------------------------- picture helpers


class DescribePictureReplaceWith:
    def it_calls_builder_with_the_pictures_bbox(self, slide):
        # add_picture needs an image; use a tiny 1x1 PNG placeholder.
        import io

        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
            "53de0000000c4944415478da6300010000000500010d0a2db40000000049"
            "454e44ae426082"
        )
        pic = slide.shapes.add_picture(io.BytesIO(png), Inches(1), Inches(1), Inches(2), Inches(2))
        called = {}

        def build(slide_arg, bbox_arg):
            called["slide"] = slide_arg
            called["bbox"] = bbox_arg

        pic.replace_with(build)
        assert called["slide"] is slide
        assert isinstance(called["bbox"], BBox)


# ---------------------------------------------------------------------------- slide-level


class DescribeSlideHelpers:
    def it_returns_a_slide_bbox(self, slide):
        bb = slide.slide_bbox()
        assert bb.width == Inches(10)
        assert bb.height == Inches(7.5)

    def it_returns_a_content_bbox(self, slide):
        slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1))
        slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(5), Inches(2), Inches(2), Inches(1))
        bb = slide.content_bbox()
        assert int(bb.left) == int(Inches(1))
        assert int(bb.right) == int(Inches(7))

    def it_returns_none_for_empty_slide(self, slide):
        bb = slide.content_bbox()
        assert bb is None

    def it_finds_empty_region(self, slide):
        slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(3), Inches(1))
        region = slide.find_empty_region(min_width=Inches(0.5), min_height=Inches(0.5))
        assert region is not None
        assert isinstance(region, BBox)

    def it_tidies_off_slide_shapes(self, slide):
        slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(15), Inches(15), Inches(2), Inches(1))
        fixes = slide.tidy()
        assert any("Clamped" in f for f in fixes)
