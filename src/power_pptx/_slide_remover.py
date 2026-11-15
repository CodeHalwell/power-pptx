"""Slide removal machinery for :meth:`Slides.remove() <power_pptx.slide.Slides.remove>`.

Taking a slide's ``p:sldId`` out of ``p:sldIdLst`` hides the slide, but on its
own leaves the package inconsistent: the presentation still relates to the
slide part, sections and custom shows still list it, and every "jump to
slide" link on the other slides still points at it — so the slide stays in
the saved package as an orphan reached through the link.  Removal therefore:

* takes the slide's entry out of ``p:sldIdLst`` and its id out of every
  ``p14:sectionLst`` section;
* drops every relationship to the slide from the parts that stay, with
  whatever refers to it through one: an entry of a custom show
  (``p:custShowLst/p:custShow/p:sldLst``) or of the outline view's slide
  list (``ppt/viewProps.xml``) goes, and so does a link — a
  ``click_action`` target, an ``hlinkClick`` / ``hlinkHover`` on a shape or
  text run, on another slide, a notes slide, a layout or a master.  The
  shape or text run itself stays; it just stops being a link.

Nothing else needs deleting.  The package is saved by walking relationships
from its root, so once nothing that stays relates to the slide, the slide and
everything only it uses — its notes slide, its charts and their workbooks,
pictures and media no other slide shows — are no longer saved.  A picture
another slide also shows is still reached through that slide and stays.

The public entry point is :func:`remove_slide`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, cast

from lxml import etree

from power_pptx._slide_importer import (
    _remap_rids,  # pyright: ignore[reportPrivateUsage, reportUnknownVariableType]
)
from power_pptx.opc.oxml import serialize_part_xml
from power_pptx.opc.package import XmlPart
from power_pptx.oxml import parse_xml
from power_pptx.oxml.ns import qn

if TYPE_CHECKING:
    from power_pptx.opc.package import OpcPackage, Part
    from power_pptx.oxml.presentation import CT_Presentation, CT_SlideId
    from power_pptx.oxml.xmlchemy import BaseOxmlElement
    from power_pptx.parts.presentation import PresentationPart


def remove_slide(prs_part: PresentationPart, slide_part: Part) -> None:
    """Remove *slide_part* from the presentation of *prs_part*, leaving no reference to it.

    Raises |ValueError| when *slide_part* is not one of the presentation's
    slides; nothing is changed then.
    """
    entries = slide_id_entries(prs_part, slide_part)
    prs_element = _presentation_element(prs_part)
    sldIdLst = prs_element.get_or_add_sldIdLst()
    for sldId in entries:
        sldIdLst.remove(sldId)
    _remove_section_members(prs_element, {sldId.id for sldId in entries})
    for part in list(_iter_remaining_parts(prs_part.package, slide_part)):
        _unlink(part, slide_part)


def slide_id_entries(prs_part: PresentationPart, slide_part: Part) -> list[CT_SlideId]:
    """The ``p:sldId`` entries of the presentation that list *slide_part*.

    Raises |ValueError|, saying why, when there is none: *slide_part*
    belongs to another presentation, or has been removed from this one.
    """
    rIds = _relationship_ids(prs_part, slide_part)
    sldIdLst = _presentation_element(prs_part).sldIdLst
    entries = [] if sldIdLst is None else [s for s in sldIdLst.sldId_lst if s.rId in rIds]
    if entries:
        return entries
    if slide_part.package is not prs_part.package:
        raise ValueError(
            "slide belongs to another presentation; use Presentation.import_slide() "
            "to copy it into this one"
        )
    raise ValueError("slide is not in this presentation; it may already have been removed")


def _presentation_element(prs_part: PresentationPart) -> CT_Presentation:
    """The ``p:presentation`` element of *prs_part*."""
    return cast("CT_Presentation", prs_part._element)  # pyright: ignore[reportPrivateUsage]


def _relationship_ids(part: Part, target: Part) -> set[str]:
    """The ids of *part*'s internal relationships whose target is *target*."""
    return {
        rel.rId for rel in part.rels.values() if not rel.is_external and rel.target_part is target
    }


def _remove_section_members(prs_element: CT_Presentation, slide_ids: set[int]) -> None:
    """Take the slides numbered *slide_ids* out of every section of the deck.

    A section left without slides stays, as it does when its last slide is
    deleted in PowerPoint.
    """
    sectionLst = prs_element.sectionLst
    if sectionLst is None:
        return
    for section in sectionLst.section_lst:
        for slide_id in slide_ids:
            section.remove_sldId(slide_id)


def _iter_remaining_parts(package: OpcPackage, removed: Part) -> Iterator[Part]:
    """Generate each part reachable from the package root without passing through *removed*.

    These are the parts saved once nothing relates to *removed*; a part only
    *removed* leads to is not among them.
    """
    seen = {removed}
    pending = list(package._rels.values())  # pyright: ignore[reportPrivateUsage]
    while pending:
        rel = pending.pop()
        if rel.is_external or rel.target_part in seen:
            continue
        part = rel.target_part
        seen.add(part)
        yield part
        pending.extend(part.rels.values())


def _unlink(part: Part, removed: Part) -> None:
    """Drop *part*'s relationships to *removed*, and every reference to them in its XML.

    The XML of a part the library keeps only as bytes, such as
    ``ppt/viewProps.xml``, is rewritten too.
    """
    rIds = _relationship_ids(part, removed)
    if not rIds:
        return
    element = _xml_of(part)
    if element is not None:
        _remove_references(element, rIds)
        if not isinstance(part, XmlPart):
            part.blob = serialize_part_xml(element)
    for rId in rIds:
        part.rels.pop(rId)


def _xml_of(part: Part) -> BaseOxmlElement | None:
    """The XML of *part* as an element, or |None| for a part that is not XML.

    That is an XML part's own element, or a parsed copy of the content of a
    part the library keeps only as bytes.
    """
    if isinstance(part, XmlPart):
        return part._element  # pyright: ignore[reportPrivateUsage]
    if not part.content_type.endswith("xml"):
        return None
    try:
        return cast("BaseOxmlElement", parse_xml(part.blob))
    except etree.XMLSyntaxError:
        return None


def _remove_references(element: BaseOxmlElement, rIds: set[str]) -> None:
    """Remove every reference to the relationships *rIds* from *element*'s tree.

    An entry of a slide list (``p:sld``, in a custom show or the outline
    view) or a hyperlink element naming one goes whole; any other reference
    attribute naming one is deleted.
    """
    r_id = qn("r:id")
    for entry in list(element.iter(qn("p:sld"))):
        parent = entry.getparent()
        if parent is not None and entry.get(r_id) in rIds:
            parent.remove(entry)
    _remap_rids(element, {}, rIds)
