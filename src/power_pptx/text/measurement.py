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
    letter_spacing: Length | int = 0,
    weight: int | str | None = None,
) -> TextMeasurement:
    """Measure wrapped text with the same font metrics as ``fit_text``.

    Raises when a whole word cannot fit at the requested size. No slide or
    text frame is changed. Explicit line breaks and empty lines are preserved.
    ``strict`` requires real metrics; otherwise ``used_fallback`` identifies
    estimates, and a missing explicitly requested family emits a warning.
    ``letter_spacing`` (a length such as ``Pt(1.4)``) is added after every
    character. ``weight`` (``"medium"``, ``600``, …) selects that exact face.
    """
    if width <= 0 or isinstance(size_pt, bool) or not isinstance(size_pt, int) or size_pt < 1:
        raise ValueError("width and integer size_pt must be positive")
    if not math.isfinite(line_spacing) or line_spacing <= 0:
        raise ValueError("line_spacing must be finite and positive")
    if not math.isfinite(letter_spacing):
        raise ValueError("letter_spacing must be finite")
    path = font_file or find_font_file(font_family or "Calibri", bold, italic, weight=weight)
    if path is None:
        message = (
            f"Font {font_family or 'Calibri'!r} is unavailable; measurement uses fallback metrics"
        )
        if strict:
            raise ValueError(message)
        if font_family is not None:
            warnings.warn(message, FontMetricsWarning, stacklevel=2)
    fitter = TextFitter(_LineSource(text), (width, Emu(1)), path, letter_spacing)
    lines = fitter._wrap_lines(_LineSource(text), size_pt)
    if lines is None:
        raise ValueError("A word does not fit at size_pt; widen the box or reduce the font size")
    sizes = [fitter._line_width(line, size_pt) for line in lines]
    leading = max(_rendered_size("Ty", size_pt, path)[1], round(size_pt * line_spacing * 12700))
    return TextMeasurement(
        tuple(lines),
        Emu(max(sizes, default=0)),
        Emu(leading * len(lines)),
        size_pt,
        path,
        path is None,
    )


def truncate_text(
    text: str,
    width: Length,
    *,
    max_lines: int = 1,
    size_pt: int = 18,
    font_family: str | None = None,
    font_file: str | None = None,
    bold: bool = False,
    italic: bool = False,
    letter_spacing: Length | int = 0,
    ellipsis: str = "…",
    strict: bool = False,
) -> str:
    """Return `text` shortened with `ellipsis` so it wraps to at most `max_lines`.

    Text that already fits is returned unchanged. Cutting prefers the last
    whole word that fits; a single over-long word is cut mid-word. Uses the
    same metrics as :func:`measure_text`, including its handling of missing
    fonts: ``strict`` raises, and a named family that isn't available warns.
    Returns `ellipsis` alone (or an empty string) when not even that fits.
    """
    if isinstance(max_lines, bool) or not isinstance(max_lines, int) or max_lines < 1:
        raise ValueError("max_lines must be a positive integer")
    if width <= 0 or isinstance(size_pt, bool) or not isinstance(size_pt, int) or size_pt < 1:
        raise ValueError("width and integer size_pt must be positive")
    path = font_file or find_font_file(font_family or "Calibri", bold, italic)
    if path is None:
        message = (
            f"Font {font_family or 'Calibri'!r} is unavailable; truncation uses fallback metrics"
        )
        if strict:
            raise ValueError(message)
        if font_family is not None:
            warnings.warn(message, FontMetricsWarning, stacklevel=2)
    fitter = TextFitter(_LineSource(text), (width, Emu(1)), path, letter_spacing)

    def fits(candidate):
        lines = fitter._wrap_lines(_LineSource(candidate), size_pt)
        if lines is None:
            return False
        return len(lines) <= max_lines and all(
            fitter._line_width(line, size_pt) <= width for line in lines
        )

    if fits(text):
        return text
    # Binary search the longest prefix that still fits once the ellipsis is added.
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if fits(text[:middle].rstrip() + ellipsis):
            low = middle
        else:
            high = middle - 1
    prefix = text[:low].rstrip()
    word_end = prefix.rfind(" ")
    if word_end > 0 and low < len(text) and not text[low].isspace():
        # Prefer ending on a whole word when the cut fell inside one.
        prefix = prefix[:word_end].rstrip()
    candidate = prefix + ellipsis
    if fits(candidate):
        return candidate
    return ellipsis if fits(ellipsis) else ""
