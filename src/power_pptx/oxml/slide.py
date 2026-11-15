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
        answer for standard ``p:`` transitions and for the extension kinds
        later PowerPoint versions add in their own namespaces (``p14:``,
        ``p15:``, ``p159:``) without enumerating every known kind.
        """
        return _transition_kind_child(self)


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
# Markup-Compatibility (mc:AlternateContent) wrapping for extension transitions
# ---------------------------------------------------------------------------
#
# Transitions added after PowerPoint 2007 live in Microsoft extension
# namespaces: ``p14`` (2010: vortex, switch, prism, …), ``p15`` (2013:
# ``<p15:prstTrans prst="airplane"/>`` and friends) and ``p159`` (2016: morph).
# ``CT_SlideTransition`` (the schema for ``<p:transition>``) only admits the
# standard ``p:`` kind elements in its choice, so a bare ``<p14:vortex/>``
# child is schema-invalid and Microsoft PowerPoint reports the deck as needing
# repair.  PowerPoint instead wraps the whole ``<p:transition>`` in
# ``<mc:AlternateContent>``: an ``<mc:Choice Requires="…">`` carrying the
# extension transition, plus an ``<mc:Fallback>`` carrying an ISO-pure
# ``<p:transition>`` for viewers that do not understand the extension.
#
# We keep the in-memory model as a plain ``<p:transition>`` (so the
# ``slide.transition`` accessors stay simple) and translate to/from the
# AlternateContent form only at the serialization boundary — see
# ``power_pptx.parts.slide.BaseSlidePart``.
#
# A wrapper read from a file is not ours to rewrite: its fallback is whatever
# the authoring application chose, and it may use extensions this library
# knows nothing about.  So on load the original ``<mc:AlternateContent>`` stays
# in the tree, right after a working copy of its transition; on save the
# original is written back untouched unless the working copy was changed in
# the meantime, in which case a fresh wrapper is generated from it.

_MC_URI = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_P14_URI = "http://schemas.microsoft.com/office/powerpoint/2010/main"
_P15_URI = "http://schemas.microsoft.com/office/powerpoint/2012/main"
_P159_URI = "http://schemas.microsoft.com/office/powerpoint/2015/09/main"
_P_URI = "http://schemas.openxmlformats.org/presentationml/2006/main"

# -- the prefix each extension namespace is conventionally bound to; used for
# -- the `Requires` token when the kind element does not carry a prefix itself
_EXTENSION_PREFIXES = {_P14_URI: "p14", _P15_URI: "p15", _P159_URI: "p159"}


def _mc(tag: str) -> str:
    return "{%s}%s" % (_MC_URI, tag)


def _p_tag(tag: str) -> str:
    return "{%s}%s" % (_P_URI, tag)


def _namespace_uri(name: str) -> "str | None":
    """Namespace URI of the Clark-notation *name*, or |None| if it has none."""
    return name[1:].split("}", 1)[0] if name.startswith("{") else None


def _transition_kind_child(transition):
    """Return the kind child of a ``<p:transition>`` (skipping sndAc/extLst)."""
    for child in transition:
        tag = child.tag
        if not isinstance(tag, str):  # -- comment or processing instruction --
            continue
        if tag in (_p_tag("sndAc"), _p_tag("extLst")):
            continue
        return child
    return None


def _extension_kind_uri(transition) -> "str | None":
    """The extension-namespace URI of the transition kind, or |None|.

    Any kind outside the ``p:`` namespace is an extension, whichever namespace
    it comes from: ``p14`` (flythrough, vortex, …), ``p15`` (prstTrans),
    ``p159`` (morph) or one that did not exist when this was written.  |None|
    for a classic ``p:`` kind or a kind-less transition.
    """
    kind = _transition_kind_child(transition)
    if kind is None:
        return None
    uri = _namespace_uri(kind.tag)
    return None if uri in (None, _P_URI) else uri


def _has_extension_attr(transition) -> bool:
    """True when *transition* carries an attribute from an extension namespace.

    The usual one is ``p14:dur`` (millisecond duration). Like the extension
    *kind* elements, such an attribute is only schema-valid inside an
    ``<mc:Choice>`` — a bare ``<p:transition p14:dur="…">`` is rejected by
    Microsoft PowerPoint (it reports the deck as needing repair).
    """
    return any(_namespace_uri(name) is not None for name in transition.attrib)


def _needs_mc_wrap(transition) -> bool:
    """True when *transition* must be wrapped in ``<mc:AlternateContent>``.

    That is whenever it holds *any* extension content — a kind child from
    outside the ``p:`` namespace (flythrough, prstTrans, morph, …) or an
    extension attribute (e.g. ``p14:dur``).
    """
    return _extension_kind_uri(transition) is not None or _has_extension_attr(transition)


def _wrapped_transition(ac):
    """The ``<p:transition>`` in the first ``<mc:Choice>`` of *ac* holding one, or |None|."""
    for choice in ac.findall(_mc("Choice")):
        transition = choice.find(_p_tag("transition"))
        if transition is not None:
            return transition
    return None


def _transition_wrappers(root) -> list:
    """The ``<mc:AlternateContent>`` children of *root* that wrap a transition."""
    return [
        ac for ac in root.findall(_mc("AlternateContent")) if _wrapped_transition(ac) is not None
    ]


def _same_markup(a, b) -> bool:
    """True when elements *a* and *b* serialize to the same canonical XML."""
    from lxml import etree

    def canonical(element) -> bytes:
        return etree.tostring(element, method="c14n", exclusive=True, with_tail=False)

    return canonical(a) == canonical(b)


def _wrapper_is_sound(ac) -> bool:
    """True when the transition wrapper *ac* can be written back as it was read.

    A wrapper is kept verbatim unless it is one of the known-broken forms, all
    of which are repaired by regenerating it from the transition it wraps:

    * the kind is a ``p14:morph`` — morph belongs to the ``p159`` namespace
      (earlier power-pptx releases wrote it in ``p14``);
    * the ``Requires`` of the choice does not name the namespace of its
      extension kind (earlier releases wrote ``Requires="p14"`` around a
      ``p15`` kind);
    * the fallback transition holds extension content, which defeats its
      purpose (earlier releases copied a ``p15`` kind into it).
    """
    transition = _wrapped_transition(ac)
    choice = transition.getparent()
    kind = _transition_kind_child(transition)
    if kind is not None:
        if kind.tag == "{%s}morph" % _P14_URI:
            return False
        kind_uri = _extension_kind_uri(transition)
        if kind_uri is not None:
            prefixes = (choice.get("Requires") or "").split()
            if kind_uri not in {choice.nsmap.get(prefix) for prefix in prefixes}:
                return False
    for fallback in ac.findall(_mc("Fallback")):
        for fb_transition in fallback.findall(_p_tag("transition")):
            if _has_extension_attr(fb_transition):
                return False
            if any(
                isinstance(child.tag, str) and _namespace_uri(child.tag) != _P_URI
                for child in fb_transition
            ):
                return False
    return True


def slide_has_p14_transition(root) -> bool:
    """True when the transition of *root* (sld/sldLayout/sldMaster) needs work on save.

    That is when it holds a bare transition needing the ``mc:AlternateContent``
    wrapper (an extension kind child or an extension attribute), or a wrapper
    kept from load that has to be reconciled with its working copy.
    """
    if any(_needs_mc_wrap(t) for t in root.findall(_p_tag("transition"))):
        return True
    return bool(_transition_wrappers(root))


def remove_transition_wrappers(root) -> None:
    """In-place: drop each transition wrapper kept from load.

    Called when the transition is removed, so the original wrapper does not
    linger in the tree after the transition it described is gone.
    """
    for ac in _transition_wrappers(root):
        root.remove(ac)


def _reusable_fallback(original, kind):
    """The fallback ``<p:transition>`` of *original* if it still fits *kind*, else |None|.

    It fits when *original* wraps a transition of the very same kind, so the
    fallback the authoring application wrote for it still applies.
    """
    if original is None or not _wrapper_is_sound(original):
        return None
    original_kind = _transition_kind_child(_wrapped_transition(original))
    if original_kind is None or not _same_markup(original_kind, kind):
        return None
    fallback = original.find(_mc("Fallback"))
    return None if fallback is None else fallback.find(_p_tag("transition"))


def _new_wrapper(transition, original):
    """Return a new `(mc:AlternateContent, mc:Choice)` pair to wrap *transition*.

    *original* is the wrapper *transition* was loaded from, or |None|.  The
    caller moves *transition* into the returned ``<mc:Choice>``.
    """
    import copy

    from lxml import etree

    # Heal decks written by earlier power-pptx releases (and any other
    # producer) that emitted morph in the p14 namespace: retag to p159 so
    # a plain load → save round-trip repairs the file.
    legacy_morph = _transition_kind_child(transition)
    if legacy_morph is not None and legacy_morph.tag == "{%s}morph" % _P14_URI:
        healed = etree.Element("{%s}morph" % _P159_URI, nsmap={"p159": _P159_URI})
        for attr_name, attr_value in legacy_morph.attrib.items():
            healed.set(attr_name, attr_value)
        transition.replace(legacy_morph, healed)

    kind = _transition_kind_child(transition)
    ext_uri = _extension_kind_uri(transition)

    # `Requires` names the namespace a consumer must understand to take the
    # choice: that of the extension kind, whichever it is — a `p159:morph`
    # needs "p159", a `p15:prstTrans` needs "p15".  Requiring only "p14"
    # there would hand the element to a PowerPoint 2010 that cannot read it,
    # which is exactly the repair-dialog class of failure.  A classic kind
    # that merely carries a p14 attribute (`p14:dur`) requires "p14".
    if kind is None or ext_uri is None:
        requires, choice_nsmap = "p14", {"p14": _P14_URI}
    else:
        requires = kind.prefix or _EXTENSION_PREFIXES.get(ext_uri, "ext")
        choice_nsmap = {requires: ext_uri}
        choice_nsmap.setdefault("p14", _P14_URI)

    ac = etree.Element(_mc("AlternateContent"), nsmap={"mc": _MC_URI})
    choice = etree.SubElement(ac, _mc("Choice"), nsmap=choice_nsmap)
    choice.set("Requires", requires)

    # Match PowerPoint: <p159:morph option="byObject"/> when option is unset.
    if kind is not None and kind.tag == "{%s}morph" % _P159_URI and kind.get("option") is None:
        kind.set("option", "byObject")

    # The fallback transition keeps the plain timing attributes and must stay
    # ISO-pure: an extension attribute or element never goes into it.
    fallback = etree.SubElement(ac, _mc("Fallback"))
    fb = etree.SubElement(fallback, _p_tag("transition"))
    for name, value in transition.attrib.items():
        if _namespace_uri(name) is None:
            fb.set(name, value)
    if kind is not None:
        original_fb = _reusable_fallback(original, kind)
        if original_fb is not None:
            # Same kind as when the deck was read (only its timing changed):
            # keep the downgrade the authoring application chose for it.
            for child in original_fb:
                fb.append(copy.deepcopy(child))
        elif ext_uri is None:
            # A *classic* (p:) kind — e.g. a fade carrying only a p14:dur — is
            # preserved so older viewers still get the transition.
            fb.append(copy.deepcopy(kind))
        else:
            # Extension kinds have no classic equivalent; PowerPoint's own
            # fallback for them is a plain fade.
            etree.SubElement(fb, _p_tag("fade"))
    return ac, choice


def wrap_p14_transitions(root) -> None:
    """In-place: put each extension ``<p:transition>`` in ``<mc:AlternateContent>``.

    Called on a *copy* of the element at serialization time so the live tree
    keeps its plain ``<p:transition>`` for the high-level accessors.

    A transition that still matches the wrapper it was loaded from gets that
    wrapper back unchanged; any other transition holding extension content
    gets a newly generated one.
    """
    originals = _transition_wrappers(root)
    for transition in list(root.findall(_p_tag("transition"))):
        original = originals[0] if originals else None
        if original is not None and _same_markup(transition, _wrapped_transition(original)):
            originals.remove(original)
            root.remove(original)
            root.replace(transition, original)
            continue
        if not _needs_mc_wrap(transition):
            continue
        ac, choice = _new_wrapper(transition, original)
        # Move the extension transition under <mc:Choice> and drop the
        # wrapper into the tree where the transition used to live.
        idx = root.index(transition)
        choice.append(transition)
        root.insert(idx, ac)
    # -- whatever is left wraps a transition that was since changed or removed --
    for stale in originals:
        root.remove(stale)


def unwrap_p14_transitions(root) -> None:
    """In-place inverse of :func:`wrap_p14_transitions` (called on load).

    Gives *root* a plain ``<p:transition>`` child for each
    ``<mc:AlternateContent>`` child that wraps a transition, so the high-level
    accessors see a normal transition element.  The wrapper itself stays in
    the tree, right after that working copy, to be written back as it was
    unless the copy is changed.  A wrapper in one of the known-broken forms
    (see :func:`_wrapper_is_sound`) is discarded so that it is regenerated.
    """
    import copy

    for ac in _transition_wrappers(root):
        transition = _wrapped_transition(ac)
        idx = root.index(ac)
        if _wrapper_is_sound(ac):
            root.insert(idx, copy.deepcopy(transition))
        else:
            root.remove(ac)
            root.insert(idx, transition)
