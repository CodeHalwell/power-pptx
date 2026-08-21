"""Internal shared text-styling vocabulary.

One place to translate the short, string-flavoured keywords the public
surface accepts (``align="center"``, ``anchor="middle"``, ``size_pt=11``,
``color="#1F2937"``) into the enum / :class:`~power_pptx.util.Length`
values the XML layer wants.

Used by :meth:`ShapeTree.add_text` and :meth:`power_pptx.table._Cell.format`
so the same words mean the same thing wherever text is styled.
"""

from __future__ import annotations

from typing import Any, Sequence

from power_pptx._color import coerce_color
from power_pptx.enum.text import MSO_VERTICAL_ANCHOR, PP_PARAGRAPH_ALIGNMENT
from power_pptx.util import Length, Pt

ALIGN_MAP = {
    "left": PP_PARAGRAPH_ALIGNMENT.LEFT,
    "right": PP_PARAGRAPH_ALIGNMENT.RIGHT,
    "center": PP_PARAGRAPH_ALIGNMENT.CENTER,
    "centre": PP_PARAGRAPH_ALIGNMENT.CENTER,
    "justify": PP_PARAGRAPH_ALIGNMENT.JUSTIFY,
}

ANCHOR_MAP = {
    "top": MSO_VERTICAL_ANCHOR.TOP,
    "middle": MSO_VERTICAL_ANCHOR.MIDDLE,
    "center": MSO_VERTICAL_ANCHOR.MIDDLE,
    "centre": MSO_VERTICAL_ANCHOR.MIDDLE,
    "bottom": MSO_VERTICAL_ANCHOR.BOTTOM,
}


def coerce_align(value: str) -> PP_PARAGRAPH_ALIGNMENT:
    """Return the `PP_ALIGN` member named by `value` (case-insensitive)."""
    try:
        return ALIGN_MAP[str(value).lower()]
    except KeyError:
        raise ValueError(
            f"align must be one of {sorted(set(ALIGN_MAP))}; got {value!r}"
        ) from None


def coerce_anchor(value: str) -> MSO_VERTICAL_ANCHOR:
    """Return the `MSO_VERTICAL_ANCHOR` member named by `value` (case-insensitive)."""
    try:
        return ANCHOR_MAP[str(value).lower()]
    except KeyError:
        raise ValueError(
            f"anchor must be one of {sorted(set(ANCHOR_MAP))}; got {value!r}"
        ) from None


def coerce_length(value: Any) -> Length:
    """Coerce a point number or a `Length` to a `Length`."""
    return value if isinstance(value, Length) else Pt(float(value))



def apply_margins(
    tf: Any, margin: float | Length | Sequence[float | Length] | None
) -> None:
    """Set text-frame insets from a scalar or a ``(top, right, bottom, left)`` sequence.

    Scalars in points (or any :class:`~power_pptx.util.Length`) — ``0`` means
    "flush to the edge", which is what a dense table cell usually wants.
    """
    if margin is None:
        return
    if isinstance(margin, (tuple, list)):
        if len(margin) != 4:
            raise ValueError(
                "margin tuple must have 4 elements (top, right, bottom, left); "
                f"got {len(margin)}"
            )
        top, right, bottom, left = (coerce_length(v) for v in margin)
    else:
        top = right = bottom = left = coerce_length(margin)
    tf.margin_top, tf.margin_right = top, right
    tf.margin_bottom, tf.margin_left = bottom, left


def apply_text_style(
    tf: Any,
    *,
    font: str | None = None,
    size_pt: float | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
    color: Any = None,
    align: str | None = None,
    anchor: str | None = None,
    margin: float | Length | Sequence[float | Length] | None = None,
    word_wrap: bool | None = None,
    paragraph_defaults: bool = False,
) -> None:
    """Apply the shared text-styling keywords to text frame `tf`.

    Every keyword is optional and ``None`` means "leave as-is", so this can be
    layered over text that already carries formatting.  `paragraph_defaults`
    additionally writes the run properties onto each paragraph's default run
    properties, so text added to the frame *later* inherits the styling —
    what a table cell wants, and what a one-shot ``add_text`` does not need.
    """
    if word_wrap is not None:
        tf.word_wrap = bool(word_wrap)
    apply_margins(tf, margin)
    if anchor is not None:
        tf.vertical_anchor = coerce_anchor(anchor)

    align_value = None if align is None else coerce_align(align)
    rgb = None if color is None else coerce_color(color)
    size = None if size_pt is None else coerce_length(size_pt)

    for paragraph in tf.paragraphs:
        if align_value is not None:
            paragraph.alignment = align_value
        fonts = [run.font for run in paragraph.runs]
        if paragraph_defaults:
            fonts.append(paragraph.font)
        for f in fonts:
            if font is not None:
                f.name = font
            if size is not None:
                f.size = size
            if bold is not None:
                f.bold = bool(bold)
            if italic is not None:
                f.italic = bool(italic)
            if rgb is not None:
                f.color.rgb = rgb


__all__ = [
    "ALIGN_MAP",
    "ANCHOR_MAP",
    "apply_margins",
    "apply_text_style",
    "coerce_align",
    "coerce_anchor",
    "coerce_length",
]
