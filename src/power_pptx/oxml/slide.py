"""Slide-related custom element classes, including those for masters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, cast

from power_pptx.oxml import parse_from_template, parse_xml
from power_pptx.oxml.dml.fill import CT_GradientFillProperties
from power_pptx.oxml.ns import nsdecls
from power_pptx.oxml.simpletypes import XsdBoolean, XsdString, XsdUnsignedInt
from power_pptx.oxml.xmlchemy import (
    BaseOxmlElement,
    Choice,
    OneAndOnlyOne,
    OptionalAttribute,
    RequiredAttribute,
    ZeroOrMore,
    ZeroOrOne,
    ZeroOrOneChoice,
)

if TYPE_CHECKING:
    from power_pptx.oxml.shapes.groupshape import CT_GroupShape


class _BaseSlideElement(BaseOxmlElement):
    """Base class for the six slide types, providing common methods."""

    cSld: CT_CommonSlideData

    @property
    def spTree(self) -> CT_GroupShape:
        """Return required `p:cSld/p:spTree` grandchild."""
        return self.cSld.spTree


class CT_Background(BaseOxmlElement):
    """`p:bg` element."""

    _insert_bgPr: Callable[[CT_BackgroundProperties], None]

    # ---these two are actually a choice, not a sequence, but simpler for
    # ---present purposes this way.
    _tag_seq = ("p:bgPr", "p:bgRef")
    bgPr: CT_BackgroundProperties | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "p:bgPr", successors=()
    )
    bgRef = ZeroOrOne("p:bgRef", successors=())
    del _tag_seq

    def add_noFill_bgPr(self):
        """Return a new `p:bgPr` element with noFill properties."""
        xml = "<p:bgPr %s>\n" "  <a:noFill/>\n" "  <a:effectLst/>\n" "</p:bgPr>" % nsdecls("a", "p")
        bgPr = cast(CT_BackgroundProperties, parse_xml(xml))
        self._insert_bgPr(bgPr)
        return bgPr


class CT_BackgroundProperties(BaseOxmlElement):
    """`p:bgPr` element."""

    _tag_seq = (
        "a:noFill",
        "a:solidFill",
        "a:gradFill",
        "a:blipFill",
        "a:pattFill",
        "a:grpFill",
        "a:effectLst",
        "a:effectDag",
        "a:extLst",
    )
    eg_fillProperties = ZeroOrOneChoice(
        (
            Choice("a:noFill"),
            Choice("a:solidFill"),
            Choice("a:gradFill"),
            Choice("a:blipFill"),
            Choice("a:pattFill"),
            Choice("a:grpFill"),
        ),
        successors=_tag_seq[6:],
    )
    del _tag_seq

    def _new_gradFill(self):
        """Override default to add default gradient subtree."""
        return CT_GradientFillProperties.new_gradFill()


class CT_CommonSlideData(BaseOxmlElement):
    """`p:cSld` element."""

    _remove_bg: Callable[[], None]
    get_or_add_bg: Callable[[], CT_Background]

    _tag_seq = ("p:bg", "p:spTree", "p:custDataLst", "p:controls", "p:extLst")
    bg: CT_Background | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "p:bg", successors=_tag_seq[1:]
    )
    spTree: CT_GroupShape = OneAndOnlyOne("p:spTree")  # pyright: ignore[reportAssignmentType]
    del _tag_seq
    name: str = OptionalAttribute(  # pyright: ignore[reportAssignmentType]
        "name", XsdString, default=""
    )

    def get_or_add_bgPr(self) -> CT_BackgroundProperties:
        """Return `p:bg/p:bgPr` grandchild.

        If no such grandchild is present, any existing `p:bg` child is first removed and a new
        default `p:bg` with noFill settings is added.
        """
        bg = self.bg
        if bg is None or bg.bgPr is None:
            bg = self._change_to_noFill_bg()
        return cast(CT_BackgroundProperties, bg.bgPr)

    def _change_to_noFill_bg(self) -> CT_Background:
        """Establish a `p:bg` child with no-fill settings.

        Any existing `p:bg` child is first removed.
        """
        self._remove_bg()
        bg = self.get_or_add_bg()
        bg.add_noFill_bgPr()
        return bg


class CT_NotesMaster(_BaseSlideElement):
    """`p:notesMaster` element, root of a notes master part."""

    _tag_seq = ("p:cSld", "p:clrMap", "p:hf", "p:notesStyle", "p:extLst")
    cSld: CT_CommonSlideData = OneAndOnlyOne("p:cSld")  # pyright: ignore[reportAssignmentType]
    del _tag_seq

    @classmethod
    def new_default(cls) -> CT_NotesMaster:
        """Return a new `p:notesMaster` element based on the built-in default template."""
        return cast(CT_NotesMaster, parse_from_template("notesMaster"))


class CT_NotesSlide(_BaseSlideElement):
    """`p:notes` element, root of a notes slide part."""

    _tag_seq = ("p:cSld", "p:clrMapOvr", "p:extLst")
    cSld: CT_CommonSlideData = OneAndOnlyOne("p:cSld")  # pyright: ignore[reportAssignmentType]
    del _tag_seq

    @classmethod
    def new(cls) -> CT_NotesSlide:
        """Return a new ``<p:notes>`` element based on the default template.

        Note that the template does not include placeholders, which must be subsequently cloned
        from the notes master.
        """
        return cast(CT_NotesSlide, parse_from_template("notes"))


class CT_Slide(_BaseSlideElement):
    """`p:sld` element, root element of a slide part (XML document)."""

    _tag_seq = ("p:cSld", "p:clrMapOvr", "p:transition", "p:timing", "p:extLst")
    cSld: CT_CommonSlideData = OneAndOnlyOne("p:cSld")  # pyright: ignore[reportAssignmentType]
    clrMapOvr = ZeroOrOne("p:clrMapOvr", successors=_tag_seq[2:])
    transition: CT_SlideTransition | None = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "p:transition", successors=_tag_seq[3:]
    )
    timing = ZeroOrOne("p:timing", successors=_tag_seq[4:])
    del _tag_seq

    @classmethod
    def new(cls) -> CT_Slide:
        """Return new `p:sld` element configured as base slide shape."""
        return cast(CT_Slide, parse_xml(cls._sld_xml()))

    @property
    def bg(self):
        """Return `p:bg` grandchild or None if not present."""
        return self.cSld.bg

    def get_or_add_childTnLst(self):
        """Return parent element for a new `p:video` child element.

        The `p:video` element causes play controls to appear under a video
        shape (pic shape containing video). There can be more than one video
        shape on a slide, which causes the precondition to vary. It needs to
        handle the case when there is no `p:sld/p:timing` element and when
        that element already exists. If the case isn't simple, it just nukes
        what's there and adds a fresh one. This could theoretically remove
        desired existing timing information, but there isn't any evidence
        available to me one way or the other, so I've taken the simple
        approach.
        """
        childTnLst = self._childTnLst
        if childTnLst is None:
            childTnLst = self._add_childTnLst()
        return childTnLst

    def _add_childTnLst(self):
        """Add `./p:timing/p:tnLst/p:par/p:cTn/p:childTnLst` descendant.

        Any existing `p:timing` child element is ruthlessly removed and
        replaced.
        """
        self.remove(self.get_or_add_timing())
        timing = parse_xml(self._childTnLst_timing_xml())
        self._insert_timing(timing)
        return timing.xpath("./p:tnLst/p:par/p:cTn/p:childTnLst")[0]

    @property
    def _childTnLst(self):
        """Return `./p:timing/p:tnLst/p:par/p:cTn/p:childTnLst` descendant.

        Return None if that element is not present.
        """
        childTnLsts = self.xpath("./p:timing/p:tnLst/p:par/p:cTn/p:childTnLst")
        if not childTnLsts:
            return None
        return childTnLsts[0]

    @staticmethod
    def _childTnLst_timing_xml():
        return (
            "<p:timing %s>\n"
            "  <p:tnLst>\n"
            "    <p:par>\n"
            '      <p:cTn id="1" dur="indefinite" restart="never" nodeType="'
            'tmRoot">\n'
            "        <p:childTnLst/>\n"
            "      </p:cTn>\n"
            "    </p:par>\n"
            "  </p:tnLst>\n"
            "</p:timing>" % nsdecls("p")
        )

    @staticmethod
    def _sld_xml():
        return (
            "<p:sld %s>\n"
            "  <p:cSld>\n"
            "    <p:spTree>\n"
            "      <p:nvGrpSpPr>\n"
            '        <p:cNvPr id="1" name=""/>\n'
            "        <p:cNvGrpSpPr/>\n"
            "        <p:nvPr/>\n"
            "      </p:nvGrpSpPr>\n"
            "      <p:grpSpPr/>\n"
            "    </p:spTree>\n"
            "  </p:cSld>\n"
            "  <p:clrMapOvr>\n"
            "    <a:masterClrMapping/>\n"
            "  </p:clrMapOvr>\n"
            "</p:sld>" % nsdecls("a", "p", "r")
        )


class CT_SlideLayout(_BaseSlideElement):
    """`p:sldLayout` element, root of a slide layout part."""

    _tag_seq = ("p:cSld", "p:clrMapOvr", "p:transition", "p:timing", "p:hf", "p:extLst")
    cSld: CT_CommonSlideData = OneAndOnlyOne("p:cSld")  # pyright: ignore[reportAssignmentType]
    del _tag_seq


class CT_SlideLayoutIdList(BaseOxmlElement):
    """`p:sldLayoutIdLst` element, child of `p:sldMaster`.

    Contains references to the slide layouts that inherit from the slide master.
    """

    sldLayoutId_lst: list[CT_SlideLayoutIdListEntry]

    sldLayoutId = ZeroOrMore("p:sldLayoutId")


class CT_SlideLayoutIdListEntry(BaseOxmlElement):
    """`p:sldLayoutId` element, child of `p:sldLayoutIdLst`.

    Contains a reference to a slide layout.
    """

    rId: str = RequiredAttribute("r:id", XsdString)  # pyright: ignore[reportAssignmentType]


class CT_SlideMaster(_BaseSlideElement):
    """`p:sldMaster` element, root of a slide master part."""

    get_or_add_sldLayoutIdLst: Callable[[], CT_SlideLayoutIdList]

    _tag_seq = (
        "p:cSld",
        "p:clrMap",
        "p:sldLayoutIdLst",
        "p:transition",
        "p:timing",
        "p:hf",
        "p:txStyles",
        "p:extLst",
    )
    cSld: CT_CommonSlideData = OneAndOnlyOne("p:cSld")  # pyright: ignore[reportAssignmentType]
    sldLayoutIdLst: CT_SlideLayoutIdList = ZeroOrOne(  # pyright: ignore[reportAssignmentType]
        "p:sldLayoutIdLst", successors=_tag_seq[3:]
    )
    del _tag_seq


class CT_SlideTransition(BaseOxmlElement):
    """`p:transition` element, specifying the transition into a slide.

    The transition kind is encoded by which child element is present (e.g.
    ``<p:fade/>``, ``<p:wipe/>``, ``<p14:morph/>``); ``<p:transition>`` may
    have at most one such child. Attributes control timing:

    * ``spd`` – legacy speed bucket (``slow``, ``med``, ``fast``).
    * ``advClick`` – whether the slide advances on mouse click. Default is
      ``True`` if the attribute is absent; setting it to ``False`` is the
      common case for kiosk-style auto-advance.
    * ``advTm`` – auto-advance time, in milliseconds.
    """

    spd: str | None = OptionalAttribute("spd", XsdString)  # pyright: ignore[reportAssignmentType]
    advClick: bool | None = OptionalAttribute(  # pyright: ignore[reportAssignmentType]
        "advClick", XsdBoolean
    )
    advTm: int | None = OptionalAttribute(  # pyright: ignore[reportAssignmentType]
        "advTm", XsdUnsignedInt
    )

    @property
    def kind_element(self):
        """The single transition-kind child element, or |None| if not set.

        The transition-kind element is the first child whose tag is not a
        sound-action or extension-list element; that gives us the right
        answer for both standard ``p:`` transitions and PowerPoint-2010+
        ``p14:`` transitions without enumerating every known kind.
        """
        for child in self:
            local = child.tag.rsplit("}", 1)[-1]
            if local in ("sndAc", "extLst"):
                continue
            return child
        return None


class CT_SlideTiming(BaseOxmlElement):
    """`p:timing` element, specifying animations and timed behaviors."""

    _tag_seq = ("p:tnLst", "p:bldLst", "p:extLst")
    tnLst = ZeroOrOne("p:tnLst", successors=_tag_seq[1:])
    del _tag_seq


class CT_TimeNodeList(BaseOxmlElement):
    """`p:tnLst` or `p:childTnList` element."""

    def add_video(self, shape_id):
        """Add a new `p:video` child element for movie having *shape_id*."""
        video_xml = (
            "<p:video %s>\n"
            '  <p:cMediaNode vol="80000">\n'
            '    <p:cTn id="%d" fill="hold" display="0">\n'
            "      <p:stCondLst>\n"
            '        <p:cond delay="indefinite"/>\n'
            "      </p:stCondLst>\n"
            "    </p:cTn>\n"
            "    <p:tgtEl>\n"
            '      <p:spTgt spid="%d"/>\n'
            "    </p:tgtEl>\n"
            "  </p:cMediaNode>\n"
            "</p:video>\n" % (nsdecls("p"), self._next_cTn_id, shape_id)
        )
        video = parse_xml(video_xml)
        self.append(video)

    @property
    def _next_cTn_id(self):
        """Return the next available unique ID (int) for p:cTn element."""
        cTn_id_strs = self.xpath("/p:sld/p:timing//p:cTn/@id")
        ids = [int(id_str) for id_str in cTn_id_strs]
        return max(ids) + 1


class CT_TLMediaNodeVideo(BaseOxmlElement):
    """`p:video` element, specifying video media details."""

    _tag_seq = ("p:cMediaNode",)
    cMediaNode = OneAndOnlyOne("p:cMediaNode")
    del _tag_seq


# ---------------------------------------------------------------------------
# Markup-Compatibility (mc:AlternateContent) wrapping for p14 transitions
# ---------------------------------------------------------------------------
#
# PowerPoint-2010+ transitions (morph, vortex, switch, …) live in the ``p14``
# namespace.  ``CT_SlideTransition`` (the schema for ``<p:transition>``) only
# admits the standard ``p:`` kind elements in its choice, so a bare
# ``<p14:morph/>`` child is schema-invalid and Microsoft PowerPoint reports the
# deck as needing repair.  PowerPoint instead wraps the whole ``<p:transition>``
# in ``<mc:AlternateContent>``: an ``<mc:Choice Requires="p14">`` carrying the
# p14 transition, plus an ``<mc:Fallback>`` carrying a plain (kind-less)
# ``<p:transition>`` for pre-2010 viewers.
#
# We keep the in-memory model as a plain ``<p:transition>`` (so the
# ``slide.transition`` accessors stay simple) and translate to/from the
# AlternateContent form only at the serialization boundary — see
# ``power_pptx.parts.slide.BaseSlidePart``.

_MC_URI = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_P14_URI = "http://schemas.microsoft.com/office/powerpoint/2010/main"
_P159_URI = "http://schemas.microsoft.com/office/powerpoint/2015/09/main"
_P_URI = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _mc(tag: str) -> str:
    return "{%s}%s" % (_MC_URI, tag)


def _p_tag(tag: str) -> str:
    return "{%s}%s" % (_P_URI, tag)


def _transition_kind_child(transition):
    """Return the kind child of a ``<p:transition>`` (skipping sndAc/extLst)."""
    for child in transition:
        local = child.tag.rsplit("}", 1)[-1]
        if local in ("sndAc", "extLst"):
            continue
        return child
    return None


def _extension_kind_uri(transition) -> "str | None":
    """The Microsoft-extension namespace URI of the transition kind, or |None|.

    Returns ``_P159_URI`` for a 2016+ kind (morph), ``_P14_URI`` for a 2010+
    kind (flythrough, vortex, …), and |None| for a classic ``p:`` kind or a
    kind-less transition.
    """
    kind = _transition_kind_child(transition)
    if kind is None:
        return None
    for uri in (_P159_URI, _P14_URI):
        if kind.tag.startswith("{%s}" % uri):
            return uri
    return None


def _has_p14_attr(transition) -> bool:
    """True when *transition* carries any PowerPoint-2010 (p14) attribute.

    The most common one is ``p14:dur`` (millisecond duration). Like the
    extension *kind* elements, a p14 attribute is only schema-valid inside an
    ``<mc:Choice>`` — a bare ``<p:transition p14:dur="…">`` is rejected by
    Microsoft PowerPoint (it reports the deck as needing repair).
    """
    p14 = "{%s}" % _P14_URI
    return any(name.startswith(p14) for name in transition.attrib)


def _needs_mc_wrap(transition) -> bool:
    """True when *transition* must be wrapped in ``<mc:AlternateContent>``.

    That is whenever it holds *any* extension content — a p14/p159 kind child
    (flythrough, morph, …) or a p14 attribute (e.g. ``p14:dur``).
    """
    return _extension_kind_uri(transition) is not None or _has_p14_attr(transition)


def slide_has_p14_transition(root) -> bool:
    """True when *root* (sld/sldLayout/sldMaster) holds a transition needing the
    ``mc:AlternateContent`` wrapper (a p14 kind child or a p14 attribute)."""
    return any(_needs_mc_wrap(t) for t in root.findall(_p_tag("transition")))


def wrap_p14_transitions(root) -> None:
    """In-place: wrap each bare p14 ``<p:transition>`` in ``<mc:AlternateContent>``.

    Called on a *copy* of the element at serialization time so the live tree
    keeps its plain ``<p:transition>`` for the high-level accessors.
    """
    import copy

    from lxml import etree

    p14 = "{%s}" % _P14_URI
    for transition in list(root.findall(_p_tag("transition"))):
        if not _needs_mc_wrap(transition):
            continue
        idx = list(root).index(transition)

        # Heal decks written by earlier power-pptx releases (and any other
        # producer) that emitted morph in the p14 namespace: retag to p159 so
        # a plain load → save round-trip repairs the file.
        legacy_morph = _transition_kind_child(transition)
        if legacy_morph is not None and legacy_morph.tag == "{%s}morph" % _P14_URI:
            healed = etree.Element("{%s}morph" % _P159_URI, nsmap={"p159": _P159_URI})
            for attr_name, attr_value in legacy_morph.attrib.items():
                healed.set(attr_name, attr_value)
            transition.replace(legacy_morph, healed)

        ext_uri = _extension_kind_uri(transition)

        # Morph is a 2015/09 (p159) element per MS-PPTX, so its Choice must
        # require "p159" — every modern PowerPoint understands p14, and an
        # undefined `p14:morph` inside the selected branch is exactly the
        # repair-dialog class of failure.  The 2010 kinds (and a p14
        # attribute on a classic kind) require "p14".
        if ext_uri == _P159_URI:
            requires, choice_nsmap = "p159", {"p159": _P159_URI, "p14": _P14_URI}
        else:
            requires, choice_nsmap = "p14", {"p14": _P14_URI}

        ac = etree.Element(_mc("AlternateContent"), nsmap={"mc": _MC_URI})
        choice = etree.SubElement(ac, _mc("Choice"), nsmap=choice_nsmap)
        choice.set("Requires", requires)

        # Match PowerPoint: <p159:morph option="byObject"/> when option is unset.
        kind = _transition_kind_child(transition)
        if kind is not None and kind.tag == "{%s}morph" % _P159_URI and kind.get("option") is None:
            kind.set("option", "byObject")

        # Fallback transition keeps the non-p14 timing attributes.  When the
        # kind is a *classic* (p:) element — e.g. a fade carrying only a p14:dur
        # — preserve it in the fallback so pre-2010 viewers still get the
        # transition.  Extension kinds (morph, vortex, …) have no classic
        # equivalent; PowerPoint's own fallback for them is a plain fade, and
        # an extension element must never leak into the ISO-pure fallback.
        fallback = etree.SubElement(ac, _mc("Fallback"))
        fb = etree.SubElement(fallback, _p_tag("transition"))
        for name, value in transition.attrib.items():
            if not name.startswith(p14):
                fb.set(name, value)
        if kind is not None:
            if ext_uri is None:
                fb.append(copy.deepcopy(kind))
            else:
                etree.SubElement(fb, _p_tag("fade"))

        # Move the original extension transition under <mc:Choice> and drop
        # it into the tree where it used to live.
        choice.append(transition)
        root.insert(idx, ac)


def unwrap_p14_transitions(root) -> None:
    """In-place inverse of :func:`wrap_p14_transitions` (called on load).

    Replaces any ``<mc:AlternateContent>`` direct child of *root* that wraps a
    transition with the plain ``<p:transition>`` from its ``<mc:Choice>`` so the
    high-level accessors see a normal transition element.
    """
    for ac in list(root.findall(_mc("AlternateContent"))):
        choice = ac.find(_mc("Choice"))
        if choice is None:
            continue
        transition = choice.find(_p_tag("transition"))
        if transition is None:
            continue
        idx = list(root).index(ac)
        root.remove(ac)
        root.insert(idx, transition)
