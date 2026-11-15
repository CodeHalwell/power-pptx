# pyright: reportPrivateUsage=false

"""Deck fixtures for tests of removing and duplicating slides.

What makes removing a slide hard is everything else in the package that refers
to it, so these helpers build each kind of reference PowerPoint writes:

* a custom show listing slides (`add_custom_show`),
* a "jump to slide" link shown on hover (`link_on_hover`) — the library only
  writes click links itself,
* an action button on a layout (`add_layout_button`),
* the outline view's list of collapsed slides (`add_outline_view_entries`),
  kept in `ppt/viewProps.xml`, a part the library holds only as bytes, and
* `linked_deck()`, a deck with all of them pointing at its second slide,
  which also carries the parts that should go with it.
"""

from __future__ import annotations

import io

from lxml import etree

from power_pptx import Presentation
from power_pptx.chart.data import CategoryChartData
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT
from power_pptx.oxml import parse_xml
from power_pptx.oxml.ns import nsdecls, qn
from power_pptx.util import Inches

#: A 1x1 PNG.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000000000500010d0a2db40000"
    "000049454e44ae426082"
)

#: A different 1x1 PNG, so a picture of its own can be told apart from a shared one.
OTHER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600"
    "00001f15c4890000000d49444154789c626001000000ffff030000"
    "060005a5f5e2bd0000000049454e44ae426082"
)


def titled_deck(*titles: str) -> Presentation:
    """A deck with one blank slide per title, the title in a text box."""
    prs = Presentation()
    for title in titles:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        box.text_frame.text = title
    return prs


def add_chart(slide):
    """Add a small column chart to *slide* and return the chart."""
    chart_data = CategoryChartData()
    chart_data.categories = ["a", "b"]
    chart_data.add_series("s", (1, 2))
    return slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(2), Inches(5), Inches(3), chart_data
    ).chart


def add_custom_show(prs: Presentation, name: str, slides) -> None:
    """Give *prs* a custom show named *name* listing *slides*, as PowerPoint writes one."""
    prs_element = prs.part._element
    custShowLst = prs_element.find(qn("p:custShowLst"))
    if custShowLst is None:
        custShowLst = parse_xml("<p:custShowLst %s/>" % nsdecls("p"))
        prs_element.find(qn("p:defaultTextStyle")).addprevious(custShowLst)
    entries = "".join(
        '<p:sld r:id="%s"/>' % prs.part.relate_to(slide.part, RT.SLIDE) for slide in slides
    )
    custShowLst.append(
        parse_xml(
            '<p:custShow %s name="%s" id="%d"><p:sldLst>%s</p:sldLst></p:custShow>'
            % (nsdecls("p", "r"), name, len(custShowLst), entries)
        )
    )


def custom_show_rIds(prs: Presentation) -> list[list[str]]:
    """The relationship ids each custom show of *prs* lists, show by show."""
    r_id = qn("r:id")
    return [
        [sld.get(r_id) for sld in show.iter(qn("p:sld"))]
        for show in prs.part._element.iter(qn("p:custShow"))
    ]


def custom_show_slides(prs: Presentation) -> list[list]:
    """The slides each custom show of *prs* lists, show by show."""
    return [[prs.part.related_slide(rId) for rId in show] for show in custom_show_rIds(prs)]


def view_props_part(prs: Presentation):
    """The part holding `ppt/viewProps.xml`, which the library keeps as bytes."""
    return prs.part.part_related_by(RT.VIEW_PROPS)


def add_outline_view_entries(prs: Presentation, slides) -> None:
    """List *slides* as collapsed in the outline view, as PowerPoint records them.

    PowerPoint keeps the list in `ppt/viewProps.xml`, by relationships of
    that part to the slides.
    """
    part = view_props_part(prs)
    viewPr = parse_xml(part.blob)
    entries = "".join(
        '<p:sld r:id="%s" collapse="1"/>' % part.relate_to(slide.part, RT.SLIDE) for slide in slides
    )
    viewPr.find(qn("p:notesTextViewPr")).addprevious(
        parse_xml(
            "<p:outlineViewPr %s><p:cViewPr><p:scale>"
            '<a:sx n="33" d="100"/><a:sy n="33" d="100"/></p:scale>'
            '<p:origin x="0" y="0"/></p:cViewPr><p:sldLst>%s</p:sldLst></p:outlineViewPr>'
            % (nsdecls("p", "a", "r"), entries)
        )
    )
    part.blob = etree.tostring(viewPr, encoding="UTF-8", standalone=True)


def outline_view_slides(prs: Presentation) -> list:
    """The slides the outline view of *prs* lists."""
    part = view_props_part(prs)
    r_id = qn("r:id")
    return [
        part.related_part(sld.get(r_id)).slide for sld in parse_xml(part.blob).iter(qn("p:sld"))
    ]


def link_on_hover(shape, slide) -> None:
    """Make *shape* jump to *slide* when the pointer moves over it."""
    rId = shape.part.relate_to(slide.part, RT.SLIDE)
    shape._element.nvSpPr.cNvPr.append(
        parse_xml(
            '<a:hlinkHover %s r:id="%s" action="ppaction://hlinksldjump"/>'
            % (nsdecls("a", "r"), rId)
        )
    )


def add_layout_button(layout, slide) -> None:
    """Put a button on *layout* that jumps to *slide*, as an action button on a layout does."""
    rId = layout.part.relate_to(slide.part, RT.SLIDE)
    layout.shapes._spTree.append(
        parse_xml(
            '<p:sp %s><p:nvSpPr><p:cNvPr id="90" name="Button">'
            '<a:hlinkClick r:id="%s" action="ppaction://hlinksldjump"/></p:cNvPr>'
            "<p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr/></p:sp>" % (nsdecls("p", "a", "r"), rId)
        )
    )


def linked_deck() -> Presentation:
    """Four slides, "a" to "d", with every kind of reference pointing at slide "b".

    Slide "b" has notes, a chart, a picture of its own and a picture it shares
    with slide "a". It is linked to from a shape on "a" (on click), a text run
    on "c", a shape on "d" (on hover), the notes of "a", and a button on the
    Blank layout. It is in the first of two sections, in a custom show with
    "c", and collapsed in the outline view with "c".
    """
    prs = titled_deck("a", "b", "c", "d")
    a, b, c, d = prs.slides
    b.notes = "notes of b"
    add_chart(b)
    a.shapes.add_picture(io.BytesIO(PNG), Inches(6), Inches(1), Inches(1), Inches(1))
    b.shapes.add_picture(io.BytesIO(PNG), Inches(6), Inches(1), Inches(1), Inches(1))
    b.shapes.add_picture(io.BytesIO(OTHER_PNG), Inches(8), Inches(1), Inches(1), Inches(1))
    a.shapes[0].click_action.target_slide = b
    c.shapes[0].text_frame.paragraphs[0].runs[0].hyperlink.target_slide = b
    link_on_hover(d.shapes[0], b)
    a.notes = "see b"
    a.notes_slide.notes_text_frame.paragraphs[0].runs[0].hyperlink.target_slide = b
    add_layout_button(prs.slide_layouts[6], b)
    prs.sections.add("One", start_slide_index=0)
    prs.sections.add("Two", start_slide_index=2)
    add_custom_show(prs, "Short", [b, c])
    add_outline_view_entries(prs, [b, c])
    return prs
