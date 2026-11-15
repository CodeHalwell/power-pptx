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
    from power_pptx.slide import Slide


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
        sections = [(heading, items) for heading, items in self._sections() if items]
        if not sections:
            lines += ["", "**No issues found.**"]
        for heading, items in sections:
            lines += ["", heading, *items]
        return "\n".join(lines)

    def _sections(self) -> list[tuple[str, list[str]]]:
        """``(heading, bullet lines)`` of each markdown section, empty ones included."""
        return [
            (
                f"## Lint ({len(self.lint_issues)})",
                [f"- slide {idx}: {issue}" for idx, issue in self.lint_issues],
            ),
            (
                f"## Broken pictures ({len(self.broken_pictures)})",
                [
                    f"- slide {idx}: `{shape.name}` is zero-sized or has missing/corrupt image data"
                    for idx, shape in self.broken_pictures
                ],
            ),
            (
                "## Empty slides",
                [f"- slide {idx}: no content-bearing shapes" for idx in self.empty_slides],
            ),
            (
                f"## Font warnings ({len(self.font_warnings)})",
                [
                    f"- slide {idx}: uses `{font}` (not in the common safe-list)"
                    for idx, font in dict.fromkeys((i, f) for i, f in self.font_warnings)
                ],
            ),
            (
                f"## Large pictures ({len(self.size_warnings)})",
                [
                    f"- slide {idx}: `{name}` is {size_bytes / 1_000_000:.1f} MB"
                    for idx, name, size_bytes in self.size_warnings
                ],
            ),
        ]

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
    report = AuditReport()
    slides = list(prs.slides)
    report.total_slides = len(slides)

    # Read slide dimensions once for the full-bleed-background heuristic.
    slide_w = int(prs.slide_width) if prs.slide_width else 0
    slide_h = int(prs.slide_height) if prs.slide_height else 0
    checks = _SlideAudit(report, (slide_w, slide_h), size_warn_bytes, check_fonts)
    for idx, slide in enumerate(slides):
        checks.run(idx, slide)
    return report


#: Image types whose data is decoded to check it.  Vectors and WDP can be
#: valid without an installed Pillow decoder.
_RASTER_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/bmp", "image/tiff"})

#: What reading or decoding a picture's image data raises when it is broken.
_IMAGE_ERRORS = (OSError, ValueError, KeyError, AttributeError, TypeError, SyntaxError)


class _SlideAudit:
    """Audits one slide at a time into `report`; see :func:`audit`."""

    def __init__(
        self,
        report: AuditReport,
        slide_size: tuple[int, int],
        size_warn_bytes: int,
        check_fonts: bool,
    ):
        self._report = report
        self._slide_size = slide_size
        self._size_warn_bytes = size_warn_bytes
        self._check_fonts = check_fonts

    def run(self, idx: int, slide: Slide) -> None:
        """Add slide `idx`'s lint issues, picture problems, fonts and emptiness."""
        from power_pptx.shapes.picture import Picture

        report = self._report
        # Lint each slide and prefix with the index.
        for issue in slide.lint().issues:
            report.lint_issues.append((idx, issue))

        fonts = _SlideFonts(slide) if self._check_fonts else None
        content_shapes = 0
        for shape in _leaf_shapes(slide.shapes):
            tx_body = _tx_body(shape)
            has_text = tx_body is not None and _has_visible_text(tx_body)
            if fonts is not None:
                fonts.collect(shape, tx_body)
            if _is_decoration(shape, tx_body, has_text, self._slide_size):
                continue
            content_shapes += 1
            if isinstance(shape, Picture):
                self._check_picture(idx, shape)

        if fonts is not None:
            report.font_warnings.extend((idx, name) for name in fonts.uncommon())

        if content_shapes == 0:
            report.empty_slides.append(idx)

    def _check_picture(self, idx: int, picture: Picture) -> None:
        """Record `picture` as broken or oversized when it is."""
        broken = int(picture.width) <= 0 or int(picture.height) <= 0
        try:
            image_part = _embedded_image_part(picture)
            blob = image_part.blob
            size_bytes = len(blob)
            if size_bytes > self._size_warn_bytes:
                self._report.size_warnings.append((idx, picture.name, size_bytes))
            if not _image_data_is_sound(blob, image_part):
                broken = True
        except _IMAGE_ERRORS:
            broken = True
        if broken:
            self._report.broken_pictures.append((idx, picture))


def _is_decoration(shape: BaseShape, tx_body, has_text: bool, slide_size: tuple[int, int]) -> bool:
    """True for a shape that is not content: an empty inherited placeholder or a backdrop.

    A full-bleed background rectangle is decoration, so a slide that only
    contains them is flagged as empty (the documented contract for
    ``empty_slides``).
    """
    if shape.is_placeholder and tx_body is not None and not has_text:
        return True
    return _is_full_bleed_rectangle(shape, has_text, slide_size)


def _is_full_bleed_rectangle(shape: BaseShape, has_text: bool, slide_size: tuple[int, int]) -> bool:
    """True for a rectangle with no text covering at least 95% of the slide each way."""
    slide_w, slide_h = slide_size
    bleed_w = slide_w * 0.95
    bleed_h = slide_h * 0.95
    try:
        sw = int(shape.width)
        sh = int(shape.height)
    except Exception:
        sw = sh = 0
    return (
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
    )


def _embedded_image_part(picture: Picture):
    """The image part `picture` shows; ``ValueError`` when it embeds none."""
    rId = picture._pic.blip_rId  # pyright: ignore[reportPrivateUsage]
    if rId is None:
        raise ValueError("picture has no embedded image")
    return picture.part.related_part(rId)


def _image_data_is_sound(blob: bytes, image_part) -> bool:
    """False for empty image data; a raster image is decoded, raising if it is corrupt."""
    if not blob:
        return False
    if image_part.content_type in _RASTER_TYPES:
        with PILImage.open(io.BytesIO(blob)) as image:
            image.verify()
    return True


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
            element: Any = shape._element  # pyright: ignore[reportPrivateUsage]
            try:
                tbl = element.graphic.graphicData.tbl
            except AttributeError:
                tbl = None
            if tbl is not None:
                bodies.extend(tc.txBody for tc in tbl.iter_tcs() if tc.txBody is not None)
        for body in bodies:
            for latin in body.iter(self._LATIN):
                face = latin.get("typeface")
                if face:
                    self._names.setdefault(self._env.family(face), None)

    def uncommon(self) -> list[str]:
        """The collected families not in the common safe-list, once each."""
        return [name for name in self._names if name.lower() not in _COMMON_FONTS]
