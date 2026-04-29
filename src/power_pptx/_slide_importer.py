"""Slide import machinery for Presentation.import_slide().

Copies a slide from one |Presentation| into another, rewriting part-names
and relationship targets so the imported slide is indistinguishable from a
natively authored one.

The public entry point is :func:`import_slide`.  Everything else is an
implementation detail.

Supported ``merge_master`` values:

``'dedupe'``
    Reuse an existing destination master when its (normalised) XML fingerprint
    matches the source master.  Otherwise clone the master.

``'clone'``
    Always clone the master and its layout/theme parts, even when the
    destination already has an identical master.

Copied content
--------------
The following slide-level parts are copied:

* The slide itself.
* Its notes slide (if any).
* All image / media / chart / OLE-object / SmartArt-diagram / video parts
  reachable from the slide.
* The slide layout (always cloned — layouts belong to a specific master).
* The slide master and its theme (deduped or cloned, see above).

The following are intentionally **not** deep-copied:

* The notes master (shared; destination keeps its own).
* The handout master.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import TYPE_CHECKING, Literal

from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT
from power_pptx.opc.package import Part, PartFactory, XmlPart
from power_pptx.opc.packuri import PackURI

if TYPE_CHECKING:
    from power_pptx.opc.package import _Relationships  # pyright: ignore[reportPrivateUsage]
    from power_pptx.package import Package
    from power_pptx.parts.presentation import PresentationPart
    from power_pptx.parts.slide import SlideLayoutPart, SlideMasterPart, SlidePart
    from power_pptx.slide import Slide

MergeMaster = Literal["dedupe", "clone"]

# Relationship types whose target parts belong to the master / layout hierarchy
# and are therefore handled separately from the general part graph copy.
_MASTER_HIERARCHY_RELTYPES = frozenset(
    {
        RT.SLIDE_LAYOUT,
        RT.SLIDE_MASTER,
        RT.THEME,
    }
)

# Relationship types for parts that travel with the slide (non-master deps)
_NOTES_MASTER_RELTYPE = RT.NOTES_MASTER


def import_slide(
    src_slide_part: SlidePart,
    dst_prs_part: PresentationPart,
    merge_master: MergeMaster = "dedupe",
) -> Slide:
    """Copy *src_slide_part* into *dst_prs_part* and return the new |Slide|.

    Parameters
    ----------
    src_slide_part:
        The :class:`~power_pptx.parts.slide.SlidePart` from the source presentation.
    dst_prs_part:
        The :class:`~power_pptx.parts.presentation.PresentationPart` of the target.
    merge_master:
        ``'dedupe'`` (default) or ``'clone'`` — controls master handling.

    Returns
    -------
    Slide
        The newly imported :class:`~power_pptx.slide.Slide` object.
    """
    importer = _SlideImporter(src_slide_part, dst_prs_part, merge_master)
    return importer.run()


# ---------------------------------------------------------------------------
# Internal implementation
# ---------------------------------------------------------------------------


class _SlideImporter:
    """Stateful helper that performs the import operation."""

    def __init__(
        self,
        src_slide_part: SlidePart,
        dst_prs_part: PresentationPart,
        merge_master: MergeMaster,
    ) -> None:
        self._src_slide_part = src_slide_part
        self._dst_prs_part = dst_prs_part
        self._merge_master = merge_master
        self._dst_package: Package = dst_prs_part.package  # type: ignore[assignment]
        # Mapping: source Part → copied destination Part
        self._part_map: dict[Part, Part] = {}
        # Partnames already picked in this import run (but not yet in the package graph)
        self._reserved_partnames: set[str] = set()

    def run(self) -> Slide:
        """Execute the import and return the new Slide."""
        dst_layout_part = self._resolve_layout()
        dst_slide_part = self._copy_slide(dst_layout_part)
        self._register_slide(dst_slide_part)
        return dst_slide_part.slide

    def _next_partname(self, tmpl: str) -> PackURI:
        """Return the next non-colliding partname for *tmpl*, accounting for parts
        not yet in the package graph that have already been reserved in this run."""
        prefix = tmpl[: (tmpl % 42).find("42")]
        existing = {
            p.partname for p in self._dst_package.iter_parts()
            if p.partname.startswith(prefix)
        }
        taken = existing | {pn for pn in self._reserved_partnames if pn.startswith(prefix)}
        n = 1
        while True:
            candidate = tmpl % n
            if candidate not in taken:
                self._reserved_partnames.add(candidate)
                return PackURI(candidate)
            n += 1

    # ------------------------------------------------------------------
    # Master / layout resolution
    # ------------------------------------------------------------------

    def _resolve_layout(self) -> SlideLayoutPart:
        """Return the destination layout part for the imported slide.

        Either reuses an existing destination master (dedupe) or clones a new
        one (clone or dedupe miss).
        """
        src_layout_part: SlideLayoutPart = self._src_slide_part.part_related_by(RT.SLIDE_LAYOUT)  # type: ignore[assignment]
        src_master_part: SlideMasterPart = src_layout_part.part_related_by(RT.SLIDE_MASTER)  # type: ignore[assignment]

        if self._merge_master == "dedupe":
            existing = self._find_matching_master(src_master_part)
            if existing is not None:
                return self._find_or_clone_layout_in_master(src_layout_part, existing)

        # Clone master + theme + all layouts
        return self._clone_master_with_layout(src_master_part, src_layout_part)

    def _find_matching_master(self, src_master_part: SlideMasterPart) -> SlideMasterPart | None:
        """Return a destination master part whose fingerprint matches src_master_part, or None."""
        src_fp = _master_fingerprint(src_master_part)
        for dst_master_part in self._iter_dst_masters():
            if _master_fingerprint(dst_master_part) == src_fp:
                return dst_master_part
        return None

    def _iter_dst_masters(self):  # type: ignore[return]
        """Yield each SlideMasterPart already in the destination presentation."""
        prs_element = self._dst_prs_part._element  # pyright: ignore[reportPrivateUsage]
        if prs_element.sldMasterIdLst is None:
            return
        for entry in prs_element.sldMasterIdLst.sldMasterId_lst:
            yield self._dst_prs_part.related_part(entry.rId)

    def _find_or_clone_layout_in_master(
        self, src_layout_part: SlideLayoutPart, dst_master_part: SlideMasterPart
    ) -> SlideLayoutPart:
        """Return the layout in *dst_master_part* that best matches *src_layout_part*.

        Matching order:
        1. Same ``<p:cSld name="…">``
        2. Same layout ``type`` attribute
        3. Fall back to first layout in master

        If no layout matches either criterion, the source layout is cloned
        into the destination master.
        """
        src_name = src_layout_part._element.cSld.name  # pyright: ignore[reportPrivateUsage]
        src_type = src_layout_part._element.get("type")  # pyright: ignore[reportPrivateUsage]

        # Walk existing layouts on the destination master
        from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT2

        layout_candidates: list[SlideLayoutPart] = []
        for rel in dst_master_part.rels.values():
            if rel.is_external or rel.reltype != RT2.SLIDE_LAYOUT:
                continue
            layout_candidates.append(rel.target_part)  # type: ignore[arg-type]

        # Priority 1: name match
        for lp in layout_candidates:
            if lp._element.cSld.name == src_name:  # pyright: ignore[reportPrivateUsage]
                return lp  # type: ignore[return-value]

        # Priority 2: type match
        if src_type:
            for lp in layout_candidates:
                if lp._element.get("type") == src_type:  # pyright: ignore[reportPrivateUsage]
                    return lp  # type: ignore[return-value]

        # Priority 3: clone the layout into the existing master
        return self._clone_layout_into_master(src_layout_part, dst_master_part)

    def _clone_layout_into_master(
        self, src_layout_part: SlideLayoutPart, dst_master_part: SlideMasterPart
    ) -> SlideLayoutPart:
        """Clone *src_layout_part* and attach it to *dst_master_part*."""
        new_partname = self._next_partname("/ppt/slideLayouts/slideLayout%d.xml")
        dst_layout_part = _clone_xml_part(src_layout_part, new_partname, self._dst_package)
        # Relate layout → master
        dst_layout_part.relate_to(dst_master_part, RT.SLIDE_MASTER)
        # Relate master → layout
        dst_master_part.relate_to(dst_layout_part, RT.SLIDE_LAYOUT)
        return dst_layout_part  # type: ignore[return-value]

    def _clone_master_with_layout(
        self, src_master_part: SlideMasterPart, src_layout_part: SlideLayoutPart
    ) -> SlideLayoutPart:
        """Clone the master (+ theme + all of its layouts), register with the destination.

        Returns the cloned layout corresponding to *src_layout_part*.
        """
        dst_package = self._dst_package

        # --- Clone theme ---
        dst_theme_part: Part | None = None
        try:
            src_theme_part = src_master_part.part_related_by(RT.THEME)
            theme_partname = self._next_partname("/ppt/theme/theme%d.xml")
            dst_theme_part = _clone_part(src_theme_part, theme_partname, dst_package)
        except KeyError:
            pass  # some masters have no theme

        # --- Clone master ---
        master_partname = self._next_partname("/ppt/slideMasters/slideMaster%d.xml")
        dst_master_part = _clone_xml_part(src_master_part, master_partname, dst_package)
        if dst_theme_part is not None:
            dst_master_part.relate_to(dst_theme_part, RT.THEME)

        # --- Clone layouts ---
        src_to_dst_layout: dict[SlideLayoutPart, SlideLayoutPart] = {}
        for rel in src_master_part.rels.values():
            if rel.is_external or rel.reltype != RT.SLIDE_LAYOUT:
                continue
            src_lo: SlideLayoutPart = rel.target_part  # type: ignore[assignment]
            lo_partname = self._next_partname("/ppt/slideLayouts/slideLayout%d.xml")
            dst_lo = _clone_xml_part(src_lo, lo_partname, dst_package)
            # layout → master
            dst_lo.relate_to(dst_master_part, RT.SLIDE_MASTER)
            # master → layout
            dst_master_part.relate_to(dst_lo, RT.SLIDE_LAYOUT)
            src_to_dst_layout[src_lo] = dst_lo  # type: ignore[assignment]

        # --- Register new master with presentation ---
        rId = self._dst_prs_part.relate_to(dst_master_part, RT.SLIDE_MASTER)
        prs_element = self._dst_prs_part._element  # pyright: ignore[reportPrivateUsage]
        sldMasterIdLst = prs_element.get_or_add_sldMasterIdLst()
        sldMasterIdLst._add_sldMasterId(rId=rId)  # pyright: ignore[reportAttributeAccessIssue]

        # Return the cloned version of the source layout
        dst_layout = src_to_dst_layout.get(src_layout_part)
        if dst_layout is None:
            # Fallback: use the first available layout
            dst_layout = next(iter(src_to_dst_layout.values()), None)
        if dst_layout is None:
            # Emergency: clone the layout directly
            dst_layout = self._clone_layout_into_master(src_layout_part, dst_master_part)  # type: ignore[assignment]
        return dst_layout  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Slide copy
    # ------------------------------------------------------------------

    def _copy_slide(self, dst_layout_part: SlideLayoutPart) -> SlidePart:
        """Return a new SlidePart copied from the source slide.

        All non-master-hierarchy dependencies (images, charts, media, notes, etc.)
        are also copied.  The new slide is related to *dst_layout_part*.
        """
        dst_package = self._dst_package
        new_partname = self._next_partname("/ppt/slides/slide%d.xml")
        dst_slide_part = _clone_xml_part(self._src_slide_part, new_partname, dst_package)

        # Copy all deps except master-hierarchy rels (and notes_master)
        skip = _MASTER_HIERARCHY_RELTYPES | {_NOTES_MASTER_RELTYPE}
        for rel in self._src_slide_part.rels.values():
            if rel.is_external:
                dst_slide_part.relate_to(rel.target_ref, rel.reltype, is_external=True)
                continue
            if rel.reltype in skip:
                continue
            dst_dep = self._copy_part_recursive(rel.target_part)
            dst_slide_part.relate_to(dst_dep, rel.reltype)

        # Always wire layout relationship
        dst_slide_part.relate_to(dst_layout_part, RT.SLIDE_LAYOUT)
        return dst_slide_part  # type: ignore[return-value]

    def _copy_part_recursive(self, src_part: Part) -> Part:
        """Return a copy of *src_part* in the destination package.

        Recursively copies all related parts (depth-first).  Each source part
        is copied at most once; subsequent calls for the same part return the
        already-copied destination counterpart.
        """
        if src_part in self._part_map:
            return self._part_map[src_part]

        dst_package = self._dst_package
        new_partname = self._next_partname(_partname_template(src_part.partname))
        dst_part = _clone_part(src_part, new_partname, dst_package)
        self._part_map[src_part] = dst_part

        for rel in src_part.rels.values():
            if rel.is_external:
                dst_part.relate_to(rel.target_ref, rel.reltype, is_external=True)
                continue
            if rel.reltype in _MASTER_HIERARCHY_RELTYPES | {_NOTES_MASTER_RELTYPE}:
                continue
            dst_dep = self._copy_part_recursive(rel.target_part)
            dst_part.relate_to(dst_dep, rel.reltype)

        return dst_part

    # ------------------------------------------------------------------
    # Presentation registration
    # ------------------------------------------------------------------

    def _register_slide(self, dst_slide_part: SlidePart) -> None:
        """Add the new slide part to the destination presentation."""
        rId = self._dst_prs_part.relate_to(dst_slide_part, RT.SLIDE)
        prs_element = self._dst_prs_part._element  # pyright: ignore[reportPrivateUsage]
        prs_element.get_or_add_sldIdLst().add_sldId(rId)


# ---------------------------------------------------------------------------
# Part-copy helpers
# ---------------------------------------------------------------------------


def _clone_part(src_part: Part, new_partname: PackURI, dst_package: Package) -> Part:
    """Return a new Part in *dst_package* that is a copy of *src_part*.

    For XmlParts the XML is re-parsed (no element sharing between packages).
    For binary Parts the blob bytes are shared (immutable).
    """
    return PartFactory(new_partname, src_part.content_type, dst_package, blob=src_part.blob)


def _clone_xml_part(src_part: XmlPart, new_partname: PackURI, dst_package: Package) -> XmlPart:
    """Return a new XmlPart in *dst_package* that is a copy of *src_part*.

    The XML element tree is deep-copied so mutations on one part do not affect the other.
    No relationships are copied; callers must add them explicitly.
    """
    new_element = deepcopy(src_part._element)  # pyright: ignore[reportPrivateUsage]
    return src_part.__class__(new_partname, src_part.content_type, dst_package, new_element)


def _master_fingerprint(master_part: Part) -> bytes:
    """Return a SHA-256 hash over the normalised master XML + its theme XML.

    Used for master deduplication: two masters with identical fingerprints are
    considered equivalent for the purposes of ``merge_master='dedupe'``.
    """
    h = hashlib.sha256()
    h.update(master_part.blob)
    try:
        theme_part = master_part.part_related_by(RT.THEME)
        h.update(theme_part.blob)
    except KeyError:
        pass
    return h.digest()


def _partname_template(partname: PackURI) -> str:
    """Return a partname template string suitable for ``Package.next_partname()``.

    E.g. ``/ppt/charts/chart3.xml`` → ``/ppt/charts/chart%d.xml``.
    """
    # Split off the trailing number (if any) and extension
    name = partname  # str-like
    # Find the last digit sequence before the extension
    base = name.rsplit(".", 1)
    if len(base) == 2:
        stem, ext = base
    else:
        stem, ext = name, ""

    # Strip trailing digits from stem to get the "root"
    root = stem.rstrip("0123456789")
    if not root.endswith("/") and root == stem:
        # No trailing digits — use the whole stem
        root = stem

    if ext:
        return f"{root}%d.{ext}"
    return f"{root}%d"
