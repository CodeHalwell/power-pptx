"""Sections API — named groupings of slides in the slide-sorter/outline pane.

Sections are stored as a PowerPoint-2010 extension on the presentation part
(``p:presentation/p:extLst/p:ext[@uri="{521415D9-...}"]/p14:sectionLst``).  A
section references its member slides by their numeric ``p:sldId/@id`` value
(not the relationship id).

The public entry point is :attr:`power_pptx.presentation.Presentation.sections`,
which returns a :class:`Sections` collection.  Typical use::

    prs.sections.add("Intro", start_slide_index=0)
    prs.sections.add("Body", start_slide_index=2)
    for section in prs.sections:
        print(section.name, [s.slide_id for s in section.slides])
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Iterator

from power_pptx.oxml.ns import qn
from power_pptx.shared import ParentedElementProxy

if TYPE_CHECKING:
    from power_pptx.oxml.presentation import (
        CT_Presentation,
        CT_Section,
    )
    from power_pptx.parts.presentation import PresentationPart
    from power_pptx.presentation import Presentation
    from power_pptx.slide import Slide

# -- brace-wrapped GUID, the lexical form ST_Guid requires for `p14:section/@id` --
_GUID_RE = re.compile(
    r"^\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}"
    r"-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}$"
)


def _remove_section_element(section_elm: CT_Section) -> None:
    """Remove *section_elm*, keeping the section list a complete partition.

    PowerPoint keeps every slide in exactly one section whenever a section
    list exists, so the removed section's member slides are merged into the
    previous section (or the next one when the first section is removed) —
    the same behaviour as PowerPoint's own "Remove Section" command.
    Removing the *only* section drops the whole `p14:sectionLst` extension
    instead: an empty `<p14:sectionLst/>` violates CT_SectionList
    (`minOccurs="1"` on `section`) and the deck simply becomes unsectioned.
    """
    sectionLst = section_elm.getparent()
    if sectionLst is None:
        return
    siblings = list(sectionLst)
    idx = siblings.index(section_elm)
    member_ids = [sldId.id for sldId in section_elm.sldId_lst]

    if len(siblings) == 1:
        ext = sectionLst.getparent()  # the `p:ext` carrying the extension
        extLst = ext.getparent() if ext is not None else None
        if ext is not None and extLst is not None:
            extLst.remove(ext)
            if len(extLst) == 0:
                prs_elm = extLst.getparent()
                if prs_elm is not None:
                    prs_elm.remove(extLst)
        return

    sectionLst.remove(section_elm)
    if not member_ids:
        return
    if idx > 0:
        # Merge into the previous section: its slides now precede these.
        for slide_id in member_ids:
            siblings[idx - 1].add_sldId(slide_id)
    else:
        # The first section was removed: its slides precede the (new) first
        # section's members, so prepend in order.
        target_lst = siblings[1].get_or_add_sldIdLst()
        for pos, slide_id in enumerate(member_ids):
            entry = target_lst.makeelement(qn("p14:sldId"), {"id": str(slide_id)})
            target_lst.insert(pos, entry)


class Sections(ParentedElementProxy):
    """Sequence of |Section| objects belonging to a |Presentation|.

    Supports ``len()``, indexed access, and iteration.  Reading the
    collection never modifies the deck; the underlying PowerPoint-2010
    extension element is created only when the first section is added.
    """

    part: PresentationPart  # pyright: ignore[reportIncompatibleMethodOverride]

    def __init__(self, prs_elm: CT_Presentation, prs: Presentation):
        super(Sections, self).__init__(prs_elm, prs)
        self._prs_elm = prs_elm
        self._prs = prs

    @property
    def _section_elms(self) -> list[CT_Section]:
        """The `p14:section` elements, or an empty list when unsectioned."""
        sectionLst = self._prs_elm.sectionLst
        if sectionLst is None:
            return []
        return sectionLst.section_lst

    def __getitem__(self, idx: int) -> Section:
        """Provide indexed access, e.g. ``prs.sections[0]``."""
        try:
            section = self._section_elms[idx]
        except IndexError:
            raise IndexError("section index out of range")
        return Section(section, self._prs)

    def __iter__(self) -> Iterator[Section]:
        """Support iteration, e.g. ``for section in prs.sections:``."""
        for section in self._section_elms:
            yield Section(section, self._prs)

    def __len__(self) -> int:
        """Support ``len()`` built-in, e.g. ``len(prs.sections)``."""
        return len(self._section_elms)

    def add(
        self,
        name: str,
        start_slide_index: int | None = None,
        *,
        id: str | None = None,
    ) -> Section:
        """Append a new |Section| named `name` and return it.

        When `start_slide_index` is given, every slide from that zero-based
        position to the end of the deck becomes a member of the new section
        (the natural PowerPoint behaviour for a section that begins at a given
        slide).  PowerPoint sections are contiguous and non-overlapping, so
        those slides are also *removed* from any earlier section that claimed
        them — a new section beginning at slide N truncates the prior section
        at N-1.  When the *first* section of the deck starts beyond slide 0,
        the slides before it are grouped into an auto-created "Default
        Section" (mirroring PowerPoint, which never leaves a slide outside
        every section).  When `start_slide_index` is omitted, the section is
        created empty.

        `id` optionally fixes the section's brace-wrapped GUID; supplying it
        keeps output deterministic for tests.  A random GUID is generated
        otherwise.  A malformed or already-used id raises |ValueError| —
        `p14:section/@id` is an ST_Guid and PowerPoint repairs decks whose
        section ids are not unique GUIDs.
        """
        if id is not None:
            if not _GUID_RE.match(id):
                raise ValueError(
                    "section id must be a brace-wrapped GUID like "
                    "'{3E86B4F5-40E6-4F32-8B4D-BE3E1E4C8A27}'; got %r" % (id,)
                )
            if any(s.id.lower() == id.lower() for s in self._section_elms):
                raise ValueError("section id %s is already used in this deck" % id)

        was_unsectioned = not self._section_elms
        sectionLst = self._prs_elm.get_or_add_sectionLst()
        section_elm = sectionLst.add_section(name, section_id=id)
        section = Section(section_elm, self._prs)
        if start_slide_index is not None:
            slides = list(self._prs.slides)
            claimed = slides[start_slide_index:]
            # Sections don't overlap: take the claimed slides away from any
            # earlier section before assigning them to the new one.
            for other in self:
                if other._element is section_elm:
                    continue
                for slide in claimed:
                    other.remove_slide(slide)
            for slide in claimed:
                section.add_slide(slide)
            # First section of the deck starting beyond slide 0: cover the
            # preceding slides so the section list partitions the whole deck.
            if was_unsectioned and start_slide_index > 0:
                default_elm = sectionLst.add_section("Default Section")
                section_elm.addprevious(default_elm)
                default = Section(default_elm, self._prs)
                for slide in slides[:start_slide_index]:
                    default.add_slide(slide)
        return section

    def remove(self, section: Section) -> None:
        """Remove `section` from this collection.

        Slides referenced by the section are not deleted from the deck; they
        are merged into the neighbouring section (previous when one exists,
        else next), matching PowerPoint's "Remove Section" command.  Removing
        the only section removes the section grouping entirely.
        """
        _remove_section_element(section._element)


class Section(ParentedElementProxy):
    """A single named section grouping a contiguous run of slides."""

    part: PresentationPart  # pyright: ignore[reportIncompatibleMethodOverride]

    def __init__(self, section: CT_Section, prs: Presentation):
        super(Section, self).__init__(section, prs)
        self._section = section
        self._prs = prs

    @property
    def id(self) -> str:
        """The section's brace-wrapped GUID identifier (read-only)."""
        return self._section.id

    @property
    def name(self) -> str:
        """The user-visible section name. Read/write."""
        return self._section.name

    @name.setter
    def name(self, value: str) -> None:
        self._section.name = value

    @property
    def slide_ids(self) -> list[int]:
        """List of numeric slide ids (``p:sldId/@id``) belonging to this section."""
        return [sldId.id for sldId in self._section.sldId_lst]

    @property
    def slides(self) -> tuple[Slide, ...]:
        """Tuple of |Slide| objects belonging to this section.

        Member references whose slide is no longer present in the deck are
        silently skipped.
        """
        result: list[Slide] = []
        for slide_id in self.slide_ids:
            slide = self.part.get_slide(slide_id)
            if slide is not None:
                result.append(slide)
        return tuple(result)

    def add_slide(self, slide: Slide) -> None:
        """Add `slide` to this section's membership (idempotent).

        Sections are non-overlapping — PowerPoint repairs a deck whose
        section list references one slide twice — so the slide is first
        removed from any other section that claims it.
        """
        slide_id = slide.slide_id
        if slide_id in self.slide_ids:
            return
        sectionLst = self._section.getparent()
        if sectionLst is not None:
            for sibling in sectionLst:
                if sibling is self._section:
                    continue
                sibling.remove_sldId(slide_id)
        self._section.add_sldId(slide_id)

    def remove_slide(self, slide: Slide) -> None:
        """Remove `slide` from this section's membership (no-op if absent)."""
        self._section.remove_sldId(slide.slide_id)

    def delete(self) -> None:
        """Remove this section from the presentation.

        The member slides themselves are left in the deck; they are merged
        into the neighbouring section (previous when one exists, else next)
        so the section list stays a complete partition.  Deleting the only
        section removes the section grouping entirely.
        """
        _remove_section_element(self._section)
