"""Table-related objects such as Table and Cell."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator

from power_pptx.dml.fill import FillFormat
from power_pptx.dml.line import LineFormat
from power_pptx.oxml.table import TcRange
from power_pptx.shapes import Subshape
from power_pptx.text.text import TextFrame
from power_pptx.util import Emu, lazyproperty

if TYPE_CHECKING:
    from power_pptx.enum.text import MSO_VERTICAL_ANCHOR
    from power_pptx.oxml.shapes.shared import CT_LineProperties
    from power_pptx.oxml.table import CT_Table, CT_TableCell, CT_TableCellProperties, CT_TableCol, CT_TableRow
    from power_pptx.parts.slide import BaseSlidePart
    from power_pptx.shapes.graphfrm import GraphicFrame
    from power_pptx.types import ProvidesPart
    from power_pptx.util import Length


class Table(object):
    """A DrawingML table object.

    Not intended to be constructed directly, use
    :meth:`.Slide.shapes.add_table` to add a table to a slide.
    """

    def __init__(self, tbl: CT_Table, graphic_frame: GraphicFrame):
        super(Table, self).__init__()
        self._tbl = tbl
        self._graphic_frame = graphic_frame

    def cell(self, row_idx: int, col_idx: int) -> _Cell:
        """Return cell at `row_idx`, `col_idx`.

        Return value is an instance of |_Cell|. `row_idx` and `col_idx` are zero-based, e.g.
        cell(0, 0) is the top, left cell in the table.
        """
        return _Cell(self._tbl.tc(row_idx, col_idx), self)

    @lazyproperty
    def columns(self) -> _ColumnCollection:
        """|_ColumnCollection| instance for this table.

        Provides access to |_Column| objects representing the table's columns. |_Column| objects
        are accessed using list notation, e.g. `col = tbl.columns[0]`.
        """
        return _ColumnCollection(self._tbl, self)

    @property
    def first_col(self) -> bool:
        """When `True`, indicates first column should have distinct formatting.

        Read/write. Distinct formatting is used, for example, when the first column contains row
        headings (is a side-heading column).
        """
        return self._tbl.firstCol

    @first_col.setter
    def first_col(self, value: bool):
        self._tbl.firstCol = value

    @property
    def first_row(self) -> bool:
        """When `True`, indicates first row should have distinct formatting.

        Read/write. Distinct formatting is used, for example, when the first row contains column
        headings.
        """
        return self._tbl.firstRow

    @first_row.setter
    def first_row(self, value: bool):
        self._tbl.firstRow = value

    @property
    def horz_banding(self) -> bool:
        """When `True`, indicates rows should have alternating shading.

        Read/write. Used to allow rows to be traversed more easily without losing track of which
        row is being read.
        """
        return self._tbl.bandRow

    @horz_banding.setter
    def horz_banding(self, value: bool):
        self._tbl.bandRow = value

    # Friendlier aliases — match the OOXML ``bandRow`` / ``bandCol``
    # vocabulary that PowerPoint's UI uses ("banded rows / columns").
    @property
    def banded_rows(self) -> bool:
        """Alias for :attr:`horz_banding` — alternating row shading."""
        return self._tbl.bandRow

    @banded_rows.setter
    def banded_rows(self, value: bool):
        self._tbl.bandRow = value

    @property
    def banded_cols(self) -> bool:
        """Alias for :attr:`vert_banding` — alternating column shading."""
        return self._tbl.bandCol

    @banded_cols.setter
    def banded_cols(self, value: bool):
        self._tbl.bandCol = value

    def iter_cells(self) -> Iterator[_Cell]:
        """Generate _Cell object for each cell in this table.

        Each grid cell is generated in left-to-right, top-to-bottom order.
        """
        return (_Cell(tc, self) for tc in self._tbl.iter_tcs())

    @property
    def last_col(self) -> bool:
        """When `True`, indicates the rightmost column should have distinct formatting.

        Read/write. Used, for example, when a row totals column appears at the far right of the
        table.
        """
        return self._tbl.lastCol

    @last_col.setter
    def last_col(self, value: bool):
        self._tbl.lastCol = value

    @property
    def last_row(self) -> bool:
        """When `True`, indicates the bottom row should have distinct formatting.

        Read/write. Used, for example, when a totals row appears as the bottom row.
        """
        return self._tbl.lastRow

    @last_row.setter
    def last_row(self, value: bool):
        self._tbl.lastRow = value

    def notify_height_changed(self) -> None:
        """Called by a row when its height changes.

        Triggers the graphic frame to recalculate its total height (as the sum of the row
        heights).
        """
        new_table_height = Emu(sum([row.height for row in self.rows]))
        self._graphic_frame.height = new_table_height

    def notify_width_changed(self) -> None:
        """Called by a column when its width changes.

        Triggers the graphic frame to recalculate its total width (as the sum of the column
        widths).
        """
        new_table_width = Emu(sum([col.width for col in self.columns]))
        self._graphic_frame.width = new_table_width

    @property
    def part(self) -> BaseSlidePart:
        """The package part containing this table."""
        return self._graphic_frame.part

    @lazyproperty
    def rows(self):
        """|_RowCollection| instance for this table.

        Provides access to |_Row| objects representing the table's rows. |_Row| objects are
        accessed using list notation, e.g. `col = tbl.rows[0]`.
        """
        return _RowCollection(self._tbl, self)

    def fit_to_box(
        self,
        *,
        font_family: str = "Calibri",
        max_font_pt: int = 18,
        min_font_pt: int = 8,
        bold: bool = False,
        italic: bool = False,
        font_file: str | None = None,
    ) -> int:
        """Shrink cell text font size until every cell fits within its bounds.

        Walks every populated cell, computes the per-cell best-fit font
        size against the cell's *own* width and row height (margins
        respected), and applies the **smallest** of those sizes uniformly
        to every cell — so the table reads as a single coherent grid
        rather than each cell at its own size.

        Returns the chosen size in points (clamped to ``min_font_pt``).

        Useful for runtime-driven tables where row counts and string
        lengths aren't known up front.

        Parameters mirror :meth:`TextFrame.fit_text`.
        """
        from power_pptx.text.fonts import FontFiles
        from power_pptx.text.layout import TextFitter
        from power_pptx.util import Emu, Pt

        if min_font_pt <= 0 or max_font_pt < min_font_pt:
            raise ValueError(
                "min_font_pt must be > 0 and max_font_pt must be >= min_font_pt"
            )

        if font_file is None:
            try:
                font_file = FontFiles.find(font_family, bold, italic)
            except (KeyError, OSError):
                font_file = None

        # Default cell margins per OOXML: 0.1" left/right, 0.05" top/bottom.
        DEFAULT_MARG_LR = 91440
        DEFAULT_MARG_TB = 45720

        cols = list(self.columns)
        rows = list(self.rows)

        per_cell_sizes: list[int] = []
        for r_idx, row in enumerate(rows):
            for c_idx, col in enumerate(cols):
                cell = self.cell(r_idx, c_idx)
                if not cell.text.strip():
                    continue
                marL = cell.margin_left if cell.margin_left is not None else DEFAULT_MARG_LR
                marR = cell.margin_right if cell.margin_right is not None else DEFAULT_MARG_LR
                marT = cell.margin_top if cell.margin_top is not None else DEFAULT_MARG_TB
                marB = cell.margin_bottom if cell.margin_bottom is not None else DEFAULT_MARG_TB
                cx = max(1, int(col.width) - int(marL) - int(marR))
                cy = max(1, int(row.height) - int(marT) - int(marB))
                try:
                    size = TextFitter.best_fit_font_size(
                        cell.text, (Emu(cx), Emu(cy)), max_font_pt, font_file
                    )
                except Exception:
                    # If measurement fails for a populated cell, treat it as
                    # the worst case so the final uniform size remains safe
                    # for every populated cell. Skipping the cell would let
                    # ``target = min(...)`` stay artificially high and other
                    # cells could end up still overflowing.
                    per_cell_sizes.append(int(min_font_pt))
                    continue
                if size is None:
                    # Text genuinely does not fit at any size in this cell;
                    # treat as ``min_font_pt``.
                    per_cell_sizes.append(int(min_font_pt))
                else:
                    per_cell_sizes.append(int(size))

        target = min(per_cell_sizes) if per_cell_sizes else max_font_pt
        target = max(target, min_font_pt)

        for cell in self.iter_cells():
            for paragraph in cell.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(target)

        return int(target)

    @property
    def vert_banding(self) -> bool:
        """When `True`, indicates columns should have alternating shading.

        Read/write. Used to allow columns to be traversed more easily without losing track of
        which column is being read.
        """
        return self._tbl.bandCol

    @vert_banding.setter
    def vert_banding(self, value: bool):
        self._tbl.bandCol = value


class _Cell(Subshape):
    """Table cell"""

    def __init__(self, tc: CT_TableCell, parent: ProvidesPart):
        super(_Cell, self).__init__(parent)
        self._tc = tc

    def __eq__(self, other: object) -> bool:
        """|True| if this object proxies the same element as `other`.

        Equality for proxy objects is defined as referring to the same XML element, whether or not
        they are the same proxy object instance.
        """
        if not isinstance(other, type(self)):
            return False
        return self._tc is other._tc

    def __ne__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            return True
        return self._tc is not other._tc

    @lazyproperty
    def borders(self) -> _Borders:
        """|_Borders| value object exposing per-edge border line formatting.

        Each border edge is a |LineFormat| reachable as `borders.left`,
        `borders.right`, `borders.top`, `borders.bottom`, `borders.diagonal_down`,
        and `borders.diagonal_up`. Convenience helpers `borders.all(...)`,
        `borders.outer(...)`, and `borders.none()` apply settings across
        multiple edges in one call.
        """
        return _Borders(self._tc)

    @lazyproperty
    def fill(self) -> FillFormat:
        """|FillFormat| instance for this cell.

        Provides access to fill properties such as foreground color.
        """
        tcPr = self._tc.get_or_add_tcPr()
        return FillFormat.from_fill_parent(tcPr)

    @property
    def is_merge_origin(self) -> bool:
        """True if this cell is the top-left grid cell in a merged cell."""
        return self._tc.is_merge_origin

    @property
    def is_spanned(self) -> bool:
        """True if this cell is spanned by a merge-origin cell.

        A merge-origin cell "spans" the other grid cells in its merge range, consuming their area
        and "shadowing" the spanned grid cells.

        Note this value is |False| for a merge-origin cell. A merge-origin cell spans other grid
        cells, but is not itself a spanned cell.
        """
        return self._tc.is_spanned

    @property
    def margin_left(self) -> Length:
        """Left margin of cells.

        Read/write. If assigned |None|, the default value is used, 0.1 inches for left and right
        margins and 0.05 inches for top and bottom.
        """
        return self._tc.marL

    @margin_left.setter
    def margin_left(self, margin_left: Length | None):
        self._validate_margin_value(margin_left)
        self._tc.marL = margin_left

    @property
    def margin_right(self) -> Length:
        """Right margin of cell."""
        return self._tc.marR

    @margin_right.setter
    def margin_right(self, margin_right: Length | None):
        self._validate_margin_value(margin_right)
        self._tc.marR = margin_right

    @property
    def margin_top(self) -> Length:
        """Top margin of cell."""
        return self._tc.marT

    @margin_top.setter
    def margin_top(self, margin_top: Length | None):
        self._validate_margin_value(margin_top)
        self._tc.marT = margin_top

    @property
    def margin_bottom(self) -> Length:
        """Bottom margin of cell."""
        return self._tc.marB

    @margin_bottom.setter
    def margin_bottom(self, margin_bottom: Length | None):
        self._validate_margin_value(margin_bottom)
        self._tc.marB = margin_bottom

    def merge(self, other_cell: _Cell) -> None:
        """Create merged cell from this cell to `other_cell`.

        This cell and `other_cell` specify opposite corners of the merged cell range. Either
        diagonal of the cell region may be specified in either order, e.g. self=bottom-right,
        other_cell=top-left, etc.

        Raises |ValueError| if the specified range already contains merged cells anywhere within
        its extents or if `other_cell` is not in the same table as `self`.
        """
        tc_range = TcRange(self._tc, other_cell._tc)

        if not tc_range.in_same_table:
            raise ValueError("other_cell from different table")
        if tc_range.contains_merged_cell:
            raise ValueError("range contains one or more merged cells")

        tc_range.move_content_to_origin()

        row_count, col_count = tc_range.dimensions

        for tc in tc_range.iter_top_row_tcs():
            tc.rowSpan = row_count
        for tc in tc_range.iter_left_col_tcs():
            tc.gridSpan = col_count
        for tc in tc_range.iter_except_left_col_tcs():
            tc.hMerge = True
        for tc in tc_range.iter_except_top_row_tcs():
            tc.vMerge = True

    @property
    def span_height(self) -> int:
        """int count of rows spanned by this cell.

        The value of this property may be misleading (often 1) on cells where `.is_merge_origin`
        is not |True|, since only a merge-origin cell contains complete span information. This
        property is only intended for use on cells known to be a merge origin by testing
        `.is_merge_origin`.
        """
        return self._tc.rowSpan

    @property
    def span_width(self) -> int:
        """int count of columns spanned by this cell.

        The value of this property may be misleading (often 1) on cells where `.is_merge_origin`
        is not |True|, since only a merge-origin cell contains complete span information. This
        property is only intended for use on cells known to be a merge origin by testing
        `.is_merge_origin`.
        """
        return self._tc.gridSpan

    def split(self) -> None:
        """Remove merge from this (merge-origin) cell.

        The merged cell represented by this object will be "unmerged", yielding a separate
        unmerged cell for each grid cell previously spanned by this merge.

        Raises |ValueError| when this cell is not a merge-origin cell. Test with
        `.is_merge_origin` before calling.
        """
        if not self.is_merge_origin:
            raise ValueError("not a merge-origin cell; only a merge-origin cell can be sp" "lit")

        tc_range = TcRange.from_merge_origin(self._tc)

        for tc in tc_range.iter_tcs():
            tc.rowSpan = tc.gridSpan = 1
            tc.hMerge = tc.vMerge = False

    @property
    def text(self) -> str:
        """Textual content of cell as a single string.

        The returned string will contain a newline character (`"\\n"`) separating each paragraph
        and a vertical-tab (`"\\v"`) character for each line break (soft carriage return) in the
        cell's text.

        Assignment to `text` replaces all text currently contained in the cell. A newline
        character (`"\\n"`) in the assigned text causes a new paragraph to be started. A
        vertical-tab (`"\\v"`) character in the assigned text causes a line-break (soft
        carriage-return) to be inserted. (The vertical-tab character appears in clipboard text
        copied from PowerPoint as its encoding of line-breaks.)
        """
        return self.text_frame.text

    @text.setter
    def text(self, text: str):
        self.text_frame.text = text

    @property
    def text_frame(self) -> TextFrame:
        """|TextFrame| containing the text that appears in the cell."""
        txBody = self._tc.get_or_add_txBody()
        return TextFrame(txBody, self)

    @property
    def width(self) -> Length:
        """Width of this cell in EMU (the parent column's width).

        Exposed so that :meth:`TextFrame.fit_text` can measure against the
        cell's bounds rather than the whole table when called on
        ``cell.text_frame``.
        """
        tr = self._tc.getparent()
        if tr is None:
            return Emu(0)
        try:
            col_idx = list(tr).index(self._tc)
        except ValueError:
            return Emu(0)
        tbl = tr.getparent()
        if tbl is None:
            return Emu(0)
        try:
            gridCol = tbl.tblGrid.gridCol_lst[col_idx]
        except IndexError:
            return Emu(0)
        return Emu(int(gridCol.w))

    @property
    def height(self) -> Length:
        """Height of this cell in EMU (the parent row's height).

        Exposed so that :meth:`TextFrame.fit_text` can measure against the
        cell's bounds rather than the whole table when called on
        ``cell.text_frame``.
        """
        tr = self._tc.getparent()
        if tr is None:
            return Emu(0)
        return Emu(int(tr.h or 0))

    @property
    def vertical_anchor(self) -> MSO_VERTICAL_ANCHOR | None:
        """Vertical alignment of this cell.

        This value is a member of the :ref:`MsoVerticalAnchor` enumeration or |None|. A value of
        |None| indicates the cell has no explicitly applied vertical anchor setting and its
        effective value is inherited from its style-hierarchy ancestors.

        Assigning |None| to this property causes any explicitly applied vertical anchor setting to
        be cleared and inheritance of its effective value to be restored.
        """
        return self._tc.anchor

    @vertical_anchor.setter
    def vertical_anchor(self, mso_anchor_idx: MSO_VERTICAL_ANCHOR | None):
        self._tc.anchor = mso_anchor_idx

    @staticmethod
    def _validate_margin_value(margin_value: Length | None) -> None:
        """Raise ValueError if `margin_value` is not a positive integer value or |None|."""
        if not isinstance(margin_value, int) and margin_value is not None:
            tmpl = "margin value must be integer or None, got '%s'"
            raise TypeError(tmpl % margin_value)


class _Column(Subshape):
    """Table column"""

    def __init__(self, gridCol: CT_TableCol, parent: _ColumnCollection):
        super(_Column, self).__init__(parent)
        self._parent = parent
        self._gridCol = gridCol
        self._tbl = getattr(parent, "_tbl", None)

    @property
    def width(self) -> Length:
        """Width of column in EMU."""
        return self._gridCol.w

    @width.setter
    def width(self, width: Length):
        self._gridCol.w = width
        self._parent.notify_width_changed()

    @lazyproperty
    def borders(self) -> _LineGroup:
        """Convenience helper for setting borders on every cell in this column.

        Mirrors :class:`_Borders` on a single cell, but applied across the
        whole column.  Examples::

            col.borders.left(width=Pt(2), color=RGBColor(0, 0, 0))
            col.borders.outer(width=Pt(1))
            col.borders.none()
        """
        if self._tbl is None:
            return _LineGroup([])
        return _LineGroup(_iter_column_cells(self._tbl, self._gridCol))


class _Row(Subshape):
    """Table row"""

    def __init__(self, tr: CT_TableRow, parent: _RowCollection):
        super(_Row, self).__init__(parent)
        self._parent = parent
        self._tr = tr

    @property
    def cells(self):
        """Read-only reference to collection of cells in row.

        An individual cell is referenced using list notation, e.g. `cell = row.cells[0]`.
        """
        return _CellCollection(self._tr, self)

    @property
    def height(self) -> Length:
        """Height of row in EMU."""
        return self._tr.h

    @height.setter
    def height(self, height: Length):
        self._tr.h = height
        self._parent.notify_height_changed()

    @lazyproperty
    def borders(self) -> _LineGroup:
        """Convenience helper for setting borders on every cell in this row.

        Mirrors :class:`_Borders` on a single cell, but applied across the
        whole row.  Examples::

            row.borders.bottom(width=Pt(2), color=RGBColor(0, 0, 0))
            row.borders.outer(width=Pt(1))
            row.borders.none()
        """
        return _LineGroup(list(self._tr.tc_lst))


def _iter_column_cells(tbl: CT_Table, gridCol):
    """Return the list of ``CT_TableCell`` elements at this column's grid index."""
    grid = list(tbl.tblGrid.gridCol_lst)
    try:
        col_idx = grid.index(gridCol)
    except ValueError:
        return []
    cells = []
    for tr in tbl.tr_lst:
        tcs = tr.tc_lst
        if col_idx < len(tcs):
            cells.append(tcs[col_idx])
    return cells


class _CellCollection(Subshape):
    """Horizontal sequence of row cells"""

    def __init__(self, tr: CT_TableRow, parent: _Row):
        super(_CellCollection, self).__init__(parent)
        self._parent = parent
        self._tr = tr

    def __getitem__(self, idx: int) -> _Cell:
        """Provides indexed access, (e.g. 'cells[0]')."""
        if idx < 0 or idx >= len(self._tr.tc_lst):
            msg = "cell index [%d] out of range" % idx
            raise IndexError(msg)
        return _Cell(self._tr.tc_lst[idx], self)

    def __iter__(self) -> Iterator[_Cell]:
        """Provides iterability."""
        return (_Cell(tc, self) for tc in self._tr.tc_lst)

    def __len__(self) -> int:
        """Supports len() function (e.g. 'len(cells) == 1')."""
        return len(self._tr.tc_lst)


class _ColumnCollection(Subshape):
    """Sequence of table columns."""

    def __init__(self, tbl: CT_Table, parent: Table):
        super(_ColumnCollection, self).__init__(parent)
        self._parent = parent
        self._tbl = tbl

    def __getitem__(self, idx: int):
        """Provides indexed access, (e.g. 'columns[0]')."""
        if idx < 0 or idx >= len(self._tbl.tblGrid.gridCol_lst):
            msg = "column index [%d] out of range" % idx
            raise IndexError(msg)
        return _Column(self._tbl.tblGrid.gridCol_lst[idx], self)

    def __len__(self):
        """Supports len() function (e.g. 'len(columns) == 1')."""
        return len(self._tbl.tblGrid.gridCol_lst)

    def notify_width_changed(self):
        """Called by a column when its width changes. Pass along to parent."""
        self._parent.notify_width_changed()


class _RowCollection(Subshape):
    """Sequence of table rows"""

    def __init__(self, tbl: CT_Table, parent: Table):
        super(_RowCollection, self).__init__(parent)
        self._parent = parent
        self._tbl = tbl

    def __getitem__(self, idx: int) -> _Row:
        """Provides indexed access, (e.g. 'rows[0]')."""
        if idx < 0 or idx >= len(self):
            msg = "row index [%d] out of range" % idx
            raise IndexError(msg)
        return _Row(self._tbl.tr_lst[idx], self)

    def __len__(self):
        """Supports len() function (e.g. 'len(rows) == 1')."""
        return len(self._tbl.tr_lst)

    def notify_height_changed(self):
        """Called by a row when its height changes. Pass along to parent."""
        self._parent.notify_height_changed()


class _BorderEdge(object):
    """Adapter exposing the |LineFormat| parent contract for one cell-border edge.

    A cell border (`a:lnL`, `a:lnR`, etc.) is itself an `<a:ln>`-shaped element
    living inside `<a:tcPr>`. |LineFormat| expects its parent to expose
    `get_or_add_ln()` and `ln`; this adapter routes those calls to the matching
    edge-specific accessor on `a:tcPr`, so a single |LineFormat| implementation
    serves shape lines and table borders alike.
    """

    def __init__(self, tc: CT_TableCell, edge: str):
        super(_BorderEdge, self).__init__()
        self._tc = tc
        self._edge = edge

    def get_or_add_ln(self) -> CT_LineProperties:
        tcPr = self._tc.get_or_add_tcPr()
        return getattr(tcPr, "get_or_add_%s" % self._edge)()

    @property
    def ln(self) -> CT_LineProperties | None:
        tcPr = self._tc.tcPr
        if tcPr is None:
            return None
        return getattr(tcPr, self._edge)


class _Borders(object):
    """Per-edge line formatting for a table cell.

    Returned by `cell.borders`. Each edge is a |LineFormat|; assignments such
    as `cell.borders.left.color.rgb = RGBColor(...)` materialize the border
    XML on demand. Convenience helpers act on multiple edges in one call.

    Edge accessors (`left`, `right`, etc.) construct a fresh |LineFormat| on
    every access rather than caching one. This keeps the common
    set → ``none()`` → set-again flow correct: after ``none()`` removes the
    underlying ``<a:ln*>`` element, the next access returns a |LineFormat|
    that re-creates the element on first write, instead of writing through
    a stale reference to a detached element.
    """

    def __init__(self, tc: CT_TableCell):
        super(_Borders, self).__init__()
        self._tc = tc

    @property
    def left(self) -> LineFormat:
        """|LineFormat| for the left edge (`a:lnL`)."""
        return LineFormat(_BorderEdge(self._tc, "lnL"))

    @property
    def right(self) -> LineFormat:
        """|LineFormat| for the right edge (`a:lnR`)."""
        return LineFormat(_BorderEdge(self._tc, "lnR"))

    @property
    def top(self) -> LineFormat:
        """|LineFormat| for the top edge (`a:lnT`)."""
        return LineFormat(_BorderEdge(self._tc, "lnT"))

    @property
    def bottom(self) -> LineFormat:
        """|LineFormat| for the bottom edge (`a:lnB`)."""
        return LineFormat(_BorderEdge(self._tc, "lnB"))

    @property
    def diagonal_down(self) -> LineFormat:
        """|LineFormat| for the top-left-to-bottom-right diagonal (`a:lnTlToBr`)."""
        return LineFormat(_BorderEdge(self._tc, "lnTlToBr"))

    @property
    def diagonal_up(self) -> LineFormat:
        """|LineFormat| for the bottom-left-to-top-right diagonal (`a:lnBlToTr`)."""
        return LineFormat(_BorderEdge(self._tc, "lnBlToTr"))

    def all(self, width: Length | None = None, color: tuple[int, int, int] | None = None) -> None:
        """Apply `width` and/or `color` to every border edge (4 sides + 2 diagonals).

        `color` is an `(r, g, b)` 3-tuple of ints in 0–255 (compatible with
        |RGBColor|). Either argument may be |None| to leave that aspect alone.
        """
        for edge in (self.left, self.right, self.top, self.bottom,
                     self.diagonal_down, self.diagonal_up):
            self._apply(edge, width, color)

    def outer(self, width: Length | None = None, color: tuple[int, int, int] | None = None) -> None:
        """Apply `width` and/or `color` to the four outer edges (left/right/top/bottom)."""
        for edge in (self.left, self.right, self.top, self.bottom):
            self._apply(edge, width, color)

    def none(self) -> None:
        """Remove all border edge elements from the cell.

        Restores theme/style inheritance for every edge. Diagonal borders are
        also cleared. Note: |LineFormat| objects retrieved before this call
        cache an internal reference to the now-detached ``<a:ln*>`` element
        and should not be reused; re-access via ``cell.borders.left`` (etc.)
        to get a fresh |LineFormat| over a re-created element.
        """
        tcPr = self._tc.tcPr
        if tcPr is None:
            return
        tcPr._remove_lnL()
        tcPr._remove_lnR()
        tcPr._remove_lnT()
        tcPr._remove_lnB()
        tcPr._remove_lnTlToBr()
        tcPr._remove_lnBlToTr()

    @staticmethod
    def _apply(line: LineFormat, width: Length | None, color: tuple[int, int, int] | None) -> None:
        from power_pptx.dml.color import RGBColor

        if width is not None:
            line.width = width
        if color is not None:
            line.color.rgb = color if isinstance(color, RGBColor) else RGBColor(*color)


class _LineGroup(object):
    """Apply border edges across a group of cells (a row or a column).

    Returned by ``row.borders`` and ``col.borders``.  Each edge accessor
    is callable; calling it with ``width`` and/or ``color`` applies those
    settings to that edge of every cell in the group.
    """

    def __init__(self, tcs):
        self._tcs = tcs

    def _apply_edge(
        self,
        edge: str,
        width: Length | None,
        color,
    ) -> None:
        from power_pptx.dml.color import RGBColor

        for tc in self._tcs:
            line = LineFormat(_BorderEdge(tc, edge))
            if width is not None:
                line.width = width
            if color is not None:
                line.color.rgb = (
                    color if isinstance(color, RGBColor) else RGBColor(*color)
                )

    def left(self, width: Length | None = None, color=None) -> None:
        """Apply *width* and/or *color* to the left edge of every cell."""
        self._apply_edge("lnL", width, color)

    def right(self, width: Length | None = None, color=None) -> None:
        """Apply *width* and/or *color* to the right edge of every cell."""
        self._apply_edge("lnR", width, color)

    def top(self, width: Length | None = None, color=None) -> None:
        """Apply *width* and/or *color* to the top edge of every cell."""
        self._apply_edge("lnT", width, color)

    def bottom(self, width: Length | None = None, color=None) -> None:
        """Apply *width* and/or *color* to the bottom edge of every cell."""
        self._apply_edge("lnB", width, color)

    def all(self, width: Length | None = None, color=None) -> None:
        """Apply *width* and/or *color* to all four outer edges of every cell."""
        for edge in ("lnL", "lnR", "lnT", "lnB"):
            self._apply_edge(edge, width, color)

    outer = all  # alias for parity with ``cell.borders.outer``

    def none(self) -> None:
        """Clear every border edge from every cell in the group."""
        for tc in self._tcs:
            tcPr = tc.tcPr
            if tcPr is None:
                continue
            tcPr._remove_lnL()
            tcPr._remove_lnR()
            tcPr._remove_lnT()
            tcPr._remove_lnB()
            tcPr._remove_lnTlToBr()
            tcPr._remove_lnBlToTr()
