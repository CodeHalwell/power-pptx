"""Geometry primitives — ``BBox`` and friends.

A first-class value object for rectangular slide regions. EMU arithmetic
is verbose and error-prone; ``BBox`` does it for you::

    from power_pptx import BBox, Inches

    bb = BBox.from_inches(1, 2, 8, 4)
    inner = bb.inset(all=Inches(0.2))
    left, right = bb.split_h([1, 1], gap=Inches(0.1))

``BBox`` is immutable, hashable, and unpacks to
``(left, top, width, height)`` so it can be passed in place of the
historical 4-tuple to ``add_shape`` / ``add_textbox`` etc. when those
APIs accept ``*box``.

Every constructor returns a ``BBox`` whose four members are
:class:`~power_pptx.util.Emu` instances — assigning ``bb.left`` to a
shape's ``shape.left`` works straight through.

See the parent skill notes for the full motivation; this module's
existence is item 1.3 of the v2.7-era recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Iterator, Sequence

from power_pptx.util import Emu, Inches, Length, _coerce_emu

if TYPE_CHECKING:
    from power_pptx.shapes.base import BaseShape


__all__ = ["BBox"]


@dataclass(frozen=True)
class BBox:
    """An immutable rectangular region in EMU.

    ``left``, ``top``, ``width``, ``height`` are integer EMU values
    stored as :class:`~power_pptx.util.Emu`.  Negative dimensions are
    rejected; negative positions are accepted (a shape can sit off the
    slide).

    Iteration yields ``(left, top, width, height)`` so the box can be
    splatted into APIs that accept four positional length arguments::

        bb = BBox.from_inches(1, 2, 4, 3)
        rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *bb)
    """

    left: Emu
    top: Emu
    width: Emu
    height: Emu

    def __post_init__(self) -> None:
        # Coerce to Emu so callers can construct from plain ints / floats
        # / Length subclasses without remembering the right wrapper.
        # ``__setattr__`` is needed because the dataclass is frozen.
        for name in ("left", "top", "width", "height"):
            object.__setattr__(self, name, Emu(_coerce_emu(getattr(self, name))))
        if int(self.width) < 0:
            raise ValueError(f"BBox.width must be >= 0, got {int(self.width)}")
        if int(self.height) < 0:
            raise ValueError(f"BBox.height must be >= 0, got {int(self.height)}")

    # -------------------------------------------------------------- constructors

    @classmethod
    def from_shape(cls, shape: "BaseShape") -> "BBox":
        """Return the BBox of a shape (``left``, ``top``, ``width``, ``height``).

        Works for any object exposing those four attributes — shapes,
        pictures, group shapes, placeholders.
        """
        return cls(shape.left, shape.top, shape.width, shape.height)

    @classmethod
    def from_inches(
        cls, left: float, top: float, width: float, height: float
    ) -> "BBox":
        """Construct a BBox with positions in inches."""
        return cls(Inches(left), Inches(top), Inches(width), Inches(height))

    @classmethod
    def from_emu(
        cls, left: int, top: int, width: int, height: int
    ) -> "BBox":
        """Construct a BBox with positions in raw EMU."""
        return cls(Emu(left), Emu(top), Emu(width), Emu(height))

    @classmethod
    def from_slide(cls, slide) -> "BBox":
        """Return the BBox covering the full slide area."""
        prs = slide.part.package.presentation_part.presentation
        return cls(Emu(0), Emu(0), Emu(int(prs.slide_width)), Emu(int(prs.slide_height)))

    # -------------------------------------------------------------- properties

    @property
    def right(self) -> Emu:
        """X coordinate of the right edge (``left + width``)."""
        return Emu(int(self.left) + int(self.width))

    @property
    def bottom(self) -> Emu:
        """Y coordinate of the bottom edge (``top + height``)."""
        return Emu(int(self.top) + int(self.height))

    @property
    def cx(self) -> Emu:
        """Horizontal centre of the box."""
        return Emu(int(self.left) + int(self.width) // 2)

    @property
    def cy(self) -> Emu:
        """Vertical centre of the box."""
        return Emu(int(self.top) + int(self.height) // 2)

    @property
    def area(self) -> int:
        return int(self.width) * int(self.height)

    # -------------------------------------------------------------- iteration

    def __iter__(self) -> Iterator[Emu]:
        # Order matches the historical (left, top, width, height)
        # positional argument convention used across add_shape, add_textbox,
        # add_picture, etc.
        yield self.left
        yield self.top
        yield self.width
        yield self.height

    def as_tuple(self) -> tuple[Emu, Emu, Emu, Emu]:
        """Return ``(left, top, width, height)``."""
        return (self.left, self.top, self.width, self.height)

    # -------------------------------------------------------------- transforms

    def shifted(self, dx: int = 0, dy: int = 0) -> "BBox":
        """Return a new BBox translated by ``(dx, dy)`` EMU."""
        return BBox(
            Emu(int(self.left) + int(dx)),
            Emu(int(self.top) + int(dy)),
            self.width,
            self.height,
        )

    def resized(
        self,
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> "BBox":
        """Return a new BBox with ``width`` and/or ``height`` overridden."""
        return BBox(
            self.left,
            self.top,
            Emu(int(width)) if width is not None else self.width,
            Emu(int(height)) if height is not None else self.height,
        )

    def inset(
        self,
        *,
        all: int | None = None,
        x: int | None = None,
        y: int | None = None,
        left: int | None = None,
        top: int | None = None,
        right: int | None = None,
        bottom: int | None = None,
    ) -> "BBox":
        """Return a BBox shrunk inwards by the given padding amounts.

        ``all`` sets every side; ``x`` sets left+right; ``y`` sets
        top+bottom; the four per-edge kwargs override anything else.
        Defaults to zero — equivalent to a no-op when called with no args.

        Negative values expand the box outward.
        """
        l_in = _resolve_inset(left, x, all, 0)
        r_in = _resolve_inset(right, x, all, 0)
        t_in = _resolve_inset(top, y, all, 0)
        b_in = _resolve_inset(bottom, y, all, 0)
        new_left = int(self.left) + l_in
        new_top = int(self.top) + t_in
        new_w = int(self.width) - l_in - r_in
        new_h = int(self.height) - t_in - b_in
        if new_w < 0:
            new_w = 0
        if new_h < 0:
            new_h = 0
        return BBox(Emu(new_left), Emu(new_top), Emu(new_w), Emu(new_h))

    def sub(self, fx: float, fy: float, fw: float, fh: float) -> "BBox":
        """Return a normalised sub-box (each arg in ``[0.0, 1.0]``).

        ``fx``/``fy`` are relative offsets, ``fw``/``fh`` are relative
        widths/heights — so ``box.sub(0.25, 0, 0.5, 1.0)`` returns the
        middle-half-width strip of the box.
        """
        return BBox(
            Emu(int(self.left) + int(round(fx * int(self.width)))),
            Emu(int(self.top) + int(round(fy * int(self.height)))),
            Emu(int(round(fw * int(self.width)))),
            Emu(int(round(fh * int(self.height)))),
        )

    # -------------------------------------------------------------- splits

    def split_h(
        self, ratios: Sequence[float], gap: int = 0
    ) -> list["BBox"]:
        """Split horizontally into N columns with the given ratios.

        ``ratios=[1, 1]`` produces two equal columns; ``[2, 1]`` makes
        the first column twice as wide as the second.  ``gap`` is the
        EMU gap between consecutive columns.
        """
        return _split(self, ratios, gap, axis="h")

    def split_v(
        self, ratios: Sequence[float], gap: int = 0
    ) -> list["BBox"]:
        """Split vertically into N rows with the given ratios."""
        return _split(self, ratios, gap, axis="v")

    def grid(
        self,
        cols: int,
        rows: int = 1,
        *,
        gap_x: int = 0,
        gap_y: int = 0,
    ) -> list["BBox"]:
        """Return a flat list of ``cols * rows`` equal cells (row-major)."""
        if cols < 1 or rows < 1:
            raise ValueError(
                f"cols and rows must be >= 1; got cols={cols}, rows={rows}"
            )
        col_boxes = _split(self, [1] * cols, gap_x, axis="h")
        cells: list[BBox] = []
        for col in col_boxes:
            cells.append(col)  # placeholder, replaced below
        # Build a row-major list by splitting each column vertically.
        result: list[BBox] = []
        for r in range(rows):
            for c in range(cols):
                row_split = _split(col_boxes[c], [1] * rows, gap_y, axis="v")
                result.append(row_split[r])
        return result

    # -------------------------------------------------------------- geometric

    def contains(self, other: "BBox", *, tol: int = 0) -> bool:
        """True if ``other`` lies entirely inside this box (within ``tol``)."""
        return (
            int(other.left) >= int(self.left) - tol
            and int(other.top) >= int(self.top) - tol
            and int(other.right) <= int(self.right) + tol
            and int(other.bottom) <= int(self.bottom) + tol
        )

    def intersects(self, other: "BBox") -> bool:
        """True if this box overlaps ``other`` (touching edges count as overlap)."""
        return not (
            int(self.right) <= int(other.left)
            or int(other.right) <= int(self.left)
            or int(self.bottom) <= int(other.top)
            or int(other.bottom) <= int(self.top)
        )

    def intersection(self, other: "BBox") -> "BBox":
        """Return the overlapping region, or a zero-area box if none."""
        ix = max(int(self.left), int(other.left))
        iy = max(int(self.top), int(other.top))
        ix2 = min(int(self.right), int(other.right))
        iy2 = min(int(self.bottom), int(other.bottom))
        if ix2 < ix or iy2 < iy:
            return BBox(Emu(ix), Emu(iy), Emu(0), Emu(0))
        return BBox(Emu(ix), Emu(iy), Emu(ix2 - ix), Emu(iy2 - iy))

    def union(self, other: "BBox") -> "BBox":
        """Return the smallest box enclosing both rectangles."""
        ix = min(int(self.left), int(other.left))
        iy = min(int(self.top), int(other.top))
        ix2 = max(int(self.right), int(other.right))
        iy2 = max(int(self.bottom), int(other.bottom))
        return BBox(Emu(ix), Emu(iy), Emu(ix2 - ix), Emu(iy2 - iy))

    # -------------------------------------------------------------- application

    def apply_to(self, shape: "BaseShape") -> "BaseShape":
        """Set ``shape.left/top/width/height`` from this box."""
        shape.left = self.left
        shape.top = self.top
        shape.width = self.width
        shape.height = self.height
        return shape


def _resolve_inset(
    edge: int | None,
    axis: int | None,
    all_: int | None,
    default: int,
) -> int:
    """Combine the inset kwargs in order of specificity."""
    if edge is not None:
        return int(edge)
    if axis is not None:
        return int(axis)
    if all_ is not None:
        return int(all_)
    return default


def _split(
    box: BBox, ratios: Sequence[float], gap: int, *, axis: str
) -> list[BBox]:
    if not ratios:
        raise ValueError("ratios must not be empty")
    if any(r < 0 for r in ratios):
        raise ValueError("ratios must be non-negative")
    total = float(sum(ratios))
    if total <= 0:
        raise ValueError("at least one ratio must be > 0")

    if axis == "h":
        span = int(box.width) - int(gap) * (len(ratios) - 1)
        if span < 0:
            raise ValueError(
                f"horizontal gaps ({len(ratios) - 1}×{int(gap)}) consume the "
                f"entire box width ({int(box.width)} EMU)"
            )
        widths = [int(round(span * r / total)) for r in ratios]
        out: list[BBox] = []
        cursor = int(box.left)
        for w in widths:
            out.append(BBox(Emu(cursor), box.top, Emu(w), box.height))
            cursor += w + int(gap)
        return out
    elif axis == "v":
        span = int(box.height) - int(gap) * (len(ratios) - 1)
        if span < 0:
            raise ValueError(
                f"vertical gaps ({len(ratios) - 1}×{int(gap)}) consume the "
                f"entire box height ({int(box.height)} EMU)"
            )
        heights = [int(round(span * r / total)) for r in ratios]
        out2: list[BBox] = []
        cursor = int(box.top)
        for h in heights:
            out2.append(BBox(box.left, Emu(cursor), box.width, Emu(h)))
            cursor += h + int(gap)
        return out2
    else:
        raise ValueError(f"axis must be 'h' or 'v'; got {axis!r}")
