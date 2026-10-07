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

import contextlib
import itertools
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.geometry import BBox
from power_pptx.util import Emu, Inches, Pt

if TYPE_CHECKING:
    from power_pptx.shapes.autoshape import Shape


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
            with contextlib.suppress(Exception):
                s.lint_group = prefix


#: Nodes shrink no further than this fraction of their requested size when a ring is crowded.
_MIN_RING_SCALE = 0.05


def _ring_is_clear(
    n: int,
    half: float,
    node_d: float,
    hub_d: float,
    scale: float,
    node_gap: float,
    hub_gap: float,
) -> bool:
    """Return True when *n* nodes of diameter ``node_d * scale`` clear each other and the hub.

    The nodes sit on a circle that touches the edge of a square of half-width *half*,
    starting at the top.  Clearance is judged on the nodes' *bounding boxes* — the
    shapes the linter compares — and each pair must also be at least *node_gap* /
    *hub_gap* (a fraction of the node diameter) apart, so an arrow between them has
    something to draw.
    """
    d = node_d * scale
    radius = half - d / 2
    if radius <= 0:
        return False
    points = [
        (
            radius * math.cos(2 * math.pi * i / n - math.pi / 2),
            radius * math.sin(2 * math.pi * i / n - math.pi / 2),
        )
        for i in range(n)
    ]
    if hub_d:
        reach = (hub_d * scale + d) / 2 + hub_gap * d
        if any(max(abs(x), abs(y)) < reach for x, y in points):
            return False
    need = d * (1 + node_gap)
    return all(
        max(abs(ax - bx), abs(ay - by)) >= need
        for (ax, ay), (bx, by) in itertools.combinations(points, 2)
    )


def _fit_ring(
    n: int,
    half: float,
    node_d: float,
    *,
    hub_d: float = 0.0,
    node_gap: float = 0.12,
    hub_gap: float = 0.12,
) -> tuple[float, float]:
    """Return ``(scale, radius)`` for *n* nodes of diameter *node_d* (EMU) on a ring.

    The ring touches the edge of a square of half-width *half*.  *scale* is 1.0 when
    the nodes — and the optional centre hub of diameter *hub_d* — fit as requested,
    and otherwise the largest factor (found by bisection, since shrinking only ever
    adds room) at which nothing overlaps; apply it to every diameter.  *radius* is the
    distance from the centre to each node's centre.
    """

    def clear(scale: float) -> bool:
        return _ring_is_clear(n, half, node_d, hub_d, scale, node_gap, hub_gap)

    scale = 1.0
    if not clear(1.0):
        low, high = _MIN_RING_SCALE, 1.0
        for _ in range(30):
            mid = (low + high) / 2
            if clear(mid):
                low = mid
            else:
                high = mid
        scale = low
    return scale, half - node_d * scale / 2


def _fit_circular_label(
    shape: Any,
    *,
    diameter: int,
    font: str | None,
    max_size_pt: float,
    bold: bool = False,
    italic: bool = False,
) -> None:
    """Shrink a circular node's label so it never clips the curved edge.

    The headline reason this fork exists is space-awareness, so the diagram
    recipes use the same ``fit_text`` pre-flight as everything else.  A circle's
    usable text area is narrower than its bounding box, so we inset the text
    frame by a fraction of the diameter — that keeps long words such as
    "Retrieval" inside the circle instead of wrapping to "Retriev al".

    The text area of an ellipse is its *inscribed* rectangle, 0.7071 of the box
    a side, and the insets come off that.  ``fit_text`` only knows the bounding
    box less the margins, so the fit is measured with margins wide enough that
    what is left is the real text area, and the render insets are set afterwards.
    """
    tf = shape.text_frame
    tf.word_wrap = True
    h_inset = Emu(int(diameter * 0.14))
    v_inset = Emu(int(diameter * 0.08))
    rim = int(diameter * (1 - math.cos(math.pi / 4)) / 2)
    tf.margin_left = tf.margin_right = Emu(int(h_inset) + rim)
    tf.margin_top = tf.margin_bottom = Emu(int(v_inset) + rim)
    # Degrade gracefully: if even 1pt won't fit (tiny circle) or no font
    # metrics are available, keep the size the caller already set.
    with contextlib.suppress(ValueError, OSError):
        tf.fit_text(
            font_family=font,
            max_size=max(1, int(round(max_size_pt))),
            bold=bold,
            italic=italic,
        )
    tf.margin_left = tf.margin_right = h_inset
    tf.margin_top = tf.margin_bottom = v_inset


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
) -> "Shape":
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
        for para in tf.paragraphs:
            para.alignment = PP_PARAGRAPH_ALIGNMENT.CENTER
            for run in para.runs:
                if font is not None:
                    run.font.name = font
                run.font.size = Pt(float(size_pt))
                run.font.bold = bool(bold)
                from power_pptx._color import coerce_color

                run.font.color.rgb = coerce_color(text_color)
        # Space-awareness: shrink the label so a long word never clips its card
        # (the rectangular siblings of the already-fitted circular nodes).
        with contextlib.suppress(ValueError, OSError):
            tf.fit_text(
                font_family=font,
                max_size=max(1, int(round(size_pt))),
                bold=bool(bold),
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
) -> PipelineResult:
    """Horizontal pipeline of N steps with arrows between them.

    Each step renders as an evenly-sized card with a centered label.
    Arrows are routed mid-edge with a small inset so the arrowhead
    doesn't bleed into the next card.

    ``steps`` may be a list of plain strings or ``{"label": ..., "sublabel": ...,
    "fill": ..., "text_color": ...}`` dicts.
    """
    coerced = _coerce_steps(steps)
    n = len(coerced)
    if gap is None:
        gap = int(Pt(12))

    card_boxes = bbox.split_h([1] * n, gap=gap)
    cards: list[Any] = []
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
            )
        )

    arrows: list[Any] = []
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
    """Vertical pipeline — same as :func:`horizontal_pipeline` but stacked."""
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
    if kwargs:
        raise TypeError(f"unexpected keyword arguments: {sorted(kwargs)}")

    card_boxes = bbox.split_v([1] * n, gap=gap)
    cards: list[Any] = []
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
            )
        )
    arrows: list[Any] = []
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
) -> HubAndSpokeResult:
    """Hub-and-spoke diagram with N spokes radially arranged.

    ``centre`` is the label of the hub.  ``spokes`` is an iterable of
    string labels or step-dicts (see :func:`horizontal_pipeline`).

    The hub sits in the middle of *bbox* and the spokes on a ring that
    touches the edge of its shorter side, so the arrows have room to show.
    The hub is ``0.25 * hub_size`` and each spoke ``0.2 * spoke_size`` of
    that side; when that many spokes would overlap the hub or each other
    the hub and every spoke shrink together, keeping their proportions,
    until they do not.  The only overlaps the diagram declares are each
    arrow's with the hub and with its own spoke, so the linter still sees
    any other.
    """
    coerced = _coerce_steps(spokes)
    n = len(coerced)

    # Place the hub in the centre at ~25% of the smaller dimension, then fit the
    # ring of spokes around it: the diameters shrink when the ring is crowded.
    short = min(int(bbox.width), int(bbox.height))
    scale, radius = _fit_ring(n, short / 2, short * 0.2 * spoke_size, hub_d=short * 0.25 * hub_size)
    hub_diameter = int(short * 0.25 * hub_size * scale)
    spoke_diameter = int(short * 0.2 * spoke_size * scale)
    cx, cy = int(bbox.cx), int(bbox.cy)

    hub_box = BBox(
        Emu(cx - hub_diameter // 2),
        Emu(cy - hub_diameter // 2),
        Emu(hub_diameter),
        Emu(hub_diameter),
    )
    from power_pptx._color import coerce_color
    from power_pptx.enum.text import MSO_VERTICAL_ANCHOR, PP_PARAGRAPH_ALIGNMENT

    hub = slide.shapes.add_shape(MSO_SHAPE.OVAL, *hub_box)
    hub.fill_hex(hub_fill or accent)
    hub.line.fill.background()

    tf = hub.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
    tf.text = centre
    for para in tf.paragraphs:
        para.alignment = PP_PARAGRAPH_ALIGNMENT.CENTER
        for run in para.runs:
            if font is not None:
                run.font.name = font
            run.font.size = Pt(float(size_pt))
            run.font.bold = True
            run.font.color.rgb = coerce_color(hub_text_color)
    _fit_circular_label(hub, diameter=hub_diameter, font=font, max_size_pt=size_pt, bold=True)

    # Place spokes evenly around the hub.
    spokes_built: list[Any] = []
    arrows: list[Any] = []
    for i, step in enumerate(coerced):
        angle = 2 * math.pi * i / n - math.pi / 2  # start at top
        sx = cx + int(radius * math.cos(angle))
        sy = cy + int(radius * math.sin(angle))
        spoke_box = BBox(
            Emu(sx - spoke_diameter // 2),
            Emu(sy - spoke_diameter // 2),
            Emu(spoke_diameter),
            Emu(spoke_diameter),
        )
        spoke = slide.shapes.add_shape(MSO_SHAPE.OVAL, *spoke_box)
        spoke.fill_hex(step.fill or fill)
        spoke.line_hex(accent, weight_pt=1.5)
        tfs = spoke.text_frame
        tfs.word_wrap = True
        tfs.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
        tfs.text = step.label
        for para in tfs.paragraphs:
            para.alignment = PP_PARAGRAPH_ALIGNMENT.CENTER
            for run in para.runs:
                if font is not None:
                    run.font.name = font
                run.font.size = Pt(float(size_pt) * 0.85)
                from power_pptx._color import coerce_color

                run.font.color.rgb = coerce_color(step.text_color or text_color)
        _fit_circular_label(spoke, diameter=spoke_diameter, font=font, max_size_pt=size_pt * 0.85)

        spokes_built.append(spoke)
        arrow = slide.shapes.add_arrow(
            hub,
            spoke,
            head="triangle",
            color=accent,
            weight_pt=1.5,
            inset_pt=2.0,
        )
        # An arrow runs into the two shapes it joins; that is the only overlap this
        # diagram intends, so allow it pair by pair rather than as one big group.
        arrow.allow_overlap_with(hub, spoke)
        arrows.append(arrow)
    return HubAndSpokeResult(hub=hub, spokes=spokes_built, arrows=arrows)


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
) -> CycleResult:
    """Cyclic diagram — N cards arranged in a circle with arrows ``i → i+1``.

    The last arrow loops back from card N-1 to card 0, completing the
    cycle.  The cards sit on a ring touching the edge of the shorter side
    of *bbox* and are ``0.22`` of that side across; they stay that size for
    up to about eight steps and shrink, together, beyond that so that
    neighbouring cards never overlap and each arrow has room to show.  The
    only overlaps the diagram declares are each arrow's with the two cards
    it joins, so the linter still sees any other.
    """
    coerced = _coerce_steps(steps)
    n = len(coerced)
    short = min(int(bbox.width), int(bbox.height))
    scale, radius = _fit_ring(n, short / 2, short * 0.22, node_gap=0.25)
    card_diameter = int(short * 0.22 * scale)
    cx, cy = int(bbox.cx), int(bbox.cy)

    cards: list[Any] = []
    for i, step in enumerate(coerced):
        angle = 2 * math.pi * i / n - math.pi / 2
        sx = cx + int(radius * math.cos(angle))
        sy = cy + int(radius * math.sin(angle))
        card_box = BBox(
            Emu(sx - card_diameter // 2),
            Emu(sy - card_diameter // 2),
            Emu(card_diameter),
            Emu(card_diameter),
        )
        card = slide.shapes.add_shape(MSO_SHAPE.OVAL, *card_box)
        card.fill_hex(step.fill or fill)
        card.line_hex(accent, weight_pt=1.5)
        from power_pptx._color import coerce_color
        from power_pptx.enum.text import MSO_VERTICAL_ANCHOR, PP_PARAGRAPH_ALIGNMENT

        tf = card.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
        tf.text = step.label
        for para in tf.paragraphs:
            para.alignment = PP_PARAGRAPH_ALIGNMENT.CENTER
            for run in para.runs:
                if font is not None:
                    run.font.name = font
                run.font.size = Pt(float(size_pt))
                run.font.color.rgb = coerce_color(step.text_color or text_color)
        _fit_circular_label(card, diameter=card_diameter, font=font, max_size_pt=size_pt)
        cards.append(card)

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
        # An arrow runs into the two cards it joins; allow exactly that, pair by pair.
        arrow.allow_overlap_with(cards[i], cards[j])
        arrows.append(arrow)
    return CycleResult(cards=cards, arrows=arrows)


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
) -> DecisionTreeResult:
    """Decision tree — root question with N branch outcomes underneath.

    ``branches`` may be plain labels (each becomes a leaf) or dicts with
    ``label`` and optional ``children=[…]`` for one additional level
    (sufficient for most decision-tree slides).

    Leaf (child) nodes inherit ``fill`` / ``text_color`` from the recipe by
    default so a dark deck with light text stays legible.  Pass ``leaf_fill``
    / ``leaf_text_color`` to give the leaves a deliberately distinct style.
    """
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
    )

    # Branches fill the lower 70% of bbox.
    branch_area = BBox(
        bbox.left,
        Emu(int(bbox.top) + int(root_h * 1.4)),
        bbox.width,
        Emu(int(bbox.height) - int(root_h * 1.4)),
    )
    coerced = []
    for b in branches:
        if isinstance(b, str):
            coerced.append({"label": b, "children": []})
        elif isinstance(b, dict):
            coerced.append({"label": b["label"], "children": b.get("children", [])})
        else:
            raise TypeError(f"branches items must be str or dict; got {type(b).__name__}")

    n = len(coerced)
    col_boxes = branch_area.split_h([1] * n, gap=int(Pt(8)))
    built: list[Any] = []
    arrows: list[Any] = []
    for branch, col in zip(coerced, col_boxes):
        has_children = bool(branch["children"])
        if has_children:
            split = col.split_v([1, 3], gap=int(Pt(8)))
            label_box = split[0]
            children_box = split[1]
        else:
            label_box = col
            children_box = None
        branch_card = _card(
            slide,
            label_box,
            fill=fill,
            line=accent,
            text=branch["label"],
            text_color=text_color,
            font=font,
            size_pt=size_pt,
            bold=False,
            radius=0.04,
        )
        built.append(branch_card)
        arrow = slide.shapes.add_arrow(
            root_card,
            branch_card,
            head="triangle",
            color=accent,
            weight_pt=1.5,
            inset_pt=4.0,
        )
        arrows.append(arrow)
        if children_box is not None:
            child_boxes = children_box.split_v([1] * len(branch["children"]), gap=int(Pt(6)))
            for c, cb in zip(branch["children"], child_boxes):
                label = c if isinstance(c, str) else c.get("label", "")
                child_card = _card(
                    slide,
                    cb,
                    fill=leaf_fill,
                    line=None,
                    text=label,
                    text_color=leaf_text_color,
                    font=font,
                    size_pt=size_pt * 0.9,
                    radius=0.04,
                )
                built.append(child_card)
                arrows.append(
                    slide.shapes.add_arrow(
                        branch_card,
                        child_card,
                        head="triangle",
                        color=accent,
                        weight_pt=1.0,
                        inset_pt=3.0,
                    )
                )
    _tag_group(slide, "decision-tree", [root_card] + built + arrows)
    return DecisionTreeResult(root=root_card, branches=built, arrows=arrows)


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
    from power_pptx._color import coerce_color
    from power_pptx.enum.text import MSO_VERTICAL_ANCHOR

    for spec, col in zip(columns, col_boxes):
        if isinstance(spec, str):
            spec = {"title": spec, "body": ""}
        title = spec.get("title", "")
        body = spec.get("body", "")
        if isinstance(body, list):
            body = "\n".join(str(item) for item in body)

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
        body_card = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *body_box)
        body_card.fill_hex(body_fill)
        body_card.line_hex(header_fill, weight_pt=1.0)
        tf = body_card.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_VERTICAL_ANCHOR.TOP
        margin = Pt(8)
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = margin
        tf.text = body
        for para in tf.paragraphs:
            for run in para.runs:
                if font is not None:
                    run.font.name = font
                run.font.size = Pt(float(body_size_pt))
                run.font.color.rgb = coerce_color(text_color)
        # Shrink a long body so it doesn't overflow the column card / slide.
        with contextlib.suppress(ValueError, OSError):
            tf.fit_text(font_family=font, max_size=max(1, int(round(body_size_pt))))
        built_headers.append(header)
        built_columns.append(body_card)
    _tag_group(slide, "columns", built_headers + built_columns)
    return ColumnsResult(columns=built_columns, headers=built_headers)
