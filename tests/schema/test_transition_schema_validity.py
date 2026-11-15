"""Schema validity of slide transitions after a load → save cycle.

The transition kinds PowerPoint 2010+ added live in extension namespaces and
reach the file wrapped in `mc:AlternateContent`. The validator resolves each
wrapper to its `mc:Fallback`, the branch every consumer must be able to read,
so these tests fail whenever extension markup leaks out of the `mc:Choice`.
"""

from __future__ import annotations

import io
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from power_pptx import Presentation
from power_pptx.enum.presentation import MSO_TRANSITION_TYPE

from .oxml_schema_validator import assert_schema_valid, schema_validation_available

pytestmark = pytest.mark.skipif(
    not schema_validation_available(),
    reason="lxml or the bundled ISO-29500 XSD schemas are unavailable",
)

_MC = 'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
_P14 = 'xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main"'
_P15 = 'xmlns:p15="http://schemas.microsoft.com/office/powerpoint/2012/main"'

# -- PowerPoint 2013+ "Airplane" --
_AIRPLANE = (
    f"<mc:AlternateContent {_MC}>"
    f'<mc:Choice {_P15} Requires="p15">'
    f'<p:transition {_P14} spd="slow" p14:dur="1250">'
    '<p15:prstTrans prst="airplane"/></p:transition></mc:Choice>'
    '<mc:Fallback><p:transition spd="slow"><p:fade/></p:transition></mc:Fallback>'
    "</mc:AlternateContent>"
)

# -- what load → save made of it before this was fixed: the p15 kind copied into
# -- the fallback, under a `Requires` naming the wrong namespace --
_AIRPLANE_CORRUPTED = (
    f"<mc:AlternateContent {_MC}>"
    f'<mc:Choice {_P14} Requires="p14">'
    f'<p:transition {_P15} spd="slow" p14:dur="1250">'
    '<p15:prstTrans prst="airplane"/></p:transition></mc:Choice>'
    f'<mc:Fallback><p:transition spd="slow"><p15:prstTrans {_P15} prst="airplane"/>'
    "</p:transition></mc:Fallback></mc:AlternateContent>"
)

_PRISM = (
    f"<mc:AlternateContent {_MC}>"
    f'<mc:Choice {_P14} Requires="p14">'
    '<p:transition spd="slow" p14:dur="1600"><p14:prism isInverted="1"/></p:transition>'
    "</mc:Choice>"
    '<mc:Fallback><p:transition spd="slow"><p:fade/></p:transition></mc:Fallback>'
    "</mc:AlternateContent>"
)


def _saved(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _deck_with_transition(markup: str) -> bytes:
    """A one-slide deck whose slide carries `markup` where its transition belongs."""
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[6])

    out = io.BytesIO()
    with ZipFile(io.BytesIO(_saved(prs))) as zin, ZipFile(out, "w", ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "ppt/slides/slide1.xml":
                assert b"</p:clrMapOvr>" in data
                data = data.replace(b"</p:clrMapOvr>", b"</p:clrMapOvr>" + markup.encode())
            zout.writestr(item, data)
    return out.getvalue()


def _reloaded(markup: str):
    return Presentation(io.BytesIO(_deck_with_transition(markup)))


class DescribeLoadedTransitionSchemaValidity:
    @pytest.mark.parametrize(
        "markup",
        [_AIRPLANE, _AIRPLANE.replace(' p14:dur="1250"', ""), _PRISM],
        ids=["p15-kind-with-p14-duration", "p15-kind-alone", "p14-kind"],
    )
    def it_saves_an_untouched_extension_transition_schema_valid(self, markup):
        assert_schema_valid(_saved(_reloaded(markup)))

    @pytest.mark.parametrize("markup", [_AIRPLANE, _PRISM], ids=["p15-kind", "p14-kind"])
    def it_saves_a_retimed_extension_transition_schema_valid(self, markup):
        prs = _reloaded(markup)
        prs.set_transition(duration=900, advance_after=4000, advance_on_click=False)

        assert_schema_valid(_saved(prs))

    def it_saves_a_replaced_extension_transition_schema_valid(self):
        prs = _reloaded(_AIRPLANE)
        prs.set_transition(MSO_TRANSITION_TYPE.FADE, force=True)

        assert_schema_valid(_saved(prs))

    def it_writes_every_kind_schema_valid(self):
        # One slide per member, each with timing settings as well, so that
        # the classic kinds, the extension kinds and their wrappers all
        # meet the schema.
        prs = Presentation()
        for kind in MSO_TRANSITION_TYPE:
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            slide.transition.kind = kind
            slide.transition.duration = 700
            slide.transition.advance_after = 3000

        pptx = _saved(prs)

        assert_schema_valid(pptx)
        reopened = Presentation(io.BytesIO(pptx))
        assert [s.transition.kind for s in reopened.slides] == list(MSO_TRANSITION_TYPE)

    def it_repairs_a_transition_an_earlier_release_corrupted(self):
        with pytest.raises(AssertionError):  # -- the input really is invalid --
            assert_schema_valid(_deck_with_transition(_AIRPLANE_CORRUPTED))

        assert_schema_valid(_saved(_reloaded(_AIRPLANE_CORRUPTED)))
