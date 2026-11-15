"""Supported, read-only validation independent of the repository's test suite."""

from __future__ import annotations

import io
import posixpath
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from lxml import etree

from power_pptx._schema import (
    assert_schema_valid,
    hardened_parser,
    iter_schema_violations,
    parse_xml,
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


_CONTENT_TYPES = "[Content_Types].xml"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


#: As hardened as the parser the rest of the package is read with, but
#: dropping the whitespace between elements, which is not content.
_CANONICAL_PARSER = hardened_parser(remove_blank_text=True)


def _canonical(data):
    root = etree.fromstring(data, _CANONICAL_PARSER)
    # -- entity references are never resolved here, and C14N cannot write one.
    # -- (`etree.Entity` is missing from the bundled lxml stubs.) --
    entity_nodes = root.iter(etree.Entity)  # pyright: ignore[reportAttributeAccessIssue]
    if next(entity_nodes, None) is not None:
        raise ValueError("XML with entity references has no canonical form")
    return etree.tostring(root, method="c14n2")


def _relationships(name, data):
    """Return the relationships declared by the ``.rels`` part *name*, order-free.

    A package means the same whatever order its ``Relationship`` elements come
    in and however an internal Target is spelled (``/ppt/media/a.png`` or
    ``../media/a.png``), so each one is reduced to (Id, Type, resolved Target,
    TargetMode). A counter rather than a set keeps a duplicated entry visible.
    """
    base = "/" + posixpath.dirname(posixpath.dirname(name))
    relationships: Counter[tuple[str | None, str | None, str, str]] = Counter()
    for rel in parse_xml(data).iter("{%s}Relationship" % _PKG_REL_NS):
        mode = rel.get("TargetMode") or "Internal"
        target = rel.get("Target") or ""
        if mode == "Internal":
            target = posixpath.normpath(posixpath.join(base, target))
        relationships[(rel.get("Id"), rel.get("Type"), target, mode)] += 1
    return relationships


def _content_types(parts):
    """Return ``{part name: content type}`` as ``[Content_Types].xml`` resolves it.

    The same type can be declared by a ``Default`` for the extension or an
    ``Override`` for the part, in any order, so only the resolved type of each
    part is comparable. Lookups ignore case, as the package reader does.
    """
    root = parse_xml(parts[_CONTENT_TYPES])
    defaults = {
        (e.get("Extension") or "").lower(): e.get("ContentType")
        for e in root.iter("{%s}Default" % _CT_NS)
    }
    overrides = {
        (e.get("PartName") or "").lower(): e.get("ContentType")
        for e in root.iter("{%s}Override" % _CT_NS)
    }
    resolved = {}
    for name in parts:
        if name == _CONTENT_TYPES or name.endswith("/"):
            continue
        content_type = overrides.get("/" + name.lower())
        if content_type is None:
            # -- everything after the last dot, so `_rels/.rels` has extension `rels` --
            base = posixpath.basename(name)
            content_type = defaults.get(base.rsplit(".", 1)[1].lower() if "." in base else "")
        resolved[name] = content_type
    return resolved


def _same_part(name, a, b):
    """True when part *name* means the same in both packages."""
    if a == b:
        return True
    try:
        if name.endswith(".rels"):
            return _relationships(name, a) == _relationships(name, b)
        if name.endswith(".xml"):
            return _canonical(a) == _canonical(b)
    except (etree.XMLSyntaxError, ValueError):
        pass  # -- not comparable as XML, and the bytes already differ --
    return False


def roundtrip_changes(first, second):
    """Return the names of the parts that differ between two saves of a package.

    Parts are compared by what they mean, not by their bytes: XML parts in
    canonical form, ``.rels`` parts as the relationships they declare, and
    ``[Content_Types].xml`` by the content type it gives each part present in
    both packages. The package writer sorts relationships and regenerates the
    content-types stream, so a byte comparison of those would report every
    package this library did not write. A part found in only one package is
    always reported.
    """
    before, after = _parts(first), _parts(second)
    changed = []
    for name in sorted(before.keys() | after.keys()):
        a, b = before.get(name), after.get(name)
        if a is None or b is None:
            changed.append(name)
        elif name == _CONTENT_TYPES:
            types_a, types_b = _content_types(before), _content_types(after)
            if any(types_a[part] != types_b[part] for part in types_a.keys() & types_b.keys()):
                changed.append(name)
        elif not _same_part(name, a, b):
            changed.append(name)
    return changed


#: The parts whose explicit fonts are checked: slides and charts.
_FONT_PARTS = ("ppt/slides/slide", "ppt/charts/chart")
_LATIN = "{http://schemas.openxmlformats.org/drawingml/2006/main}latin"


def _missing_fonts(blob):
    missing = set()
    for doc in _font_part_docs(blob):
        for node in doc.iter(_LATIN):
            font = _explicit_font(node)
            if font is not None and not font_is_installed(*font):
                missing.add(_font_label(*font))
    return sorted(missing)


def _font_part_docs(blob):
    """Yield the parsed slide and chart parts of package *blob*."""
    for name, data in _parts(blob).items():
        if name.endswith(".xml") and name.startswith(_FONT_PARTS):
            yield parse_xml(data)


def _explicit_font(latin):
    """Return ``(family, bold, italic)`` for an ``a:latin`` naming a face, else |None|.

    A theme font (``+mn-lt`` and the like) and an empty typeface name no face;
    the style comes from the run properties the ``a:latin`` belongs to.
    """
    family = latin.get("typeface")
    if not family or family.startswith("+"):
        return None
    properties = latin.getparent()
    if properties is None:
        return None
    return family, properties.get("b") == "1", properties.get("i") == "1"


def _font_label(family, bold, italic):
    """Return how a missing face is listed, e.g. ``"Inter bold italic"``."""
    return family + (" bold" if bold else "") + (" italic" if italic else "")


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

    The round-trip check opens the package, saves it and lists the parts whose
    content, relationships or content type differ, so it passes for a deck
    from PowerPoint or any other producer that the library preserves. The
    order of relationships and of content-type declarations is not content.
    """
    from power_pptx import Presentation

    report = ValidationReport()
    try:
        data = presentation_bytes(source)
        if check_schema:
            report.schema_violations = list(iter_schema_violations(data))
            report.schema_checked = True
        prs = Presentation(io.BytesIO(data))
        if check_roundtrip:
            # -- Save before anything reads `prs`. `Presentation.slides` adds an
            # -- empty `p:sldIdLst` to a deck without one and renames slide parts
            # -- into sequence; neither is a change made by opening and saving.
            report.roundtrip_changed_parts = roundtrip_changes(data, presentation_bytes(prs))
            report.roundtrip_checked = True
        report.slide_count = len(prs.slides)
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
