"""Unit-test suite for `power_pptx.dml.effect` module."""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx.dml.effect import BlurFormat, ReflectionFormat, ShadowFormat
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.oxml.ns import qn
from power_pptx.util import Emu, Inches

from ..unitutil.cxml import element, xml


class DescribeShadowFormat(object):
    def it_knows_whether_it_inherits(self, inherit_get_fixture):
        shadow, expected_value = inherit_get_fixture
        with pytest.warns(DeprecationWarning, match="ShadowFormat.inherit"):
            inherit = shadow.inherit
        assert inherit is expected_value

    def it_can_change_whether_it_inherits(self, inherit_set_fixture):
        shadow, value, expected_xml = inherit_set_fixture
        with pytest.warns(DeprecationWarning, match="ShadowFormat.inherit"):
            shadow.inherit = value
        assert shadow._element.xml == expected_xml

    def it_emits_deprecation_warning_on_inherit_access(self):
        shadow = ShadowFormat(element("p:spPr"))
        with pytest.warns(DeprecationWarning, match="ShadowFormat.inherit"):
            _ = shadow.inherit

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

    def it_defaults_color_to_black_on_alpha_only_assignment(self):
        # Regression: setting shadow.color.alpha on a fresh shadow used to
        # raise because color.type was None.  Shadows are almost always black,
        # so an alpha-only assignment now defaults the colour to black.
        from power_pptx.dml.color import RGBColor

        shadow = ShadowFormat(element("p:spPr"))
        shadow.color.alpha = 0.4
        assert shadow.color.rgb == RGBColor(0x00, 0x00, 0x00)
        assert shadow.color.alpha == 0.4

    def it_writes_a_colour_child_for_a_geometry_only_shadow(self):
        # <a:outerShdw> requires exactly one EG_ColorChoice child; a
        # geometry-only shadow used to emit a colour-less element that
        # PowerPoint flags as broken (the empty-scene3d failure mode).
        from power_pptx.dml.color import RGBColor

        shadow = ShadowFormat(element("p:spPr"))
        shadow.blur_radius = Emu(50800)
        assert shadow.color.rgb == RGBColor(0x00, 0x00, 0x00)

    def it_supports_direct_color_assignment(self):
        from power_pptx.dml.color import RGBColor

        shadow = ShadowFormat(element("p:spPr"))
        shadow.color = RGBColor(0x11, 0x22, 0x33)
        assert shadow.color.rgb == RGBColor(0x11, 0x22, 0x33)


class DescribeGlowFormatColor(object):
    def it_writes_a_colour_child_for_a_radius_only_glow(self):
        from power_pptx.dml.color import RGBColor
        from power_pptx.dml.effect import GlowFormat

        glow = GlowFormat(element("p:spPr"))
        glow.radius = Emu(76200)
        assert glow.color.rgb == RGBColor(0x00, 0x00, 0x00)

    def it_supports_direct_color_assignment(self):
        from power_pptx.dml.color import RGBColor
        from power_pptx.dml.effect import GlowFormat

        glow = GlowFormat(element("p:spPr"))
        glow.color = RGBColor(0xAA, 0xBB, 0xCC)
        assert glow.color.rgb == RGBColor(0xAA, 0xBB, 0xCC)


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
            "p:spPr/a:effectLst/a:reflection{blurRad=38100,dist=50800,dir=5400000,stA=50000,endA=0}"
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


class DescribeInnerShadowFormat(object):
    def it_returns_None_for_unset_attributes(self):
        from power_pptx.dml.effect import InnerShadowFormat

        inner = InnerShadowFormat(element("p:spPr"))
        assert inner.blur_radius is None
        assert inner.distance is None
        assert inner.direction is None
        assert inner.color.rgb is None
        assert inner._element.xml == xml("p:spPr")

    def it_reads_explicit_attributes(self):
        from power_pptx.dml.effect import InnerShadowFormat

        spPr = element(
            "p:spPr/a:effectLst/a:innerShdw{blurRad=50800,dist=38100,dir=2700000}"
            "/a:srgbClr{val=112233}"
        )
        inner = InnerShadowFormat(spPr)
        assert inner.blur_radius == Emu(50800)
        assert inner.distance == Emu(38100)
        assert inner.direction == 45.0

    def it_reads_explicit_color(self):
        from power_pptx.dml.color import RGBColor
        from power_pptx.dml.effect import InnerShadowFormat

        spPr = element("p:spPr/a:effectLst/a:innerShdw/a:srgbClr{val=112233}")
        inner = InnerShadowFormat(spPr)
        assert inner.color.rgb == RGBColor(0x11, 0x22, 0x33)

    def it_creates_innerShdw_element_lazily_on_set(self):
        from power_pptx.dml.effect import InnerShadowFormat

        spPr = element("p:spPr")
        inner = InnerShadowFormat(spPr)

        assert spPr.effectLst is None

        inner.blur_radius = Emu(50800)

        assert spPr.effectLst is not None
        assert spPr.effectLst.innerShdw is not None
        assert inner.blur_radius == Emu(50800)

    def it_writes_a_colour_child_for_a_geometry_only_inner_shadow(self):
        from power_pptx.dml.color import RGBColor
        from power_pptx.dml.effect import InnerShadowFormat

        inner = InnerShadowFormat(element("p:spPr"))
        inner.distance = Emu(38100)
        # <a:innerShdw> requires exactly one EG_ColorChoice child; geometry-only
        # writes must still emit a colour or PowerPoint flags the deck broken.
        assert inner.color.rgb == RGBColor(0x00, 0x00, 0x00)

    def it_sets_direction_and_color_together(self):
        from power_pptx.dml.color import RGBColor
        from power_pptx.dml.effect import InnerShadowFormat

        inner = InnerShadowFormat(element("p:spPr"))
        inner.direction = 90.0
        inner.color.rgb = RGBColor(0xAA, 0xBB, 0xCC)
        assert inner.direction == 90.0
        assert inner.color.rgb == RGBColor(0xAA, 0xBB, 0xCC)

    def it_supports_direct_color_assignment(self):
        from power_pptx.dml.color import RGBColor
        from power_pptx.dml.effect import InnerShadowFormat

        inner = InnerShadowFormat(element("p:spPr"))
        inner.color = RGBColor(0x11, 0x22, 0x33)
        assert inner.color.rgb == RGBColor(0x11, 0x22, 0x33)


class DescribePresetShadowFormat(object):
    def it_returns_None_for_unset_attributes(self):
        from power_pptx.dml.effect import PresetShadowFormat

        preset = PresetShadowFormat(element("p:spPr"))
        assert preset.preset is None
        assert preset.distance is None
        assert preset.direction is None
        assert preset.color.rgb is None
        assert preset._element.xml == xml("p:spPr")

    def it_reads_explicit_preset_and_attributes(self):
        from power_pptx.dml.effect import PresetShadowFormat
        from power_pptx.enum.dml import MSO_PRESET_SHADOW

        spPr = element(
            "p:spPr/a:effectLst/a:prstShdw{prst=shdw5,dist=38100,dir=2700000}/a:srgbClr{val=aabbcc}"
        )
        preset = PresetShadowFormat(spPr)
        assert preset.preset is MSO_PRESET_SHADOW.SHADOW_5
        assert preset.distance == Emu(38100)
        assert preset.direction == 45.0

    def it_accepts_a_preset_string(self):
        from power_pptx.dml.effect import PresetShadowFormat
        from power_pptx.enum.dml import MSO_PRESET_SHADOW

        preset = PresetShadowFormat(element("p:spPr"))
        preset.preset = "shdw7"
        assert preset.preset is MSO_PRESET_SHADOW.SHADOW_7

    def it_accepts_an_enum_member(self):
        from power_pptx.dml.effect import PresetShadowFormat
        from power_pptx.enum.dml import MSO_PRESET_SHADOW

        preset = PresetShadowFormat(element("p:spPr"))
        preset.preset = MSO_PRESET_SHADOW.SHADOW_12
        assert preset.preset is MSO_PRESET_SHADOW.SHADOW_12

    def it_defaults_preset_to_shdw1_on_geometry_only_write(self):
        from power_pptx.dml.color import RGBColor
        from power_pptx.dml.effect import PresetShadowFormat
        from power_pptx.enum.dml import MSO_PRESET_SHADOW

        # `prst` is schema-REQUIRED; setting only distance/color must still
        # produce a valid element with a preset and a colour child.
        preset = PresetShadowFormat(element("p:spPr"))
        preset.distance = Emu(38100)
        assert preset.preset is MSO_PRESET_SHADOW.SHADOW_1
        assert preset.color.rgb == RGBColor(0x00, 0x00, 0x00)

    def it_reads_explicit_color(self):
        from power_pptx.dml.color import RGBColor
        from power_pptx.dml.effect import PresetShadowFormat

        spPr = element("p:spPr/a:effectLst/a:prstShdw{prst=shdw3}/a:srgbClr{val=aabbcc}")
        preset = PresetShadowFormat(spPr)
        assert preset.color.rgb == RGBColor(0xAA, 0xBB, 0xCC)

    def it_clears_the_element_when_preset_set_to_None(self):
        from power_pptx.dml.effect import PresetShadowFormat

        spPr = element("p:spPr/a:effectLst/a:prstShdw{prst=shdw5}/a:srgbClr{val=aabbcc}")
        preset = PresetShadowFormat(spPr)

        preset.preset = None

        assert spPr.effectLst is not None
        assert spPr.effectLst.prstShdw is None

    def it_supports_direct_color_assignment(self):
        from power_pptx.dml.color import RGBColor
        from power_pptx.dml.effect import PresetShadowFormat

        preset = PresetShadowFormat(element("p:spPr"))
        preset.color = RGBColor(0x11, 0x22, 0x33)
        assert preset.color.rgb == RGBColor(0x11, 0x22, 0x33)


def _deck_with_shadow_effects():
    """Build a one-slide deck with an inner-shadow shape and a preset-shadow shape."""
    from power_pptx import Presentation
    from power_pptx.enum.shapes import MSO_SHAPE
    from power_pptx.util import Inches

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    sp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(3), Inches(1.5))
    sp.inner_shadow.blur_radius = Emu(50800)
    sp.inner_shadow.distance = Emu(38100)
    sp.inner_shadow.direction = 45.0
    sp.inner_shadow.color.rgb = (0x11, 0x22, 0x33)

    sp2 = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(1), Inches(3), Inches(3), Inches(1.5))
    sp2.preset_shadow.preset = "shdw5"
    sp2.preset_shadow.distance = Emu(38100)
    sp2.preset_shadow.color.rgb = (0xAA, 0xBB, 0xCC)
    return prs


class DescribeShadowEffectsRoundTrip(object):
    def it_round_trips_inner_and_preset_shadow(self):
        from tests.integration.round_trip import assert_round_trip

        assert_round_trip(_deck_with_shadow_effects())

    def it_reopens_inner_and_preset_shadow(self):
        import io

        from power_pptx import Presentation
        from power_pptx.enum.dml import MSO_PRESET_SHADOW

        buf = io.BytesIO()
        _deck_with_shadow_effects().save(buf)
        buf.seek(0)
        prs = Presentation(buf)
        shapes = list(prs.slides[0].shapes)
        assert shapes[0].inner_shadow.blur_radius == Emu(50800)
        assert shapes[0].inner_shadow.direction == 45.0
        assert shapes[1].preset_shadow.preset is MSO_PRESET_SHADOW.SHADOW_5


class DescribeShadowEffectsSchemaValidity(object):
    def it_emits_schema_valid_inner_and_preset_shadow(self):
        import io

        from tests.schema.oxml_schema_validator import (
            iter_schema_violations,
            schema_validation_available,
        )

        if not schema_validation_available():
            pytest.skip("schema validation unavailable")

        buf = io.BytesIO()
        _deck_with_shadow_effects().save(buf)
        assert list(iter_schema_violations(buf.getvalue())) == []


class DescribeShadowFormatClear(object):
    """Unit-test suite for `ShadowFormat.clear()`."""

    def it_removes_every_explicit_shadow_element(self):
        shadow = ShadowFormat(
            element("p:spPr/a:effectLst/(a:innerShdw,a:outerShdw,a:prstShdw{prst=shdw1})")
        )
        shadow.clear()
        assert shadow._element.xml == xml("p:spPr/a:effectLst")

    def it_keeps_non_shadow_effects(self):
        shadow = ShadowFormat(element("p:spPr/a:effectLst/(a:glow{rad=50800},a:outerShdw)"))
        shadow.clear()
        assert shadow._element.xml == xml("p:spPr/a:effectLst/a:glow{rad=50800}")

    def it_writes_an_empty_effectLst_when_there_was_none(self):
        shadow = ShadowFormat(element("p:spPr{a:b=c}"))
        shadow.clear()
        assert shadow._element.xml == xml("p:spPr{a:b=c}/a:effectLst")

    def it_is_idempotent(self):
        shadow = ShadowFormat(element("p:spPr{a:b=c}"))
        assert shadow.clear().clear()._element.xml == xml("p:spPr{a:b=c}/a:effectLst")

    def it_suppresses_the_theme_effect_style_of_an_autoshape(self):
        shape = _autoshape()
        assert _effect_ref_idx(shape) == "2"  # theme's soft drop shadow

        shape.shadow.clear()

        assert _effect_ref_idx(shape) == "0"
        assert shape.shadow.blur_radius is None

    def but_the_deprecated_inherit_False_stays_symmetric(self):
        # `inherit` has to round-trip: `clear()` edits <p:style>, which
        # `inherit = True` could never put back, so the deprecated property
        # keeps its historical effectLst-only behaviour and its warning names
        # `clear()` as the way to actually remove a shadow.
        shape = _autoshape()

        with pytest.warns(DeprecationWarning, match=r"clear\(\)"):
            shape.shadow.inherit = False
        assert _effect_ref_idx(shape) == "2"

        with pytest.warns(DeprecationWarning, match="ShadowFormat.inherit"):
            shape.shadow.inherit = True
        assert _effect_ref_idx(shape) == "2"
        assert shape._element.spPr.effectLst is None

    def it_prunes_shadows_from_an_effect_dag_instead_of_adding_a_list(self):
        # <a:effectLst> and <a:effectDag> are the two arms of one
        # EG_EffectProperties choice, so a sibling list would be schema-invalid
        # and would leave the DAG's own shadow rendering.
        shadow = ShadowFormat(
            element(
                "p:spPr/a:effectDag/(a:cont/(a:outerShdw,a:glow{rad=50800}),a:innerShdw)"
            )
        )

        shadow.clear()

        assert shadow._element.xml == xml(
            "p:spPr/a:effectDag/a:cont/a:glow{rad=50800}"
        )
        assert shadow._element.effectLst is None

    def it_leaves_a_shape_without_a_style_element_alone(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        textbox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))

        textbox.shadow.clear()  # no <p:style> to re-point — must not raise

        assert textbox._element.find(qn("p:style")) is None


def _autoshape():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    return slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1), Inches(1), Inches(3), Inches(2)
    )


def _effect_ref_idx(shape):
    style = shape._element.find(qn("p:style"))
    return style.find(qn("a:effectRef")).get("idx")
