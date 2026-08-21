"""Integration tests for the new table API surfaces:

* ``row.borders`` / ``col.borders`` shorthand
* ``Table.banded_rows`` / ``banded_cols`` aliases
* ``Table.fit_to_box``
* ``cell.text_frame.fit_text`` honoring cell bounds
"""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx.dml.color import RGBColor
from power_pptx.util import Inches, Pt


def _new_table(rows=2, cols=2, w=Inches(4), h=Inches(2)):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    gf = slide.shapes.add_table(rows, cols, Inches(1), Inches(1), w, h)
    return prs, slide, gf.table


class DescribeRowBordersShorthand:
    def it_applies_a_bottom_border_to_every_cell_in_the_row(self):
        _, _, table = _new_table()
        table.rows[0].borders.bottom(width=Pt(2), color=RGBColor(0, 0, 0))
        for cell in table.rows[0].cells:
            assert cell.borders.bottom.width == Pt(2)

    def it_applies_outer_borders_to_every_cell_in_the_row(self):
        _, _, table = _new_table()
        table.rows[0].borders.outer(width=Pt(1), color=RGBColor(255, 0, 0))
        for cell in table.rows[0].cells:
            for edge in (cell.borders.left, cell.borders.right, cell.borders.top, cell.borders.bottom):
                assert edge.width == Pt(1)

    def it_clears_all_borders_in_the_row(self):
        _, _, table = _new_table()
        table.rows[0].borders.outer(width=Pt(2), color=RGBColor(0, 0, 0))
        # Sanity: the width was set.
        assert table.rows[0].cells[0].borders.bottom.width == Pt(2)
        table.rows[0].borders.none()
        # After clear, the underlying ``<a:ln*>`` elements are removed; the
        # LineFormat returns either ``None`` or a default of 0 EMU depending
        # on which path the proxy takes — what matters is the explicit value
        # from before is gone.
        for cell in table.rows[0].cells:
            for edge in (cell.borders.left, cell.borders.right, cell.borders.top, cell.borders.bottom):
                assert edge.width != Pt(2)


class DescribeColumnBordersShorthand:
    def it_applies_a_right_border_to_every_cell_in_the_column(self):
        _, _, table = _new_table()
        table.columns[0].borders.right(width=Pt(2), color=(0, 128, 0))
        # First column is the cells at col_idx=0 across all rows.
        for row in table.rows:
            assert row.cells[0].borders.right.width == Pt(2)


class DescribeBandedRowsAliases:
    def it_aliases_banded_rows_to_horz_banding(self):
        _, _, table = _new_table()
        table.banded_rows = True
        assert table.banded_rows is True
        assert table.horz_banding is True
        table.banded_rows = False
        assert table.horz_banding is False

    def it_aliases_banded_cols_to_vert_banding(self):
        _, _, table = _new_table()
        table.banded_cols = True
        assert table.vert_banding is True


class DescribeFitToBox:
    def it_keeps_max_size_when_text_already_fits(self):
        _, _, table = _new_table(2, 2, w=Inches(8), h=Inches(4))
        table.cell(0, 0).text = "short"
        table.cell(0, 1).text = "fine"
        size = table.fit_to_box(max_font_pt=18, min_font_pt=8)
        assert size == 18

    def it_shrinks_when_a_cell_overflows(self):
        # Tiny cells (1in × 0.25in) with way too much text.
        _, _, table = _new_table(2, 2, w=Inches(2), h=Inches(0.5))
        table.cell(0, 0).text = (
            "lorem ipsum dolor sit amet consectetur adipiscing elit"
        )
        table.cell(0, 1).text = "x"
        size = table.fit_to_box(max_font_pt=18, min_font_pt=6)
        assert 6 <= size < 18

    def it_clamps_to_min_font_pt(self):
        _, _, table = _new_table(2, 2, w=Inches(0.5), h=Inches(0.25))
        # Even one word won't fit at any size.
        table.cell(0, 0).text = "supercalifragilisticexpialidocious " * 5
        size = table.fit_to_box(max_font_pt=18, min_font_pt=8)
        assert size == 8

    def it_applies_target_size_to_every_cell(self):
        _, _, table = _new_table()
        table.cell(0, 0).text = "a"
        table.cell(0, 1).text = "b"
        table.cell(1, 0).text = "c"
        table.cell(1, 1).text = "d"
        target = table.fit_to_box(max_font_pt=14, min_font_pt=8)
        for cell in table.iter_cells():
            for paragraph in cell.text_frame.paragraphs:
                for run in paragraph.runs:
                    assert run.font.size == Pt(target)

    def it_rejects_invalid_bounds(self):
        _, _, table = _new_table()
        with pytest.raises(ValueError):
            table.fit_to_box(max_font_pt=4, min_font_pt=8)
        with pytest.raises(ValueError):
            table.fit_to_box(min_font_pt=0)


class DescribeCellExtents:
    def it_exposes_cell_width_and_height(self):
        _, _, table = _new_table(2, 2, w=Inches(4), h=Inches(2))
        cell = table.cell(0, 0)
        # Each column = 2", each row = 1" by default split.
        assert int(cell.width) == int(Inches(2))
        assert int(cell.height) == int(Inches(1))


class DescribeAddTableStyleClean:
    def it_disables_every_inherited_style_flag(self):
        # ``style="clean"`` is the right base for hand-styled tables —
        # custom cell borders / fills then render consistently across
        # PowerPoint and LibreOffice without the inherited style
        # overlay.
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        gf = slide.shapes.add_table(
            2, 2, Inches(1), Inches(1), Inches(4), Inches(2), style="clean"
        )
        tbl = gf.table
        assert tbl.first_row is False
        assert tbl.first_col is False
        assert tbl.last_row is False
        assert tbl.last_col is False
        assert tbl.horz_banding is False
        assert tbl.vert_banding is False

    def it_leaves_default_style_alone_when_unspecified(self):
        # Confirm style="default" (and the no-arg default) doesn't
        # silently change the inherited-style flags users may rely on.
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        gf_default = slide.shapes.add_table(
            2, 2, Inches(1), Inches(1), Inches(4), Inches(2)
        )
        # New python-pptx tables come with first_row=True by default;
        # make sure we don't change that without an opt-in.
        assert gf_default.table.first_row is True

    def it_rejects_unknown_style_names(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        with pytest.raises(ValueError, match="style must be"):
            slide.shapes.add_table(
                2, 2, Inches(1), Inches(1), Inches(4), Inches(2), style="bogus"
            )


class DescribeCellFitText:
    def it_now_measures_against_cell_bounds_not_table_bounds(self):
        # Before this fix, ``cell.text_frame.fit_text`` measured against the
        # whole table; the result was meaningless. After: it measures
        # against the cell's own width/height.
        _, _, table = _new_table(1, 1, w=Inches(2), h=Inches(0.5))
        cell = table.cell(0, 0)
        cell.text = "lorem ipsum dolor sit amet consectetur adipiscing"
        cell.text_frame.fit_text(max_size=18)
        # The applied size must be < 18 because the text overflows the cell.
        size = cell.text_frame.paragraphs[0].runs[0].font.size
        assert size is not None
        assert size.pt < 18


class DescribeCellFormat:
    """``cell.format(...)`` — fill + text styling in one call."""

    def it_sets_fill_and_text_style_together(self):
        _, _, table = _new_table()
        cell = table.cell(0, 0)
        cell.text = "Metric"

        returned = cell.format(
            fill="#1F2937", color=(255, 255, 255), bold=True, size_pt=12, align="center"
        )

        assert returned is cell
        assert cell.fill.fore_color.rgb == RGBColor(0x1F, 0x29, 0x37)
        font = cell.text_frame.paragraphs[0].runs[0].font
        assert font.color.rgb == RGBColor(0xFF, 0xFF, 0xFF)
        assert font.bold is True
        assert font.size == Pt(12)
        assert str(cell.text_frame.paragraphs[0].alignment) == "CENTER (2)"

    def it_leaves_unmentioned_properties_alone(self):
        _, _, table = _new_table()
        cell = table.cell(0, 0)
        cell.text = "Metric"
        cell.format(bold=True, size_pt=14)

        cell.format(color="#112233")

        font = cell.text_frame.paragraphs[0].runs[0].font
        assert font.bold is True
        assert font.size == Pt(14)

    def it_makes_a_cell_transparent_for_fill_none(self):
        _, _, table = _new_table()
        cell = table.cell(0, 0)
        cell.format(fill="#FF0000")

        cell.format(fill="none")

        assert str(cell.fill.type) == "BACKGROUND (5)"

    def it_sets_vertical_anchor_and_margins(self):
        _, _, table = _new_table()
        cell = table.cell(0, 0)

        cell.format(anchor="middle", margin=(2, 8, 2, 8))

        assert str(cell.vertical_anchor) == "MIDDLE (3)"
        assert cell.margin_top == Pt(2)
        assert cell.margin_left == Pt(8)

    def it_styles_paragraph_defaults_so_later_text_inherits(self):
        _, _, table = _new_table()
        cell = table.cell(0, 0)
        cell.text = "before"

        cell.format(size_pt=9)
        cell.text_frame.paragraphs[0].add_run().text = "after"

        assert cell.text_frame.paragraphs[0].font.size == Pt(9)

    def it_rejects_an_unknown_alignment_word(self):
        _, _, table = _new_table()
        with pytest.raises(ValueError, match="align must be one of"):
            table.cell(0, 0).format(align="middle")


class DescribeTableFormatCells:
    """``table.format_cells(...)`` — the same styling over a row/column selection."""

    def it_styles_every_cell_by_default(self):
        _, _, table = _new_table(rows=3, cols=3)

        returned = table.format_cells(size_pt=10)

        assert returned is table
        for cell in table.iter_cells():
            assert cell.text_frame.paragraphs[0].font.size == Pt(10)

    def it_selects_a_single_row_by_index(self):
        _, _, table = _new_table(rows=3, cols=2)

        table.format_cells(rows=0, fill="#1F2937")

        assert table.cell(0, 1).fill.fore_color.rgb == RGBColor(0x1F, 0x29, 0x37)
        assert str(table.cell(1, 0).fill.type) == "None"

    def it_selects_with_a_slice_an_iterable_and_a_negative_index(self):
        _, _, table = _new_table(rows=4, cols=3)

        table.format_cells(rows=slice(1, None), size_pt=11)
        table.format_cells(rows=range(1, 4, 2), fill="#F6F7F9")
        table.format_cells(cols=-1, align="right")

        assert table.cell(3, 0).text_frame.paragraphs[0].font.size == Pt(11)
        assert table.cell(1, 0).fill.fore_color.rgb == RGBColor(0xF6, 0xF7, 0xF9)
        assert str(table.cell(2, 0).fill.type) == "None"
        assert str(table.cell(0, 2).text_frame.paragraphs[0].alignment) == "RIGHT (3)"

    def it_skips_spanned_cells(self):
        _, _, table = _new_table(rows=2, cols=3)
        table.cell(0, 0).merge(table.cell(0, 1))

        table.format_cells(rows=0, fill="#101010")

        assert table.cell(0, 0).fill.fore_color.rgb == RGBColor(0x10, 0x10, 0x10)
        assert table.cell(0, 1).is_spanned

    def it_raises_for_an_out_of_range_selection(self):
        _, _, table = _new_table(rows=2, cols=2)
        with pytest.raises(IndexError, match="rows index 5 out of range"):
            table.format_cells(rows=5, fill="#000000")
        with pytest.raises(IndexError, match="cols index -3 out of range"):
            table.format_cells(cols=-3, fill="#000000")
