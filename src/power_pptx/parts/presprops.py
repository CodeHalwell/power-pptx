"""Presentation-properties part, corresponds to `/ppt/presProps.xml` in a package."""

from __future__ import annotations

from typing import TYPE_CHECKING

from power_pptx.opc.constants import CONTENT_TYPE as CT
from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT
from power_pptx.opc.package import XmlPart
from power_pptx.opc.packuri import PackURI
from power_pptx.oxml.presprops import CT_PresentationProperties

if TYPE_CHECKING:
    from power_pptx.package import Package
    from power_pptx.parts.presentation import PresentationPart


class PresentationPropertiesPart(XmlPart):
    """Corresponds to the part named `/ppt/presProps.xml`.

    Holds presentation-wide settings that are not part of the slide content:
    the slide-show setup (`p:showPr`), print and web-publishing options, the
    recently-used colour list and PowerPoint's own extension list. Only the
    slide-show setup is given an API (see
    :attr:`power_pptx.presentation.Presentation.slide_show`); everything else
    passes through a load/save cycle unchanged.
    """

    _element: CT_PresentationProperties

    #: |True| only for a part this library added to a deck that had none, so
    #: it can be taken away again if it ends up empty. A part that arrived
    #: with the file is never removed.
    added_on_demand: bool = False

    @classmethod
    def new(cls, package: Package) -> PresentationPropertiesPart:
        """Return a new, empty presentation-properties part for `package`.

        The part is not yet related to anything; use :meth:`get_or_add` to
        create one that is.
        """
        # -- `/ppt/presProps.xml` is the name every producer uses. Fall back to
        # -- a numbered name only if some unrelated part already holds it. --
        partname = PackURI("/ppt/presProps.xml")
        if any(part.partname == partname for part in package.iter_parts()):
            partname = package.next_partname("/ppt/presProps%d.xml")
        part = cls(partname, CT.PML_PRES_PROPS, package, CT_PresentationProperties.new())
        part.added_on_demand = True
        return part

    @classmethod
    def find(cls, presentation_part: PresentationPart) -> PresentationPropertiesPart | None:
        """Return the presentation-properties part of `presentation_part`, or |None|.

        Never creates anything. A related part that was not loaded as this
        class (its content type is not the one the standard assigns) is
        treated as absent.
        """
        for rel in presentation_part.rels.values():
            if rel.is_external or rel.reltype != RT.PRES_PROPS:
                continue
            part = rel.target_part
            if isinstance(part, cls):
                return part
        return None

    @classmethod
    def get_or_add(cls, presentation_part: PresentationPart) -> PresentationPropertiesPart:
        """Return the presentation-properties part of `presentation_part`, adding one if needed.

        Raises |ValueError| if the deck already has a presentation-properties
        part this library could not load as XML; adding a second one would
        leave PowerPoint to choose between them.
        """
        existing = cls.find(presentation_part)
        if existing is not None:
            return existing
        for rel in presentation_part.rels.values():
            if not rel.is_external and rel.reltype == RT.PRES_PROPS:
                raise ValueError(
                    "this presentation already has a presentation-properties part (%s) with "
                    "the unexpected content type %r, so its settings cannot be changed"
                    % (rel.target_part.partname, rel.target_part.content_type)
                )
        part = cls.new(presentation_part.package)
        presentation_part.relate_to(part, RT.PRES_PROPS)
        return part

    @property
    def presentationPr(self) -> CT_PresentationProperties:
        """The `p:presentationPr` root element of this part."""
        return self._element

    def remove_from(self, presentation_part: PresentationPart) -> None:
        """Drop the relationship(s) from `presentation_part` to this part.

        A part nothing relates to is not written when the package is saved,
        so this removes it from the deck.
        """
        rIds = [
            rId
            for rId, rel in presentation_part.rels.items()
            if not rel.is_external and rel.target_part is self
        ]
        for rId in rIds:
            presentation_part.drop_rel(rId)
