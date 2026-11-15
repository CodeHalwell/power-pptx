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
from typing import TYPE_CHECKING, Iterator, cast

from power_pptx.oxml.ns import qn
from power_pptx.shared import ParentedElementProxy

if TYPE_CHECKING:
    from lxml.etree import _Element  # pyright: ignore[reportPrivateUsage]

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
    siblings = cast("list[CT_Section]", list(sectionLst))
    if len(siblings) == 1:
        _remove_section_extension(sectionLst)
        return

    idx = siblings.index(section_elm)
    member_ids = [sldId.id for sldId in section_elm.sldId_lst]
    sectionLst.remove(section_elm)
    if not member_ids:
        return
    if idx > 0:
        # Merge into the previous section: its slides now precede these.
        for slide_id in member_ids:
            siblings[idx - 1].add_sldId(slide_id)
    else:
        # The first section was removed: its slides precede the (new) first
        # section's members.
        _prepend_members(siblings[1], member_ids)


def _remove_section_extension(sectionLst: _Element) -> None:
    """Remove the ``p:ext`` carrying *sectionLst*, and the ``p:extLst`` if that empties it."""
    ext = sectionLst.getparent()
    if ext is None:
        return
    extLst = ext.getparent()
    if extLst is None:
        return
    extLst.remove(ext)
    if len(extLst) > 0:
        return
    prs_elm = extLst.getparent()
    if prs_elm is not None:
        prs_elm.remove(extLst)


def _prepend_members(section_elm: CT_Section, slide_ids: list[int]) -> None:
    """Put the slides *slide_ids*, in order, ahead of the members of *section_elm*."""
    target_lst = section_elm.get_or_add_sldIdLst()
    for pos, slide_id in enumerate(slide_ids):
        entry = target_lst.makeelement(qn("p14:sldId"), {"id": str(slide_id)})
        target_lst.insert(pos, entry)


def _follow_slide_order(
    prs_elm: CT_Presentation,
    old_ids: list[int],
    new_ids: list[int],
    moved: frozenset[int] | None = None,
) -> None:
    """Bring the deck's sections into line after its slides were put in a new order.

    `old_ids` and `new_ids` are the numeric slide ids before and after. A
    section is a contiguous run of slides, so a slide that lands among another
    section's slides has to change section, or the section list stops
    describing the deck (PowerPoint shows such a slide in the wrong group).

    `moved`, when given, names the slides that were moved, as by
    :meth:`Slides.move`; every other slide keeps its section. Each moved slide
    is placed the way PowerPoint places a slide dropped in the slide sorter:
    it stays in its own section when it lands next to another member of it,
    and otherwise joins the section of the slide before it (of the slide after
    it, when it lands first).

    Without `moved`, as for :meth:`Slides.reorder`, the order is examined
    first. When every section's slides are still contiguous — the deck was
    reversed, say, or whole sections were shuffled — every slide keeps its
    section and the sections are put in the order of their slides. Otherwise
    the slides that are still in their old relative order (a longest such
    run) keep their sections and the others are placed as moved slides are.

    Each section's member list is rewritten in deck order, which also drops
    references to slides no longer in the deck. Does nothing for a deck
    without sections.
    """
    sectionLst = getattr(prs_elm, "sectionLst", None)
    if sectionLst is None or old_ids == new_ids:
        return
    sections = list(sectionLst.section_lst)
    in_deck = set(new_ids)
    owner = _section_owners(sections, in_deck)

    if moved is None:
        block_order = _sections_as_blocks(sections, new_ids, owner)
        if block_order is not None:
            for section in block_order:
                sectionLst.append(section)  # -- moves it to the end, in turn
            _write_members(sections, new_ids, owner)
            return
        old_position = {slide_id: i for i, slide_id in enumerate(old_ids)}
        anchored = _longest_increasing_run(new_ids, old_position)
    else:
        anchored = in_deck - moved
    _write_members(sections, new_ids, _sections_after_placing(new_ids, anchored, owner))


def _section_owners(sections: list[CT_Section], in_deck: set[int]) -> dict[int, CT_Section]:
    """The section each slide of *in_deck* belongs to: the first of *sections* listing it."""
    owner: dict[int, CT_Section] = {}
    for section in sections:
        for sldId in section.sldId_lst:
            if sldId.id in in_deck:
                owner.setdefault(sldId.id, section)
    return owner


def _sections_after_placing(
    new_ids: list[int], anchored: set[int], owner: dict[int, CT_Section]
) -> dict[int, CT_Section | None]:
    """The section of each slide of *new_ids* once those not *anchored* have been placed.

    An anchored slide keeps the section *owner* gives it; every other slide is
    placed, in deck order, by :func:`_landing_section`.
    """
    final: dict[int, CT_Section | None] = {
        slide_id: owner.get(slide_id) for slide_id in new_ids if slide_id in anchored
    }
    for i, slide_id in enumerate(new_ids):
        if slide_id in anchored:
            continue
        before = final[new_ids[i - 1]] if i > 0 else None
        after = next(
            (final[later] for later in new_ids[i + 1 :] if later in anchored), None
        )
        final[slide_id] = _landing_section(owner.get(slide_id), before, after)
    return final


def _landing_section(
    own: CT_Section | None, before: CT_Section | None, after: CT_Section | None
) -> CT_Section | None:
    """The section a moved slide of section *own* joins, landing between *before* and *after*.

    It stays in its own section when it lands next to another member of it,
    and otherwise joins the section of the slide before it (of the slide after
    it, when it lands first or the slide before it is in no section).
    """
    if own is not None and (own is before or own is after):
        return own
    if before is not None:
        return before
    if after is not None:
        return after
    return own


def _sections_as_blocks(
    sections: list[CT_Section], new_ids: list[int], owner: dict[int, CT_Section]
) -> list[CT_Section] | None:
    """The sections in the order their slides now appear, or |None| if any is split.

    A section without slides keeps its place after the section it followed.
    """
    seen: list[CT_Section] = []
    previous = None
    for slide_id in new_ids:
        section = owner.get(slide_id)
        if section is previous:
            continue
        if section is not None and section in seen:
            return None
        if section is not None:
            seen.append(section)
        previous = section
    order = list(seen)
    for i, section in enumerate(sections):
        if section in order:
            continue
        # -- empty: after the section it followed, or first if it was first
        position = order.index(sections[i - 1]) + 1 if i > 0 else 0
        order.insert(position, section)
    return order


def _longest_increasing_run(new_ids: list[int], old_position: dict[int, int]) -> set[int]:
    """The ids of a longest set of slides whose relative order did not change."""
    import bisect

    tails: list[int] = []  # -- old position ending the best run of each length
    tail_index: list[int] = []  # -- ...and the index in `new_ids` it came from
    parent: list[int] = [-1] * len(new_ids)
    for i, slide_id in enumerate(new_ids):
        position = old_position.get(slide_id, -1)
        length = bisect.bisect_left(tails, position)
        if length == len(tails):
            tails.append(position)
            tail_index.append(i)
        else:
            tails[length] = position
            tail_index[length] = i
        parent[i] = tail_index[length - 1] if length > 0 else -1
    run: set[int] = set()
    i = tail_index[-1] if tail_index else -1
    while i != -1:
        run.add(new_ids[i])
        i = parent[i]
    return run


def _write_members(
    sections: list[CT_Section], new_ids: list[int], section_of: dict
) -> None:
    """Rewrite each section's member list from `section_of`, in deck order."""
    for section in sections:
        sldIdLst = section.get_or_add_sldIdLst()
        for sldId in list(sldIdLst):
            sldIdLst.remove(sldId)
    for slide_id in new_ids:
        section = section_of.get(slide_id)
        if section is not None:
            section.add_sldId(slide_id)


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
            self._check_new_id(id)
        was_unsectioned = not self._section_elms
        sectionLst = self._prs_elm.get_or_add_sectionLst()
        section_elm = sectionLst.add_section(name, section_id=id)
        section = Section(section_elm, self._prs)
        if start_slide_index is None:
            return section

        slides = list(self._prs.slides)
        self._claim_slides(section, slides[start_slide_index:])
        # First section of the deck starting beyond slide 0: cover the
        # preceding slides so the section list partitions the whole deck.
        if was_unsectioned and start_slide_index > 0:
            default_elm = sectionLst.add_section("Default Section")
            section_elm.addprevious(default_elm)
            default = Section(default_elm, self._prs)
            for slide in slides[:start_slide_index]:
                default.add_slide(slide)
        return section

    def _check_new_id(self, section_id: str) -> None:
        """Raise |ValueError| unless *section_id* is a GUID no section of the deck has yet."""
        if not _GUID_RE.match(section_id):
            raise ValueError(
                "section id must be a brace-wrapped GUID like "
                "'{3E86B4F5-40E6-4F32-8B4D-BE3E1E4C8A27}'; got %r" % (section_id,)
            )
        if any(s.id.lower() == section_id.lower() for s in self._section_elms):
            raise ValueError("section id %s is already used in this deck" % section_id)

    def _claim_slides(self, section: Section, slides: list[Slide]) -> None:
        """Make *slides* members of *section*, and of no other section."""
        # Sections don't overlap: take the claimed slides away from any
        # other section before assigning them to this one.
        for other in self:
            if other._element is section._element:
                continue
            for slide in slides:
                other.remove_slide(slide)
        for slide in slides:
            section.add_slide(slide)

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
