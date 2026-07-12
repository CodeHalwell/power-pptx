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
import posixpath
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

# Relationship + content-type namespaces, for the structural checks below that
# catch repair triggers the XSD cannot express (dangling ``r:id`` references,
# duplicate shape ids, parts absent from ``[Content_Types].xml``).
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

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


# Slide-like parts whose ``p:cNvPr`` shape ids must be unique within the part.
# PowerPoint reports a deck as needing repair when two shapes on the same slide
# share an id — a class the XSD (which types the id as a bare ``unsignedInt``)
# cannot express.
_ID_CHECKED_PREFIXES = (
    "ppt/slides/slide",
    "ppt/slideLayouts/slideLayout",
    "ppt/slideMasters/slideMaster",
    "ppt/notesSlides/notesSlide",
    "ppt/notesMasters/notesMaster",
)


def _rels_partname_for(partname: str) -> str:
    """Return the ``.rels`` partname that holds *partname*'s relationships."""
    folder, base = posixpath.split(partname)
    return posixpath.join(folder, "_rels", base + ".rels")


def _iter_duplicate_shape_id_violations(name: str, doc) -> "Iterator[tuple[str, str]]":
    """Yield violations for non-unique ``p:cNvPr`` shape ids within one part.

    Two shapes sharing an id on the same slide is a classic "PowerPoint repairs
    the file" trigger that pure XSD validation (``unsignedInt``) cannot catch.
    """
    seen: "dict[str, str]" = {}
    for el in doc.iter():
        if etree.QName(el).localname != "cNvPr":
            continue
        sid = el.get("id")
        if sid is None:
            continue
        if sid in seen:
            yield (
                name,
                "duplicate shape id %s (used by %r and %r) — PowerPoint repairs "
                "decks whose shape ids are not unique within this part"
                % (sid, seen[sid], el.get("name")),
            )
        else:
            seen[sid] = el.get("name")


def _iter_content_type_violations(zf, names) -> "Iterator[tuple[str, str]]":
    """Yield a violation for any package part not declared in ``[Content_Types].xml``.

    A part with no matching ``Default`` (by extension) or ``Override`` (by
    partname) makes PowerPoint reject the package — invisible to per-part XSD
    validation, which never looks at the content-types stream.
    """
    try:
        ct = etree.fromstring(zf.read("[Content_Types].xml"))
    except KeyError:
        yield ("[Content_Types].xml", "package is missing [Content_Types].xml")
        return
    except etree.XMLSyntaxError as exc:
        # Report rather than crash — the harness exists to surface structural
        # problems, and a corrupt content-types stream is itself a fatal one.
        yield ("[Content_Types].xml", "not well-formed XML: %s" % exc)
        return
    defaults = {
        e.get("Extension").lower()
        for e in ct.iter("{%s}Default" % _CT_NS)
        if e.get("Extension")
    }
    overrides = {
        e.get("PartName") for e in ct.iter("{%s}Override" % _CT_NS) if e.get("PartName")
    }
    for part in names:
        if part.endswith("/") or part == "[Content_Types].xml":
            continue
        if "/_rels/" in part or part.startswith("_rels/"):
            ext = "rels"
        elif "." in part:
            ext = part.rsplit(".", 1)[-1].lower()
        else:
            ext = ""
        if ext not in defaults and ("/" + part) not in overrides:
            yield (part, "part is not declared in [Content_Types].xml (extension %r)" % ext)


def _rels_source_dir(rels_name: str) -> str:
    """Return the base directory a ``.rels`` part's Targets resolve against.

    Relationship Targets are relative to the directory *containing* the
    ``_rels`` folder, so the package-root ``_rels/.rels`` resolves against the
    package root (``""``) and ``ppt/slides/_rels/slide1.xml.rels`` against
    ``ppt/slides``.
    """
    return posixpath.dirname(posixpath.dirname(rels_name))


def _iter_relationship_violations(zf, names) -> "Iterator[tuple[str, str]]":
    """Yield violations for broken relationships and dangling ``r:id`` references.

    Catches two repair triggers the XSD cannot see: an internal relationship
    whose target part does not exist in the package, and an ``r:id`` /
    ``r:embed`` / ``r:link`` attribute whose target relationship is absent from
    the referencing part's ``.rels``.

    Every ``.rels`` part is checked for missing targets — including the
    package-root ``_rels/.rels`` (whose ``officeDocument`` relationship points
    at ``ppt/presentation.xml``), which a part-driven scan would skip because
    the package root is not itself an XML part.
    """
    name_set = set(names)

    # -- 1. every relationship in every .rels part must resolve to an existing
    # -- part (covers _rels/.rels and all other rels, not just XML parts') --
    for rels_name in sorted(name_set):
        if not rels_name.endswith(".rels"):
            continue
        base = _rels_source_dir(rels_name)
        try:
            rels = etree.fromstring(zf.read(rels_name))
        except etree.XMLSyntaxError as exc:
            # A corrupt .rels part is itself a repair trigger; report and skip.
            yield (rels_name, "not well-formed XML: %s" % exc)
            continue
        for rel in rels.iter("{%s}Relationship" % _PKG_REL_NS):
            if rel.get("TargetMode") == "External":
                continue
            target = rel.get("Target") or ""
            resolved = posixpath.normpath(posixpath.join(base, target)).lstrip("/")
            if resolved not in name_set:
                yield (
                    rels_name,
                    "relationship %s points at missing part %r" % (rel.get("Id"), resolved),
                )

    # -- 2. every r:id / r:embed / r:link reference in a part's content must
    # -- name a relationship declared in that part's .rels --
    for part in sorted(name_set):
        if not part.endswith(".xml") or "/_rels/" in part or part.startswith("_rels/"):
            continue
        rels_name = _rels_partname_for(part)
        rel_ids = set()
        if rels_name in name_set:
            try:
                rels = etree.fromstring(zf.read(rels_name))
            except etree.XMLSyntaxError:
                # Pass 1 already reported this malformed .rels; skip the r:id
                # scan for this part rather than flag every ref as dangling.
                continue
            rel_ids = {rel.get("Id") for rel in rels.iter("{%s}Relationship" % _PKG_REL_NS)}
        try:
            doc = etree.fromstring(zf.read(part))
        except etree.XMLSyntaxError:
            continue  # not-well-formed is reported by the main XSD pass
        for el in doc.iter():
            for attr, value in el.attrib.items():
                if not attr.startswith("{%s}" % _R_NS) or not value:
                    continue
                if value not in rel_ids:
                    yield (
                        part,
                        "dangling %s=%r on <%s> — no such relationship in %s"
                        % (attr.split("}")[1], value, etree.QName(el).localname, rels_name),
                    )


def _iter_duplicate_member_violations(names) -> "Iterator[tuple[str, str]]":
    """Yield a violation for each zip member name that appears more than once.

    OPC (ISO 29500-2) requires part names to be unique within the package;
    a zip carrying two different payloads under one name is rejected or
    repaired by PowerPoint's package reader, while ``zipfile`` reads it
    silently (returning only the last payload), so nothing else notices.
    """
    seen: "set[str]" = set()
    reported: "set[str]" = set()
    for name in names:
        if name in seen and name not in reported:
            reported.add(name)
            yield (name, "zip member name appears more than once in the package")
        seen.add(name)


def _iter_orphan_slide_violations(zf, names) -> "Iterator[tuple[str, str]]":
    """Yield a violation for each slide part not registered in ``p:sldIdLst``.

    A ``ppt/slides/slideN.xml`` part that no ``p:sldId`` entry resolves to is
    invisible in the deck yet still validated/loaded by PowerPoint — the
    signature of a botched copy operation (and the partname it squats on can
    collide with the next added slide).
    """
    name_set = set(names)
    if "ppt/presentation.xml" not in name_set:
        return
    try:
        prs = etree.fromstring(zf.read("ppt/presentation.xml"))
        rels = etree.fromstring(zf.read("ppt/_rels/presentation.xml.rels"))
    except (KeyError, etree.XMLSyntaxError):
        return  # reported by the content/rels passes
    rel_targets = {
        rel.get("Id"): posixpath.normpath(
            posixpath.join("ppt", rel.get("Target") or "")
        ).lstrip("/")
        for rel in rels.iter("{%s}Relationship" % _PKG_REL_NS)
        if rel.get("TargetMode") != "External"
    }
    p_ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
    registered = set()
    for sldId in prs.iter("{%s}sldId" % p_ns):
        rId = sldId.get("{%s}id" % _R_NS)
        target = rel_targets.get(rId)
        if target is not None:
            registered.add(target)
    for part in sorted(name_set):
        if not part.startswith("ppt/slides/slide") or not part.endswith(".xml"):
            continue
        if part not in registered:
            yield (
                part,
                "slide part is not referenced by any p:sldId in "
                "ppt/presentation.xml — an orphan slide left by a copy "
                "operation",
            )


def iter_schema_violations(
    pptx: Union[str, Path, bytes, "io.BytesIO"],
) -> Iterator["tuple[str, str]"]:
    """Yield ``(partname, message)`` for each schema violation in *pptx*.

    *pptx* may be a path, raw ``bytes``, or a file-like object.  Only parts
    with a known root schema are checked against the XSDs; ``mc:AlternateContent``
    is resolved to its fallback first.  In addition, five package-wide
    structural checks run that the XSD cannot express — duplicate zip member
    names, parts missing from ``[Content_Types].xml``, broken/dangling
    relationships, slide parts absent from ``p:sldIdLst``, and duplicate shape
    ids — because each is a real "PowerPoint repairs the file" trigger.  Yields
    nothing for a clean package.
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
        names = zf.namelist()

        # -- package-level structural checks (content types + relationships) --
        yield from _iter_duplicate_member_violations(names)
        yield from _iter_content_type_violations(zf, names)
        yield from _iter_relationship_violations(zf, names)
        yield from _iter_orphan_slide_violations(zf, names)

        for name in names:
            if not name.endswith(".xml"):
                continue
            # Duplicate-shape-id check runs on the raw part (before any mce
            # resolution) for every slide-like part, not just XSD-checked ones.
            if name.startswith(_ID_CHECKED_PREFIXES):
                try:
                    raw_doc = etree.fromstring(zf.read(name))
                except etree.XMLSyntaxError:
                    raw_doc = None
                if raw_doc is not None:
                    yield from _iter_duplicate_shape_id_violations(name, raw_doc)

            if not _should_check(name):
                continue
            try:
                doc = etree.fromstring(zf.read(name))
            except etree.XMLSyntaxError as exc:
                yield (name, "not well-formed XML: %s" % exc)
                continue
            # PowerPoint-specific range check the XSD can't express. axId /
            # crossAx only occur in chart parts, so skip the scan elsewhere.
            if name.startswith("ppt/charts/chart"):
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
