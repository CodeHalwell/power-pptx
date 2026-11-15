"""Custom element classes for the presentation-properties part (`ppt/presProps.xml`)."""

from __future__ import annotations

from typing import Callable, cast

from power_pptx.oxml import parse_xml
from power_pptx.oxml.ns import nsdecls
from power_pptx.oxml.simpletypes import XsdBoolean
from power_pptx.oxml.xmlchemy import (
    BaseOxmlElement,
    Choice,
    OptionalAttribute,
    ZeroOrOne,
    ZeroOrOneChoice,
)


class CT_PresentationProperties(BaseOxmlElement):
    """`p:presentationPr` element, root of the presentation-properties part.

    Only `p:showPr` is modelled. The other children (`p:htmlPubPr`, `p:webPr`,
    `p:prnPr`, `p:clrMru` and `p:extLst`) are left exactly as they were read.
    """

    get_or_add_showPr: Callable[[], CT_ShowProperties]
    _remove_showPr: Callable[[], None]

    # -- CT_PresentationProperties is a sequence: htmlPubPr, webPr, prnPr,
    # -- showPr, clrMru, extLst. A bare append would land after the `p:extLst`
    # -- every PowerPoint-authored file carries and break the schema. --
    showPr: CT_ShowProperties | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "p:showPr", successors=("p:clrMru", "p:extLst")
    )

    @classmethod
    def new(cls) -> CT_PresentationProperties:
        """Return a new, empty `p:presentationPr` element.

        Declares the same three namespaces PowerPoint does, so anything added
        later (a `p:penClr` colour, say) needs no extra declarations.
        """
        return cast(
            CT_PresentationProperties,
            parse_xml("<p:presentationPr %s/>" % nsdecls("a", "r", "p")),
        )


class CT_ShowProperties(BaseOxmlElement):
    """`p:showPr` element, the slide-show settings of a presentation."""

    get_or_change_to_browse: Callable[[], BaseOxmlElement]
    get_or_change_to_kiosk: Callable[[], BaseOxmlElement]
    get_or_change_to_present: Callable[[], BaseOxmlElement]
    _remove_eg_showType: Callable[[], None]

    # -- CT_ShowProperties is a sequence: EG_ShowType, EG_SlideListChoice
    # -- (sldAll | sldRg | custShow), penClr, extLst. --
    eg_showType: BaseOxmlElement | None = ZeroOrOneChoice(  # pyright: ignore[reportAssignmentType]
        (Choice("p:present"), Choice("p:browse"), Choice("p:kiosk")),
        successors=("p:sldAll", "p:sldRg", "p:custShow", "p:penClr", "p:extLst"),
    )

    loop: bool = OptionalAttribute(  # pyright: ignore[reportAssignmentType]
        "loop", XsdBoolean, default=False
    )
    showAnimation: bool = OptionalAttribute(  # pyright: ignore[reportAssignmentType]
        "showAnimation", XsdBoolean, default=True
    )
    useTimings: bool = OptionalAttribute(  # pyright: ignore[reportAssignmentType]
        "useTimings", XsdBoolean, default=True
    )
    # -- The schema default for `showNarration` is false, but a presentation
    # -- with no `p:showPr` at all plays its narration: PowerPoint writes
    # -- `showNarration="1"` whenever it writes this element. So absence is
    # -- reported as |None| here, not folded into a default, and the caller
    # -- decides what it means. --
    showNarration: bool | None = OptionalAttribute(  # pyright: ignore[reportAssignmentType]
        "showNarration", XsdBoolean
    )

    @property
    def says_nothing(self) -> bool:
        """True when this element could be removed without changing the show.

        That is the case when it has no children and its attributes describe
        exactly what PowerPoint assumes for a presentation with no `p:showPr`:
        no looping, timings and animation used, narration played.
        """
        if len(self):
            return False
        if set(self.attrib) - {"loop", "showAnimation", "showNarration", "useTimings"}:
            return False
        return (
            self.loop is False
            and self.showAnimation is True
            and self.useTimings is True
            and self.showNarration is True
        )
