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

    def __init__(self, shape: BaseShape, side: str, code: str = "OffSlide"):
        super().__init__(
            severity=LintSeverity.ERROR,
            code=code,
            message=f"Shape '{shape.name}' extends beyond the {side} edge of the slide.",
            shapes=(shape,),
        )
        self.side = side


@dataclass
class OffSlideShadow(OffSlide):
    """Shape's shadow bleed extends beyond the slide boundary.

    Emitted when the raw shape bbox sits inside the slide but
    inflating by the shadow blur radius pushes it past an edge.  Only
    fires when ``slide.lint(include_effect_bleed=True)`` is set.  Use
    ``shape.lint_skip = {"OffSlideShadow"}`` to silence the bleed-only
    variant without silencing real :class:`OffSlide` issues.
    """

    def __init__(self, shape: BaseShape, side: str):
        super().__init__(shape, side, code="OffSlideShadow")
        # The raw bbox stays on-slide; only the shadow bleed crosses
        # the edge, so the inherited "Shape extends beyond …" message
        # would mislead readers.
        self.message = (
            f"Shape '{shape.name}': shadow bleed extends beyond the "
            f"{side} edge of the slide (raw bbox is on-slide)."
        )


@dataclass
class ShapeCollision(LintIssue):
    """Two shapes' bounding boxes overlap.

    The detector tiers each collision into a *kind* and a numeric *score*
    so callers can distinguish layered card-on-panel patterns
    ("incidental", INFO) from genuine duplicate-rectangle bugs
    ("matched", ERROR).  See :func:`_check_collisions` for the heuristic.
    """

    intersection_area: int = 0
    intersection_pct: float = 0.0
    #: ``(group_a, group_b)`` — the ``lint_group`` tag of each shape (or
    #: ``None`` if untagged).  Lets callers triage "intentional overlap I
    #: forgot to tag" (one or both ``None``) vs. "genuine layout bug"
    #: (different non-``None`` tags) at a glance in ``report.summary()``.
    groups: tuple[str | None, str | None] = (None, None)
    #: Likelihood this overlap is a layout bug, in [0.0, 1.0].  Higher is
    #: more suspicious; ``"incidental"`` collisions tend to score low.
    score: float = 0.0
    #: One of ``"incidental"`` (small inside large), ``"partial"``
    #: (similarly-sized partial overlap), or ``"matched"`` (near-identical
    #: bbox — almost certainly a duplicate).
    kind: str = "partial"

    def __init__(
        self,
        shape_a: BaseShape,
        shape_b: BaseShape,
        intersection_area: int,
        intersection_pct: float,
        groups: tuple[str | None, str | None] = (None, None),
        score: float = 0.0,
        kind: str = "partial",
        code: str = "ShapeCollision",
    ):
        severity = _SEVERITY_BY_KIND.get(kind, LintSeverity.WARNING)
        group_suffix = ""
        if groups != (None, None):
            group_suffix = f" [groups: {groups[0]!r} vs {groups[1]!r}]"
        super().__init__(
            severity=severity,
            code=code,
            message=(
                f"Shapes '{shape_a.name}' and '{shape_b.name}' overlap "
                f"({intersection_pct:.0%} of the smaller shape's area) "
                f"[kind={kind}, score={score:.2f}]"
                + group_suffix
            ),
            shapes=(shape_a, shape_b),
        )
        self.intersection_area = intersection_area
        self.intersection_pct = intersection_pct
        self.groups = groups
        self.score = score
        self.kind = kind


_SEVERITY_BY_KIND: dict[str, LintSeverity] = {
    "incidental": LintSeverity.INFO,
    "partial": LintSeverity.WARNING,
    # ``matched`` (near-identical bbox) was originally ERROR, but in
    # practice the overwhelmingly common cause is intentional visual
    # layering — a badge drawn over a number, a button drawn over its
    # label.  Demoting to INFO keeps the signal in the report without
    # flooding ``has_errors`` and CI pipelines with false positives;
    # the ``matched`` kind is preserved on the issue so callers who
    # really want to flag duplicates can filter on it.
    "matched": LintSeverity.INFO,
}


@dataclass
class ShapeCollisionShadow(ShapeCollision):
    """Two shapes' shadow bleed regions overlap.

    Emitted when raw bboxes don't overlap but shadow-inflated bboxes
    do.  Only fires when ``slide.lint(include_effect_bleed=True)`` is
    set.  Suppress with ``shape.lint_skip = {"ShapeCollisionShadow"}``.
    """

    def __init__(
        self,
        shape_a: BaseShape,
        shape_b: BaseShape,
        intersection_area: int,
        intersection_pct: float,
        groups: tuple[str | None, str | None] = (None, None),
        score: float = 0.0,
        kind: str = "partial",
    ):
        super().__init__(
            shape_a,
            shape_b,
            intersection_area=intersection_area,
            intersection_pct=intersection_pct,
            groups=groups,
            score=score,
            kind=kind,
            code="ShapeCollisionShadow",
        )
        # The raw bboxes don't overlap; only the shadow-inflated ones
        # do, so the inherited "Shapes … overlap …" wording from
        # ShapeCollision would mislead readers.
        group_suffix = ""
        if groups != (None, None):
            group_suffix = f" [groups: {groups[0]!r} vs {groups[1]!r}]"
        self.message = (
            f"Shapes '{shape_a.name}' and '{shape_b.name}': shadow bleed "
            f"regions overlap ({intersection_pct:.0%} of the smaller "
            f"shape's area), though the raw bboxes do not "
            f"[kind={kind}, score={score:.2f}]"
            + group_suffix
        )


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

    def __init__(
        self,
        slide: Slide,
        issues: list[LintIssue],
        *,
        include_effect_bleed: bool = False,
        disable: Sequence[str] = (),
        min_severity: LintSeverity = LintSeverity.INFO,
    ):
        self._slide = slide
        self._issues = issues
        # Remember the mode the report was generated under so
        # ``auto_fix()``'s post-fix refresh stays consistent — refreshing
        # under default kwargs would otherwise drop bleed-only issues
        # from a bleed-enabled report or surface issues the caller had
        # asked to disable.
        self._include_effect_bleed = include_effect_bleed
        self._disable = tuple(disable)
        self._min_severity = min_severity

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
        that *would* be applied if *dry_run* is True).  After a non-dry-run
        call, :attr:`issues` is refreshed to reflect the post-fix state — so
        the residual punch list is just ``report.issues`` rather than a
        second ``slide.lint()`` call.

        Currently auto-fixable:

        * ``OffSlide``     — clamps the shape on-slide.  Shrinks the
          width / height first when the shape is larger than the slide
          (translation alone can't fix that), then nudges position
          inside the bounds.  Each shape is clamped at most once even
          when it triggered multiple OffSlide issues (e.g. left + right).
        * ``OffGridDrift`` — snaps the shape's drifted edge onto the dominant
          grid line (Tier 3 of the auto-fix tier list).
        * ``TextOverflow`` — flips the offending text frame's auto-size
          setting to ``MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE`` so PowerPoint
          shrinks the runs at render time.  This is a non-destructive
          fix: the text content is preserved verbatim, only the
          render-time sizing changes.  Frames that already have a
          non-NONE auto-size are skipped (they should not have linted
          in the first place).

        Not auto-fixable:

        * ``ShapeCollision`` — nudging shapes apart almost always breaks intent;
          tag intentional overlaps with ``shape.lint_group`` to suppress.
        * ``LowContrast``, ``MinFontSize``, ``ZOrderAnomaly``,
          ``MasterPlaceholderCollision`` — require designer judgment.
        """
        fixes: list[str] = []
        slide_w, slide_h = _slide_dimensions(self._slide)

        # Cross-issue de-dup: a single shape can pop several OffSlide
        # issues (left + right, or top + bottom) and the per-issue loop
        # would otherwise fire twice for the same nudge.  Tracking
        # already-clamped shapes by id keeps the fix descriptions and
        # the resulting position consistent.
        clamped: set[int] = set()

        for issue in list(self._issues):
            if isinstance(issue, OffSlide):
                shape = issue.shapes[0]
                shape_key = id(shape._element)  # pyright: ignore[reportPrivateUsage]
                if shape_key in clamped:
                    continue
                left, top, width, height = shape.left, shape.top, shape.width, shape.height
                new_left, new_top = left, top
                new_width, new_height = width, height

                # First clamp size: a shape larger than the slide can
                # never be fully on-slide just by translation, so shrink
                # to fit before deciding where to put it.  This used to
                # be a silent no-op — auto_fix would translate but never
                # converge.
                if slide_w is not None and int(width) > int(slide_w):
                    new_width = Emu(int(slide_w))
                if slide_h is not None and int(height) > int(slide_h):
                    new_height = Emu(int(slide_h))

                if int(left) < 0:
                    new_left = Emu(0)
                if int(top) < 0:
                    new_top = Emu(0)
                if slide_w is not None and (int(new_left) + int(new_width)) > int(slide_w):
                    new_left = Emu(max(0, int(slide_w) - int(new_width)))
                if slide_h is not None and (int(new_top) + int(new_height)) > int(slide_h):
                    new_top = Emu(max(0, int(slide_h) - int(new_height)))

                changed = (
                    new_left != left
                    or new_top != top
                    or new_width != width
                    or new_height != height
                )
                if changed:
                    parts = []
                    if new_left != left or new_top != top:
                        parts.append(
                            f"position ({left},{top}) → ({new_left},{new_top})"
                        )
                    if new_width != width or new_height != height:
                        parts.append(
                            f"size ({width},{height}) → ({new_width},{new_height})"
                        )
                    desc = f"Clamped '{shape.name}' on-slide: " + "; ".join(parts) + "."
                    fixes.append(desc)
                    if not dry_run:
                        shape.left = new_left
                        shape.top = new_top
                        if new_width != width:
                            shape.width = new_width
                        if new_height != height:
                            shape.height = new_height
                    clamped.add(shape_key)

            elif isinstance(issue, TextOverflow):
                shape = issue.shapes[0]
                # Skip silently if the shape no longer has a text frame
                # (defensive — TextOverflow only fires for has_text_frame).
                if not getattr(shape, "has_text_frame", False):
                    continue
                tf = shape.text_frame  # type: ignore[attr-defined]
                # Only fix frames whose auto-size hasn't been set yet —
                # SHAPE_TO_FIT_TEXT or TEXT_TO_FIT_SHAPE owners have made
                # an explicit choice and shouldn't be silently flipped.
                if tf.auto_size in (
                    MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT,
                    MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE,
                ):
                    continue
                desc = (
                    f"Set '{shape.name}' text frame auto_size = "
                    f"TEXT_TO_FIT_SHAPE (estimated {issue.ratio:.1f}× overflow)."
                )
                fixes.append(desc)
                if not dry_run:
                    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

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

        # Refresh ``issues`` so the residual punch list is just
        # ``report.issues`` (no extra ``slide.lint()`` call needed).
        # Skipped on dry_run because nothing changed on the slide.
        # Re-uses the same ``include_effect_bleed`` mode the original
        # report was built under, so a bleed-enabled report's residual
        # punch list still includes bleed-only issues.
        if not dry_run and fixes:
            self._issues = self._slide.lint(
                include_effect_bleed=self._include_effect_bleed,
                disable=self._disable,
                min_severity=self._min_severity,
            ).issues

        return fixes

    def fingerprints(self) -> list[str]:
        """Return a stable fingerprint string for each issue.

        Useful for CI baselining: serialise this list into the repo,
        re-run lint after changes, and diff to see only newly-introduced
        issues.

        The fingerprint is a 12-char hex digest of
        ``code | shape names | side / kind / axis``: the *content* of
        the issue, not its position in the report or any volatile field
        like the exact intersection area.  Tweaking text inside a shape
        without moving it does not change the fingerprint; resizing a
        shape that was already off-slide does not produce a new
        fingerprint either (still the same OffSlide on the same shape).
        """
        return [_issue_fingerprint(i) for i in self._issues]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DEFAULT_SLIDE_W = Emu(9144000)  # 10 inches in EMU (standard widescreen)
_DEFAULT_SLIDE_H = Emu(6858000)  # 7.5 inches in EMU


def _issue_fingerprint(issue: LintIssue) -> str:
    """Return a 12-char hex digest stable across runs for *issue*.

    Encodes only the *content* of the issue: the rule code, the names
    of the involved shapes, and any classifying field (``side`` for
    OffSlide, ``axis`` for OffGridDrift, ``kind`` for ShapeCollision).
    Volatile fields like exact intersection area or absolute position
    are deliberately excluded so a CI baseline survives small layout
    nudges that don't fix the underlying issue.
    """
    import hashlib

    parts: list[str] = [issue.code]
    for shape in issue.shapes:
        try:
            parts.append(shape.name or "")
        except Exception:
            parts.append("?")
    for attr in ("side", "axis", "kind"):
        val = getattr(issue, attr, None)
        if val:
            parts.append(f"{attr}={val}")
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


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


def _effective_bbox(shape: BaseShape) -> tuple[int, int, int, int]:
    """Return the shape bbox inflated by its shadow's blur radius.

    Each side is extended by ``blur_radius / 2``.  Returns the raw bbox
    when no shadow is set or when ``shape.shadow`` is ``None`` (e.g.
    :class:`~power_pptx.shapes.graphfrm.GraphicFrame`).

    TODO: project the shadow ``distance`` along its ``direction`` to
    extend only the side(s) the shadow falls on, instead of inflating
    every side uniformly.  Glow / soft-edges / reflection follow the
    same pattern and should be folded in.
    """
    left, top, right, bottom = _shape_bbox(shape)
    try:
        shadow = shape.shadow
    except Exception:
        return left, top, right, bottom
    if shadow is None:
        return left, top, right, bottom
    try:
        blur = shadow.blur_radius
    except Exception:
        return left, top, right, bottom
    if blur is None:
        return left, top, right, bottom
    inflate = int(int(blur) / 2)
    if inflate <= 0:
        return left, top, right, bottom
    return left - inflate, top - inflate, right + inflate, bottom + inflate


def _check_off_slide(
    shape: BaseShape,
    slide_w: Length,
    slide_h: Length,
    *,
    bbox_fn=None,
) -> list[LintIssue]:
    """Return OffSlide issues for *shape* if it exceeds the slide boundary.

    *bbox_fn* picks the bbox provider; defaults to :func:`_shape_bbox`.
    Pass :func:`_effective_bbox` to inflate by shadow blur radius.  When
    a non-default *bbox_fn* is used, edges that exceed the slide *only*
    because of effect bleed are emitted as :class:`OffSlideShadow`.
    """
    issues: list[LintIssue] = []
    bbox_fn = bbox_fn or _shape_bbox
    left, top, right, bottom = bbox_fn(shape)
    raw = (
        (left, top, right, bottom)
        if bbox_fn is _shape_bbox
        else _shape_bbox(shape)
    )
    sw, sh = int(slide_w), int(slide_h)

    def _cls(side: str, raw_off: bool) -> LintIssue:
        if bbox_fn is _shape_bbox or raw_off:
            return OffSlide(shape, side)
        return OffSlideShadow(shape, side)

    if left < 0:
        issues.append(_cls("left", raw[0] < 0))
    if top < 0:
        issues.append(_cls("top", raw[1] < 0))
    if right > sw:
        issues.append(_cls("right", raw[2] > sw))
    if bottom > sh:
        issues.append(_cls("bottom", raw[3] > sh))
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

    # Approximate character width at the given pt size.  The base 0.55×
    # multiplier is a Calibri-ish average across mixed casing, but it
    # systematically over-estimates short uppercase strings (badge /
    # pill labels) where every character is an upper-case letter and
    # there's only one line.  For short single-line strings (≤ 20
    # chars), use a tighter 0.45× multiplier — see IMPROVEMENT_PLAN
    # item 11 for the failure case ("MOST POPULAR" pill at 9pt).
    has_newline = "\n" in text
    short_single_line = (not has_newline) and len(text) <= 20
    char_w_pt_mult = 0.45 if short_single_line else 0.55
    char_w_emu = font_pt * char_w_pt_mult * _PT_TO_EMU
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
_PP_LINTSKIP = "{%s}lintSkip" % _LINT_NS

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
    """Return the ``lint_group`` value stored on *cNvPr*, or ``None``.

    An *explicitly empty* tag is preserved as ``""`` (the "opted out
    of any implicit group" sentinel); a *missing* tag returns ``None``.
    """
    ext = _find_lint_ext(cNvPr)
    if ext is not None:
        node = ext.find(_PP_LINTGROUP)
        if node is not None:
            name = node.get("name")
            if name is not None:
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

    # Go through the oxml descriptor so cNvPr's child ordering
    # (hlinkClick → hlinkHover → extLst) is respected even when the
    # other children are present.
    extLst = cNvPr.get_or_add_extLst()

    ext = _find_lint_ext(cNvPr)
    if ext is None:
        ext = etree.SubElement(extLst, _A_EXT)
        ext.set("uri", _LINT_EXT_URI)

    node = ext.find(_PP_LINTGROUP)
    if node is None:
        node = etree.SubElement(ext, _PP_LINTGROUP)
    node.set("name", value)


def _clear_lint_group(cNvPr) -> None:
    """Remove any lint-group metadata from *cNvPr* (both new and legacy).

    Only the ``<pp:lintGroup>`` node is removed; siblings under the same
    ``<a:ext>`` (notably ``<pp:lintSkip>``) are preserved.  The
    enclosing ``<a:ext>`` and ``<a:extLst>`` are removed only when they
    become empty as a side-effect.
    """
    if _LEGACY_LINT_GROUP_ATTR in cNvPr.attrib:
        del cNvPr.attrib[_LEGACY_LINT_GROUP_ATTR]
    extLst = cNvPr.find(_A_EXTLST)
    if extLst is None:
        return
    ext = _find_lint_ext(cNvPr)
    if ext is None:
        return
    node = ext.find(_PP_LINTGROUP)
    if node is not None:
        ext.remove(node)
    # Tidy up: drop the wrapper elements only if nothing else lives in
    # them, so an unrelated ``lint_skip`` setting on the same shape
    # survives a ``lint_group = None`` clear.
    if len(ext) == 0:
        extLst.remove(ext)
    if len(extLst) == 0:
        cNvPr.remove(extLst)


def _shape_lint_group(shape: BaseShape) -> str | None:
    """Return the ``lint_group`` tag for *shape*, or ``None`` if untagged.

    Resolution order:

    1. An explicit ``lint_group`` value stored on the shape's ``cNvPr``
       (set via ``shape.lint_group = "card"``).
    2. A name-prefix convention: a shape named ``"card.bg"`` /
       ``"card.label"`` / ``"card.title"`` is implicitly grouped under
       ``"card"``.  This lets a recipe author group several
       co-positioned shapes by naming them once, rather than tagging
       each individually after the fact.

    The dotted-prefix convention is only a fallback — an explicit tag
    always wins, so callers who really want shapes named ``"foo.bar"``
    not to be grouped can clear the implicit grouping with
    ``shape.lint_group = ""`` (empty string is treated as a no-group
    sentinel).
    """
    try:
        cNvPr = shape._element._nvXxPr.cNvPr  # pyright: ignore[reportPrivateUsage]
    except AttributeError:
        cNvPr = None
    if cNvPr is not None:
        explicit = _read_lint_group(cNvPr)
        if explicit is not None:
            # Empty-string explicit tag opts the shape *out* of any
            # implicit name-prefix group.
            return explicit or None
    # Name-prefix fallback.
    try:
        name = shape.name
    except Exception:
        return None
    if name and "." in name:
        prefix = name.split(".", 1)[0].strip()
        if prefix:
            return prefix
    return None


def _read_lint_skip(cNvPr) -> frozenset[str]:
    """Return the set of lint check codes silenced on *cNvPr*."""
    ext = _find_lint_ext(cNvPr)
    if ext is None:
        return frozenset()
    node = ext.find(_PP_LINTSKIP)
    if node is None:
        return frozenset()
    raw = node.get("codes") or ""
    return frozenset(code for code in raw.split(",") if code)


def _write_lint_skip(cNvPr, codes) -> None:
    """Store ``lint_skip = codes`` on *cNvPr* using ``a:extLst/a:ext``."""
    from lxml import etree

    # Drop any pre-2.1.1 legacy attribute so the new format stays
    # canonical.  Without this, decks created with 2.1.0 that touch
    # ``lint_skip`` (and never ``lint_group``) keep emitting the
    # schema-invalid custom-namespace attribute on cNvPr — the same
    # XML PowerPoint "repairs and removes" on open.
    if _LEGACY_LINT_GROUP_ATTR in cNvPr.attrib:
        del cNvPr.attrib[_LEGACY_LINT_GROUP_ATTR]

    # Go through the oxml descriptor so cNvPr's child ordering is
    # respected — see ``_write_lint_group``.
    extLst = cNvPr.get_or_add_extLst()

    ext = _find_lint_ext(cNvPr)
    if ext is None:
        ext = etree.SubElement(extLst, _A_EXT)
        ext.set("uri", _LINT_EXT_URI)

    node = ext.find(_PP_LINTSKIP)
    if not codes:
        # Empty assignment clears the node entirely.
        if node is not None:
            ext.remove(node)
        # Drop the ext / extLst if nothing else lives in them, so the
        # XML stays minimal.
        if len(ext) == 0:
            extLst.remove(ext)
        if len(extLst) == 0:
            cNvPr.remove(extLst)
        return

    if node is None:
        node = etree.SubElement(ext, _PP_LINTSKIP)
    # Sort for stable round-trip diffs; comma-joined is the simplest legal
    # serialisation for a small string set on a single attribute.
    node.set("codes", ",".join(sorted(codes)))


def _shape_lint_skip(shape: BaseShape) -> frozenset[str]:
    """Return the set of lint check codes suppressed on *shape*."""
    try:
        cNvPr = shape._element._nvXxPr.cNvPr  # pyright: ignore[reportPrivateUsage]
    except AttributeError:
        return frozenset()
    return _read_lint_skip(cNvPr)


def _bbox_overlap(
    bbox_a: tuple[int, int, int, int],
    bbox_b: tuple[int, int, int, int],
) -> tuple[int, float]:
    """Return ``(intersection_area, overlap_pct)`` for two bboxes.

    ``overlap_pct`` is the intersection area as a fraction of the
    smaller shape's area — the same metric the collision detector
    thresholds against.  Returns ``(0, 0.0)`` when the bboxes do not
    intersect.
    """
    al, at, ar, ab = bbox_a
    bl, bt, br, bb = bbox_b
    ix_l = max(al, bl)
    ix_t = max(at, bt)
    ix_r = min(ar, br)
    ix_b = min(ab, bb)
    if ix_r <= ix_l or ix_b <= ix_t:
        return 0, 0.0
    area = (ix_r - ix_l) * (ix_b - ix_t)
    area_a = max(1, (ar - al) * (ab - at))
    area_b = max(1, (br - bl) * (bb - bt))
    return area, area / min(area_a, area_b)


def _classify_collision(
    bbox_a: tuple[int, int, int, int],
    bbox_b: tuple[int, int, int, int],
    overlap_pct: float,
) -> tuple[str, float]:
    """Score and tier a collision into ``(kind, score)``.

    ``score`` is the likelihood the overlap is a layout bug, in
    ``[0.0, 1.0]``.  Higher = more suspicious.  ``kind`` is one of
    ``"incidental"``, ``"partial"``, ``"matched"``.

    Heuristic intent:

    * **Containment** (the smaller shape is fully inside the larger)
      pulls the score *down* — this is the card-on-panel pattern.
      ``overlap_pct`` doubles as the containment ratio: it's the
      intersection area divided by the smaller shape's area, which
      reaches 1.0 exactly when the smaller shape is fully contained.
    * **Size ratio** (smaller_area / larger_area) close to 1.0 pulls
      the score *up* — same-size pairs are more likely duplicates.
    * **Overlap percentage** of the smaller shape pulls the score *up*.
    """
    al, at, ar, ab = bbox_a
    bl, bt, br, bb = bbox_b
    area_a = max(1, (ar - al) * (ab - at))
    area_b = max(1, (br - bl) * (bb - bt))
    size_ratio = min(area_a, area_b) / max(area_a, area_b)  # in (0, 1]

    # Tolerance in EMU for "near-identical bbox" (5% on each axis).
    tol_w = max(1, int(0.05 * max(ar - al, br - bl)))
    tol_h = max(1, int(0.05 * max(ab - at, bb - bt)))
    bboxes_match = (
        abs(al - bl) <= tol_w
        and abs(at - bt) <= tol_h
        and abs(ar - br) <= tol_w
        and abs(ab - bb) <= tol_h
    )

    # "matched": near-identical bbox AND heavy overlap.  Almost
    # certainly a duplicate / copy-paste bug.
    if bboxes_match and overlap_pct > 0.80:
        return "matched", min(1.0, 0.85 + 0.15 * overlap_pct)

    # "incidental": one shape fully contains the other and they aren't
    # the same size — the card-on-panel pattern.
    fully_contained = (
        _bbox_contains(bbox_a, bbox_b) or _bbox_contains(bbox_b, bbox_a)
    )
    if fully_contained and size_ratio < 0.9:
        # Full containment + small size_ratio → very low score.
        score = 0.5 * size_ratio + 0.1 * (1.0 - overlap_pct)
        return "incidental", max(0.0, min(1.0, score))

    # "partial": neither contains the other, scored on size_ratio and
    # overlap_pct.  Two similarly-sized shapes overlapping a lot is
    # suspicious; two very-different sizes barely touching is not.
    score = 0.4 * size_ratio + 0.6 * min(1.0, overlap_pct)
    return "partial", max(0.0, min(1.0, score))


def _check_collisions(
    shapes: Sequence[BaseShape],
    *,
    bbox_fn=None,
) -> list[LintIssue]:
    """Return ShapeCollision issues for pairs of overlapping shapes.

    Shapes sharing a non-empty ``lint_group`` are treated as intentionally
    layered and never produce a collision warning — group suppression
    runs *before* scoring, since a tagged group is "intentional" by
    definition.  Shapes with no group, or shapes in different groups,
    continue through to scoring + classification.

    *bbox_fn* picks the bbox provider; defaults to :func:`_shape_bbox`.
    Pass :func:`_effective_bbox` to inflate by shadow blur radius.  When
    a non-default *bbox_fn* is supplied, collisions that would *not*
    fire on the raw bbox are emitted as the ``ShapeCollisionShadow``
    subclass so callers can opt them out separately via ``lint_skip``.
    """
    issues: list[LintIssue] = []
    bbox_fn = bbox_fn or _shape_bbox
    bboxes = [bbox_fn(s) for s in shapes]
    # Only compute raw bboxes when bleed is enabled — otherwise the
    # raw and effective bboxes are the same and there's nothing to
    # compare against.
    using_bleed = bbox_fn is not _shape_bbox
    raw_bboxes = [_shape_bbox(s) for s in shapes] if using_bleed else None
    groups = [_shape_lint_group(s) for s in shapes]

    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            # Suppress collisions inside a designer-tagged group *before*
            # scoring — a tagged group is "intentional" by definition.
            gi, gj = groups[i], groups[j]
            if gi is not None and gi == gj:
                continue

            area, pct = _bbox_overlap(bboxes[i], bboxes[j])
            if pct < _COLLISION_THRESHOLD:
                continue

            # Auto-suppress the "small shape stacked on top of a larger
            # backing card" pattern (badge-on-card, eyebrow-on-rectangle,
            # accent-bar-on-card).  The combination of (a) the smaller
            # shape is *strictly* contained inside the larger (size
            # ratio < 0.9 — equal-bbox pairs are still classified as
            # ``matched`` so callers can audit them), and (b) the
            # smaller shape has a higher z-order — i.e. it's drawn
            # later in spTree (higher index in this iteration) — is the
            # canonical layered-design layout.  See IMPROVEMENT_PLAN.md
            # item 12.
            ai_l, ai_t, ai_r, ai_b = bboxes[i]
            aj_l, aj_t, aj_r, aj_b = bboxes[j]
            area_i = max(1, (ai_r - ai_l) * (ai_b - ai_t))
            area_j = max(1, (aj_r - aj_l) * (aj_b - aj_t))
            size_ratio = min(area_i, area_j) / max(area_i, area_j)
            if size_ratio < 0.9:
                if _bbox_contains(bboxes[i], bboxes[j]) and area_j < area_i:
                    # j is the smaller shape and it's drawn on top of i
                    # (j > i in spTree order); skip.
                    continue
                # Note: ``i contained in j with i < j`` would mean the
                # smaller shape is *under* the larger one — a
                # ZOrderAnomaly, not a layered-design pattern — so we
                # let collision detection proceed.

            kind, score = _classify_collision(bboxes[i], bboxes[j], pct)

            # Decide whether the inflated bbox is what triggered the
            # collision: if the raw bboxes don't intersect by at least
            # the threshold, this is bleed-only.
            cls: type[ShapeCollision] = ShapeCollision
            if using_bleed:
                assert raw_bboxes is not None  # narrows type for mypy
                _, raw_pct = _bbox_overlap(raw_bboxes[i], raw_bboxes[j])
                if raw_pct < _COLLISION_THRESHOLD:
                    cls = ShapeCollisionShadow

            issues.append(
                cls(
                    shapes[i],
                    shapes[j],
                    intersection_area=area,
                    intersection_pct=pct,
                    groups=(gi, gj),
                    score=score,
                    kind=kind,
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
_GRID_TIGHT_TOLERANCE_EMU = 45720  # ~0.05" (was 0.01"; see IMPROVEMENT_PLAN item 10)
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


def lint_slide(
    slide: Slide,
    *,
    include_effect_bleed: bool = False,
    disable: Sequence[str] = (),
    min_severity: str | LintSeverity = LintSeverity.INFO,
) -> SlideLintReport:
    """Inspect *slide* for geometric and typographic issues.

    *include_effect_bleed* is opt-in (default ``False``): when ``True``
    the :class:`OffSlide` and :class:`ShapeCollision` detectors widen
    each shape's bbox by its shadow blur radius before checking
    geometry.  Bleed-only triggers come back as :class:`OffSlideShadow`
    / :class:`ShapeCollisionShadow` so callers can opt them out
    separately via ``shape.lint_skip``.

    *disable* is an iterable of issue ``code`` values to skip entirely
    — e.g. ``disable=["ShapeCollision", "OffGridDrift"]`` silences both
    rules deck-wide.  ``ShapeCollisionShadow`` and ``OffSlideShadow``
    are *not* implied by their non-shadow base codes; pass them
    explicitly.

    *min_severity* drops issues below the named threshold from the
    report.  Accepts a :class:`LintSeverity` member or a case-insensitive
    string (``"info"``, ``"warning"``, ``"error"``).  The default
    ``"info"`` keeps everything.

    Returns a :class:`SlideLintReport` with the detected issues.
    """
    if isinstance(min_severity, str):
        try:
            min_severity_enum = LintSeverity(min_severity.lower())
        except ValueError:
            raise ValueError(
                f"min_severity must be one of "
                f"{[s.value for s in LintSeverity]}, got {min_severity!r}"
            )
    else:
        min_severity_enum = min_severity
    disabled = frozenset(disable)

    slide_w, slide_h = _slide_dimensions(slide)
    issues: list[LintIssue] = []
    shapes = list(slide.shapes)
    bbox_fn = _effective_bbox if include_effect_bleed else _shape_bbox

    for shape in shapes:
        if slide_w is not None and slide_h is not None:
            issues.extend(
                _check_off_slide(shape, slide_w, slide_h, bbox_fn=bbox_fn)
            )
        issues.extend(_check_text_overflow(shape))
        issues.extend(_check_min_font_size(shape))
        issues.extend(_check_low_contrast(shape, slide))

    issues.extend(_check_collisions(shapes, bbox_fn=bbox_fn))
    issues.extend(_check_off_grid_drift(shapes))
    issues.extend(_check_z_order_anomalies(shapes))
    issues.extend(_check_master_placeholder_collision(slide, shapes))

    # Per-shape opt-out: drop issues whose code is silenced on *every*
    # target shape via ``shape.lint_skip``.  Cross-shape issues
    # (ShapeCollision, ZOrderAnomaly) are only suppressed when *both*
    # shapes opt out — a one-sided opt-out keeps the warning, since the
    # other shape might still want to know.
    skip_cache: dict[int, frozenset[str]] = {}

    def _skipped(issue: LintIssue) -> bool:
        if not issue.shapes:
            return False
        for shape in issue.shapes:
            key = id(shape._element)  # pyright: ignore[reportPrivateUsage]
            if key not in skip_cache:
                skip_cache[key] = _shape_lint_skip(shape)
            if issue.code not in skip_cache[key]:
                return False
        return True

    _order = {LintSeverity.ERROR: 0, LintSeverity.WARNING: 1, LintSeverity.INFO: 2}
    threshold = _order[min_severity_enum]

    issues = [
        i for i in issues
        if not _skipped(i)
        and i.code not in disabled
        and _order[i.severity] <= threshold
    ]

    # Sort: errors → warnings → info
    issues.sort(key=lambda x: _order[x.severity])

    return SlideLintReport(
        slide,
        issues,
        include_effect_bleed=include_effect_bleed,
        disable=tuple(disabled),
        min_severity=min_severity_enum,
    )
