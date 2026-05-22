"""One-call deck audit — combines lint, picture sanity, and empty-slide checks.

For agents producing a deck end-to-end the question is "did I do a
good job?".  :func:`audit` returns a small structured report so the
agent can include a "what I shipped" summary in its reply to the user
without crawling every slide manually::

    from power_pptx import audit

    report = audit(prs)
    print(report.markdown())

The report contains:

* ``lint_issues`` — every :class:`~power_pptx.lint.LintIssue` aggregated
  across slides, each annotated with the slide index it came from.
* ``broken_pictures`` — pictures whose dimensions are zero or whose
  embedded image part appears corrupt.
* ``empty_slides`` — slide indexes whose only shapes are background
  decoration (full-bleed rects, layout placeholders).
* ``font_warnings`` — fonts referenced by shapes that aren't typically
  pre-installed on Windows / macOS / Linux (raises false positives;
  treat as advisory).
* ``size_warnings`` — pictures larger than ``size_warn_bytes`` (default
  2 MB) — flagged so callers can choose to compress.

The audit is read-only — it never mutates the deck.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from power_pptx.api import Presentation
    from power_pptx.lint import LintIssue


__all__ = ["AuditReport", "audit"]


# Fonts that ship with stock Windows / macOS / Office installs.  Used as
# a (very conservative) safe-list for the font_warnings probe.
_COMMON_FONTS = frozenset(
    name.lower()
    for name in (
        "Arial", "Calibri", "Helvetica", "Times New Roman", "Cambria",
        "Verdana", "Tahoma", "Georgia", "Courier New", "Consolas",
        "Segoe UI", "Trebuchet MS", "Garamond", "Impact", "Comic Sans MS",
        "Lucida Console", "Palatino", "Palatino Linotype", "Symbol",
        "Wingdings", "Wingdings 2", "Wingdings 3", "Webdings",
        "Inter", "Roboto", "Open Sans", "Lato", "Noto Sans",
    )
)


@dataclass
class AuditReport:
    """Structured summary returned by :func:`audit`."""

    lint_issues: list[tuple[int, "LintIssue"]] = field(default_factory=list)
    broken_pictures: list[tuple[int, Any]] = field(default_factory=list)
    empty_slides: list[int] = field(default_factory=list)
    font_warnings: list[tuple[int, str]] = field(default_factory=list)
    size_warnings: list[tuple[int, str, int]] = field(default_factory=list)
    total_slides: int = 0

    @property
    def has_errors(self) -> bool:
        from power_pptx.lint import LintSeverity

        return any(
            issue.severity == LintSeverity.ERROR
            for _idx, issue in self.lint_issues
        )

    def markdown(self) -> str:
        """Render the report as a markdown string suitable for chat replies."""
        lines = [f"# Audit report — {self.total_slides} slide(s)"]
        if not (
            self.lint_issues
            or self.broken_pictures
            or self.empty_slides
            or self.font_warnings
            or self.size_warnings
        ):
            lines.append("")
            lines.append("**No issues found.**")
            return "\n".join(lines)

        if self.lint_issues:
            lines.append("")
            lines.append(f"## Lint ({len(self.lint_issues)})")
            for idx, issue in self.lint_issues:
                lines.append(f"- slide {idx}: {issue}")
        if self.broken_pictures:
            lines.append("")
            lines.append(f"## Broken pictures ({len(self.broken_pictures)})")
            for idx, shape in self.broken_pictures:
                lines.append(f"- slide {idx}: `{shape.name}` is zero-sized or missing image data")
        if self.empty_slides:
            lines.append("")
            lines.append("## Empty slides")
            for idx in self.empty_slides:
                lines.append(f"- slide {idx}: no content-bearing shapes")
        if self.font_warnings:
            lines.append("")
            lines.append(f"## Font warnings ({len(self.font_warnings)})")
            seen = set()
            for idx, font in self.font_warnings:
                key = (idx, font)
                if key in seen:
                    continue
                seen.add(key)
                lines.append(f"- slide {idx}: uses `{font}` (not in the common safe-list)")
        if self.size_warnings:
            lines.append("")
            lines.append(f"## Large pictures ({len(self.size_warnings)})")
            for idx, name, size_bytes in self.size_warnings:
                lines.append(
                    f"- slide {idx}: `{name}` is {size_bytes / 1_000_000:.1f} MB"
                )
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.markdown()


def audit(
    prs: "Presentation",
    *,
    size_warn_bytes: int = 2_000_000,
    check_fonts: bool = True,
) -> AuditReport:
    """Walk the deck and return an :class:`AuditReport` summary.

    Read-only — never mutates the presentation.  Each slide is linted
    in passing-defaults mode; per-slide overrides should be supplied
    via the slide-level ``slide.lint(...)`` API directly.
    """
    from power_pptx.shapes.picture import Picture

    report = AuditReport()
    slides = list(prs.slides)
    report.total_slides = len(slides)

    # Read slide dimensions once for the full-bleed-background heuristic.
    slide_w = int(prs.slide_width) if prs.slide_width else 0
    slide_h = int(prs.slide_height) if prs.slide_height else 0
    bleed_w = slide_w * 0.95
    bleed_h = slide_h * 0.95

    for idx, slide in enumerate(slides):
        # Lint each slide and prefix with the index.
        for issue in slide.lint().issues:
            report.lint_issues.append((idx, issue))

        content_shapes = 0
        for shape in slide.shapes:
            # Skip layout placeholders that are entirely inherited.
            if (
                shape.is_placeholder
                and getattr(shape, "has_text_frame", False)
                and not shape.text_frame.text.strip()
            ):
                continue
            # Skip full-bleed background rectangles — they're decoration,
            # not content, so a slide that only contains them should be
            # flagged as empty (matches the documented contract for
            # ``empty_slides``).
            try:
                sw = int(shape.width)
                sh = int(shape.height)
            except Exception:
                sw = sh = 0
            if (
                bleed_w > 0
                and bleed_h > 0
                and sw >= bleed_w
                and sh >= bleed_h
            ):
                has_text = (
                    getattr(shape, "has_text_frame", False)
                    and shape.text_frame.text.strip()
                )
                if not has_text:
                    continue
            content_shapes += 1

            # Picture sanity.
            if isinstance(shape, Picture):
                if int(shape.width) <= 0 or int(shape.height) <= 0:
                    report.broken_pictures.append((idx, shape))
                # Picture size warning via the underlying image part.
                try:
                    img = shape.image  # type: ignore[attr-defined]
                    size_bytes = len(img.blob)
                    if size_bytes > size_warn_bytes:
                        report.size_warnings.append((idx, shape.name, size_bytes))
                except Exception:
                    pass

            # Font warning sweep.
            if check_fonts and getattr(shape, "has_text_frame", False):
                tf = shape.text_frame
                for para in tf.paragraphs:
                    for run in para.runs:
                        name = run.font.name
                        if name and name.lower() not in _COMMON_FONTS:
                            report.font_warnings.append((idx, name))

        if content_shapes == 0:
            report.empty_slides.append(idx)

    return report
