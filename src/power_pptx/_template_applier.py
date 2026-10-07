"""Template application machinery for ``Presentation.apply_template()``."""

from __future__ import annotations

import contextlib
import warnings
from typing import TYPE_CHECKING, Iterator

from power_pptx._slide_importer import _PartCopier  # pyright: ignore[reportPrivateUsage]
from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT

if TYPE_CHECKING:
    from power_pptx.parts.presentation import PresentationPart
    from power_pptx.parts.slide import SlideLayoutPart, SlideMasterPart, SlidePart


def apply_template(
    dst_prs_part: PresentationPart,
    template_prs_part: PresentationPart,
) -> None:
    """Re-point every slide in *dst_prs_part* at the masters/layouts from *template_prs_part*.

    Existing slide content (shapes, text, animations) is preserved.
    Each slide's layout is matched to the closest layout in the template (by name, then by
    type, then fallback to the template's first layout).

    The template's masters are cloned into the destination together with their themes, layouts
    and the pictures and other parts those use, under fresh unique ids.  The old
    master/layout/theme parts are then unregistered, so the package no longer reaches them and
    they are not written when it is saved.  The presentation stays fully usable in memory
    afterwards; collections obtained earlier (``Presentation.slide_masters``) keep working.

    A template without any slide layout cannot take over the slides: a :class:`UserWarning` is
    issued and the destination is left unchanged.

    Parameters
    ----------
    dst_prs_part:
        The presentation to modify in place.
    template_prs_part:
        The template presentation whose masters/layouts/themes are to be applied.
    """
    applier = _TemplateApplier(dst_prs_part, template_prs_part)
    applier.run()


class _TemplateApplier(_PartCopier):
    """Stateful helper for template application."""

    def __init__(
        self,
        dst_prs_part: PresentationPart,
        tpl_prs_part: PresentationPart,
    ) -> None:
        super().__init__(dst_prs_part)
        self._tpl_prs_part = tpl_prs_part

    def run(self) -> None:
        """Execute the template application."""
        tpl_masters = list(self._iter_template_masters())
        if not any(self._iter_master_layouts(master) for master in tpl_masters):
            warnings.warn(
                "apply_template: no layouts available in the template; "
                "the presentation was left unchanged.",
                stacklevel=4,
            )
            return

        # 1. Clone the template masters (with themes, layouts and their dependencies) into the
        # destination.  The clones are registered next to the old masters, which keeps every
        # master and layout id unique while both sets exist.
        new_masters: list[SlideMasterPart] = []
        tpl_layouts: list[SlideLayoutPart] = []
        dst_layouts: list[SlideLayoutPart] = []
        for tpl_master in tpl_masters:
            dst_master, layout_map = self._clone_master(tpl_master)
            new_masters.append(dst_master)
            tpl_layouts.extend(layout_map.keys())
            dst_layouts.extend(layout_map.values())

        # 2. Remap each existing slide to the best-matching template layout
        dst_prs_element = self._dst_prs_part._element  # pyright: ignore[reportPrivateUsage]
        sldIdLst = dst_prs_element.sldIdLst
        if sldIdLst is not None:
            for sldId in list(sldIdLst.sldId_lst):
                slide_part: SlidePart = self._dst_prs_part.related_part(sldId.rId)  # type: ignore[assignment]
                self._remap_slide(slide_part, tpl_layouts, dst_layouts)

        # 3. Unregister the old masters (unreachable parts are not included when the package is
        # saved)
        self._drop_old_masters(new_masters)

    def _iter_template_masters(self) -> Iterator[SlideMasterPart]:
        """Yield each slide master of the template, in `p:sldMasterIdLst` order."""
        sldMasterIdLst = self._tpl_prs_part._element.sldMasterIdLst  # pyright: ignore[reportPrivateUsage]
        if sldMasterIdLst is None:
            return
        for entry in sldMasterIdLst.sldMasterId_lst:
            yield self._tpl_prs_part.related_part(entry.rId)  # type: ignore[misc]

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

        # Determine current slide's layout info for matching
        current_lo_name: str = ""
        current_lo_type: str = ""
        if old_layout_rId is not None:
            old_lo_part: SlideLayoutPart = slide_part.related_part(old_layout_rId)  # type: ignore[assignment]
            with contextlib.suppress(AttributeError):
                current_lo_name = old_lo_part._element.cSld.name  # pyright: ignore[reportPrivateUsage]
            current_lo_type = old_lo_part._element.get("type") or ""  # pyright: ignore[reportPrivateUsage]

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

    def _drop_old_masters(self, new_masters: list[SlideMasterPart]) -> None:
        """Unregister every master of the destination that is not one of *new_masters*.

        The old masters' relationships and `p:sldMasterIdLst` entries are removed; the list
        element itself is edited in place rather than replaced, so a
        `Presentation.slide_masters` collection obtained earlier (it wraps that very element)
        keeps working.  Also re-points the presentation→theme relationship: it is removed
        from the old theme and now targets the theme of the first new master, as in a
        PowerPoint-authored file.

        The old Part objects remain in memory but will not be written to the package
        because they are no longer reachable from any relationship.
        """
        prs_part = self._dst_prs_part
        keep = set(new_masters)

        for rId, rel in list(prs_part.rels.items()):
            if (
                not rel.is_external
                and rel.reltype == RT.SLIDE_MASTER
                and rel.target_part not in keep
            ):
                prs_part.rels.pop(rId)

        sldMasterIdLst = prs_part._element.sldMasterIdLst  # pyright: ignore[reportPrivateUsage]
        if sldMasterIdLst is not None:
            for entry in list(sldMasterIdLst.sldMasterId_lst):
                if entry.rId not in prs_part.rels:
                    sldMasterIdLst.remove(entry)

        # Remove any direct presentation→theme relationship so the old theme
        # is no longer reachable from the presentation.
        for rId, rel in list(prs_part.rels.items()):
            if not rel.is_external and rel.reltype == RT.THEME:
                prs_part.rels.pop(rId)
        with contextlib.suppress(KeyError):  # a master need not have a theme
            prs_part.relate_to(new_masters[0].part_related_by(RT.THEME), RT.THEME)
