"""Helpers shared by the playground decks.

Just a lint-or-die that's reused across scripts, plus a tiny stdout
formatter so build_all output stays scannable.
"""

from __future__ import annotations

from power_pptx.exc import LintError
from power_pptx.lint import LintSeverity
from power_pptx.presentation import Presentation


def lint_or_die(prs: Presentation) -> None:
    """Auto-fix what we can and raise on residual errors."""
    for slide in prs.slides:
        slide.lint().auto_fix()

    errors: list[str] = []
    for i, slide in enumerate(prs.slides, start=1):
        for issue in slide.lint().issues:
            if issue.severity is LintSeverity.ERROR:
                errors.append(f"slide {i}: {issue}")

    if errors:
        raise LintError("\n".join(errors))
