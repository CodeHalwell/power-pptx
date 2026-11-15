"""Round-trip suite for slide transitions written by PowerPoint itself.

Transitions newer than PowerPoint 2007 arrive wrapped in `mc:AlternateContent`,
with a fallback of the authoring application's choosing. Opening such a deck
and saving it again without touching the transition must give the slide back
exactly as it was read.
"""

from __future__ import annotations

import io
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from power_pptx import Presentation
from power_pptx.enum.presentation import MSO_TRANSITION_TYPE

from .round_trip import _canonicalize_xml, _parts, _save_to_bytes, assert_round_trip

_SLIDE = "ppt/slides/slide1.xml"

_MC = 'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
_P14 = 'xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main"'
_P15 = 'xmlns:p15="http://schemas.microsoft.com/office/powerpoint/2012/main"'
_P159 = 'xmlns:p159="http://schemas.microsoft.com/office/powerpoint/2015/09/main"'

# -- PowerPoint 2013+ "Airplane": a p15 kind, a p14 duration, a fade for older viewers --
_AIRPLANE = (
    f"<mc:AlternateContent {_MC}>"
    f'<mc:Choice {_P15} Requires="p15">'
    f'<p:transition {_P14} spd="slow" p14:dur="1250">'
    '<p15:prstTrans prst="airplane"/></p:transition></mc:Choice>'
    '<mc:Fallback><p:transition spd="slow"><p:fade/></p:transition></mc:Fallback>'
    "</mc:AlternateContent>"
)

_TRANSITIONS = {
    "p15-kind-with-p14-duration": _AIRPLANE,
    # -- some producers leave the duration out --
    "p15-kind-alone": _AIRPLANE.replace(' p14:dur="1250"', ""),
    # -- a p14 kind with attributes, and a fallback this library would not generate --
    "p14-kind-with-its-own-fallback": (
        f"<mc:AlternateContent {_MC}>"
        f'<mc:Choice {_P14} Requires="p14">'
        '<p:transition spd="slow" p14:dur="1600" advTm="3000">'
        '<p14:prism isInverted="1"/></p:transition></mc:Choice>'
        '<mc:Fallback><p:transition spd="slow" advTm="3000"><p:push dir="u"/></p:transition>'
        "</mc:Fallback></mc:AlternateContent>"
    ),
    "p159-morph": (
        f"<mc:AlternateContent {_MC}>"
        f'<mc:Choice {_P159} {_P14} Requires="p159">'
        '<p:transition spd="slow" p14:dur="2000">'
        '<p159:morph option="byObject"/></p:transition></mc:Choice>'
        '<mc:Fallback><p:transition spd="slow"><p:fade/></p:transition></mc:Fallback>'
        "</mc:AlternateContent>"
    ),
    # -- a classic kind that only needs the wrapper for its p14 duration --
    "classic-kind-with-p14-duration": (
        f"<mc:AlternateContent {_MC}>"
        f'<mc:Choice {_P14} Requires="p14">'
        '<p:transition spd="med" p14:dur="700"><p:push dir="u"/></p:transition></mc:Choice>'
        '<mc:Fallback><p:transition spd="med"><p:push dir="u"/></p:transition></mc:Fallback>'
        "</mc:AlternateContent>"
    ),
}


def _deck_with_transition(markup: str) -> bytes:
    """A one-slide deck whose slide carries `markup` where its transition belongs."""
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[6])
    base = _save_to_bytes(prs)

    out = io.BytesIO()
    with ZipFile(io.BytesIO(base)) as zin, ZipFile(out, "w", ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == _SLIDE:
                assert b"</p:clrMapOvr>" in data
                data = data.replace(b"</p:clrMapOvr>", b"</p:clrMapOvr>" + markup.encode())
            zout.writestr(item, data)
    return out.getvalue()


def _slide_xml(pptx: bytes) -> bytes:
    return _canonicalize_xml(_parts(pptx)[_SLIDE])


class DescribePowerPointAuthoredTransitionsRoundTrip:
    """A transition the library was not asked to change survives load → save unchanged."""

    @pytest.mark.parametrize("name", sorted(_TRANSITIONS))
    def it_saves_an_untouched_transition_back_as_it_was_read(self, name):
        source = _deck_with_transition(_TRANSITIONS[name])

        resaved = _save_to_bytes(Presentation(io.BytesIO(source)))

        assert _slide_xml(resaved) == _slide_xml(source)

    @pytest.mark.parametrize("name", sorted(_TRANSITIONS))
    def it_stays_stable_over_further_load_and_save_cycles(self, name):
        source = _deck_with_transition(_TRANSITIONS[name])

        assert_round_trip(Presentation(io.BytesIO(source)))

    def it_saves_the_transition_back_unchanged_after_only_reading_it(self):
        source = _deck_with_transition(_AIRPLANE)
        prs = Presentation(io.BytesIO(source))
        transition = prs.slides[0].transition

        assert transition.kind is None  # -- no enum member for the p15 kinds --
        assert transition.duration == 1250
        assert transition.advance_after is None

        assert _slide_xml(_save_to_bytes(prs)) == _slide_xml(source)

    def it_round_trips_a_transition_changed_after_load(self):
        prs = Presentation(io.BytesIO(_deck_with_transition(_AIRPLANE)))
        prs.slides[0].transition.advance_after = 3000

        resaved = _save_to_bytes(prs)

        # -- the change is there, in the choice and in the fallback alike --
        assert _parts(resaved)[_SLIDE].count(b'advTm="3000"') == 2
        reopened = Presentation(io.BytesIO(resaved))
        assert reopened.slides[0].transition.advance_after == 3000
        assert reopened.slides[0].transition.duration == 1250
        assert_round_trip(reopened)

    def it_round_trips_a_transition_replaced_after_load(self):
        prs = Presentation(io.BytesIO(_deck_with_transition(_AIRPLANE)))
        prs.slides[0].transition.kind = MSO_TRANSITION_TYPE.VORTEX

        reopened = Presentation(io.BytesIO(_save_to_bytes(prs)))

        assert reopened.slides[0].transition.kind == MSO_TRANSITION_TYPE.VORTEX
        assert b"prstTrans" not in _parts(_save_to_bytes(reopened))[_SLIDE]
        assert_round_trip(reopened)

    @pytest.mark.parametrize("kind", list(MSO_TRANSITION_TYPE), ids=lambda k: k.name)
    def it_round_trips_every_kind_the_library_writes(self, kind):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.transition.kind = kind
        slide.transition.duration = 600

        reopened = Presentation(io.BytesIO(_save_to_bytes(prs)))

        assert reopened.slides[0].transition.kind == kind
        assert reopened.slides[0].transition.duration == 600
        assert_round_trip(reopened)

    def it_round_trips_a_transition_removed_after_load(self):
        prs = Presentation(io.BytesIO(_deck_with_transition(_AIRPLANE)))
        prs.slides[0].transition.clear()

        resaved = _save_to_bytes(prs)

        slide_xml = _parts(resaved)[_SLIDE]
        assert b"transition" not in slide_xml
        assert b"AlternateContent" not in slide_xml
        assert_round_trip(Presentation(io.BytesIO(resaved)))
