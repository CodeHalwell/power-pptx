"""Named chart color palettes, applied independently of `chart_style`.

The PowerPoint `chart_style` integer (1-48) bundles a fill palette together with
font, axis, and gridline tweaks. Users who want to recolor only the series — for
example to match a brand palette — without inheriting the rest of the style end
up either fighting the chart_style enum or hand-painting each series. This module
exposes a small set of curated palettes plus a tiny resolver that
`Chart.apply_palette` uses to translate a name or sequence into concrete
``RGBColor`` values.

Adding a palette here is intentionally lightweight: drop a new entry in
``CHART_PALETTES`` and it becomes addressable by name from ``apply_palette``.
"""

from __future__ import annotations

from typing import Iterable, Sequence, Union

from power_pptx.dml.color import RGBColor

ColorLike = Union[RGBColor, str, Sequence[int]]
"""Anything ``_to_rgb`` knows how to turn into an `RGBColor`."""


CHART_PALETTES: dict[str, tuple[str, ...]] = {
    # Saturated, contemporary brand palette — pairs well with the "Modern"
    # design-token starter pack.
    "modern": (
        "#2D3142",
        "#4F5D75",
        "#EF8354",
        "#BFC0C0",
        "#FFFFFF",
        "#057DCD",
    ),
    # Conservative, presentation-friendly palette — close to PowerPoint's
    # default Office accents but a touch desaturated for print.
    "classic": (
        "#1F4E79",
        "#2E75B6",
        "#9DC3E6",
        "#C00000",
        "#7F6000",
        "#548235",
    ),
    # Higher-contrast editorial palette — useful for narrative decks where
    # one series should clearly dominate.
    "editorial": (
        "#0B132B",
        "#1C2541",
        "#3A506B",
        "#5BC0BE",
        "#6FFFE9",
        "#FF6B6B",
    ),
    # Vibrant categorical palette — eight colors so 5+ series stay readable.
    "vibrant": (
        "#E63946",
        "#F1A208",
        "#2A9D8F",
        "#264653",
        "#7209B7",
        "#3A86FF",
        "#FB5607",
        "#06D6A0",
    ),
    # Monochrome blue ramp — ordered, useful when categories have a natural
    # progression (light-to-dark).
    "monochrome_blue": (
        "#CFE2F3",
        "#9FC5E8",
        "#6FA8DC",
        "#3D85C6",
        "#0B5394",
        "#073763",
    ),
    # Monochrome warm ramp.
    "monochrome_warm": (
        "#FFF4E6",
        "#FFD8A8",
        "#FFA94D",
        "#FF922B",
        "#E8590C",
        "#A5450A",
    ),
}


def palette_names() -> tuple[str, ...]:
    """Return the names of the built-in palettes, in declaration order."""
    return tuple(CHART_PALETTES.keys())


def resolve_palette(palette: Union[str, Iterable[ColorLike]]) -> tuple[RGBColor, ...]:
    """Return a tuple of `RGBColor` values for a palette name or sequence.

    `palette` is either:

    * A string naming a built-in palette (see :func:`palette_names`), or
    * An iterable of color-likes — `RGBColor`, hex strings (with or without
      leading ``'#'``), or 3-tuples of ints in ``0-255``.

    Raises ``ValueError`` if `palette` is an unknown name or resolves to an
    empty sequence (which would make :meth:`Chart.apply_palette` a no-op and
    silently mask user error).
    """
    if isinstance(palette, str):
        try:
            colors = CHART_PALETTES[palette]
        except KeyError:
            raise ValueError(
                "unknown palette %r; choose from %r" % (palette, palette_names())
            )
        return tuple(RGBColor.from_hex(c) for c in colors)

    resolved = tuple(_to_rgb(c) for c in palette)
    if not resolved:
        raise ValueError("palette must contain at least one color")
    return resolved


def _to_rgb(color: ColorLike) -> RGBColor:
    if isinstance(color, RGBColor):
        return color
    if isinstance(color, str):
        return RGBColor.from_hex(color)
    # Treat any other sequence as an (r, g, b) triple.
    r, g, b = color
    return RGBColor(r, g, b)
