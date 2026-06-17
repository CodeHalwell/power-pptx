"""Tables torture: large tables, every Cell.borders helper, merged cells,
diagonal borders, per-cell fills, zebra striping, and vertical anchors.
"""

from __future__ import annotations

from _util import blank, deck, save

from power_pptx.dml.color import RGBColor
from power_pptx.enum.text import MSO_VERTICAL_ANCHOR
from power_pptx.util import Inches, Pt

LIGHT = RGBColor(0xE5, 0xE7, 0xEB)
DARK = RGBColor(0x1F, 0x29, 0x37)
HEAD = RGBColor(0x0B, 0x24, 0x47)


def build():
    prs = deck()

    # --- Slide 1: big zebra table with header + per-edge borders ---------
    s = blank(prs)
    rows, cols = 12, 6
    shape = s.shapes.add_table(rows, cols, Inches(0.5), Inches(0.5),
                               Inches(12.3), Inches(6.5))
    table = shape.table
    for c in range(cols):
        cell = table.cell(0, c)
        cell.text = f"Col {c + 1}"
        cell.fill.solid()
        cell.fill.fore_color.rgb = HEAD
        p = cell.text_frame.paragraphs[0]
        p.font.bold = True
        p.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
        cell.borders.bottom.color.rgb = DARK
        cell.borders.bottom.width = Pt(1.5)
    for r in range(1, rows):
        for c in range(cols):
            cell = table.cell(r, c)
            cell.text = f"r{r}c{c}"
            if r % 2 == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(0xF8, 0xFA, 0xFC)
            cell.borders.bottom.color.rgb = LIGHT
            cell.borders.bottom.width = Pt(0.5)

    # --- Slide 2: borders helpers (all / outer / none) + diagonals -------
    s = blank(prs)
    shape = s.shapes.add_table(4, 4, Inches(1), Inches(1),
                               Inches(11), Inches(5))
    table = shape.table
    for r in range(4):
        for c in range(4):
            table.cell(r, c).text = f"{r},{c}"
    # all edges on top-left block
    table.cell(0, 0).borders.all(width=Pt(1.0), color=LIGHT)
    table.cell(0, 1).borders.outer(width=Pt(2.0), color=DARK)
    table.cell(0, 2).borders.none()
    # diagonal borders
    table.cell(1, 1).borders.diagonal_down.color.rgb = RGBColor(0xEF, 0x44, 0x44)
    table.cell(1, 1).borders.diagonal_down.width = Pt(1.5)
    table.cell(1, 2).borders.diagonal_up.color.rgb = RGBColor(0x10, 0xB9, 0x81)
    table.cell(1, 2).borders.diagonal_up.width = Pt(1.5)

    # --- Slide 3: merged cells -------------------------------------------
    s = blank(prs)
    shape = s.shapes.add_table(5, 5, Inches(1), Inches(1),
                               Inches(11), Inches(5))
    table = shape.table
    # merge a 2x2 block
    table.cell(0, 0).merge(table.cell(1, 1))
    table.cell(0, 0).text = "merged 2x2"
    # merge a row span
    table.cell(0, 2).merge(table.cell(0, 4))
    table.cell(0, 2).text = "merged row"
    # merge a column span
    table.cell(2, 0).merge(table.cell(4, 0))
    table.cell(2, 0).text = "merged col"
    for r in range(5):
        for c in range(5):
            cell = table.cell(r, c)
            if not cell.is_spanned and not cell.text:
                cell.text = f"{r},{c}"

    # --- Slide 4: column widths / row heights + read-back of unset border -
    s = blank(prs)
    shape = s.shapes.add_table(3, 3, Inches(1), Inches(2),
                               Inches(11), Inches(3))
    table = shape.table
    table.columns[0].width = Inches(5)
    table.columns[1].width = Inches(3.5)
    table.columns[2].width = Inches(2.5)
    table.rows[0].height = Inches(0.8)
    # NOTE: tables.md documents that an unset edge reads back as None, but
    # LineFormat.width returns Emu(0) here (upstream-consistent: a plain
    # shape's line.width does the same). Doc/contract mismatch, not a crash.
    _unset = table.cell(2, 2).borders.bottom.width
    assert _unset in (None, 0), _unset
    for r in range(3):
        for c in range(3):
            table.cell(r, c).text = f"{r}{c}"

    return prs


if __name__ == "__main__":
    save(build(), "03_tables_torture.pptx")
