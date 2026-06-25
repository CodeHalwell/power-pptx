"""Read-only accessibility audit for a generated deck.

Decks produced programmatically routinely ship without the metadata a
screen reader needs — pictures with no alt text, slides with no title,
text whose contrast against its fill falls below WCAG AA.  These slip
past the layout linter (the deck *looks* fine) but make the result
unusable for assistive technology.

:func:`audit_accessibility` walks every slide and shape and returns a
small structured :class:`AccessibilityReport` so an agent that builds a
deck can answer "is this accessible?" without crawling the slides by
hand::

    from power_pptx import accessibility

    report = accessibility.audit_accessibility(prs)
    print(report.markdown())
    if report.has_errors:
        ...

The audit is strictly read-only — it never mutates the deck.

Issue codes:

* ``MissingAltText``   — a picture or other meaningful shape carries no
  ``alt_text`` (``<p:cNvPr descr=...>``).  Pictures are ERROR (a screen
  reader has nothing to announce); other meaningful shapes are WARNING.
* ``LowContrast``      — text-on-fill contrast is below WCAG AA (4.5:1),
  reusing the contrast math from :mod:`power_pptx.lint`.
* ``NoSlideTitle``     — a slide has no (non-empty) title, so it has no
  landmark for navigation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from power_pptx.api import Presentation
    from power_pptx.shapes.base import BaseShape
    from power_pptx.slide import Slide


__all__ = [
    "AccessibilitySeverity",
    "AccessibilityIssue",
    "AccessibilityReport",
    "audit_accessibility",
]


class AccessibilitySeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class AccessibilityIssue:
    """A single accessibility problem found on a slide.

    ``slide`` is the zero-based slide index; ``shape`` is the offending
    shape's name (``None`` for slide-level issues such as a missing
    title).  ``code`` is one of ``"MissingAltText"``, ``"LowContrast"``,
    ``"NoSlideTitle"``.
    """

    slide: int
    code: str
    message: str
    severity: AccessibilitySeverity = AccessibilitySeverity.WARNING
    shape: str | None = None

    def __str__(self) -> str:
        where = f"slide {self.slide}"
        if self.shape is not None:
            where += f" / {self.shape!r}"
        return f"[{self.severity.value.upper()}] {self.code} ({where}): {self.message}"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict describing this issue."""
        payload = asdict(self)
        payload["severity"] = self.severity.value
        return payload


# Shape types that carry visual meaning and should describe themselves to a
# screen reader.  Decorative chrome (plain text boxes, which already expose
# their text, and group containers) is handled separately below.
_MEANINGFUL_TYPE_NAMES = frozenset(
    {
        "PICTURE",
        "LINKED_PICTURE",
        "CHART",
        "TABLE",
        "DIAGRAM",
        "IGX_GRAPHIC",
        "MEDIA",
        "EMBEDDED_OLE_OBJECT",
        "LINKED_OLE_OBJECT",
        "FREEFORM",
        "WEB_VIDEO",
    }
)

# Picture-like types are held to a higher standard: a screen reader has
# literally nothing to announce for them without alt text, so a missing
# description is an ERROR rather than a WARNING.
_PICTURE_TYPE_NAMES = frozenset({"PICTURE", "LINKED_PICTURE", "MEDIA", "WEB_VIDEO"})


def _shape_type_name(shape: "BaseShape") -> str | None:
    """Return the ``MSO_SHAPE_TYPE`` member name for *shape*, or ``None``.

    Some shapes (notably bare group children or proxies that don't
    implement ``shape_type``) raise on access; treat those as untyped.
    """
    try:
        st = shape.shape_type
    except Exception:
        return None
    return getattr(st, "name", None)


def _has_text(shape: "BaseShape") -> bool:
    try:
        if not getattr(shape, "has_text_frame", False):
            return False
        return bool(shape.text_frame.text.strip())  # type: ignore[attr-defined]
    except Exception:
        return False


def _slide_has_title(slide: "Slide") -> bool:
    """Return ``True`` when *slide* has a title placeholder with text."""
    try:
        title = slide.shapes.title
    except Exception:
        title = None
    if title is None:
        return False
    try:
        return bool(title.text_frame.text.strip())
    except Exception:
        # A title placeholder exists; without readable text we still
        # treat the landmark as present (the placeholder is navigable).
        return True


def _check_alt_text(slide_idx: int, shape: "BaseShape") -> list[AccessibilityIssue]:
    """Flag meaningful shapes that carry no alt text."""
    type_name = _shape_type_name(shape)
    if type_name is None:
        return []
    if type_name not in _MEANINGFUL_TYPE_NAMES:
        return []
    try:
        alt = shape.alt_text
    except Exception:
        return []
    if alt.strip():
        return []
    # A meaningful shape that also exposes its text content is partially
    # self-describing; still flag it, but as a warning either way.
    is_picture = type_name in _PICTURE_TYPE_NAMES
    severity = AccessibilitySeverity.ERROR if is_picture else AccessibilitySeverity.WARNING
    kind = "picture" if is_picture else type_name.replace("_", " ").lower()
    return [
        AccessibilityIssue(
            slide=slide_idx,
            code="MissingAltText",
            message=f"{kind} has no alt text; set shape.alt_text for screen readers.",
            severity=severity,
            shape=shape.name,
        )
    ]


def _check_contrast(slide_idx: int, shape: "BaseShape", slide: "Slide") -> list[AccessibilityIssue]:
    """Flag low text/background contrast, reusing lint's contrast math.

    Imports the contrast helpers from :mod:`power_pptx.lint` read-only.
    Skips silently whenever colours can't be resolved (theme colours,
    gradients, inherited backgrounds) — matching the linter's behaviour.
    """
    try:
        from power_pptx.lint import (
            _CONTRAST_THRESHOLD,
            _contrast_ratio,
            _resolve_solid_rgb,
            _slide_background_rgb,
        )
    except Exception:
        return []

    if not _has_text(shape):
        return []

    tf = shape.text_frame  # type: ignore[attr-defined]
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
        return []
    if text_rgb is None:
        return []

    bg_rgb = None
    try:
        bg_rgb = _resolve_solid_rgb(shape.fill)  # type: ignore[attr-defined]
    except Exception:
        bg_rgb = None
    if bg_rgb is None:
        bg_rgb = _slide_background_rgb(slide)
    if bg_rgb is None:
        return []

    ratio = _contrast_ratio(text_rgb, bg_rgb)
    if ratio >= _CONTRAST_THRESHOLD:
        return []
    return [
        AccessibilityIssue(
            slide=slide_idx,
            code="LowContrast",
            message=(
                f"text-on-fill contrast {ratio:.2f}:1 is below WCAG AA "
                f"({_CONTRAST_THRESHOLD:.1f}:1)."
            ),
            severity=AccessibilitySeverity.WARNING,
            shape=shape.name,
        )
    ]


@dataclass
class AccessibilityReport:
    """Structured summary returned by :func:`audit_accessibility`."""

    issues: list[AccessibilityIssue] = field(default_factory=list)
    total_slides: int = 0

    @property
    def has_errors(self) -> bool:
        """True when at least one ERROR-severity issue is present."""
        return any(i.severity == AccessibilitySeverity.ERROR for i in self.issues)

    def markdown(self) -> str:
        """Render the report as a markdown string suitable for chat replies."""
        lines = [f"# Accessibility report — {self.total_slides} slide(s)"]
        if not self.issues:
            lines.append("")
            lines.append("**No accessibility issues found.**")
            return "\n".join(lines)

        # Group by code so the reader sees "all the missing alt text"
        # together rather than interleaved per slide.
        by_code: dict[str, list[AccessibilityIssue]] = {}
        for issue in self.issues:
            by_code.setdefault(issue.code, []).append(issue)

        for code in sorted(by_code):
            bucket = by_code[code]
            lines.append("")
            lines.append(f"## {code} ({len(bucket)})")
            for issue in bucket:
                where = f"slide {issue.slide}"
                if issue.shape is not None:
                    where += f" — `{issue.shape}`"
                lines.append(f"- {where}: {issue.message}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of the whole audit."""
        return {
            "total_slides": self.total_slides,
            "has_errors": self.has_errors,
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        """Return :meth:`to_dict` serialized as a JSON string."""
        import json

        return json.dumps(self.to_dict(), indent=indent)

    def __str__(self) -> str:
        return self.markdown()


def audit_accessibility(
    prs: "Presentation",
    *,
    check_contrast: bool = True,
) -> AccessibilityReport:
    """Walk the deck and return an :class:`AccessibilityReport`.

    Read-only — never mutates the presentation.  Flags:

    * pictures and other meaningful shapes missing ``alt_text``;
    * text whose contrast against its fill/background is below WCAG AA
      (when ``check_contrast`` is True and the colours are resolvable);
    * slides with no (non-empty) title placeholder.
    """
    report = AccessibilityReport()
    slides = list(prs.slides)
    report.total_slides = len(slides)

    for idx, slide in enumerate(slides):
        if not _slide_has_title(slide):
            report.issues.append(
                AccessibilityIssue(
                    slide=idx,
                    code="NoSlideTitle",
                    message=(
                        "slide has no title; screen-reader users rely on the "
                        "title as a navigation landmark."
                    ),
                    severity=AccessibilitySeverity.WARNING,
                    shape=None,
                )
            )

        for shape in slide.shapes:
            report.issues.extend(_check_alt_text(idx, shape))
            if check_contrast:
                report.issues.extend(_check_contrast(idx, shape, slide))

    # Order: errors first, then warnings, then info — mirrors lint.
    _order = {
        AccessibilitySeverity.ERROR: 0,
        AccessibilitySeverity.WARNING: 1,
        AccessibilitySeverity.INFO: 2,
    }
    report.issues.sort(key=lambda i: (_order.get(i.severity, 3), i.slide))
    return report
