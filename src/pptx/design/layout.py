"""Build-time layout helpers — :class:`Grid` and :class:`Stack`.

These objects compute ``(left, top, width, height)`` rectangles so callers
don't eyeball EMU values when placing shapes. They never read or mutate
slide XML on their own; geometry is only applied to a shape when the
caller passes it to :meth:`Grid.place` / :meth:`Stack.place` or assigns
the returned :class:`Box` to the shape's geometry properties directly.

Example::

    from pptx import Presentation
    from pptx.design.layout import Grid, Stack
    from pptx.util import Inches, Pt

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    grid = Grid(slide, cols=12, rows=6, gutter=Pt(12), margin=Inches(0.5))
    title_box = grid.cell(col=0, row=0, col_span=12, row_span=1)

    stack = Stack(
        direction="vertical", gap=Pt(8),
        left=Inches(0.5), top=Inches(2),
        width=Inches(9),
    )
    bullet_one = stack.next(height=Inches(0.5))
    bullet_two = stack.next(height=Inches(0.5))
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, Tuple, Union

from pptx.util import Emu, Length

if TYPE_CHECKING:
    from pptx.shapes.base import BaseShape
    from pptx.slide import Slide

MarginSpec = Union[
    int,
    Length,
    Tuple[int, int],
    Tuple[int, int, int, int],
]


class Box(NamedTuple):
    """A rectangular region expressed as ``(left, top, width, height)``.

    All four members are :class:`~pptx.util.Length` (EMU) instances and so
    can be assigned directly to a shape's positional properties::

        box = grid.cell(col=0, row=0, col_span=6)
        shape.left, shape.top = box.left, box.top
        shape.width, shape.height = box.width, box.height
    """

    left: Length
    top: Length
    width: Length
    height: Length


def _slide_dimensions(slide: "Slide") -> tuple[Length, Length]:
    """Return ``(slide_width, slide_height)`` for `slide`.

    Raises :class:`ValueError` if either dimension is unset on the host
    presentation.
    """
    presentation = slide.part.package.presentation_part.presentation
    width, height = presentation.slide_width, presentation.slide_height
    if width is None or height is None:
        raise ValueError(
            "slide width/height must be set on the presentation to use a Grid"
        )
    return width, height


def _apply_box(shape: "BaseShape", box: Box) -> "BaseShape":
    shape.left, shape.top = box.left, box.top
    shape.width, shape.height = box.width, box.height
    return shape


class Grid:
    """A column/row grid spanning a slide's content area.

    Parameters
    ----------
    slide : Slide
        Host slide. Used only to read the parent presentation's slide
        dimensions; the slide is not mutated.
    cols : int
        Number of columns. Must be >= 1.
    rows : int, optional
        Number of rows. Defaults to 1; cells implicitly span the full
        slide height when only one row is requested.
    gutter : Length, optional
        Spacing between cells, applied between columns and between rows.
        Defaults to 0 (no gutter).
    margin : Length or tuple, optional
        Outer margin. Either a single :class:`Length` (uniform on all
        four sides), or a 2-tuple ``(vertical, horizontal)``, or a
        4-tuple ``(top, right, bottom, left)``. Defaults to 0.
    """

    def __init__(
        self,
        slide: "Slide",
        cols: int,
        rows: int = 1,
        gutter: int = 0,
        margin: MarginSpec = 0,
    ):
        if cols < 1:
            raise ValueError("Grid.cols must be >= 1, got %r" % cols)
        if rows < 1:
            raise ValueError("Grid.rows must be >= 1, got %r" % rows)

        self._cols = int(cols)
        self._rows = int(rows)
        self._gutter = Emu(int(gutter))
        self._top_m, self._right_m, self._bottom_m, self._left_m = self._coerce_margin(
            margin
        )

        slide_w, slide_h = _slide_dimensions(slide)
        self._slide_width = slide_w
        self._slide_height = slide_h

        usable_w = slide_w - self._left_m - self._right_m - self._gutter * (self._cols - 1)
        usable_h = slide_h - self._top_m - self._bottom_m - self._gutter * (self._rows - 1)
        if usable_w <= 0 or usable_h <= 0:
            raise ValueError(
                "grid margins+gutters consume the entire slide; reduce them"
            )
        # store as float so col_span math is exact; we round on emission
        self._col_w = usable_w / self._cols
        self._row_h = usable_h / self._rows

    @property
    def cols(self) -> int:
        return self._cols

    @property
    def rows(self) -> int:
        return self._rows

    def cell(self, col: int = 0, row: int = 0, col_span: int = 1, row_span: int = 1) -> Box:
        """Return the :class:`Box` for the cell starting at (`col`, `row`).

        `col_span` and `row_span` extend the cell across additional
        columns/rows. Negative indices and out-of-bounds spans raise
        :class:`IndexError`.
        """
        if col < 0 or row < 0:
            raise IndexError("col/row must be non-negative")
        if col_span < 1 or row_span < 1:
            raise IndexError("col_span/row_span must be >= 1")
        if col + col_span > self._cols or row + row_span > self._rows:
            raise IndexError(
                "cell (col=%d, row=%d, col_span=%d, row_span=%d) exceeds "
                "%dx%d grid" % (col, row, col_span, row_span, self._cols, self._rows)
            )

        left = self._left_m + (self._col_w + self._gutter) * col
        top = self._top_m + (self._row_h + self._gutter) * row
        width = self._col_w * col_span + self._gutter * (col_span - 1)
        height = self._row_h * row_span + self._gutter * (row_span - 1)
        return Box(
            Emu(int(round(left))),
            Emu(int(round(top))),
            Emu(int(round(width))),
            Emu(int(round(height))),
        )

    def place(
        self,
        shape: "BaseShape",
        col: int = 0,
        row: int = 0,
        col_span: int = 1,
        row_span: int = 1,
    ) -> "BaseShape":
        """Move `shape` to the cell at (`col`, `row`) with the given span.

        Returns the shape so calls can be chained.
        """
        return _apply_box(shape, self.cell(col, row, col_span, row_span))

    @staticmethod
    def _coerce_margin(margin: MarginSpec) -> Tuple[Length, Length, Length, Length]:
        if isinstance(margin, (tuple, list)):
            if len(margin) == 2:
                v, h = margin
                return Emu(int(v)), Emu(int(h)), Emu(int(v)), Emu(int(h))
            if len(margin) == 4:
                top, right, bottom, left = margin
                return Emu(int(top)), Emu(int(right)), Emu(int(bottom)), Emu(int(left))
            raise ValueError(
                "margin tuple must have 2 or 4 elements, got %d" % len(margin)
            )
        m = Emu(int(margin))
        return m, m, m, m


class Stack:
    """A linear stack of cells laid out vertically or horizontally.

    Parameters
    ----------
    direction : str
        ``"vertical"`` (default) stacks downward; ``"horizontal"`` stacks
        rightward.
    gap : Length
        Spacing between consecutive cells. Defaults to 0.
    left, top : Length
        Origin of the first cell. Default 0.
    width, height : Length, optional
        Cross-axis span. For a vertical stack, `width` is the cell width
        and each call to :meth:`next` consumes `height`; for a horizontal
        stack, `height` is the cell height and each call consumes `width`.

    The stack maintains a running cursor that advances after every
    :meth:`next` (or :meth:`place`) call. :meth:`reset` returns the
    cursor to the origin.
    """

    _AXES = ("vertical", "horizontal")

    def __init__(
        self,
        direction: str = "vertical",
        gap: int = 0,
        left: int = 0,
        top: int = 0,
        width: int | None = None,
        height: int | None = None,
    ):
        if direction not in self._AXES:
            raise ValueError(
                "direction must be 'vertical' or 'horizontal', got %r" % direction
            )
        self._direction = direction
        self._gap = Emu(int(gap))
        self._origin_left = Emu(int(left))
        self._origin_top = Emu(int(top))
        self._width = None if width is None else Emu(int(width))
        self._height = None if height is None else Emu(int(height))
        self._cursor = 0

    @property
    def direction(self) -> str:
        return self._direction

    def reset(self) -> None:
        """Reset the cursor so the next :meth:`next` call starts at the origin."""
        self._cursor = 0

    def next(self, *, width: int | None = None, height: int | None = None) -> Box:
        """Allocate the next cell and return its :class:`Box`.

        For a vertical stack, `height` is required; `width` overrides the
        stack-level default. For a horizontal stack, `width` is required;
        `height` overrides the stack-level default.
        """
        leading_gap = 0 if self._cursor == 0 else int(self._gap)

        if self._direction == "vertical":
            if height is None:
                raise TypeError("vertical Stack.next() requires `height=`")
            cell_h = int(height)
            cell_w = self._width if width is None else int(width)
            if cell_w is None:
                raise TypeError(
                    "vertical Stack needs a `width` "
                    "(either on the constructor or as a per-cell override)"
                )
            self._cursor += leading_gap
            box = Box(
                self._origin_left,
                Emu(self._origin_top + self._cursor),
                Emu(cell_w),
                Emu(cell_h),
            )
            self._cursor += cell_h
        else:
            if width is None:
                raise TypeError("horizontal Stack.next() requires `width=`")
            cell_w = int(width)
            cell_h = self._height if height is None else int(height)
            if cell_h is None:
                raise TypeError(
                    "horizontal Stack needs a `height` "
                    "(either on the constructor or as a per-cell override)"
                )
            self._cursor += leading_gap
            box = Box(
                Emu(self._origin_left + self._cursor),
                self._origin_top,
                Emu(cell_w),
                Emu(cell_h),
            )
            self._cursor += cell_w
        return box

    def place(
        self,
        shape: "BaseShape",
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> "BaseShape":
        """Allocate the next cell and apply it to `shape`.

        Returns the shape so calls can be chained.
        """
        return _apply_box(shape, self.next(width=width, height=height))
