"""Schema validity of slide timing trees after shapes are removed or effects added.

A timing tree that names a shape no longer on the slide, or that is left with
an empty `p:childTnLst` or `p:bldLst` once the nodes for that shape are gone,
is a PowerPoint repair trigger. These decks start from the timing structure
PowerPoint itself writes: effects nested in a main sequence, with a build list.
"""

from __future__ import annotations

import io
import os
from zipfile import ZipFile

import pytest
from lxml import etree

from power_pptx import Presentation
from power_pptx.animation import Emphasis, Entrance, Exit, MotionPath, Trigger
from power_pptx.oxml import parse_xml
from power_pptx.util import Inches

from .oxml_schema_validator import assert_schema_valid, schema_validation_available

pytestmark = pytest.mark.skipif(
    not schema_validation_available(),
    reason="lxml or the bundled ISO-29500 XSD schemas are unavailable",
)

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
MOVIE = os.path.join(os.path.dirname(__file__), "..", "test_files", "dummy.mp4")


def _saved(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


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
    """A `p:timing` with a main sequence fading each of `spids` in on its own click.

    With no `spids` the main sequence is there but empty: PowerPoint leaves
    none like that behind, but nothing stops a file from holding one.
    """
    steps = "".join(_click_step(spid, 3 + 5 * i) for i, spid in enumerate(spids))
    builds = "".join('<p:bldP spid="%d" grpId="0" animBg="1"/>' % spid for spid in spids)
    return parse_xml(
        '<p:timing xmlns:p="%s"><p:tnLst><p:par>'
        '<p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>'
        '<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq">'
        "%s</p:cTn>"
        '<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond>'
        "</p:prevCondLst>"
        '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond>'
        "</p:nextCondLst></p:seq>"
        "</p:childTnLst></p:cTn></p:par></p:tnLst>%s</p:timing>"
        % (
            P_NS,
            "<p:childTnLst>%s</p:childTnLst>" % steps if steps else "",
            "<p:bldLst>%s</p:bldLst>" % builds if builds else "",
        )
    )


def _animated_deck(count: int, animated: int):
    """A one-slide deck of `count` shapes, the first `animated` of which PowerPoint animated."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    shapes = [
        slide.shapes.add_shape(1, Inches(1 + i), Inches(1), Inches(1), Inches(1))
        for i in range(count)
    ]
    slide._element._insert_timing(_powerpoint_timing(*[s.shape_id for s in shapes[:animated]]))
    return prs, slide, shapes


def _assert_no_dangling_target(pptx: bytes) -> None:
    """Every shape id the timing of slide 1 names belongs to a shape on that slide."""
    with ZipFile(io.BytesIO(pptx)) as zf:
        sld = etree.fromstring(zf.read("ppt/slides/slide1.xml"))
    ns = {"p": P_NS}
    live = set(sld.xpath("p:cSld/p:spTree//p:cNvPr/@id", namespaces=ns))
    named = set(sld.xpath("//p:timing//@spid", namespaces=ns))
    assert named <= live, "timing names missing shape(s) %s" % sorted(named - live)


class DescribeTimingTreeSchemaValidity:
    def it_validates_the_powerpoint_style_timing_it_starts_from(self):
        # -- so that a failure below is down to the library, not to the input --
        prs, _, _ = _animated_deck(2, animated=2)
        assert_schema_valid(_saved(prs))

    @pytest.mark.parametrize("delete", [(0,), (1,), (0, 1)], ids=["first", "last", "all"])
    def it_stays_valid_after_animated_shapes_are_deleted(self, delete):
        prs, _, shapes = _animated_deck(2, animated=2)

        for idx in delete:
            shapes[idx].delete()
        pptx = _saved(prs)

        assert_schema_valid(pptx)
        _assert_no_dangling_target(pptx)

    def it_stays_valid_after_a_movie_is_deleted(self):
        prs, slide, _ = _animated_deck(1, animated=1)
        movie = slide.shapes.add_movie(MOVIE, Inches(1), Inches(3), Inches(3), Inches(2))

        movie.delete()
        pptx = _saved(prs)

        assert_schema_valid(pptx)
        _assert_no_dangling_target(pptx)

    def it_stays_valid_after_an_animated_group_is_ungrouped(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        group = slide.shapes.add_group_shape()
        member = group.shapes.add_shape(1, Inches(1), Inches(1), Inches(1), Inches(1))
        group.shapes.add_shape(1, Inches(3), Inches(1), Inches(1), Inches(1))
        Entrance.fade(slide, group)
        Entrance.fade(slide, member)

        group.ungroup()
        pptx = _saved(prs)

        assert_schema_valid(pptx)
        _assert_no_dangling_target(pptx)

    def it_stays_valid_after_effects_are_cleared_or_removed(self):
        prs, slide, _ = _animated_deck(3, animated=3)
        slide.animations.list()[1].remove()
        assert_schema_valid(_saved(prs))

        slide.animations.clear()
        assert_schema_valid(_saved(prs))

    def it_stays_valid_after_effects_are_added_to_the_main_sequence(self):
        prs, slide, shapes = _animated_deck(5, animated=1)
        Entrance.fade(slide, shapes[1], trigger=Trigger.WITH_PREVIOUS, duration=800)
        Entrance.fly_in(slide, shapes[2], trigger=Trigger.AFTER_PREVIOUS)
        Emphasis.spin(slide, shapes[3])
        Exit.fade(slide, shapes[4], trigger=Trigger.AFTER_PREVIOUS, delay=250)
        MotionPath.line(slide, shapes[3], Inches(1), Inches(1))

        assert_schema_valid(_saved(prs))

    def it_stays_valid_when_times_and_angles_come_from_float_arithmetic(self):
        # `dur` and `delay` are unsigned integers and a rotation is a whole
        # number of 60000ths of a degree; "500.0" in any of them is invalid.
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shape = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(1), Inches(1))
        Entrance.fade(slide, shape, duration=1500 / 3, delay=0.2 * 1000)
        Exit.fly_out(slide, shape, duration=2000 / 3, delay=1e2)
        Emphasis.spin(slide, shape, degrees=360 / 7, duration=0.75 * 1000)
        MotionPath.line(slide, shape, Inches(1), Inches(1), duration=2.5e3, delay=100 / 3)
        with slide.animations.sequence(delay=0.1 * 1000):
            Emphasis.pulse(slide, shape, duration=900 / 3)
        slide.animations.typewriter([shape], delay_between_ms=400 / 3, duration=1000 / 3)

        assert_schema_valid(_saved(prs))

    def it_stays_valid_when_the_first_effect_of_a_main_sequence_is_not_on_click(self):
        prs, slide, shapes = _animated_deck(2, animated=0)

        Entrance.fade(slide, shapes[0], trigger=Trigger.AFTER_PREVIOUS)
        Entrance.fade(slide, shapes[1], trigger=Trigger.WITH_PREVIOUS)

        assert_schema_valid(_saved(prs))
