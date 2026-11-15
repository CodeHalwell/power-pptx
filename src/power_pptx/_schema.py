"""Validate generated ``.pptx`` parts against the ISO/IEC 29500 XSD schemas.

PowerPoint rejects (and silently "repairs") files that violate the OOXML
schema even when ``lxml`` / python-pptx / LibreOffice happily accept them — an
empty ``<a:scene3d>``, a colour-less ``<a:outerShdw>``, a negative chart
``axId``, a bare ``<p14:morph>``, and so on.  Those bugs are invisible to the
normal "does it parse / does it reopen" checks, so this module validates the
XML of each generated part against the XSDs bundled in the installed package.

Usage from a test::

    from power_pptx.validation import (
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


# -- locate the bundled XSD schemas (installed package resources) --------------------
_XSD_DIR = Path(__file__).with_name("schemas")

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
_CHECKED_EXACT = ("ppt/presentation.xml", "ppt/presProps.xml")

_schema_cache: "dict[str, object]" = {}


def hardened_parser(**options):
    """Return an XML parser that is safe on a package from an unknown source.

    Entity references are left unresolved and nothing is fetched from the
    network, so a part cannot pull a local file into a violation message
    (XXE) or expand a few bytes into gigabytes.  lxml's default parser
    resolves entities, external ones included before lxml 5.  *options* are
    further ``etree.XMLParser`` arguments.
    """
    return etree.XMLParser(resolve_entities=False, no_network=True, **options)


#: The parser every part in this module is read with.
_PARSER = hardened_parser() if _LXML else None


def parse_xml(data: bytes):
    """Return the root element of package XML *data*, parsed without resolving entities."""
    return etree.fromstring(data, _PARSER)


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
        doc = etree.parse(str(_XSD_DIR / xsd_file), _PARSER)
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


_PML_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"

# ``r:id`` references that only make sense when their relationship is of one
# type: the entries of the presentation's and a slide master's id lists.  Keyed
# by element, the value is the last segment of the relationship type, which is
# the same in the transitional and strict relationship namespaces.  An entry
# that resolves to another kind of part (a master's ``p:sldLayoutId`` naming
# its theme relationship, say) reopens here but is a repair in PowerPoint.
_TYPED_REFERENCES = {
    "{%s}sldLayoutId" % _PML_NS: "slideLayout",
    "{%s}sldMasterId" % _PML_NS: "slideMaster",
    "{%s}sldId" % _PML_NS: "slide",
    "{%s}notesMasterId" % _PML_NS: "notesMaster",
    "{%s}handoutMasterId" % _PML_NS: "handoutMaster",
}

# Descendants of ``p:timing`` whose ``spid`` names the shape they animate or
# build: every animation target, and the paragraph builds of the build list.
_SPID_ELEMENTS = ("{%s}spTgt" % _PML_NS, "{%s}bldP" % _PML_NS)


def _rels_partname_for(partname: str) -> str:
    """Return the ``.rels`` partname that holds *partname*'s relationships."""
    folder, base = posixpath.split(partname)
    return posixpath.join(folder, "_rels", base + ".rels")


def _shape_id_key(raw: str) -> "int | str":
    """Return a shape id in comparable form, so ``"07"`` and ``"7"`` are one id."""
    try:
        return int(raw)
    except ValueError:
        return raw


def _iter_animation_target_violations(name: str, doc) -> "Iterator[tuple[str, str]]":
    """Yield violations for animation targets that name no shape on the slide.

    A ``p:spTgt`` or ``p:bldP`` inside ``p:timing`` refers to its shape by
    id.  When that shape is gone — deleted or replaced without its animations —
    PowerPoint reports the deck as needing repair, while XSD validation only
    sees a well-typed ``unsignedInt``.

    Every ``cNvPr`` in the part counts as a shape, whatever its namespace and
    however deeply it sits in groups or ``mc:AlternateContent`` branches, so a
    reference is reported only when nothing on the slide can be its target.
    """
    timings = list(doc.iter("{%s}timing" % _PML_NS))
    if not timings:
        return
    shape_ids = {
        _shape_id_key(el.get("id"))
        for el in doc.iter("*")
        if etree.QName(el).localname == "cNvPr" and el.get("id") is not None
    }
    reported: "set[tuple[str, int | str]]" = set()
    for timing in timings:
        for el in timing.iter(*_SPID_ELEMENTS):
            raw = el.get("spid")
            if raw is None:
                continue
            key = (el.tag, _shape_id_key(raw))
            if key[1] in shape_ids or key in reported:
                continue
            reported.add(key)
            yield (
                name,
                "p:%s spid=%s names no shape on this slide — PowerPoint repairs "
                "an animation whose target shape is missing" % (etree.QName(el).localname, raw),
            )


def _iter_duplicate_shape_id_violations(name: str, doc) -> "Iterator[tuple[str, str]]":
    """Yield violations for non-unique ``p:cNvPr`` shape ids within one part.

    Two shapes sharing an id on the same slide is a classic "PowerPoint repairs
    the file" trigger that pure XSD validation (``unsignedInt``) cannot catch.
    """
    seen: "dict[str, str]" = {}
    for el in doc.iter("*"):  # -- elements only: a comment has no QName --
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
        ct = parse_xml(zf.read("[Content_Types].xml"))
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

    Catches three repair triggers the XSD cannot see: an internal relationship
    whose target part does not exist in the package, an ``r:id`` /
    ``r:embed`` / ``r:link`` attribute whose target relationship is absent from
    the referencing part's ``.rels``, and an id-list entry (``p:sldLayoutId``,
    ``p:sldId``, …; see ``_TYPED_REFERENCES``) whose relationship is of the
    wrong type.

    Every ``.rels`` part is checked for missing targets — including the
    package-root ``_rels/.rels`` (whose ``officeDocument`` relationship points
    at ``ppt/presentation.xml``), which a part-driven scan would skip because
    the package root is not itself an XML part.
    """
    name_set = set(names)
    yield from _iter_missing_target_violations(zf, name_set)
    yield from _iter_reference_violations(zf, name_set)


def _iter_missing_target_violations(
    zf: zipfile.ZipFile, name_set: "set[str]"
) -> "Iterator[tuple[str, str]]":
    """Yield a violation for each internal relationship whose target part is absent.

    Every relationship in every ``.rels`` part must resolve to an existing part
    (this covers ``_rels/.rels`` and all other rels, not just XML parts').
    """
    for rels_name in sorted(name_set):
        if not rels_name.endswith(".rels"):
            continue
        try:
            rels = parse_xml(zf.read(rels_name))
        except etree.XMLSyntaxError as exc:
            # A corrupt .rels part is itself a repair trigger; report and skip.
            yield (rels_name, "not well-formed XML: %s" % exc)
            continue
        for rel_id, resolved in _internal_targets(rels, _rels_source_dir(rels_name)):
            if resolved not in name_set:
                yield (rels_name, "relationship %s points at missing part %r" % (rel_id, resolved))


def _internal_targets(rels, base: str) -> "Iterator[tuple[str | None, str]]":
    """Yield ``(Id, partname)`` for each internal relationship in the *rels* element.

    Targets are resolved against *base*, the folder the ``.rels`` part's source
    lives in, to a partname without a leading slash.
    """
    for rel in rels.iter("{%s}Relationship" % _PKG_REL_NS):
        if rel.get("TargetMode") == "External":
            continue
        target = rel.get("Target") or ""
        yield rel.get("Id"), posixpath.normpath(posixpath.join(base, target)).lstrip("/")


def _iter_reference_violations(
    zf: zipfile.ZipFile, name_set: "set[str]"
) -> "Iterator[tuple[str, str]]":
    """Yield a violation for each ``r:*`` reference a part's ``.rels`` cannot satisfy.

    Every ``r:id`` / ``r:embed`` / ``r:link`` reference in a part's content
    must name a relationship declared in that part's ``.rels``, and an id-list
    entry must name a relationship of its own kind.
    """
    for part in sorted(name_set):
        if not _is_content_xml(part):
            continue
        rels_name = _rels_partname_for(part)
        try:
            rel_types = _relationship_types(zf, rels_name, name_set)
        except etree.XMLSyntaxError:
            # The missing-target pass already reported this malformed .rels;
            # skip the r:id scan for this part rather than flag every ref as
            # dangling.
            continue
        try:
            doc = parse_xml(zf.read(part))
        except etree.XMLSyntaxError:
            continue  # not-well-formed is reported by the main XSD pass
        yield from _PartReferences(part, rels_name, rel_types).iter_violations(doc)


def _is_content_xml(partname: str) -> bool:
    """True when *partname* is an XML part other than a ``.rels`` part."""
    in_rels_folder = "/_rels/" in partname or partname.startswith("_rels/")
    return partname.endswith(".xml") and not in_rels_folder


def _relationship_types(
    zf: zipfile.ZipFile, rels_name: str, name_set: "set[str]"
) -> "dict[str | None, str]":
    """Return ``{Id: Type}`` for the relationships in the ``.rels`` part *rels_name*.

    A part without a ``.rels`` part has no relationships.  Raises
    ``etree.XMLSyntaxError`` when the ``.rels`` part is not well-formed.
    """
    if rels_name not in name_set:
        return {}
    rels = parse_xml(zf.read(rels_name))
    return {
        rel.get("Id"): rel.get("Type") or ""
        for rel in rels.iter("{%s}Relationship" % _PKG_REL_NS)
    }


class _PartReferences:
    """The ``r:*`` references in one part, checked against the relationships it declares."""

    def __init__(self, part: str, rels_name: str, rel_types: "dict[str | None, str]") -> None:
        self._part = part
        self._rels_name = rels_name
        self._rel_types = rel_types

    def iter_violations(self, doc) -> "Iterator[tuple[str, str]]":
        """Yield a violation for each reference in *doc* that is dangling or mistyped."""
        for el in doc.iter("*"):
            for attr, value in el.attrib.items():
                if not attr.startswith("{%s}" % _R_NS) or not value:
                    continue
                problem = self._problem(el, attr, value)
                if problem is not None:
                    yield (self._part, problem)

    def _problem(self, el, attr: str, value: str) -> "str | None":
        """Return what is wrong with the reference *attr*=*value* on *el*, or None."""
        if value not in self._rel_types:
            return "dangling %s=%r on <%s> — no such relationship in %s" % (
                attr.split("}")[1],
                value,
                etree.QName(el).localname,
                self._rels_name,
            )
        # -- an id-list entry must name a relationship of its kind --
        expected = _TYPED_REFERENCES.get(el.tag)
        if expected is None or attr != "{%s}id" % _R_NS:
            return None
        actual = self._rel_types[value].rsplit("/", 1)[-1]
        if actual == expected:
            return None
        return (
            "<%s> r:id=%r resolves to a relationship of type %r, not %r — "
            "PowerPoint repairs an id list that points at the wrong kind of part"
            % (etree.QName(el).localname, value, actual, expected)
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


def _iter_dtd_violations(zf, names) -> "Iterator[tuple[str, str]]":
    """Yield a violation for each XML part that carries a DOCTYPE declaration.

    OPC (ISO/IEC 29500-2, "XML usage") forbids DTD declarations in package
    XML and PowerPoint refuses such a part.  A DTD is also the only way to
    declare the entities behind XXE and "billion laughs" payloads; this module
    never resolves those (see :func:`hardened_parser`), so a part that uses
    them cannot be validated further and is reported here instead.
    """
    for name in dict.fromkeys(names):
        if not name.endswith((".xml", ".rels")):
            continue
        data = zf.read(name)
        if b"<!DOCTYPE" not in data:
            continue  # -- cheap pre-check that ends it for every ordinary part --
        try:
            root = parse_xml(data)
        except etree.XMLSyntaxError:
            continue  # -- reported by the passes that read the part --
        # -- the text can also sit in a comment or CDATA section; ask the parser --
        if root.getroottree().docinfo.doctype:
            yield (
                name,
                "part declares a DTD (<!DOCTYPE ...>) — OPC forbids DTD "
                "declarations in package XML and PowerPoint rejects the part",
            )


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
        prs = parse_xml(zf.read("ppt/presentation.xml"))
        rels = parse_xml(zf.read("ppt/_rels/presentation.xml.rels"))
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
    is resolved to its fallback first.  In addition, package-wide structural
    checks run that the XSD cannot express — duplicate zip member names, parts
    that declare a DTD, parts missing from ``[Content_Types].xml``,
    broken/dangling relationships, id-list entries (``p:sldLayoutId``,
    ``p:sldId``, …) whose relationship is of the wrong type, slide parts absent
    from ``p:sldIdLst``, duplicate shape ids, and animation targets that name no
    shape on their slide — because each is a real "PowerPoint repairs the file"
    trigger.  Yields nothing for a clean package.

    Parts are parsed without resolving entities or touching the network, so
    validating a package from an unknown source is safe.
    """
    if not schema_validation_available():  # pragma: no cover - guarded by tests
        raise RuntimeError("schema validation unavailable (lxml or XSDs missing)")

    with zipfile.ZipFile(_zip_source(pptx)) as zf:  # type: ignore[arg-type]
        names = zf.namelist()

        # -- package-level structural checks (content types + relationships) --
        yield from _iter_duplicate_member_violations(names)
        yield from _iter_dtd_violations(zf, names)
        yield from _iter_content_type_violations(zf, names)
        yield from _iter_relationship_violations(zf, names)
        yield from _iter_orphan_slide_violations(zf, names)

        # -- then the content of each XML part, one part at a time --
        for name in names:
            if not name.endswith(".xml"):
                continue
            yield from _iter_shape_reference_violations(zf, name)
            yield from _iter_xsd_violations(zf, name)


def _zip_source(pptx: Union[str, Path, bytes, "io.BytesIO"]) -> object:
    """Return *pptx* as something ``zipfile.ZipFile`` opens: a path string or a stream."""
    if isinstance(pptx, (bytes, bytearray)):
        return io.BytesIO(pptx)
    if isinstance(pptx, (str, Path)):
        return str(pptx)
    return pptx


def _iter_shape_reference_violations(
    zf: zipfile.ZipFile, name: str
) -> "Iterator[tuple[str, str]]":
    """Yield duplicate-shape-id and missing-animation-target violations for part *name*.

    These run on the raw part (before any mce resolution) for every
    slide-like part, not just XSD-checked ones.  A part that is not
    well-formed is left to the schema pass to report.
    """
    if not name.startswith(_ID_CHECKED_PREFIXES):
        return
    try:
        doc = parse_xml(zf.read(name))
    except etree.XMLSyntaxError:
        return
    yield from _iter_duplicate_shape_id_violations(name, doc)
    if name.startswith("ppt/slides/slide"):
        yield from _iter_animation_target_violations(name, doc)


def _iter_xsd_violations(zf: zipfile.ZipFile, name: str) -> "Iterator[tuple[str, str]]":
    """Yield the violations of part *name* against its XSD, when it has one."""
    if not _should_check(name):
        return
    try:
        doc = parse_xml(zf.read(name))
    except etree.XMLSyntaxError as exc:
        yield (name, "not well-formed XML: %s" % exc)
        return
    # PowerPoint-specific range check the XSD can't express. axId /
    # crossAx only occur in chart parts, so skip the scan elsewhere.
    if name.startswith("ppt/charts/chart"):
        yield from _iter_axid_range_violations(name, doc)
    schema = _schema_for_namespace(etree.QName(doc).namespace)
    if schema is None:
        return
    yield from _iter_schema_errors(name, schema, _resolve_mce(doc))


def _iter_schema_errors(name: str, schema, doc) -> "Iterator[tuple[str, str]]":
    """Yield a violation for each error *schema* finds in the part *name* parsed as *doc*."""
    try:
        valid = schema.validate(doc)  # type: ignore[attr-defined]
    except etree.XMLSchemaError as exc:
        # -- libxml2 cannot validate a tree that holds entity references,
        # -- which are deliberately left unresolved; say so rather than
        # -- pass the part as clean --
        yield (name, "could not be validated against the schema: %s" % exc)
        return
    if not valid:
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
