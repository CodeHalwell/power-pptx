"""Unit-test suite for `power_pptx.lint`."""

from __future__ import annotations

import io

import pytest

from power_pptx import Presentation
from power_pptx.dml.color import RGBColor
from power_pptx.lint import (
    LowContrast,
    MasterPlaceholderCollision,
    MinFontSize,
    OffGridDrift,
    ShapeCollision,
    ZOrderAnomaly,
    _LEGACY_LINT_GROUP_ATTR,
    _LINT_EXT_URI,
    _contrast_ratio,
    _find_lint_ext,
    _write_lint_group,
)
from power_pptx.util import Inches, Pt


def _new_blank_slide():
    prs = Presentation()
    # Layout 6 is "Blank" in the default template.
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    return prs, slide


def _add_overlapping_rects(slide, n=3):
    """Add `n` axis-aligned rectangles, each overlapping its neighbour by ~50%."""
    shapes = []
    for i in range(n):
        s = slide.shapes.add_shape(
            1,  # MSO_SHAPE.RECTANGLE
            Inches(1 + 0.5 * i),
            Inches(1 + 0.5 * i),
            Inches(2),
            Inches(2),
        )
        shapes.append(s)
    return shapes


def _collisions(slide):
    return [i for i in slide.lint().issues if isinstance(i, ShapeCollision)]


class DescribeShapeLintGroup:
    """Per-shape ``lint_group`` property."""

    def it_defaults_to_None(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        assert s.lint_group is None

    def it_round_trips_a_string_value(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.lint_group = "kpi-card-1"
        assert s.lint_group == "kpi-card-1"

    def it_persists_through_save_and_load(self):
        prs, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.lint_group = "kpi-card-1"
        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        prs2 = Presentation(buf)
        s2 = list(prs2.slides[0].shapes)[0]
        assert s2.lint_group == "kpi-card-1"

    def it_clears_when_set_to_None(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.lint_group = "kpi-card-1"
        s.lint_group = None
        assert s.lint_group is None
        cNvPr = s._element._nvXxPr.cNvPr
        assert _LEGACY_LINT_GROUP_ATTR not in cNvPr.attrib
        assert _find_lint_ext(cNvPr) is None

    def it_rejects_an_empty_string(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        with pytest.raises(ValueError):
            s.lint_group = ""

    def it_writes_metadata_via_extLst_not_a_custom_attribute(self):
        # Custom-namespaced *attributes* on cNvPr violate the OOXML schema
        # and trigger PowerPoint's "Repaired and removed" prompt; metadata
        # must live in an a:ext extension instead.
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.lint_group = "kpi-card-1"
        cNvPr = s._element._nvXxPr.cNvPr
        assert _LEGACY_LINT_GROUP_ATTR not in cNvPr.attrib
        ext = _find_lint_ext(cNvPr)
        assert ext is not None
        assert ext.get("uri") == _LINT_EXT_URI

    def it_reads_legacy_pre_2_1_1_attribute_layout(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        cNvPr = s._element._nvXxPr.cNvPr
        cNvPr.set(_LEGACY_LINT_GROUP_ATTR, "legacy-card")
        assert s.lint_group == "legacy-card"

    def it_migrates_legacy_attribute_to_extLst_on_write(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        cNvPr = s._element._nvXxPr.cNvPr
        cNvPr.set(_LEGACY_LINT_GROUP_ATTR, "legacy-card")
        s.lint_group = "kpi-card-1"
        assert _LEGACY_LINT_GROUP_ATTR not in cNvPr.attrib
        assert _find_lint_ext(cNvPr) is not None


class DescribeSlideLintGroupBatch:
    """``slide.lint_group(name, *shapes)`` batch tagger."""

    def it_tags_all_supplied_shapes(self):
        _, slide = _new_blank_slide()
        a, b, c = _add_overlapping_rects(slide, 3)
        slide.lint_group("kpi-card-1", a, b, c)
        assert (a.lint_group, b.lint_group, c.lint_group) == (
            "kpi-card-1",
            "kpi-card-1",
            "kpi-card-1",
        )

    def it_clears_all_supplied_shapes_when_name_is_None(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        slide.lint_group("kpi", a, b)
        slide.lint_group(None, a, b)
        assert a.lint_group is None and b.lint_group is None

    def it_accepts_zero_shapes_as_a_no_op(self):
        _, slide = _new_blank_slide()
        slide.lint_group("kpi-card-1")  # must not raise


class DescribeSlideDesignGroup:
    """``slide.design_group(name)`` context manager."""

    def it_auto_tags_shapes_added_in_the_block(self):
        _, slide = _new_blank_slide()
        with slide.design_group("kpi-card-1"):
            a = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(1), Inches(1))
            b = slide.shapes.add_shape(1, Inches(0), Inches(1), Inches(1), Inches(1))
        assert (a.lint_group, b.lint_group) == ("kpi-card-1", "kpi-card-1")

    def it_does_not_tag_shapes_added_outside_the_block(self):
        _, slide = _new_blank_slide()
        outside = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(1), Inches(1))
        with slide.design_group("kpi-card-1"):
            inside = slide.shapes.add_shape(1, Inches(0), Inches(1), Inches(1), Inches(1))
        after = slide.shapes.add_shape(1, Inches(0), Inches(2), Inches(1), Inches(1))
        assert outside.lint_group is None
        assert inside.lint_group == "kpi-card-1"
        assert after.lint_group is None

    def it_uses_the_innermost_label_when_nested(self):
        _, slide = _new_blank_slide()
        with slide.design_group("outer"):
            a = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(1), Inches(1))
            with slide.design_group("inner"):
                b = slide.shapes.add_shape(1, Inches(1), Inches(0), Inches(1), Inches(1))
            c = slide.shapes.add_shape(1, Inches(2), Inches(0), Inches(1), Inches(1))
        assert (a.lint_group, b.lint_group, c.lint_group) == ("outer", "inner", "outer")

    def it_does_not_overwrite_an_explicit_pre_set_group(self):
        _, slide = _new_blank_slide()
        with slide.design_group("auto"):
            a = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(1), Inches(1))
            a.lint_group = "manual"
        assert a.lint_group == "manual"

    def it_rejects_an_empty_or_None_name(self):
        _, slide = _new_blank_slide()
        with pytest.raises(ValueError):
            with slide.design_group(""):
                pass
        with pytest.raises(ValueError):
            with slide.design_group(None):  # type: ignore[arg-type]
                pass


class DescribeCollisionGroupSuppression:
    """``ShapeCollision`` lint check honors ``lint_group``."""

    def it_suppresses_collisions_inside_a_single_group(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        # baseline: a vs b collides
        assert len(_collisions(slide)) == 1
        slide.lint_group("kpi-card-1", a, b)
        assert _collisions(slide) == []

    def it_still_warns_across_different_groups(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        slide.lint_group("card-A", a)
        slide.lint_group("card-B", b)
        assert len(_collisions(slide)) == 1

    def it_still_warns_when_only_one_shape_is_grouped(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        slide.lint_group("card-A", a)
        # b is left untagged
        assert len(_collisions(slide)) == 1

    def it_suppresses_only_the_intra_group_pair(self):
        _, slide = _new_blank_slide()
        a, b, c = _add_overlapping_rects(slide, 3)
        # All three currently collide pairwise (3 collisions).
        assert len(_collisions(slide)) == 3
        # Tag a+b together; c stays untagged.
        slide.lint_group("kpi-card-1", a, b)
        # Only a/c and b/c remain.
        remaining = _collisions(slide)
        assert len(remaining) == 2
        pairs = {tuple(sorted((i.shapes[0].name, i.shapes[1].name))) for i in remaining}
        assert pairs == {
            tuple(sorted((a.name, c.name))),
            tuple(sorted((b.name, c.name))),
        }

    def it_works_end_to_end_with_design_group(self):
        _, slide = _new_blank_slide()
        with slide.design_group("kpi-card-1"):
            slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
            slide.shapes.add_shape(1, Inches(1.5), Inches(1.5), Inches(2), Inches(2))
        assert _collisions(slide) == []

    def it_exposes_each_shapes_lint_group_on_the_collision(self):
        # Triage hint: a ShapeCollision between two differently-grouped
        # shapes is "genuine layout bug"; one between an untagged and a
        # tagged shape is "I forgot to tag this".  Surface the groups so
        # callers can tell at a glance from report.summary().
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        slide.lint_group("card-A", a)
        slide.lint_group("card-B", b)
        c = _collisions(slide)
        assert len(c) == 1
        assert c[0].groups == ("card-A", "card-B")

    def it_reports_None_for_an_untagged_shape_in_the_groups_pair(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        slide.lint_group("card-A", a)
        c = _collisions(slide)
        assert len(c) == 1
        assert c[0].groups == ("card-A", None)


class DescribeShapeLintSkip:
    """Per-shape ``lint_skip`` opt-out for individual checks."""

    def it_defaults_to_an_empty_set(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        assert s.lint_skip == frozenset()

    def it_round_trips_a_set_of_codes(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.lint_skip = {"MinFontSize", "TextOverflow"}
        assert s.lint_skip == frozenset({"MinFontSize", "TextOverflow"})

    def it_persists_through_save_and_load(self):
        prs, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.lint_skip = {"MinFontSize"}
        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        prs2 = Presentation(buf)
        s2 = list(prs2.slides[0].shapes)[0]
        assert s2.lint_skip == frozenset({"MinFontSize"})

    def it_clears_when_set_to_an_empty_set(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.lint_skip = {"MinFontSize"}
        s.lint_skip = set()
        assert s.lint_skip == frozenset()

    def it_suppresses_a_per_shape_min_font_size_warning(self):
        _, slide = _new_blank_slide()
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
        tb.text_frame.paragraphs[0].text = "tiny"
        tb.text_frame.paragraphs[0].runs[0].font.size = Pt(7)
        # Baseline: warning fires.
        assert any(
            i.code == "MinFontSize" for i in slide.lint().issues
        )
        # Opt-out silences it.
        tb.lint_skip = {"MinFontSize"}
        assert not any(
            i.code == "MinFontSize" for i in slide.lint().issues
        )

    def it_keeps_collisions_when_only_one_shape_opts_out(self):
        # Cross-shape issues only drop when *both* shapes opt out.
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.lint_skip = {"ShapeCollision"}
        assert len(_collisions(slide)) == 1
        b.lint_skip = {"ShapeCollision"}
        assert _collisions(slide) == []


class DescribeMinFontSize:
    def it_flags_a_run_below_threshold(self):
        _, slide = _new_blank_slide()
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
        tb.text_frame.paragraphs[0].text = "tiny"
        tb.text_frame.paragraphs[0].runs[0].font.size = Pt(7)
        issues = [i for i in slide.lint().issues if isinstance(i, MinFontSize)]
        assert len(issues) == 1
        assert issues[0].pt == 7.0
        assert issues[0].threshold_pt == 9.0

    def it_does_not_flag_at_threshold(self):
        _, slide = _new_blank_slide()
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
        tb.text_frame.paragraphs[0].text = "fine"
        tb.text_frame.paragraphs[0].runs[0].font.size = Pt(9)
        assert [i for i in slide.lint().issues if isinstance(i, MinFontSize)] == []

    def it_skips_shapes_without_text(self):
        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(1), Inches(1))
        assert [i for i in slide.lint().issues if isinstance(i, MinFontSize)] == []


class DescribeOffGridDrift:
    def _column_with_drift(self):
        _, slide = _new_blank_slide()
        # Four shapes at exactly Inches(6).
        for i in range(4):
            slide.shapes.add_shape(
                1, Inches(6), Inches(0.5 + i * 1.0), Inches(1), Inches(0.5)
            )
        # One drift offender ~0.033" off the column.
        drift = slide.shapes.add_shape(
            1, Inches(6) + 30000, Inches(5), Inches(1), Inches(0.5)
        )
        return slide, drift

    def it_flags_a_shape_off_a_dominant_column(self):
        slide, drift = self._column_with_drift()
        issues = [i for i in slide.lint().issues if isinstance(i, OffGridDrift)]
        # Shape proxies compare by underlying element, not identity.
        assert any(
            i.shapes[0] == drift and i.axis == "left" for i in issues
        )

    def it_does_not_flag_shapes_when_there_are_no_3plus_clusters(self):
        _, slide = _new_blank_slide()
        # Just two shapes — no grid line is strong enough.
        slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(1), Inches(1))
        slide.shapes.add_shape(1, Inches(1) + 30000, Inches(2), Inches(1), Inches(1))
        assert [i for i in slide.lint().issues if isinstance(i, OffGridDrift)] == []

    def it_can_auto_fix_by_snapping_to_the_grid(self):
        slide, drift = self._column_with_drift()
        before = int(drift.left)
        report = slide.lint()
        fixes = report.auto_fix()
        assert any("Snapped" in f for f in fixes)
        assert int(drift.left) == int(Inches(6))
        # And the issue is gone on a fresh lint pass.
        assert [
            i for i in slide.lint().issues if isinstance(i, OffGridDrift)
        ] == []
        assert before != int(drift.left)

    def it_refreshes_report_issues_after_auto_fix(self):
        # ``report.auto_fix(); report.issues`` should reflect the post-fix
        # state — no second ``slide.lint()`` pass required.
        slide, drift = self._column_with_drift()
        report = slide.lint()
        assert any(isinstance(i, OffGridDrift) for i in report.issues)
        report.auto_fix()
        assert [i for i in report.issues if isinstance(i, OffGridDrift)] == []

    def it_does_not_refresh_report_issues_on_dry_run(self):
        slide, _ = self._column_with_drift()
        report = slide.lint()
        before = list(report.issues)
        report.auto_fix(dry_run=True)
        assert report.issues == before


class DescribeLowContrast:
    def it_computes_wcag_contrast_ratio(self):
        # Black on white is 21:1.
        ratio = _contrast_ratio(RGBColor(0, 0, 0), RGBColor(255, 255, 255))
        assert ratio == pytest.approx(21.0, rel=0.01)
        # Yellow on white is awful.
        ratio = _contrast_ratio(RGBColor(0xFF, 0xFF, 0x00), RGBColor(0xFF, 0xFF, 0xFF))
        assert ratio < 2.0

    def it_flags_low_contrast_text_on_filled_shape(self):
        _, slide = _new_blank_slide()
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
        tb.text_frame.paragraphs[0].text = "low"
        tb.text_frame.paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0x00)
        tb.fill.solid()
        tb.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        issues = [i for i in slide.lint().issues if isinstance(i, LowContrast)]
        assert len(issues) == 1
        assert issues[0].ratio < 4.5

    def it_does_not_flag_high_contrast(self):
        _, slide = _new_blank_slide()
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
        tb.text_frame.paragraphs[0].text = "fine"
        tb.text_frame.paragraphs[0].runs[0].font.color.rgb = RGBColor(0, 0, 0)
        tb.fill.solid()
        tb.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        assert [i for i in slide.lint().issues if isinstance(i, LowContrast)] == []

    def it_skips_silently_when_color_is_unresolvable(self):
        # Theme color text on default fill — both unresolvable to RGB without
        # walking the theme. We just want no false positives.
        _, slide = _new_blank_slide()
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
        tb.text_frame.paragraphs[0].text = "theme color"
        # Don't set explicit colors -> nothing resolvable.
        assert [i for i in slide.lint().issues if isinstance(i, LowContrast)] == []


class DescribeZOrderAnomaly:
    def it_flags_a_filled_shape_drawn_above_a_contained_shape(self):
        _, slide = _new_blank_slide()
        # Add the small textbox first, then a big filled rect that covers it.
        small = slide.shapes.add_textbox(Inches(2), Inches(2), Inches(1), Inches(1))
        small.text_frame.text = "hidden"
        big = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(4), Inches(4))
        big.fill.solid()
        big.fill.fore_color.rgb = RGBColor(0, 0, 255)
        issues = [i for i in slide.lint().issues if isinstance(i, ZOrderAnomaly)]
        assert any(
            i.shapes[0] == big and i.shapes[1] == small for i in issues
        )

    def it_does_not_flag_when_container_is_drawn_first(self):
        _, slide = _new_blank_slide()
        # Big rect first (drawn underneath); textbox added second (on top).
        big = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(4), Inches(4))
        big.fill.solid()
        big.fill.fore_color.rgb = RGBColor(0, 0, 255)
        slide.shapes.add_textbox(Inches(2), Inches(2), Inches(1), Inches(1))
        assert [i for i in slide.lint().issues if isinstance(i, ZOrderAnomaly)] == []

    def it_does_not_flag_unfilled_containers(self):
        _, slide = _new_blank_slide()
        small = slide.shapes.add_textbox(Inches(2), Inches(2), Inches(1), Inches(1))
        small.text_frame.text = "visible"
        # No fill on the big rect.
        slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(4), Inches(4))
        assert [i for i in slide.lint().issues if isinstance(i, ZOrderAnomaly)] == []


class DescribeMasterPlaceholderCollision:
    def it_flags_a_textbox_at_the_position_of_an_unused_layout_placeholder(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[1])  # Title and Content
        # Drop the title placeholder so its idx becomes "unused" on this slide.
        title = slide.placeholders[0]
        title._element.getparent().remove(title._element)
        # Add a textbox at exactly the placeholder position.
        layout_title = list(slide.slide_layout.placeholders)[0]
        slide.shapes.add_textbox(
            layout_title.left,
            layout_title.top,
            layout_title.width,
            layout_title.height,
        )
        issues = [
            i for i in slide.lint().issues
            if isinstance(i, MasterPlaceholderCollision)
        ]
        assert len(issues) == 1
        assert issues[0].placeholder_idx == 0

    def it_does_not_flag_a_normally_inherited_placeholder(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        # Slide already inherits the title; no extra textbox added.
        assert [
            i for i in slide.lint().issues
            if isinstance(i, MasterPlaceholderCollision)
        ] == []


class DescribeReportSummary:
    def it_lists_no_issues_when_clean(self):
        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(1), Inches(1))
        assert slide.lint().summary() == "No issues found."
