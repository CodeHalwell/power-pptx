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
  treat as advisory).  Fonts set on runs, on paragraphs and in table
  cells all count, once per slide; a theme reference such as ``+mn-lt``
  is reported as the theme font it stands for.
* ``size_warnings`` — pictures larger than ``size_warn_bytes`` (default
  2 MB) — flagged so callers can choose to compress.

The audit is read-only — it never mutates the deck.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable, Iterator

from PIL import Image as PILImage

from power_pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
from power_pptx.lint import _has_visible_text
from power_pptx.oxml.ns import qn
from power_pptx.shapes.autoshape import Shape
from power_pptx.shapes.group import GroupShape

if TYPE_CHECKING:
    from power_pptx.lint import LintIssue
    from power_pptx.presentation import Presentation
    from power_pptx.shapes.base import BaseShape
    from power_pptx.shapes.picture import Picture


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
    broken_pictures: list[tuple[int, Picture]] = field(default_factory=list)
    empty_slides: list[int] = field(default_factory=list)
    font_warnings: list[tuple[int, str]] = field(default_factory=list)
    size_warnings: list[tuple[int, str, int]] = field(default_factory=list)
    total_slides: int = 0

    @property
    def has_errors(self) -> bool:
        """True when lint errors or broken pictures need fixing."""
        from power_pptx.lint import LintSeverity

        return bool(self.broken_pictures) or any(
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
                lines.append(
                    f"- slide {idx}: `{shape.name}` is zero-sized or has missing/corrupt image data"
                )
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

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of the whole audit.

        This is the machine-readable counterpart to :meth:`markdown` — built
        for the agent loop that generates a deck, audits it, and feeds the
        result back to a model (or a CI gate) to decide what to fix. Every
        lint issue is expanded via :meth:`~power_pptx.lint.LintIssue.to_dict`,
        and slide-relative shape references are reduced to names::

            report = audit(prs)
            if report.to_dict()["has_errors"]:
                ...

        Top-level keys: ``total_slides``, ``has_errors``, ``lint_issues``,
        ``broken_pictures``, ``empty_slides``, ``font_warnings``,
        ``size_warnings``.
        """
        return {
            "total_slides": self.total_slides,
            "has_errors": self.has_errors,
            "lint_issues": [
                {"slide": idx, **issue.to_dict()} for idx, issue in self.lint_issues
            ],
            "broken_pictures": [
                {"slide": idx, "shape": shape.name} for idx, shape in self.broken_pictures
            ],
            "empty_slides": list(self.empty_slides),
            "font_warnings": [
                {"slide": idx, "font": font} for idx, font in self.font_warnings
            ],
            "size_warnings": [
                {"slide": idx, "shape": name, "bytes": size_bytes}
                for idx, name, size_bytes in self.size_warnings
            ],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        """Return :meth:`to_dict` serialized as a JSON string."""
        import json

        return json.dumps(self.to_dict(), indent=indent)

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

        fonts = _SlideFonts(slide) if check_fonts else None
        content_shapes = 0
        for shape in _leaf_shapes(slide.shapes):
            tx_body = _tx_body(shape)
            has_text = tx_body is not None and _has_visible_text(tx_body)
            if fonts is not None:
                fonts.collect(shape, tx_body)
            # Skip layout placeholders that are entirely inherited.
            if shape.is_placeholder and tx_body is not None and not has_text:
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
                isinstance(shape, Shape)
                and shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
                and shape.auto_shape_type == MSO_SHAPE.RECTANGLE
                and bleed_w > 0
                and bleed_h > 0
                and sw >= bleed_w
                and sh >= bleed_h
                and int(shape.left or 0) <= slide_w * 0.05
                and int(shape.top or 0) <= slide_h * 0.05
                and int(shape.left or 0) + sw >= bleed_w
                and int(shape.top or 0) + sh >= bleed_h
                and not has_text
            ):
                continue
            content_shapes += 1

            # Picture sanity.
            if isinstance(shape, Picture):
                broken = int(shape.width) <= 0 or int(shape.height) <= 0
                try:
                    rId = shape._pic.blip_rId
                    if rId is None:
                        raise ValueError("picture has no embedded image")
                    image_part = shape.part.related_part(rId)
                    blob = image_part.blob
                    size_bytes = len(blob)
                    if size_bytes > size_warn_bytes:
                        report.size_warnings.append((idx, shape.name, size_bytes))
                    if not blob:
                        broken = True
                    elif image_part.content_type in {
                        "image/png", "image/jpeg", "image/gif", "image/bmp", "image/tiff"
                    }:
                        # Validate standard raster formats. Vectors and WDP
                        # can be valid without an installed Pillow decoder.
                        with PILImage.open(io.BytesIO(blob)) as image:
                            image.verify()
                except (OSError, ValueError, KeyError, AttributeError, TypeError, SyntaxError):
                    broken = True
                if broken:
                    report.broken_pictures.append((idx, shape))

        if fonts is not None:
            report.font_warnings.extend((idx, name) for name in fonts.uncommon())

        if content_shapes == 0:
            report.empty_slides.append(idx)

    return report


def _leaf_shapes(shapes: Iterable[BaseShape]) -> Iterator[BaseShape]:
    """Visit content inside nested groups without counting group wrappers."""
    for shape in shapes:
        if isinstance(shape, GroupShape):
            yield from _leaf_shapes(shape.shapes)
        else:
            yield shape


def _tx_body(shape: BaseShape):
    """The shape's ``<p:txBody>``, or ``None``.

    Read off the element: ``shape.text_frame`` adds an empty text body to a
    shape that has none, and the audit must not change the deck.
    """
    if not getattr(shape, "has_text_frame", False):
        return None
    return getattr(shape._element, "txBody", None)  # pyright: ignore[reportPrivateUsage]


class _SlideFonts:
    """Collects the typefaces a slide's text asks for, in order of appearance.

    Every ``<a:latin>`` counts — on a run, on a paragraph's default run
    properties, on an end-of-paragraph mark, or in a list style — in shapes
    and in table cells alike.  A theme reference such as ``+mn-lt`` is
    resolved to the theme's font, the one PowerPoint actually draws with.
    """

    _LATIN = qn("a:latin")

    def __init__(self, slide):
        from power_pptx.lint import _TextEnv

        self._env = _TextEnv(slide)
        self._names: dict[str, None] = {}

    def collect(self, shape: BaseShape, tx_body) -> None:
        bodies = [] if tx_body is None else [tx_body]
        if getattr(shape, "has_table", False):
            try:
                tbl = shape._element.graphic.graphicData.tbl  # pyright: ignore[reportPrivateUsage]
                bodies.extend(tc.txBody for tc in tbl.iter_tcs() if tc.txBody is not None)
            except AttributeError:
                pass
        for body in bodies:
            for latin in body.iter(self._LATIN):
                face = latin.get("typeface")
                if face:
                    self._names.setdefault(self._env.family(face), None)

    def uncommon(self) -> list[str]:
        """The collected families not in the common safe-list, once each."""
        return [name for name in self._names if name.lower() not in _COMMON_FONTS]
