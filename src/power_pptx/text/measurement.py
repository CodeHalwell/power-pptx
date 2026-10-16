"""Read-only text measurement for declarative layouts and pre-flight checks."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

from power_pptx.exc import FontMetricsWarning
from power_pptx.text.fonts import find_font_file
from power_pptx.text.layout import TextFitter, _LineSource, _rendered_size
from power_pptx.util import Emu, Length


@dataclass(frozen=True)
class TextMeasurement:
    lines: tuple[str, ...]
    width: Length
    height: Length
    font_size_pt: int
    font_file: str | None
    used_fallback: bool


def measure_text(
    text: str,
    width: Length,
    *,
    size_pt: int = 18,
    font_family: str | None = None,
    font_file: str | None = None,
    bold: bool = False,
    italic: bool = False,
    line_spacing: float = 1.2,
    strict: bool = False,
) -> TextMeasurement:
    """Measure wrapped text with the same font metrics as ``fit_text``.

    Raises when a whole word cannot fit at the requested size. No slide or
    text frame is changed. Explicit line breaks and empty lines are preserved.
    ``strict`` requires real metrics; otherwise ``used_fallback`` identifies
    estimates, and a missing explicitly requested family emits a warning.
    """
    if width <= 0 or isinstance(size_pt, bool) or not isinstance(size_pt, int) or size_pt < 1:
        raise ValueError("width and integer size_pt must be positive")
    if not math.isfinite(line_spacing) or line_spacing <= 0:
        raise ValueError("line_spacing must be finite and positive")
    path = font_file or find_font_file(font_family or "Calibri", bold, italic)
    if path is None:
        message = (
            f"Font {font_family or 'Calibri'!r} is unavailable; measurement uses fallback metrics"
        )
        if strict:
            raise ValueError(message)
        if font_family is not None:
            warnings.warn(message, FontMetricsWarning, stacklevel=2)
    fitter = TextFitter(_LineSource(text), (width, Emu(1)), path)
    lines = fitter._wrap_lines(_LineSource(text), size_pt)
    if lines is None:
        raise ValueError("A word does not fit at size_pt; widen the box or reduce the font size")
    sizes = [_rendered_size(line, size_pt, path)[0] for line in lines]
    leading = max(_rendered_size("Ty", size_pt, path)[1], round(size_pt * line_spacing * 12700))
    return TextMeasurement(
        tuple(lines),
        Emu(max(sizes, default=0)),
        Emu(leading * len(lines)),
        size_pt,
        path,
        path is None,
    )
