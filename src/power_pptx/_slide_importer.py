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

* The notes master — the copied notes slide is re-linked to the destination's
  own notes master; the source's is cloned only when the destination has none.
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
        """Clone *src_layout_part* and attach it to *dst_master_part*.

        Copies the layout's own dependencies (background pictures etc.),
        wires the layout ↔ master relationships, and registers the layout in
        the master's `p:sldLayoutIdLst` with a fresh unique id — an
        unregistered layout is invisible to PowerPoint's layout picker and
        leaves the master's id list inconsistent with its relationships.
        """
        new_partname = self._next_partname("/ppt/slideLayouts/slideLayout%d.xml")
        dst_layout_part = _clone_xml_part(src_layout_part, new_partname, self._dst_package)
        id_map = self._copy_dependencies(src_layout_part, dst_layout_part)
        _remap_rids(dst_layout_part._element, id_map)  # pyright: ignore[reportPrivateUsage]
        # Relate layout → master
        dst_layout_part.relate_to(dst_master_part, RT.SLIDE_MASTER)
        # Relate master → layout
        rId = dst_master_part.relate_to(dst_layout_part, RT.SLIDE_LAYOUT)
        # Register in the master's layout-id list
        master_element = dst_master_part._element  # pyright: ignore[reportPrivateUsage]
        sldLayoutIdLst = master_element.get_or_add_sldLayoutIdLst()
        entry = sldLayoutIdLst._add_sldLayoutId(rId=rId)
        entry.set("id", str(self._next_hierarchy_id()))
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
        id_map = self._copy_dependencies(src_master_part, dst_master_part)
        _remap_rids(dst_master_part._element, id_map)  # pyright: ignore[reportPrivateUsage]

        # The deep-copied master XML still carries the *source* master's
        # `p:sldLayoutIdLst` — its r:id values point at whatever landed on
        # those rIds in the new rels (the theme, off-by-one layouts), which
        # PowerPoint cannot resolve.  Empty it here and rebuild it entry by
        # entry as each layout is cloned below.
        master_element = dst_master_part._element  # pyright: ignore[reportPrivateUsage]
        sldLayoutIdLst = master_element.get_or_add_sldLayoutIdLst()
        for stale_entry in list(sldLayoutIdLst):
            sldLayoutIdLst.remove(stale_entry)

        # --- Register new master with presentation (fresh unique id) ---
        rId = self._dst_prs_part.relate_to(dst_master_part, RT.SLIDE_MASTER)
        prs_element = self._dst_prs_part._element  # pyright: ignore[reportPrivateUsage]
        sldMasterIdLst = prs_element.get_or_add_sldMasterIdLst()
        master_entry = sldMasterIdLst._add_sldMasterId(rId=rId)  # pyright: ignore[reportAttributeAccessIssue]
        master_entry.set("id", str(self._next_hierarchy_id()))

        # --- Clone layouts, preserving the source master's layout order ---
        src_to_dst_layout: dict[SlideLayoutPart, SlideLayoutPart] = {}
        for src_lo in self._iter_master_layouts(src_master_part):
            src_to_dst_layout[src_lo] = self._clone_layout_into_master(src_lo, dst_master_part)

        # Return the cloned version of the source layout
        dst_layout = src_to_dst_layout.get(src_layout_part)
        if dst_layout is None:
            # Fallback: use the first available layout
            dst_layout = next(iter(src_to_dst_layout.values()), None)
        if dst_layout is None:
            # Emergency: clone the layout directly
            dst_layout = self._clone_layout_into_master(src_layout_part, dst_master_part)  # type: ignore[assignment]
        return dst_layout  # type: ignore[return-value]

    def _iter_master_layouts(self, master_part: SlideMasterPart) -> list[SlideLayoutPart]:
        """Return *master_part*'s layout parts, in `p:sldLayoutIdLst` order.

        Falls back to relationship order for a master whose layout-id list is
        absent or entirely unresolvable.
        """
        layouts: list[SlideLayoutPart] = []
        sldLayoutIdLst = master_part._element.sldLayoutIdLst  # pyright: ignore[reportPrivateUsage]
        if sldLayoutIdLst is not None:
            for entry in sldLayoutIdLst.sldLayoutId_lst:
                try:
                    layouts.append(master_part.related_part(entry.rId))  # type: ignore[arg-type]
                except KeyError:
                    continue
        if layouts:
            return layouts
        return [
            rel.target_part  # type: ignore[misc]
            for rel in master_part.rels.values()
            if not rel.is_external and rel.reltype == RT.SLIDE_LAYOUT
        ]

    def _next_hierarchy_id(self) -> int:
        """Return a fresh unique id for a `p:sldMasterId` / `p:sldLayoutId` entry.

        These share one id space starting at 2147483648 (ST_SlideMasterId /
        ST_SlideLayoutId minimum); duplicates across the presentation are a
        repair trigger, so scan every master's layout-id list plus the
        presentation's master-id list for the current maximum.
        """
        used = [2147483647]
        prs_element = self._dst_prs_part._element  # pyright: ignore[reportPrivateUsage]
        used += [int(v) for v in prs_element.xpath("p:sldMasterIdLst/p:sldMasterId/@id")]
        for dst_master_part in self._iter_dst_masters():
            used += [
                int(v)
                for v in dst_master_part._element.xpath(  # pyright: ignore[reportPrivateUsage]
                    "p:sldLayoutIdLst/p:sldLayoutId/@id"
                )
            ]
        return max(used) + 1

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

        # Seed the part map with the slide itself so a copied notes slide's
        # back-reference to its slide resolves to *this* part rather than
        # triggering a second, orphan clone of the whole slide graph.
        self._part_map[self._src_slide_part] = dst_slide_part

        # Copy all deps except master-hierarchy rels.  Track source-rId ->
        # destination-rId so the cloned slide XML's embedded references
        # (r:embed, r:id, …) can be rewritten to the new ids.
        id_map = self._copy_dependencies(self._src_slide_part, dst_slide_part)

        # Always wire layout relationship; map the source layout rId onto the new
        # one in case the slide XML references it.
        layout_rId = dst_slide_part.relate_to(dst_layout_part, RT.SLIDE_LAYOUT)
        for rel in self._src_slide_part.rels.values():
            if rel.reltype == RT.SLIDE_LAYOUT:
                id_map[rel.rId] = layout_rId
                break

        _remap_rids(dst_slide_part._element, id_map)  # pyright: ignore[reportPrivateUsage]
        return dst_slide_part  # type: ignore[return-value]

    def _copy_dependencies(self, src_part: Part, dst_part: Part) -> dict[str, str]:
        """Copy *src_part*'s dependencies onto *dst_part*; return the rId map.

        External relationships are re-created verbatim; master-hierarchy
        relationships (layout / master / theme) are skipped — callers wire
        those explicitly; a notes-master relationship is re-pointed at the
        destination's own notes master (importing the source's only when the
        destination has none).  Every other related part is copied
        recursively.  The caller is responsible for running the returned
        source-rId → destination-rId map through :func:`_remap_rids`.
        """
        id_map: dict[str, str] = {}
        for rel in src_part.rels.values():
            if rel.is_external:
                id_map[rel.rId] = dst_part.relate_to(
                    rel.target_ref, rel.reltype, is_external=True
                )
                continue
            if rel.reltype in _MASTER_HIERARCHY_RELTYPES:
                continue
            if rel.reltype == _NOTES_MASTER_RELTYPE:
                # Re-point at the destination's own notes master (created
                # from the default template when absent) — a notes slide
                # without its notesSlide→notesMaster relationship risks the
                # repair prompt when notes view is opened or notes printed.
                dst_notes_master = self._dst_prs_part.notes_master_part
                id_map[rel.rId] = dst_part.relate_to(dst_notes_master, RT.NOTES_MASTER)
                continue
            dst_dep = self._copy_part_recursive(rel.target_part)
            id_map[rel.rId] = dst_part.relate_to(dst_dep, rel.reltype)
        return id_map

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

        id_map = self._copy_dependencies(src_part, dst_part)

        # Rewrite embedded rId references in cloned XML parts (e.g. a chart's
        # <c:externalData r:id=…> pointing at its embedded workbook).
        if isinstance(dst_part, XmlPart):
            _remap_rids(dst_part._element, id_map)  # pyright: ignore[reportPrivateUsage]

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


# Relationship-id references embedded in part XML all live in the ``r:``
# namespace (``r:embed``, ``r:id``, ``r:link``, and the SmartArt
# ``dgm:relIds`` ``r:dm``/``r:lo``/``r:qs``/``r:cs``).  When a part is cloned its
# relationships are re-created in copy order, so the new rIds rarely match the
# ones baked into the deep-copied XML — leaving e.g. a picture's
# ``r:embed="rId2"`` pointing at whatever part happened to land on rId2 in the
# destination.  PowerPoint then can't resolve the image and repairs the deck.
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _remap_rids(element, id_map: dict[str, str]) -> None:
    """Rewrite every ``r:*`` attribute on *element*'s tree through *id_map*.

    Only relationship-namespace attributes whose value is a known source rId are
    touched, so non-relationship attributes are never disturbed.
    """
    if not id_map:
        return
    prefix = "{%s}" % _R_NS
    for el in element.iter():
        for name, value in list(el.attrib.items()):
            if name.startswith(prefix) and value in id_map:
                el.set(name, id_map[value])


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
