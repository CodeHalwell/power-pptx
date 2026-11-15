"""Template application machinery for ``Presentation.apply_template()``."""

from __future__ import annotations

import os
from typing import IO, TYPE_CHECKING, Union

from power_pptx._slide_importer import (
    _iter_master_layouts,  # pyright: ignore[reportPrivateUsage]
    _PartCopier,  # pyright: ignore[reportPrivateUsage]
)
from power_pptx.opc.constants import CONTENT_TYPE as CT
from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT

if TYPE_CHECKING:
    from power_pptx.opc.package import Part
    from power_pptx.parts.presentation import PresentationPart
    from power_pptx.parts.slide import SlideLayoutPart, SlideMasterPart, SlidePart
    from power_pptx.presentation import Presentation

    TemplateSource = Union[Presentation, PresentationPart, str, "os.PathLike[str]", IO[bytes]]


def apply_template(
    presentation: Presentation | PresentationPart | None = None,
    template: TemplateSource | None = None,
    *,
    dst_prs_part: PresentationPart | None = None,
    template_prs_part: PresentationPart | None = None,
) -> None:
    """Re-point every slide in *presentation* at the masters/layouts from *template*.

    ::

        from power_pptx.compose import apply_template

        apply_template(prs, "brand-template.potx")

    This is the function form of :meth:`Presentation.apply_template()
    <power_pptx.presentation.Presentation.apply_template>`.

    Existing slide content (shapes, text, animations) is preserved.
    Each slide's layout is matched to the closest layout in the template (by name, then by
    type, then fallback to the template's first layout).

    The template's masters, with their themes, layouts and the pictures those
    use, are copied into *presentation* and replace its own.  The old
    master/layout/theme parts are no longer referenced, so they are left out
    when the package is saved.  |SlideMaster| and |SlideLayout| objects
    obtained *before* the call belong to the replaced masters; fetch them
    again from ``prs.slide_masters`` / ``prs.slide_layouts`` afterwards.

    Parameters
    ----------
    presentation:
        The |Presentation| to modify in place (or its
        :class:`~power_pptx.parts.presentation.PresentationPart`).
    template:
        The template whose masters/layouts/themes are to be applied: a path
        to a ``.potx`` / ``.pptx`` file, a file-like object, an open
        |Presentation|, or a ``PresentationPart``.

    The original part-based keywords ``dst_prs_part=`` and
    ``template_prs_part=`` are still accepted.

    Raises
    ------
    ValueError
        If the template has no slide master, or *presentation* has slides
        and the template has no slide layout to put them on.  Nothing is
        changed in that case.
    """
    if presentation is None:
        presentation = dst_prs_part
    elif dst_prs_part is not None:
        raise TypeError("apply_template() got the presentation to modify twice")
    if template is None:
        template = template_prs_part
    elif template_prs_part is not None:
        raise TypeError("apply_template() got the template twice")
    if presentation is None:
        raise TypeError("apply_template() needs the Presentation to modify")
    if template is None:
        raise TypeError("apply_template() needs a template")

    _TemplateApplier(_presentation_part(presentation), _template_part(template)).run()


def _presentation_part(presentation: object) -> PresentationPart:
    """Return the |PresentationPart| behind *presentation* (a proxy or the part itself)."""
    from power_pptx.parts.presentation import PresentationPart
    from power_pptx.presentation import Presentation

    part = presentation.part if isinstance(presentation, Presentation) else presentation
    if not isinstance(part, PresentationPart):
        raise TypeError(
            "apply_template() takes a Presentation to modify, got %s"
            % type(presentation).__name__
        )
    return part


def _template_part(template: object) -> PresentationPart:
    """Return the |PresentationPart| of *template*, opening it when it is a path or stream."""
    from power_pptx.parts.presentation import PresentationPart
    from power_pptx.presentation import Presentation

    if isinstance(template, Presentation):
        return template.part
    if isinstance(template, PresentationPart):
        return template
    if isinstance(template, (str, os.PathLike)) or hasattr(template, "read"):
        from power_pptx.api import Presentation as open_presentation

        return open_presentation(template).part  # type: ignore[arg-type]
    raise TypeError(
        "apply_template() takes a template path, file-like object or Presentation, got %s"
        % type(template).__name__
    )


class _TemplateApplier:
    """Stateful helper for template application."""

    def __init__(
        self,
        dst_prs_part: PresentationPart,
        tpl_prs_part: PresentationPart,
    ) -> None:
        self._dst_prs_part = dst_prs_part
        self._tpl_prs_part = tpl_prs_part
        # Shared with slide import: clones a master with its theme, layouts
        # and their dependencies, and rebuilds the master's layout-id list to
        # match the relationships it actually ends up with.
        self._copier = _PartCopier(dst_prs_part)

    def run(self) -> None:
        """Execute the template application."""
        tpl_masters = self._template_masters()
        slide_parts = self._slide_parts()

        # Check everything that can be refused *before* touching the deck, so
        # a rejected template leaves it exactly as it was.
        if not tpl_masters:
            raise ValueError("apply_template: the template has no slide master")
        if slide_parts and not any(_iter_master_layouts(m) for m in tpl_masters):
            raise ValueError(
                "apply_template: the template has no slide layouts, so the "
                "presentation's slides cannot be re-pointed at it"
            )

        # The masters this deck has now; everything in this list is replaced.
        prs_element = self._dst_prs_part._element  # pyright: ignore[reportPrivateUsage]
        sldMasterIdLst = prs_element.get_or_add_sldMasterIdLst()
        old_entries = list(sldMasterIdLst.sldMasterId_lst)

        # 1. Clone the template masters (with themes + layouts + their
        #    pictures) into the destination, after the existing ones.
        new_masters: list[SlideMasterPart] = []
        tpl_layouts: list[SlideLayoutPart] = []
        dst_layouts: list[SlideLayoutPart] = []
        for tpl_master_part in tpl_masters:
            dst_master_part, layout_map = self._copier.clone_master(tpl_master_part)
            new_masters.append(dst_master_part)
            for tpl_layout, dst_layout in layout_map.items():
                tpl_layouts.append(tpl_layout)
                dst_layouts.append(dst_layout)

        # 2. Remap each existing slide to the best-matching template layout
        for slide_part in slide_parts:
            self._remap_slide(slide_part, tpl_layouts, dst_layouts)

        # 3. Drop the old masters from the presentation
        # (unreachable parts are not included when the package is saved)
        self._drop_old_masters(old_entries, new_masters)

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------

    def _template_masters(self) -> list[SlideMasterPart]:
        """Return the template's slide-master parts, in presentation order."""
        tpl_prs_element = self._tpl_prs_part._element  # pyright: ignore[reportPrivateUsage]
        sldMasterIdLst = tpl_prs_element.sldMasterIdLst
        if sldMasterIdLst is None:
            return []
        masters: list[SlideMasterPart] = []
        for entry in sldMasterIdLst.sldMasterId_lst:
            try:
                masters.append(self._tpl_prs_part.related_part(entry.rId))  # type: ignore[arg-type]
            except KeyError:
                continue
        return masters

    def _slide_parts(self) -> list[SlidePart]:
        """Return every slide part in the destination package.

        The presentation's own slides come first, in order.  Slide parts that
        are in the package without being listed in `p:sldIdLst` are included
        too: left on an old layout they would keep the old master in the
        saved package while it is no longer listed in the presentation.
        """
        slide_parts: list[SlidePart] = []
        prs_element = self._dst_prs_part._element  # pyright: ignore[reportPrivateUsage]
        sldIdLst = prs_element.sldIdLst
        if sldIdLst is not None:
            for sldId in sldIdLst.sldId_lst:
                try:
                    slide_parts.append(self._dst_prs_part.related_part(sldId.rId))  # type: ignore[arg-type]
                except KeyError:
                    continue
        listed = set(slide_parts)
        for part in self._dst_prs_part.package.iter_parts():
            if part.content_type == CT.PML_SLIDE and part not in listed:
                slide_parts.append(part)  # type: ignore[arg-type]
        return slide_parts

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
            old_lo_element = getattr(old_lo_part, "_element", None)
            if old_lo_element is not None:
                current_lo_name = getattr(getattr(old_lo_element, "cSld", None), "name", "") or ""
                current_lo_type = old_lo_element.get("type") or ""

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

    def _drop_old_masters(self, old_entries: list, new_masters: list[SlideMasterPart]) -> None:
        """Remove the replaced masters' entries and relationships from the presentation.

        The `p:sldMasterIdLst` element itself is kept and edited in place: the
        |Presentation| object caches a `SlideMasters` collection wrapping that
        very element, so replacing the element would leave `prs.slide_masters`
        (and with it `prs.slide_layouts`, `prs.slide_master`, `prs.theme`)
        reading a detached list of relationship ids that no longer exist.

        Also re-points the presentation's own theme relationship at the first
        new master's theme, so the old theme is no longer reachable.

        The old Part objects remain in memory but will not be written to the package
        because they are no longer reachable from any relationship.
        """
        prs_part = self._dst_prs_part

        for entry in old_entries:
            rId = entry.rId
            entry.getparent().remove(entry)
            if rId in prs_part.rels:
                prs_part.rels.pop(rId)

        # Remove any direct presentation→theme relationship so the old theme
        # is no longer reachable from the presentation...
        for rId, rel in list(prs_part.rels.items()):
            if not rel.is_external and rel.reltype == RT.THEME:
                prs_part.rels.pop(rId)

        # ... and give the presentation the first new master's theme instead,
        # which is how PowerPoint itself relates the two.
        new_theme: Part | None = next(
            (
                rel.target_part
                for rel in new_masters[0].rels.values()
                if not rel.is_external and rel.reltype == RT.THEME
            ),
            None,
        )
        if new_theme is not None:
            prs_part.relate_to(new_theme, RT.THEME)
