"""Slide and deck linter — detects layout/typographic issues on generated slides.

Public entry point::

    report = slide.lint()              # SlideLintReport
    report.issues                      # list[LintIssue]
    report.has_errors                  # bool
    report.summary()                   # human-readable string
    report.auto_fix()                  # mutates; returns list of fix descriptions

Issue types:

* ``TextOverflow``             — text does not fit its text frame, measured
  with the same font metrics ``TextFrame.fit_text`` uses.
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
* ``LayerOrderViolation``      — a shape declares ``layer_above`` but is drawn
  below the layer it claims to sit on top of.
* ``RaggedEdge``               — a filled panel ends above the bottom edge its
  neighbouring panels share, with nothing beneath it.
* ``InvalidGeometry``          — a shape's stored width or height is negative.

Declaring intentional overlap (so the collision detector stays quiet)::

    badge.lint_group = "card-1"           # n-ary: everything sharing a tag
    badge.allow_overlap_with(card)        # pairwise: exactly this one pair
    card.layer, badge.layer_above = "card", "card"   # asserts z-order too
"""

from __future__ import annotations

import functools
import math
import re
import unicodedata
from dataclasses import dataclass, field
from dataclasses import fields as dataclass_fields
from enum import Enum
from typing import TYPE_CHECKING, Any, Iterator, NamedTuple, Sequence

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

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable dict describing this issue.

        Shapes are represented by name (the full shape objects aren't
        serializable). Every subclass-specific field — ``ratio`` on
        :class:`TextOverflow`, ``side`` on :class:`OffSlide`, the collision
        scoring on :class:`ShapeCollision`, etc. — is included automatically,
        so the payload is self-describing for an LLM auto-fix loop or a CI
        dashboard consuming ``report.to_json()``.
        """
        skip = {"severity", "code", "message", "shapes"}
        # Reading a shape name dereferences its XML; guard so a single
        # orphaned/malformed shape can't crash the whole serialization
        # (this payload feeds automated agent / CI loops).
        shape_names: list[str] = []
        for s in self.shapes:
            try:
                shape_names.append(s.name or "")
            except Exception:
                shape_names.append("")
        payload: dict[str, object] = {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "shapes": shape_names,
        }
        for f in dataclass_fields(self):
            if f.name in skip:
                continue
            value = getattr(self, f.name)
            # Normalize tuples (e.g. ShapeCollision.groups) to lists for JSON.
            payload[f.name] = list(value) if isinstance(value, tuple) else value
        return payload


@dataclass
class TextOverflow(LintIssue):
    """Text does not fit the text frame (or table row) that holds it.

    The text is laid out with the font metrics ``TextFrame.fit_text`` uses:
    each run is measured at its effective size and typeface (run, then
    paragraph, then the placeholder / master it inherits from), wrapped to
    the frame width inside its insets, and stacked at the frame's line
    spacing.

    Severity depends on whether a renderer can repair the overflow.  A
    fixed-size frame is an ERROR: the text spills in every renderer.  A frame
    set to resize or shrink (``MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT`` /
    ``TEXT_TO_FIT_SHAPE``) and a table row, which grows to fit, are a WARNING:
    the stored geometry is stale, but the renderer adjusts it when the deck
    is opened or the text is edited.
    """

    #: Extent the text needs divided by the extent available, along
    #: :attr:`dimension`.  Always greater than 1.
    ratio: float = 1.0
    #: ``"height"`` when the lines do not fit vertically, ``"width"`` when a
    #: line is wider than the frame and word wrap is off.
    dimension: str = "height"
    #: How far the text runs past the frame, in points.
    overflow_pt: float = 0.0
    #: The frame's effective auto-size mode: ``"NONE"``,
    #: ``"SHAPE_TO_FIT_TEXT"``, ``"TEXT_TO_FIT_SHAPE"``, or ``None`` when no
    #: mode is set on the shape or anything it inherits from.
    auto_size: str | None = None
    #: True when a typeface was not installed, so the figures come from the
    #: text engine's fallback metrics rather than the real font.
    estimated: bool = False
    #: Zero-based table row and column of the cell with the most text, for an
    #: overflowing table row; ``None`` for a shape's own text frame.
    row: int | None = None
    col: int | None = None

    def __init__(
        self,
        shape: BaseShape,
        ratio: float,
        *,
        severity: LintSeverity = LintSeverity.ERROR,
        dimension: str = "height",
        overflow_pt: float = 0.0,
        auto_size: str | None = None,
        missing_font: str | None = None,
        row: int | None = None,
        col: int | None = None,
    ):
        times = f"{ratio:.1f}" if ratio >= 1.15 else f"{ratio:.2f}"
        if row is not None:
            detail = (
                f"row {row} needs {times}× its height for the text in cell "
                f"({row}, {col}) ({overflow_pt:.0f}pt too short). Table rows grow to fit "
                f"when rendered, so the table will be taller than its stored size."
            )
        elif dimension == "width":
            detail = (
                f"text is {times}× the text frame width with word wrap off "
                f"({overflow_pt:.0f}pt too wide)."
            )
        else:
            detail = f"text needs {times}× the text frame height ({overflow_pt:.0f}pt too tall)."
        if row is None and auto_size == "SHAPE_TO_FIT_TEXT":
            detail += (
                " The shape is set to resize to its text, so it grows when rendered or "
                "edited and its stored size is stale."
            )
        elif row is None and auto_size == "TEXT_TO_FIT_SHAPE":
            detail += (
                " The frame is set to shrink text on overflow, which PowerPoint only "
                "applies when the text is next edited."
            )
        if missing_font is not None:
            detail += (
                f" Measured with fallback font metrics because {missing_font!r} is not installed."
            )
        super().__init__(
            severity=severity,
            code="TextOverflow",
            message=f"Shape '{shape.name}': {detail}",
            shapes=(shape,),
        )
        self.ratio = ratio
        self.dimension = dimension
        self.overflow_pt = overflow_pt
        self.auto_size = auto_size
        self.estimated = missing_font is not None
        self.row = row
        self.col = col


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
        # When neither shape is tagged, append a one-line hint so
        # readers don't have to know about ``shape.lint_group`` from
        # the docstring alone. Skip the hint when the user already
        # set tags (the warning still fires because the tags don't
        # match — that signal carries different intent).
        hint_suffix = ""
        if groups == (None, None):
            hint_suffix = (
                " — tip: if this overlap is intentional, set "
                'shape.lint_group = "<name>" on both shapes, or use '
                "slide.shapes.lint_group_scope() to tag a block of "
                "shapes at once."
            )
        super().__init__(
            severity=severity,
            code=code,
            message=(
                f"Shapes '{shape_a.name}' and '{shape_b.name}' overlap "
                f"({intersection_pct:.0%} of the smaller shape's area) "
                f"[kind={kind}, score={score:.2f}]"
                + group_suffix
                + hint_suffix
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
class LayerOrderViolation(LintIssue):
    """A shape declares it sits above another layer but is drawn below it.

    Emitted when ``shape.layer_above`` names a layer the shape actually
    overlaps, *but* the z-order contradicts the declaration — the shape
    that claims to be on top is earlier in ``spTree`` and is therefore
    painted underneath.  The declaration is treated as the author's
    intent, so the drawing order is what's reported as wrong.
    """

    #: The layer name the shape declared it sits above.
    layer: str = ""

    def __init__(self, above: BaseShape, below: BaseShape, layer: str):
        super().__init__(
            severity=LintSeverity.ERROR,
            code="LayerOrderViolation",
            message=(
                f"Shape '{above.name}' declares layer_above={layer!r} but is "
                f"drawn *below* '{below.name}' (layer={layer!r}); it will be "
                f"hidden. Move '{above.name}' later in the shape tree, or drop "
                f"the layer_above declaration."
            ),
            shapes=(above, below),
        )
        self.layer = layer


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


@dataclass
class InvalidGeometry(LintIssue):
    """A shape's stored width or height is negative.

    OOXML extents must not be negative, so PowerPoint reports such a file as
    needing repair.  The shape is left out of every other geometric check,
    which cannot say anything meaningful about an area that does not exist.
    """

    #: ``"width"`` or ``"height"``.
    dimension: str = ""
    #: The negative extent as stored, in EMU.
    value_emu: int = 0

    def __init__(self, shape: BaseShape, dimension: str, value_emu: int):
        super().__init__(
            severity=LintSeverity.ERROR,
            code="InvalidGeometry",
            message=(
                f"Shape '{shape.name}' has a negative {dimension} "
                f"({value_emu / 914400:.2f}\"); PowerPoint reports the file as needing "
                f"repair. Give it a positive size."
            ),
            shapes=(shape,),
        )
        self.dimension = dimension
        self.value_emu = value_emu


@dataclass
class RaggedEdge(LintIssue):
    """A filled panel stops short of the bottom edge its neighbours share."""

    gap_emu: int = 0

    def __init__(self, shape: BaseShape, gap_emu: int):
        super().__init__(
            severity=LintSeverity.WARNING,
            code="RaggedEdge",
            message=(
                f"Shape '{shape.name}': bottom edge is {gap_emu / 12700:.1f}pt above "
                f"the bottom edge of the panels beside it, with nothing beneath it."
            ),
            shapes=(shape,),
        )
        self.gap_emu = gap_emu


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

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable dict of this slide's lint result.

        Shape: ``{"has_errors": bool, "issue_count": int, "issues": [...]}``
        where each issue is :meth:`LintIssue.to_dict`. Feed it to an LLM or a
        CI gate instead of parsing :meth:`summary`.
        """
        return {
            "has_errors": self.has_errors,
            "issue_count": len(self._issues),
            "issues": [issue.to_dict() for issue in self._issues],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        """Return :meth:`to_dict` serialized as a JSON string."""
        import json

        return json.dumps(self.to_dict(), indent=indent)

    def auto_fix(self, *, dry_run: bool = False, fix_grid_drift: bool = False) -> list[str]:
        """Apply automatic fixes for issues that can be resolved without designer judgment.

        Returns a list of human-readable descriptions of the fixes applied (or
        that *would* be applied if *dry_run* is True).  After a non-dry-run
        call, :attr:`issues` is refreshed to reflect the post-fix state — so
        the residual punch list is just ``report.issues`` rather than a
        second ``slide.lint()`` call.

        Currently auto-fixable:

        * ``OffSlide``     — moves the shape so the area it covers when
          rendered (rotated, and grown to its text when it resizes to fit)
          is on the slide.  A shape larger than the slide is shrunk first —
          a picture or group proportionally, anything else along the axis
          that is too long — since translation alone can't fix that.  Each
          shape is clamped at most once even when it triggered multiple
          OffSlide issues (e.g. left + right).
        * ``OffGridDrift`` — only with ``fix_grid_drift=True`` (the default
          is ``False``, matching :meth:`Slide.tidy`): snaps the shape's
          drifted edge onto the dominant grid line.  Off by default because
          an inferred grid can be wrong, and a snap then pulls a shape off
          an alignment the author meant.
        * ``TextOverflow`` — makes the text fit, in the way the frame's own
          auto-size setting asks for.  The text content is preserved
          verbatim in every case:

          - a frame with no auto-size setting is set to
            ``MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE`` *with the font scale that
            makes the text fit* — the value PowerPoint stores when it
            shrinks text itself.  (Setting the mode alone would shrink
            nothing until the text was next edited in PowerPoint.)  A
            frame already set to ``TEXT_TO_FIT_SHAPE`` gets the same
            computed scale;
          - a ``SHAPE_TO_FIT_TEXT`` frame is resized to its text;
          - a frame explicitly set to ``MSO_AUTO_SIZE.NONE`` keeps that
            setting and has its font sizes reduced in place, as
            ``fit_text`` does;
          - a table row is made tall enough for its text.

          Text that would need shrinking below a quarter of its size is
          left alone; the issue stays in the report.

        * ``LayerOrderViolation`` — restacks the shape that declared
          ``layer_above`` to sit immediately after the layer it named, so
          the drawing order matches the declaration.  Unlike the
          collision fixes below this needs no designer judgment: the
          author already stated which shape belongs on top, and the fix
          only makes the z-order say the same thing.  Geometry is
          untouched.

        Not auto-fixable:

        * ``ShapeCollision`` — nudging shapes apart almost always breaks intent;
          declare deliberate overlaps with ``shape.lint_group``,
          ``shape.allow_overlap_with(...)``, or a ``layer`` /
          ``layer_above`` pair to suppress.
        * ``LowContrast``, ``MinFontSize``, ``ZOrderAnomaly``,
          ``MasterPlaceholderCollision`` — require designer judgment.
        """
        fixer = _AutoFixer(self._slide, dry_run=dry_run, fix_grid_drift=fix_grid_drift)
        issues = list(self._issues)
        # Text first: resizing a shape to its text or growing a table row
        # changes geometry the OffSlide fix has to work from.
        for issue in issues:
            if isinstance(issue, TextOverflow):
                fixer.fix_text(issue)
        for issue in issues:
            fixer.fix_geometry(issue)
        fixes = fixer.fixes

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

    def diff(self, baseline: "SlideLintReport") -> list[LintIssue]:
        """Return issues present in *self* but not in *baseline*.

        This is the CI-hookable "did my change add new problems?"
        primitive.  Identity is the stable :meth:`fingerprints` digest, so
        an issue that merely *moved* (a shape already off-slide that was
        nudged but still off-slide) is treated as the same issue and is
        *not* reported as new.  The returned list preserves ``self``'s
        ordering (errors → warnings → info), and is empty when ``self`` is
        a subset of (or identical to) *baseline*.

        Use :meth:`diff_detail` if you also need the set of issues that
        were *fixed* relative to the baseline.
        """
        baseline_fps = set(baseline.fingerprints())
        return [
            issue
            for issue, fp in zip(self._issues, self.fingerprints())
            if fp not in baseline_fps
        ]

    def diff_detail(self, baseline: "SlideLintReport") -> dict[str, list[LintIssue]]:
        """Return a symmetric diff against *baseline*.

        Shape: ``{"added": [...], "fixed": [...]}`` where ``added`` are
        issues new in ``self`` (the same list :meth:`diff` returns) and
        ``fixed`` are issues that were in ``baseline`` but are gone in
        ``self``.  Both are matched by the stable :meth:`fingerprints`
        digest.
        """
        self_fps = self.fingerprints()
        base_fps = baseline.fingerprints()
        self_fp_set = set(self_fps)
        base_fp_set = set(base_fps)
        added = [
            issue
            for issue, fp in zip(self._issues, self_fps)
            if fp not in base_fp_set
        ]
        fixed = [
            issue
            for issue, fp in zip(baseline.issues, base_fps)
            if fp not in self_fp_set
        ]
        return {"added": added, "fixed": fixed}

    def to_sarif(self, *, slide_index: int | None = None) -> dict[str, object]:
        """Return a SARIF v2.1.0 document describing this slide's issues.

        SARIF (Static Analysis Results Interchange Format) is the format
        GitHub code-scanning ingests, so a CI job can upload the result
        and have lint issues surface as annotations on a PR.  The returned
        value is a plain ``dict`` that is directly ``json.dumps``-able.

        The document has a single ``run`` whose ``tool.driver`` is named
        ``power-pptx-lint``; the driver's ``rules`` list is derived from
        the distinct issue codes present, and each issue becomes one entry
        under ``runs[0].results`` with a ``ruleId``, a ``level`` mapped
        from :class:`LintSeverity` (ERROR→``error``, WARNING→``warning``,
        INFO→``note``), a ``message.text``, and a ``locations`` entry
        naming the involved shape(s).

        When *slide_index* is given it is recorded on every result (as a
        ``logicalLocation`` and a ``properties.slideIndex``) so a
        per-slide SARIF can be merged or read with the slide it came from.
        Prefer :func:`lint_report_to_sarif` to aggregate a whole deck into
        a single document.
        """
        return _build_sarif([(slide_index, self._issues)])

    def to_sarif_json(
        self, *, slide_index: int | None = None, indent: int | None = 2
    ) -> str:
        """Return :meth:`to_sarif` serialized as a JSON string."""
        import json

        return json.dumps(self.to_sarif(slide_index=slide_index), indent=indent)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DEFAULT_SLIDE_W = Emu(9144000)  # 10 inches in EMU (standard widescreen)
_DEFAULT_SLIDE_H = Emu(6858000)  # 7.5 inches in EMU


def _issue_fingerprint(issue: LintIssue) -> str:
    """Return a 12-char hex digest stable across runs for *issue*.

    Encodes only the *content* of the issue: the rule code, the names
    of the involved shapes, and any classifying field (``side`` for
    OffSlide, ``axis`` for OffGridDrift, ``kind`` for ShapeCollision,
    ``layer`` for LayerOrderViolation).
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
    for attr in ("side", "axis", "kind", "layer"):
        val = getattr(issue, attr, None)
        if val:
            parts.append(f"{attr}={val}")
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


# ---------------------------------------------------------------------------
# SARIF v2.1.0 export — the GitHub code-scanning interchange format.
# ---------------------------------------------------------------------------

#: SARIF schema URI / version constants. ``$schema`` is advisory but lets
#: GitHub and other consumers validate the document.
_SARIF_VERSION = "2.1.0"
_SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/"
    "Schemata/sarif-schema-2.1.0.json"
)
_SARIF_TOOL_NAME = "power-pptx-lint"

#: LintSeverity → SARIF result level. SARIF defines exactly these four
#: notification levels; ``info`` maps to ``note`` (its lowest).
_SARIF_LEVEL_BY_SEVERITY: dict[LintSeverity, str] = {
    LintSeverity.ERROR: "error",
    LintSeverity.WARNING: "warning",
    LintSeverity.INFO: "note",
}

#: One-line descriptions per known rule code, surfaced as the SARIF
#: rule's ``shortDescription``. Unknown codes fall back to the code
#: itself so a new issue type still produces a valid (if terse) rule.
_RULE_DESCRIPTIONS: dict[str, str] = {
    "TextOverflow": "Text does not fit the text frame or table row that holds it.",
    "OffSlide": "A shape extends beyond the slide boundary.",
    "OffSlideShadow": "A shape's shadow bleed extends beyond the slide boundary.",
    "ShapeCollision": "Two shapes' bounding boxes overlap.",
    "ShapeCollisionShadow": "Two shapes' shadow-bleed regions overlap.",
    "MinFontSize": "A text run is below the legibility threshold.",
    "OffGridDrift": "A shape is slightly off a column/row grid its siblings hit cleanly.",
    "LowContrast": "Text/background contrast is below the WCAG AA threshold.",
    "ZOrderAnomaly": "A filled shape is drawn above a shape it visually contains.",
    "MasterPlaceholderCollision": (
        "A shape sits at the position of an inheritable layout placeholder."
    ),
    "LayerOrderViolation": (
        "A shape declares it sits above a layer but is drawn below it."
    ),
    "RaggedEdge": "A filled panel ends above the bottom edge its neighbouring panels share.",
    "InvalidGeometry": "A shape's stored width or height is negative.",
}


def _sarif_artifact_uri(slide_index: int | None) -> str:
    """Return a stable artifact URI for *slide_index*.

    A deck has no on-disk per-slide file, so we synthesize a logical
    ``slide/<n>`` (or ``slide/unknown``) URI. GitHub keys annotations off
    this; keeping it stable means re-runs land on the same logical file.
    """
    if slide_index is None:
        return "slide/unknown"
    return f"slide/{slide_index}"


def _sarif_result(issue: LintIssue, slide_index: int | None) -> dict[str, object]:
    """Return a single SARIF ``result`` object for *issue*."""
    level = _SARIF_LEVEL_BY_SEVERITY.get(issue.severity, "warning")

    shape_names: list[str] = []
    for shape in issue.shapes:
        try:
            shape_names.append(shape.name or "")
        except Exception:
            shape_names.append("?")

    locations: list[dict[str, object]] = []
    artifact_uri = _sarif_artifact_uri(slide_index)
    if shape_names:
        for name in shape_names:
            location: dict[str, object] = {
                "physicalLocation": {
                    "artifactLocation": {"uri": artifact_uri},
                },
                "logicalLocations": [
                    {"name": name, "kind": "shape"},
                ],
            }
            locations.append(location)
    else:
        # No shape attached (rare) — still anchor the result to the slide.
        locations.append(
            {"physicalLocation": {"artifactLocation": {"uri": artifact_uri}}}
        )

    if slide_index is not None:
        for location in locations:
            logical = location.setdefault("logicalLocations", [])
            assert isinstance(logical, list)
            logical.append(
                {"fullyQualifiedName": f"slide[{slide_index}]", "kind": "slide"}
            )

    result: dict[str, object] = {
        "ruleId": issue.code,
        "level": level,
        "message": {"text": issue.message},
        "locations": locations,
        "partialFingerprints": {"powerPptxLintFingerprint/v1": _issue_fingerprint(issue)},
        "properties": {"shapes": shape_names},
    }
    if slide_index is not None:
        props = result["properties"]
        assert isinstance(props, dict)
        props["slideIndex"] = slide_index
    return result


def _build_sarif(
    grouped: Sequence[tuple[int | None, Sequence[LintIssue]]],
) -> dict[str, object]:
    """Assemble a SARIF v2.1.0 document from ``(slide_index, issues)`` groups.

    Shared by :meth:`SlideLintReport.to_sarif` (one group) and
    :func:`lint_report_to_sarif` (one group per slide). The driver's
    ``rules`` list is the de-duplicated set of issue codes encountered,
    in first-seen order.
    """
    results: list[dict[str, object]] = []
    rule_ids: list[str] = []
    seen_rules: set[str] = set()

    for slide_index, issues in grouped:
        for issue in issues:
            if issue.code not in seen_rules:
                seen_rules.add(issue.code)
                rule_ids.append(issue.code)
            results.append(_sarif_result(issue, slide_index))

    rules: list[dict[str, object]] = []
    for code in rule_ids:
        rules.append(
            {
                "id": code,
                "name": code,
                "shortDescription": {"text": _RULE_DESCRIPTIONS.get(code, code)},
            }
        )

    return {
        "version": _SARIF_VERSION,
        "$schema": _SARIF_SCHEMA,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": _SARIF_TOOL_NAME,
                        "informationUri": "https://github.com/power-pptx/power-pptx",
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }


def lint_report_to_sarif(
    reports: "SlideLintReport | Sequence[SlideLintReport]",
    *,
    start_index: int = 0,
) -> dict[str, object]:
    """Aggregate per-slide lint reports into one deck-level SARIF document.

    Pass a single :class:`SlideLintReport` or a sequence of them (one per
    slide, in deck order). Each result records the slide index it came
    from (in ``properties.slideIndex`` and as a ``logicalLocation``), so a
    whole-deck SARIF uploaded to GitHub code-scanning keeps the slide
    provenance of every annotation. *start_index* sets the index assigned
    to the first report (default ``0``).

    The result is a plain, ``json.dumps``-able ``dict``::

        reports = [s.lint() for s in prs.slides]
        sarif = lint_report_to_sarif(reports)
    """
    if isinstance(reports, SlideLintReport):
        reports = [reports]
    grouped: list[tuple[int | None, Sequence[LintIssue]]] = [
        (start_index + i, report.issues) for i, report in enumerate(reports)
    ]
    return _build_sarif(grouped)


def _slide_dimensions(slide: Slide) -> tuple[Length | None, Length | None]:
    """Return (width, height) of the slide in EMU, falling back to widescreen defaults."""
    try:
        prs = slide.part.package.presentation_part.presentation
        return prs.slide_width or _DEFAULT_SLIDE_W, prs.slide_height or _DEFAULT_SLIDE_H
    except Exception:
        return _DEFAULT_SLIDE_W, _DEFAULT_SLIDE_H


def _shape_frame(shape: BaseShape) -> tuple[int, int, int, int]:
    """Return ``(left, top, right, bottom)`` of *shape*'s stored frame, unrotated.

    Returns (0, 0, 0, 0) when position/size information is not available.
    A negative width or height is returned as stored (right < left), so a
    caller can tell malformed geometry from an empty frame.
    """
    try:
        left = int(shape.left or 0)
        top = int(shape.top or 0)
        width = int(shape.width or 0)
        height = int(shape.height or 0)
        return left, top, left + width, top + height
    except Exception:
        return 0, 0, 0, 0


def _shape_rotation(shape: BaseShape) -> float:
    """Clockwise rotation of *shape* in degrees, 0.0 when it has none."""
    try:
        return float(shape.rotation or 0.0) % 360.0
    except Exception:
        return 0.0


def _rotated_extent(
    frame: tuple[float, float, float, float], rotation: float
) -> tuple[int, int, int, int]:
    """The axis-aligned box a *frame* rotated by *rotation* degrees occupies.

    PowerPoint rotates a shape about the centre of its frame, so the box
    keeps that centre and takes the rotated corners' extent.
    """
    left, top, right, bottom = frame
    if rotation in (0.0, 180.0):
        return math.floor(left), math.floor(top), math.ceil(right), math.ceil(bottom)
    width, height = right - left, bottom - top
    if rotation in (90.0, 270.0):
        rot_w, rot_h = height, width
    else:
        theta = math.radians(rotation)
        cos, sin = abs(math.cos(theta)), abs(math.sin(theta))
        rot_w, rot_h = width * cos + height * sin, width * sin + height * cos
    cx, cy = (left + right) / 2, (top + bottom) / 2
    return (
        math.floor(cx - rot_w / 2),
        math.floor(cy - rot_h / 2),
        math.ceil(cx + rot_w / 2),
        math.ceil(cy + rot_h / 2),
    )


def _shape_bbox(shape: BaseShape) -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) in EMU of the area the shape covers.

    A rotated shape covers the axis-aligned extent of its rotated frame, not
    its stored frame: a 3"×0.5" bar turned 90° is half an inch wide.
    Returns (0, 0, 0, 0) when position/size information is not available.
    """
    frame = _shape_frame(shape)
    if frame[2] < frame[0] or frame[3] < frame[1]:
        return frame
    return _rotated_extent(frame, _shape_rotation(shape))


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
    inflate = _shadow_inflation(shape)
    if inflate <= 0:
        return left, top, right, bottom
    return left - inflate, top - inflate, right + inflate, bottom + inflate


def _shadow_inflation(shape: BaseShape) -> int:
    """Return the EMU a shape's shadow adds on each side (half its blur radius)."""
    try:
        shadow = shape.shadow
        blur = None if shadow is None else shadow.blur_radius
    except Exception:
        return 0
    if blur is None:
        return 0
    return max(0, int(int(blur) / 2))


class _ShapeInfo:
    """What the checks need to know about one top-level shape, read once.

    Every cross-shape check used to go back to the XML for each *pair* of
    shapes — the id lookup behind ``allow_overlap_with`` alone is an XPath
    query — which made linting a busy slide quadratic.  Reading each shape's
    box and lint metadata up front keeps the pairwise work to integer
    comparisons.
    """

    __slots__ = (
        "shape",
        "frame",
        "rotation",
        "malformed",
        "stored_box",
        "box",
        "bleed_box",
        "text_issues",
        "group",
        "allow",
        "layer",
        "skip",
        "shape_id",
        "path",
        "_bleed",
        "_backdrop",
    )

    def __init__(self, shape: BaseShape, include_effect_bleed: bool = False):
        self.shape = shape
        #: ``(left, top, right, bottom)`` of the frame stored in the XML, unrotated.
        self.frame = _shape_frame(shape)
        self.rotation = _shape_rotation(shape)
        left, top, right, bottom = self.frame
        #: ``"width"`` / ``"height"`` when that extent is negative, else ``None``.
        self.malformed = "width" if right < left else "height" if bottom < top else None
        if self.malformed:
            # Malformed geometry covers nothing: it is reported on its own
            # and kept out of every check that compares areas.
            self.frame = (left, top, left, top)
        #: The area the stored geometry covers: `frame`, rotated.
        self.stored_box = _rotated_extent(self.frame, self.rotation)
        #: The area the shape covers when rendered: `stored_box`, enlarged by
        #: :meth:`grow` for a shape that resizes to its text.
        self.box = self.stored_box
        #: `box` widened by the shadow, when effect bleed is being checked.
        self.bleed_box = self.box
        self._bleed = _shadow_inflation(shape) if include_effect_bleed else 0
        if self._bleed > 0:
            self.grow(_NO_GROWTH)
        #: ``TextOverflow`` issues found while measuring this shape's text.
        self.text_issues: list[LintIssue] = []
        cNvPr = _shape_cNvPr(shape)
        self.group = _lint_group_of(shape, cNvPr)
        self.shape_id: int | None = None
        if cNvPr is None:
            self.allow: frozenset[int] = frozenset()
            self.layer: tuple[str | None, str | None] = (None, None)
            self.skip: frozenset[str] = frozenset()
        else:
            self.allow = _read_lint_allow(cNvPr)
            self.layer = _read_lint_layer(cNvPr)
            self.skip = _read_lint_skip(cNvPr)
            self.shape_id = _int_attr(cNvPr, "id")
        #: For a connector, the segments it is drawn along (see
        #: :func:`_connector_path`); ``None`` for any other shape.
        self.path = None if self.malformed else _connector_path(shape)
        self._backdrop: Any = _UNSET

    def grow(self, growth: tuple[float, float, float, float]) -> None:
        """Enlarge `box` by a ``(d_left, d_top, d_width, d_height)`` growth.

        The growth is of the shape's own frame, so it is applied before the
        frame is rotated.
        """
        d_left, d_top, d_width, d_height = growth
        left, top, right, bottom = self.frame
        grown = (left + d_left, top + d_top, right + d_left + d_width, bottom + d_top + d_height)
        self.box = left, top, right, bottom = _rotated_extent(grown, self.rotation)
        bleed = self._bleed
        self.bleed_box = (left - bleed, top - bleed, right + bleed, bottom + bleed)

    def checked_box(self, use_bleed: bool) -> tuple[int, int, int, int]:
        """The box a geometric check tests: `bleed_box` when it counts the shadow, else `box`."""
        return self.bleed_box if use_bleed else self.box

    @property
    def backdrop(self) -> tuple[str, Any]:
        """How this shape paints over what is beneath it: ``(kind, rgb)``.

        `kind` is ``"clear"`` (nothing painted), ``"opaque"`` (a solid,
        fully opaque fill of colour `rgb`, which is ``None`` when the colour
        cannot be resolved) or ``"unknown"`` (gradient, picture, translucent
        fill, or a shape with no fill to ask about).
        """
        if self._backdrop is _UNSET:
            self._backdrop = _fill_backdrop(self.shape)
        return self._backdrop


#: A connector whose path only grazes a shape's edge by this much — an arrow
#: head pulled inside the shape it points at — does not collide with it.
_CONNECTOR_TOUCH_EMU = 45720  # 0.05"

_Point = tuple  # (x, y) in EMU


def _connector_path(shape: BaseShape) -> list[tuple[_Point, _Point]] | None:
    """The segments a connector is drawn along, in slide coordinates.

    A connector is a line, not the rectangle that bounds it: a diagonal from
    one corner of its frame to the other passes nowhere near the frame's
    other two corners.  Straight connectors are one segment; elbow
    connectors, and curved ones (which stay close to the same route), are
    the three-segment elbow through their adjustment point.  Returns
    ``None`` for anything else — a rotated connector, an unknown geometry,
    or a shape that is not a connector — so the caller falls back to the
    bounding box.
    """
    try:
        element = shape._element  # pyright: ignore[reportPrivateUsage]
        if element.tag != _P + "cxnSp" or _shape_rotation(shape):
            return None
        left, top, right, bottom = _shape_frame(shape)
        flip_h, flip_v = bool(element.flipH), bool(element.flipV)
        geom = element.spPr.find(_A + "prstGeom")
        prst = None if geom is None else geom.get("prst")
    except Exception:
        return None
    width, height = right - left, bottom - top
    if width < 0 or height < 0:
        return None
    route = _connector_route(prst, geom)
    if route is None:
        return None
    points = [
        (left + width * _flipped(x, flip_h), top + height * _flipped(y, flip_v)) for x, y in route
    ]
    return list(zip(points, points[1:]))


def _connector_route(prst: str | None, geom) -> list[tuple[float, float]] | None:
    """The points a connector of preset geometry `prst` passes through, in its frame.

    As fractions of the frame's width and height, from its start to its end;
    ``None`` for a geometry whose route is not known.
    """
    if prst in ("line", "straightConnector1"):
        return [(0.0, 0.0), (1.0, 1.0)]
    if prst == "bentConnector2":
        return [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
    if prst in ("bentConnector3", "curvedConnector3"):
        mid = _adjust_value(geom, "adj1", 0.5)
        return [(0.0, 0.0), (mid, 0.0), (mid, 1.0), (1.0, 1.0)]
    return None


def _adjust_value(geom, name: str, default: float) -> float:
    """The ``<a:gd name fmla="val N">`` adjustment `name` of `geom`, as a fraction."""
    for gd in geom.iter(_A + "gd"):
        if gd.get("name") != name:
            continue
        formula = (gd.get("fmla") or "").split()
        if len(formula) == 2 and formula[0] == "val":
            try:
                return float(formula[1]) / 100000.0
            except ValueError:
                return default
    return default


def _flipped(fraction: float, flip: bool) -> float:
    return (1.0 - fraction) if flip else fraction


def _segment_enters_box(segment: tuple[_Point, _Point], box: tuple[int, int, int, int]) -> bool:
    """True when *segment* runs through the interior of *box*.

    Liang–Barsky clipping against the box shrunk by ``_CONNECTOR_TOUCH_EMU``
    on every side, so a line ending on (or just inside) a shape's edge does
    not count.
    """
    (x0, y0), (x1, y1) = segment
    inset = _CONNECTOR_TOUCH_EMU
    left, top, right, bottom = box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset
    if right <= left or bottom <= top:
        return False
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - left), (dx, right - x0), (-dy, y0 - top), (dy, bottom - y0)):
        if p == 0:
            if q <= 0:
                return False
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 >= t1:
            return False
    return True


def _segments_cross(a: tuple[_Point, _Point], b: tuple[_Point, _Point]) -> bool:
    """True when two segments properly cross (not merely meet at an end)."""
    (ax, ay), (bx, by) = a
    (cx, cy), (dx, dy) = b

    def orient(px: float, py: float, qx: float, qy: float, rx: float, ry: float) -> float:
        return (qx - px) * (ry - py) - (qy - py) * (rx - px)

    d1 = orient(ax, ay, bx, by, cx, cy)
    d2 = orient(ax, ay, bx, by, dx, dy)
    d3 = orient(cx, cy, dx, dy, ax, ay)
    d4 = orient(cx, cy, dx, dy, bx, by)
    return d1 * d2 < 0 and d3 * d4 < 0


def _paths_meet(a: _ShapeInfo, b: _ShapeInfo) -> bool:
    """Whether two shapes, at least one a connector, actually touch.

    Called only for pairs whose bounding boxes overlap.  A connector meets a
    shape when its path enters the shape's box, and another connector when
    the two paths cross.
    """
    path_a, path_b = a.path, b.path
    if path_a is not None and path_b is not None:
        return any(_segments_cross(s, t) for s in path_a for t in path_b)
    if path_a is not None:
        return any(_segment_enters_box(s, b.box) for s in path_a)
    assert path_b is not None
    return any(_segment_enters_box(s, a.box) for s in path_b)


def _overlapping_pairs(boxes: Sequence[tuple[int, int, int, int]]) -> list[tuple[int, int]]:
    """Return the index pairs ``(i, j)``, ``i < j``, of boxes that share area.

    A sweep along the x-axis: only shapes whose horizontal spans overlap are
    ever compared, so a slide of many shapes that mostly do not touch costs
    little more than the sort.  Pairs come back in ``(i, j)`` order, which is
    shape-tree order — the order the pairwise checks report in.
    """
    order = sorted(
        (k for k, box in enumerate(boxes) if box[2] > box[0] and box[3] > box[1]),
        key=lambda k: boxes[k][0],
    )
    pairs: list[tuple[int, int]] = []
    active: list[int] = []
    for k in order:
        left, top, _right, bottom = boxes[k]
        active = [a for a in active if boxes[a][2] > left]
        for a in active:
            if boxes[a][1] < bottom and top < boxes[a][3]:
                pairs.append((a, k) if a < k else (k, a))
        active.append(k)
    pairs.sort()
    return pairs


def _check_off_slide(
    info: _ShapeInfo,
    slide_w: Length,
    slide_h: Length,
    use_bleed: bool = False,
) -> list[LintIssue]:
    """Return OffSlide issues for the shape in *info* if it exceeds the slide.

    With *use_bleed* the box widened by the shadow blur is tested; edges
    that exceed the slide *only* because of that bleed are emitted as
    :class:`OffSlideShadow`.
    """
    issues: list[LintIssue] = []
    shape = info.shape
    raw = info.box
    left, top, right, bottom = info.bleed_box if use_bleed else raw
    sw, sh = int(slide_w), int(slide_h)

    def _cls(side: str, raw_off: bool) -> LintIssue:
        if not use_bleed or raw_off:
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


# ---------------------------------------------------------------------------
# Text measurement — lay a text frame out with the library's text engine.
#
# ``TextOverflow`` used to count characters at the first run's size.  It now
# measures: every run at its effective size and typeface, words through the
# same Pillow metrics ``TextFrame.fit_text`` and ``measure_text`` use, wrapped
# to the frame width inside its insets, stacked at the paragraph's line
# spacing.  Everything here reads the XML directly so that linting never adds
# a ``<p:txBody>`` or ``<a:rPr>`` to the slide it is inspecting.
# ---------------------------------------------------------------------------

_EMU_PER_PT = 12700
#: Height of a single-spaced line in a shape as a multiple of its font size:
#: the pitch PowerPoint and LibreOffice render at 100% line spacing, whatever
#: the typeface, and what the text engine reserves.  Table cells differ (see
#: :func:`_line_em`).
_LINE_PITCH = 1.2
#: Family assumed when a run names no typeface and the theme supplies none —
#: the same default ``fit_text`` applies.
_DEFAULT_FAMILY = "Calibri"
#: Words are measured once at this size and scaled: glyph advances are linear
#: in the point size, and a large reference size keeps Pillow's whole-pixel
#: rounding negligible while letting one measurement serve every size.
_REF_SIZE_PT = 100
#: Rounding slack when comparing a laid-out extent with the frame: OOXML
#: stores exact line spacing in 1/100 pt, so allow that much per line.
_LINE_TOLERANCE_EMU = _EMU_PER_PT // 100
#: Slack for a line measured against the frame width with word wrap off.
_WIDTH_TOLERANCE_EMU = _EMU_PER_PT // 2

_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
_T_P = _A + "p"
_T_R = _A + "r"
_T_BR = _A + "br"
_T_FLD = _A + "fld"
_T_T = _A + "t"
_T_RPR = _A + "rPr"
_T_PPR = _A + "pPr"
_T_DEFRPR = _A + "defRPr"
_T_ENDPARARPR = _A + "endParaRPr"
_T_LATIN = _A + "latin"
_T_LNSPC = _A + "lnSpc"
_T_SPCBEF = _A + "spcBef"
_T_SPCAFT = _A + "spcAft"
_T_SPCPCT = _A + "spcPct"
_T_SPCPTS = _A + "spcPts"
_T_BODYPR = _A + "bodyPr"
_T_LSTSTYLE = _A + "lstStyle"
_T_NOAUTOFIT = _A + "noAutofit"
_T_NORMAUTOFIT = _A + "normAutofit"
_T_SPAUTOFIT = _A + "spAutoFit"

_UNSET: Any = object()
_TOKEN_RE = re.compile(r"\s+|\S+")
#: ``<a:bodyPr vert>`` values whose lines run top-to-bottom, so the frame's
#: height is the line length and its width is what the lines stack across.
_ROTATED_TEXT = frozenset({"vert", "vert270", "eaVert", "mongolianVert"})
#: ``vert`` values that stack individual letters; not measured.
_STACKED_TEXT = frozenset({"wordArtVert", "wordArtVertRtl"})


class _RunStyle(NamedTuple):
    """How one run of text is measured."""

    size: float  # points, after any autofit font scale
    font_file: str | None  # None: the text engine's fallback metrics
    spacing: float  # extra EMU after each character (``<a:rPr spc>``)
    caps: bool
    line_em: float  # single-spaced line height as a multiple of `size`

    @property
    def line_pt(self) -> float:
        """Height of a single-spaced line in this style, in points."""
        return self.size * self.line_em


class _BodyProps(NamedTuple):
    """Effective ``<a:bodyPr>`` settings of a text frame."""

    l_ins: int
    t_ins: int
    r_ins: int
    b_ins: int
    wrap: bool
    anchor: str  # "t", "ctr" or "b"
    vert: str
    cols: int
    col_gap: int
    #: Auto-size in effect, inherited through the placeholder chain.
    autofit: MSO_AUTO_SIZE | None
    #: Auto-size written on the shape itself (``None`` when inherited or unset).
    own_autofit: MSO_AUTO_SIZE | None
    font_scale: float  # 1.0 unless ``<a:normAutofit fontScale>`` says otherwise
    ln_reduction: float  # ``<a:normAutofit lnSpcReduction>`` as a fraction


class _TextMeasure(NamedTuple):
    """The laid-out extent of a text frame against the space it has."""

    text_w: float  # widest line, EMU
    text_h: float  # height of all lines and paragraph spacing, EMU
    avail_w: float  # line length available inside the insets, EMU
    avail_h: float  # stacking extent available (all columns), EMU
    lines: int
    body: _BodyProps
    align: str  # "l", "ctr" or "r" — where a non-wrapping line grows from
    #: Typeface that was not installed, when fallback metrics were used.
    missing_font: str | None
    #: ``(family, bold, italic, point_size, line_spacing)`` when every run
    #: shares one whole-point style and nothing but ``fit_text``'s own
    #: settings shapes the layout; ``None`` otherwise.
    uniform: tuple[str, bool, bool, int, float | None] | None

    @property
    def over_h(self) -> float:
        """EMU by which the text is taller than the frame (0 when it fits)."""
        over = self.text_h - self.avail_h
        return over if over > self.lines * _LINE_TOLERANCE_EMU else 0.0

    @property
    def over_w(self) -> float:
        """EMU by which a non-wrapping line is wider than the frame."""
        if self.body.wrap:
            return 0.0
        over = self.text_w - self.avail_w
        return over if over > _WIDTH_TOLERANCE_EMU else 0.0


@functools.lru_cache(maxsize=65536)
def _ref_width(text: str, font_file: str | None) -> int:
    """Width in EMU of the single line `text` at the reference size.

    Measured by :func:`power_pptx.text.measure_text`, so the font lookup, the
    Pillow metrics and the fallback when no font file is available are the
    text engine's own.  Passing a file rather than a family name keeps the
    engine from warning about a missing family: linting a deck on a machine
    without its fonts is routine, not something to warn about per word.
    """
    from power_pptx.text.measurement import measure_text

    try:
        return int(
            measure_text(text, Emu(10**12), size_pt=_REF_SIZE_PT, font_file=font_file).width
        )
    except Exception:
        # An unreadable font file must not take the whole lint run down;
        # half an em per character is the engine-free estimate of last resort.
        return int(len(text) * 0.5 * _REF_SIZE_PT * _EMU_PER_PT)


@functools.lru_cache(maxsize=1024)
def _line_em(font_file: str | None, in_table: bool = False) -> float:
    """Single-spaced line height for *font_file*, as a multiple of the font size.

    The text engine's model, which is how the renderers lay text out: 1.2 x
    the size in a shape whatever the face, and in a table cell the taller of
    that and the font's own ascent plus descent.  Asking the engine keeps the
    two in step, so a frame ``fit_text`` or ``measure_text`` sized is never
    reported because lint assumed a different line height.
    """
    if not in_table:
        return _LINE_PITCH
    from power_pptx.text.measurement import measure_text

    try:
        engine = measure_text(
            "Ty",
            Emu(10**12),
            size_pt=_REF_SIZE_PT,
            font_file=font_file,
            line_spacing=None,
            in_table=True,
        ).height / (_REF_SIZE_PT * _EMU_PER_PT)
    except Exception:
        return _LINE_PITCH
    return max(_LINE_PITCH, engine)


@functools.lru_cache(maxsize=1024)
def _ref_space_width(font_file: str | None) -> int:
    """Width in EMU of one space at the reference size."""
    return max(0, _ref_width("x x", font_file) - 2 * _ref_width("x", font_file))


def _is_wide(char: str) -> bool:
    """True for East Asian full-width characters, which occupy one em each."""
    return unicodedata.east_asian_width(char) in ("W", "F")


def _text_width(text: str, style: _RunStyle) -> float:
    """Width in EMU of `text` (no spaces, no breaks) set in `style`."""
    if style.caps:
        text = text.upper()
    scale = style.size / _REF_SIZE_PT
    if text.isascii():
        width = _ref_width(text, style.font_file) * scale
    else:
        # CJK ideographs and kana are one em wide in every font that has
        # them; measuring them in a Latin face would report the width of its
        # "missing glyph" box instead.
        width = 0.0
        narrow: list[str] = []
        for char in text:
            if _is_wide(char):
                width += style.size * _EMU_PER_PT
            else:
                narrow.append(char)
        if narrow:
            width += _ref_width("".join(narrow), style.font_file) * scale
    return width + style.spacing * len(text)


_Atom = tuple  # (width, line_height_pt, space_before, pieces)


def _text_atoms(fragments: Sequence[tuple[str, _RunStyle]]) -> list[_Atom]:
    """Split `fragments` into the unbreakable units a line is built from.

    Each atom is ``(width, line_height_pt, space_before, pieces)``.  A break is
    allowed at whitespace and on either side of an East Asian wide character;
    a word that changes style mid-way stays one atom.
    """
    builder = _AtomBuilder()
    for text, style in fragments:
        for token in _TOKEN_RE.findall(text):
            if token.isspace():
                builder.add_space(style)
            else:
                builder.add_word(token, style)
    builder.close()
    return builder.atoms


def _space_advance(style: _RunStyle) -> float:
    """Width in EMU of one space set in `style`, before letter spacing."""
    return _ref_space_width(style.font_file) * style.size / _REF_SIZE_PT


def _wide_parts(word: str) -> list[str]:
    """`word` cut so that each East Asian wide character stands alone."""
    if word.isascii():
        return [word]
    parts: list[str] = []
    run = ""
    for char in word:
        if not _is_wide(char):
            run += char
            continue
        if run:
            parts.append(run)
            run = ""
        parts.append(char)
    if run:
        parts.append(run)
    return parts


class _AtomBuilder:
    """Collects the atoms of :func:`_text_atoms`, one piece of text at a time."""

    def __init__(self):
        self.atoms: list[_Atom] = []
        self._pieces: list[tuple[str, _RunStyle]] = []
        self._space = 0.0  # whitespace owed before the atom being built
        self._pending = 0.0  # whitespace seen since the last atom was closed

    def add_space(self, style: _RunStyle) -> None:
        """Whitespace set in `style`: it ends the atom being built."""
        self.close()
        self._pending = max(self._pending, _space_advance(style) + style.spacing)

    def add_word(self, word: str, style: _RunStyle) -> None:
        """Text without whitespace set in `style`, broken around wide characters."""
        for part in _wide_parts(word):
            if self._pieces and (_is_wide(part[0]) or _is_wide(self._pieces[-1][0][-1])):
                self.close()
            if not self._pieces:
                self._space, self._pending = (self._pending if self.atoms else 0.0), 0.0
            self._pieces.append((part, style))

    def close(self) -> None:
        """Finish the atom being built, if any."""
        pieces = self._pieces
        if not pieces:
            return
        self.atoms.append(
            (
                sum(_text_width(text, style) for text, style in pieces),
                max(style.line_pt for _, style in pieces),
                self._space,
                pieces,
            )
        )
        self._pieces = []


def _split_overlong(
    pieces: Sequence[tuple[str, _RunStyle]], first_limit: float, limit: float
) -> list[tuple[float, float]]:
    """Break one over-wide word at characters, the way a renderer does.

    Returns ``(width, line_height_pt)`` for each line the word occupies.
    """
    lines: list[tuple[float, float]] = []
    width = size = 0.0
    cap = first_limit
    for text, style in pieces:
        for char in text:
            char_width = _text_width(char, style)
            if width > 0 and width + char_width > cap:
                lines.append((width, size))
                width = size = 0.0
                cap = limit
            width += char_width
            size = max(size, style.line_pt)
    if width > 0:
        lines.append((width, size))
    return lines


def _wrap_fragments(
    fragments: Sequence[tuple[str, _RunStyle]], first_limit: float, limit: float, wrap: bool
) -> list[tuple[float, float]]:
    """Lay one explicit line of text out as ``(width, line_height_pt)`` per rendered line.

    Greedy first-fit, which is what ``TextFitter`` and the renderers do.  An
    empty list means the fragments hold no visible text.  A line that cannot
    wrap is measured whole, run by run, as ``measure_text`` measures a line,
    so spacing between words matches the engine exactly.
    """
    if not wrap:
        return _unwrapped_line(fragments)
    lines: list[tuple[float, float]] = []
    line: tuple[float, float] | None = None  # (width, line_height_pt) being filled
    cap = first_limit
    for atom_width, atom_size, space, pieces in _text_atoms(fragments):
        if line is not None:
            width, size = line
            if width + space + atom_width <= cap:
                line = (width + (space + atom_width), max(size, atom_size))
                continue
            lines.append(line)
            cap = limit
        # A word too long for a line of its own is broken at characters.
        placed = (
            _split_overlong(pieces, cap, limit) if atom_width > cap else [(atom_width, atom_size)]
        )
        lines.extend(placed[:-1])
        if len(placed) > 1:
            cap = limit
        line = placed[-1]
    if line is not None:
        lines.append(line)
    return lines


def _unwrapped_line(fragments: Sequence[tuple[str, _RunStyle]]) -> list[tuple[float, float]]:
    """:func:`_wrap_fragments` for a frame whose word wrap is off: one line, or none."""
    if not any(text.strip() for text, _ in fragments):
        return []
    width = 0.0
    gap_pending = False  # whitespace seen since the last word
    for text, style in fragments:
        words = text.split()
        if not words:
            gap_pending = gap_pending or width > 0
            continue
        if width > 0 and (gap_pending or text[0].isspace()):
            width += _space_advance(style)
            width += style.spacing
        width += _text_width(" ".join(words), style)
        gap_pending = text[-1].isspace()
    return [(width, max(style.line_pt for _, style in fragments))]


def _fraction(value: str | None) -> float | None:
    """Parse an OOXML percentage (``"90000"`` or ``"90%"``) as a fraction."""
    if value is None:
        return None
    try:
        if value.endswith("%"):
            return float(value[:-1]) / 100.0
        return float(value) / 100000.0
    except ValueError:
        return None


def _int_attr(element, name: str) -> int | None:
    value = element.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _bool_attr(element, name: str) -> bool | None:
    value = element.get(name)
    if value is None:
        return None
    return value in ("1", "true")


#: Character properties: (size in 1/100 pt, bold, italic, typeface, letter
#: spacing in 1/100 pt, all-caps).
_CharProps = tuple
_DEFAULT_CHAR_PROPS: _CharProps = (1800, False, False, None, 0, False)
#: Paragraph properties: (line spacing, space before, space after, left
#: margin, first-line indent, right margin, alignment).  A spacing value is
#: ``("pct", fraction)``, ``("pts", emu)`` or ``None``.
_ParaProps = tuple
_DEFAULT_PARA_PROPS: _ParaProps = (None, None, None, 0, 0, 0, "l")


def _apply_char_props(props: _CharProps, rpr) -> _CharProps:
    """Return `props` overridden by whatever `rpr` (an ``a:rPr``-like element) sets."""
    if rpr is None:
        return props
    size, bold, italic, face, spacing, caps = props
    value = _int_attr(rpr, "sz")
    if value is not None and value > 0:
        size = value
    flag = _bool_attr(rpr, "b")
    if flag is not None:
        bold = flag
    flag = _bool_attr(rpr, "i")
    if flag is not None:
        italic = flag
    value = _int_attr(rpr, "spc")
    if value is not None:
        spacing = value
    cap = rpr.get("cap")
    if cap is not None:
        caps = cap == "all"
    latin = rpr.find(_T_LATIN)
    if latin is not None and latin.get("typeface"):
        face = latin.get("typeface")
    return (size, bold, italic, face, spacing, caps)


def _spacing_value(element):
    """Read an ``a:lnSpc`` / ``a:spcBef`` / ``a:spcAft`` element."""
    pct = element.find(_T_SPCPCT)
    if pct is not None:
        fraction = _fraction(pct.get("val"))
        return None if fraction is None else ("pct", fraction)
    pts = element.find(_T_SPCPTS)
    if pts is not None:
        value = _int_attr(pts, "val")
        return None if value is None else ("pts", value * _EMU_PER_PT / 100.0)
    return None


def _apply_para_props(props: _ParaProps, ppr) -> _ParaProps:
    """Return `props` overridden by whatever `ppr` (an ``a:pPr``-like element) sets."""
    if ppr is None:
        return props
    line, before, after, mar_l, indent, mar_r, align = props
    for child in ppr:
        tag = child.tag
        if tag == _T_LNSPC:
            line = _spacing_value(child) or line
        elif tag == _T_SPCBEF:
            before = _spacing_value(child) or before
        elif tag == _T_SPCAFT:
            after = _spacing_value(child) or after
    value = _int_attr(ppr, "marL")
    if value is not None:
        mar_l = value
    value = _int_attr(ppr, "indent")
    if value is not None:
        indent = value
    value = _int_attr(ppr, "marR")
    if value is not None:
        mar_r = value
    algn = ppr.get("algn")
    if algn is not None:
        align = algn
    return (line, before, after, mar_l, indent, mar_r, align)


class _TextEnv:
    """The style sources text on one slide inherits from, resolved lazily.

    One instance serves a whole lint run, so the presentation defaults, the
    theme fonts and each font-file lookup are read once however many text
    frames the slide holds.
    """

    def __init__(self, slide: Slide | None):
        self._slide = slide
        self._default_style: Any = _UNSET
        self._theme_fonts: Any = _UNSET
        self._master_styles: Any = _UNSET
        self._font_files: dict[tuple[str, bool, bool], tuple[str | None, bool]] = {}
        self._level_props: dict[tuple, tuple[_CharProps, _ParaProps, list]] = {}

    def default_style(self):
        """The presentation's ``<p:defaultTextStyle>``, or ``None``."""
        if self._default_style is _UNSET:
            style = None
            try:
                assert self._slide is not None
                prs_elm = self._slide.part.package.presentation_part.presentation._element
                style = prs_elm.find(_P + "defaultTextStyle")
            except Exception:
                style = None
            self._default_style = style
        return self._default_style

    def master_style(self, ph_type: str | None):
        """The master ``<p:txStyles>`` entry a placeholder of `ph_type` inherits."""
        if self._master_styles is _UNSET:
            styles = None
            try:
                assert self._slide is not None
                master = self._slide.slide_layout.slide_master._element
                styles = master.find(_P + "txStyles")
            except Exception:
                styles = None
            self._master_styles = styles
        styles = self._master_styles
        if styles is None:
            return None
        if ph_type in ("title", "ctrTitle"):
            name = "titleStyle"
        elif ph_type in ("dt", "ftr", "sldNum", "hdr"):
            name = "otherStyle"
        else:
            name = "bodyStyle"
        return styles.find(_P + name)

    def family(self, face: str | None) -> str:
        """Resolve a typeface attribute (possibly a theme reference) to a family."""
        if face and not face.startswith("+"):
            return face
        if self._theme_fonts is _UNSET:
            fonts = None
            try:
                assert self._slide is not None
                theme = self._slide.slide_layout.slide_master.part.theme
                fonts = (theme.fonts.major, theme.fonts.minor)
            except Exception:
                fonts = None
            self._theme_fonts = fonts
        fonts = self._theme_fonts
        if fonts is None:
            return _DEFAULT_FAMILY
        major, minor = fonts
        if face and face.startswith("+mj"):
            return major or minor or _DEFAULT_FAMILY
        return minor or _DEFAULT_FAMILY

    def font_file(self, family: str, bold: bool, italic: bool) -> tuple[str | None, bool]:
        """Return ``(path, installed)`` for the face that measures `family`.

        A missing bold or italic face falls back to another style of the same
        family, since renderers synthesise those.  A family that is not
        installed at all yields ``(None, False)``; the text engine then
        measures with its fallback metrics, exactly as ``fit_text`` does.
        """
        key = (family, bold, italic)
        found = self._font_files.get(key)
        if found is None:
            from power_pptx.text.fonts import find_font_file

            path = None
            for style in dict.fromkeys(
                ((bold, italic), (bold, False), (False, italic), (False, False))
            ):
                try:
                    path = find_font_file(family, *style)
                except Exception:
                    path = None
                if path is not None:
                    break
            found = (path, path is not None)
            self._font_files[key] = found
        return found

    def sources(self, shape: BaseShape | None, tx_body) -> tuple[list, list]:
        """Return ``(body_prs, level_sources)`` for `tx_body`, nearest first.

        `body_prs` are the ``<a:bodyPr>`` elements whose settings apply and
        `level_sources` the elements holding ``<a:lvlNpPr>`` defaults: the
        frame's own, then — for a placeholder — the layout and master
        placeholders and the master text style, then the presentation default.
        """
        body_prs: list = []
        levels: list = []
        _add_own_sources(tx_body, body_prs, levels)
        ph_type = _placeholder_type(shape)
        if ph_type is not _UNSET:
            for base_tx in _base_text_bodies(shape):
                _add_own_sources(base_tx, body_prs, levels)
            master_style = self.master_style(ph_type)
            if master_style is not None:
                levels.append(master_style)
        default_style = self.default_style()
        if default_style is not None:
            levels.append(default_style)
        return body_prs, levels

    def level_props(self, levels: list, level: int) -> tuple[_CharProps, _ParaProps]:
        """Inherited character and paragraph properties for indent `level`."""
        key = (tuple(id(source) for source in levels), level)
        cached = self._level_props.get(key)
        if cached is None:
            tag = _A + "lvl%dpPr" % (level + 1)
            char_props = _DEFAULT_CHAR_PROPS
            para_props = _DEFAULT_PARA_PROPS
            for source in reversed(levels):  # most general first
                ppr = source.find(tag)
                if ppr is None:
                    continue
                para_props = _apply_para_props(para_props, ppr)
                char_props = _apply_char_props(char_props, ppr.find(_T_DEFRPR))
            # Keep `levels` alive with the entry so the ids in `key` stay unique.
            cached = (char_props, para_props, levels)
            self._level_props[key] = cached
        return cached[0], cached[1]


def _list_style(tx_body):
    """`tx_body`'s own ``<a:lstStyle>``, or ``None`` when it sets nothing."""
    lst_style = tx_body.find(_T_LSTSTYLE)
    return lst_style if lst_style is not None and len(lst_style) else None


def _add_own_sources(tx_body, body_prs: list, levels: list) -> None:
    """Append the ``<a:bodyPr>`` and the list style `tx_body` itself holds."""
    body_pr = tx_body.find(_T_BODYPR)
    if body_pr is not None:
        body_prs.append(body_pr)
    lst_style = _list_style(tx_body)
    if lst_style is not None:
        levels.append(lst_style)


def _placeholder_type(shape: BaseShape | None):
    """The ``<p:ph type>`` of `shape` (``None`` when it names none).

    `_UNSET` when `shape` is not a placeholder or cannot be asked.
    """
    if shape is None:
        return _UNSET
    try:
        if not shape.is_placeholder:
            return _UNSET
        ph = shape._element.ph  # pyright: ignore[reportPrivateUsage]
        return None if ph is None else ph.get("type")
    except Exception:
        return _UNSET


def _base_text_bodies(shape: Any) -> Iterator[Any]:
    """Yield the text bodies of the layout, then the master, placeholder `shape` inherits."""
    base = shape
    for _ in range(2):
        try:
            base = base._base_placeholder  # pyright: ignore[reportPrivateUsage]
            base_tx = None if base is None else base._element.txBody
        except Exception:
            return
        if base is None:
            return
        if base_tx is not None:
            yield base_tx


def _first_attr(body_prs: Sequence, name: str) -> str | None:
    """The value of attribute `name` on the nearest ``<a:bodyPr>`` that sets it."""
    for body_pr in body_prs:
        value = body_pr.get(name)
        if value is not None:
            return value
    return None


def _inset(body_prs: Sequence, name: str, default: int) -> int:
    """An inset attribute from a nearest-first ``<a:bodyPr>`` chain, in EMU."""
    value = _first_attr(body_prs, name)
    try:
        return default if value is None else int(value)
    except ValueError:
        return default


def _autofit_setting(body_pr) -> tuple[MSO_AUTO_SIZE, float, float] | None:
    """``(mode, font_scale, ln_reduction)`` that `body_pr` writes, or ``None``."""
    norm = body_pr.find(_T_NORMAUTOFIT)
    if norm is not None:
        return (
            MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE,
            _fraction(norm.get("fontScale")) or 1.0,
            _fraction(norm.get("lnSpcReduction")) or 0.0,
        )
    if body_pr.find(_T_SPAUTOFIT) is not None:
        return MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT, 1.0, 0.0
    if body_pr.find(_T_NOAUTOFIT) is not None:
        return MSO_AUTO_SIZE.NONE, 1.0, 0.0
    return None


def _resolve_autofit(
    body_prs: Sequence,
) -> tuple[MSO_AUTO_SIZE | None, MSO_AUTO_SIZE | None, float, float]:
    """``(autofit, own_autofit, font_scale, ln_reduction)``; see :class:`_BodyProps`.

    The nearest ``<a:bodyPr>`` that sets an auto-size decides it.
    """
    for index, body_pr in enumerate(body_prs):
        setting = _autofit_setting(body_pr)
        if setting is not None:
            autofit, font_scale, ln_reduction = setting
            return autofit, (autofit if index == 0 else None), font_scale, ln_reduction
    return None, None, 1.0, 0.0


def _resolve_body_props(body_prs: Sequence) -> _BodyProps:
    """Effective ``<a:bodyPr>`` settings from a nearest-first chain."""
    autofit, own_autofit, font_scale, ln_reduction = _resolve_autofit(body_prs)
    cols = 1
    col_gap = 0
    if body_prs:
        cols = max(1, _int_attr(body_prs[0], "numCol") or 1)
        col_gap = max(0, _int_attr(body_prs[0], "spcCol") or 0)
    return _BodyProps(
        l_ins=_inset(body_prs, "lIns", 91440),
        t_ins=_inset(body_prs, "tIns", 45720),
        r_ins=_inset(body_prs, "rIns", 91440),
        b_ins=_inset(body_prs, "bIns", 45720),
        wrap=_first_attr(body_prs, "wrap") != "none",
        anchor=_first_attr(body_prs, "anchor") or "t",
        vert=_first_attr(body_prs, "vert") or "horz",
        cols=cols,
        col_gap=col_gap,
        autofit=autofit,
        own_autofit=own_autofit,
        font_scale=font_scale,
        ln_reduction=ln_reduction,
    )


def _has_visible_text(tx_body) -> bool:
    return any(t.text and t.text.strip() for t in tx_body.iter(_T_T))


def _measure_text_body(
    env: _TextEnv,
    tx_body,
    body: _BodyProps,
    levels: list,
    width: float,
    height: float,
    in_table: bool = False,
) -> _TextMeasure | None:
    """Lay `tx_body` out in a `width` × `height` frame and report its extent.

    `body` supplies the insets, wrapping, columns and any stored autofit
    scale; pass a modified copy to ask "would it fit at this scale?".
    `in_table` measures a table cell, whose lines are as tall as the font's
    own ascent and descent when that is more than 1.2 em.
    Returns ``None`` when there is nothing to measure: no visible text, a
    frame with no room inside its insets, or stacked WordArt text.
    """
    if body.vert in _STACKED_TEXT or not _has_visible_text(tx_body):
        return None
    inner_w = width - body.l_ins - body.r_ins
    inner_h = height - body.t_ins - body.b_ins
    if body.vert in _ROTATED_TEXT:
        inner_w, inner_h = inner_h, inner_w
    line_len = (inner_w - (body.cols - 1) * body.col_gap) / body.cols
    if line_len <= 0 or inner_h <= 0:
        return None

    layout = _TextLayout(env, body, levels, line_len, in_table)
    paragraphs = tx_body.findall(_T_P)
    for index, paragraph in enumerate(paragraphs):
        layout.add_paragraph(paragraph, first=index == 0, last=index == len(paragraphs) - 1)
    return _TextMeasure(
        text_w=layout.text_w,
        text_h=layout.text_h,
        avail_w=line_len,
        avail_h=inner_h * body.cols,
        lines=layout.lines,
        body=body,
        align=layout.first_align or "l",
        missing_font=layout.missing_font,
        uniform=layout.uniform(),
    )


def _paragraph_props(env: _TextEnv, levels: list, paragraph) -> tuple[_CharProps, _ParaProps]:
    """Character and paragraph properties of `paragraph`: its level's, then its own."""
    ppr = paragraph.find(_T_PPR)
    level = 0 if ppr is None else min(8, max(0, _int_attr(ppr, "lvl") or 0))
    char_props, para_props = env.level_props(levels, level)
    if ppr is not None:
        para_props = _apply_para_props(para_props, ppr)
        char_props = _apply_char_props(char_props, ppr.find(_T_DEFRPR))
    return char_props, para_props


def _run_text(run) -> str:
    """The text of an ``<a:r>`` or ``<a:fld>``."""
    t = run.find(_T_T)
    return "" if t is None else (t.text or "")


def _is_exact(line_spacing) -> bool:
    """True for a line spacing given in points rather than as a multiple."""
    return line_spacing is not None and line_spacing[0] == "pts"


def _paragraph_gap(value, line_pt: float) -> float:
    """Paragraph spacing in EMU; a percentage is of the line it adjoins."""
    if value is None:
        return 0.0
    if value[0] == "pts":
        return value[1]
    return value[1] * line_pt * _EMU_PER_PT


class _TextLayout:
    """Lays a text body out paragraph by paragraph, keeping the running extent.

    Serves one :func:`_measure_text_body` call.  Besides the extent it notes
    what :func:`_engine_says_it_fits` needs to know: a typeface that was not
    installed, and whether every run shares one plain style.
    """

    def __init__(
        self, env: _TextEnv, body: _BodyProps, levels: list, line_len: float, in_table: bool
    ):
        self.env = env
        self.body = body
        self.levels = levels
        self.line_len = line_len
        self.in_table = in_table
        self.text_w = 0.0
        self.text_h = 0.0
        self.lines = 0
        self.first_align: str | None = None
        self.missing_font: str | None = None
        #: False once anything but ``fit_text``'s own settings shapes the layout.
        self.plain = body.cols == 1 and body.wrap and body.vert == "horz" and body.font_scale == 1.0
        self._styles: set[tuple[str, bool, bool, int]] = set()
        self._spacings: set[float | None] = set()

    def style(self, props: _CharProps, track: bool = False) -> _RunStyle:
        """How text with character properties `props` is measured.

        With `track` the text is visible, and its style counts towards
        `missing_font` and :meth:`uniform`.
        """
        size, bold, italic, face, spacing, caps = props
        family = self.env.family(face)
        font_file, installed = self.env.font_file(family, bold, italic)
        if track:
            if not installed and self.missing_font is None:
                self.missing_font = family
            self._styles.add((family, bold, italic, size))
            if spacing or caps:
                self.plain = False
        return _RunStyle(
            size=size / 100.0 * self.body.font_scale,
            font_file=font_file,
            spacing=spacing * _EMU_PER_PT / 100.0,
            caps=caps,
            line_em=_line_em(font_file, self.in_table),
        )

    def add_paragraph(self, paragraph, first: bool, last: bool) -> None:
        """Lay `paragraph` out below the text so far.

        Space before the first paragraph and after the last is not counted.
        """
        char_props, para_props = _paragraph_props(self.env, self.levels, paragraph)
        line_spacing, before, after, mar_l, indent, mar_r, align = para_props
        if self.first_align is None:
            self.first_align = align
        if mar_l or indent or mar_r:
            self.plain = False
        limit = max(1.0, self.line_len - mar_l - mar_r)
        lines, end_h = self._wrap(paragraph, char_props, max(1.0, limit - max(0, indent)), limit)
        paragraph_h = 0.0
        for line_width, line_pt in lines:
            self.text_w = max(self.text_w, line_width + mar_l + mar_r)
            paragraph_h += self._advance(line_pt, line_spacing)
        self.lines += len(lines)
        line_h = lines[0][1] or end_h
        space_before = 0.0 if first else _paragraph_gap(before, line_h)
        space_after = 0.0 if last else _paragraph_gap(after, line_h)
        self.text_h += space_before + paragraph_h + space_after
        if space_before or space_after or _is_exact(line_spacing):
            self.plain = False
        self._spacings.add(None if line_spacing is None else line_spacing[1])

    def uniform(self) -> tuple[str, bool, bool, int, float | None] | None:
        """See :attr:`_TextMeasure.uniform`."""
        if not self.plain or len(self._styles) != 1 or len(self._spacings) != 1:
            return None
        family, bold, italic, size = next(iter(self._styles))
        if size % 100:
            return None
        return (family, bold, italic, size // 100, next(iter(self._spacings)))

    def _wrap(
        self, paragraph, char_props: _CharProps, first_limit: float, limit: float
    ) -> tuple[list[tuple[float, float]], float]:
        """The lines `paragraph` renders as, ``(width, line_height_pt)`` each.

        Also returns the height of the paragraph's end mark.  Every explicit
        line takes at least one line: an empty one is as tall as the break
        that ends it, or as the end mark when it is the last.
        """
        explicit, break_heights = self._explicit_lines(paragraph, char_props)
        end_props = _apply_char_props(char_props, paragraph.find(_T_ENDPARARPR))
        end_h = self.style(end_props).line_pt
        lines: list[tuple[float, float]] = []
        for index, (fragments, empty_h) in enumerate(zip(explicit, [*break_heights, end_h])):
            cap = first_limit if index == 0 else limit
            lines.extend(_wrap_fragments(fragments, cap, limit, self.body.wrap) or [(0.0, empty_h)])
        return lines, end_h

    def _explicit_lines(
        self, paragraph, char_props: _CharProps
    ) -> tuple[list[list[tuple[str, _RunStyle]]], list[float]]:
        """Split `paragraph` at each ``<a:br>``: each line's runs, and each break's height."""
        explicit: list[list[tuple[str, _RunStyle]]] = [[]]
        break_heights: list[float] = []
        for child in paragraph:
            tag = child.tag
            if tag in (_T_R, _T_FLD):
                text = _run_text(child)
                if text:
                    props = _apply_char_props(char_props, child.find(_T_RPR))
                    explicit[-1].append((text, self.style(props, bool(text.strip()))))
            elif tag == _T_BR:
                props = _apply_char_props(char_props, child.find(_T_RPR))
                break_heights.append(self.style(props).line_pt)
                explicit.append([])
        return explicit, break_heights

    def _advance(self, line_pt: float, line_spacing) -> float:
        """Distance in EMU from a line `line_pt` tall to the next, at `line_spacing`."""
        if _is_exact(line_spacing):
            return line_spacing[1]
        factor = 1.0 if line_spacing is None else line_spacing[1]
        factor = max(0.1, factor - self.body.ln_reduction)
        return line_pt * _EMU_PER_PT * factor


def _engine_says_it_fits(tx_body, measure: _TextMeasure) -> bool:
    """Ask ``TextFitter`` — the engine behind ``fit_text`` — whether the text fits.

    A frame ``fit_text`` has just sized must never be reported as overflowing,
    so when the layout above finds a marginal overflow in a frame that looks
    like ``fit_text`` output (one family, one whole-point size), the engine's
    own verdict at that size is authoritative.  Only marginal cases are
    referred: the two agree to within Pillow's pixel rounding, and re-wrapping
    a frame the engine's way is far costlier than the layout above.
    """
    uniform = measure.uniform
    if uniform is None or measure.over_w:
        return False
    line_h = measure.text_h / max(1, measure.lines)
    if measure.over_h > max(1.5 * line_h, 0.15 * measure.avail_h):
        return False
    family, bold, italic, size, line_spacing = uniform
    try:
        from power_pptx.text.fonts import find_font_file
        from power_pptx.text.layout import TextFitter

        text = "\n".join(paragraph.text for paragraph in tx_body.findall(_T_P))
        extents = (Emu(int(measure.avail_w)), Emu(int(measure.avail_h)))
        font_file = find_font_file(family, bold, italic)
        if line_spacing is None:
            fitted = TextFitter.best_fit_font_size(text, extents, size, font_file)
        else:
            fitted = TextFitter.best_fit_font_size(
                text, extents, size, font_file, min_size=size, line_spacing=line_spacing
            )
        return fitted == size
    except Exception:
        return False


class _TextTarget(NamedTuple):
    """A text body to measure and the frame it must fit."""

    shape: BaseShape  # the shape reported in an issue
    tx_body: Any
    width: float  # frame extent on the slide, EMU
    height: float
    body: _BodyProps
    levels: list

    def measure(self, env: _TextEnv, body: _BodyProps | None = None) -> _TextMeasure | None:
        """Lay the text out in the frame, with `body` in place of its own settings if given."""
        body = self.body if body is None else body
        return _measure_text_body(env, self.tx_body, body, self.levels, self.width, self.height)


class _FrameOverflow(NamedTuple):
    """A text frame whose text does not fit it."""

    target: _TextTarget
    measure: _TextMeasure
    over_w: float  # EMU by which the text is too wide (see :func:`_frame_overflow`)
    over_h: float  # EMU by which it is too tall


def _group_scale(element) -> tuple[float, float]:
    """Factor by which enclosing groups scale `element`'s own extents."""
    scale_x = scale_y = 1.0
    parent = element.getparent()
    while parent is not None and parent.tag == _P + "grpSp":
        try:
            xfrm = parent.grpSpPr.xfrm
            child_ext = None if xfrm is None else xfrm.chExt
            if child_ext is not None and xfrm.ext is not None and child_ext.cx and child_ext.cy:
                scale_x *= xfrm.ext.cx / child_ext.cx
                scale_y *= xfrm.ext.cy / child_ext.cy
        except Exception:
            pass
        parent = parent.getparent()
    return scale_x, scale_y


def _shape_text_target(env: _TextEnv, shape: BaseShape) -> _TextTarget | None:
    """Return the measurable text frame of `shape`, or ``None`` if it has none.

    Reads ``<p:txBody>`` straight off the element: ``shape.text_frame`` would
    add an empty one to a shape that has none.
    """
    try:
        if not shape.has_text_frame:
            return None
        element = shape._element  # pyright: ignore[reportPrivateUsage]
        tx_body = element.txBody
        if tx_body is None:
            return None
        width = float(shape.width or 0)
        height = float(shape.height or 0)
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    scale_x, scale_y = _group_scale(element)
    body_prs, levels = env.sources(shape, tx_body)
    return _TextTarget(
        shape, tx_body, width * scale_x, height * scale_y, _resolve_body_props(body_prs), levels
    )


def _iter_text_shapes(shapes) -> Iterator[BaseShape]:
    """Yield every shape that can hold text, descending into groups."""
    for shape in shapes:
        members = None
        try:
            if shape._element.tag == _P + "grpSp":  # pyright: ignore[reportPrivateUsage]
                members = shape.shapes  # type: ignore[attr-defined]
        except Exception:
            members = None
        if members is not None:
            yield from _iter_text_shapes(members)
        else:
            yield shape


def _auto_size_name(autofit: MSO_AUTO_SIZE | None) -> str | None:
    return None if autofit is None else autofit.name


def _frame_overflow(target: _TextTarget, measure: _TextMeasure) -> tuple[float, float]:
    """Return ``(over_w, over_h)``: EMU by which the text exceeds its frame.

    Both are zero when the text fits — including when the layout finds a
    marginal overflow that ``TextFitter`` itself does not (see
    :func:`_engine_says_it_fits`).
    """
    over_w, over_h = measure.over_w, measure.over_h
    if over_h and not over_w and _engine_says_it_fits(target.tx_body, measure):
        over_h = 0.0
    return over_w, over_h


def _frame_overflow_of(env: _TextEnv, shape: BaseShape) -> _FrameOverflow | None:
    """Measure the text frame of `shape`; ``None`` when it has none or its text fits."""
    target = _shape_text_target(env, shape)
    if target is None:
        return None
    measure = target.measure(env)
    if measure is None:
        return None
    over_w, over_h = _frame_overflow(target, measure)
    if not over_w and not over_h:
        return None
    return _FrameOverflow(target, measure, over_w, over_h)


def _frame_overflow_issue(
    target: _TextTarget, measure: _TextMeasure, over_w: float, over_h: float
) -> LintIssue:
    """Return the ``TextOverflow`` for a text frame that is `over_w` / `over_h` out.

    A frame that resizes or shrinks to fit is a WARNING: a renderer repairs it
    when the deck is opened or the text is edited.  A fixed frame is an ERROR.
    """
    # Report the dimension that is further out; width only arises with
    # word wrap off, where it is usually the whole story.
    ratio_w = measure.text_w / measure.avail_w if over_w else 0.0
    ratio_h = measure.text_h / measure.avail_h if over_h else 0.0
    autofit = measure.body.autofit
    repairable = autofit in (MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT, MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE)
    return TextOverflow(
        target.shape,
        max(ratio_w, ratio_h),
        severity=LintSeverity.WARNING if repairable else LintSeverity.ERROR,
        dimension="width" if ratio_w >= ratio_h else "height",
        overflow_pt=(over_w if ratio_w >= ratio_h else over_h) / _EMU_PER_PT,
        auto_size=_auto_size_name(autofit),
        missing_font=measure.missing_font,
    )


_NO_GROWTH = (0.0, 0.0, 0.0, 0.0)


def _auto_size_growth(
    measure: _TextMeasure, over_w: float, over_h: float
) -> tuple[float, float, float, float]:
    """Change in ``(left, top, width, height)`` when a shape resizes to its text.

    A ``SHAPE_TO_FIT_TEXT`` shape keeps the edge its text is anchored to and
    grows away from it: down from a top anchor, up from a bottom anchor, both
    ways from the middle; a line that cannot wrap grows away from the side the
    paragraph is aligned to.
    """
    if measure.body.vert != "horz":
        return _NO_GROWTH
    grow_h = over_h / measure.body.cols
    grow_w = over_w
    d_top = {"ctr": -grow_h / 2, "b": -grow_h}.get(measure.body.anchor, 0.0)
    d_left = {"ctr": -grow_w / 2, "r": -grow_w}.get(measure.align, 0.0)
    return (d_left, d_top, grow_w, grow_h)


def _table_cell_body(tc) -> _BodyProps:
    """Body properties of a table cell: its margins, always wrapping, no autofit."""
    return _BodyProps(
        l_ins=int(tc.marL),
        t_ins=int(tc.marT),
        r_ins=int(tc.marR),
        b_ins=int(tc.marB),
        wrap=True,
        anchor="t",
        vert="horz",
        cols=1,
        col_gap=0,
        autofit=None,
        own_autofit=None,
        font_scale=1.0,
        ln_reduction=0.0,
    )


def _table_row_needs(env: _TextEnv, shape: BaseShape) -> list[tuple[int, int, float, int, Any]]:
    """Measure the text in each row of the table in `shape`.

    Returns ``(row_idx, stored_height, needed_height, col_idx, measure)`` for
    every row that holds text, where the needed height is that of its tallest
    cell including the cell margins.  Cells that span several rows are left
    out: their text is shared between rows the stored heights do not divide.
    """
    try:
        tbl = shape._element.graphic.graphicData.tbl  # pyright: ignore[reportPrivateUsage]
        if tbl is None:
            return []
        col_widths = [int(grid_col.w) for grid_col in tbl.tblGrid.gridCol_lst]
        rows = list(tbl.tr_lst)
    except Exception:
        return []
    needs: list[tuple[int, int, float, int, Any]] = []
    default_style = env.default_style()
    for row_idx, tr in enumerate(rows):
        try:
            row_h = int(tr.h)
        except Exception:
            continue
        worst = _tallest_cell(env, tr, col_widths, default_style)
        if worst is not None:
            needs.append((row_idx, row_h, worst[0], worst[1], worst[2]))
    return needs


def _own_cells(tr) -> Iterator[tuple[Any, Any, int, int]]:
    """Yield ``(tc, tx_body, first_column, column_span)`` for each cell of row `tr`.

    Cells merged into another, and cells whose attributes cannot be read, are
    left out but still take up their columns.
    """
    col_idx = 0
    for tc in tr.tc_lst:
        try:
            span = max(1, int(tc.gridSpan))
            merged = bool(tc.hMerge) or bool(tc.vMerge) or int(tc.rowSpan) > 1
            tx_body = tc.txBody
        except Exception:
            span, merged, tx_body = 1, True, None
        start = col_idx
        col_idx += span
        if not merged and tx_body is not None:
            yield tc, tx_body, start, span


def _tallest_cell(
    env: _TextEnv, tr, col_widths: Sequence[int], default_style
) -> tuple[float, int, Any] | None:
    """``(needed_height, column, measure)`` of the cell of `tr` that needs the most height."""
    worst: tuple[float, int, Any] | None = None
    for tc, tx_body, start, span in _own_cells(tr):
        width = sum(col_widths[start : start + span])
        if width <= 0:
            continue
        need = _cell_need(env, tc, tx_body, width, default_style)
        if need is not None and (worst is None or need[0] > worst[0]):
            worst = (need[0], start, need[1])
    return worst


def _cell_need(env: _TextEnv, tc, tx_body, width: int, default_style) -> tuple[float, Any] | None:
    """``(needed_height, measure)`` of a table cell `width` wide, margins included."""
    levels = []
    lst_style = _list_style(tx_body)
    if lst_style is not None:
        levels.append(lst_style)
    if default_style is not None:
        levels.append(default_style)
    body = _table_cell_body(tc)
    # Measured against a notional frame: only the text height matters here,
    # the row height is compared by the caller.
    measure = _measure_text_body(env, tx_body, body, levels, width, 10**9, True)
    if measure is None:
        return None
    return measure.text_h + body.t_ins + body.b_ins, measure


class _TextFinding(NamedTuple):
    """What measuring the text a top-level shape holds found."""

    issues: list[LintIssue]
    #: Change to the shape's stored ``(left, top, width, height)`` a renderer
    #: makes when it resizes the shape to its text or grows a table's rows.
    growth: tuple[float, float, float, float]


def _analyse_text(env: _TextEnv, shape: BaseShape) -> _TextFinding:
    """Measure the text `shape` holds: its overflow issues and how it will grow.

    Covers the shape's own text frame, the text frames of every shape inside
    it when it is a group, and each row when it is a table.  The text is laid
    out with the text engine's font metrics (see :func:`_measure_text_body`);
    a frame that ``TextFrame.fit_text`` has sized is never reported.

    Writing ``<a:spAutoFit/>`` or ``<a:normAutofit/>`` only records an
    intention: nothing resizes the shape or the text until a renderer does.
    So a frame set to auto-size is measured like any other.  When it resizes
    to its text (``SHAPE_TO_FIT_TEXT``) or is a table, whose rows grow to fit,
    the extent it will actually occupy is returned as `growth`, so that the
    off-slide and collision checks see the box a viewer sees rather than the
    stale stored one.
    """
    issues: list[LintIssue] = []
    growth = _NO_GROWTH
    for member in _iter_text_shapes([shape]):
        if getattr(member, "has_table", False):
            row_issues, grow_h = _table_overflows(env, member)
            issues.extend(row_issues)
            if member is shape and grow_h:
                growth = (0.0, 0.0, 0.0, grow_h)
            continue
        overflow = _frame_overflow_of(env, member)
        if overflow is None:
            continue
        issues.append(_frame_overflow_issue(*overflow))
        if member is shape and overflow.measure.body.autofit == MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT:
            growth = _auto_size_growth(overflow.measure, overflow.over_w, overflow.over_h)
    return _TextFinding(issues, growth)


def _table_overflows(env: _TextEnv, shape: BaseShape) -> tuple[list[LintIssue], float]:
    """``TextOverflow`` for each row of the table in `shape` too short for its text.

    Also returns the EMU by which the rows grow, together, when rendered.
    """
    issues: list[LintIssue] = []
    grow_h = 0.0
    for row_idx, row_h, needed, col_idx, measure in _table_row_needs(env, shape):
        over = needed - row_h
        if over <= measure.lines * _LINE_TOLERANCE_EMU or row_h <= 0:
            continue
        grow_h += over
        issues.append(
            TextOverflow(
                shape,
                needed / row_h,
                severity=LintSeverity.WARNING,
                overflow_pt=over / _EMU_PER_PT,
                missing_font=measure.missing_font,
                row=row_idx,
                col=col_idx,
            )
        )
    return issues, grow_h


def _check_text_overflow(shape: BaseShape, env: _TextEnv | None = None) -> list[LintIssue]:
    """Return TextOverflow issues for the text `shape` holds; see :func:`_analyse_text`."""
    return _analyse_text(_TextEnv(None) if env is None else env, shape).issues


# ---------------------------------------------------------------------------
# Fixing text overflow.  Each fix leaves the frame in a state the measurement
# above can still see: a stored font scale is applied when measuring, baked
# sizes and grown shapes are simply what the XML now says.
# ---------------------------------------------------------------------------

#: The ``(fontScale, lnSpcReduction)`` steps PowerPoint itself walks down when
#: it shrinks text on overflow; the first that fits is stored.
_AUTOFIT_STEPS = (
    (0.925, 0.10),
    (0.85, 0.20),
    (0.775, 0.20),
    (0.70, 0.20),
    (0.625, 0.20),
    (0.55, 0.20),
    (0.475, 0.20),
    (0.40, 0.20),
    (0.325, 0.20),
    (0.25, 0.20),
)
#: Smallest factor explicit font sizes are baked down by; below this the text
#: is unreadable and the frame needs a human.
_MIN_BAKE_PCT = 25


def _fits_scaled(env: _TextEnv, target: _TextTarget, scale: float, reduction: float) -> bool:
    """True when the text of `target` fits with its fonts scaled by `scale`."""
    trial = target.measure(env, target.body._replace(font_scale=scale, ln_reduction=reduction))
    return trial is None or (not trial.over_w and not trial.over_h)


def _iter_sized_elements(env: _TextEnv, target: _TextTarget) -> Iterator[tuple[Any, bool, int]]:
    """Yield ``(element, is_end_mark, size)`` for everything that carries a font size.

    `element` is an ``<a:r>``, ``<a:fld>`` or ``<a:br>``, or the ``<a:p>``
    itself for its end-of-paragraph mark; `size` is the effective size in
    1/100 pt, resolved the way the measurement resolves it.
    """
    for paragraph in target.tx_body.findall(_T_P):
        char_props, _ = _paragraph_props(env, target.levels, paragraph)
        for child in paragraph:
            if child.tag in (_T_R, _T_FLD, _T_BR):
                yield child, False, _apply_char_props(char_props, child.find(_T_RPR))[0]
        yield paragraph, True, _apply_char_props(char_props, paragraph.find(_T_ENDPARARPR))[0]


def _describe_overflow(over_w: float, measure: _TextMeasure) -> str:
    if over_w:
        return f"the text was {measure.text_w / measure.avail_w:.1f}× the frame width"
    return f"the text needed {measure.text_h / measure.avail_h:.1f}× the frame height"


def _fix_text_overflow(env: _TextEnv, issue: TextOverflow, dry_run: bool) -> str | None:
    """Make the text of the frame in `issue` fit; return a description, or ``None``.

    What "fit" means follows the frame's own auto-size setting, so the fix is
    the one a renderer would apply rather than a change of mode:

    * ``SHAPE_TO_FIT_TEXT`` — the shape is resized to its text.
    * ``TEXT_TO_FIT_SHAPE``, or no setting at all — the frame is set to
      ``TEXT_TO_FIT_SHAPE`` with the font scale (and line-spacing reduction)
      that makes the text fit, the values PowerPoint stores when it shrinks
      text itself.  A bare ``<a:normAutofit/>`` would shrink nothing until the
      text was next edited.
    * ``NONE`` — the author asked for no auto-fit, so the sizes are reduced in
      place, as ``fit_text`` does, and the setting is left alone.
    * a table row — the row is made tall enough for its text.

    Returns ``None``, changing nothing, when the frame no longer overflows or
    no legible size fits.
    """
    shape = issue.shapes[0]
    if issue.row is not None:
        return _fix_table_row(env, shape, issue.row, dry_run)
    overflow = _frame_overflow_of(env, shape)
    if overflow is None:
        return None
    autofit = overflow.measure.body.autofit
    if autofit == MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT:
        return _resize_to_text(shape, overflow, dry_run)
    if autofit == MSO_AUTO_SIZE.NONE:
        return _reduce_font_sizes(env, shape, overflow, dry_run)
    return _store_font_scale(env, shape, overflow, dry_run)


def _resize_to_text(shape: BaseShape, overflow: _FrameOverflow, dry_run: bool) -> str | None:
    """Grow a ``SHAPE_TO_FIT_TEXT`` shape to its text, as a renderer would."""
    d_left, d_top, d_width, d_height = _auto_size_growth(
        overflow.measure, overflow.over_w, overflow.over_h
    )
    if not d_width and not d_height:
        return None
    scale_x, scale_y = _group_scale(overflow.target.tx_body.getparent())
    left, top = int(shape.left or 0), int(shape.top or 0)
    width, height = int(shape.width or 0), int(shape.height or 0)
    new_width = width + math.ceil(d_width / scale_x)
    new_height = height + math.ceil(d_height / scale_y)
    if not dry_run:
        shape.left = Emu(left + math.floor(d_left / scale_x))
        shape.top = Emu(top + math.floor(d_top / scale_y))
        shape.width = Emu(new_width)
        shape.height = Emu(new_height)
    return (
        f"Resized '{shape.name}' to fit its text: size ({width},{height}) → "
        f"({new_width},{new_height})."
    )


def _largest_fitting_pct(env: _TextEnv, target: _TextTarget) -> int | None:
    """Largest whole percentage of its font sizes at which `target`'s text fits.

    ``None`` when even ``_MIN_BAKE_PCT`` is too large.
    """
    low, high = _MIN_BAKE_PCT, 99
    if not _fits_scaled(env, target, low / 100.0, 0.0):
        return None
    while low < high:
        middle = (low + high + 1) // 2
        if _fits_scaled(env, target, middle / 100.0, 0.0):
            low = middle
        else:
            high = middle - 1
    return low


def _reduce_font_sizes(
    env: _TextEnv, shape: BaseShape, overflow: _FrameOverflow, dry_run: bool
) -> str | None:
    """Scale the font sizes of a frame set to no auto-fit down until its text fits."""
    target = overflow.target
    pct = _largest_fitting_pct(env, target)
    if pct is None:
        return None
    # Round each size down to a half point, never up: the text must fit.
    planned = [
        (element, is_end, size * pct // 100 // 50 * 50)
        for element, is_end, size in _iter_sized_elements(env, target)
    ]
    if any(size < 100 for _, _, size in planned):
        return None
    if not dry_run:
        for element, is_end, size in planned:
            rpr = element.get_or_add_endParaRPr() if is_end else element.get_or_add_rPr()
            rpr.set("sz", str(size))
    return (
        f"Reduced the font sizes in '{shape.name}' to {pct}% so the text fits its "
        f"frame ({_describe_overflow(overflow.over_w, overflow.measure)})."
    )


def _fitting_autofit_step(
    env: _TextEnv, target: _TextTarget, font_scale: float
) -> tuple[float, float] | None:
    """The first of PowerPoint's shrink steps below `font_scale` at which the text fits."""
    for scale, reduction in _AUTOFIT_STEPS:
        if scale < font_scale and _fits_scaled(env, target, scale, reduction):
            return scale, reduction
    return None


def _store_font_scale(
    env: _TextEnv, shape: BaseShape, overflow: _FrameOverflow, dry_run: bool
) -> str | None:
    """Set the frame to shrink its text, storing the font scale that makes it fit."""
    target, measure = overflow.target, overflow.measure
    step = _fitting_autofit_step(env, target, measure.body.font_scale)
    if step is None:
        return None
    body_pr = target.tx_body.find(_T_BODYPR)
    if body_pr is None:
        return None
    scale, reduction = step
    if not dry_run:
        body_pr.autofit = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        norm = body_pr.find(_T_NORMAUTOFIT)
        norm.set("fontScale", str(round(scale * 100000)))
        norm.set("lnSpcReduction", str(round(reduction * 100000)))
    return (
        f"Set '{shape.name}' text frame auto_size = TEXT_TO_FIT_SHAPE with a "
        f"{scale * 100:g}% font scale ({_describe_overflow(overflow.over_w, measure)})."
    )


def _scales_as_a_whole(shape: BaseShape) -> bool:
    """True for shapes whose width and height must change together.

    Shrinking one axis of a picture distorts the image, and of a group
    squashes every shape inside it.
    """
    try:
        tag = shape._element.tag  # pyright: ignore[reportPrivateUsage]
    except Exception:
        return False
    return tag in (_P + "pic", _P + "grpSp")


def _fix_off_slide(
    env: _TextEnv,
    shape: BaseShape,
    slide_w: Length | None,
    slide_h: Length | None,
    dry_run: bool,
) -> str | None:
    """Clamp `shape` on-slide; return a description, or ``None`` if nothing changes.

    Works from the area the shape covers when rendered — rotated, and grown
    to its text when it resizes to fit — and moves its stored frame so that
    area lands on the slide.  A shape larger than the slide is shrunk first:
    a picture or group proportionally, anything else along the axis that is
    too long.
    """
    old = _Frame(
        int(shape.left or 0), int(shape.top or 0), int(shape.width or 0), int(shape.height or 0)
    )
    if old.width < 0 or old.height < 0:
        return None  # InvalidGeometry: there is no area to place
    area = _RenderedArea(_shape_rotation(shape), _analyse_text(env, shape).growth)
    sw = None if slide_w is None else int(slide_w)
    sh = None if slide_h is None else int(slide_h)
    # First clamp size: a shape larger than the slide can never be fully
    # on-slide just by translation, so shrink to fit before deciding where
    # to put it.
    sized = _shrunk_to_slide(shape, area, old, sw, sh)
    e_left, e_top, e_right, e_bottom = area.extent(sized)
    new = sized._replace(
        left=old.left + _shift_into(e_left, e_right, sw),
        top=old.top + _shift_into(e_top, e_bottom, sh),
    )
    if new == old:
        return None
    if not dry_run:
        _move_and_resize(shape, old, new)
    return _describe_clamp(shape.name, old, new)


class _Frame(NamedTuple):
    """A shape's stored position and size, in EMU."""

    left: int
    top: int
    width: int
    height: int


class _RenderedArea(NamedTuple):
    """What turns a shape's stored frame into the area it covers when rendered."""

    rotation: float
    growth: tuple[float, float, float, float]  # see :attr:`_TextFinding.growth`

    def extent(self, frame: _Frame) -> tuple[int, int, int, int]:
        """``(left, top, right, bottom)`` of the area `frame` covers when rendered."""
        g_left, g_top, g_width, g_height = self.growth
        grown = (
            frame.left + g_left,
            frame.top + g_top,
            frame.left + g_left + frame.width + g_width,
            frame.top + g_top + frame.height + g_height,
        )
        return _rotated_extent(grown, self.rotation)


def _shrunk_to_slide(
    shape: BaseShape, area: _RenderedArea, frame: _Frame, sw: int | None, sh: int | None
) -> _Frame:
    """`frame` made small enough that its rendered area fits a `sw` × `sh` slide.

    A picture or group, or any shape not turned by a multiple of 90°, is
    scaled as a whole; anything else is shortened along the axis that is too
    long.
    """
    e_left, e_top, e_right, e_bottom = area.extent(frame)
    too_wide = sw is not None and e_right - e_left > sw
    too_tall = sh is not None and e_bottom - e_top > sh
    if not (too_wide or too_tall):
        return frame
    quarter_turns = round(area.rotation / 90.0)
    axis_aligned = abs(area.rotation - 90.0 * quarter_turns) < 1e-6
    if _scales_as_a_whole(shape) or not axis_aligned:
        factor = _fit_factor((e_left, e_top, e_right, e_bottom), sw, sh)
        return frame._replace(
            width=math.floor(frame.width * factor), height=math.floor(frame.height * factor)
        )
    # A quarter turn swaps which stored extent lies along each axis.
    limit_w, limit_h = (sh, sw) if quarter_turns % 2 else (sw, sh)
    return frame._replace(
        width=_capped(frame.width, limit_w), height=_capped(frame.height, limit_h)
    )


def _fit_factor(extent: tuple[int, int, int, int], sw: int | None, sh: int | None) -> float:
    """Largest scale, at most 1, at which `extent` fits a `sw` × `sh` slide."""
    e_left, e_top, e_right, e_bottom = extent
    factor = 1.0
    if sw is not None and e_right > e_left:
        factor = min(factor, sw / (e_right - e_left))
    if sh is not None and e_bottom > e_top:
        factor = min(factor, sh / (e_bottom - e_top))
    return factor


def _capped(value: int, limit: int | None) -> int:
    return limit if limit is not None and value > limit else value


def _shift_into(low: int, high: int, limit: int | None) -> int:
    """Move needed to bring ``[low, high]`` inside ``[0, limit]``."""
    if low < 0:
        return -low
    if limit is not None and high > limit:
        return max(-low, limit - high)
    return 0


def _move_and_resize(shape: BaseShape, old: _Frame, new: _Frame) -> None:
    """Give `shape`, stored at `old`, the frame `new`; an unchanged extent is not rewritten."""
    shape.left = Emu(new.left)
    shape.top = Emu(new.top)
    if new.width != old.width:
        shape.width = Emu(new.width)
    if new.height != old.height:
        shape.height = Emu(new.height)


def _describe_clamp(name: str, old: _Frame, new: _Frame) -> str:
    parts = []
    if (new.left, new.top) != (old.left, old.top):
        parts.append(f"position ({old.left},{old.top}) → ({new.left},{new.top})")
    if (new.width, new.height) != (old.width, old.height):
        parts.append(f"size ({old.width},{old.height}) → ({new.width},{new.height})")
    return f"Clamped '{name}' on-slide: " + "; ".join(parts) + "."


def _fix_table_row(env: _TextEnv, shape: BaseShape, row_idx: int, dry_run: bool) -> str | None:
    """Grow row `row_idx` of the table in `shape` to the height its text needs."""
    for index, row_h, needed, _col_idx, measure in _table_row_needs(env, shape):
        if index != row_idx:
            continue
        if needed - row_h <= measure.lines * _LINE_TOLERANCE_EMU:
            return None
        new_h = math.ceil(needed)
        if not dry_run:
            shape.table.rows[row_idx].height = Emu(new_h)  # type: ignore[attr-defined]
        return f"Grew row {row_idx} of '{shape.name}' from {row_h} to {new_h} EMU to fit its text."
    return None


class _AutoFixer:
    """Applies :meth:`SlideLintReport.auto_fix`'s fixes one issue at a time.

    Collects a description of each fix in `fixes`.  A shape is moved at most
    once per pass: one shape can be off two edges (left and right) at once,
    and with three or more layers restacks interact, so re-linting after a
    pass gives a truer picture than stacking speculative moves.
    """

    def __init__(self, slide: Slide, *, dry_run: bool, fix_grid_drift: bool):
        self._slide_w, self._slide_h = _slide_dimensions(slide)
        self._env = _TextEnv(slide)
        self._dry_run = dry_run
        self._fix_grid_drift = fix_grid_drift
        self._clamped: set[int] = set()
        self._restacked: set[int] = set()
        self.fixes: list[str] = []

    def fix_text(self, issue: TextOverflow) -> None:
        """Make the text `issue` reports fit; see :func:`_fix_text_overflow`."""
        self._record(_fix_text_overflow(self._env, issue, self._dry_run))

    def fix_geometry(self, issue: LintIssue) -> None:
        """Fix `issue` when it is an off-slide shape, a layer-order or a grid-drift issue."""
        if isinstance(issue, OffSlide):
            self._record(self._clamp(issue))
        elif isinstance(issue, LayerOrderViolation):
            self._record(self._restack(issue))
        elif isinstance(issue, OffGridDrift) and self._fix_grid_drift:
            self._record(self._snap(issue))

    def _record(self, fix: str | None) -> None:
        if fix is not None:
            self.fixes.append(fix)

    def _clamp(self, issue: OffSlide) -> str | None:
        shape = issue.shapes[0]
        key = id(shape._element)  # pyright: ignore[reportPrivateUsage]
        if key in self._clamped:
            return None
        fix = _fix_off_slide(self._env, shape, self._slide_w, self._slide_h, self._dry_run)
        if fix is not None:
            self._clamped.add(key)
        return fix

    def _restack(self, issue: LayerOrderViolation) -> str | None:
        """Move the shape that declared ``layer_above`` to just after the layer it named."""
        above, below = issue.shapes[0], issue.shapes[1]
        above_el = above._element  # pyright: ignore[reportPrivateUsage]
        below_el = below._element  # pyright: ignore[reportPrivateUsage]
        # Only siblings are restacked: a pair across containers (one inside a
        # group) has no single ordering to fix and is left for the author.
        if above_el.getparent() is not below_el.getparent() or id(above_el) in self._restacked:
            return None
        # Recorded before the dry_run gate, so a preview reports exactly the
        # fixes a real run would apply.
        self._restacked.add(id(above_el))
        fix = (
            f"Restacked '{above.name}' above '{below.name}' to honour "
            f"layer_above={issue.layer!r}."
        )
        if not self._dry_run:
            # ``addnext`` moves the element rather than copying it, so this
            # is a reorder, not a duplication.
            below_el.addnext(above_el)
        return fix

    def _snap(self, issue: OffGridDrift) -> str | None:
        """Move the drifted left or top edge of a shape onto the grid line."""
        shape, axis = issue.shapes[0], issue.axis
        if axis not in ("left", "top"):
            return None
        old, new = int(getattr(shape, axis)), issue.grid_emu
        fix = f"Snapped '{shape.name}' {axis} edge from {old} to {new} EMU (grid)."
        if not self._dry_run:
            setattr(shape, axis, Emu(new))
        return fix


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
_PP_LINTALLOW = "{%s}lintAllow" % _LINT_NS
_PP_LINTLAYER = "{%s}lintLayer" % _LINT_NS

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
    """Store ``lint_group = value`` on *cNvPr* using ``a:extLst/a:ext``.

    Any legacy-format attribute is dropped by :func:`_get_or_add_lint_ext`
    and then overwritten here, so the new format is canonical.
    """
    from lxml import etree

    ext = _get_or_add_lint_ext(cNvPr)
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
    return _lint_group_of(shape, _shape_cNvPr(shape))


def _lint_group_of(shape: BaseShape, cNvPr) -> str | None:
    """:func:`_shape_lint_group` for a caller that already holds *cNvPr*."""
    if cNvPr is not None:
        explicit = _read_lint_group(cNvPr)
        if explicit is not None:
            # Empty-string explicit tag opts the shape *out* of any
            # implicit name-prefix group.
            return explicit or None
        name = cNvPr.get("name")
    else:
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

    # ``_get_or_add_lint_ext`` drops the pre-2.1.1 legacy attribute —
    # the schema-invalid XML PowerPoint "repairs and removes" on open —
    # and migrates its value so writing ``lint_skip`` never costs the
    # caller their group tag.
    ext = _get_or_add_lint_ext(cNvPr)

    node = ext.find(_PP_LINTSKIP)
    if not codes:
        # Empty assignment clears the node entirely, then drops the
        # ext / extLst if nothing else lives in them.
        if node is not None:
            ext.remove(node)
        _prune_lint_ext(cNvPr, ext, cNvPr.find(_A_EXTLST))
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


def _shape_id(shape: BaseShape) -> int | None:
    """Return the ``cNvPr/@id`` of *shape*, or ``None`` if unavailable.

    Shape ids are unique within a slide and are what the pairwise
    overlap allowances below are keyed on — unlike ``shape.name`` they
    are guaranteed unique, and unlike ``id(shape)`` they survive a
    save/open round trip.
    """
    cNvPr = _shape_cNvPr(shape)
    if cNvPr is None:
        return None
    raw = cNvPr.get("id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _shape_cNvPr(shape: BaseShape):
    """Return the shape's ``cNvPr`` element, or ``None`` if it has none."""
    try:
        return shape._element._nvXxPr.cNvPr  # pyright: ignore[reportPrivateUsage]
    except AttributeError:
        return None


def _prune_lint_ext(cNvPr, ext, extLst) -> None:
    """Drop *ext* / *extLst* once they hold no lint metadata.

    Keeps the emitted XML minimal, so clearing the last lint setting on
    a shape leaves no residue behind.
    """
    if len(ext) == 0:
        extLst.remove(ext)
    if len(extLst) == 0:
        cNvPr.remove(extLst)


def _get_or_add_lint_ext(cNvPr):
    """Return the lint ``<a:ext>`` for *cNvPr*, creating it if absent.

    Touching the ext also *migrates* any pre-2.1.1 legacy ``lint_group``
    attribute into the canonical ``<pp:lintGroup>`` node.  The legacy
    attribute is schema-invalid and has to go, but dropping it outright
    would mean that writing an unrelated field — a layer name, an
    overlap allowance, even a documented-no-op ``lint_skip = set()`` —
    silently erased a group tag the caller never mentioned.
    """
    from lxml import etree

    legacy = cNvPr.get(_LEGACY_LINT_GROUP_ATTR)
    if _LEGACY_LINT_GROUP_ATTR in cNvPr.attrib:
        del cNvPr.attrib[_LEGACY_LINT_GROUP_ATTR]

    # Go through the oxml descriptor so cNvPr's child ordering
    # (hlinkClick -> hlinkHover -> extLst) is respected.
    extLst = cNvPr.get_or_add_extLst()
    ext = _find_lint_ext(cNvPr)
    if ext is None:
        ext = etree.SubElement(extLst, _A_EXT)
        ext.set("uri", _LINT_EXT_URI)

    # Carry the legacy value across, unless the canonical node already
    # exists (in which case it is authoritative and the attribute was
    # stale residue).
    if legacy and ext.find(_PP_LINTGROUP) is None:
        node = etree.SubElement(ext, _PP_LINTGROUP)
        node.set("name", legacy)
    return ext


def _read_lint_allow(cNvPr) -> frozenset[int]:
    """Return the set of shape ids *cNvPr* is allowed to overlap."""
    ext = _find_lint_ext(cNvPr)
    if ext is None:
        return frozenset()
    node = ext.find(_PP_LINTALLOW)
    if node is None:
        return frozenset()
    ids: set[int] = set()
    for token in (node.get("ids") or "").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            ids.add(int(token))
        except ValueError:
            # Ignore junk rather than failing the whole lint run — the
            # value may have been hand-edited or written by a future
            # release using a wider id syntax.
            continue
    return frozenset(ids)


def _write_lint_allow(cNvPr, ids) -> None:
    """Store the pairwise overlap allowance set *ids* on *cNvPr*."""
    from lxml import etree

    ext = _get_or_add_lint_ext(cNvPr)
    node = ext.find(_PP_LINTALLOW)
    if not ids:
        if node is not None:
            ext.remove(node)
        _prune_lint_ext(cNvPr, ext, cNvPr.find(_A_EXTLST))
        return
    if node is None:
        node = etree.SubElement(ext, _PP_LINTALLOW)
    # Sorted + comma-joined for stable round-trip diffs.
    node.set("ids", ",".join(str(i) for i in sorted(ids)))


def _shape_lint_allow(shape: BaseShape) -> frozenset[int]:
    """Return the shape ids *shape* has been cleared to overlap."""
    cNvPr = _shape_cNvPr(shape)
    if cNvPr is None:
        return frozenset()
    return _read_lint_allow(cNvPr)


def _read_lint_layer(cNvPr) -> tuple[str | None, str | None]:
    """Return ``(layer, layer_above)`` declared on *cNvPr*."""
    ext = _find_lint_ext(cNvPr)
    if ext is None:
        return None, None
    node = ext.find(_PP_LINTLAYER)
    if node is None:
        return None, None
    return node.get("name"), node.get("above")


def _write_lint_layer(cNvPr, *, name: str | None, above: str | None) -> None:
    """Store the layer declaration ``(name, above)`` on *cNvPr*.

    Passing ``None`` for both clears the declaration entirely.
    """
    from lxml import etree

    ext = _get_or_add_lint_ext(cNvPr)
    node = ext.find(_PP_LINTLAYER)
    if name is None and above is None:
        if node is not None:
            ext.remove(node)
        _prune_lint_ext(cNvPr, ext, cNvPr.find(_A_EXTLST))
        return
    if node is None:
        node = etree.SubElement(ext, _PP_LINTLAYER)
    for attr, value in (("name", name), ("above", above)):
        if value is None:
            node.attrib.pop(attr, None)
        else:
            node.set(attr, value)


def _shape_lint_layer(shape: BaseShape) -> tuple[str | None, str | None]:
    """Return ``(layer, layer_above)`` for *shape*."""
    cNvPr = _shape_cNvPr(shape)
    if cNvPr is None:
        return None, None
    return _read_lint_layer(cNvPr)


def _overlap_allowed(a: _ShapeInfo, b: _ShapeInfo) -> bool:
    """Return True if either shape has cleared the other to overlap it.

    The relationship is declared one-sided but read symmetrically: it
    takes only one of the pair to say "this overlap is deliberate" for
    the collision to be suppressed, matching how a designer thinks
    about it ("the badge is allowed to sit on the card") without
    forcing them to tag both ends.
    """
    if a.allow and b.shape_id is not None and b.shape_id in a.allow:
        return True
    return bool(b.allow) and a.shape_id is not None and a.shape_id in b.allow


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


def _layers_consistent(
    lower: tuple[str | None, str | None],
    upper: tuple[str | None, str | None],
) -> bool:
    """Return True if a pair declares a *satisfied* layer relationship.

    Both arguments are ``(layer, layer_above)`` pairs.  *lower* is the
    shape painted first and *upper* the one painted over it, so callers
    must pass them in ``spTree`` order.  The relationship holds when the
    shape that is actually on top is the one that claimed to be: *upper*
    declares ``layer_above`` naming *lower*'s ``layer``.

    The mirror case — the shape claiming to sit above is drawn
    underneath — is deliberately *not* handled here.  That is the
    violation, and :func:`_check_layer_order` reports it.
    """
    lower_name, _ = lower
    _, upper_above = upper
    return bool(lower_name) and upper_above == lower_name


def _check_layer_order(
    infos: Sequence[_ShapeInfo],
    pairs: Sequence[tuple[int, int]],
    use_bleed: bool = False,
) -> list[LintIssue]:
    """Return LayerOrderViolation issues for contradicted layer hints.

    A shape that declares ``layer_above = "card"`` asserts it is painted
    on top of every shape whose ``layer`` is ``"card"`` that it overlaps.
    When the shape tree says otherwise — the declaring shape comes
    *earlier* in ``spTree`` and is therefore drawn underneath — the
    declaration and the drawing order contradict each other.  The
    declaration is taken as the author's intent, so the z-order is
    reported as the bug.

    Only overlapping pairs are considered: a layer declaration between
    shapes that never touch is inert, not wrong.  *pairs* are the
    overlapping index pairs from :func:`_overlapping_pairs`.
    """
    # Nothing declared anywhere — nothing to contradict.
    if not any(name or above for name, above in (info.layer for info in infos)):
        return []

    issues: list[LintIssue] = []
    for i, j in pairs:
        lower, upper = infos[i], infos[j]
        above_i = lower.layer[1]
        if not above_i or upper.layer[0] != above_i:
            continue
        # ``i`` claims to sit above layer ``name_j``, but ``j`` is
        # painted later and therefore covers it.
        _area, pct = _bbox_overlap(lower.checked_box(use_bleed), upper.checked_box(use_bleed))
        if pct < _COLLISION_THRESHOLD:
            continue
        issues.append(LayerOrderViolation(lower.shape, upper.shape, above_i))
    return issues


def _check_collisions(
    infos: Sequence[_ShapeInfo],
    pairs: Sequence[tuple[int, int]],
    use_bleed: bool = False,
) -> list[LintIssue]:
    """Return ShapeCollision issues for pairs of overlapping shapes.

    *pairs* are the overlapping index pairs from :func:`_overlapping_pairs`,
    so shapes that do not touch are never looked at.

    Shapes sharing a non-empty ``lint_group`` are treated as intentionally
    layered and never produce a collision warning — group suppression
    runs *before* scoring, since a tagged group is "intentional" by
    definition.  Shapes with no group, or shapes in different groups,
    continue through to scoring + classification.

    Two further intent declarations suppress a collision, both checked
    before scoring for the same reason:

    * **Pairwise** — either shape has cleared the other via
      ``shape_a.allow_overlap_with(shape_b)``.  Narrower than a
      ``lint_group``: it licenses exactly one pair rather than a whole
      tagged set.
    * **Layer hints** — the shapes declare a consistent
      ``layer`` / ``layer_above`` relationship (see
      :func:`_check_layer_order`, which reports the *inconsistent* case
      as a :class:`LayerOrderViolation` error).

    With *use_bleed* each box is widened by its shadow blur radius, and
    collisions that would *not* fire on the raw boxes are emitted as the
    ``ShapeCollisionShadow`` subclass so callers can opt them out
    separately via ``lint_skip``.
    """
    issues: list[LintIssue] = []

    for i, j in pairs:
        a, b = infos[i], infos[j]
        # Declared intent is honoured *before* scoring.
        if _overlap_declared(a, b):
            continue

        box_i, box_j = a.checked_box(use_bleed), b.checked_box(use_bleed)
        area, pct = _bbox_overlap(box_i, box_j)
        if pct < _COLLISION_THRESHOLD:
            continue

        # A connector is a line: overlapping its bounding box means nothing
        # unless the line itself runs into the other shape.
        if _connector_misses(a, b):
            continue

        # j is drawn after i: a smaller shape inside it is on top of it.  A
        # line is not a backing card.
        if a.path is None and _sits_on_its_card(box_i, box_j):
            continue

        kind, score = _classify_collision(box_i, box_j, pct)
        issues.append(
            _collision_class(a, b, use_bleed)(
                a.shape,
                b.shape,
                intersection_area=area,
                intersection_pct=pct,
                groups=(a.group, b.group),
                score=score,
                kind=kind,
            )
        )

    return issues


def _overlap_declared(a: _ShapeInfo, b: _ShapeInfo) -> bool:
    """True when the author has said the two shapes may overlap.

    A shared ``lint_group`` (a tagged group is intentional by definition), an
    ``allow_overlap_with`` allowance (one side naming the other is enough), or
    a ``layer`` / ``layer_above`` relationship the drawing order agrees with.
    A layer relationship it contradicts is *not* intent: that surfaces as a
    :class:`LayerOrderViolation` from :func:`_check_layer_order`.
    """
    if a.group is not None and a.group == b.group:
        return True
    return _overlap_allowed(a, b) or _layers_consistent(a.layer, b.layer)


def _connector_misses(a: _ShapeInfo, b: _ShapeInfo) -> bool:
    """True when either shape is a connector whose line does not touch the other."""
    return (a.path is not None or b.path is not None) and not _paths_meet(a, b)


def _box_area(box: tuple[int, int, int, int]) -> int:
    left, top, right, bottom = box
    return max(1, (right - left) * (bottom - top))


def _sits_on_its_card(below: tuple[int, int, int, int], above: tuple[int, int, int, int]) -> bool:
    """True for a small shape drawn on top of the larger backing card it lies within.

    Badge-on-card, eyebrow-on-rectangle, accent-bar-on-card: the canonical
    layered design (see IMPROVEMENT_PLAN.md item 12).  The smaller shape must
    be *strictly* contained (size ratio < 0.9 — equal boxes are still
    classified as ``matched`` so callers can audit them) and drawn later.
    A smaller shape *beneath* the card is hidden, so that remains a collision.
    """
    area_below, area_above = _box_area(below), _box_area(above)
    size_ratio = min(area_below, area_above) / max(area_below, area_above)
    return size_ratio < 0.9 and _bbox_contains(below, above) and area_above < area_below


def _collision_class(a: _ShapeInfo, b: _ShapeInfo, use_bleed: bool) -> type[ShapeCollision]:
    """:class:`ShapeCollisionShadow` when only the shadow bleed makes the pair collide."""
    if use_bleed:
        _, raw_pct = _bbox_overlap(a.box, b.box)
        if raw_pct < _COLLISION_THRESHOLD:
            return ShapeCollisionShadow
    return ShapeCollision


# ---------------------------------------------------------------------------
# Min font size — flag any run below the legibility threshold (default 9pt).
# ---------------------------------------------------------------------------

_DEFAULT_MIN_FONT_PT = 9.0
_PT_TO_EMU = 12700


def _check_min_font_size(
    shape: BaseShape, threshold_pt: float = _DEFAULT_MIN_FONT_PT
) -> list[LintIssue]:
    """Return a single MinFontSize issue if any run is below *threshold_pt*.

    Only sizes set on a run are considered, scaled by the font scale stored
    on a ``TEXT_TO_FIT_SHAPE`` frame: a frame shrunk to 50% shows an 18pt run
    at 9pt.  The runs are read from the XML: ``shape.text_frame`` would add a
    ``<p:txBody>`` to a shape without one.
    """
    tx_body = _shape_tx_body(shape)
    smallest = None if tx_body is None else _smallest_run_size(tx_body)
    if smallest is None:
        return []
    pt = smallest / 100.0 * _stored_font_scale(tx_body)
    if pt < threshold_pt:
        return [MinFontSize(shape, pt, threshold_pt)]
    return []


def _shape_tx_body(shape: BaseShape):
    """`shape`'s ``<p:txBody>``, or ``None``; read off the element, adding none."""
    try:
        if not shape.has_text_frame:
            return None
        return shape._element.txBody  # pyright: ignore[reportPrivateUsage]
    except Exception:
        return None


def _smallest_run_size(tx_body) -> int | None:
    """The smallest font size set on a run of `tx_body`, in 1/100 pt."""
    sizes: list[int] = []
    for run in tx_body.iter(_T_R):
        rpr = run.find(_T_RPR)
        size = None if rpr is None else _int_attr(rpr, "sz")
        if size is not None and size > 0:
            sizes.append(size)
    return min(sizes, default=None)


def _stored_font_scale(tx_body) -> float:
    """The font scale a ``TEXT_TO_FIT_SHAPE`` frame stores, 1.0 when it stores none."""
    body_pr = tx_body.find(_T_BODYPR)
    norm = None if body_pr is None else body_pr.find(_T_NORMAUTOFIT)
    return 1.0 if norm is None else (_fraction(norm.get("fontScale")) or 1.0)


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

    Greedy single-pass clustering over the sorted values.  A cluster spans at
    most *tol* from its first member: chaining each value to the previous one
    instead would let a staircase of edges a little apart (the tops of bars in
    a native bar chart) merge into one wide "grid line" whose mean sits
    between them.
    """
    if not values:
        return []
    sorted_v = sorted(values)
    clusters: list[list[int]] = [[sorted_v[0]]]
    for v in sorted_v[1:]:
        if v - clusters[-1][0] <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    # ``+ 0.5`` is round-half-up for the always-non-negative cluster centers;
    # behaves identically to ``round()`` here but avoids any banker's-rounding
    # edge case at exact half-EMU boundaries.
    return [(int(sum(c) / len(c) + 0.5), len(c)) for c in clusters]


def _grid_lines(edges: Sequence[int]) -> list[int]:
    """Grid lines: clusters of at least ``_GRID_MIN_CLUSTER`` coinciding edges."""
    clusters = _cluster_edges(list(edges), _GRID_TIGHT_TOLERANCE_EMU)
    return [center for center, n in clusters if n >= _GRID_MIN_CLUSTER]


def _on_grid(edge: int, grid_lines: Sequence[int]) -> bool:
    return any(abs(edge - g) <= _GRID_TIGHT_TOLERANCE_EMU for g in grid_lines)


def _check_off_grid_drift(infos: Sequence[_ShapeInfo]) -> list[LintIssue]:
    """Return OffGridDrift issues for shapes whose edges are slightly off a grid.

    Only the left and top edges are snapped, but a shape whose opposite edge
    (right or bottom) already sits on a grid line is aligned there on purpose
    — bars sharing a baseline, labels right-aligned to a column — and is left
    alone.  Rotated shapes, whose stored edges are not the edges a viewer
    sees, take no part.
    """
    issues: list[LintIssue] = []
    # Alignment is about where shapes were placed, so the stored frame.
    placed = [
        info
        for info in infos
        if not info.malformed and info.rotation in (0.0, 180.0)
    ]
    if len(placed) < _GRID_MIN_CLUSTER + 1:
        return issues

    for axis_name, edge_idx, opposite_idx in (("left", 0, 2), ("top", 1, 3)):
        issues.extend(_axis_drift(placed, axis_name, edge_idx, opposite_idx))
    return issues


def _axis_drift(
    placed: Sequence[_ShapeInfo], axis_name: str, edge_idx: int, opposite_idx: int
) -> list[LintIssue]:
    """OffGridDrift issues for the edge `edge_idx` of each frame (0 left, 1 top)."""
    edges = [info.frame[edge_idx] for info in placed]
    grid_lines = _grid_lines(edges)
    if not grid_lines:
        return []
    opposite_lines = _grid_lines([info.frame[opposite_idx] for info in placed])
    issues: list[LintIssue] = []
    for info, edge in zip(placed, edges):
        # Skip shapes that already sit on a grid line, by either edge.
        if _on_grid(edge, grid_lines) or _on_grid(info.frame[opposite_idx], opposite_lines):
            continue
        # Find the closest grid line; if it's within the loose tolerance,
        # this is drift.
        closest = min(grid_lines, key=lambda g: abs(edge - g))
        drift = abs(edge - closest)
        if _GRID_TIGHT_TOLERANCE_EMU < drift <= _GRID_LOOSE_TOLERANCE_EMU:
            issues.append(OffGridDrift(info.shape, axis_name, drift, closest))
    return issues


# ---------------------------------------------------------------------------
# Low contrast — compare text RGB against its visible fill or the nearest
# enclosing card behind it, then the slide background (WCAG AA, 4.5:1).
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


def _fill_backdrop(shape: BaseShape) -> tuple[str, Any]:
    """Classify how *shape*'s fill paints over what lies beneath it.

    Returns ``(kind, rgb)``; see :attr:`_ShapeInfo.backdrop` for the kinds.
    """
    from power_pptx.enum.dml import MSO_FILL_TYPE

    try:
        fill = shape.fill  # type: ignore[attr-defined]
        fill_type = fill.type
        if fill_type in (None, MSO_FILL_TYPE.BACKGROUND):
            return ("clear", None)
        if fill_type == MSO_FILL_TYPE.SOLID:
            alpha = fill.fore_color.alpha
            if alpha == 0.0:
                return ("clear", None)
            if alpha == 1.0:
                return ("opaque", _resolve_solid_rgb(fill))
    except (AttributeError, NotImplementedError):
        pass
    return ("unknown", None)


class _Backdrops:
    """Resolves the opaque colour painted behind each shape's text.

    Text boxes commonly have no fill of their own. Looking straight through
    their containing card to the slide background produces false contrast
    warnings (and misses dark text on dark cards). Respect painting order.
    Skip ambiguous gradients, translucent fills, pictures, and partial covers
    rather than claiming a contrast ratio for a background we cannot resolve.

    Built once per slide: each shape's fill is classified at most once and
    only shapes that actually overlap the text are consulted, so resolving
    every text shape on a busy slide stays cheap.  The accessibility audit
    uses the same resolver, so the two never disagree about a backdrop.
    """

    def __init__(
        self,
        slide: Slide,
        infos: Sequence[_ShapeInfo] | None = None,
        pairs: Sequence[tuple[int, int]] | None = None,
    ):
        if infos is None:
            infos = [_ShapeInfo(shape) for shape in slide.shapes]
        if pairs is None:
            pairs = _overlapping_pairs([info.box for info in infos])
        self._slide = slide
        self._infos = infos
        self._slide_rgb: Any = _UNSET
        # index of each shape, and the indexes of the shapes painted beneath it
        self._index = {
            id(info.shape._element): n  # pyright: ignore[reportPrivateUsage]
            for n, info in enumerate(infos)
        }
        self._beneath: dict[int, list[int]] = {}
        for i, j in pairs:
            self._beneath.setdefault(j, []).append(i)

    def slide_rgb(self):
        """RGB of the slide's own solid background, or ``None``."""
        if self._slide_rgb is _UNSET:
            self._slide_rgb = _slide_background_rgb(self._slide)
        return self._slide_rgb

    def rgb_behind(self, shape: BaseShape):
        """Return the RGB behind *shape*'s text, or ``None`` if unresolvable."""
        index = self._index.get(id(shape._element))  # pyright: ignore[reportPrivateUsage]
        kind, rgb = _fill_backdrop(shape) if index is None else self._infos[index].backdrop
        if kind == "opaque":
            return rgb
        if kind != "clear":
            return None
        if index is None:
            # A shape inside a group: what the group is painted over is not
            # modelled, so only the slide background can be offered.
            return self.slide_rgb()
        bounds = self._infos[index].box
        for k in reversed(self._beneath.get(index, ())):  # nearest beneath first
            other = self._infos[k]
            box = other.box
            if bounds[0] >= box[2] or box[0] >= bounds[2]:
                continue
            if bounds[1] >= box[3] or box[1] >= bounds[3]:
                continue
            kind, rgb = other.backdrop
            if kind == "clear":
                continue
            if kind == "opaque" and _bbox_contains(box, bounds) and not _is_rotated(other.shape):
                return rgb
            return None
        return self.slide_rgb()


def _is_rotated(shape: BaseShape) -> bool:
    try:
        return bool(shape.rotation)
    except Exception:
        return False


def _first_run_rgb(tx_body):
    """Return the first explicit RGB font colour in *tx_body*, or ``None``.

    Reads ``<a:rPr>`` where it exists: ``run.font`` would add an empty one to
    every run that has none.
    """
    from power_pptx.text.text import Font

    for run in tx_body.iter(_T_R):
        rpr = run.find(_T_RPR)
        if rpr is None:
            continue
        try:
            rgb = Font(rpr).color.rgb
        except (AttributeError, ValueError):
            rgb = None
        if rgb is not None:
            return rgb
    return None


def _text_background_rgb(shape: BaseShape, slide: Slide):
    """Resolve the opaque RGB behind *shape*'s text; see :class:`_Backdrops`."""
    return _Backdrops(slide).rgb_behind(shape)


def _check_low_contrast(shape: BaseShape, backdrops: _Backdrops) -> list[LintIssue]:
    """Return a LowContrast issue if shape's text has poor contrast against its fill."""
    issues: list[LintIssue] = []
    try:
        if not shape.has_text_frame:
            return issues
        tx_body = shape._element.txBody  # pyright: ignore[reportPrivateUsage]
        if tx_body is None or not _has_visible_text(tx_body):
            return issues
        # Pick the first run's font color (best-effort).
        text_rgb = _first_run_rgb(tx_body)
    except Exception:
        return issues
    if text_rgb is None:
        return issues

    bg_rgb = backdrops.rgb_behind(shape)
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
    """Return ``True`` if *shape* has a solid, fully opaque fill.

    A translucent fill — a 35% black scrim over a photo — hides nothing.
    """
    return _fill_backdrop(shape)[0] == "opaque"


def _check_z_order_anomalies(
    infos: Sequence[_ShapeInfo], pairs: Sequence[tuple[int, int]]
) -> list[LintIssue]:
    """Find filled shapes drawn above shapes they visually contain.

    *pairs* are the overlapping index pairs from :func:`_overlapping_pairs`;
    a shape can only contain one it overlaps.  Only a fully opaque fill hides
    what is beneath it, and the same declarations that mark an overlap as
    intended for :class:`ShapeCollision` — a shared ``lint_group``, an
    ``allow_overlap_with`` allowance, or a consistent ``layer`` /
    ``layer_above`` pair — mark the stacking as intended too.
    """
    issues: list[LintIssue] = []
    # Document order = draw order; later shapes are drawn on top, so in each
    # pair ``j`` is the candidate "container" drawn above the earlier ``i``.
    for i, j in sorted(pairs, key=lambda pair: (pair[1], pair[0])):
        lower, upper = infos[i], infos[j]
        if lower.group is not None and lower.group == upper.group:
            continue
        if _overlap_allowed(lower, upper) or _layers_consistent(lower.layer, upper.layer):
            continue
        box_i, box_j = lower.box, upper.box
        if not _bbox_contains(box_j, box_i):
            continue
        # Tolerate identical bboxes — those are layered groups, not
        # anomalies; the drift case is when j strictly contains i.
        if box_j == box_i:
            continue
        if upper.backdrop[0] != "opaque":
            continue
        issues.append(ZOrderAnomaly(container=upper.shape, contained=lower.shape))
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
            left, top, right, bottom = _shape_bbox(ph)
            if right - left <= 0 or bottom - top <= 0:
                continue
            out.append((left, top, right, bottom, idx))
    except Exception:
        return out
    return out


def _check_master_placeholder_collision(
    slide: Slide, infos: Sequence[_ShapeInfo]
) -> list[LintIssue]:
    """Find shapes whose bbox lines up with an unused layout placeholder."""
    issues: list[LintIssue] = []
    ph_bboxes = _placeholder_bboxes(slide)
    if not ph_bboxes:
        return issues
    for info in infos:
        shape = info.shape
        if shape.is_placeholder:
            continue
        sl, st, sr, sb = info.stored_box
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


# ---------------------------------------------------------------------------
# Ragged edge — side-by-side panels that should end on one bottom line, but
# one stops short with empty space underneath it.
# ---------------------------------------------------------------------------

#: How far above the lowest panel bottom a panel may end before it is ragged.
_RAGGED_TOLERANCE_EMU = 19050  # 1.5pt

#: Shorter rounded shapes are badges, pills and tags, not peer panels.
_RAGGED_MIN_PANEL_HEIGHT_EMU = 457200  # 0.5"

#: Row neighbours sit side by side with at most this horizontal gap.
_RAGGED_MAX_ROW_GAP_EMU = 914400  # 1"

#: A row's columns start level: their top edges agree within this distance.
_RAGGED_TOP_TOLERANCE_EMU = 45720  # 0.05"


def _is_filled_panel(shape: BaseShape) -> bool:
    """True for a solid-filled rounded rectangle, the usual card backdrop."""
    try:
        from power_pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE

        if shape.shape_type != MSO_SHAPE_TYPE.AUTO_SHAPE:
            return False
        if shape.auto_shape_type != MSO_SHAPE.ROUNDED_RECTANGLE:  # type: ignore[attr-defined]
            return False
    except Exception:
        return False
    return _shape_has_opaque_fill(shape)


def _check_ragged_edges(infos: Sequence[_ShapeInfo]) -> list[LintIssue]:
    """Find panels whose bottom sits above the bottom edge of their own row.

    Only top-level panels (not nested inside another panel) at least 0.5" tall
    are compared, so badges and pills beside a card are not peers. A panel's
    row is the panels beside it, at most 1" away, whose tops are level with
    the top of the stack the panel ends. The panel is flagged when it ends more
    than 1.5pt above the lowest of those neighbours and no other shape starts in
    the gap between its bottom and that row bottom. Each row is judged on its
    own, so another row above or below does not hide a ragged one.
    """
    tol = _RAGGED_TOLERANCE_EMU
    boxes = [(info.shape, info.box) for info in infos]
    panels = [
        (s, b)
        for s, b in boxes
        if b[3] - b[1] >= _RAGGED_MIN_PANEL_HEIGHT_EMU and _is_filled_panel(s)
    ]
    top_level = [
        (s, b)
        for s, b in panels
        if not any(o is not s and o_b != b and _bbox_contains(o_b, b) for o, o_b in panels)
    ]
    issues: list[LintIssue] = []
    for shape, (left, top, right, bottom) in top_level:
        # The column this panel ends: panels stacked above it in its band.
        column_top = min(
            (
                o_top
                for _, (o_left, o_top, o_right, o_bottom) in top_level
                if o_left < right and o_right > left and o_bottom <= bottom + tol
            ),
            default=top,
        )
        row_bottoms = [
            n_bottom
            for other, (n_left, n_top, n_right, n_bottom) in top_level
            if other is not shape
            and 0 <= max(n_left - right, left - n_right) <= _RAGGED_MAX_ROW_GAP_EMU
            and abs(n_top - column_top) <= _RAGGED_TOP_TOLERANCE_EMU
        ]
        if not row_bottoms:
            continue
        row_bottom = max(row_bottoms)
        gap = row_bottom - bottom
        if gap <= tol:
            continue
        # Something placed in the gap (a caption, a button) fills the row.
        beneath = any(
            other is not shape
            and bottom - tol <= o_top < row_bottom
            and o_left < right
            and o_right > left
            for other, (o_left, o_top, o_right, _) in boxes
        )
        if not beneath:
            issues.append(RaggedEdge(shape, gap))
    return issues


_SEVERITY_ORDER = {LintSeverity.ERROR: 0, LintSeverity.WARNING: 1, LintSeverity.INFO: 2}

#: The most severe level each issue code can be reported at.  A rule none of
#: whose codes can reach the report — because they are disabled or fall below
#: ``min_severity`` — is not run at all.
_RULE_SEVERITY: dict[str, LintSeverity] = {
    "TextOverflow": LintSeverity.ERROR,
    "OffSlide": LintSeverity.ERROR,
    "OffSlideShadow": LintSeverity.ERROR,
    "ShapeCollision": LintSeverity.WARNING,
    "ShapeCollisionShadow": LintSeverity.WARNING,
    "MinFontSize": LintSeverity.WARNING,
    "OffGridDrift": LintSeverity.WARNING,
    "LowContrast": LintSeverity.WARNING,
    "ZOrderAnomaly": LintSeverity.WARNING,
    "MasterPlaceholderCollision": LintSeverity.WARNING,
    "LayerOrderViolation": LintSeverity.ERROR,
    "RaggedEdge": LintSeverity.WARNING,
    "InvalidGeometry": LintSeverity.ERROR,
}


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
    explicitly.  A disabled rule is not evaluated, so disabling the rules
    you do not need also makes linting faster.

    *min_severity* drops issues below the named threshold from the
    report.  Accepts a :class:`LintSeverity` member or a case-insensitive
    string (``"info"``, ``"warning"``, ``"error"``).  The default
    ``"info"`` keeps everything.

    Returns a :class:`SlideLintReport` with the detected issues.
    """
    severity = _parse_min_severity(min_severity)
    rules = _RuleSelection(disable, severity)
    slide_w, slide_h = _slide_dimensions(slide)
    # Read every shape's box and lint metadata once; the checks below work
    # from these records instead of going back to the XML per shape or pair.
    infos = [_ShapeInfo(shape, include_effect_bleed) for shape in slide.shapes]
    text_env = _TextEnv(slide)

    # Measure the text first.  It yields the TextOverflow issues, and for a
    # shape that resizes to its text (or a table, whose rows grow) the box it
    # will really occupy, which is what the geometric checks must test.
    if rules.wanted("TextOverflow", "OffSlide", "OffSlideShadow", *_PAIRWISE_CODES):
        _measure_texts(text_env, infos)

    # Shapes that actually overlap, found by a sweep rather than by trying
    # every pair; shared by all the cross-shape checks.
    pairs: list[tuple[int, int]] = []
    if rules.wanted(*_PAIRWISE_CODES):
        pairs = _overlapping_pairs([info.bleed_box for info in infos])
    backdrops = _Backdrops(slide, infos, pairs) if rules.wanted("LowContrast") else None
    slide_size = (slide_w, slide_h) if slide_w is not None and slide_h is not None else None

    issues = _shape_issues(infos, rules, slide_size, include_effect_bleed, backdrops)
    issues += _cross_shape_issues(slide, infos, pairs, rules, include_effect_bleed)

    skips = _LintSkips(infos)
    issues = [i for i in issues if not skips.silences(i) and rules.keeps(i)]
    # Sort: errors → warnings → info
    issues.sort(key=lambda x: _SEVERITY_ORDER[x.severity])

    return SlideLintReport(
        slide,
        issues,
        include_effect_bleed=include_effect_bleed,
        disable=tuple(rules.disabled),
        min_severity=severity,
    )


#: Codes of the rules that compare shapes which overlap.
_PAIRWISE_CODES = (
    "LowContrast",
    "ShapeCollision",
    "ShapeCollisionShadow",
    "ZOrderAnomaly",
    "LayerOrderViolation",
)


def _parse_min_severity(min_severity: str | LintSeverity) -> LintSeverity:
    """`min_severity` as a :class:`LintSeverity`; a string is matched case-insensitively."""
    if isinstance(min_severity, str):
        try:
            return LintSeverity(min_severity.lower())
        except ValueError:
            raise ValueError(
                f"min_severity must be one of "
                f"{[s.value for s in LintSeverity]}, got {min_severity!r}"
            )
    return min_severity


class _RuleSelection:
    """The issue codes one lint run reports: those not disabled, at or above a severity."""

    def __init__(self, disable: Sequence[str], min_severity: LintSeverity):
        self.disabled = frozenset(disable)
        self._threshold = _SEVERITY_ORDER[min_severity]

    def wanted(self, *codes: str) -> bool:
        """True when a rule emitting any of *codes* can contribute to the report."""
        return any(
            code not in self.disabled and _SEVERITY_ORDER[_RULE_SEVERITY[code]] <= self._threshold
            for code in codes
        )

    def keeps(self, issue: LintIssue) -> bool:
        """True when `issue` belongs in the report."""
        if issue.code in self.disabled:
            return False
        return _SEVERITY_ORDER[issue.severity] <= self._threshold


def _measure_texts(env: _TextEnv, infos: Sequence[_ShapeInfo]) -> None:
    """Record each shape's ``TextOverflow`` issues and grow its box to its text."""
    for info in infos:
        finding = _analyse_text(env, info.shape)
        info.text_issues = finding.issues
        if finding.growth != _NO_GROWTH:
            info.grow(finding.growth)


def _invalid_geometry(info: _ShapeInfo, dimension: str) -> InvalidGeometry:
    left, top, right, bottom = _shape_frame(info.shape)
    extent = right - left if dimension == "width" else bottom - top
    return InvalidGeometry(info.shape, dimension, extent)


def _shape_issues(
    infos: Sequence[_ShapeInfo],
    rules: _RuleSelection,
    slide_size: tuple[Length, Length] | None,
    use_bleed: bool,
    backdrops: _Backdrops | None,
) -> list[LintIssue]:
    """The issues each shape has on its own, shape by shape in shape-tree order."""
    invalid_geometry = rules.wanted("InvalidGeometry")
    off_slide = slide_size if rules.wanted("OffSlide", "OffSlideShadow") else None
    text_overflow = rules.wanted("TextOverflow")
    min_font = rules.wanted("MinFontSize")
    issues: list[LintIssue] = []
    for info in infos:
        if info.malformed and invalid_geometry:
            issues.append(_invalid_geometry(info, info.malformed))
        if off_slide is not None:
            issues.extend(_check_off_slide(info, off_slide[0], off_slide[1], use_bleed))
        if text_overflow:
            issues.extend(info.text_issues)
        if min_font:
            issues.extend(_check_min_font_size(info.shape))
        if backdrops is not None:
            issues.extend(_check_low_contrast(info.shape, backdrops))
    return issues


def _cross_shape_issues(
    slide: Slide,
    infos: Sequence[_ShapeInfo],
    pairs: Sequence[tuple[int, int]],
    rules: _RuleSelection,
    use_bleed: bool,
) -> list[LintIssue]:
    """The issues that arise between shapes, rule by rule."""
    issues: list[LintIssue] = []
    if rules.wanted("ShapeCollision", "ShapeCollisionShadow"):
        issues.extend(_check_collisions(infos, pairs, use_bleed))
    if rules.wanted("OffGridDrift"):
        issues.extend(_check_off_grid_drift(infos))
    if rules.wanted("ZOrderAnomaly"):
        issues.extend(_check_z_order_anomalies(infos, pairs))
    if rules.wanted("LayerOrderViolation"):
        issues.extend(_check_layer_order(infos, pairs, use_bleed))
    if rules.wanted("MasterPlaceholderCollision"):
        issues.extend(_check_master_placeholder_collision(slide, infos))
    if rules.wanted("RaggedEdge"):
        issues.extend(_check_ragged_edges(infos))
    return issues


class _LintSkips:
    """The codes each shape silences through ``shape.lint_skip``.

    An issue is dropped when its code is silenced on *every* shape it names.
    Cross-shape issues (ShapeCollision, ZOrderAnomaly) are only suppressed
    when *both* shapes opt out — a one-sided opt-out keeps the warning, since
    the other shape might still want to know.
    """

    def __init__(self, infos: Sequence[_ShapeInfo]):
        self._skips: dict[int, frozenset[str]] = {
            id(info.shape._element): info.skip  # pyright: ignore[reportPrivateUsage]
            for info in infos
            if hasattr(info.shape, "_element")
        }

    def silences(self, issue: LintIssue) -> bool:
        if not issue.shapes:
            return False
        return all(issue.code in self._skips_of(shape) for shape in issue.shapes)

    def _skips_of(self, shape: BaseShape) -> frozenset[str]:
        """The codes `shape` silences; read from the XML for a shape inside a group."""
        key = id(shape._element)  # pyright: ignore[reportPrivateUsage]
        if key not in self._skips:
            self._skips[key] = _shape_lint_skip(shape)
        return self._skips[key]
