"""Declarative native components with measurement, padding, and nested layout.

The component tree is measured before slide mutation. Rendered text and shapes
remain ordinary editable PowerPoint objects; no HTML renderer is involved.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Sequence

from power_pptx._color import coerce_color
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import MSO_AUTO_SIZE
from power_pptx.geometry import BBox
from power_pptx.text.fonts import (
    WEIGHT_NAMES,
    drawing_family,
    find_font_file,
    font_face_family,
    resolve_weight,
)
from power_pptx.text.layout import TextFitter
from power_pptx.text.measurement import TextMeasurement, measure_text, truncate_text
from power_pptx.util import Emu, Pt

if TYPE_CHECKING:
    from power_pptx.design.tokens import DesignTokens
    from power_pptx.slide import Slide


class LayoutOverflowError(ValueError):
    """A component cannot fit its region at its requested minimum sizes."""


class LayoutWarning(UserWarning):
    """A layout fits but will look wrong, e.g. a stretched column ends short."""


#: Spare height a stretched column may leave under its last panel before
#: preflight reports a ragged bottom edge.
RAGGED_TOLERANCE = Pt(1.5)


@dataclass
class LayoutResult:
    bbox: BBox
    shapes: list[Any] = field(default_factory=list)
    named: dict[str, Any] = field(default_factory=dict)
    estimated_fonts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __getitem__(self, name: str):
        return self.named[name]


class Component:
    """Base for native components; lengths use EMU through Inches/Pt helpers."""

    width = None
    height = None
    grow = 0.0
    name = None

    def render(
        self,
        slide: Slide,
        bbox: BBox,
        *,
        tokens: DesignTokens | None = None,
        strict_fonts: bool = False,
    ) -> LayoutResult:
        """Preflight the tree, then create editable objects inside ``bbox``.

        Explicit dimensions are fixed; other row widths share available space.
        Column heights are measured from their content. ``grow`` distributes
        spare height to selected column children; ``fill_last`` gives it to the
        last child. Invalid layouts raise before shape creation. A column that a
        row stretches past its content, leaving space under a filled or bordered
        last child, emits :class:`LayoutWarning` and is listed in
        ``result.warnings``. Custom NativeContent builders own their side effects.
        """
        context = _Context(tokens, strict_fonts)
        _validate(self, context, set())
        plan = _plan(self, bbox, context)
        result = LayoutResult(bbox)
        result.warnings.extend(context.warnings)
        for message in context.warnings:
            warnings.warn(message, LayoutWarning, stacklevel=2)
        _draw(plan, slide, context, result)
        return result


@dataclass
class TextBlock(Component):
    text: str
    size_pt: int = 18
    min_size_pt: int = 12
    font: str | None = None
    font_file: str | None = None
    color: Any = "neutral"
    bold: bool = False
    italic: bool = False
    line_spacing: float = 1.2
    max_lines: int | None = None
    preserve_breaks: bool = False
    align: str = "left"
    anchor: str = "top"
    width: int | None = None
    height: int | None = None
    grow: float = 0.0
    name: str | None = None
    weight: int | str | None = None
    letter_spacing: int = 0
    case: str | None = None


@dataclass
class Container(Component):
    children: Sequence[Component]
    direction: str = "vertical"
    padding: Any = 0
    gap: int = Pt(12)
    fill: Any = None
    border: Any = None
    radius: int = 0
    align: str = "stretch"
    justify: str = "start"
    width: int | None = None
    height: int | None = None
    grow: float = 0.0
    name: str | None = None
    fill_last: bool = False


class Row(Container):
    def __init__(self, children: Sequence[Component], **kwargs):
        super().__init__(children, direction="horizontal", **kwargs)


class Column(Container):
    def __init__(self, children: Sequence[Component], **kwargs):
        super().__init__(children, direction="vertical", **kwargs)


class Card(Column):
    def __init__(self, children: Sequence[Component], **kwargs):
        options = {
            "padding": Pt(18),
            "gap": Pt(12),
            "fill": "surface",
            "border": "#DCE3ED",
            "radius": Pt(12),
        }
        options.update(kwargs)
        super().__init__(children, **options)


class Badge(Column):
    def __init__(
        self,
        text: str,
        *,
        size_pt: int = 12,
        font: str | None = None,
        color: Any = "#4838B3",
        fill: Any = "#EDEAFF",
        **kwargs,
    ):
        self.label = TextBlock(
            text,
            size_pt=size_pt,
            min_size_pt=size_pt,
            font=font,
            color=color,
            bold=True,
            max_lines=1,
            align="center",
        )
        options = {"padding": (Pt(6), Pt(10)), "gap": 0, "fill": fill, "radius": Pt(8)}
        options.update(kwargs)
        super().__init__([self.label], **options)


class MetricTile(Card):
    def __init__(
        self,
        value: str,
        label: str,
        *,
        detail: str | None = None,
        accent: Any = "primary",
        font: str | None = None,
        **kwargs,
    ):
        children = [
            TextBlock(label, size_pt=14, font=font, color="muted"),
            TextBlock(
                value, size_pt=38, min_size_pt=24, font=font, color=accent, bold=True, max_lines=1
            ),
        ]
        if detail is not None:
            children.append(TextBlock(detail, size_pt=14, font=font, color="muted"))
        super().__init__(children, **kwargs)


@dataclass
class NativeContent(Component):
    """A fixed-height slot for a chart, table, figure, or custom native builder.

    The callable receives ``(slide, bbox)`` and may return one shape or a
    sequence. Layout preflight cannot validate the callable's own behavior.
    """

    builder: Callable
    height: int
    width: int | None = None
    grow: float = 0.0
    name: str | None = None


@dataclass
class DataTable(Component):
    """A native table whose row heights are measured from its cell text.

    ``rows`` holds cell values (converted with ``str``); with ``header`` the
    first row is styled as a header. ``columns`` gives relative column widths
    (equal by default). Cells wrap; ``max_lines`` caps each cell, and with
    ``truncate=True`` over-long cells are cut with an ellipsis instead of
    raising :class:`LayoutOverflowError`. ``align`` is one value or one per
    column. The table takes the measured height at the top of its region.
    """

    rows: Sequence[Sequence[Any]]
    header: bool = True
    columns: Sequence[float] | None = None
    size_pt: int = 12
    font: str | None = None
    color: Any = "neutral"
    header_color: Any = "neutral"
    header_fill: Any = "#EEF2F7"
    fill: Any = None
    border: Any = "#DCE3ED"
    cell_padding: Any = (Pt(4), Pt(6))
    line_spacing: float = 1.2
    max_lines: int | None = None
    truncate: bool = False
    align: Any = "left"
    width: int | None = None
    height: int | None = None
    grow: float = 0.0
    name: str | None = None


@dataclass
class _TableLayout:
    widths: list[int]
    heights: list[int]
    lines: list[list[tuple[str, ...]]]
    font_size_pt: int
    estimated: bool
    family: str | None = None


@dataclass
class _Face:
    family: str | None
    path: str | None
    draw_family: str | None
    draw_bold: bool
    estimated: bool


@dataclass
class _Context:
    tokens: Any
    strict_fonts: bool
    warnings: list[str] = field(default_factory=list)

    def color(self, value):
        if value is None:
            return None
        palette = self.tokens.palette if self.tokens is not None else {}
        defaults = {
            "neutral": "#172334",
            "primary": "#6554E8",
            "surface": "#FFFFFF",
            "muted": "#526176",
        }
        if isinstance(value, str):
            value = palette.get(value, defaults.get(value, value))
        return coerce_color(value)

    def font(self, node):
        if node.font is not None:
            return node.font
        if self.tokens is not None and "body" in self.tokens.typography:
            return self.tokens.typography["body"].family
        return None


@dataclass
class _Plan:
    node: Component
    bbox: BBox
    children: list[_Plan] = field(default_factory=list)
    text: TextMeasurement | None = None
    table: _TableLayout | None = None


def _insets(value):
    if isinstance(value, (int, float)):
        values = (value,) * 4
    elif len(value) == 2:
        values = (value[0], value[1], value[0], value[1])
    elif len(value) == 4:
        values = value
    else:
        raise ValueError("padding must be a length, a pair, or four lengths")
    if any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("padding cannot be negative or non-finite")
    return tuple(round(v) for v in values)


def _validate(node, context, names):
    if not isinstance(node, (Container, TextBlock, NativeContent, DataTable)):
        raise TypeError("children must be native Component objects")
    if id(node) in names:
        raise ValueError("Component trees cannot contain cycles or reuse the same instance")
    names.add(id(node))
    for value in (node.width, node.height):
        if value is not None and (not math.isfinite(value) or value <= 0):
            raise ValueError("component dimensions must be finite and positive")
    if not math.isfinite(node.grow) or node.grow < 0:
        raise ValueError("grow must be finite and non-negative")
    if node.name is not None:
        if node.name in names:
            raise ValueError(f"Duplicate component name: {node.name!r}")
        names.add(node.name)
    if isinstance(node, Container):
        _insets(node.padding)
        if (
            not math.isfinite(node.gap)
            or node.gap < 0
            or not math.isfinite(node.radius)
            or node.radius < 0
        ):
            raise ValueError("gap and radius must be non-negative")
        if node.direction not in {"horizontal", "vertical"}:
            raise ValueError("direction must be horizontal or vertical")
        if node.align not in {"start", "center", "end", "stretch"}:
            raise ValueError("align must be start, center, end, or stretch")
        if node.justify not in {"start", "center", "end", "space-between"}:
            raise ValueError("justify must be start, center, end, or space-between")
        context.color(node.fill)
        context.color(node.border)
        if node.fill_last:
            if node.direction != "vertical":
                raise ValueError("fill_last applies to vertical containers")
            if node.children and node.children[-1].height is not None:
                raise ValueError("fill_last needs a last child without a fixed height")
        for child in node.children:
            _validate(child, context, names)
    elif isinstance(node, TextBlock):
        context.color(node.color)
        if node.align not in {"left", "center", "right", "justify"}:
            raise ValueError("invalid text align")
        if node.anchor not in {"top", "middle", "bottom"}:
            raise ValueError("invalid text anchor")
        if node.case not in {None, "upper", "lower"}:
            raise ValueError("case must be 'upper', 'lower', or None")
        if not math.isfinite(node.letter_spacing):
            raise ValueError("letter_spacing must be finite")
        resolve_weight(node.weight, node.bold)
    elif isinstance(node, DataTable):
        _validate_table(node, context)


def _validate_table(node, context):
    if not node.rows or not all(len(row) == len(node.rows[0]) for row in node.rows):
        raise ValueError("DataTable rows must be non-empty and rectangular")
    count = len(node.rows[0])
    if count == 0:
        raise ValueError("DataTable rows need at least one column")
    if node.columns is not None and (
        len(node.columns) != count or any(not math.isfinite(w) or w <= 0 for w in node.columns)
    ):
        raise ValueError("DataTable columns must give one positive weight per column")
    aligns = [node.align] * count if isinstance(node.align, str) else list(node.align)
    if len(aligns) != count or any(a not in {"left", "center", "right"} for a in aligns):
        raise ValueError("DataTable align must be left/center/right, once or per column")
    lines = node.max_lines
    if lines is not None and (isinstance(lines, bool) or not isinstance(lines, int) or lines < 1):
        raise ValueError("max_lines must be a positive integer or None")
    if node.truncate and node.max_lines is None:
        raise ValueError("truncate=True needs max_lines")
    if isinstance(node.size_pt, bool) or not isinstance(node.size_pt, int) or node.size_pt < 1:
        raise ValueError("size_pt must be a positive integer")
    if not math.isfinite(node.line_spacing) or node.line_spacing <= 0:
        raise ValueError("line_spacing must be finite and positive")
    _insets(node.cell_padding)
    for value in (node.color, node.header_color, node.header_fill, node.fill, node.border):
        context.color(value)


def _table_layout(node, width, context):
    count = len(node.rows[0])
    weights = list(node.columns) if node.columns is not None else [1.0] * count
    total = sum(weights)
    widths, cursor, cumulative = [], 0, 0.0
    for weight in weights:
        cumulative += weight
        edge = round(width * cumulative / total)
        widths.append(edge - cursor)
        cursor = edge
    t, r, b, left_pad = _insets(node.cell_padding)
    family = context.font(node)
    lookup = family or "Calibri"
    heights, lines, estimated = [], [], False
    for row_index, row in enumerate(node.rows):
        bold = node.header and row_index == 0
        path = find_font_file(lookup, bold, False)
        if path is None:
            if context.strict_fonts:
                raise ValueError(
                    f"Font {lookup!r} is unavailable; install it or register its folder"
                )
            estimated = True
        row_lines, row_height = [], 0
        for column, value in enumerate(row):
            inner = widths[column] - left_pad - r
            if inner <= 0:
                raise LayoutOverflowError(
                    f"DataTable {node.name or ''!r} padding consumes a column"
                )
            text = "" if value is None else str(value)
            if node.truncate:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    text = truncate_text(
                        text,
                        Emu(inner),
                        max_lines=node.max_lines or 1,
                        size_pt=node.size_pt,
                        font_family=family,
                        font_file=path,
                        bold=bold,
                    )
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    m = measure_text(
                        text,
                        Emu(inner),
                        size_pt=node.size_pt,
                        font_family=family,
                        font_file=path,
                        bold=bold,
                        line_spacing=node.line_spacing,
                    )
            except ValueError as exc:
                raise LayoutOverflowError(
                    f"DataTable {node.name or ''!r} cell ({row_index}, {column}) cannot fit: {exc}"
                ) from None
            if node.max_lines is not None and len(m.lines) > node.max_lines:
                raise LayoutOverflowError(
                    f"DataTable {node.name or ''!r} cell ({row_index}, {column}) needs "
                    f"{len(m.lines)} lines; max_lines is {node.max_lines}"
                )
            row_lines.append(m.lines)
            line = _rendered_line_height(path, node.size_pt, node.line_spacing)
            row_height = max(row_height, line * len(m.lines))
        heights.append(row_height + t + b)
        lines.append(row_lines)
    regular = find_font_file(lookup)
    return _TableLayout(
        widths, heights, lines, node.size_pt, estimated, drawing_family(family, regular)
    )


def _rendered_line_height(font_file, size_pt, line_spacing):
    """EMU per line as table cells render it: percentage spacing scales the
    font's own line height (ascent + descent), not the point size. Table rows
    grow to fit, so measuring with the point size alone under-reserves them.
    """
    em = 1.2
    if font_file is not None:
        try:
            from PIL import ImageFont

            ascent, descent = ImageFont.truetype(font_file, 1000).getmetrics()
            em = (ascent + descent) / 1000
        except OSError:
            pass
    return math.ceil(size_pt * line_spacing * em * 12700)


def _display_text(node):
    if node.case == "upper":
        return node.text.upper()
    if node.case == "lower":
        return node.text.lower()
    return node.text


def _face(node, context):
    """Resolve the font file that measures `node` and the face that draws it.

    PowerPoint has no weight attribute: regular and bold use the family plus
    ``b``; other weights are selected by the face's legacy family name.
    """
    family = context.font(node)
    lookup = family or "Calibri"
    weight = resolve_weight(node.weight, node.bold)
    path = node.font_file or find_font_file(lookup, italic=node.italic, weight=weight)
    if weight in (400, 700):
        draw = family if node.font_file else drawing_family(family, path)
        return _Face(family, path, draw, weight == 700, False)
    if path is not None:
        return _Face(family, path, font_face_family(path) or family, False, False)
    if context.strict_fonts:
        raise ValueError(
            f"Font {lookup!r} {WEIGHT_NAMES[weight]} is unavailable; "
            "register its file or folder, or pass font_file"
        )
    # Draw what was measured: the nearest regular/bold face, flagged as estimated.
    nearest_bold = weight >= 600
    path = find_font_file(lookup, nearest_bold, node.italic)
    return _Face(family, path, drawing_family(family, path), nearest_bold, True)


def _text_measure(node, width, height, context):
    face = _face(node, context)
    family, path = face.family, face.path
    if path is None and context.strict_fonts:
        raise ValueError(
            f"Font {family or 'Calibri'!r} is unavailable; install it, register its "
            "folder with register_font_dir, or pass font_file"
        )
    text = _display_text(node)
    size = TextFitter.best_fit_font_size(
        text,
        (Emu(width), Emu(height)),
        node.size_pt,
        path,
        min_size=node.min_size_pt,
        max_lines=node.max_lines,
        preserve_breaks=node.preserve_breaks,
        line_spacing=node.line_spacing,
        letter_spacing=int(node.letter_spacing),
    )
    if size is None:
        raise LayoutOverflowError(
            f"Text {node.name or node.text[:40]!r} cannot fit its constraints"
        )
    return measure_text(
        text,
        Emu(width),
        size_pt=size,
        font_family=family,
        font_file=path,
        bold=face.draw_bold,
        italic=node.italic,
        line_spacing=node.line_spacing,
        strict=context.strict_fonts,
        letter_spacing=int(node.letter_spacing),
    )


def _row_widths(node, available, context):
    widths = []
    for child in node.children:
        width = child.width
        if width is None and isinstance(child, Badge):
            t, r, b, left_pad = _insets(child.padding)
            measurement = _text_measure(child.label, available, 10**12, context)
            width = measurement.width + left_pad + r
        widths.append(width)
    fixed = sum(width for width in widths if width is not None)
    remaining = available - fixed - node.gap * max(0, len(widths) - 1)
    flexible = [i for i, width in enumerate(widths) if width is None]
    if remaining < 0 or (flexible and remaining <= 0):
        raise LayoutOverflowError("Row children and gaps exceed available width")
    total = sum(node.children[i].grow or 1 for i in flexible)
    cursor = 0
    for position, i in enumerate(flexible):
        edge = round(
            remaining * sum(node.children[j].grow or 1 for j in flexible[: position + 1]) / total
        )
        widths[i] = edge - cursor
        cursor = edge
    return [round(width) for width in widths]


def _measure(node, width, context):
    if node.height is not None:
        return int(node.height)
    if isinstance(node, TextBlock):
        return int(_text_measure(node, width, 10**12, context).height)
    if isinstance(node, DataTable):
        return sum(_table_layout(node, width, context).heights)
    if isinstance(node, Container):
        t, r, b, left_pad = _insets(node.padding)
        inner = width - left_pad - r
        if inner <= 0:
            raise LayoutOverflowError("Container padding consumes its width")
        if node.direction == "horizontal":
            widths = _row_widths(node, inner, context)
            heights = [_measure(child, w, context) for child, w in zip(node.children, widths)]
            return t + b + max(heights, default=0)
        return (
            t
            + b
            + sum(_measure(c, c.width or inner, context) for c in node.children)
            + node.gap * max(0, len(node.children) - 1)
        )
    raise TypeError("NativeContent requires a height")


def _is_panel(node):
    return isinstance(node, Container) and (node.fill is not None or node.border is not None)


def _plan(node, bbox, context, stretched=False):
    if bbox.width <= 0 or bbox.height <= 0:
        raise LayoutOverflowError("Component regions must have positive dimensions")
    plan = _Plan(node, bbox)
    if isinstance(node, TextBlock):
        plan.text = _text_measure(node, bbox.width, bbox.height, context)
        return plan
    if isinstance(node, DataTable):
        plan.table = _table_layout(node, bbox.width, context)
        if sum(plan.table.heights) > bbox.height:
            raise LayoutOverflowError(
                f"DataTable {node.name or ''!r} needs {sum(plan.table.heights) / 12700:.1f}pt; "
                f"its region is {bbox.height / 12700:.1f}pt"
            )
        return plan
    if not isinstance(node, Container):
        return plan
    if node.radius > min(bbox.width, bbox.height) / 2:
        raise LayoutOverflowError("Container radius exceeds half its shorter side")
    t, r, b, left_pad = _insets(node.padding)
    inner = BBox(
        Emu(bbox.left + left_pad),
        Emu(bbox.top + t),
        Emu(bbox.width - left_pad - r),
        Emu(bbox.height - t - b),
    )
    if inner.width <= 0 or inner.height <= 0:
        raise LayoutOverflowError("Container padding consumes its region")
    horizontal = node.direction == "horizontal"
    widths = (
        _row_widths(node, inner.width, context)
        if horizontal
        else [c.width or inner.width for c in node.children]
    )
    heights = [_measure(child, w, context) for child, w in zip(node.children, widths)]
    sizes = widths if horizontal else heights
    available = inner.width if horizontal else inner.height
    spare = available - sum(sizes) - node.gap * max(0, len(sizes) - 1)
    if spare < 0 or any(w > inner.width for w in widths) or any(h > inner.height for h in heights):
        raise LayoutOverflowError(f"Container {node.name or ''!r} content exceeds its region")
    grows = sum(c.grow for c in node.children) if not horizontal else 0
    if grows:
        allocated = 0
        cumulative = 0.0
        for i, child in enumerate(node.children):
            cumulative += child.grow
            edge = round(spare * cumulative / grows)
            heights[i] += edge - allocated
            allocated = edge
        spare = 0
    elif not horizontal and node.fill_last and node.children:
        heights[-1] += spare
        spare = 0
    elif (
        not horizontal
        and stretched
        and spare > RAGGED_TOLERANCE
        and node.justify == "start"
        and not _is_panel(node)
        and node.children
        and _is_panel(node.children[-1])
    ):
        label = f"Column {node.name!r}" if node.name else "A column"
        context.warnings.append(
            f"{label} ends {spare / 12700:.1f}pt above the bottom of "
            "its row, so its last panel won't share a bottom edge with its neighbours; "
            "set grow on its last child or fill_last=True"
        )
    gap = node.gap
    offset = 0
    if node.justify == "center":
        offset = spare / 2
    elif node.justify == "end":
        offset = spare
    elif node.justify == "space-between" and len(sizes) > 1:
        gap += spare / (len(sizes) - 1)
    cursor = offset
    for child, w, h in zip(node.children, widths, heights):
        cross = inner.height - h if horizontal else inner.width - w
        shift = cross / 2 if node.align == "center" else cross if node.align == "end" else 0
        child_stretched = False
        if node.align == "stretch":
            if horizontal and child.height is None:
                child_stretched = inner.height > h
                h = inner.height
            elif not horizontal and child.width is None:
                w = inner.width
        child_box = BBox(
            Emu(round(inner.left + (cursor if horizontal else shift))),
            Emu(round(inner.top + (shift if horizontal else cursor))),
            Emu(w),
            Emu(h),
        )
        plan.children.append(_plan(child, child_box, context, child_stretched))
        cursor += (w if horizontal else h) + gap
    return plan


def _draw(plan, slide, context, result):
    node, bbox = plan.node, plan.bbox
    start = len(result.shapes)
    background = None
    if isinstance(node, TextBlock):
        m = plan.text
        face = _face(node, context)
        shape = slide.shapes.add_text(
            bbox,
            text="\v".join(m.lines),
            size_pt=m.font_size_pt,
            font=face.draw_family,
            color=context.color(node.color),
            bold=face.draw_bold,
            italic=node.italic,
            align=node.align,
            anchor=node.anchor,
            margin_pt=0,
        )
        shape.text_frame.auto_size = MSO_AUTO_SIZE.NONE
        # Bake measured lines so Office cannot introduce extra wrapping (most
        # visible on intrinsically sized badges and narrow card copy).
        shape.text_frame.word_wrap = False
        for paragraph in shape.text_frame.paragraphs:
            paragraph.line_spacing = node.line_spacing
            paragraph.space_before = paragraph.space_after = Pt(0)
            if node.letter_spacing:
                for run in paragraph.runs:
                    run.font.letter_spacing = Emu(int(node.letter_spacing))
        if m.used_fallback or face.estimated:
            result.estimated_fonts.append(node.name or node.text[:40])
        result.shapes.append(shape)
    elif isinstance(node, Container):
        if node.fill is not None or node.border is not None:
            background = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE if node.radius else MSO_SHAPE.RECTANGLE, *bbox
            )
            if node.fill is not None:
                background.fill_hex(context.color(node.fill))
            else:
                background.fill.background()
            if node.border is not None:
                background.line_hex(context.color(node.border), weight_pt=0.75)
            else:
                background.line.fill.background()
            background.shadow.clear()
            if node.radius:
                background.corner_radius = Emu(node.radius)
            result.shapes.append(background)
        for child in plan.children:
            _draw(child, slide, context, result)
        if background is not None:
            for child_shape in result.shapes[start + 1 :]:
                background.allow_overlap_with(child_shape)
    elif isinstance(node, DataTable):
        result.shapes.append(_draw_table(node, plan, slide, context))
        if plan.table.estimated:
            result.estimated_fonts.append(node.name or "DataTable")
    elif isinstance(node, NativeContent):
        before = len(slide.shapes)
        node.builder(slide, bbox)
        result.shapes.extend(list(slide.shapes)[before:])
    if node.name is not None:
        created = result.shapes[start:]
        if created:
            created[0].name = node.name
            result.named[node.name] = created[0]


def _draw_table(node, plan, slide, context):
    layout, bbox = plan.table, plan.bbox
    count = len(layout.widths)
    frame = slide.shapes.add_table(
        len(node.rows),
        count,
        bbox.left,
        bbox.top,
        bbox.width,
        Emu(sum(layout.heights)),
        style="clean",
    )
    table = frame.table
    for column, width in zip(table.columns, layout.widths):
        column.width = Emu(width)
    for row, height in zip(table.rows, layout.heights):
        row.height = Emu(height)
    t, r, b, left_pad = _insets(node.cell_padding)
    aligns = [node.align] * count if isinstance(node.align, str) else list(node.align)
    for row_index, row_lines in enumerate(layout.lines):
        is_header = node.header and row_index == 0
        for column, lines in enumerate(row_lines):
            cell = table.cell(row_index, column)
            cell.text = "\v".join(lines)
            fill = node.header_fill if is_header else node.fill
            cell.format(
                fill=context.color(fill) if fill is not None else "none",
                color=context.color(node.header_color if is_header else node.color),
                font=layout.family,
                size_pt=layout.font_size_pt,
                bold=is_header,
                align=aligns[column],
                anchor="top",
                margin=(t / 12700, r / 12700, b / 12700, left_pad / 12700),
                # Lines are baked; re-wrapping with other metrics would outgrow the row.
                word_wrap=False,
            )
            for paragraph in cell.text_frame.paragraphs:
                paragraph.line_spacing = node.line_spacing
                paragraph.space_before = paragraph.space_after = Pt(0)
            if node.border is not None:
                cell.borders.outer(Pt(0.75), context.color(node.border))
    return frame
