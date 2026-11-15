"""Validate the slide-show settings XML against the ISO-29500 schema.

`prs.slide_show` writes `p:showPr` into `ppt/presProps.xml`, and both that
element and its parent are strict sequences: `p:showPr` has to come before
`p:clrMru` and `p:extLst`, and the show-type child before the slide list, the
pen colour and the extension list. The packaged validator does not check this
part, so each deck is validated twice: as a package (relationships, content
types, the parts the validator does cover) and `presProps.xml` on its own
against `pml.xsd`.
"""

from __future__ import annotations

import io

import pytest

from power_pptx import Presentation

from ..unitutil.presprops import (
    POWERPOINT_PRESPROPS_XML,
    PRESPROPS,
    part_names,
    presprops_root,
    presprops_schema_errors,
    saved,
    with_presprops,
    without_presprops,
)
from .oxml_schema_validator import assert_schema_valid, schema_validation_available

pytestmark = pytest.mark.skipif(
    not schema_validation_available(),
    reason="lxml or the bundled ISO-29500 XSD schemas are unavailable",
)

_P = "http://schemas.openxmlformats.org/presentationml/2006/main"

_EVERYTHING = {
    "loop": True,
    "show_type": "kiosk",
    "use_timings": False,
    "show_narration": False,
    "show_animation": False,
}


def _default_deck():
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[6])
    return prs


def _bare_deck():
    return Presentation(io.BytesIO(without_presprops()))


def _powerpoint_deck():
    return Presentation(io.BytesIO(with_presprops(POWERPOINT_PRESPROPS_XML)))


def _apply(prs, **settings) -> bytes:
    for name, value in settings.items():
        setattr(prs.slide_show, name, value)
    return saved(prs)


def _deck_set_then_reset(factory) -> bytes:
    prs = factory()
    _apply(prs, **_EVERYTHING)
    return _apply(
        prs,
        loop=False,
        show_type="speaker",
        use_timings=True,
        show_narration=True,
        show_animation=True,
    )


_DECK_BUILDERS = {
    "loop": lambda: _apply(_default_deck(), loop=True),
    "kiosk": lambda: _apply(_default_deck(), show_type="kiosk"),
    "window": lambda: _apply(_default_deck(), show_type="window"),
    "manual_advance": lambda: _apply(_default_deck(), use_timings=False),
    "no_narration": lambda: _apply(_default_deck(), show_narration=False),
    "no_animation": lambda: _apply(_default_deck(), show_animation=False),
    "everything": lambda: _apply(_default_deck(), **_EVERYTHING),
    "set_then_reset": lambda: _deck_set_then_reset(_default_deck),
    # -- the part and its relationship are created for a deck that lacks them --
    "created_part_loop": lambda: _apply(_bare_deck(), loop=True),
    "created_part_everything": lambda: _apply(_bare_deck(), **_EVERYTHING),
    "created_part_set_then_reset": lambda: _deck_set_then_reset(_bare_deck),
    # -- `p:showPr` already holds a slide list, pen colour and extension list --
    "powerpoint_untouched": lambda: saved(_powerpoint_deck()),
    "powerpoint_window": lambda: _apply(_powerpoint_deck(), show_type="window"),
    "powerpoint_speaker": lambda: _apply(_powerpoint_deck(), show_type="speaker", loop=False),
    "powerpoint_everything": lambda: _apply(_powerpoint_deck(), **_EVERYTHING),
    "powerpoint_set_then_reset": lambda: _deck_set_then_reset(_powerpoint_deck),
}


class DescribeSlideShowSettingsSchemaValidity:
    @pytest.mark.parametrize("name", sorted(_DECK_BUILDERS))
    def it_validates_against_the_ooxml_schema(self, name):
        blob = _DECK_BUILDERS[name]()

        assert_schema_valid(blob)
        if PRESPROPS in part_names(blob):
            assert presprops_schema_errors(blob) == []

    def it_actually_validates_a_showPr_element(self):
        # -- guard against passing vacuously: the decks must carry the element --
        for name in ("loop", "everything", "created_part_loop", "powerpoint_window"):
            root = presprops_root(_DECK_BUILDERS[name]())
            assert root.find("{%s}showPr" % _P) is not None, name

    @pytest.mark.parametrize(
        ("body", "complaint"),
        [
            # -- p:showPr after the extension list it has to precede --
            ('<p:extLst/><p:showPr loop="1"/>', "showPr"),
            # -- the show type after the slide list it has to precede --
            ("<p:showPr><p:sldAll/><p:kiosk/></p:showPr>", "kiosk"),
            # -- two show types --
            ("<p:showPr><p:kiosk/><p:browse/></p:showPr>", "browse"),
            # -- a value that is not an xsd:boolean --
            ('<p:showPr loop="yes"/>', "loop"),
        ],
    )
    def it_detects_a_showPr_the_schema_does_not_allow(self, body: str, complaint: str):
        # -- self-test for the helper: bypass the API and confirm the mistakes it
        # -- exists to catch are in fact reported --
        xml = '<p:presentationPr xmlns:p="%s">%s</p:presentationPr>' % (_P, body)

        errors = presprops_schema_errors(with_presprops(xml))

        assert errors, body
        assert any(complaint in error for error in errors), errors
