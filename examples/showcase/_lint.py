"""Shared lint-on-save helper for the showcase decks."""

from __future__ import annotations

from pptx.exc import LintError
from pptx.lint import LintSeverity
from pptx.presentation import Presentation


def lint_or_die(prs: Presentation) -> None:
    """Auto-fix what we can, then raise on any residual error issue."""
    for slide in prs.slides:
        slide.lint().auto_fix()

    errors: list[str] = []
    for i, slide in enumerate(prs.slides):
        for issue in slide.lint().issues:
            if issue.severity is LintSeverity.ERROR:
                errors.append(f"slide {i + 1}: {issue}")

    if errors:
        raise LintError("\n".join(errors))
