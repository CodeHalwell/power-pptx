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

from typing import TYPE_CHECKING, Iterator

from power_pptx.shared import ParentedElementProxy

if TYPE_CHECKING:
    from power_pptx.oxml.presentation import (
        CT_Section,
        CT_SectionList,
    )
    from power_pptx.parts.presentation import PresentationPart
    from power_pptx.presentation import Presentation
    from power_pptx.slide import Slide


class Sections(ParentedElementProxy):
    """Sequence of |Section| objects belonging to a |Presentation|.

    Supports ``len()``, indexed access, and iteration.
    """

    part: PresentationPart  # pyright: ignore[reportIncompatibleMethodOverride]

    def __init__(self, sectionLst: CT_SectionList, prs: Presentation):
        super(Sections, self).__init__(sectionLst, prs)
        self._sectionLst = sectionLst
        self._prs = prs

    def __getitem__(self, idx: int) -> Section:
        """Provide indexed access, e.g. ``prs.sections[0]``."""
        try:
            section = self._sectionLst.section_lst[idx]
        except IndexError:
            raise IndexError("section index out of range")
        return Section(section, self._prs)

    def __iter__(self) -> Iterator[Section]:
        """Support iteration, e.g. ``for section in prs.sections:``."""
        for section in self._sectionLst.section_lst:
            yield Section(section, self._prs)

    def __len__(self) -> int:
        """Support ``len()`` built-in, e.g. ``len(prs.sections)``."""
        return len(self._sectionLst.section_lst)

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
        at N-1.  When `start_slide_index` is omitted, the section is created
        empty.

        `id` optionally fixes the section's brace-wrapped GUID; supplying it
        keeps output deterministic for tests.  A random GUID is generated
        otherwise.
        """
        section_elm = self._sectionLst.add_section(name, section_id=id)
        section = Section(section_elm, self._prs)
        if start_slide_index is not None:
            claimed = list(self._prs.slides)[start_slide_index:]
            # Sections don't overlap: take the claimed slides away from any
            # earlier section before assigning them to the new one.
            for other in self:
                if other._element is section_elm:
                    continue
                for slide in claimed:
                    other.remove_slide(slide)
            for slide in claimed:
                section.add_slide(slide)
        return section

    def remove(self, section: Section) -> None:
        """Remove `section` from this collection.

        Slides referenced by the section are not deleted from the deck; only
        the section grouping is removed.
        """
        self._sectionLst.remove(section._element)


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
        """Add `slide` to this section's membership (idempotent)."""
        slide_id = slide.slide_id
        if slide_id in self.slide_ids:
            return
        self._section.add_sldId(slide_id)

    def remove_slide(self, slide: Slide) -> None:
        """Remove `slide` from this section's membership (no-op if absent)."""
        self._section.remove_sldId(slide.slide_id)

    def delete(self) -> None:
        """Remove this section from the presentation.

        The member slides themselves are left in the deck.
        """
        parent = self._section.getparent()
        if parent is not None:
            parent.remove(self._section)
