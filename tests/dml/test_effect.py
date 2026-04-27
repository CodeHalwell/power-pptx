"""Unit-test suite for `pptx.dml.effect` module."""

from __future__ import annotations

import pytest

from pptx.dml.effect import BlurFormat, ReflectionFormat, ShadowFormat
from pptx.util import Emu

from ..unitutil.cxml import element, xml


class DescribeShadowFormat(object):
    def it_knows_whether_it_inherits(self, inherit_get_fixture):
        shadow, expected_value = inherit_get_fixture
        inherit = shadow.inherit
        assert inherit is expected_value

    def it_can_change_whether_it_inherits(self, inherit_set_fixture):
        shadow, value, expected_xml = inherit_set_fixture
        shadow.inherit = value
        assert shadow._element.xml == expected_xml

    # fixtures -------------------------------------------------------

    @pytest.fixture(
        params=[
            ("p:spPr", True),
            ("p:spPr/a:effectLst", False),
            ("p:grpSpPr", True),
            ("p:grpSpPr/a:effectLst", False),
        ]
    )
    def inherit_get_fixture(self, request):
        cxml, expected_value = request.param
        shadow = ShadowFormat(element(cxml))
        return shadow, expected_value

    @pytest.fixture(
        params=[
            ("p:spPr{a:b=c}", False, "p:spPr{a:b=c}/a:effectLst"),
            ("p:grpSpPr{a:b=c}", False, "p:grpSpPr{a:b=c}/a:effectLst"),
            ("p:spPr{a:b=c}/a:effectLst", True, "p:spPr{a:b=c}"),
            ("p:grpSpPr{a:b=c}/a:effectLst", True, "p:grpSpPr{a:b=c}"),
            ("p:spPr", True, "p:spPr"),
            ("p:grpSpPr", True, "p:grpSpPr"),
            ("p:spPr/a:effectLst", False, "p:spPr/a:effectLst"),
            ("p:grpSpPr/a:effectLst", False, "p:grpSpPr/a:effectLst"),
        ]
    )
    def inherit_set_fixture(self, request):
        cxml, value, expected_cxml = request.param
        shadow = ShadowFormat(element(cxml))
        expected_value = xml(expected_cxml)
        return shadow, value, expected_value


class DescribeBlurFormat(object):
    def it_returns_None_for_radius_when_no_blur_element(self):
        blur = BlurFormat(element("p:spPr"))
        assert blur.radius is None
        assert blur.grow is None
        # read must not have mutated XML
        assert blur._element.xml == xml("p:spPr")

    def it_reads_explicit_radius_and_grow(self):
        spPr = element("p:spPr/a:effectLst/a:blur{rad=63500,grow=0}")
        blur = BlurFormat(spPr)
        assert blur.radius == Emu(63500)
        assert blur.grow is False

    def it_creates_blur_element_lazily_on_radius_set(self):
        spPr = element("p:spPr")
        blur = BlurFormat(spPr)

        # before write: no <a:effectLst> child
        assert spPr.effectLst is None

        blur.radius = Emu(63500)

        # after write: <a:effectLst><a:blur rad="63500"/></a:effectLst>
        assert spPr.effectLst is not None
        assert spPr.effectLst.blur is not None
        assert blur.radius == Emu(63500)

    def it_drops_blur_element_on_radius_None(self):
        spPr = element("p:spPr/a:effectLst/a:blur{rad=63500}")
        blur = BlurFormat(spPr)

        blur.radius = None

        # blur child is dropped; the surrounding effectLst can stay since
        # it may host other effects
        assert spPr.effectLst is not None
        assert spPr.effectLst.blur is None

    def it_can_round_trip_grow(self):
        spPr = element("p:spPr")
        blur = BlurFormat(spPr)

        blur.radius = Emu(63500)
        blur.grow = True
        assert blur.grow is True

        blur.grow = False
        assert blur.grow is False

        blur.grow = None
        assert blur.grow is None

    def it_drops_blur_element_when_last_attribute_cleared_via_grow(self):
        # `grow=False` then `grow=None` was previously leaving an empty
        # `<a:blur/>` behind that blocked theme inheritance even though
        # every exposed property read `None`.
        spPr = element("p:spPr")
        blur = BlurFormat(spPr)

        blur.grow = False
        assert spPr.effectLst is not None
        assert spPr.effectLst.blur is not None

        blur.grow = None
        # The empty <a:blur> element must be removed so theme inheritance
        # is restored.
        assert spPr.effectLst is None or spPr.effectLst.blur is None

    def it_keeps_blur_when_other_attribute_remains(self):
        # Clearing `radius` while `grow` is still set must NOT drop the
        # element — that would silently lose the user's `grow` choice.
        spPr = element("p:spPr")
        blur = BlurFormat(spPr)

        blur.radius = Emu(63500)
        blur.grow = False

        blur.radius = None

        assert spPr.effectLst.blur is not None
        assert blur.radius is None
        assert blur.grow is False


class DescribeReflectionFormat(object):
    def it_returns_None_for_unset_attributes(self):
        reflection = ReflectionFormat(element("p:spPr"))
        assert reflection.blur_radius is None
        assert reflection.distance is None
        assert reflection.direction is None
        assert reflection.start_alpha is None
        assert reflection.end_alpha is None
        assert reflection._element.xml == xml("p:spPr")

    def it_reads_explicit_attributes(self):
        spPr = element(
            "p:spPr/a:effectLst/a:reflection{blurRad=38100,dist=50800,dir=5400000"
            ",stA=50000,endA=0}"
        )
        reflection = ReflectionFormat(spPr)
        assert reflection.blur_radius == Emu(38100)
        assert reflection.distance == Emu(50800)
        assert reflection.direction == 90.0
        assert reflection.start_alpha == 0.5
        assert reflection.end_alpha == 0.0

    def it_creates_reflection_element_lazily_on_set(self):
        spPr = element("p:spPr")
        reflection = ReflectionFormat(spPr)

        assert spPr.effectLst is None

        reflection.blur_radius = Emu(38100)

        assert spPr.effectLst is not None
        assert spPr.effectLst.reflection is not None
        assert reflection.blur_radius == Emu(38100)

    def it_drops_reflection_when_last_attribute_cleared(self):
        spPr = element("p:spPr/a:effectLst/a:reflection{blurRad=38100}")
        reflection = ReflectionFormat(spPr)

        reflection.blur_radius = None

        # the empty <a:reflection> element should have been removed; the
        # surrounding <a:effectLst> can stay since it may host other effects
        assert spPr.effectLst is not None
        assert spPr.effectLst.reflection is None

    def it_keeps_reflection_when_other_attributes_remain(self):
        spPr = element("p:spPr/a:effectLst/a:reflection{blurRad=38100,dist=50800}")
        reflection = ReflectionFormat(spPr)

        reflection.blur_radius = None

        assert spPr.effectLst.reflection is not None
        assert reflection.blur_radius is None
        assert reflection.distance == Emu(50800)
