"""Round-trip suite for slide timing trees in the structure PowerPoint writes.

PowerPoint nests the effects of a slide in a main sequence and lists the
animated shapes in a build list. Such a tree must come through a plain
load → save untouched, and must still round-trip after the library has
purged, removed or added effects in it.
"""

from __future__ import annotations

import io

from power_pptx import Presentation
from power_pptx.animation import Entrance, Exit, Trigger
from power_pptx.oxml import parse_xml
from power_pptx.util import Inches

from .round_trip import _canonicalize_xml, _parts, _save_to_bytes, assert_round_trip

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_SLIDE = "ppt/slides/slide1.xml"


def _click_step(spid: int, ctn_id: int) -> str:
    """A click step of the main sequence fading shape `spid` in, as PowerPoint writes it."""
    return (
        f'<p:par><p:cTn id="{ctn_id}" fill="hold">'
        '<p:stCondLst><p:cond delay="indefinite"/></p:stCondLst><p:childTnLst>'
        f'<p:par><p:cTn id="{ctn_id + 1}" fill="hold">'
        '<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
        f'<p:par><p:cTn id="{ctn_id + 2}" presetID="10" presetClass="entr" presetSubtype="0"'
        ' fill="hold" grpId="0" nodeType="clickEffect">'
        '<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
        f'<p:set><p:cBhvr><p:cTn id="{ctn_id + 3}" dur="1" fill="hold">'
        '<p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
        f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'
        "<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr>"
        '<p:to><p:strVal val="visible"/></p:to></p:set>'
        f'<p:animEffect transition="in" filter="fade"><p:cBhvr><p:cTn id="{ctn_id + 4}" dur="500"/>'
        f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect>'
        "</p:childTnLst></p:cTn></p:par>"
        "</p:childTnLst></p:cTn></p:par>"
        "</p:childTnLst></p:cTn></p:par>"
    )


def _powerpoint_timing(*spids: int):
    steps = "".join(_click_step(spid, 3 + 5 * i) for i, spid in enumerate(spids))
    builds = "".join('<p:bldP spid="%d" grpId="0" animBg="1"/>' % spid for spid in spids)
    return parse_xml(
        '<p:timing xmlns:p="%s"><p:tnLst><p:par>'
        '<p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>'
        '<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq">'
        "<p:childTnLst>%s</p:childTnLst></p:cTn>"
        '<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond>'
        "</p:prevCondLst>"
        '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond>'
        "</p:nextCondLst></p:seq>"
        "</p:childTnLst></p:cTn></p:par></p:tnLst><p:bldLst>%s</p:bldLst></p:timing>"
        % (P_NS, steps, builds)
    )


def _animated_deck(count: int, animated: int) -> bytes:
    """A saved one-slide deck of `count` shapes, the first `animated` of them animated."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    shapes = [
        slide.shapes.add_shape(1, Inches(1 + i), Inches(1), Inches(1), Inches(1))
        for i in range(count)
    ]
    slide._element._insert_timing(_powerpoint_timing(*[s.shape_id for s in shapes[:animated]]))
    return _save_to_bytes(prs)


def _slide_xml(pptx: bytes) -> bytes:
    return _canonicalize_xml(_parts(pptx)[_SLIDE])


class DescribePowerPointAuthoredTimingRoundTrip:
    def it_saves_an_untouched_timing_tree_back_as_it_was_read(self):
        source = _animated_deck(3, animated=2)
        prs = Presentation(io.BytesIO(source))

        # -- reading the effects must not disturb them either --
        assert len(prs.slides[0].animations) == 2
        assert [e.preset for e in prs.slides[0].animations] == ["fade", "fade"]

        assert _slide_xml(_save_to_bytes(prs)) == _slide_xml(source)

    def it_round_trips_after_an_animated_shape_is_deleted(self):
        prs = Presentation(io.BytesIO(_animated_deck(3, animated=2)))
        slide = prs.slides[0]
        list(slide.shapes)[0].delete()

        assert len(slide.animations) == 1
        assert_round_trip(prs)

    def it_round_trips_effects_added_to_the_main_sequence(self):
        prs = Presentation(io.BytesIO(_animated_deck(4, animated=1)))
        slide = prs.slides[0]
        _, b, c, d = list(slide.shapes)
        Entrance.fade(slide, b, trigger=Trigger.WITH_PREVIOUS)
        Entrance.fly_in(slide, c, trigger=Trigger.AFTER_PREVIOUS)
        Exit.fade(slide, d)

        reopened = Presentation(io.BytesIO(_save_to_bytes(prs)))

        assert [(e.kind, e.trigger) for e in reopened.slides[0].animations] == [
            ("entrance", Trigger.ON_CLICK),
            ("entrance", Trigger.WITH_PREVIOUS),
            ("entrance", Trigger.AFTER_PREVIOUS),
            ("exit", Trigger.ON_CLICK),
        ]
        assert_round_trip(reopened)
