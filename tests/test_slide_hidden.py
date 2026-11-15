# pyright: reportPrivateUsage=false

"""Unit-test suite for `power_pptx.slide.Slide.hidden`."""

from __future__ import annotations

import io

import pytest

from power_pptx import Presentation
from power_pptx.slide import Slide

from .unitutil.cxml import element, xml


def _deck(slides: int = 3):
    prs = Presentation()
    for _ in range(slides):
        prs.slides.add_slide(prs.slide_layouts[6])
    return prs


def _reopened(prs):
    buf = io.BytesIO()
    prs.save(buf)
    return Presentation(io.BytesIO(buf.getvalue()))


class DescribeSlide_hidden(object):
    """`Slide.hidden` is the public face of the `show` attribute of `p:sld`."""

    @pytest.mark.parametrize(
        ("sld_cxml", "expected_value"),
        [
            # -- the attribute is an xsd:boolean defaulting to true ("shown") --
            ("p:sld/p:cSld", False),
            ("p:sld{show=1}/p:cSld", False),
            ("p:sld{show=true}/p:cSld", False),
            ("p:sld{show=0}/p:cSld", True),
            ("p:sld{show=false}/p:cSld", True),
        ],
    )
    def it_knows_whether_it_is_hidden(self, sld_cxml: str, expected_value: bool):
        slide = Slide(element(sld_cxml), None)  # pyright: ignore[reportArgumentType]

        assert slide.hidden is expected_value

    @pytest.mark.parametrize(
        ("sld_cxml", "value", "expected_cxml"),
        [
            ("p:sld/p:cSld", True, "p:sld{show=0}/p:cSld"),
            ("p:sld{show=1}/p:cSld", True, "p:sld{show=0}/p:cSld"),
            # -- un-hiding removes the attribute rather than writing show="1" --
            ("p:sld{show=0}/p:cSld", False, "p:sld/p:cSld"),
            ("p:sld{show=false}/p:cSld", False, "p:sld/p:cSld"),
            ("p:sld{show=1}/p:cSld", False, "p:sld/p:cSld"),
            # -- and assigning the value it has changes nothing --
            ("p:sld/p:cSld", False, "p:sld/p:cSld"),
            ("p:sld{show=0}/p:cSld", True, "p:sld{show=0}/p:cSld"),
            ("p:sld{show=false}/p:cSld", True, "p:sld{show=false}/p:cSld"),
        ],
    )
    def it_can_hide_and_show_itself(self, sld_cxml: str, value: bool, expected_cxml: str):
        slide = Slide(element(sld_cxml), None)  # pyright: ignore[reportArgumentType]

        slide.hidden = value

        assert slide._element.xml == xml(expected_cxml)
        assert slide.hidden is value

    def it_keeps_the_other_attributes_of_the_slide_element(self):
        slide = Slide(
            element("p:sld{showMasterSp=0,show=0}/p:cSld"),
            None,  # pyright: ignore[reportArgumentType]
        )

        slide.hidden = False

        assert slide._element.xml == xml("p:sld{showMasterSp=0}/p:cSld")

    @pytest.mark.parametrize("value", [None, 1, 0, "true", "no", 1.0])
    def it_rejects_a_value_that_is_not_a_bool(self, value):
        slide = Slide(element("p:sld/p:cSld"), None)  # pyright: ignore[reportArgumentType]

        with pytest.raises(TypeError, match="hidden must be True or False"):
            slide.hidden = value

        assert slide._element.xml == xml("p:sld/p:cSld")

    def it_is_visible_when_newly_added_and_reading_it_changes_nothing(self):
        prs = _deck(1)
        slide = prs.slides[0]
        before = slide._element.xml

        assert slide.hidden is False
        assert slide._element.xml == before
        assert slide._element.get("show") is None

    def it_hides_only_the_slide_it_is_set_on(self):
        prs = _deck(3)

        prs.slides[1].hidden = True

        assert [slide.hidden for slide in prs.slides] == [False, True, False]

    def it_is_still_hidden_after_a_save_and_reload(self):
        prs = _deck(3)
        prs.slides[0].hidden = True
        prs.slides[2].hidden = True

        again = _reopened(prs)

        assert [slide.hidden for slide in again.slides] == [True, False, True]
        assert [slide._element.get("show") for slide in again.slides] == ["0", None, "0"]

    def it_leaves_the_slide_as_it_was_after_hiding_and_showing_it(self):
        prs = _deck(1)
        slide = prs.slides[0]
        before = slide._element.xml

        slide.hidden = True
        assert slide._element.xml != before
        slide.hidden = False

        assert slide._element.xml == before

    def it_replaces_the_hand_written_show_attribute_idiom(self):
        """`slide._element.set("show", "0")` was the only way to hide a slide before."""
        prs = _deck(2)
        prs.slides[0]._element.set("show", "0")
        assert prs.slides[0].hidden is True

        prs.slides[1].hidden = True

        assert prs.slides[1]._element.get("show") == prs.slides[0]._element.get("show")

    def it_is_a_property_of_slides_only(self):
        # -- `show` is not an attribute of a layout, master or notes page --
        prs = _deck(1)
        assert not hasattr(prs.slide_layouts[0], "hidden")
        assert not hasattr(prs.slide_master, "hidden")
        assert not hasattr(prs.slides[0].notes_slide, "hidden")
