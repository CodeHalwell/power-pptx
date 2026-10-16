"""Supported, read-only validation independent of the repository's test suite."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from lxml import etree

from power_pptx._schema import (
    assert_schema_valid,
    iter_schema_violations,
    schema_validation_available,
)
from power_pptx.audit import audit
from power_pptx.text.fonts import font_is_installed

__all__ = [
    "ValidationReport",
    "validate_presentation",
    "assert_schema_valid",
    "iter_schema_violations",
    "schema_validation_available",
]


@dataclass
class ValidationReport:
    slide_count: int = 0
    schema_checked: bool = False
    roundtrip_checked: bool = False
    schema_violations: list[tuple[str, str]] = field(default_factory=list)
    roundtrip_changed_parts: list[str] = field(default_factory=list)
    missing_fonts: list[str] = field(default_factory=list)
    audit: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(
            self.errors
            or self.schema_violations
            or self.roundtrip_changed_parts
            or self.audit.get("has_errors")
            or self.audit.get("empty_slides")
        )

    def to_dict(self):
        from dataclasses import asdict

        result = asdict(self)
        result["has_errors"] = self.has_errors
        result["font_check_scope"] = "Explicit slide/chart font declarations, including font style"
        return result


def presentation_bytes(source):
    """Serialize an in-memory presentation without altering its content."""
    if isinstance(source, bytes):
        return source
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    buffer = io.BytesIO()
    source.save(buffer)
    return buffer.getvalue()


def _parts(data):
    with ZipFile(io.BytesIO(data)) as package:
        return {name: package.read(name) for name in package.namelist()}


def _canonical(data):
    parser = etree.XMLParser(remove_blank_text=True, resolve_entities=False, no_network=True)
    return etree.tostring(etree.fromstring(data, parser), method="c14n2")


def roundtrip_changes(first, second):
    before, after = _parts(first), _parts(second)
    changed = []
    for name in sorted(before.keys() | after.keys()):
        a, b = before.get(name), after.get(name)
        if a is not None and b is not None and name.endswith((".xml", ".rels")):
            a, b = _canonical(a), _canonical(b)
        if a != b:
            changed.append(name)
    return changed


def _missing_fonts(blob):
    missing = set()
    for name, data in _parts(blob).items():
        if not name.endswith(".xml") or not name.startswith(
            ("ppt/slides/slide", "ppt/charts/chart")
        ):
            continue
        doc = etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True))
        for node in doc.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}latin"):
            family = node.get("typeface")
            if not family or family.startswith("+"):
                continue
            parent = node.getparent()
            if parent is None:
                continue
            bold = parent.get("b") == "1"
            italic = parent.get("i") == "1"
            if not font_is_installed(family, bold, italic):
                missing.add(family + (" bold" if bold else "") + (" italic" if italic else ""))
    return sorted(missing)


def validate_presentation(
    source,
    *,
    check_schema: bool = True,
    check_roundtrip: bool = True,
    check_fonts: bool = True,
) -> ValidationReport:
    """Audit a presentation, validate OOXML, and check save/reopen fidelity.

    Accepts a Presentation, PPTX path, or bytes. XSDs ship in the installed
    package; no test checkout is needed. Missing explicit fonts are advisory.
    Malformed packages produce an error report instead of aborting a batch.
    Input files and in-memory presentation XML are never changed.
    """
    from power_pptx import Presentation

    report = ValidationReport()
    try:
        data = presentation_bytes(source)
        if check_schema:
            report.schema_violations = list(iter_schema_violations(data))
            report.schema_checked = True
        prs = Presentation(io.BytesIO(data))
        report.slide_count = len(prs.slides)
        if check_roundtrip:
            report.roundtrip_changed_parts = roundtrip_changes(data, presentation_bytes(prs))
            report.roundtrip_checked = True
        # The installed-font inventory below replaces audit's portability
        # heuristic, which warns about every face outside its common-font list.
        report.audit = audit(prs, check_fonts=False).to_dict()
        if not report.slide_count:
            report.errors.append("Presentation has no slides")
        if check_fonts:
            report.missing_fonts = _missing_fonts(data)
    except Exception as exc:
        report.errors.append(f"{type(exc).__name__}: {exc}")
    return report
