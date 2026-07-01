"""Integration tests for the new chart / animation / theme APIs."""

from __future__ import annotations

import glob
import io
import os

import pytest

from power_pptx import Presentation
from power_pptx.chart.data import CategoryChartData
from power_pptx.chart.quick_layouts import apply_quick_layout
from power_pptx.dml.color import RGBColor
from power_pptx.enum.chart import XL_CHART_TYPE
from power_pptx.enum.dml import MSO_THEME_COLOR
from power_pptx.util import Inches


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------


def _new_chart(chart_type=XL_CHART_TYPE.COLUMN_STACKED):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    data = CategoryChartData()
    data.categories = ["A", "B", "C"]
    data.add_series("S1", (1.0, 2.0, 3.0))
    data.add_series("S2", (4.0, 5.0, 6.0))
    gf = slide.shapes.add_chart(
        chart_type, Inches(1), Inches(1), Inches(6), Inches(4), data
    )
    return prs, slide, gf, gf.chart


class DescribeQuickLayoutOverrides:
    def it_overrides_a_named_preset_with_keyword_args(self):
        _, _, _, chart = _new_chart()
        chart.apply_quick_layout("title_legend_right", title_text="Q4 ARR")
        assert chart.has_title
        assert chart.chart_title.text_frame.text == "Q4 ARR"

    def it_supports_value_axis_overrides(self):
        _, _, _, chart = _new_chart()
        chart.apply_quick_layout(
            "title_axes_legend_bottom",
            value_axis_title_text="Revenue (£m)",
            has_major_gridlines=False,
        )
        # value-axis title was set; gridlines were forced off.
        assert not chart.value_axis.has_major_gridlines

    def it_rejects_unknown_override_keys(self):
        _, _, _, chart = _new_chart()
        with pytest.raises(TypeError):
            apply_quick_layout(chart, "title_legend_right", bogus_key=True)


class DescribeColorByCategory:
    def it_recolors_each_data_point_in_each_series(self):
        _, _, _, chart = _new_chart()
        chart.color_by_category(["#FF0000", "#00FF00", "#0000FF"])
        # Each (series, category) cell now has a <c:dPt> child with a
        # solid fill — count dPt elements anywhere in the chart XML.
        import lxml.etree as etree
        xml = etree.tostring(chart._chartSpace).decode()
        # 2 series × 3 categories = 6 dPt elements minimum.
        assert xml.count("<c:dPt") >= 6 or xml.count(":dPt") >= 6


class DescribeNumberFormatStillWorks:
    """Sanity: `number_format` was already there and we didn't break it."""

    def it_sets_value_axis_number_format(self):
        _, _, _, chart = _new_chart()
        chart.value_axis.tick_labels.number_format = "£#,##0"
        assert chart.value_axis.tick_labels.number_format == "£#,##0"


# ---------------------------------------------------------------------------
# Animations
# ---------------------------------------------------------------------------


class DescribeTypewriter:
    def it_chains_entrance_animations_across_shapes(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        s1 = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        s2 = slide.shapes.add_shape(1, Inches(1), Inches(2.5), Inches(2), Inches(1))
        s3 = slide.shapes.add_shape(1, Inches(1), Inches(4), Inches(2), Inches(1))
        slide.animations.typewriter([s1, s2, s3], delay_between_ms=200)
        # Three top-level animation pars (one per shape).
        pars = slide._element.xpath(
            "p:timing/p:tnLst/p:par/p:cTn/p:childTnLst/p:par"
        )
        assert len(pars) == 3

    def it_is_a_no_op_on_empty_input(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.animations.typewriter([])
        # No timing tree should have been created.
        assert slide._element.xpath("p:timing") == [] or len(
            slide._element.xpath("p:timing/p:tnLst/p:par/p:cTn/p:childTnLst/p:par")
        ) == 0


class DescribeEasing:
    def it_stamps_accel_decel_on_animation_cTn(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        sh = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        slide.animations.add_entrance("fade", sh, easing="ease_in_out")
        accels = slide._element.xpath("//@accel")
        assert any(a == "30000" for a in accels)
        decels = slide._element.xpath("//@decel")
        assert any(d == "30000" for d in decels)

    def it_accepts_an_explicit_accel_decel_tuple(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        sh = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        slide.animations.add_entrance("fade", sh, easing=(0.4, 0.2))
        accels = slide._element.xpath("//@accel")
        assert any(a == "40000" for a in accels)

    def it_rejects_unknown_preset(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        sh = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        with pytest.raises(ValueError):
            slide.animations.add_entrance("fade", sh, easing="bouncy")

    def it_rejects_invalid_tuple(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        sh = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        with pytest.raises(ValueError):
            slide.animations.add_entrance("fade", sh, easing=(0.7, 0.7))


class DescribeOrphanCleanup:
    def it_removes_animation_entries_for_deleted_shape(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        s1 = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        s2 = slide.shapes.add_shape(1, Inches(1), Inches(2.5), Inches(2), Inches(1))
        slide.animations.typewriter([s1, s2])
        before = len(
            slide._element.xpath(
                "p:timing/p:tnLst/p:par/p:cTn/p:childTnLst/p:par"
            )
        )
        s1.delete()
        after = len(
            slide._element.xpath(
                "p:timing/p:tnLst/p:par/p:cTn/p:childTnLst/p:par"
            )
        )
        assert after == before - 1

    def it_can_be_invoked_explicitly_via_purge_orphans(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        s1 = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        slide.animations.add_entrance("fade", s1)
        # Manually detach the shape (no orphan cleanup).
        s1._element.getparent().remove(s1._element)
        purged = slide.animations.purge_orphans()
        assert purged == 1


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------


class DescribeThemeApplyRebind:
    def it_rebinds_literal_RGB_to_a_theme_slot_after_apply(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        old_accent = prs.theme.colors[MSO_THEME_COLOR.ACCENT_1]
        sh = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        sh.fill.solid()
        sh.fill.fore_color.rgb = old_accent

        new_prs = Presentation()
        new_prs.theme.colors[MSO_THEME_COLOR.ACCENT_1] = RGBColor(0xFF, 0x00, 0x00)
        n = prs.theme.apply(
            new_prs.theme, rebind_shape_colors=True, presentation=prs
        )
        assert n == 1

    def it_requires_presentation_when_rebind_is_set(self):
        prs = Presentation()
        with pytest.raises(ValueError):
            prs.theme.apply(prs.theme, rebind_shape_colors=True)

    def it_returns_zero_when_rebind_is_off(self):
        prs = Presentation()
        new_prs = Presentation()
        n = prs.theme.apply(new_prs.theme)
        assert n == 0


class DescribeColorVariant:
    def it_is_light_for_a_fresh_slide(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        assert slide.color_variant == "light"

    def it_can_set_dark_variant(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.color_variant = "dark"
        assert slide.color_variant == "dark"

    def it_round_trips_dark_variant_through_save_load(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.color_variant = "dark"
        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        prs2 = Presentation(buf)
        assert prs2.slides[0].color_variant == "dark"

    def it_rejects_unknown_variants(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        with pytest.raises(ValueError):
            slide.color_variant = "neon"

    def it_supports_set_clr_map_override_for_arbitrary_mappings(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.set_clr_map_override(bg1="dk2", tx1="lt2")
        # color_variant returns None for non-standard overrides.
        assert slide.color_variant is None


class DescribeEmbedFont:
    def it_embeds_a_TTF_into_the_presentation(self):
        # Find any system TTF for the test.
        candidates = (
            glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
            + glob.glob("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        )
        candidates = [p for p in candidates if os.path.isfile(p)]
        if not candidates:
            pytest.skip("no system TTF found to embed")
        font_path = candidates[0]

        prs = Presentation()
        prs.theme.embed_font(prs, font_path, typeface="EmbeddedTest", weight="regular")

        # Round-trip: presentation.xml should now contain an
        # <p:embeddedFontLst> with a <p:embeddedFont> registered for our
        # typeface.
        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        prs2 = Presentation(buf)
        import lxml.etree as etree
        xml = etree.tostring(prs2._element).decode()
        assert "embeddedFontLst" in xml
        assert "EmbeddedTest" in xml

    def it_orders_weight_slots_by_schema_sequence(self):
        # CT_EmbeddedFontListEntry is a fixed sequence (font, regular, bold,
        # italic, boldItalic).  Adding weights out of order must still produce
        # schema-ordered children, not the call order.
        from power_pptx.oxml import parse_xml
        from power_pptx.oxml.ns import qn
        from power_pptx.theme import _add_embedded_font_entry

        pres = parse_xml(
            b'<p:presentation '
            b'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
            b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
        )

        class _Wrap:
            _element = pres

        for weight, rId in [
            ("italic", "rId1"),
            ("boldItalic", "rId2"),
            ("bold", "rId3"),
            ("regular", "rId4"),
        ]:
            _add_embedded_font_entry(_Wrap, "Inter", weight, rId)

        ef = pres.find(qn("p:embeddedFontLst")).find(qn("p:embeddedFont"))
        order = [child.tag.rsplit("}", 1)[-1] for child in ef]
        assert order == ["font", "regular", "bold", "italic", "boldItalic"]

    def it_places_embeddedFontLst_before_defaultTextStyle(self):
        # CT_Presentation requires embeddedFontLst to precede defaultTextStyle,
        # which every default template already carries.  A bare append put the
        # font list *after* it and produced a presentation.xml PowerPoint
        # reports as broken.
        from lxml import etree

        from power_pptx.oxml.ns import qn

        candidates = [
            p
            for p in glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
            if os.path.isfile(p)
        ]
        if not candidates:
            pytest.skip("no system TTF found to embed")

        prs = Presentation()
        prs.theme.embed_font(prs, candidates[0], typeface="OrderTest", weight="regular")

        pres_elm = prs.part.presentation._element
        children = [etree.QName(c).localname for c in pres_elm]
        assert "embeddedFontLst" in children
        # defaultTextStyle is present in the default template; the font list
        # must come strictly before it.
        assert children.index("embeddedFontLst") < children.index("defaultTextStyle")

    def it_rejects_invalid_weight(self):
        prs = Presentation()
        with pytest.raises(ValueError):
            prs.theme.embed_font(prs, "/dev/null", typeface="X", weight="bogus")

    def it_rejects_missing_file(self):
        prs = Presentation()
        with pytest.raises(FileNotFoundError):
            prs.theme.embed_font(
                prs, "/path/that/definitely/does/not/exist.ttf",
                typeface="X", weight="regular",
            )
