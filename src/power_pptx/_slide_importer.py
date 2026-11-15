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
  reachable from the slide.  An image or media file the destination already
  holds (same bytes) is reused rather than copied again.
* The slide layout (always cloned — layouts belong to a specific master).
* The slide master and its theme (deduped or cloned, see above).

The following are intentionally **not** deep-copied:

* The notes master — the copied notes slide is re-linked to the destination's
  own notes master; the source's is cloned only when the destination has none.
* The handout master.
* **Other slides.**  A "jump to slide" link (``click_action.target_slide``,
  a text-run hyperlink to a slide) is a relationship to another slide.  It is
  re-pointed when the target is already in the destination — a same-deck
  import, or a slide imported earlier into the same |Presentation| object —
  and removed otherwise.  The target slide is never brought along: the caller
  did not ask for it, and an unregistered slide part corrupts the package.
"""

from __future__ import annotations

import hashlib
import weakref
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Literal

from power_pptx.opc.constants import CONTENT_TYPE as CT
from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT
from power_pptx.opc.package import Part, PartFactory, XmlPart
from power_pptx.opc.packuri import PackURI, numbered_partname_pieces

if TYPE_CHECKING:
    from power_pptx.package import Package
    from power_pptx.parts.presentation import PresentationPart
    from power_pptx.parts.slide import SlideLayoutPart, SlideMasterPart, SlidePart
    from power_pptx.presentation import Presentation
    from power_pptx.slide import Slide

MergeMaster = Literal["dedupe", "clone"]

_MERGE_MASTER_VALUES: tuple[str, ...] = ("dedupe", "clone")

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

# Relationship types whose targets are opaque binary payloads (pictures,
# video, audio).  Such a part is immutable and has no relationships of its
# own, so one copy can safely serve every slide that uses the same bytes.
_SHARED_BINARY_RELTYPES = frozenset({RT.IMAGE, RT.MEDIA, RT.VIDEO, RT.AUDIO})

# Local names of the DrawingML elements that carry a hyperlink relationship.
# When the relationship they name is not carried over, the whole element goes:
# a hyperlink element without its `r:id` is a link to nowhere.
_HYPERLINK_TAGS = frozenset({"hlinkClick", "hlinkHover", "hlinkMouseOver"})

# Destination package → {source slide part → weakref to the slide part it was
# imported as}.  Lets a later import re-point a "jump to slide" link at a
# slide that an earlier `import_slide()` call already brought across.  Both
# levels are weak so neither the source nor the destination deck is kept
# alive by this bookkeeping.
_IMPORTED_SLIDES: "weakref.WeakKeyDictionary[Any, Any]" = weakref.WeakKeyDictionary()


def import_slide(
    presentation: Presentation | PresentationPart | Slide | SlidePart | None = None,
    slide: Slide | SlidePart | Presentation | PresentationPart | None = None,
    merge_master: MergeMaster = "dedupe",
    *,
    src_slide_part: SlidePart | None = None,
    dst_prs_part: PresentationPart | None = None,
) -> Slide:
    """Copy *slide* into *presentation* and return the new |Slide|.

    ::

        from power_pptx.compose import import_slide

        new_slide = import_slide(dst, src.slides[3], merge_master="dedupe")

    This is the function form of :meth:`Presentation.import_slide()
    <power_pptx.presentation.Presentation.import_slide>`.

    Parameters
    ----------
    presentation:
        The destination |Presentation| (or its
        :class:`~power_pptx.parts.presentation.PresentationPart`).
    slide:
        The |Slide| to copy (or its :class:`~power_pptx.parts.slide.SlidePart`),
        from any presentation, including the destination itself.
    merge_master:
        ``'dedupe'`` (default) or ``'clone'`` — controls master handling.
        Any other value raises :class:`ValueError`.

    The two objects are told apart by type, so the original part-based call
    ``import_slide(src_slide_part, dst_prs_part)`` (source first) and its
    ``src_slide_part=`` / ``dst_prs_part=`` keywords keep working.

    Returns
    -------
    Slide
        The newly imported :class:`~power_pptx.slide.Slide` object.
    """
    source_part, destination_part = _resolve_import_arguments(
        presentation, slide, src_slide_part, dst_prs_part
    )
    return _import_slide_part(source_part, destination_part, merge_master)


def _import_slide_part(
    src_slide_part: SlidePart,
    dst_prs_part: PresentationPart,
    merge_master: MergeMaster = "dedupe",
) -> Slide:
    """Copy *src_slide_part* into the presentation of *dst_prs_part*; return the new |Slide|."""
    if merge_master not in _MERGE_MASTER_VALUES:
        raise ValueError("merge_master must be 'dedupe' or 'clone', got %r" % (merge_master,))
    importer = _SlideImporter(src_slide_part, dst_prs_part, merge_master)
    return importer.run()


def _resolve_import_arguments(
    first: object,
    second: object,
    src_slide_part: object,
    dst_prs_part: object,
) -> tuple[SlidePart, PresentationPart]:
    """Return (source slide part, destination presentation part) from the call's arguments.

    Accepts the proxy objects (|Presentation|, |Slide|) or their parts, in
    either order, plus the two legacy keywords.
    """
    from power_pptx.parts.presentation import PresentationPart

    slide_part: SlidePart | None = None
    prs_part: PresentationPart | None = None

    for arg in (first, second, src_slide_part, dst_prs_part):
        if arg is None:
            continue
        part = _import_argument_part(arg)
        if isinstance(part, PresentationPart):
            if prs_part is not None:
                raise TypeError("import_slide() got more than one destination presentation")
            prs_part = part
        else:
            if slide_part is not None:
                raise TypeError("import_slide() got more than one slide to import")
            slide_part = part

    if prs_part is None:
        raise TypeError("import_slide() needs the destination Presentation")
    if slide_part is None:
        raise TypeError("import_slide() needs the Slide to import")
    return slide_part, prs_part


def _import_argument_part(arg: object) -> SlidePart | PresentationPart:
    """Return the slide or presentation part behind one argument of `import_slide()`.

    *arg* is a |Presentation| or |Slide| proxy, or one of their parts; anything
    else raises |TypeError|.
    """
    from power_pptx.parts.presentation import PresentationPart
    from power_pptx.parts.slide import SlidePart
    from power_pptx.presentation import Presentation
    from power_pptx.slide import Slide

    part = arg.part if isinstance(arg, (Presentation, Slide)) else arg
    if isinstance(part, (PresentationPart, SlidePart)):
        return part
    raise TypeError("import_slide() takes a Presentation and a Slide, got %s" % type(arg).__name__)


# ---------------------------------------------------------------------------
# Internal implementation
# ---------------------------------------------------------------------------


class _PartCopier:
    """Copies parts, and everything they depend on, into a destination presentation.

    Shared by slide import and template application: both need to bring a
    master, its theme, its layouts and their pictures across intact, with
    non-colliding partnames and relationship ids rewritten to match.

    One instance covers one operation; it remembers what it has copied so a
    part reachable by two routes is copied once.
    """

    def __init__(self, dst_prs_part: PresentationPart) -> None:
        self._dst_prs_part = dst_prs_part
        self._dst_package: Package = dst_prs_part.package  # type: ignore[assignment]
        # Mapping: source Part → copied (or reused) destination Part
        self.part_map: dict[Part, Part] = {}
        # Partnames already picked in this run (but not yet in the package graph)
        self._reserved_partnames: set[str] = set()
        # (content-type, sha1) → binary part available in the destination;
        # built on first use, see `_binary_parts`.
        self._binary_index: dict[tuple[str, str], Part] | None = None

    # ------------------------------------------------------------------
    # Partnames
    # ------------------------------------------------------------------

    def next_partname(self, prefix: str, suffix: str) -> PackURI:
        """Return the next free partname of the form `{prefix}{n}{suffix}`.

        Accounts for parts copied earlier in this run that are not reachable
        from the package graph yet.  *prefix* and *suffix* are used verbatim —
        no printf formatting — so a name containing ``%`` is safe.
        """
        taken = {p.partname.lower() for p in self._dst_package.iter_parts()}
        taken |= self._reserved_partnames
        n = 1
        while True:
            candidate = "%s%d%s" % (prefix, n, suffix)
            if candidate.lower() not in taken:
                self._reserved_partnames.add(candidate.lower())
                return PackURI(candidate)
            n += 1

    # ------------------------------------------------------------------
    # Generic part-graph copy
    # ------------------------------------------------------------------

    def copy_dependencies(self, src_part: Part, dst_part: Part) -> tuple[dict[str, str], set[str]]:
        """Copy *src_part*'s dependencies onto *dst_part*.

        Returns ``(id_map, dropped)``: the source-rId → destination-rId map,
        and the source rIds that were deliberately not carried over.  The
        caller runs both through :func:`_remap_rids` on the copied XML.

        External relationships are re-created verbatim; master-hierarchy
        relationships (layout / master / theme) are skipped — callers wire
        those explicitly; a notes-master relationship is re-pointed at the
        destination's own notes master (importing the source's only when the
        destination has none).  A relationship to a *slide* is re-pointed at
        that slide's counterpart in the destination when there is one and
        dropped otherwise — the slide itself is never copied.  Every other
        related part is copied recursively.
        """
        id_map: dict[str, str] = {}
        dropped: set[str] = set()
        for rel in src_part.rels.values():
            if rel.is_external:
                id_map[rel.rId] = dst_part.relate_to(rel.target_ref, rel.reltype, is_external=True)
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
            target_part = rel.target_part
            if rel.reltype == RT.SLIDE or target_part.content_type == CT.PML_SLIDE:
                dst_slide_part = self._destination_slide_for(target_part)
                if dst_slide_part is None:
                    dropped.add(rel.rId)
                else:
                    id_map[rel.rId] = dst_part.relate_to(dst_slide_part, rel.reltype)
                continue
            dst_dep = self.copy_part(target_part, rel.reltype)
            id_map[rel.rId] = dst_part.relate_to(dst_dep, rel.reltype)
        return id_map, dropped

    def copy_part(self, src_part: Part, reltype: str | None = None) -> Part:
        """Return the destination counterpart of *src_part*, copying it if need be.

        Recursively copies all related parts (depth-first).  Each source part
        is copied at most once; subsequent calls for the same part return the
        already-copied destination counterpart.  *reltype* is the type of the
        relationship the part was reached by; a picture or media file the
        destination already holds is reused instead of copied.
        """
        if src_part in self.part_map:
            return self.part_map[src_part]

        binary_key = _binary_key(src_part) if _is_shared_binary(src_part, reltype) else None
        if binary_key is not None:
            existing = self._binary_parts.get(binary_key)
            if existing is not None:
                self.part_map[src_part] = existing
                return existing

        prefix, suffix = _numbered_partname(src_part.partname)
        dst_part = _clone_part(src_part, self.next_partname(prefix, suffix), self._dst_package)
        self.part_map[src_part] = dst_part
        if binary_key is not None:
            self._binary_parts[binary_key] = dst_part

        id_map, dropped = self.copy_dependencies(src_part, dst_part)

        # Rewrite embedded rId references in cloned XML parts (e.g. a chart's
        # <c:externalData r:id=…> pointing at its embedded workbook).
        if isinstance(dst_part, XmlPart):
            _remap_rids(dst_part._element, id_map, dropped)  # pyright: ignore[reportPrivateUsage]

        return dst_part

    @property
    def _binary_parts(self) -> dict[tuple[str, str], Part]:
        """(content-type, sha1) → picture/media part already in the destination.

        Built once per run, on first need, so importing a slide with no
        pictures never walks the destination package for this.
        """
        if self._binary_index is None:
            index: dict[tuple[str, str], Part] = {}
            for rel in self._dst_package.iter_rels():
                if rel.is_external:
                    continue
                part = rel.target_part
                if _is_shared_binary(part, rel.reltype):
                    index.setdefault(_binary_key(part), part)
            self._binary_index = index
        return self._binary_index

    # ------------------------------------------------------------------
    # Slide-to-slide links
    # ------------------------------------------------------------------

    def remember_imported_slide(self, src_slide_part: Part, dst_slide_part: Part) -> None:
        """Record that *src_slide_part* now lives in the destination as *dst_slide_part*."""
        imported = _IMPORTED_SLIDES.get(self._dst_package)
        if imported is None:
            imported = weakref.WeakKeyDictionary()
            _IMPORTED_SLIDES[self._dst_package] = imported
        imported[src_slide_part] = weakref.ref(dst_slide_part)

    def _destination_slide_for(self, src_slide_part: Part) -> Part | None:
        """Return the slide in the destination that a link to *src_slide_part* should target.

        That is, in order: the copy being made in this run (a slide linking to
        itself, or a notes slide's back-reference); the very same slide for a
        same-deck import; the copy made by an earlier import into this
        destination.  |None| when the destination has no such slide.
        """
        mapped = self.part_map.get(src_slide_part)
        if mapped is not None:
            return mapped
        if src_slide_part.package is self._dst_package:
            return src_slide_part if self._is_registered_slide(src_slide_part) else None
        imported = _IMPORTED_SLIDES.get(self._dst_package)
        ref = imported.get(src_slide_part) if imported is not None else None
        dst_slide_part = ref() if ref is not None else None
        if dst_slide_part is not None and self._is_registered_slide(dst_slide_part):
            return dst_slide_part
        return None

    def _is_registered_slide(self, slide_part: Part) -> bool:
        """True when *slide_part* is one of the destination presentation's slides."""
        return any(
            not rel.is_external and rel.reltype == RT.SLIDE and rel.target_part is slide_part
            for rel in self._dst_prs_part.rels.values()
        )

    # ------------------------------------------------------------------
    # Master / layout cloning
    # ------------------------------------------------------------------

    def clone_master(
        self, src_master_part: SlideMasterPart
    ) -> tuple[SlideMasterPart, dict[SlideLayoutPart, SlideLayoutPart]]:
        """Clone a master (+ theme + all of its layouts) and register it with the destination.

        Returns the new master part and a source-layout → cloned-layout map,
        in the source master's layout order.
        """
        dst_package = self._dst_package

        # --- Clone theme (with any pictures it references) ---
        dst_theme_part: Part | None = None
        try:
            src_theme_part = src_master_part.part_related_by(RT.THEME)
        except KeyError:
            pass  # some masters have no theme
        else:
            dst_theme_part = self.copy_part(src_theme_part, RT.THEME)

        # --- Clone master ---
        master_partname = self.next_partname("/ppt/slideMasters/slideMaster", ".xml")
        dst_master_part = _clone_xml_part(src_master_part, master_partname, dst_package)

        # The deep-copied master XML still carries the *source* master's
        # `p:sldLayoutIdLst` — its r:id values point at whatever landed on
        # those rIds in the new rels (the theme, off-by-one layouts), which
        # PowerPoint cannot resolve.  Empty it here and rebuild it entry by
        # entry as each layout is cloned below.
        master_element = dst_master_part._element  # pyright: ignore[reportPrivateUsage]
        sldLayoutIdLst = master_element.get_or_add_sldLayoutIdLst()
        for stale_entry in list(sldLayoutIdLst):
            sldLayoutIdLst.remove(stale_entry)

        if dst_theme_part is not None:
            dst_master_part.relate_to(dst_theme_part, RT.THEME)
        id_map, dropped = self.copy_dependencies(src_master_part, dst_master_part)
        _remap_rids(master_element, id_map, dropped)

        # --- Register new master with presentation (fresh unique id) ---
        rId = self._dst_prs_part.relate_to(dst_master_part, RT.SLIDE_MASTER)
        prs_element = self._dst_prs_part._element  # pyright: ignore[reportPrivateUsage]
        sldMasterIdLst = prs_element.get_or_add_sldMasterIdLst()
        master_entry = sldMasterIdLst._add_sldMasterId(rId=rId)  # pyright: ignore[reportAttributeAccessIssue]
        master_entry.set("id", str(self.next_hierarchy_id()))

        # --- Clone layouts, preserving the source master's layout order ---
        src_to_dst_layout: dict[SlideLayoutPart, SlideLayoutPart] = {}
        for src_lo in _iter_master_layouts(src_master_part):
            src_to_dst_layout[src_lo] = self.clone_layout_into_master(src_lo, dst_master_part)

        return dst_master_part, src_to_dst_layout  # type: ignore[return-value]

    def clone_layout_into_master(
        self, src_layout_part: SlideLayoutPart, dst_master_part: SlideMasterPart
    ) -> SlideLayoutPart:
        """Clone *src_layout_part* and attach it to *dst_master_part*.

        Copies the layout's own dependencies (background pictures etc.),
        wires the layout ↔ master relationships, and registers the layout in
        the master's `p:sldLayoutIdLst` with a fresh unique id — an
        unregistered layout is invisible to PowerPoint's layout picker and
        leaves the master's id list inconsistent with its relationships.
        """
        new_partname = self.next_partname("/ppt/slideLayouts/slideLayout", ".xml")
        dst_layout_part = _clone_xml_part(src_layout_part, new_partname, self._dst_package)
        id_map, dropped = self.copy_dependencies(src_layout_part, dst_layout_part)
        _remap_rids(dst_layout_part._element, id_map, dropped)  # pyright: ignore[reportPrivateUsage]
        # Relate layout → master
        dst_layout_part.relate_to(dst_master_part, RT.SLIDE_MASTER)
        # Relate master → layout
        rId = dst_master_part.relate_to(dst_layout_part, RT.SLIDE_LAYOUT)
        # Register in the master's layout-id list
        master_element = dst_master_part._element  # pyright: ignore[reportPrivateUsage]
        sldLayoutIdLst = master_element.get_or_add_sldLayoutIdLst()
        entry = sldLayoutIdLst._add_sldLayoutId(rId=rId)
        entry.set("id", str(self.next_hierarchy_id()))
        return dst_layout_part  # type: ignore[return-value]

    def iter_dst_masters(self):  # type: ignore[return]
        """Yield each SlideMasterPart registered in the destination presentation."""
        prs_element = self._dst_prs_part._element  # pyright: ignore[reportPrivateUsage]
        if prs_element.sldMasterIdLst is None:
            return
        for entry in prs_element.sldMasterIdLst.sldMasterId_lst:
            try:
                yield self._dst_prs_part.related_part(entry.rId)
            except KeyError:
                continue

    def next_hierarchy_id(self) -> int:
        """Return a fresh unique id for a `p:sldMasterId` / `p:sldLayoutId` entry.

        These share one id space starting at 2147483648 (ST_SlideMasterId /
        ST_SlideLayoutId minimum); duplicates across the presentation are a
        repair trigger, so scan every master's layout-id list plus the
        presentation's master-id list for the current maximum.
        """
        used = [2147483647]
        prs_element = self._dst_prs_part._element  # pyright: ignore[reportPrivateUsage]
        used += [int(v) for v in prs_element.xpath("p:sldMasterIdLst/p:sldMasterId/@id")]
        for dst_master_part in self.iter_dst_masters():
            used += [
                int(v)
                for v in dst_master_part._element.xpath(  # pyright: ignore[reportPrivateUsage]
                    "p:sldLayoutIdLst/p:sldLayoutId/@id"
                )
            ]
        return max(used) + 1


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
        self._copier = _PartCopier(dst_prs_part)

    def run(self) -> Slide:
        """Execute the import and return the new Slide."""
        dst_layout_part = self._resolve_layout()
        dst_slide_part = self._copy_slide(dst_layout_part)
        self._register_slide(dst_slide_part)
        self._copier.remember_imported_slide(self._src_slide_part, dst_slide_part)
        return dst_slide_part.slide

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
        """Return a destination master part whose fingerprint matches src_master_part, or None.

        In a same-deck import that is the source master itself, even when an
        earlier master of the deck is identical to it: the copy keeps the
        master, and so the layout, of the slide it was copied from.
        """
        dst_masters = list(self._copier.iter_dst_masters())
        if any(dst_master_part is src_master_part for dst_master_part in dst_masters):
            return src_master_part
        src_fp = _master_fingerprint(src_master_part)
        for dst_master_part in dst_masters:
            if _master_fingerprint(dst_master_part) == src_fp:
                return dst_master_part
        return None

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
        layout_candidates: list[SlideLayoutPart] = [
            rel.target_part  # type: ignore[misc]
            for rel in dst_master_part.rels.values()
            if not rel.is_external and rel.reltype == RT.SLIDE_LAYOUT
        ]
        match = _matching_layout(layout_candidates, src_layout_part, src_name, src_type)
        if match is not None:
            return match

        # Priority 3: clone the layout into the existing master
        return self._copier.clone_layout_into_master(src_layout_part, dst_master_part)

    def _clone_master_with_layout(
        self, src_master_part: SlideMasterPart, src_layout_part: SlideLayoutPart
    ) -> SlideLayoutPart:
        """Clone the master (+ theme + all of its layouts), register with the destination.

        Returns the cloned layout corresponding to *src_layout_part*.
        """
        dst_master_part, src_to_dst_layout = self._copier.clone_master(src_master_part)

        # Return the cloned version of the source layout
        dst_layout = src_to_dst_layout.get(src_layout_part)
        if dst_layout is None:
            # Fallback: use the first available layout
            dst_layout = next(iter(src_to_dst_layout.values()), None)
        if dst_layout is None:
            # Emergency: clone the layout directly
            dst_layout = self._copier.clone_layout_into_master(src_layout_part, dst_master_part)
        return dst_layout

    # ------------------------------------------------------------------
    # Slide copy
    # ------------------------------------------------------------------

    def _copy_slide(self, dst_layout_part: SlideLayoutPart) -> SlidePart:
        """Return a new SlidePart copied from the source slide.

        All non-master-hierarchy dependencies (images, charts, media, notes, etc.)
        are also copied.  The new slide is related to *dst_layout_part*.
        """
        dst_package = self._dst_package
        new_partname = self._copier.next_partname("/ppt/slides/slide", ".xml")
        dst_slide_part = _clone_xml_part(self._src_slide_part, new_partname, dst_package)

        # Seed the part map with the slide itself so a copied notes slide's
        # back-reference to its slide resolves to *this* part rather than
        # triggering a second, orphan clone of the whole slide graph.
        self._copier.part_map[self._src_slide_part] = dst_slide_part

        # Copy all deps except master-hierarchy rels.  Track source-rId ->
        # destination-rId so the cloned slide XML's embedded references
        # (r:embed, r:id, …) can be rewritten to the new ids.
        id_map, dropped = self._copier.copy_dependencies(self._src_slide_part, dst_slide_part)

        # Always wire layout relationship; map the source layout rId onto the new
        # one in case the slide XML references it.
        layout_rId = dst_slide_part.relate_to(dst_layout_part, RT.SLIDE_LAYOUT)
        for rel in self._src_slide_part.rels.values():
            if rel.reltype == RT.SLIDE_LAYOUT:
                id_map[rel.rId] = layout_rId
                break

        _remap_rids(dst_slide_part._element, id_map, dropped)  # pyright: ignore[reportPrivateUsage]
        return dst_slide_part  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Presentation registration
    # ------------------------------------------------------------------

    def _register_slide(self, dst_slide_part: SlidePart) -> None:
        """Add the new slide part to the destination presentation."""
        rId = self._dst_prs_part.relate_to(dst_slide_part, RT.SLIDE)
        prs_element = self._dst_prs_part._element  # pyright: ignore[reportPrivateUsage]
        sldId = prs_element.get_or_add_sldIdLst().add_sldId(rId)
        # A sectioned destination keeps its section list a complete partition
        # — the imported slide lands at the end of the deck, so it joins the
        # final section (same rule as Slides.add_slide).
        sectionLst = getattr(prs_element, "sectionLst", None)
        if sectionLst is not None and sectionLst.section_lst:
            sectionLst.section_lst[-1].add_sldId(sldId.id)


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


def _iter_master_layouts(master_part: SlideMasterPart) -> list[SlideLayoutPart]:
    """Return *master_part*'s layout parts, in `p:sldLayoutIdLst` order.

    Falls back to relationship order for a master whose layout-id list is
    absent or entirely unresolvable.
    """
    layouts: list[SlideLayoutPart] = []
    sldLayoutIdLst = master_part._element.sldLayoutIdLst  # pyright: ignore[reportPrivateUsage]
    if sldLayoutIdLst is not None:
        for entry in sldLayoutIdLst.sldLayoutId_lst:
            try:
                rel = master_part.rels[entry.rId]
            except KeyError:
                continue
            # An id-list entry whose relationship is not a layout (a master
            # damaged by an earlier tool) must not be cloned as one.
            if rel.is_external or rel.reltype != RT.SLIDE_LAYOUT:
                continue
            layouts.append(rel.target_part)  # type: ignore[arg-type]
    if layouts:
        return layouts
    return [
        rel.target_part  # type: ignore[misc]
        for rel in master_part.rels.values()
        if not rel.is_external and rel.reltype == RT.SLIDE_LAYOUT
    ]


def _matching_layout(
    candidates: list[SlideLayoutPart],
    src_layout_part: SlideLayoutPart,
    src_name: str,
    src_type: str | None,
) -> SlideLayoutPart | None:
    """Return the layout among *candidates* that best stands in for *src_layout_part*.

    In order: the very same layout, one named *src_name*, one of type
    *src_type*; |None| when there is none of those.
    """
    # Priority 0: the very same layout (a same-deck import) — two layouts
    # of one master may share a name, and the slide must keep its own.
    for lp in candidates:
        if lp is src_layout_part:
            return lp

    # Priority 1: name match
    for lp in candidates:
        if lp._element.cSld.name == src_name:  # pyright: ignore[reportPrivateUsage]
            return lp

    # Priority 2: type match
    if not src_type:
        return None
    for lp in candidates:
        if lp._element.get("type") == src_type:  # pyright: ignore[reportPrivateUsage]
            return lp
    return None


def _is_shared_binary(part: Part, reltype: str | None) -> bool:
    """True when *part* is a picture/media payload one copy of which can be shared.

    That means: reached by an image/media relationship, not an XML part
    (those are mutable and belong to one slide), and with no relationships
    of its own.
    """
    return reltype in _SHARED_BINARY_RELTYPES and not isinstance(part, XmlPart) and not part.rels


def _binary_key(part: Part) -> tuple[str, str]:
    """Return the (content-type, sha1) identity of a binary *part*."""
    sha1 = getattr(part, "sha1", None)
    if not isinstance(sha1, str):
        sha1 = hashlib.sha1(part.blob).hexdigest()
    return part.content_type, sha1


# Relationship-id references embedded in part XML all live in the ``r:``
# namespace (``r:embed``, ``r:id``, ``r:link``, and the SmartArt
# ``dgm:relIds`` ``r:dm``/``r:lo``/``r:qs``/``r:cs``).  When a part is cloned its
# relationships are re-created in copy order, so the new rIds rarely match the
# ones baked into the deep-copied XML — leaving e.g. a picture's
# ``r:embed="rId2"`` pointing at whatever part happened to land on rId2 in the
# destination.  PowerPoint then can't resolve the image and repairs the deck.
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _remap_rids(
    element, id_map: dict[str, str], dropped: set[str] | frozenset[str] = frozenset()
) -> None:
    """Rewrite every ``r:*`` attribute on *element*'s tree through *id_map*.

    Only relationship-namespace attributes whose value is a known source rId are
    touched, so non-relationship attributes are never disturbed.

    *dropped* holds source rIds whose relationship was deliberately not
    carried over (a link to a slide that is not in the destination).  A
    hyperlink element naming one is removed outright — the shape or text run
    simply stops being a link; on any other element just the dangling
    attribute is removed.
    """
    if not id_map and not dropped:
        return
    dead_links = [el for el in element.iter("*") if _remap_element_rids(el, id_map, dropped)]
    for el in dead_links:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)


def _remap_element_rids(el, id_map: dict[str, str], dropped: set[str] | frozenset[str]) -> bool:
    """Rewrite the ``r:*`` attributes of *el* itself, not its descendants.

    Returns True when *el* is a hyperlink naming a dropped relationship, which
    the caller removes; any other attribute naming one is deleted here.
    """
    prefix = "{%s}" % _R_NS
    is_dead_link = False
    for name, value in list(el.attrib.items()):
        if not name.startswith(prefix):
            continue
        if value in id_map:
            el.set(name, id_map[value])
        elif value in dropped:
            if el.tag.rpartition("}")[2] in _HYPERLINK_TAGS:
                is_dead_link = True
            else:
                del el.attrib[name]
    return is_dead_link


def _master_fingerprint(master_part: Part) -> bytes:
    """Return a SHA-256 hash over the normalised master XML + its theme XML.

    Used for master deduplication: two masters with identical fingerprints are
    considered equivalent for the purposes of ``merge_master='dedupe'``.

    The hash must be *stable across packages*: cloning a master rebuilds its
    `p:sldLayoutIdLst` (fresh rIds and unique ids) and remaps any `r:embed`
    references in its body, so those package-allocation artifacts are
    normalised out before hashing.  Otherwise a master cloned by one import
    would stop matching its own source, and every later import of a slide
    from that source would clone yet another duplicate master/layout set.
    """
    h = hashlib.sha256()
    element = getattr(master_part, "_element", None)
    if element is not None:
        h.update(_normalized_master_xml(master_part, element))
    else:  # pragma: no cover - a master part is always an XmlPart
        h.update(master_part.blob)
    try:
        theme_part = master_part.part_related_by(RT.THEME)
        h.update(theme_part.blob)
    except KeyError:
        pass
    return h.digest()


def _normalized_master_xml(master_part: Part, master_elm) -> bytes:
    """Serialize *master_elm* with package-allocation artifacts normalised.

    Drops the `p:sldLayoutIdLst` (its rId/id values are allocated per
    package) and replaces every relationship-id attribute value (`r:embed`
    etc. are renumbered when dependencies are copied) with a *stable token
    derived from the referenced content* — the SHA-1 of the target part's
    bytes, or the verbatim URL for an external target.  Masking with a
    constant would make two masters that differ only in a referenced image
    (a different logo, say) fingerprint-identical and dedupe onto the wrong
    branding; content-addressing keeps the hash stable across packages
    while still distinguishing what the references point at.
    """
    from lxml import etree

    p_ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
    clone = deepcopy(master_elm)
    for layout_id_lst in clone.findall("{%s}sldLayoutIdLst" % p_ns):
        clone.remove(layout_id_lst)
    _replace_rids_with_target_tokens(clone, master_part)
    return etree.tostring(clone)


def _replace_rids_with_target_tokens(element, part: Part) -> None:
    """Replace every ``r:*`` attribute value in *element*'s tree by its target's token.

    Each relationship id of *part* is resolved once, however often it is used.
    """
    tokens: dict[str, str] = {}
    r_prefix = "{%s}" % _R_NS
    for el in element.iter():
        for attr_name, rId in list(el.attrib.items()):
            if not attr_name.startswith(r_prefix):
                continue
            if rId not in tokens:
                tokens[rId] = _target_token(part, rId)
            el.set(attr_name, tokens[rId])


def _target_token(part: Part, rId: str) -> str:
    """Return a stable token for what relationship *rId* of *part* points at.

    That is the SHA-1 of the target part's bytes, the URL of an external
    target, or ``"unresolved"`` when *part* has no such relationship.
    """
    try:
        rel = part.rels[rId]
    except KeyError:
        return "unresolved"
    if rel.is_external:
        return "external:%s" % rel.target_ref
    return hashlib.sha1(rel.target_part.blob).hexdigest()


def _numbered_partname(partname: str) -> tuple[str, str]:
    """Split *partname* around its trailing number, for allocating a sibling name.

    E.g. ``/ppt/charts/chart3.xml`` → ``("/ppt/charts/chart", ".xml")``, so the
    next free name is ``/ppt/charts/chart{n}.xml``.  The pieces are plain
    strings to be concatenated, never a printf template, so a ``%`` in the
    name (as in ``/ppt/media/my%20logo.png``) needs no escaping.
    """
    return numbered_partname_pieces(partname)
