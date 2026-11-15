"""Unit-test suite for `power_pptx.dml.effect` module."""

from __future__ import annotations

import pytest

from power_pptx import Presentation
from power_pptx.dml.effect import BlurFormat, ReflectionFormat, ShadowFormat
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.oxml.ns import qn
from power_pptx.util import Emu, Inches

from ..unitutil.cxml import element, xml


def _same_xml(elm, cxml: str) -> bool:
    """True if `elm` is the XML `cxml` describes, wherever its namespaces are declared.

    An element that has gained and then lost an `a:` child keeps (or lacks) the
    `xmlns:a` declaration depending on how it was built, which a plain string
    comparison would trip over.
    """
    from lxml import etree

    def canonical(e):
        return etree.tostring(e, method="c14n", exclusive=True)

    return canonical(elm) == canonical(element(cxml))


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

        # blur child is dropped, and the effectLst it emptied goes with it: an
        # empty <a:effectLst/> would keep overriding the theme's effects
        assert _same_xml(spPr, "p:spPr")

    def but_it_keeps_an_effectLst_that_hosts_another_effect(self):
        spPr = element("p:spPr/a:effectLst/(a:blur{rad=63500},a:softEdge{rad=12700})")

        BlurFormat(spPr).radius = None

        assert _same_xml(spPr, "p:spPr/a:effectLst/a:softEdge{rad=12700}")

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

        # the empty <a:reflection> element is removed, along with the
        # <a:effectLst> it emptied, so theme effects are inherited again
        assert _same_xml(spPr, "p:spPr")

    def but_it_keeps_an_effectLst_that_hosts_another_effect(self):
        spPr = element("p:spPr/a:effectLst/(a:reflection{blurRad=38100},a:softEdge{rad=12700})")

        ReflectionFormat(spPr).blur_radius = None

        assert _same_xml(spPr, "p:spPr/a:effectLst/a:softEdge{rad=12700}")

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

        # the element goes, and so does the <a:effectLst> it emptied
        assert _same_xml(spPr, "p:spPr")

    def but_it_keeps_the_preset_when_only_distance_is_cleared(self):
        # The preset is what defines the effect, so it survives clearing an
        # override; `preset = None` is what removes a preset shadow.
        from power_pptx.dml.effect import PresetShadowFormat
        from power_pptx.enum.dml import MSO_PRESET_SHADOW

        spPr = element("p:spPr")
        preset = PresetShadowFormat(spPr)
        preset.preset = "shdw1"
        preset.distance = Emu(38100)

        preset.distance = None

        assert preset.preset is MSO_PRESET_SHADOW.SHADOW_1
        assert preset.distance is None

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


# ---------------------------------------------------------------------------
# Lengths may be floats; a rejected value leaves no XML behind; and assigning
# None gives the theme its say back.
# ---------------------------------------------------------------------------

_HALF = Emu(76200) / 2  # a float, as any arithmetic on a Length produces


def _effect(name):
    """Return (spPr, proxy) for the effect proxy class called `name`."""
    from power_pptx.dml import effect

    spPr = element("p:spPr")
    return spPr, getattr(effect, name)(spPr)


class DescribeEffectLengthCoercion(object):
    """Float lengths are rounded to whole EMU, as `shape.left` does."""

    @pytest.mark.parametrize(
        ("cls_name", "prop"),
        [
            ("ShadowFormat", "blur_radius"),
            ("ShadowFormat", "distance"),
            ("InnerShadowFormat", "blur_radius"),
            ("InnerShadowFormat", "distance"),
            ("PresetShadowFormat", "distance"),
            ("GlowFormat", "radius"),
            ("SoftEdgeFormat", "radius"),
            ("BlurFormat", "radius"),
            ("ReflectionFormat", "blur_radius"),
            ("ReflectionFormat", "distance"),
        ],
    )
    def it_accepts_a_float_length(self, cls_name, prop):
        assert isinstance(_HALF, float)
        _, proxy = _effect(cls_name)

        setattr(proxy, prop, _HALF)

        assert getattr(proxy, prop) == Emu(38100)

    def it_rounds_a_fractional_emu_count(self):
        spPr, glow = _effect("GlowFormat")
        glow.radius = 12700.6
        assert spPr.effectLst.glow.get("rad") == "12701"

    @pytest.mark.parametrize("bad", ["38100", True, float("nan"), float("inf")])
    def but_it_rejects_a_value_that_is_not_a_length(self, bad):
        spPr, shadow = _effect("ShadowFormat")
        with pytest.raises(TypeError):
            shadow.blur_radius = bad
        assert _same_xml(spPr, "p:spPr")


class DescribeEffectSettersAreAtomic(object):
    """A setter that rejects its value must not leave an element behind."""

    @pytest.mark.parametrize(
        ("cls_name", "prop", "bad", "exc"),
        [
            ("ShadowFormat", "blur_radius", -1, ValueError),
            ("ShadowFormat", "distance", "far", TypeError),
            ("ShadowFormat", "direction", "down", TypeError),
            ("ShadowFormat", "direction", float("nan"), ValueError),
            ("ShadowFormat", "color", "not-a-colour", ValueError),
            ("InnerShadowFormat", "blur_radius", -1, ValueError),
            ("InnerShadowFormat", "direction", [45], TypeError),
            ("PresetShadowFormat", "preset", "shdw21", ValueError),
            ("PresetShadowFormat", "preset", 99, ValueError),
            ("PresetShadowFormat", "distance", -1, ValueError),
            ("PresetShadowFormat", "direction", "down", TypeError),
            ("GlowFormat", "radius", -1, ValueError),
            ("GlowFormat", "color", (300, 0, 0), ValueError),
            # -- <a:softEdge/> without its required `rad` is schema-invalid
            ("SoftEdgeFormat", "radius", -1, ValueError),
            ("SoftEdgeFormat", "radius", "3pt", TypeError),
            ("BlurFormat", "radius", -1, ValueError),
            # -- a bare <a:reflection/> is a full default reflection
            ("ReflectionFormat", "start_alpha", 1.2, ValueError),
            ("ReflectionFormat", "end_alpha", -0.1, ValueError),
            ("ReflectionFormat", "start_alpha", float("nan"), ValueError),
            ("ReflectionFormat", "blur_radius", -1, ValueError),
            ("ReflectionFormat", "distance", "far", TypeError),
            ("ReflectionFormat", "direction", "down", TypeError),
        ],
    )
    def it_leaves_the_shape_untouched_when_the_value_is_rejected(
        self, cls_name, prop, bad, exc
    ):
        spPr, proxy = _effect(cls_name)

        with pytest.raises(exc):
            setattr(proxy, prop, bad)

        assert _same_xml(spPr, "p:spPr")

    @pytest.mark.parametrize(
        ("cls_name", "sub_prop", "bad"),
        [
            ("ShadowFormat", "rgb", "#FFF"),
            ("ShadowFormat", "alpha", 1.5),
            ("InnerShadowFormat", "rgb", (1, 2)),
            ("PresetShadowFormat", "rgb", "red"),
            ("GlowFormat", "alpha", -0.1),
            ("InnerShadowFormat", "alpha", float("nan")),
        ],
    )
    def it_leaves_the_shape_untouched_when_a_colour_value_is_rejected(
        self, cls_name, sub_prop, bad
    ):
        spPr, proxy = _effect(cls_name)

        with pytest.raises(ValueError):
            setattr(proxy.color, sub_prop, bad)

        assert _same_xml(spPr, "p:spPr")

    def it_rejects_a_theme_colour_with_no_xml_form_before_creating_anything(self):
        from power_pptx.enum.dml import MSO_THEME_COLOR

        spPr, shadow = _effect("ShadowFormat")

        with pytest.raises(ValueError):
            shadow.color.theme_color = MSO_THEME_COLOR.NOT_THEME_COLOR

        assert _same_xml(spPr, "p:spPr")

    def it_does_not_create_a_shadow_to_hold_a_cleared_alpha(self):
        spPr, shadow = _effect("ShadowFormat")
        shadow.color.alpha = None
        assert _same_xml(spPr, "p:spPr")

    def it_keeps_an_existing_effect_intact_when_a_later_value_is_rejected(self):
        from power_pptx.dml.effect import SoftEdgeFormat

        spPr = element("p:spPr/a:effectLst/a:softEdge{rad=12700}")

        with pytest.raises(ValueError):
            SoftEdgeFormat(spPr).radius = -5

        assert _same_xml(spPr, "p:spPr/a:effectLst/a:softEdge{rad=12700}")


class DescribeEffectClearingRestoresInheritance(object):
    """Assigning None drops the element, and an effectLst that leaves empty."""

    def it_drops_the_outer_shadow_once_every_property_is_cleared(self):
        spPr, shadow = _effect("ShadowFormat")
        shadow.blur_radius = Emu(101600)
        shadow.distance = Emu(38100)
        shadow.direction = 45.0

        shadow.blur_radius = None
        shadow.distance = None
        assert spPr.effectLst.outerShdw is not None  # -- `dir` still explicit
        shadow.direction = None

        assert _same_xml(spPr, "p:spPr")

    def it_treats_an_explicit_plain_black_like_the_default_colour(self):
        # Indistinguishable in the XML from the colour the setters insert.
        spPr, shadow = _effect("ShadowFormat")
        shadow.blur_radius = Emu(101600)
        shadow.color.rgb = "000000"

        shadow.blur_radius = None

        assert _same_xml(spPr, "p:spPr")

    def but_it_keeps_a_shadow_that_carries_a_colour_the_caller_chose(self):
        spPr, shadow = _effect("ShadowFormat")
        shadow.blur_radius = Emu(101600)
        shadow.color.rgb = "000000"
        shadow.color.alpha = 0.35

        shadow.blur_radius = None

        assert _same_xml(
            spPr, "p:spPr/a:effectLst/a:outerShdw/a:srgbClr{val=000000}/a:alpha{val=35000}"
        )

    def and_color_None_clears_that_colour_too(self):
        spPr, shadow = _effect("ShadowFormat")
        shadow.blur_radius = Emu(101600)
        shadow.color.rgb = "FF0000"
        shadow.blur_radius = None

        shadow.color = None

        assert _same_xml(spPr, "p:spPr")

    def it_falls_back_to_the_default_colour_while_geometry_remains(self):
        spPr, shadow = _effect("ShadowFormat")
        shadow.blur_radius = Emu(101600)
        shadow.color.rgb = "FF0000"

        shadow.color = None

        assert _same_xml(
            spPr, "p:spPr/a:effectLst/a:outerShdw{blurRad=101600}/a:srgbClr{val=000000}"
        )

    def it_ignores_color_None_when_there_is_no_shadow(self):
        spPr, shadow = _effect("ShadowFormat")
        shadow.color = None
        assert _same_xml(spPr, "p:spPr")

    def it_keeps_an_attribute_it_does_not_expose(self):
        spPr = element(
            "p:spPr/a:effectLst/a:outerShdw{blurRad=5,rotWithShape=0}/a:srgbClr{val=000000}"
        )

        ShadowFormat(spPr).blur_radius = None

        assert _same_xml(
            spPr, "p:spPr/a:effectLst/a:outerShdw{rotWithShape=0}/a:srgbClr{val=000000}"
        )

    def it_drops_the_inner_shadow_once_every_property_is_cleared(self):
        spPr, inner = _effect("InnerShadowFormat")
        inner.distance = Emu(38100)
        inner.distance = None
        assert _same_xml(spPr, "p:spPr")

    def it_drops_the_glow_when_its_radius_is_cleared(self):
        spPr, glow = _effect("GlowFormat")
        glow.radius = Emu(76200)
        glow.radius = None
        assert _same_xml(spPr, "p:spPr")

    def but_it_keeps_a_glow_colour_the_caller_chose_until_it_is_cleared(self):
        spPr, glow = _effect("GlowFormat")
        glow.radius = Emu(76200)
        glow.color.rgb = "4F9DFF"

        glow.radius = None
        assert _same_xml(spPr, "p:spPr/a:effectLst/a:glow/a:srgbClr{val=4F9DFF}")

        glow.color = None
        assert _same_xml(spPr, "p:spPr")

    def it_drops_the_soft_edge_and_its_emptied_effectLst(self):
        spPr, soft = _effect("SoftEdgeFormat")
        soft.radius = Emu(38100)
        soft.radius = None
        assert _same_xml(spPr, "p:spPr")

    def it_resets_a_preset_shadow_colour_but_keeps_the_preset(self):
        spPr, preset = _effect("PresetShadowFormat")
        preset.preset = "shdw5"
        preset.color.rgb = "AABBCC"

        preset.color = None

        assert _same_xml(
            spPr, "p:spPr/a:effectLst/a:prstShdw{prst=shdw5}/a:srgbClr{val=000000}"
        )

    def it_keeps_the_effectLst_while_another_effect_lives_in_it(self):
        from power_pptx.dml.effect import SoftEdgeFormat

        spPr, shadow = _effect("ShadowFormat")
        SoftEdgeFormat(spPr).radius = Emu(12700)
        shadow.distance = Emu(38100)

        shadow.distance = None

        assert _same_xml(spPr, "p:spPr/a:effectLst/a:softEdge{rad=12700}")

    def it_leaves_an_effectLst_it_did_not_empty_alone(self):
        # `shadow.clear()` writes an empty list on purpose; a no-op `= None`
        # must not undo that.
        from power_pptx.dml.effect import GlowFormat

        spPr = element("p:spPr/a:effectLst")

        ShadowFormat(spPr).blur_radius = None
        GlowFormat(spPr).radius = None

        assert _same_xml(spPr, "p:spPr/a:effectLst")

    def it_restores_theme_inheritance_on_a_real_autoshape(self):
        shape = _autoshape()
        before = shape._element.xml
        shape.shadow.blur_radius = Emu(101600)
        shape.shadow.distance = Emu(38100)
        shape.shadow.direction = 45
        shape.glow.radius = Emu(50800)
        shape.inner_shadow.distance = Emu(50800)
        shape.soft_edges.radius = Emu(50800)
        shape.blur.radius = Emu(50800)
        shape.reflection.distance = Emu(50800)
        shape.preset_shadow.distance = Emu(50800)

        shape.shadow.blur_radius = None
        shape.shadow.distance = None
        shape.shadow.direction = None
        shape.glow.radius = None
        shape.inner_shadow.distance = None
        shape.soft_edges.radius = None
        shape.blur.radius = None
        shape.reflection.distance = None
        shape.preset_shadow.preset = None

        assert shape._element.xml == before
        # -- the theme's effect style is referenced again, untouched --
        assert _effect_ref_idx(shape) == "2"


def _deck_with_float_effects():
    """A deck whose every effect length came from float arithmetic."""
    from power_pptx.enum.dml import BevelPreset
    from power_pptx.util import Pt

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    sp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(3), Inches(1.5))
    sp.shadow.blur_radius = Pt(8) / 2
    sp.shadow.distance = Pt(8) * 0.5
    sp.glow.radius = Pt(6) / 2
    sp.soft_edges.radius = Pt(6) / 2
    sp.blur.radius = Pt(6) / 2
    sp.reflection.distance = Pt(6) / 2
    sp.inner_shadow.blur_radius = Pt(6) / 2
    sp.line.width = Pt(3) / 2
    sp.three_d.bevel_top.width = Pt(6) / 2
    sp.three_d.extrusion_height = Pt(6) / 2
    sp.three_d.contour_width = Pt(6) / 2

    # -- a second shape on which every assignment is rejected --
    bad = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(1), Inches(3), Inches(3), Inches(1.5))
    for proxy, prop, value in (
        (bad.soft_edges, "radius", -1),
        (bad.reflection, "start_alpha", 1.2),
        (bad.three_d.bevel_top, "width", -1),
        (bad.three_d.extrusion_color, "rgb", "nope"),
        (bad.glow, "radius", "wide"),
    ):
        with pytest.raises((TypeError, ValueError)):
            setattr(proxy, prop, value)

    # -- and a third on which everything is set, then cleared --
    gone = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(5), Inches(3), Inches(3), Inches(1.5))
    gone.shadow.blur_radius = Pt(4)
    gone.shadow.blur_radius = None
    gone.soft_edges.radius = Pt(4)
    gone.soft_edges.radius = None
    gone.three_d.bevel_top.preset = BevelPreset.CIRCLE
    gone.three_d.bevel_top.preset = None
    return prs


class DescribeFloatEffectLengthsInASavedDeck(object):
    def it_writes_whole_emu_for_float_lengths(self):
        prs = _deck_with_float_effects()
        sp = prs.slides[0].shapes[0]
        assert sp.shadow.blur_radius == Emu(50800)
        assert sp.glow.radius == Emu(38100)
        assert sp.line.width == Emu(19050)
        assert sp.three_d.bevel_top.width == Emu(38100)
        # -- no attribute anywhere under spPr holds a fractional number --
        assert not [
            v for el in sp._element.spPr.iter() for v in el.attrib.values() if "." in v
        ]

    def it_leaves_no_residue_from_rejected_or_cleared_assignments(self):
        shapes = _deck_with_float_effects().slides[0].shapes
        rejected, cleared = shapes[1]._element.spPr, shapes[2]._element.spPr
        assert rejected.effectLst is None
        assert rejected.scene3d is None
        assert rejected.sp3d is None
        assert cleared.effectLst is None
        # -- an empty <a:bevelT/> would render as the default circle bevel --
        assert cleared.sp3d.bevelT is None

    def it_is_schema_valid(self):
        import io

        from tests.schema.oxml_schema_validator import (
            iter_schema_violations,
            schema_validation_available,
        )

        if not schema_validation_available():
            pytest.skip("schema validation unavailable")

        buf = io.BytesIO()
        _deck_with_float_effects().save(buf)
        assert list(iter_schema_violations(buf.getvalue())) == []

    def it_round_trips(self):
        from tests.integration.round_trip import assert_round_trip

        assert_round_trip(_deck_with_float_effects())
