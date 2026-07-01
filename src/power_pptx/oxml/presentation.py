"""Custom element classes for presentation-related XML elements."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Callable, cast

from power_pptx.oxml.ns import nsmap, qn
from power_pptx.oxml.simpletypes import ST_SlideId, ST_SlideSizeCoordinate, XsdString
from power_pptx.oxml.xmlchemy import (
    BaseOxmlElement,
    OxmlElement,
    RequiredAttribute,
    ZeroOrMore,
    ZeroOrOne,
)

if TYPE_CHECKING:
    from power_pptx.util import Length

# -- GUID identifying the PowerPoint 2010 sectionLst presentation extension. --
SECTION_EXT_URI = "{521415D9-36F7-43E2-AB2F-B90AF26B5E84}"


class CT_Presentation(BaseOxmlElement):
    """`p:presentation` element, root of the Presentation part stored as `/ppt/presentation.xml`."""

    get_or_add_sldSz: Callable[[], CT_SlideSize]
    get_or_add_sldIdLst: Callable[[], CT_SlideIdList]
    get_or_add_sldMasterIdLst: Callable[[], CT_SlideMasterIdList]
    get_or_add_embeddedFontLst: Callable[[], BaseOxmlElement]
    get_or_add_extLst: Callable[[], BaseOxmlElement]

    sldMasterIdLst: CT_SlideMasterIdList | None = (
        ZeroOrOne(  # pyright: ignore[reportAssignmentType]
            "p:sldMasterIdLst",
            successors=(
                "p:notesMasterIdLst",
                "p:handoutMasterIdLst",
                "p:sldIdLst",
                "p:sldSz",
                "p:notesSz",
            ),
        )
    )
    sldIdLst: CT_SlideIdList | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "p:sldIdLst", successors=("p:sldSz", "p:notesSz")
    )
    sldSz: CT_SlideSize | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "p:sldSz", successors=("p:notesSz",)
    )
    # -- `p:embeddedFontLst` follows `p:notesSz` but precedes `custShowLst`,
    # -- `photoAlbum`, `custDataLst`, `kinsoku`, `defaultTextStyle`,
    # -- `modifyVerifier`, and `extLst` in the CT_Presentation sequence.
    # -- Every default template already carries a `defaultTextStyle`, so a bare
    # -- append would place the font list *after* it and produce a
    # -- presentation.xml PowerPoint reports as broken. --
    embeddedFontLst: BaseOxmlElement | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "p:embeddedFontLst",
        successors=(
            "p:custShowLst",
            "p:photoAlbum",
            "p:custDataLst",
            "p:kinsoku",
            "p:defaultTextStyle",
            "p:modifyVerifier",
            "p:extLst",
        ),
    )
    # -- `p:extLst` is the final child of `p:presentation` (no successors). --
    extLst: BaseOxmlElement | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "p:extLst"
    )

    @property
    def sectionLst(self) -> CT_SectionList | None:
        """The `p14:sectionLst` element, or |None| if not present.

        Reaches through `p:extLst/p:ext[@uri='{...}']` to find the
        PowerPoint-2010 section-list extension.
        """
        ext = self._section_ext
        if ext is None:
            return None
        return cast("CT_SectionList | None", ext.find(qn("p14:sectionLst")))

    def get_or_add_sectionLst(self) -> CT_SectionList:
        """Return the `p14:sectionLst` element, newly created if not present.

        The wrapping `p:extLst/p:ext` are created as needed.
        """
        sectionLst = self.sectionLst
        if sectionLst is not None:
            return sectionLst
        ext = self._get_or_add_section_ext()
        sectionLst = cast("CT_SectionList", OxmlElement("p14:sectionLst", nsmap=nsmap("p14")))
        ext.append(sectionLst)
        return sectionLst

    @property
    def _section_ext(self) -> BaseOxmlElement | None:
        """The `p:ext` element carrying the section-list extension, or |None|."""
        extLst = self.extLst
        if extLst is None:
            return None
        for ext in extLst.findall(qn("p:ext")):
            if ext.get("uri") == SECTION_EXT_URI:
                return cast("BaseOxmlElement", ext)
        return None

    def _get_or_add_section_ext(self) -> BaseOxmlElement:
        """Return the section-list `p:ext`, newly created if not present."""
        ext = self._section_ext
        if ext is not None:
            return ext
        extLst = self.get_or_add_extLst()
        ext = OxmlElement("p:ext")
        ext.set("uri", SECTION_EXT_URI)
        extLst.append(ext)
        return ext


class CT_SlideId(BaseOxmlElement):
    """`p:sldId` element.

    Direct child of `p:sldIdLst` that contains an `rId` reference to a slide in the presentation.
    """

    id: int = RequiredAttribute("id", ST_SlideId)  # pyright: ignore[reportAssignmentType]
    rId: str = RequiredAttribute("r:id", XsdString)  # pyright: ignore[reportAssignmentType]


class CT_SlideIdList(BaseOxmlElement):
    """`p:sldIdLst` element.

    Direct child of <p:presentation> that contains a list of the slide parts in the presentation.
    """

    sldId_lst: list[CT_SlideId]

    _add_sldId: Callable[..., CT_SlideId]
    sldId = ZeroOrMore("p:sldId")

    def add_sldId(self, rId: str) -> CT_SlideId:
        """Create and return a reference to a new `p:sldId` child element.

        The new `p:sldId` element has its r:id attribute set to `rId`.
        """
        return self._add_sldId(id=self._next_id, rId=rId)

    @property
    def _next_id(self) -> int:
        """The next available slide ID as an `int`.

        Valid slide IDs start at 256. The next integer value greater than the max value in use is
        chosen, which minimizes that chance of reusing the id of a deleted slide.
        """
        MIN_SLIDE_ID = 256
        MAX_SLIDE_ID = 2147483647

        used_ids = [int(s) for s in cast("list[str]", self.xpath("./p:sldId/@id"))]
        simple_next = max([MIN_SLIDE_ID - 1] + used_ids) + 1
        if simple_next <= MAX_SLIDE_ID:
            return simple_next

        # -- fall back to search for next unused from bottom --
        valid_used_ids = sorted(id for id in used_ids if (MIN_SLIDE_ID <= id <= MAX_SLIDE_ID))
        return (
            next(
                candidate_id
                for candidate_id, used_id in enumerate(valid_used_ids, start=MIN_SLIDE_ID)
                if candidate_id != used_id
            )
            if valid_used_ids
            else 256
        )


class CT_SlideMasterIdList(BaseOxmlElement):
    """`p:sldMasterIdLst` element.

    Child of `p:presentation` containing references to the slide masters that belong to the
    presentation.
    """

    sldMasterId_lst: list[CT_SlideMasterIdListEntry]

    sldMasterId = ZeroOrMore("p:sldMasterId")


class CT_SlideMasterIdListEntry(BaseOxmlElement):
    """
    ``<p:sldMasterId>`` element, child of ``<p:sldMasterIdLst>`` containing
    a reference to a slide master.
    """

    rId: str = RequiredAttribute("r:id", XsdString)  # pyright: ignore[reportAssignmentType]


class CT_SlideSize(BaseOxmlElement):
    """`p:sldSz` element.

    Direct child of <p:presentation> that contains the width and height of slides in the
    presentation.
    """

    cx: Length = RequiredAttribute(  # pyright: ignore[reportAssignmentType]
        "cx", ST_SlideSizeCoordinate
    )
    cy: Length = RequiredAttribute(  # pyright: ignore[reportAssignmentType]
        "cy", ST_SlideSizeCoordinate
    )


# ===========================================================================
# PowerPoint 2010 section extension (`p14:sectionLst`).
#
# Stored inside `p:presentation/p:extLst/p:ext[@uri="{521415D9-...}"]`.  These
# `p14:*` classes are registered at module-import time (see bottom of file) so
# the off-limits `power_pptx.oxml.__init__` does not need editing.
# ===========================================================================


class CT_SectionList(BaseOxmlElement):
    """`p14:sectionLst` element, container for the deck's `p14:section` children."""

    section_lst: list[CT_Section]

    _add_section: Callable[..., CT_Section]
    section = ZeroOrMore("p14:section")

    def add_section(self, name: str, section_id: str | None = None) -> CT_Section:
        """Create, append, and return a new `p14:section` element.

        `name` is the user-visible section label.  `section_id`, when supplied,
        is the brace-wrapped GUID used as the section's `id`; a random one is
        generated when omitted.
        """
        if section_id is None:
            section_id = "{%s}" % str(uuid.uuid4()).upper()
        section = self._add_section()
        section.name = name
        section.id = section_id
        return section


class CT_Section(BaseOxmlElement):
    """`p14:section` element, a single named section referencing member slides."""

    get_or_add_sldIdLst: Callable[[], CT_SectionSlideIdList]

    name: str = RequiredAttribute("name", XsdString)  # pyright: ignore[reportAssignmentType]
    id: str = RequiredAttribute("id", XsdString)  # pyright: ignore[reportAssignmentType]

    sldIdLst: CT_SectionSlideIdList | None = (
        ZeroOrOne(  # pyright: ignore[reportAssignmentType]
            "p14:sldIdLst"
        )
    )

    @property
    def sldId_lst(self) -> list[CT_SectionSlideId]:
        """List of `p14:sldId` member references (possibly empty)."""
        sldIdLst = self.sldIdLst
        if sldIdLst is None:
            return []
        return sldIdLst.sldId_lst

    def add_sldId(self, id: int) -> CT_SectionSlideId:
        """Append a `p14:sldId` referencing the slide whose numeric id is `id`."""
        sldIdLst = self.get_or_add_sldIdLst()
        return sldIdLst.add_sldId(id)

    def remove_sldId(self, id: int) -> None:
        """Remove the `p14:sldId` member referencing `id`, if present."""
        for sldId in list(self.sldId_lst):
            if sldId.id == id:
                sldId.getparent().remove(sldId)


class CT_SectionSlideIdList(BaseOxmlElement):
    """`p14:sldIdLst` element, child of `p14:section` listing member slide ids."""

    sldId_lst: list[CT_SectionSlideId]

    _add_sldId: Callable[..., CT_SectionSlideId]
    sldId = ZeroOrMore("p14:sldId")

    def add_sldId(self, id: int) -> CT_SectionSlideId:
        """Create and return a new `p14:sldId` child with its `id` set to `id`."""
        return self._add_sldId(id=id)


class CT_SectionSlideId(BaseOxmlElement):
    """`p14:sldId` element, references a slide by its numeric `p:sldId/@id` value."""

    id: int = RequiredAttribute("id", ST_SlideId)  # pyright: ignore[reportAssignmentType]


# -- Register the `p14:*` section element classes so the lxml parser maps these
# -- tags to the custom classes above.  Done here (not in `oxml.__init__`) via
# -- the public `register_element_cls` hook.  Imported at module bottom (E402)
# -- to avoid the partial-import cycle with `power_pptx.oxml.__init__`, which
# -- imports this module while it is still initializing.
from power_pptx.oxml import register_element_cls  # noqa: E402

register_element_cls("p14:sectionLst", CT_SectionList)
register_element_cls("p14:section", CT_Section)
register_element_cls("p14:sldIdLst", CT_SectionSlideIdList)
register_element_cls("p14:sldId", CT_SectionSlideId)
