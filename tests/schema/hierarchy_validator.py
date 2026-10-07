"""Structural checks for the slide-master / slide-layout hierarchy of a saved ``.pptx``.

The XSD cannot express the invariants PowerPoint relies on when it opens the
master/layout hierarchy, and a violation shows up as the "PowerPoint found a
problem with content ... repair" prompt (or a silently lost layout):

* every ``p:sldMasterId`` / ``p:sldLayoutId`` ``r:id`` must resolve, in the
  referencing part's ``.rels``, to a relationship of the *right type*
  (``slideMaster`` / ``slideLayout``) -- not merely to *some* relationship;
* a master must list each of its ``slideLayout`` relationships exactly once;
* each listed layout must point back at the master that lists it;
* the ``id`` values of all masters and layouts share one id space, must be
  unique across the whole presentation and lie in ``2147483648 .. 4294967295``.

Usage mirrors :func:`tests.schema.oxml_schema_validator.iter_schema_violations`::

    violations = list(iter_hierarchy_violations(pptx_bytes_or_path))  # (partname, message)
"""

from __future__ import annotations

import io
import posixpath
import zipfile
from pathlib import Path
from typing import Iterator, Union

from lxml import etree

_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

_RT_SLIDE_MASTER = f"{_R_NS}/slideMaster"
_RT_SLIDE_LAYOUT = f"{_R_NS}/slideLayout"

# -- ST_SlideMasterId / ST_SlideLayoutId: xsd:unsignedInt, minInclusive 2147483648 --
_MIN_ID = 2147483648
_MAX_ID = 4294967295


def _rels_of(zf: zipfile.ZipFile, partname: str) -> "dict[str, tuple[str, str]]":
    """Return ``{rId: (reltype, resolved target partname)}`` for *partname*'s ``.rels``."""
    folder, base = posixpath.split(partname)
    rels_name = posixpath.join(folder, "_rels", base + ".rels")
    if rels_name not in zf.namelist():
        return {}
    root = etree.fromstring(zf.read(rels_name))
    rels: "dict[str, tuple[str, str]]" = {}
    for rel in root.iter("{%s}Relationship" % _PKG_REL_NS):
        if rel.get("TargetMode") == "External":
            continue
        target = posixpath.normpath(posixpath.join(folder, rel.get("Target") or "")).lstrip("/")
        rels[rel.get("Id") or ""] = (rel.get("Type") or "", target)
    return rels


def iter_hierarchy_violations(
    pptx: Union[str, Path, bytes, "io.BytesIO"],
) -> Iterator["tuple[str, str]"]:
    """Yield ``(partname, message)`` for each master/layout hierarchy problem in *pptx*."""
    if isinstance(pptx, (bytes, bytearray)):
        source: object = io.BytesIO(pptx)
    elif isinstance(pptx, (str, Path)):
        source = str(pptx)
    else:
        source = pptx

    with zipfile.ZipFile(source) as zf:  # type: ignore[arg-type]
        names = set(zf.namelist())
        if "ppt/presentation.xml" not in names:
            return
        prs = etree.fromstring(zf.read("ppt/presentation.xml"))
        prs_rels = _rels_of(zf, "ppt/presentation.xml")
        # -- id -> where it was seen first, for the cross-presentation uniqueness check --
        seen_ids: "dict[str, str]" = {}

        def check_id(where: str, raw: "str | None") -> "Iterator[tuple[str, str]]":
            if raw is None:
                yield (where, "entry has no id attribute")
                return
            if not raw.isdigit() or not _MIN_ID <= int(raw) <= _MAX_ID:
                yield (where, "id %r is outside %d..%d" % (raw, _MIN_ID, _MAX_ID))
            if raw in seen_ids:
                yield (where, "id %s is already used by %s" % (raw, seen_ids[raw]))
            else:
                seen_ids[raw] = where

        for entry in prs.iter("{%s}sldMasterId" % _P_NS):
            rId = entry.get("{%s}id" % _R_NS)
            reltype, master_name = prs_rels.get(rId or "", ("", ""))
            if reltype != _RT_SLIDE_MASTER:
                yield (
                    "ppt/presentation.xml",
                    "sldMasterId r:id=%r resolves to %r (%s), not a slideMaster relationship"
                    % (rId, master_name or None, reltype or "no relationship"),
                )
                continue
            yield from check_id("sldMasterId -> %s" % master_name, entry.get("id"))
            yield from _iter_master_violations(zf, names, master_name, check_id)


def _iter_master_violations(zf, names, master_name, check_id) -> "Iterator[tuple[str, str]]":
    """Yield the layout-list problems of one master part."""
    if master_name not in names:
        yield (master_name, "slide master part is missing from the package")
        return
    master = etree.fromstring(zf.read(master_name))
    master_rels = _rels_of(zf, master_name)

    listed: "list[str]" = []
    for entry in master.iter("{%s}sldLayoutId" % _P_NS):
        rId = entry.get("{%s}id" % _R_NS)
        reltype, layout_name = master_rels.get(rId or "", ("", ""))
        if reltype != _RT_SLIDE_LAYOUT:
            yield (
                master_name,
                "sldLayoutId r:id=%r resolves to %r (%s), not a slideLayout relationship"
                % (rId, layout_name or None, reltype or "no relationship"),
            )
            continue
        listed.append(layout_name)
        yield from check_id("sldLayoutId -> %s" % layout_name, entry.get("id"))
        if layout_name not in names:
            yield (master_name, "listed layout %s is missing from the package" % layout_name)
            continue
        layout_rels = _rels_of(zf, layout_name)
        back = [t for rt, t in layout_rels.values() if rt == _RT_SLIDE_MASTER]
        if back != [master_name]:
            yield (
                layout_name,
                "layout is listed by %s but its slideMaster relationship targets %s"
                % (master_name, back or "nothing"),
            )

    related = [t for rt, t in master_rels.values() if rt == _RT_SLIDE_LAYOUT]
    for layout_name in sorted(set(related) - set(listed)):
        yield (master_name, "layout %s is related to the master but not listed" % layout_name)
    for layout_name in sorted({n for n in listed if listed.count(n) > 1}):
        yield (master_name, "layout %s is listed more than once" % layout_name)
