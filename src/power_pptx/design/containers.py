"""Declarative native components with measurement, padding, and nested layout.

The component tree is measured before slide mutation. Rendered text and shapes
remain ordinary editable PowerPoint objects; no HTML renderer is involved.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Sequence

from power_pptx._color import coerce_color
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.enum.text import MSO_AUTO_SIZE
from power_pptx.geometry import BBox
from power_pptx.text.fonts import find_font_file
from power_pptx.text.layout import TextFitter
from power_pptx.text.measurement import TextMeasurement, measure_text
from power_pptx.util import Emu, Pt

if TYPE_CHECKING:
    from power_pptx.design.tokens import DesignTokens
    from power_pptx.slide import Slide


class LayoutOverflowError(ValueError):
    """A component cannot fit its region at its requested minimum sizes."""


@dataclass
class LayoutResult:
    bbox: BBox
    shapes: list[Any] = field(default_factory=list)
    named: dict[str, Any] = field(default_factory=dict)
    estimated_fonts: list[str] = field(default_factory=list)

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
        spare height to selected column children. Invalid layouts raise before
        shape creation. Custom NativeContent builders own their side effects.
        """
        context = _Context(tokens, strict_fonts)
        _validate(self, context, set())
        plan = _plan(self, bbox, context)
        result = LayoutResult(bbox)
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
class _Context:
    tokens: Any
    strict_fonts: bool

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
    if not isinstance(node, (Container, TextBlock, NativeContent)):
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
        for child in node.children:
            _validate(child, context, names)
    elif isinstance(node, TextBlock):
        context.color(node.color)
        if node.align not in {"left", "center", "right", "justify"}:
            raise ValueError("invalid text align")
        if node.anchor not in {"top", "middle", "bottom"}:
            raise ValueError("invalid text anchor")


def _text_measure(node, width, height, context):
    family = context.font(node)
    path = node.font_file or find_font_file(family or "Calibri", node.bold, node.italic)
    if path is None and context.strict_fonts:
        raise ValueError(
            f"Font {family or 'Calibri'!r} is unavailable; install it or pass font_file"
        )
    size = TextFitter.best_fit_font_size(
        node.text,
        (Emu(width), Emu(height)),
        node.size_pt,
        path,
        min_size=node.min_size_pt,
        max_lines=node.max_lines,
        preserve_breaks=node.preserve_breaks,
        line_spacing=node.line_spacing,
    )
    if size is None:
        raise LayoutOverflowError(
            f"Text {node.name or node.text[:40]!r} cannot fit its constraints"
        )
    return measure_text(
        node.text,
        Emu(width),
        size_pt=size,
        font_family=family,
        font_file=path,
        bold=node.bold,
        italic=node.italic,
        line_spacing=node.line_spacing,
        strict=context.strict_fonts,
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


def _plan(node, bbox, context):
    if bbox.width <= 0 or bbox.height <= 0:
        raise LayoutOverflowError("Component regions must have positive dimensions")
    plan = _Plan(node, bbox)
    if isinstance(node, TextBlock):
        plan.text = _text_measure(node, bbox.width, bbox.height, context)
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
        if node.align == "stretch":
            if horizontal and child.height is None:
                h = inner.height
            elif not horizontal and child.width is None:
                w = inner.width
        child_box = BBox(
            Emu(round(inner.left + (cursor if horizontal else shift))),
            Emu(round(inner.top + (shift if horizontal else cursor))),
            Emu(w),
            Emu(h),
        )
        plan.children.append(_plan(child, child_box, context))
        cursor += (w if horizontal else h) + gap
    return plan


def _draw(plan, slide, context, result):
    node, bbox = plan.node, plan.bbox
    start = len(result.shapes)
    background = None
    if isinstance(node, TextBlock):
        m = plan.text
        shape = slide.shapes.add_text(
            bbox,
            text="\v".join(m.lines),
            size_pt=m.font_size_pt,
            font=context.font(node),
            color=context.color(node.color),
            bold=node.bold,
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
        if m.used_fallback:
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
    elif isinstance(node, NativeContent):
        before = len(slide.shapes)
        node.builder(slide, bbox)
        result.shapes.extend(list(slide.shapes)[before:])
    if node.name is not None:
        created = result.shapes[start:]
        if created:
            created[0].name = node.name
            result.named[node.name] = created[0]
