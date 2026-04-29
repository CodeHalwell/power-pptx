"""Slide and deck linter — detects layout/typographic issues on generated slides.

Public entry point::

    report = slide.lint()              # SlideLintReport
    report.issues                      # list[LintIssue]
    report.has_errors                  # bool
    report.summary()                   # human-readable string
    report.auto_fix()                  # mutates; returns list of fix descriptions

Issue types:

* ``TextOverflow``             — text likely exceeds the text-frame bounds.
* ``ShapeCollision``           — two shapes' bounding boxes overlap.
* ``OffSlide``                 — a shape extends outside the slide.
* ``MinFontSize``              — a text run is below the legibility threshold.
* ``OffGridDrift``             — shape is slightly off a column/row grid that
  several siblings hit cleanly.
* ``LowContrast``              — text/background contrast is below WCAG AA.
* ``ZOrderAnomaly``            — a filled card-shaped backdrop is drawn above
  shapes it visually contains.
* ``MasterPlaceholderCollision`` — a shape sits exactly on a placeholder it
  should likely have inherited from the layout.
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


@dataclass
class MinFontSize(LintIssue):
    """A text run uses a font size below the configured legibility threshold."""

    pt: float = 0.0
    threshold_pt: float = 9.0

    def __init__(self, shape: BaseShape, pt: float, threshold_pt: float):
        super().__init__(
            severity=LintSeverity.WARNING,
            code="MinFontSize",
            message=(
                f"Shape '{shape.name}': run at {pt:.1f}pt is below the "
                f"{threshold_pt:.0f}pt legibility threshold."
            ),
            shapes=(shape,),
        )
        self.pt = pt
        self.threshold_pt = threshold_pt


@dataclass
class OffGridDrift(LintIssue):
    """Shape sits slightly off a column/row grid that other shapes hit cleanly."""

    axis: str = ""
    drift_emu: int = 0
    grid_emu: int = 0

    def __init__(self, shape: BaseShape, axis: str, drift_emu: int, grid_emu: int):
        drift_in = drift_emu / 914400.0
        super().__init__(
            severity=LintSeverity.WARNING,
            code="OffGridDrift",
            message=(
                f"Shape '{shape.name}': {axis} edge is {drift_in:.3f}\" "
                f"off the dominant grid line at {grid_emu / 914400.0:.3f}\"."
            ),
            shapes=(shape,),
        )
        self.axis = axis
        self.drift_emu = drift_emu
        self.grid_emu = grid_emu


@dataclass
class LowContrast(LintIssue):
    """Text/background contrast ratio is below the WCAG AA threshold."""

    ratio: float = 0.0
    threshold: float = 4.5

    def __init__(self, shape: BaseShape, ratio: float, threshold: float = 4.5):
        super().__init__(
            severity=LintSeverity.WARNING,
            code="LowContrast",
            message=(
                f"Shape '{shape.name}': text-on-fill contrast ratio "
                f"{ratio:.2f}:1 is below WCAG AA threshold ({threshold:.1f}:1)."
            ),
            shapes=(shape,),
        )
        self.ratio = ratio
        self.threshold = threshold


@dataclass
class ZOrderAnomaly(LintIssue):
    """A filled shape is drawn above a shape it visually contains."""

    def __init__(self, container: BaseShape, contained: BaseShape):
        super().__init__(
            severity=LintSeverity.WARNING,
            code="ZOrderAnomaly",
            message=(
                f"Shape '{container.name}' (filled) is drawn above "
                f"'{contained.name}' that it visually contains; "
                f"'{contained.name}' will be hidden."
            ),
            shapes=(container, contained),
        )


@dataclass
class MasterPlaceholderCollision(LintIssue):
    """A non-placeholder shape sits at exactly the position of a layout placeholder."""

    placeholder_idx: int = 0

    def __init__(self, shape: BaseShape, placeholder_idx: int):
        super().__init__(
            severity=LintSeverity.WARNING,
            code="MasterPlaceholderCollision",
            message=(
                f"Shape '{shape.name}' sits at the position of layout "
                f"placeholder idx={placeholder_idx}; it likely should have "
                f"inherited from the placeholder instead of redrawing it."
            ),
            shapes=(shape,),
        )
        self.placeholder_idx = placeholder_idx


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

        * ``OffSlide``     — nudges the shape so it sits inside the slide bounds.
        * ``OffGridDrift`` — snaps the shape's drifted edge onto the dominant
          grid line (Tier 3 of the auto-fix tier list).

        Not auto-fixable:

        * ``ShapeCollision`` — nudging shapes apart almost always breaks intent;
          tag intentional overlaps with ``shape.lint_group`` to suppress.
        * ``TextOverflow`` — requires designer judgment on font size / content.
        * ``LowContrast``, ``MinFontSize``, ``ZOrderAnomaly``,
          ``MasterPlaceholderCollision`` — require designer judgment.
        """
        fixes: list[str] = []
        slide_w, slide_h = _slide_dimensions(self._slide)

        for issue in list(self._issues):
            if isinstance(issue, OffSlide):
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
                    desc = (
                        f"Nudged '{shape.name}' from ({left},{top}) to "
                        f"({new_left},{new_top})."
                    )
                    fixes.append(desc)
                    if not dry_run:
                        shape.left = new_left
                        shape.top = new_top

            elif isinstance(issue, OffGridDrift):
                shape = issue.shapes[0]
                if issue.axis == "left":
                    old, new = int(shape.left), issue.grid_emu
                    desc = (
                        f"Snapped '{shape.name}' left edge from {old} to "
                        f"{new} EMU (grid)."
                    )
                    fixes.append(desc)
                    if not dry_run:
                        shape.left = Emu(new)
                elif issue.axis == "top":
                    old, new = int(shape.top), issue.grid_emu
                    desc = (
                        f"Snapped '{shape.name}' top edge from {old} to "
                        f"{new} EMU (grid)."
                    )
                    fixes.append(desc)
                    if not dry_run:
                        shape.top = Emu(new)

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

# Namespace for power-pptx metadata round-tripped through the deck. The
# metadata is stored as a child element under ``cNvPr/extLst/ext``, the
# OOXML-sanctioned extension mechanism — using a custom-namespaced
# *attribute* on ``cNvPr`` (as the previous implementation did) violates
# the CT_NonVisualDrawingProps schema, which has no ``xsd:anyAttribute``,
# and triggers PowerPoint's "Repaired and removed" prompt on open.
_LINT_NS = "https://power-pptx.io/lint/2024"

# Stable GUID identifying the lint-metadata ``<a:ext>`` block. Once
# published it must not change — PowerPoint preserves the element verbatim
# as long as it doesn't recognise the URI.
_LINT_EXT_URI = "{B7AB0FE6-95E5-4FB6-B41F-2C8B9F4D3A21}"

_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_A_EXTLST = "{%s}extLst" % _A_NS
_A_EXT = "{%s}ext" % _A_NS
_PP_LINTGROUP = "{%s}lintGroup" % _LINT_NS

# Pre-2.1.1 layout stored the value as a custom-namespaced attribute
# directly on ``cNvPr``. Read-only fallback so decks saved with the old
# release continue to round-trip after upgrade.
_LEGACY_LINT_GROUP_ATTR = "{%s}group" % _LINT_NS

# Backwards-compatible alias for the public-but-underscored name some
# external code (and our own tests) imported. Reads still work via the
# fallback path; new writes go through the helpers below.
_LINT_GROUP_ATTR = _LEGACY_LINT_GROUP_ATTR


def _find_lint_ext(cNvPr):
    """Return the ``<a:ext uri=...>`` element holding lint metadata, or None."""
    extLst = cNvPr.find(_A_EXTLST)
    if extLst is None:
        return None
    for ext in extLst.findall(_A_EXT):
        if ext.get("uri") == _LINT_EXT_URI:
            return ext
    return None


def _read_lint_group(cNvPr) -> str | None:
    """Return the ``lint_group`` value stored on *cNvPr*, or ``None``."""
    ext = _find_lint_ext(cNvPr)
    if ext is not None:
        node = ext.find(_PP_LINTGROUP)
        if node is not None:
            name = node.get("name")
            if name:
                return name
    # Fallback: legacy attribute layout from pre-2.1.1.
    legacy = cNvPr.get(_LEGACY_LINT_GROUP_ATTR)
    return legacy if legacy else None


def _write_lint_group(cNvPr, value: str) -> None:
    """Store ``lint_group = value`` on *cNvPr* using ``a:extLst/a:ext``."""
    from lxml import etree

    # Drop any legacy-format attribute so the new format is canonical.
    if _LEGACY_LINT_GROUP_ATTR in cNvPr.attrib:
        del cNvPr.attrib[_LEGACY_LINT_GROUP_ATTR]

    extLst = cNvPr.find(_A_EXTLST)
    if extLst is None:
        # ``a:extLst`` is the last allowed child of cNvPr per the schema
        # (after a:hlinkClick / a:hlinkHover); appending is safe because
        # python-pptx removes any element it doesn't recognise on read.
        extLst = etree.SubElement(cNvPr, _A_EXTLST)

    ext = _find_lint_ext(cNvPr)
    if ext is None:
        ext = etree.SubElement(extLst, _A_EXT)
        ext.set("uri", _LINT_EXT_URI)

    node = ext.find(_PP_LINTGROUP)
    if node is None:
        node = etree.SubElement(ext, _PP_LINTGROUP)
    node.set("name", value)


def _clear_lint_group(cNvPr) -> None:
    """Remove any lint-group metadata from *cNvPr* (both new and legacy)."""
    if _LEGACY_LINT_GROUP_ATTR in cNvPr.attrib:
        del cNvPr.attrib[_LEGACY_LINT_GROUP_ATTR]
    extLst = cNvPr.find(_A_EXTLST)
    if extLst is None:
        return
    for ext in list(extLst.findall(_A_EXT)):
        if ext.get("uri") == _LINT_EXT_URI:
            extLst.remove(ext)
    # If we just emptied extLst, drop it too — an empty <a:extLst/> is
    # legal but pointless and confuses round-trip diff tests.
    if len(extLst) == 0:
        cNvPr.remove(extLst)


def _shape_lint_group(shape: BaseShape) -> str | None:
    """Return the ``lint_group`` tag for *shape*, or ``None`` if untagged."""
    try:
        cNvPr = shape._element._nvXxPr.cNvPr  # pyright: ignore[reportPrivateUsage]
    except AttributeError:
        return None
    return _read_lint_group(cNvPr)


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


# ---------------------------------------------------------------------------
# Min font size — flag any run below the legibility threshold (default 9pt).
# ---------------------------------------------------------------------------

_DEFAULT_MIN_FONT_PT = 9.0
_PT_TO_EMU = 12700


def _check_min_font_size(
    shape: BaseShape, threshold_pt: float = _DEFAULT_MIN_FONT_PT
) -> list[LintIssue]:
    """Return a single MinFontSize issue if any run is below *threshold_pt*."""
    issues: list[LintIssue] = []
    if not shape.has_text_frame:
        return issues
    tf = shape.text_frame  # type: ignore[attr-defined]
    smallest: float | None = None
    for paragraph in tf.paragraphs:
        for run in paragraph.runs:
            try:
                size = run.font.size
            except (AttributeError, ValueError):
                continue
            if size is None:
                continue
            pt = float(size) / _PT_TO_EMU
            if pt > 0 and (smallest is None or pt < smallest):
                smallest = pt
    if smallest is not None and smallest < threshold_pt:
        issues.append(MinFontSize(shape, smallest, threshold_pt))
    return issues


# ---------------------------------------------------------------------------
# Off-grid drift — find shapes whose edge is slightly off a grid line that
# at least three siblings hit cleanly.
# ---------------------------------------------------------------------------

# A shape is "on" a grid line if it's within this much of the cluster center
# (1/100"). Anything further is potential drift.
_GRID_TIGHT_TOLERANCE_EMU = 9144  # ~0.01"
# Drift candidates must be within this much of a cluster (else they're just
# unrelated edges).
_GRID_LOOSE_TOLERANCE_EMU = 91440  # ~0.10"
# A grid line needs at least this many shapes on it before we trust it.
_GRID_MIN_CLUSTER = 3


def _cluster_edges(values: list[int], tol: int) -> list[tuple[int, int]]:
    """Return list of (cluster_center_emu, member_count) for clusters of values
    that lie within *tol* of each other.

    Greedy single-pass clustering; values are sorted, then any gap larger
    than *tol* breaks the cluster.
    """
    if not values:
        return []
    sorted_v = sorted(values)
    clusters: list[list[int]] = [[sorted_v[0]]]
    for v in sorted_v[1:]:
        if v - clusters[-1][-1] <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    # ``+ 0.5`` is round-half-up for the always-non-negative cluster centers;
    # behaves identically to ``round()`` here but avoids any banker's-rounding
    # edge case at exact half-EMU boundaries.
    return [(int(sum(c) / len(c) + 0.5), len(c)) for c in clusters]


def _check_off_grid_drift(shapes: Sequence[BaseShape]) -> list[LintIssue]:
    """Return OffGridDrift issues for shapes whose edges are slightly off a grid."""
    issues: list[LintIssue] = []
    if len(shapes) < _GRID_MIN_CLUSTER + 1:
        return issues

    bboxes = [_shape_bbox(s) for s in shapes]

    for axis_name, edge_idx in (("left", 0), ("top", 1)):
        edges = [b[edge_idx] for b in bboxes]
        clusters = _cluster_edges(edges, _GRID_TIGHT_TOLERANCE_EMU)
        # Only clusters with enough members are "grid lines".
        grid_lines = [center for center, n in clusters if n >= _GRID_MIN_CLUSTER]
        if not grid_lines:
            continue
        for shape, edge in zip(shapes, edges):
            # Skip shapes that already sit on a grid line.
            on_grid = any(
                abs(edge - g) <= _GRID_TIGHT_TOLERANCE_EMU for g in grid_lines
            )
            if on_grid:
                continue
            # Find the closest grid line; if it's within the loose tolerance,
            # this is drift.
            closest = min(grid_lines, key=lambda g: abs(edge - g))
            drift = abs(edge - closest)
            if (
                _GRID_TIGHT_TOLERANCE_EMU < drift <= _GRID_LOOSE_TOLERANCE_EMU
            ):
                issues.append(OffGridDrift(shape, axis_name, drift, closest))
    return issues


# ---------------------------------------------------------------------------
# Low contrast — compare text RGB against shape fill RGB (or, if absent,
# slide background RGB) and warn when the ratio is below WCAG AA (4.5:1).
# Skips silently when colors can't be resolved (theme color, gradient, etc.).
# ---------------------------------------------------------------------------

_CONTRAST_THRESHOLD = 4.5


def _relative_luminance(rgb) -> float:
    """Return WCAG relative luminance of an ``RGBColor``."""
    r, g, b = (int(rgb[0]) / 255.0, int(rgb[1]) / 255.0, int(rgb[2]) / 255.0)

    def _ch(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _ch(r) + 0.7152 * _ch(g) + 0.0722 * _ch(b)


def _contrast_ratio(rgb_a, rgb_b) -> float:
    """Return WCAG contrast ratio between two ``RGBColor`` values."""
    la = _relative_luminance(rgb_a)
    lb = _relative_luminance(rgb_b)
    light, dark = (la, lb) if la >= lb else (lb, la)
    return (light + 0.05) / (dark + 0.05)


def _resolve_solid_rgb(fill):
    """Return RGB of *fill* if it's an explicit solid RGB; ``None`` otherwise.

    We deliberately don't resolve theme colors or gradients here — getting
    that right requires walking the theme + clrMap. Skipping silently keeps
    the lint check noise-free.
    """
    if fill is None:
        return None
    try:
        from power_pptx.enum.dml import MSO_FILL_TYPE

        if fill.type != MSO_FILL_TYPE.SOLID:
            return None
        return fill.fore_color.rgb
    except Exception:
        return None


def _slide_background_rgb(slide: Slide):
    """Best-effort RGB extraction from the slide's explicit background fill.

    Returns ``None`` if the background inherits from the master/layout or is
    not a solid RGB color.
    """
    try:
        bg = slide._element.bg  # pyright: ignore[reportPrivateUsage]
        if bg is None:
            return None
        # Read the existing ``<p:bgPr>`` non-destructively. ``get_or_add_bgPr``
        # would mutate the slide (drop a ``<p:bgRef>`` style reference and
        # synthesize a noFill ``<p:bgPr>``), and ``slide.lint()`` must never
        # mutate slide XML.
        bgPr = bg.bgPr
        if bgPr is None:
            return None
        from power_pptx.dml.fill import FillFormat

        return _resolve_solid_rgb(FillFormat.from_fill_parent(bgPr))
    except Exception:
        return None


def _check_low_contrast(shape: BaseShape, slide: Slide) -> list[LintIssue]:
    """Return a LowContrast issue if shape's text has poor contrast against its fill."""
    issues: list[LintIssue] = []
    if not shape.has_text_frame:
        return issues
    tf = shape.text_frame  # type: ignore[attr-defined]
    if not tf.text.strip():
        return issues

    # Pick the first run's font color (best-effort).
    text_rgb = None
    try:
        for paragraph in tf.paragraphs:
            for run in paragraph.runs:
                try:
                    rgb = run.font.color.rgb
                except (AttributeError, ValueError):
                    rgb = None
                if rgb is not None:
                    text_rgb = rgb
                    break
            if text_rgb is not None:
                break
    except Exception:
        return issues
    if text_rgb is None:
        return issues

    # Find a background to compare against: prefer shape fill, then slide bg.
    bg_rgb = None
    try:
        bg_rgb = _resolve_solid_rgb(shape.fill)  # type: ignore[attr-defined]
    except Exception:
        pass
    if bg_rgb is None:
        bg_rgb = _slide_background_rgb(slide)
    if bg_rgb is None:
        return issues

    ratio = _contrast_ratio(text_rgb, bg_rgb)
    if ratio < _CONTRAST_THRESHOLD:
        issues.append(LowContrast(shape, ratio, _CONTRAST_THRESHOLD))
    return issues


# ---------------------------------------------------------------------------
# Z-order anomaly — a filled shape A is drawn above shape B that A visually
# contains. A's fill would hide B at render time.
# ---------------------------------------------------------------------------


def _bbox_contains(outer: tuple[int, int, int, int], inner: tuple[int, int, int, int]) -> bool:
    """True if *inner* sits fully inside *outer* (with a small tolerance)."""
    tol = 2  # EMU; tolerance for floating-point round trips
    return (
        outer[0] - tol <= inner[0]
        and outer[1] - tol <= inner[1]
        and outer[2] + tol >= inner[2]
        and outer[3] + tol >= inner[3]
        and (inner[2] - inner[0]) > 0
        and (inner[3] - inner[1]) > 0
    )


def _shape_has_opaque_fill(shape: BaseShape) -> bool:
    """Return ``True`` if *shape* has an opaque (solid) fill."""
    try:
        from power_pptx.enum.dml import MSO_FILL_TYPE

        return shape.fill.type == MSO_FILL_TYPE.SOLID  # type: ignore[attr-defined]
    except Exception:
        return False


def _check_z_order_anomalies(shapes: Sequence[BaseShape]) -> list[LintIssue]:
    """Find filled shapes drawn above shapes they visually contain."""
    issues: list[LintIssue] = []
    bboxes = [_shape_bbox(s) for s in shapes]
    # Document order = draw order; later shapes are drawn on top.
    for j in range(len(shapes)):
        # j is the candidate "container" drawn above earlier shapes
        if not _shape_has_opaque_fill(shapes[j]):
            continue
        for i in range(j):
            if not _bbox_contains(bboxes[j], bboxes[i]):
                continue
            # Tolerate identical bboxes — those are layered groups, not
            # anomalies; the drift case is when j strictly contains i.
            if bboxes[j] == bboxes[i]:
                continue
            issues.append(ZOrderAnomaly(container=shapes[j], contained=shapes[i]))
    return issues


# ---------------------------------------------------------------------------
# Master-placeholder collision — a non-placeholder shape whose bbox closely
# matches a layout placeholder. Caller likely meant to populate the
# placeholder rather than redraw it.
# ---------------------------------------------------------------------------

# Tolerance for deciding "same position" — 1/20".
_PH_POS_TOLERANCE_EMU = 45720


def _placeholder_bboxes(slide: Slide) -> list[tuple[int, int, int, int, int]]:
    """Return (left, top, right, bottom, idx) for each layout placeholder.

    Only inheritable placeholders that the slide doesn't already use are
    returned.
    """
    out: list[tuple[int, int, int, int, int]] = []
    try:
        layout = slide.slide_layout
    except Exception:
        return out
    used_idxs: set[int] = set()
    try:
        for ph in slide.placeholders:
            used_idxs.add(int(ph.placeholder_format.idx))
    except Exception:
        pass
    try:
        for ph in layout.placeholders:
            try:
                idx = int(ph.placeholder_format.idx)
            except Exception:
                continue
            if idx in used_idxs:
                continue
            l, t, r, b = _shape_bbox(ph)
            if r - l <= 0 or b - t <= 0:
                continue
            out.append((l, t, r, b, idx))
    except Exception:
        return out
    return out


def _check_master_placeholder_collision(
    slide: Slide, shapes: Sequence[BaseShape]
) -> list[LintIssue]:
    """Find shapes whose bbox lines up with an unused layout placeholder."""
    issues: list[LintIssue] = []
    ph_bboxes = _placeholder_bboxes(slide)
    if not ph_bboxes:
        return issues
    for shape in shapes:
        if shape.is_placeholder:
            continue
        sl, st, sr, sb = _shape_bbox(shape)
        if sr - sl <= 0 or sb - st <= 0:
            continue
        for pl, pt, pr, pb, idx in ph_bboxes:
            if (
                abs(sl - pl) <= _PH_POS_TOLERANCE_EMU
                and abs(st - pt) <= _PH_POS_TOLERANCE_EMU
                and abs(sr - pr) <= _PH_POS_TOLERANCE_EMU
                and abs(sb - pb) <= _PH_POS_TOLERANCE_EMU
            ):
                issues.append(MasterPlaceholderCollision(shape, idx))
                break
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
        issues.extend(_check_min_font_size(shape))
        issues.extend(_check_low_contrast(shape, slide))

    issues.extend(_check_collisions(shapes))
    issues.extend(_check_off_grid_drift(shapes))
    issues.extend(_check_z_order_anomalies(shapes))
    issues.extend(_check_master_placeholder_collision(slide, shapes))

    # Sort: errors → warnings → info
    _order = {LintSeverity.ERROR: 0, LintSeverity.WARNING: 1, LintSeverity.INFO: 2}
    issues.sort(key=lambda x: _order[x.severity])

    return SlideLintReport(slide, issues)
