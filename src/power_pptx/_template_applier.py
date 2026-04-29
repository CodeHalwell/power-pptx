"""Template application machinery for ``Presentation.apply_template()``."""

from __future__ import annotations

import warnings
from copy import deepcopy
from typing import TYPE_CHECKING

from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT
from power_pptx.opc.packuri import PackURI

if TYPE_CHECKING:
    from power_pptx.opc.package import Part
    from power_pptx.package import Package
    from power_pptx.parts.presentation import PresentationPart
    from power_pptx.parts.slide import SlideLayoutPart, SlideMasterPart, SlidePart
    from power_pptx.slide import Slide


def apply_template(
    dst_prs_part: PresentationPart,
    template_prs_part: PresentationPart,
) -> None:
    """Re-point every slide in *dst_prs_part* at the masters/layouts from *template_prs_part*.

    Existing slide content (shapes, text, animations) is preserved.
    Each slide's layout is matched to the closest layout in the template (by name, then by
    type, then fallback to the template's first layout).

    After all slides are remapped the old master/layout/theme parts that are no longer
    referenced are dropped automatically when the package is saved (they are no longer
    reachable from any relationship).

    Parameters
    ----------
    dst_prs_part:
        The presentation to modify in place.
    template_prs_part:
        The template presentation whose masters/layouts/themes are to be applied.
    """
    applier = _TemplateApplier(dst_prs_part, template_prs_part)
    applier.run()


class _TemplateApplier:
    """Stateful helper for template application."""

    def __init__(
        self,
        dst_prs_part: PresentationPart,
        tpl_prs_part: PresentationPart,
    ) -> None:
        self._dst_prs_part = dst_prs_part
        self._tpl_prs_part = tpl_prs_part
        self._dst_package: Package = dst_prs_part.package  # type: ignore[assignment]
        # Tracks partnames already reserved during this run to avoid collisions
        self._reserved: set[str] = set()

    def run(self) -> None:
        """Execute the template application."""
        # 1. Clone the template masters (with themes + layouts) into the destination
        tpl_master_to_dst_master = self._clone_template_masters()

        # 2. Build a flat list of all template layout parts (for matching)
        tpl_layouts: list[SlideLayoutPart] = []
        for tpl_master_part, dst_master_part in tpl_master_to_dst_master.items():
            for rel in tpl_master_part.rels.values():
                if rel.is_external or rel.reltype != RT.SLIDE_LAYOUT:
                    continue
                tpl_layouts.append(rel.target_part)  # type: ignore[arg-type]

        # Map tpl layout partname → corresponding dst layout part
        tpl_partname_to_dst_layout: dict[str, SlideLayoutPart] = {}
        for tpl_master_part, dst_master_part in tpl_master_to_dst_master.items():
            for tpl_rel, dst_rel in zip(
                [r for r in tpl_master_part.rels.values() if not r.is_external and r.reltype == RT.SLIDE_LAYOUT],
                [r for r in dst_master_part.rels.values() if not r.is_external and r.reltype == RT.SLIDE_LAYOUT],
            ):
                tpl_partname_to_dst_layout[tpl_rel.target_part.partname] = dst_rel.target_part  # type: ignore[assignment]

        # Build dst layouts list in the same order as tpl_layouts (parallel)
        dst_layouts: list[SlideLayoutPart] = [
            tpl_partname_to_dst_layout[lp.partname]  # type: ignore[index]
            for lp in tpl_layouts
            if lp.partname in tpl_partname_to_dst_layout
        ]

        # 3. Remap each existing slide to the best-matching template layout
        dst_prs_element = self._dst_prs_part._element  # pyright: ignore[reportPrivateUsage]
        sldIdLst = dst_prs_element.sldIdLst
        if sldIdLst is not None:
            for sldId in list(sldIdLst.sldId_lst):
                slide_part: SlidePart = self._dst_prs_part.related_part(sldId.rId)  # type: ignore[assignment]
                self._remap_slide(slide_part, tpl_layouts, dst_layouts)

        # 4. Remove old masters from the presentation element
        # (unreachable parts are not included when the package is saved)
        self._drop_old_masters(set(tpl_master_to_dst_master.values()))

        # 5. Register new masters in presentation element
        for dst_master_part in tpl_master_to_dst_master.values():
            rId = self._dst_prs_part.relate_to(dst_master_part, RT.SLIDE_MASTER)
            sldMasterIdLst = dst_prs_element.get_or_add_sldMasterIdLst()
            sldMasterIdLst._add_sldMasterId(rId=rId)  # pyright: ignore[reportAttributeAccessIssue]

    # ------------------------------------------------------------------
    # Master cloning
    # ------------------------------------------------------------------

    def _clone_template_masters(self) -> dict[SlideMasterPart, SlideMasterPart]:
        """Clone each master in the template into the destination.

        Returns a mapping: template SlideMasterPart → cloned destination SlideMasterPart.
        """
        result: dict[SlideMasterPart, SlideMasterPart] = {}
        dst_package = self._dst_package
        tpl_prs_element = self._tpl_prs_part._element  # pyright: ignore[reportPrivateUsage]

        if tpl_prs_element.sldMasterIdLst is None:
            return result

        for entry in tpl_prs_element.sldMasterIdLst.sldMasterId_lst:
            tpl_master_part: SlideMasterPart = self._tpl_prs_part.related_part(entry.rId)  # type: ignore[assignment]

            # Clone theme
            dst_theme_part: Part | None = None
            try:
                src_theme = tpl_master_part.part_related_by(RT.THEME)
                theme_pn = self._next_partname("/ppt/theme/theme%d.xml")
                dst_theme_part = _clone_part(src_theme, theme_pn, dst_package)
            except KeyError:
                pass

            # Clone master
            master_pn = self._next_partname("/ppt/slideMasters/slideMaster%d.xml")
            dst_master_part = _clone_xml_part(tpl_master_part, master_pn, dst_package)
            if dst_theme_part is not None:
                dst_master_part.relate_to(dst_theme_part, RT.THEME)

            # Clone layouts
            for rel in tpl_master_part.rels.values():
                if rel.is_external or rel.reltype != RT.SLIDE_LAYOUT:
                    continue
                src_lo: SlideLayoutPart = rel.target_part  # type: ignore[assignment]
                lo_pn = self._next_partname("/ppt/slideLayouts/slideLayout%d.xml")
                dst_lo = _clone_xml_part(src_lo, lo_pn, dst_package)
                dst_lo.relate_to(dst_master_part, RT.SLIDE_MASTER)
                dst_master_part.relate_to(dst_lo, RT.SLIDE_LAYOUT)

            result[tpl_master_part] = dst_master_part  # type: ignore[assignment]

        return result

    # ------------------------------------------------------------------
    # Slide remapping
    # ------------------------------------------------------------------

    def _remap_slide(
        self,
        slide_part: SlidePart,
        tpl_layouts: list[SlideLayoutPart],
        dst_layouts: list[SlideLayoutPart],
    ) -> None:
        """Replace the slide's layout relationship to point to a template layout."""
        # Find the current layout rel and remove it
        old_layout_rId: str | None = None
        for rId, rel in list(slide_part.rels.items()):
            if not rel.is_external and rel.reltype == RT.SLIDE_LAYOUT:
                old_layout_rId = rId
                break

        if not dst_layouts:
            warnings.warn(
                "apply_template: no layouts available in the template; "
                "slide layout relationship could not be updated.",
                stacklevel=3,
            )
            return

        # Determine current slide's layout info for matching
        current_lo_name: str = ""
        current_lo_type: str = ""
        if old_layout_rId is not None:
            old_lo_part: SlideLayoutPart = slide_part.related_part(old_layout_rId)  # type: ignore[assignment]
            try:
                current_lo_name = old_lo_part._element.cSld.name  # pyright: ignore[reportPrivateUsage]
            except AttributeError:
                pass
            current_lo_type = (old_lo_part._element.get("type") or "")  # pyright: ignore[reportPrivateUsage]

        # Match: name, then type, then first
        matched_dst_lo: SlideLayoutPart | None = None
        for tpl_lo, dst_lo in zip(tpl_layouts, dst_layouts):
            tpl_name = tpl_lo._element.cSld.name  # pyright: ignore[reportPrivateUsage]
            if tpl_name == current_lo_name:
                matched_dst_lo = dst_lo
                break
        if matched_dst_lo is None and current_lo_type:
            for tpl_lo, dst_lo in zip(tpl_layouts, dst_layouts):
                tpl_type = tpl_lo._element.get("type") or ""  # pyright: ignore[reportPrivateUsage]
                if tpl_type == current_lo_type:
                    matched_dst_lo = dst_lo
                    break
        if matched_dst_lo is None:
            matched_dst_lo = dst_layouts[0]

        # Remove old layout relationship
        if old_layout_rId is not None:
            slide_part.rels.pop(old_layout_rId)

        # Add new layout relationship
        slide_part.relate_to(matched_dst_lo, RT.SLIDE_LAYOUT)

    # ------------------------------------------------------------------
    # Old master removal
    # ------------------------------------------------------------------

    def _drop_old_masters(self, new_masters: set[SlideMasterPart]) -> None:
        """Remove old master entries from the presentation element.

        Also removes any direct presentation→theme relationship, since the
        theme is now owned by the new master.

        The old Part objects remain in memory but will not be written to the package
        because they are no longer reachable from any relationship.
        """
        prs_element = self._dst_prs_part._element  # pyright: ignore[reportPrivateUsage]
        sldMasterIdLst = prs_element.sldMasterIdLst

        if sldMasterIdLst is None:
            return

        # Collect rIds that point to OLD masters (not in new_masters)
        old_rIds: list[str] = []
        for entry in list(sldMasterIdLst.sldMasterId_lst):
            part = self._dst_prs_part.related_part(entry.rId)
            if part not in new_masters:
                old_rIds.append(entry.rId)

        # Remove relationships to old masters
        for rId in old_rIds:
            self._dst_prs_part.rels.pop(rId)

        # Remove any direct presentation→theme relationship so the old theme
        # is no longer reachable from the presentation.
        theme_rIds_to_remove: list[str] = []
        for rId, rel in list(self._dst_prs_part.rels.items()):
            if not rel.is_external and rel.reltype == RT.THEME:
                theme_rIds_to_remove.append(rId)
        for rId in theme_rIds_to_remove:
            self._dst_prs_part.rels.pop(rId)

        # Remove the entire sldMasterIdLst — it will be rebuilt in run()
        prs_element.remove(sldMasterIdLst)

    # ------------------------------------------------------------------
    # Partname helpers
    # ------------------------------------------------------------------

    def _next_partname(self, tmpl: str) -> PackURI:
        """Return the next non-colliding partname, accounting for locally reserved names."""
        prefix = tmpl[: (tmpl % 42).find("42")]
        existing = {
            p.partname for p in self._dst_package.iter_parts()
            if p.partname.startswith(prefix)
        }
        taken = existing | {pn for pn in self._reserved if pn.startswith(prefix)}
        n = 1
        while True:
            candidate = tmpl % n
            if candidate not in taken:
                self._reserved.add(candidate)
                return PackURI(candidate)
            n += 1


# ---------------------------------------------------------------------------
# Part-copy helpers (shared logic)
# ---------------------------------------------------------------------------


def _clone_part(src_part: Part, new_partname: PackURI, dst_package: Package) -> Part:
    from power_pptx.opc.package import PartFactory

    return PartFactory(new_partname, src_part.content_type, dst_package, blob=src_part.blob)


def _clone_xml_part(src_part: Part, new_partname: PackURI, dst_package: Package) -> Part:
    from power_pptx.opc.package import XmlPart

    new_element = deepcopy(src_part._element)  # pyright: ignore[reportPrivateUsage]
    return src_part.__class__(new_partname, src_part.content_type, dst_package, new_element)
