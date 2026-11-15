"""Native-shape diagram recipes — pipelines, hub-and-spoke, cycles.

This module addresses the most common cause of "I built it out of 20
``add_shape`` calls and the layout maths is wrong" diagrams produced by
LLM-driven deck generation.  Each recipe takes a slide, a
:class:`~power_pptx.geometry.BBox` to live inside, and a small
content spec; the recipe handles equal-column widths, mid-point
arrow routing, and inset padding so the caller only specifies the
*semantics*::

    from power_pptx.diagrams import horizontal_pipeline

    horizontal_pipeline(
        slide,
        bbox,
        steps=["Extract", "Classify", "Enrich", "Output"],
        accent="#0B5CFF",
    )

Every recipe returns a small dataclass exposing the shapes it built
(``cards``, ``arrows``, ``hub``, …) so callers can tweak individually.

The recipes deliberately use built-in :class:`~power_pptx.enum.shapes.MSO_SHAPE`
geometry only.  No images, no SmartArt — every output is fully native
PowerPoint shapes that PowerPoint, Keynote, and LibreOffice all render
identically.
"""

from __future__ import annotations

import math
import warnings
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterator, Sequence

from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.geometry import BBox
from power_pptx.util import Emu, Inches, Pt

if TYPE_CHECKING:
    from power_pptx.shapes.autoshape import Shape
    from power_pptx.slide import Slide


__all__ = [
    "PipelineResult",
    "HubAndSpokeResult",
    "CycleResult",
    "DecisionTreeResult",
    "ColumnsResult",
    "horizontal_pipeline",
    "vertical_pipeline",
    "hub_and_spoke",
    "cycle",
    "decision_tree",
    "comparison_columns",
]


# ----------------------------------------------------------------------------- specs


@dataclass
class _Step:
    label: str
    sublabel: str | None = None
    fill: str | None = None
    text_color: str | None = None


def _coerce_steps(steps: Sequence[Any]) -> list[_Step]:
    out: list[_Step] = []
    for s in steps:
        if isinstance(s, str):
            out.append(_Step(label=s))
        elif isinstance(s, dict):
            out.append(
                _Step(
                    label=s.get("label", ""),
                    sublabel=s.get("sublabel"),
                    fill=s.get("fill"),
                    text_color=s.get("text_color"),
                )
            )
        elif isinstance(s, _Step):
            out.append(s)
        else:
            raise TypeError(
                f"steps must be strings, dicts, or _Step instances; got {type(s).__name__}"
            )
    if not out:
        raise ValueError("steps must be non-empty")
    return out


# ----------------------------------------------------------------------------- results


@dataclass
class PipelineResult:
    cards: list[Any] = field(default_factory=list)
    arrows: list[Any] = field(default_factory=list)


@dataclass
class HubAndSpokeResult:
    hub: Any = None
    spokes: list[Any] = field(default_factory=list)
    arrows: list[Any] = field(default_factory=list)


@dataclass
class CycleResult:
    cards: list[Any] = field(default_factory=list)
    arrows: list[Any] = field(default_factory=list)


@dataclass
class DecisionTreeResult:
    root: Any = None
    branches: list[Any] = field(default_factory=list)
    arrows: list[Any] = field(default_factory=list)


@dataclass
class ColumnsResult:
    columns: list[Any] = field(default_factory=list)
    headers: list[Any] = field(default_factory=list)


# ----------------------------------------------------------------------------- helpers


def _tag_group(slide, prefix: str, shapes: list[Any]) -> None:
    """Tag every shape with a unique-on-slide ``lint_group``.

    Diagram arrows intentionally overlap their target cards; without
    this tag the linter / audit() would flood with ShapeCollision
    warnings for the recipe's design.
    """
    if not shapes:
        return
    try:
        slide.lint_group_overlaps(*shapes)
    except Exception:
        for s in shapes:
            with suppress(Exception):
                s.lint_group = prefix


# Smallest label size, in points, a diagram recipe will produce by default.
# A node whose label cannot be set at this size (whole words, no clipping)
# makes the recipe raise instead of emitting an unreadable diagram; pass
# ``min_size_pt`` to a recipe to move the floor.
_MIN_LABEL_PT = 6.0

# The ``ellipse`` preset places text in the rectangle inscribed in the
# ellipse — for a circle, a square of side d / sqrt(2) — not in the shape's
# bounding box.
_INSCRIBED = math.sqrt(0.5)


@contextmanager
def _atomic(slide) -> Iterator[None]:
    """Remove whatever the block added to *slide* if the block raises.

    A recipe that rejects its input part-way through (a label that does
    not fit the fifth node) must not leave the first four on the slide.
    """
    tree = slide.shapes._spTree  # pyright: ignore[reportPrivateUsage]
    before = list(tree)
    try:
        yield
    except Exception:
        kept = {id(element) for element in before}
        for element in list(tree):
            if id(element) not in kept:
                tree.remove(element)
        raise


def _fit_label(
    tf: Any,
    width: int,
    height: int,
    *,
    font: str | None,
    max_size_pt: float,
    min_size_pt: float,
    bold: bool = False,
    italic: bool = False,
    what: str,
) -> None:
    """Bake the largest size at which *tf*'s text fits a ``width`` x ``height`` area.

    The same metrics-based fit as ``TextFrame.fit_text`` — text wraps at
    whole words only — but against an explicit area, because a shape's
    text area is not always its bounding box (see :data:`_INSCRIBED`),
    and with a floor: when the text does not fit at *min_size_pt* a
    :class:`ValueError` is raised naming the label, rather than keeping
    a size that overflows or shrinking to nothing.
    """
    from power_pptx.exc import FontMetricsWarning
    from power_pptx.text.fonts import find_font_file
    from power_pptx.text.layout import TextFitter

    text = tf.text
    if not text.strip():
        return
    family = font if font is not None else "Calibri"
    font_file = find_font_file(family, bold, italic)
    if font_file is None and font is not None:
        warnings.warn(
            f"{family!r} is not installed, so the {what} label was measured with Pillow's "
            "default font instead of real metrics — the chosen size is an estimate. Pass an "
            "installed family or register the font with power_pptx.text.register_font_dir().",
            FontMetricsWarning,
            stacklevel=4,
        )
    top = max(1, int(round(max_size_pt)))
    floor = min(top, max(1, int(math.ceil(min_size_pt))))
    size = None
    if width > 0 and height > 0:
        size = TextFitter.best_fit_font_size(
            text,
            (Emu(width), Emu(height)),
            top,
            font_file,
            min_size=floor,
            line_spacing=1.0,
            break_long_words=False,
        )
    if size is None:
        raise ValueError(
            f"{what}: the label {text!r} does not fit its "
            f"{max(0, width) / 914400:.2f}in x {max(0, height) / 914400:.2f}in text area at "
            f"{floor}pt. Use a larger bbox, fewer or shorter labels, or a lower min_size_pt."
        )
    tf._apply_fit(family, size, bold, italic)  # pyright: ignore[reportPrivateUsage]


def _fit_circular_label(
    shape: Any,
    *,
    diameter: int,
    font: str | None,
    max_size_pt: float,
    min_size_pt: float = _MIN_LABEL_PT,
    bold: bool = False,
    italic: bool = False,
    what: str = "node",
) -> None:
    """Shrink a circular node's label so it never clips the curved edge.

    The headline reason this fork exists is space-awareness, so the diagram
    recipes use the same metrics-based pre-flight as everything else.  A
    circle's text area is the square inscribed in it (about 0.707 x the
    diameter), which is what the label is fitted against, less a small
    inset.  Fitting against the bounding box instead let a long word such
    as "Retrieval" pass the check and then break as "Retri / eval" when
    rendered.  Words are never split: a label that cannot be set at
    *min_size_pt* raises :class:`ValueError`.
    """
    tf = shape.text_frame
    tf.word_wrap = True
    inset = max(int(Pt(1)), int(diameter * 0.02))
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Emu(inset)
    side = int(diameter * _INSCRIBED) - 2 * inset
    _fit_label(
        tf,
        side,
        side,
        font=font,
        max_size_pt=max_size_pt,
        min_size_pt=min_size_pt,
        bold=bold,
        italic=italic,
        what=what,
    )


def _style_runs(
    tf: Any,
    *,
    font: str | None,
    size_pt: float,
    color: str,
    bold: bool | None = None,
    align: Any = None,
) -> None:
    """Set every run of *tf* in *font* at *size_pt* points and *color*.

    *bold*, when given, is set on every run too, and *align* on every
    paragraph.  Size and colour are converted per run, so text without
    runs never looks at them.
    """
    from power_pptx._color import coerce_color

    for para in tf.paragraphs:
        if align is not None:
            para.alignment = align
        for run in para.runs:
            if font is not None:
                run.font.name = font
            run.font.size = Pt(float(size_pt))
            if bold is not None:
                run.font.bold = bold
            run.font.color.rgb = coerce_color(color)


def _circle_box(centre: tuple[int, int], diameter: int) -> BBox:
    """The bounding box of a circle of *diameter* centred on *centre*."""
    cx, cy = centre
    return BBox(
        Emu(cx - diameter // 2),
        Emu(cy - diameter // 2),
        Emu(diameter),
        Emu(diameter),
    )


def _ring_point(centre: tuple[int, int], radius: int, angle: float) -> tuple[int, int]:
    """The point *radius* from *centre* in the direction *angle* (radians)."""
    cx, cy = centre
    return cx + int(radius * math.cos(angle)), cy + int(radius * math.sin(angle))


def _ring_angle(index: int, count: int) -> float:
    """Angle of node *index* of *count* spaced evenly round a ring, the first at the top."""
    return 2 * math.pi * index / count - math.pi / 2


def _set_circle_label(
    node: Any,
    text: str,
    *,
    font: str | None,
    size_pt: float,
    color: str,
    bold: bool | None = None,
) -> None:
    """Write *text* into circular *node*, centred both ways and wrapping."""
    from power_pptx.enum.text import MSO_VERTICAL_ANCHOR, PP_PARAGRAPH_ALIGNMENT

    tf = node.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
    tf.text = text
    _style_runs(
        tf,
        font=font,
        size_pt=size_pt,
        color=color,
        bold=bold,
        align=PP_PARAGRAPH_ALIGNMENT.CENTER,
    )


def _add_step_node(
    slide: "Slide",
    step: _Step,
    centre: tuple[int, int],
    diameter: int,
    *,
    fill: str,
    accent: str,
    text_color: str,
    font: str | None,
    size_pt: float,
    min_size_pt: float,
    what: str,
) -> Any:
    """Add *step* as an outlined circle of *diameter* on *centre*, its label fitted.

    The step's own ``fill`` / ``text_color`` win over the recipe's.
    """
    node = slide.shapes.add_shape(MSO_SHAPE.OVAL, *_circle_box(centre, diameter))
    node.fill_hex(step.fill or fill)
    node.line_hex(accent, weight_pt=1.5)
    _set_circle_label(
        node, step.label, font=font, size_pt=size_pt, color=step.text_color or text_color
    )
    _fit_circular_label(
        node,
        diameter=diameter,
        font=font,
        max_size_pt=size_pt,
        min_size_pt=min_size_pt,
        what=what,
    )
    return node


def _card(
    slide,
    bbox: BBox,
    *,
    fill: str = "#FFFFFF",
    line: str | None = "#0D0D0D",
    weight_pt: float = 1.0,
    text: str | None = None,
    text_color: str = "#0D0D0D",
    font: str | None = None,
    size_pt: float = 14.0,
    bold: bool = False,
    radius: float = 0.0,
    min_size_pt: float = _MIN_LABEL_PT,
    what: str = "card",
) -> "Shape":
    if int(bbox.width) <= 0 or int(bbox.height) <= 0:
        raise ValueError(
            f"{what}: the bbox leaves no room for this card "
            f"({int(bbox.width) / 914400:.2f}in x {int(bbox.height) / 914400:.2f}in). "
            "Use a larger bbox, a smaller gap or fewer items."
        )
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius > 0 else MSO_SHAPE.RECTANGLE
    rect = slide.shapes.add_shape(shape_type, *bbox)
    rect.fill_hex(fill)
    if line is not None:
        rect.line_hex(line, weight_pt=weight_pt)
    else:
        rect.line.fill.background()
    if text:
        tf = rect.text_frame
        tf.word_wrap = True
        from power_pptx.enum.text import MSO_VERTICAL_ANCHOR, PP_PARAGRAPH_ALIGNMENT

        tf.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
        margin = Pt(6)
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = margin
        tf.text = text
        _style_runs(
            tf,
            font=font,
            size_pt=size_pt,
            color=text_color,
            bold=bool(bold),
            align=PP_PARAGRAPH_ALIGNMENT.CENTER,
        )
        # Space-awareness: shrink the label so a long word never clips its card
        # (the rectangular siblings of the already-fitted circular nodes).  A
        # card too small for its label at the minimum size is an error, not a
        # silently overflowing card.
        _fit_label(
            tf,
            int(bbox.width) - 2 * int(margin),
            int(bbox.height) - 2 * int(margin),
            font=font,
            max_size_pt=size_pt,
            min_size_pt=min_size_pt,
            bold=bool(bold),
            what=what,
        )
    return rect


# ----------------------------------------------------------------------------- pipelines


def horizontal_pipeline(
    slide,
    bbox: BBox,
    steps: Sequence[Any],
    *,
    accent: str = "#0B5CFF",
    fill: str = "#FFFFFF",
    text_color: str = "#0D0D0D",
    font: str | None = None,
    size_pt: float = 14.0,
    bold_labels: bool = True,
    gap: int | None = None,
    arrow_inset_pt: float = 6.0,
    arrow_head: str = "triangle",
    card_line: str | None = "#0D0D0D",
    card_radius: float = 0.0,
    min_size_pt: float = _MIN_LABEL_PT,
) -> PipelineResult:
    """Horizontal pipeline of N steps with arrows between them.

    Each step renders as an evenly-sized card with a centered label.
    Arrows are routed mid-edge with a small inset so the arrowhead
    doesn't bleed into the next card.

    ``steps`` may be a list of plain strings or ``{"label": ..., "sublabel": ...,
    "fill": ..., "text_color": ...}`` dicts.

    Labels start at ``size_pt`` and shrink to fit their card.  When a card
    cannot hold its label at ``min_size_pt`` (too many steps for the bbox,
    or a very long label) :class:`ValueError` is raised and nothing is
    added to the slide.
    """
    coerced = _coerce_steps(steps)
    n = len(coerced)
    if gap is None:
        gap = int(Pt(12))

    card_boxes = bbox.split_h([1] * n, gap=gap)
    cards: list[Any] = []
    arrows: list[Any] = []
    with _atomic(slide):
        for step, cb in zip(coerced, card_boxes):
            label = step.label
            if step.sublabel:
                label = f"{label}\n{step.sublabel}"
            cards.append(
                _card(
                    slide,
                    cb,
                    fill=step.fill or fill,
                    line=card_line,
                    text=label,
                    text_color=step.text_color or text_color,
                    font=font,
                    size_pt=size_pt,
                    bold=bold_labels,
                    radius=card_radius,
                    min_size_pt=min_size_pt,
                    what=f"horizontal_pipeline ({n} steps)",
                )
            )

        for i in range(n - 1):
            arrow = slide.shapes.add_arrow(
                cards[i],
                cards[i + 1],
                head=arrow_head,
                color=accent,
                weight_pt=2.0,
                inset_pt=arrow_inset_pt,
            )
            arrows.append(arrow)
    _tag_group(slide, "pipeline", cards + arrows)
    return PipelineResult(cards=cards, arrows=arrows)


def vertical_pipeline(
    slide,
    bbox: BBox,
    steps: Sequence[Any],
    **kwargs,
) -> PipelineResult:
    """Vertical pipeline — same as :func:`horizontal_pipeline` but stacked.

    Takes the same keyword arguments, including ``min_size_pt``: a card
    too short for its label at that size raises :class:`ValueError`.
    """
    coerced = _coerce_steps(steps)
    n = len(coerced)
    gap = kwargs.pop("gap", None)
    if gap is None:
        gap = int(Pt(12))
    accent = kwargs.pop("accent", "#0B5CFF")
    fill = kwargs.pop("fill", "#FFFFFF")
    text_color = kwargs.pop("text_color", "#0D0D0D")
    font = kwargs.pop("font", None)
    size_pt = kwargs.pop("size_pt", 14.0)
    bold_labels = kwargs.pop("bold_labels", True)
    arrow_inset_pt = kwargs.pop("arrow_inset_pt", 6.0)
    arrow_head = kwargs.pop("arrow_head", "triangle")
    card_line = kwargs.pop("card_line", "#0D0D0D")
    card_radius = kwargs.pop("card_radius", 0.0)
    min_size_pt = kwargs.pop("min_size_pt", _MIN_LABEL_PT)
    if kwargs:
        raise TypeError(f"unexpected keyword arguments: {sorted(kwargs)}")

    card_boxes = bbox.split_v([1] * n, gap=gap)
    cards: list[Any] = []
    arrows: list[Any] = []
    with _atomic(slide):
        for step, cb in zip(coerced, card_boxes):
            label = step.label
            if step.sublabel:
                label = f"{label}\n{step.sublabel}"
            cards.append(
                _card(
                    slide,
                    cb,
                    fill=step.fill or fill,
                    line=card_line,
                    text=label,
                    text_color=step.text_color or text_color,
                    font=font,
                    size_pt=size_pt,
                    bold=bold_labels,
                    radius=card_radius,
                    min_size_pt=min_size_pt,
                    what=f"vertical_pipeline ({n} steps)",
                )
            )
        for i in range(n - 1):
            arrow = slide.shapes.add_arrow(
                cards[i],
                cards[i + 1],
                head=arrow_head,
                color=accent,
                weight_pt=2.0,
                inset_pt=arrow_inset_pt,
            )
            arrows.append(arrow)
    _tag_group(slide, "vpipeline", cards + arrows)
    return PipelineResult(cards=cards, arrows=arrows)


# ----------------------------------------------------------------------------- hub


def hub_and_spoke(
    slide,
    bbox: BBox,
    *,
    centre: str,
    spokes: Sequence[Any],
    accent: str = "#0B5CFF",
    fill: str = "#FFFFFF",
    hub_fill: str | None = None,
    text_color: str = "#0D0D0D",
    hub_text_color: str = "#FFFFFF",
    font: str | None = None,
    size_pt: float = 14.0,
    spoke_size: float = 1.0,
    hub_size: float = 1.4,
    min_size_pt: float = _MIN_LABEL_PT,
) -> HubAndSpokeResult:
    """Hub-and-spoke diagram with N spokes radially arranged.

    ``centre`` is the label of the hub.  ``spokes`` is an iterable of
    string labels or step-dicts (see :func:`horizontal_pipeline`).
    Spoke centers use the available outer radius; node diameters shrink
    when necessary to leave space between the hub and neighboring spokes.

    Labels are fitted to the square inscribed in each circle, starting
    at ``size_pt`` and never splitting a word.  When a label cannot be
    set at ``min_size_pt`` — a dense diagram, a small bbox, a long
    label — :class:`ValueError` is raised and nothing is added to the
    slide: split the diagram across slides or shorten the labels.
    """
    coerced = _coerce_steps(spokes)
    n = len(coerced)

    if any(not math.isfinite(value) or value <= 0 for value in (spoke_size, hub_size)):
        raise ValueError("spoke_size and hub_size must be finite and positive")

    # Place the hub in the centre at ~25% of the smaller dimension.
    short = min(int(bbox.width), int(bbox.height))
    hub_diameter = int(short * 0.25 * hub_size)
    gap = max(1, int(short * 0.04))
    max_spoke = (short - hub_diameter) / 2 - gap
    if n > 1:
        # Neighbor distance is 2r sin(pi/n), with r=(short-diameter)/2.
        sine = math.sin(math.pi / n)
        max_spoke = min(max_spoke, (short * sine - gap) / (1 + sine))
    spoke_diameter = int(min(short * 0.2 * spoke_size, max_spoke))
    if hub_diameter <= 0 or spoke_diameter <= 0:
        raise ValueError("bbox is too small for the requested hub_size and spoke count")
    cx, cy = int(bbox.cx), int(bbox.cy)

    hub_box = BBox(
        Emu(cx - hub_diameter // 2),
        Emu(cy - hub_diameter // 2),
        Emu(hub_diameter),
        Emu(hub_diameter),
    )
    with _atomic(slide):
        hub, spokes_built, arrows = _build_hub_and_spoke(
            slide,
            coerced,
            centre,
            cx,
            cy,
            short,
            hub_box,
            hub_diameter,
            spoke_diameter,
            gap,
            accent=accent,
            fill=fill,
            hub_fill=hub_fill,
            text_color=text_color,
            hub_text_color=hub_text_color,
            font=font,
            size_pt=size_pt,
            min_size_pt=min_size_pt,
        )
    _tag_group(slide, "hub-and-spoke", [hub] + spokes_built + arrows)
    return HubAndSpokeResult(hub=hub, spokes=spokes_built, arrows=arrows)


def _build_hub_and_spoke(
    slide,
    coerced: list[_Step],
    centre: str,
    cx: int,
    cy: int,
    short: int,
    hub_box: BBox,
    hub_diameter: int,
    spoke_diameter: int,
    gap: int,
    *,
    accent: str,
    fill: str,
    hub_fill: str | None,
    text_color: str,
    hub_text_color: str,
    font: str | None,
    size_pt: float,
    min_size_pt: float,
) -> tuple[Any, list[Any], list[Any]]:
    """Add the hub, spokes and arrows of :func:`hub_and_spoke` to *slide*."""
    n = len(coerced)
    hub = slide.shapes.add_shape(MSO_SHAPE.OVAL, *hub_box)
    hub.fill_hex(hub_fill or accent)
    hub.line.fill.background()
    _set_circle_label(hub, centre, font=font, size_pt=size_pt, color=hub_text_color, bold=True)
    _fit_circular_label(
        hub,
        diameter=hub_diameter,
        font=font,
        max_size_pt=size_pt,
        min_size_pt=min_size_pt,
        bold=True,
        what="hub_and_spoke hub",
    )

    # Place spokes evenly around the hub; each arrow stops a little short of
    # the hub's and the spoke's edges.
    radius = (short - spoke_diameter) // 2
    inset = min(int(Pt(2)), gap // 4)
    spokes_built: list[Any] = []
    arrows: list[Any] = []
    for i, step in enumerate(coerced):
        angle = _ring_angle(i, n)
        spoke_centre = _ring_point((cx, cy), radius, angle)
        spoke = _add_step_node(
            slide,
            step,
            spoke_centre,
            spoke_diameter,
            fill=fill,
            accent=accent,
            text_color=text_color,
            font=font,
            size_pt=size_pt * 0.85,
            min_size_pt=min_size_pt,
            what=f"hub_and_spoke ({n} spokes)",
        )
        spokes_built.append(spoke)
        arrows.append(
            _add_radial_arrow(
                slide,
                (cx, cy),
                hub_diameter / 2 + inset,
                spoke_centre,
                spoke_diameter / 2 + inset,
                angle,
                accent,
            )
        )
    return hub, spokes_built, arrows


def _add_radial_arrow(
    slide: "Slide",
    start: tuple[int, int],
    start_r: float,
    end: tuple[int, int],
    end_r: float,
    angle: float,
    color: str,
) -> Any:
    """Add an arrow along *angle* from *start_r* out of *start* to *end_r* short of *end*.

    Shape-to-shape arrow routing chooses rectangular card edges. Circular
    nodes need perimeter points along the radial direction instead.
    """
    ux, uy = math.cos(angle), math.sin(angle)
    return slide.shapes.add_arrow(
        (Emu(round(start[0] + start_r * ux)), Emu(round(start[1] + start_r * uy))),
        (Emu(round(end[0] - end_r * ux)), Emu(round(end[1] - end_r * uy))),
        head="triangle",
        color=color,
        weight_pt=1.5,
        inset_pt=0.0,
    )


# ----------------------------------------------------------------------------- cycle


def cycle(
    slide,
    bbox: BBox,
    steps: Sequence[Any],
    *,
    accent: str = "#0B5CFF",
    fill: str = "#FFFFFF",
    text_color: str = "#0D0D0D",
    font: str | None = None,
    size_pt: float = 14.0,
    min_size_pt: float = _MIN_LABEL_PT,
) -> CycleResult:
    """Cyclic diagram — N cards arranged in a circle with arrows ``i → i+1``.

    The last arrow loops back from card N-1 to card 0, completing the
    cycle.  Works best with 3–8 steps, where every node is 22% of the
    bbox's short side across.  With more steps the nodes shrink so that
    neighbours keep a gap for the arrow between them instead of
    overlapping.

    Labels are fitted to the square inscribed in each circle, starting
    at ``size_pt`` and never splitting a word.  When a label cannot be
    set at ``min_size_pt`` — too many steps for the bbox, or a long
    label — :class:`ValueError` is raised and nothing is added to the
    slide.
    """
    coerced = _coerce_steps(steps)
    n = len(coerced)
    short = min(int(bbox.width), int(bbox.height))
    card_diameter = int(short * 0.22)
    if n > 2:
        # Neighbouring centres are 2 r sin(pi/n) apart with r = (short - d) / 2.
        # Keep at least `gap` of clear space between two nodes for the arrow.
        gap = short * 0.06
        sine = math.sin(math.pi / n)
        card_diameter = min(card_diameter, int((short * sine - gap) / (1 + sine)))
    if card_diameter <= 0:
        raise ValueError(f"cycle: bbox is too small for {n} steps")
    cx, cy = int(bbox.cx), int(bbox.cy)
    radius = (short - card_diameter) // 2

    with _atomic(slide):
        cards, arrows = _build_cycle(
            slide,
            coerced,
            cx,
            cy,
            radius,
            card_diameter,
            accent=accent,
            fill=fill,
            text_color=text_color,
            font=font,
            size_pt=size_pt,
            min_size_pt=min_size_pt,
        )
    _tag_group(slide, "cycle", cards + arrows)
    return CycleResult(cards=cards, arrows=arrows)


def _build_cycle(
    slide,
    coerced: list[_Step],
    cx: int,
    cy: int,
    radius: int,
    card_diameter: int,
    *,
    accent: str,
    fill: str,
    text_color: str,
    font: str | None,
    size_pt: float,
    min_size_pt: float,
) -> tuple[list[Any], list[Any]]:
    """Add the nodes and arrows of :func:`cycle` to *slide*."""
    n = len(coerced)
    cards = [
        _add_step_node(
            slide,
            step,
            _ring_point((cx, cy), radius, _ring_angle(i, n)),
            card_diameter,
            fill=fill,
            accent=accent,
            text_color=text_color,
            font=font,
            size_pt=size_pt,
            min_size_pt=min_size_pt,
            what=f"cycle ({n} steps)",
        )
        for i, step in enumerate(coerced)
    ]

    arrows: list[Any] = []
    for i in range(n):
        j = (i + 1) % n
        arrow = slide.shapes.add_arrow(
            cards[i],
            cards[j],
            head="triangle",
            color=accent,
            weight_pt=1.5,
            inset_pt=2.0,
            route="curved",
        )
        arrows.append(arrow)
    return cards, arrows


# ----------------------------------------------------------------------------- decision tree


def decision_tree(
    slide,
    bbox: BBox,
    *,
    root: str,
    branches: Sequence[Any],
    accent: str = "#0B5CFF",
    fill: str = "#FFFFFF",
    text_color: str = "#0D0D0D",
    font: str | None = None,
    size_pt: float = 13.0,
    root_fill: str | None = None,
    root_text_color: str = "#FFFFFF",
    leaf_fill: str | None = None,
    leaf_text_color: str | None = None,
    min_size_pt: float = _MIN_LABEL_PT,
) -> DecisionTreeResult:
    """Decision tree — root question with N branch outcomes underneath.

    ``branches`` may be plain labels (each becomes a leaf) or dicts with
    ``label`` and optional ``children=[…]`` for one additional level
    (sufficient for most decision-tree slides).

    Children are stacked under their branch and indented, with a
    connector running down the indent and a short arrow into each child
    — like a file tree — so no arrow crosses another child's card.
    ``result.arrows`` holds, per branch, the root-to-branch arrow, then
    that connector, then one arrow per child.

    Leaf (child) nodes inherit ``fill`` / ``text_color`` from the recipe by
    default so a dark deck with light text stays legible.  Pass ``leaf_fill``
    / ``leaf_text_color`` to give the leaves a deliberately distinct style.

    A card that cannot hold its label at ``min_size_pt`` raises
    :class:`ValueError` and nothing is added to the slide.
    """
    with _atomic(slide):
        return _decision_tree(
            slide,
            bbox,
            root=root,
            branches=branches,
            accent=accent,
            fill=fill,
            text_color=text_color,
            font=font,
            size_pt=size_pt,
            root_fill=root_fill,
            root_text_color=root_text_color,
            leaf_fill=leaf_fill,
            leaf_text_color=leaf_text_color,
            min_size_pt=min_size_pt,
        )


def _decision_tree(
    slide,
    bbox: BBox,
    *,
    root: str,
    branches: Sequence[Any],
    accent: str,
    fill: str,
    text_color: str,
    font: str | None,
    size_pt: float,
    root_fill: str | None,
    root_text_color: str,
    leaf_fill: str | None,
    leaf_text_color: str | None,
    min_size_pt: float,
) -> DecisionTreeResult:
    """Build :func:`decision_tree`; the caller removes partial output on error."""
    leaf_fill = leaf_fill if leaf_fill is not None else fill
    leaf_text_color = leaf_text_color if leaf_text_color is not None else text_color
    if not branches:
        raise ValueError("branches must be non-empty")

    # Root sits at the top, taking ~25% of the height.
    root_h = int(int(bbox.height) * 0.25)
    root_w = max(int(int(bbox.width) * 0.4), int(Inches(2)))
    root_box = BBox(
        Emu(int(bbox.cx) - root_w // 2),
        bbox.top,
        Emu(root_w),
        Emu(root_h),
    )
    root_card = _card(
        slide,
        root_box,
        fill=root_fill or accent,
        line=None,
        text=root,
        text_color=root_text_color,
        font=font,
        size_pt=size_pt,
        bold=True,
        radius=0.05,
        min_size_pt=min_size_pt,
        what="decision_tree root",
    )

    # Branches fill the lower 70% of bbox.
    branch_area = BBox(
        bbox.left,
        Emu(int(bbox.top) + int(root_h * 1.4)),
        bbox.width,
        Emu(int(bbox.height) - int(root_h * 1.4)),
    )
    coerced = _coerce_branches(branches)
    style = _TreeStyle(
        accent=accent,
        fill=fill,
        text_color=text_color,
        leaf_fill=leaf_fill,
        leaf_text_color=leaf_text_color,
        font=font,
        size_pt=size_pt,
        min_size_pt=min_size_pt,
    )

    n = len(coerced)
    col_boxes = branch_area.split_h([1] * n, gap=int(Pt(8)))
    built: list[Any] = []
    arrows: list[Any] = []
    for branch, col in zip(coerced, col_boxes):
        cards, links = _add_tree_branch(slide, root_card, branch, col, n, style)
        built += cards
        arrows += links
    _tag_group(slide, "decision-tree", [root_card] + built + arrows)
    return DecisionTreeResult(root=root_card, branches=built, arrows=arrows)


@dataclass(frozen=True)
class _TreeStyle:
    """How :func:`decision_tree` draws its branch and leaf cards and arrows."""

    accent: str
    fill: str
    text_color: str
    leaf_fill: str
    leaf_text_color: str
    font: str | None
    size_pt: float
    min_size_pt: float


def _coerce_branches(branches: Sequence[Any]) -> list[dict[str, Any]]:
    """Normalise each branch to ``{"label": ..., "children": [...]}``."""
    coerced = []
    for b in branches:
        if isinstance(b, str):
            coerced.append({"label": b, "children": []})
        elif isinstance(b, dict):
            coerced.append({"label": b["label"], "children": b.get("children", [])})
        else:
            raise TypeError(f"branches items must be str or dict; got {type(b).__name__}")
    return coerced


def _add_tree_branch(
    slide: "Slide",
    root_card: Any,
    branch: dict[str, Any],
    col: BBox,
    n_branches: int,
    style: _TreeStyle,
) -> tuple[list[Any], list[Any]]:
    """Add one branch card in *col*, linked to *root_card*, with any children below it.

    Returns ``(cards, arrows)``: the branch card then its children, and the
    root-to-branch arrow then the children's links.
    """
    children = branch["children"]
    if children:
        label_box, children_box = col.split_v([1, 3], gap=int(Pt(8)))
    else:
        label_box, children_box = col, None
    branch_card = _card(
        slide,
        label_box,
        fill=style.fill,
        line=style.accent,
        text=branch["label"],
        text_color=style.text_color,
        font=style.font,
        size_pt=style.size_pt,
        bold=False,
        radius=0.04,
        min_size_pt=style.min_size_pt,
        what=f"decision_tree ({n_branches} branches)",
    )
    arrow = slide.shapes.add_arrow(
        root_card,
        branch_card,
        head="triangle",
        color=style.accent,
        weight_pt=1.5,
        inset_pt=4.0,
    )
    if children_box is None:
        return [branch_card], [arrow]
    child_cards, child_links = _add_tree_children(
        slide, children, col, label_box, children_box, style
    )
    return [branch_card, *child_cards], [arrow, *child_links]


def _add_tree_children(
    slide: "Slide",
    children: Sequence[Any],
    col: BBox,
    label_box: BBox,
    children_box: BBox,
    style: _TreeStyle,
) -> tuple[list[Any], list[Any]]:
    """Stack the leaf cards of one branch in *children_box*; return ``(cards, arrows)``.

    The children are siblings, so each needs its own link to the branch.
    Straight branch-to-child arrows would run through the children above;
    instead the children are indented and a rail down the indent feeds a
    short arrow into each one's left edge.  The rail is the first arrow.
    """
    indent = min(int(int(col.width) * 0.18), int(Inches(0.35)))
    rail_x = int(col.left) + indent // 2
    child_area = BBox(
        Emu(int(children_box.left) + indent),
        children_box.top,
        Emu(int(children_box.width) - indent),
        children_box.height,
    )
    child_boxes = child_area.split_v([1] * len(children), gap=int(Pt(6)))
    last_cy = int(child_boxes[-1].cy)
    arrows = [
        slide.shapes.add_arrow(
            (Emu(rail_x), Emu(int(label_box.bottom))),
            (Emu(rail_x), Emu(last_cy)),
            head=None,
            color=style.accent,
            weight_pt=1.0,
        )
    ]
    cards = []
    for c, cb in zip(children, child_boxes):
        label = c if isinstance(c, str) else c.get("label", "")
        cards.append(
            _card(
                slide,
                cb,
                fill=style.leaf_fill,
                line=None,
                text=label,
                text_color=style.leaf_text_color,
                font=style.font,
                size_pt=style.size_pt * 0.9,
                radius=0.04,
                min_size_pt=style.min_size_pt,
                what=f"decision_tree ({len(child_boxes)} children)",
            )
        )
        arrows.append(
            slide.shapes.add_arrow(
                (Emu(rail_x), Emu(int(cb.cy))),
                (Emu(int(cb.left) - int(Pt(1))), Emu(int(cb.cy))),
                head="triangle",
                color=style.accent,
                weight_pt=1.0,
            )
        )
    return cards, arrows


# ----------------------------------------------------------------------------- columns


def comparison_columns(
    slide,
    bbox: BBox,
    columns: Sequence[Any],
    *,
    header_fill: str = "#0B5CFF",
    header_text_color: str = "#FFFFFF",
    body_fill: str = "#FFFFFF",
    text_color: str = "#0D0D0D",
    font: str | None = None,
    header_size_pt: float = 16.0,
    body_size_pt: float = 12.0,
    gap: int | None = None,
) -> ColumnsResult:
    """N-column comparison layout.

    Each column has a header card and a body card stacked vertically.
    ``columns`` is a list of dicts shaped
    ``{"title": str, "body": str | list[str]}``.
    """
    if not columns:
        raise ValueError("columns must be non-empty")
    if gap is None:
        gap = int(Pt(12))

    col_boxes = bbox.split_h([1] * len(columns), gap=gap)
    header_h = int(int(bbox.height) * 0.18)
    built_columns: list[Any] = []
    built_headers: list[Any] = []

    for spec, col in zip(columns, col_boxes):
        title, body = _column_texts(spec)
        header_box = BBox(col.left, col.top, col.width, Emu(header_h))
        body_box = BBox(
            col.left,
            Emu(int(col.top) + header_h + int(Pt(6))),
            col.width,
            Emu(int(col.height) - header_h - int(Pt(6))),
        )

        header = _card(
            slide,
            header_box,
            fill=header_fill,
            line=None,
            text=title,
            text_color=header_text_color,
            font=font,
            size_pt=header_size_pt,
            bold=True,
            radius=0.05,
        )
        body_card = _add_column_body(
            slide,
            body_box,
            body,
            fill=body_fill,
            line=header_fill,
            text_color=text_color,
            font=font,
            size_pt=body_size_pt,
        )
        built_headers.append(header)
        built_columns.append(body_card)
    _tag_group(slide, "columns", built_headers + built_columns)
    return ColumnsResult(columns=built_columns, headers=built_headers)


def _column_texts(spec: Any) -> tuple[Any, Any]:
    """Return ``(title, body)`` of a column spec; a bare string is a title alone.

    A list body is one line per item.
    """
    if isinstance(spec, str):
        spec = {"title": spec, "body": ""}
    title = spec.get("title", "")
    body = spec.get("body", "")
    if isinstance(body, list):
        body = "\n".join(str(item) for item in body)
    return title, body


def _add_column_body(
    slide: "Slide",
    box: BBox,
    text: str,
    *,
    fill: str,
    line: str,
    text_color: str,
    font: str | None,
    size_pt: float,
) -> Any:
    """Add a column's body card: top-anchored text, shrunk to fit where it can be."""
    from power_pptx.enum.text import MSO_VERTICAL_ANCHOR

    body_card = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *box)
    body_card.fill_hex(fill)
    body_card.line_hex(line, weight_pt=1.0)
    tf = body_card.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_VERTICAL_ANCHOR.TOP
    margin = Pt(8)
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = margin
    tf.text = text
    _style_runs(tf, font=font, size_pt=size_pt, color=text_color)
    # Shrink a long body so it doesn't overflow the column card / slide.
    with suppress(ValueError, OSError):
        tf.fit_text(font_family=font, max_size=max(1, int(round(size_pt))))
    return body_card
