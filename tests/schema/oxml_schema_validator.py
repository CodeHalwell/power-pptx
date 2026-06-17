"""Validate generated ``.pptx`` parts against the ISO/IEC 29500 XSD schemas.

PowerPoint rejects (and silently "repairs") files that violate the OOXML
schema even when ``lxml`` / python-pptx / LibreOffice happily accept them — an
empty ``<a:scene3d>``, a colour-less ``<a:outerShdw>``, a negative chart
``axId``, a bare ``<p14:morph>``, and so on.  Those bugs are invisible to the
normal "does it parse / does it reopen" checks, so this module validates the
XML of each generated part against the schemas the repo already ships in
``spec/ISO-IEC-29500-4/xsd``.

Usage from a test::

    from tests.schema.oxml_schema_validator import (
        schema_validation_available,
        iter_schema_violations,
    )

    violations = list(iter_schema_violations(pptx_bytes_or_path))
    assert not violations, violations

The validator is deliberately conservative: it only checks the parts whose
root namespace it has a schema for (PresentationML slides/layouts/masters/notes
+ presentation.xml, DrawingML themes, and chart parts) and resolves
``mc:AlternateContent`` to its ``mc:Fallback`` first — the ISO-pure branch a
non-extension processor would use — so Microsoft-namespace extensions (p14
morph, etc.) are validated through their fallback rather than reported as
"unexpected".
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Iterator, Union

try:
    from lxml import etree

    _LXML = True
except ImportError:  # pragma: no cover - lxml is a hard dependency, but be safe
    _LXML = False


# -- locate the bundled XSD schemas (repo-root/spec/...) --------------------
_XSD_DIR = Path(__file__).resolve().parents[2] / "spec" / "ISO-IEC-29500-4" / "xsd"

# Root-element namespace -> the schema file that defines that target namespace.
_NS_SCHEMA = {
    "http://schemas.openxmlformats.org/presentationml/2006/main": "pml.xsd",
    "http://schemas.openxmlformats.org/drawingml/2006/main": "dml-main.xsd",
    "http://schemas.openxmlformats.org/drawingml/2006/chart": "dml-chart.xsd",
}

_MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_CHART_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"

# PowerPoint parses chart axis ids (``c:axId`` / ``c:crossAx``) as *signed*
# 32-bit integers, so a value above 2**31-1 reads back negative and PowerPoint
# reports the deck as needing repair.  The ISO schema types these as
# ``xsd:unsignedInt`` (0 .. 2**32-1), so XSD validation can't see the problem.
# A valid id is therefore a positive signed-int32: 1 .. 2**31-1.
_INT32_MAX = 2**31 - 1

# Only validate parts we have a root schema for.  Keyed by partname prefix.
_CHECKED_PREFIXES = (
    "ppt/slides/slide",
    "ppt/slideLayouts/slideLayout",
    "ppt/slideMasters/slideMaster",
    "ppt/notesSlides/notesSlide",
    "ppt/notesMasters/notesMaster",
    "ppt/charts/chart",
    "ppt/theme/theme",
)
_CHECKED_EXACT = ("ppt/presentation.xml",)

_schema_cache: "dict[str, object]" = {}


def schema_validation_available() -> bool:
    """Return True when lxml is importable and the bundled XSDs are present."""
    return _LXML and (_XSD_DIR / "pml.xsd").is_file()


def _schema_for_namespace(namespace: str):
    """Return a compiled ``etree.XMLSchema`` for *namespace*, or None."""
    xsd_file = _NS_SCHEMA.get(namespace)
    if xsd_file is None:
        return None
    if namespace not in _schema_cache:
        # Parsing with the file path as base URI lets lxml resolve the
        # schema's relative <xsd:import schemaLocation="..."> references.
        doc = etree.parse(str(_XSD_DIR / xsd_file))
        _schema_cache[namespace] = etree.XMLSchema(doc)
    return _schema_cache[namespace]


def _resolve_mce(doc):
    """Resolve ``mc:AlternateContent`` to its ``mc:Fallback`` content in place.

    This mirrors how a processor that doesn't understand the required
    extension namespaces reads the file, leaving pure ISO markup to validate.
    An AlternateContent with no Fallback is dropped (its Choice content is, by
    definition, extension-only and outside the ISO schema).
    """
    fallback_tag = "{%s}Fallback" % _MC_NS
    for ac in list(doc.iter("{%s}AlternateContent" % _MC_NS)):
        parent = ac.getparent()
        if parent is None:
            continue
        idx = list(parent).index(ac)
        parent.remove(ac)
        fallback = ac.find(fallback_tag)
        if fallback is not None:
            for child in list(fallback):
                parent.insert(idx, child)
                idx += 1
    return doc


def _should_check(partname: str) -> bool:
    return partname in _CHECKED_EXACT or partname.startswith(_CHECKED_PREFIXES)


def _iter_axid_range_violations(name: str, doc) -> "Iterator[tuple[str, str]]":
    """Yield violations for chart axis ids outside PowerPoint's signed-int32 range.

    XSD types ``c:axId`` / ``c:crossAx`` as ``unsignedInt``, so a value in
    ``2**31 .. 2**32-1`` passes schema validation but overflows the signed int
    PowerPoint uses internally, triggering a repair.  This catches that class,
    which pure XSD validation cannot.
    """
    for tag in ("axId", "crossAx"):
        for el in doc.iter("{%s}%s" % (_CHART_NS, tag)):
            raw = el.get("val")
            if raw is None:
                continue
            try:
                val = int(raw)
            except ValueError:
                continue
            if val < 1 or val > _INT32_MAX:
                yield (
                    name,
                    "c:%s val=%s is outside PowerPoint's valid axis-id range "
                    "(1..%d); values >= 2**31 overflow the signed int32 "
                    "PowerPoint uses and trigger a repair" % (tag, raw, _INT32_MAX),
                )


def iter_schema_violations(
    pptx: Union[str, Path, bytes, "io.BytesIO"],
) -> Iterator["tuple[str, str]"]:
    """Yield ``(partname, message)`` for each schema violation in *pptx*.

    *pptx* may be a path, raw ``bytes``, or a file-like object.  Only parts
    with a known root schema are checked; ``mc:AlternateContent`` is resolved
    to its fallback first.  Yields nothing for a schema-clean package.
    """
    if not schema_validation_available():  # pragma: no cover - guarded by tests
        raise RuntimeError("schema validation unavailable (lxml or XSDs missing)")

    if isinstance(pptx, (bytes, bytearray)):
        source: object = io.BytesIO(pptx)
    elif isinstance(pptx, (str, Path)):
        source = str(pptx)
    else:
        source = pptx

    with zipfile.ZipFile(source) as zf:  # type: ignore[arg-type]
        for name in zf.namelist():
            if not name.endswith(".xml") or not _should_check(name):
                continue
            try:
                doc = etree.fromstring(zf.read(name))
            except etree.XMLSyntaxError as exc:
                yield (name, "not well-formed XML: %s" % exc)
                continue
            # PowerPoint-specific range check the XSD can't express.
            yield from _iter_axid_range_violations(name, doc)
            schema = _schema_for_namespace(etree.QName(doc).namespace)
            if schema is None:
                continue
            _resolve_mce(doc)
            if not schema.validate(doc):
                for err in schema.error_log:  # type: ignore[attr-defined]
                    yield (name, "line %s: %s" % (err.line, err.message))


def assert_schema_valid(pptx: Union[str, Path, bytes, "io.BytesIO"]) -> None:
    """Raise ``AssertionError`` listing every schema violation in *pptx*."""
    violations = list(iter_schema_violations(pptx))
    if violations:
        detail = "\n".join("  [%s] %s" % (part, msg) for part, msg in violations)
        raise AssertionError(
            "%d OOXML schema violation(s):\n%s" % (len(violations), detail)
        )
