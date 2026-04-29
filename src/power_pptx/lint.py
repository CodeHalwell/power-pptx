"""Slide and deck linter — detects layout/typographic issues on generated slides.

Public entry point::

    report = slide.lint()              # SlideLintReport
    report.issues                      # list[LintIssue]
    report.has_errors                  # bool
    report.summary()                   # human-readable string
    report.auto_fix()                  # mutates; returns list of fix descriptions

Issue types shipped in this release:

* ``TextOverflow``   — text content likely exceeds the text-frame bounds.
* ``ShapeCollision`` — two shapes' bounding boxes overlap significantly.
* ``OffSlide``       — a shape extends (partly or wholly) outside the slide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Sequence

from power_pptx.enum.text import MSO_AUTO_SIZE
from power_pptx.util import Emu

if TYPE_CHECKING:
    from power_pptx.shapes.base import BaseShape
    from power_pptx.slide import Slide
    from power_pptx.util import Length


class LintSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class LintIssue:
    """A single linting issue detected on a slide."""

    severity: LintSeverity
    code: str
    message: str
    shapes: tuple[BaseShape, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        return f"[{self.severity.value.upper()}] {self.code}: {self.message}"


@dataclass
class TextOverflow(LintIssue):
    """Estimated text content exceeds the text frame's visible area."""

    ratio: float = 1.0

    def __init__(self, shape: BaseShape, ratio: float):
        super().__init__(
            severity=LintSeverity.ERROR,
            code="TextOverflow",
            message=(
                f"Shape '{shape.name}': estimated text height is {ratio:.1f}× "
                f"the text frame height."
            ),
            shapes=(shape,),
        )
        self.ratio = ratio


@dataclass
class OffSlide(LintIssue):
    """Shape extends beyond the slide boundary."""

    side: str = ""

    def __init__(self, shape: BaseShape, side: str):
        super().__init__(
            severity=LintSeverity.ERROR,
            code="OffSlide",
            message=f"Shape '{shape.name}' extends beyond the {side} edge of the slide.",
            shapes=(shape,),
        )
        self.side = side


@dataclass
class ShapeCollision(LintIssue):
    """Two shapes' bounding boxes overlap."""

    intersection_area: int = 0
    intersection_pct: float = 0.0

    def __init__(
        self,
        shape_a: BaseShape,
        shape_b: BaseShape,
        intersection_area: int,
        intersection_pct: float,
    ):
        super().__init__(
            severity=LintSeverity.WARNING,
            code="ShapeCollision",
            message=(
                f"Shapes '{shape_a.name}' and '{shape_b.name}' overlap "
                f"({intersection_pct:.0%} of the smaller shape's area)."
            ),
            shapes=(shape_a, shape_b),
        )
        self.intersection_area = intersection_area
        self.intersection_pct = intersection_pct


class SlideLintReport:
    """Lint report for a single slide.

    Returned by :meth:`Slide.lint()`.  Provides a list of issues, a boolean
    ``has_errors`` flag, a human-readable ``summary()``, and an ``auto_fix()``
    mutator for the fixable subset.
    """

    def __init__(self, slide: Slide, issues: list[LintIssue]):
        self._slide = slide
        self._issues = issues

    @property
    def issues(self) -> list[LintIssue]:
        """All detected issues, ordered: errors first, then warnings, then info."""
        return self._issues

    @property
    def has_errors(self) -> bool:
        """True when at least one ERROR-severity issue is present."""
        return any(i.severity == LintSeverity.ERROR for i in self._issues)

    def summary(self) -> str:
        """Return a human-readable string summarising the issues found."""
        if not self._issues:
            return "No issues found."
        lines = [f"{len(self._issues)} issue(s) found:"]
        for issue in self._issues:
            lines.append(f"  {issue}")
        return "\n".join(lines)

    def auto_fix(self, *, dry_run: bool = False) -> list[str]:
        """Apply automatic fixes for issues that can be resolved without designer judgment.

        Returns a list of human-readable descriptions of the fixes applied (or
        that *would* be applied if *dry_run* is True).

        Currently auto-fixable:

        * ``OffSlide`` — nudges the shape so it sits inside the slide bounds.

        Not auto-fixable:

        * ``ShapeCollision`` — nudging shapes apart almost always breaks intent.
        * ``TextOverflow`` — requires designer judgment on font size / content.
        """
        fixes: list[str] = []
        slide_w, slide_h = _slide_dimensions(self._slide)

        for issue in list(self._issues):
            if not isinstance(issue, OffSlide):
                continue
            shape = issue.shapes[0]
            left, top, width, height = shape.left, shape.top, shape.width, shape.height
            new_left, new_top = left, top

            if left < 0:
                new_left = Emu(0)
            if top < 0:
                new_top = Emu(0)
            if slide_w is not None and (left + width) > slide_w:
                new_left = Emu(max(0, int(slide_w) - int(width)))
            if slide_h is not None and (top + height) > slide_h:
                new_top = Emu(max(0, int(slide_h) - int(height)))

            if new_left != left or new_top != top:
                desc = f"Nudged '{shape.name}' from ({left},{top}) to ({new_left},{new_top})."
                fixes.append(desc)
                if not dry_run:
                    shape.left = new_left
                    shape.top = new_top

        return fixes


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DEFAULT_SLIDE_W = Emu(9144000)  # 10 inches in EMU (standard widescreen)
_DEFAULT_SLIDE_H = Emu(6858000)  # 7.5 inches in EMU


def _slide_dimensions(slide: Slide) -> tuple[Length | None, Length | None]:
    """Return (width, height) of the slide in EMU, falling back to widescreen defaults."""
    try:
        prs = slide.part.package.presentation_part.presentation
        return prs.slide_width or _DEFAULT_SLIDE_W, prs.slide_height or _DEFAULT_SLIDE_H
    except Exception:
        return _DEFAULT_SLIDE_W, _DEFAULT_SLIDE_H


def _shape_bbox(shape: BaseShape) -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) in EMU for the shape's bounding box.

    Returns (0, 0, 0, 0) when position/size information is not available.
    """
    try:
        left = int(shape.left or 0)
        top = int(shape.top or 0)
        width = int(shape.width or 0)
        height = int(shape.height or 0)
        return left, top, left + width, top + height
    except Exception:
        return 0, 0, 0, 0


def _check_off_slide(
    shape: BaseShape, slide_w: Length, slide_h: Length
) -> list[LintIssue]:
    """Return OffSlide issues for *shape* if it exceeds the slide boundary."""
    issues: list[LintIssue] = []
    left, top, right, bottom = _shape_bbox(shape)
    sw, sh = int(slide_w), int(slide_h)

    if left < 0:
        issues.append(OffSlide(shape, "left"))
    if top < 0:
        issues.append(OffSlide(shape, "top"))
    if right > sw:
        issues.append(OffSlide(shape, "right"))
    if bottom > sh:
        issues.append(OffSlide(shape, "bottom"))
    return issues


def _check_text_overflow(shape: BaseShape) -> list[LintIssue]:
    """Return TextOverflow issues for *shape* using a simple line-count heuristic.

    Skips shapes with auto-size enabled or when no text frame is present.
    The heuristic estimates the number of lines the text would require
    (assuming ~60 characters per line at the default font size) and compares
    that to the number of lines that fit in the text-frame height.
    """
    issues: list[LintIssue] = []
    if not shape.has_text_frame:
        return issues

    tf = shape.text_frame  # type: ignore[attr-defined]
    # Skip when the shape auto-sizes (no overflow possible by definition)
    if tf.auto_size in (MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT, MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE):
        return issues

    text = tf.text.strip()
    if not text:
        return issues

    # Rough per-run font-size estimate: fall back to 18pt (914400 EMU/pt = 12700)
    _PT_TO_EMU = 12700
    _DEFAULT_FONT_PT = 18
    try:
        first_run = tf.paragraphs[0].runs[0]
        font_pt = (first_run.font.size or (_DEFAULT_FONT_PT * _PT_TO_EMU)) / _PT_TO_EMU
    except (IndexError, AttributeError):
        font_pt = _DEFAULT_FONT_PT

    # Estimate shape inner width/height in EMU, accounting for text-frame margins.
    try:
        frame_w = int(shape.width or 0) - int(tf.margin_left or 0) - int(tf.margin_right or 0)
        frame_h = int(shape.height or 0) - int(tf.margin_top or 0) - int(tf.margin_bottom or 0)
    except Exception:
        return issues

    if frame_w <= 0 or frame_h <= 0:
        return issues

    # Approximate character width at the given pt size (very rough: 0.55 × pt)
    char_w_emu = font_pt * 0.55 * _PT_TO_EMU
    # Line height ~ 1.2 × font size
    line_h_emu = font_pt * 1.2 * _PT_TO_EMU

    chars_per_line = max(1, frame_w / char_w_emu)
    lines_available = max(1, frame_h / line_h_emu)
    estimated_lines = sum(max(1.0, len(line) / chars_per_line) for line in text.split("\n"))

    if estimated_lines > lines_available:
        ratio = estimated_lines / lines_available
        issues.append(TextOverflow(shape, ratio))

    return issues


# Minimum overlap fraction to report a collision (avoids noise from barely
# touching shapes)
_COLLISION_THRESHOLD = 0.05

# Custom namespace for shape metadata that the linter consults but PowerPoint
# ignores. Stored as an attribute on the shape's ``p:cNvPr`` element; lxml
# round-trips unknown namespaces through save/load.
_LINT_NS = "https://power-pptx.io/lint/2024"
_LINT_GROUP_ATTR = "{%s}group" % _LINT_NS


def _shape_lint_group(shape: BaseShape) -> str | None:
    """Return the ``lint_group`` tag for *shape*, or ``None`` if untagged."""
    try:
        cNvPr = shape._element._nvXxPr.cNvPr  # pyright: ignore[reportPrivateUsage]
    except AttributeError:
        return None
    return cNvPr.get(_LINT_GROUP_ATTR)


def _check_collisions(
    shapes: Sequence[BaseShape],
) -> list[LintIssue]:
    """Return ShapeCollision issues for pairs of overlapping shapes.

    Shapes sharing a non-empty ``lint_group`` are treated as intentionally
    layered and never produce a collision warning. Shapes with no group, or
    shapes in different groups, continue to warn on overlap.
    """
    issues: list[LintIssue] = []
    bboxes = [_shape_bbox(s) for s in shapes]
    groups = [_shape_lint_group(s) for s in shapes]

    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            # Suppress collisions inside a designer-tagged group.
            gi, gj = groups[i], groups[j]
            if gi is not None and gi == gj:
                continue

            al, at, ar, ab = bboxes[i]
            bl, bt, br, bb = bboxes[j]

            ix_l = max(al, bl)
            ix_t = max(at, bt)
            ix_r = min(ar, br)
            ix_b = min(ab, bb)

            if ix_r <= ix_l or ix_b <= ix_t:
                continue

            area = (ix_r - ix_l) * (ix_b - ix_t)
            area_a = max(1, (ar - al) * (ab - at))
            area_b = max(1, (br - bl) * (bb - bt))
            pct = area / min(area_a, area_b)

            if pct >= _COLLISION_THRESHOLD:
                issues.append(
                    ShapeCollision(
                        shapes[i],
                        shapes[j],
                        intersection_area=area,
                        intersection_pct=pct,
                    )
                )

    return issues


def lint_slide(slide: Slide) -> SlideLintReport:
    """Inspect *slide* for geometric and typographic issues.

    Returns a :class:`SlideLintReport` with the detected issues.
    """
    slide_w, slide_h = _slide_dimensions(slide)
    issues: list[LintIssue] = []
    shapes = list(slide.shapes)

    for shape in shapes:
        if slide_w is not None and slide_h is not None:
            issues.extend(_check_off_slide(shape, slide_w, slide_h))
        issues.extend(_check_text_overflow(shape))

    issues.extend(_check_collisions(shapes))

    # Sort: errors → warnings → info
    _order = {LintSeverity.ERROR: 0, LintSeverity.WARNING: 1, LintSeverity.INFO: 2}
    issues.sort(key=lambda x: _order[x.severity])

    return SlideLintReport(slide, issues)
