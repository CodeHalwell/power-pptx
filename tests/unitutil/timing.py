"""Builders for PowerPoint-authored animation timing trees, for use in tests.

``power_pptx`` writes a *flat* timing tree: one click-group ``p:par`` per effect, directly under
the root ``p:cTn``.  PowerPoint nests everything under a main sequence instead, and puts every
"With Previous" / "After Previous" effect inside the click group of the effect before it::

    tmRoot
      seq / mainSeq
        par                      <- click group
          par                    <- with/after group
            par  clickEffect     <- effect (shape A)
            par  withEffect      <- effect (shape B)
      video / audio / seq interactiveSeq ...

The helpers here emit that second shape (trimmed to what the library reads) so tests can exercise
decks authored in PowerPoint.
"""

from __future__ import annotations

import itertools

from power_pptx.oxml import parse_xml
from power_pptx.oxml.ns import qn

_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _effect_xml(ids, spid, node_type):
    """One Fade entrance effect ``p:par`` (a ``p:set`` plus a ``p:animEffect``) for *spid*."""
    effect_id, set_id, anim_id = next(ids), next(ids), next(ids)
    return (
        f'<p:par><p:cTn id="{effect_id}" presetID="10" presetClass="entr" presetSubtype="0"'
        f' fill="hold" grpId="0" nodeType="{node_type}">'
        '<p:stCondLst><p:cond delay="0"/></p:stCondLst>'
        "<p:childTnLst>"
        f'<p:set><p:cBhvr><p:cTn id="{set_id}" dur="1" fill="hold">'
        '<p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
        f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'
        "<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>"
        '</p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>'
        '<p:animEffect transition="in" filter="fade"><p:cBhvr>'
        f'<p:cTn id="{anim_id}" dur="500"/>'
        f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'
        "</p:cBhvr></p:animEffect>"
        "</p:childTnLst></p:cTn></p:par>"
    )


def _group_par_xml(group_id, cond_delay, inner):
    """A structural ``p:par`` (click group or with/after group) wrapping *inner*."""
    return (
        f'<p:par><p:cTn id="{group_id}" fill="hold">'
        f'<p:stCondLst><p:cond delay="{cond_delay}"/></p:stCondLst>'
        f"<p:childTnLst>{inner}</p:childTnLst></p:cTn></p:par>"
    )


def _sequence_body_xml(ids, effects):
    """Click groups for *effects*, grouped the way PowerPoint groups them.

    *effects* is a list of ``(spid, node_type)`` in play order.  A ``clickEffect`` opens a new
    click group; an ``afterEffect`` opens a new with/after group inside the current click group;
    a ``withEffect`` joins the current with/after group.
    """
    assert effects, "a sequence needs at least one effect"
    assert effects[0][1] == "clickEffect", "a sequence opens with a clickEffect"
    clicks = []  # [[ [effect_xml, ...] (a with/after group), ... ] (a click group), ...]
    for spid, node_type in effects:
        if node_type == "clickEffect":
            clicks.append([[]])
        elif node_type == "afterEffect":
            clicks[-1].append([])
        elif node_type != "withEffect":
            raise ValueError(node_type)
        clicks[-1][-1].append((spid, node_type))
    out = []
    for click in clicks:
        # cTn ids are handed out in document order, so each wrapper takes its id before the
        # nodes inside it do
        click_id = next(ids)
        groups = []
        for n, group in enumerate(click):
            group_id = next(ids)
            body = "".join(_effect_xml(ids, spid, node_type) for spid, node_type in group)
            groups.append(_group_par_xml(group_id, "0" if n == 0 else "500", body))
        out.append(_group_par_xml(click_id, "indefinite", "".join(groups)))
    return "".join(out)


def _interactive_seq_xml(ids, trigger_spid, effects):
    """A ``p:seq`` interactive sequence: clicking *trigger_spid* plays *effects*."""
    seq_id = next(ids)
    cond = (
        '<p:cond evt="onClick" delay="0"><p:tgtEl>'
        f'<p:spTgt spid="{trigger_spid}"/></p:tgtEl></p:cond>'
    )
    return (
        '<p:seq concurrent="1" nextAc="seek">'
        f'<p:cTn id="{seq_id}" restart="whenNotActive" fill="hold" evtFilter="cancelBubble"'
        ' nodeType="interactiveSeq">'
        f"<p:stCondLst>{cond}</p:stCondLst>"
        '<p:endSync evt="end" delay="0"><p:rtn val="all"/></p:endSync>'
        f"<p:childTnLst>{_sequence_body_xml(ids, effects)}</p:childTnLst>"
        "</p:cTn>"
        f"<p:nextCondLst>{cond}</p:nextCondLst>"
        "</p:seq>"
    )


def _media_xml(ids, kind, spid):
    """A ``p:video`` or ``p:audio`` media node controlling the shape *spid*."""
    ctn_id = next(ids)
    return (
        f"<p:{kind}>"
        '<p:cMediaNode vol="80000">'
        f'<p:cTn id="{ctn_id}" fill="hold" display="0">'
        '<p:stCondLst><p:cond delay="indefinite"/></p:stCondLst>'
        "</p:cTn>"
        f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'
        f"</p:cMediaNode></p:{kind}>"
    )


def powerpoint_timing_xml(effects, *, interactive=(), media=(), bld=()):
    """Return a ``p:timing`` XML string shaped the way PowerPoint writes it.

    *effects* are the main-sequence effects as ``(spid, node_type)`` pairs, with node_type one of
    ``"clickEffect"``, ``"withEffect"`` and ``"afterEffect"``; an empty list gives a main
    sequence without effects (PowerPoint writes it as a self-closing ``p:cTn``).
    *interactive* is a list of ``(trigger_spid, effects)`` interactive sequences, *media* a list
    of ``("video" | "audio", spid)`` media nodes and *bld* the shape ids to list in ``p:bldLst``.
    """
    ids = itertools.count(1)
    root_id, main_id = next(ids), next(ids)
    if effects:
        main_cTn = (
            f'<p:cTn id="{main_id}" dur="indefinite" nodeType="mainSeq">'
            f"<p:childTnLst>{_sequence_body_xml(ids, effects)}</p:childTnLst></p:cTn>"
        )
    else:
        main_cTn = f'<p:cTn id="{main_id}" dur="indefinite" nodeType="mainSeq"/>'
    main_seq = (
        f'<p:seq concurrent="1" nextAc="seek">{main_cTn}'
        '<p:prevCondLst><p:cond evt="onPrev" delay="0">'
        "<p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>"
        '<p:nextCondLst><p:cond evt="onNext" delay="0">'
        "<p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst></p:seq>"
    )
    extras = "".join(_interactive_seq_xml(ids, trigger, fx) for trigger, fx in interactive)
    extras += "".join(_media_xml(ids, kind, spid) for kind, spid in media)
    bld_lst = ""
    if bld:
        entries = "".join(f'<p:bldP spid="{spid}" grpId="0"/>' for spid in bld)
        bld_lst = f"<p:bldLst>{entries}</p:bldLst>"
    return (
        f'<p:timing xmlns:p="{_P_NS}"><p:tnLst><p:par>'
        f'<p:cTn id="{root_id}" dur="indefinite" restart="never" nodeType="tmRoot">'
        f"<p:childTnLst>{main_seq}{extras}</p:childTnLst></p:cTn></p:par></p:tnLst>"
        f"{bld_lst}</p:timing>"
    )


def install_timing(slide, timing_xml):
    """Make *timing_xml* the ``p:timing`` of *slide*, replacing any timing already there."""
    sld = slide._element
    existing = sld.find(qn("p:timing"))
    if existing is not None:
        sld.remove(existing)
    sld._insert_timing(parse_xml(timing_xml))


def target_ids(slide):
    """Every ``p:spTgt/@spid`` left in *slide*'s timing tree, as ints, in document order."""
    return [int(spid) for spid in slide._element.xpath("p:timing//p:spTgt/@spid")]


def build_ids(slide):
    """The ``spid`` of every entry in *slide*'s ``p:bldLst``, as ints, in document order."""
    return [int(spid) for spid in slide._element.xpath("p:timing/p:bldLst/*/@spid")]


def cTn_ids(slide):
    """Every ``p:cTn/@id`` in *slide*'s timing tree, in document order."""
    return [int(i) for i in slide._element.xpath("p:timing//p:cTn/@id")]
