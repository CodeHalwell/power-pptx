"""Unit-test suite for `power_pptx.lint`."""

from __future__ import annotations

import io
import math
import os
import random

import pytest

from power_pptx import Presentation
from power_pptx.dml.color import RGBColor
from power_pptx.enum.text import MSO_AUTO_SIZE
from power_pptx.lint import (
    LayerOrderViolation,
    LintSeverity,
    LowContrast,
    MasterPlaceholderCollision,
    MinFontSize,
    OffGridDrift,
    OffSlide,
    OffSlideShadow,
    ShapeCollision,
    ShapeCollisionShadow,
    SlideLintReport,
    TextOverflow,
    ZOrderAnomaly,
    _LEGACY_LINT_GROUP_ATTR,
    _LINT_EXT_URI,
    _contrast_ratio,
    _find_lint_ext,
    _write_lint_group,
)
from power_pptx.util import Emu, Inches, Pt


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

    def it_accepts_empty_string_as_opt_out_of_implicit_groups(self):
        # Empty-string is now a sentinel that overrides the implicit
        # name-prefix grouping (see DescribeNamePrefixGroups) — round-trip
        # the value verbatim rather than rejecting it.
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.lint_group = ""
        assert s.lint_group == ""

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

    def it_preserves_lint_skip_when_clearing_lint_group(self):
        # P1 regression: ``lint_group = None`` must not wipe co-located
        # ``lint_skip`` codes.  Both live under the same ``<a:ext>`` block,
        # so the clear must remove only the ``<pp:lintGroup>`` node and
        # leave any sibling ``<pp:lintSkip>`` intact.
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.lint_group = "card-1"
        s.lint_skip = {"MinFontSize"}
        s.lint_group = None
        assert s.lint_group is None
        assert s.lint_skip == frozenset({"MinFontSize"})


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

    def it_tags_exactly_the_shapes_added_when_no_references_are_kept(self):
        # Shapes created and dropped without being held in a variable, on a
        # layout whose placeholders already sit in the tree: the identity of
        # each shape must not depend on Python object addresses.
        import gc

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[1])  # Title and Content
        slide.shapes.title.text = "Q4 Review"
        gc.collect()
        for n in (1, 2):
            with slide.design_group(f"kpi-card-{n}"):
                slide.shapes.add_shape(5, Inches(n * 3), Inches(2), Inches(2), Inches(2))
                slide.shapes.add_shape(1, Inches(n * 3), Inches(2), Inches(2), Inches(0.1))
                slide.shapes.add_textbox(Inches(n * 3), Inches(2.5), Inches(2), Inches(1))
            gc.collect()

        tags = [shape.lint_group for shape in slide.shapes]

        assert tags == [None, None] + ["kpi-card-1"] * 3 + ["kpi-card-2"] * 3

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

    def it_preserves_lint_group_when_lint_skip_changes(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.lint_group = "card-1"
        s.lint_skip = {"MinFontSize"}
        # Mutating lint_skip mustn't disturb lint_group, and vice versa.
        s.lint_skip = {"TextOverflow"}
        assert s.lint_group == "card-1"
        s.lint_skip = set()
        assert s.lint_group == "card-1"

    def it_rejects_empty_or_comma_containing_codes(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        with pytest.raises(ValueError):
            s.lint_skip = {""}
        with pytest.raises(ValueError):
            s.lint_skip = {"   "}
        with pytest.raises(ValueError):
            s.lint_skip = {"foo,bar"}

    def it_rejects_non_string_codes(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        with pytest.raises(TypeError):
            s.lint_skip = {None}  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            s.lint_skip = {42}  # type: ignore[arg-type]

    def it_strips_whitespace_around_codes(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.lint_skip = {"  MinFontSize  "}
        assert s.lint_skip == frozenset({"MinFontSize"})

    def it_migrates_legacy_attribute_on_lint_skip_write(self):
        # P2 regression: decks saved with 2.1.0 carry a custom-namespace
        # attribute on cNvPr.  Touching only ``lint_skip`` (without ever
        # setting ``lint_group``) must still strip that legacy attribute,
        # otherwise the schema-invalid XML survives the round-trip and
        # PowerPoint keeps "repairing" the file.
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        cNvPr = s._element._nvXxPr.cNvPr
        cNvPr.set(_LEGACY_LINT_GROUP_ATTR, "card-1")
        s.lint_skip = {"MinFontSize"}
        assert _LEGACY_LINT_GROUP_ATTR not in cNvPr.attrib

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
        # One drift offender ~0.07" off the column — must exceed the
        # tight tolerance (0.05" after IMPROVEMENT_PLAN.md item 10) but
        # stay under the loose tolerance (0.10").
        drift = slide.shapes.add_shape(
            1, Inches(6) + 64000, Inches(5), Inches(1), Inches(0.5)
        )
        return slide, drift

    def it_flags_a_shape_off_a_dominant_column(self):
        slide, drift = self._column_with_drift()
        issues = [i for i in slide.lint().issues if isinstance(i, OffGridDrift)]
        # Shape proxies compare by underlying element, not identity.
        assert any(
            i.shapes[0] == drift and i.axis == "left" for i in issues
        )

    def it_does_not_flag_small_drift_within_tight_tolerance(self):
        # Regression for IMPROVEMENT_PLAN.md item 10: a drift of ~0.033"
        # (e.g. Inches(0.6) divider vs Inches(0.62) eyebrow) should be
        # tolerated.  Before the tolerance change this lit up a warning
        # on basically every section header.
        _, slide = _new_blank_slide()
        for i in range(4):
            slide.shapes.add_shape(
                1, Inches(0.6), Inches(0.5 + i * 1.0), Inches(1), Inches(0.5)
            )
        # 0.02" off the column — well inside the new 0.05" tolerance.
        slide.shapes.add_shape(
            1, Inches(0.62), Inches(5), Inches(1), Inches(0.5)
        )
        assert [
            i for i in slide.lint().issues if isinstance(i, OffGridDrift)
        ] == []

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
        fixes = report.auto_fix(fix_grid_drift=True)
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
        report.auto_fix(fix_grid_drift=True)
        assert [i for i in report.issues if isinstance(i, OffGridDrift)] == []

    def it_does_not_refresh_report_issues_on_dry_run(self):
        slide, _ = self._column_with_drift()
        report = slide.lint()
        before = list(report.issues)
        report.auto_fix(dry_run=True)
        assert report.issues == before


class DescribeSetParagraphDefaults:
    """Regression tests for IMPROVEMENT_PLAN.md item 8 + PR #27 review."""

    def it_does_not_crash_on_runs_with_an_explicit_theme_color(self):
        # Regression for codex review on PR #27: reading
        # ``font.color.rgb`` to decide whether a run is unset crashes
        # with ``AttributeError`` for runs that have an explicit
        # non-RGB colour (e.g. ``theme_color``).  ``set_paragraph_defaults``
        # must use ``font.color.type`` as the "is anything set?" probe
        # so mixed-format text frames work.
        from power_pptx.dml.color import RGBColor
        from power_pptx.enum.dml import MSO_THEME_COLOR
        from power_pptx.util import Pt

        _, slide = _new_blank_slide()
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(2))
        tf = box.text_frame
        tf.text = "themed\nplain"
        # First run has an explicit theme colour; second is unset.
        tf.paragraphs[0].runs[0].font.color.theme_color = MSO_THEME_COLOR.ACCENT_1

        # No exception.
        tf.set_paragraph_defaults(font_name="Inter", size=Pt(14), color="#222222")

        # Theme colour preserved on run 0.
        assert (
            tf.paragraphs[0].runs[0].font.color.theme_color
            == MSO_THEME_COLOR.ACCENT_1
        )
        # Default colour applied on the unset run.
        assert tf.paragraphs[1].runs[0].font.color.rgb == RGBColor(
            0x22, 0x22, 0x22
        )
        # And the font name was filled in everywhere.
        assert tf.paragraphs[0].runs[0].font.name == "Inter"
        assert tf.paragraphs[1].runs[0].font.name == "Inter"


class DescribeAutoFixTextOverflow:
    """Regression tests for IMPROVEMENT_PLAN.md item 4.

    Before this change, ``auto_fix()`` only handled ``OffSlide`` and
    ``OffGridDrift``; ``TextOverflow`` was the most common runtime issue
    when generating decks from dynamic input but the linter detected and
    refused to act.  ``auto_fix()`` now flips the offending text frame's
    auto-size to ``MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE`` so PowerPoint
    shrinks the runs at render time.
    """

    def _overflowing_textbox(self):
        from power_pptx.enum.shapes import MSO_SHAPE
        from power_pptx.enum.text import MSO_AUTO_SIZE
        from power_pptx.lint import TextOverflow

        _, slide = _new_blank_slide()
        # 1.5" × 0.4" rectangle with ~80 chars at 18pt — way too much.
        # Autoshapes default to auto_size=None (NONE), unlike add_textbox
        # which defaults to SHAPE_TO_FIT_TEXT and would silence the lint.
        box = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(1.5), Inches(0.4)
        )
        box.text_frame.text = (
            "This is a deliberately long string that will not fit "
            "in this tiny one-inch wide badge text frame."
        )
        # Sanity check: the linter should flag this.
        issues = slide.lint().issues
        assert any(isinstance(i, TextOverflow) for i in issues)
        # And the shape should not yet have auto_size set.
        assert box.text_frame.auto_size in (None, MSO_AUTO_SIZE.NONE)
        return slide, box

    def it_flips_auto_size_to_TEXT_TO_FIT_SHAPE(self):
        from power_pptx.enum.text import MSO_AUTO_SIZE
        from power_pptx.lint import TextOverflow

        slide, box = self._overflowing_textbox()
        report = slide.lint()
        fixes = report.auto_fix()

        assert any("TEXT_TO_FIT_SHAPE" in f for f in fixes)
        assert box.text_frame.auto_size == MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        # And the issue is gone after the fix.
        assert [
            i for i in report.issues if isinstance(i, TextOverflow)
        ] == []

    def it_skips_frames_that_already_set_auto_size(self):
        from power_pptx.enum.text import MSO_AUTO_SIZE

        slide, box = self._overflowing_textbox()
        # Capture the report while auto_size is still NONE so the report
        # contains the TextOverflow.  Then flip auto_size to
        # SHAPE_TO_FIT_TEXT manually before running auto_fix to prove
        # that the fixer respects an explicit per-frame choice.
        before = slide.lint()
        box.text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT

        fixes = before.auto_fix()

        assert not any("TEXT_TO_FIT_SHAPE" in f for f in fixes)
        # The explicit author choice is preserved verbatim.
        assert box.text_frame.auto_size == MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT

    def it_supports_dry_run(self):
        from power_pptx.enum.text import MSO_AUTO_SIZE

        slide, box = self._overflowing_textbox()
        report = slide.lint()

        fixes = report.auto_fix(dry_run=True)

        assert any("TEXT_TO_FIT_SHAPE" in f for f in fixes)
        # Nothing should have been mutated.
        assert box.text_frame.auto_size in (None, MSO_AUTO_SIZE.NONE)


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


class DescribeShapeCollisionScoring:
    """Structural-vs-incidental scoring on ``ShapeCollision``."""

    def it_auto_suppresses_a_card_on_panel_layered_design(self):
        # Big panel, small card fully inside it, smaller drawn on top.
        # IMPROVEMENT_PLAN.md item 12: this is the canonical
        # layered-design pattern (badge-on-card, eyebrow-over-rectangle,
        # accent-bar-on-card) and is auto-suppressed entirely — not
        # even an INFO issue lands in the report.
        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(5), Inches(5))
        slide.shapes.add_shape(1, Inches(2), Inches(2), Inches(1), Inches(1))
        assert _collisions(slide) == []

    def it_classifies_two_partially_overlapping_peers_as_partial_WARNING(self):
        # Two same-size rectangles partially overlapping, neither contains
        # the other.
        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        slide.shapes.add_shape(1, Inches(1.5), Inches(1.5), Inches(2), Inches(2))
        cs = _collisions(slide)
        assert len(cs) == 1
        assert cs[0].kind == "partial"
        assert cs[0].severity == LintSeverity.WARNING

    def it_classifies_near_identical_bboxes_as_matched_INFO(self):
        # Two rectangles at the same place — almost always intentional
        # visual layering (badge + number, button + label).  The kind
        # stays ``matched`` so callers who really want to flag duplicates
        # can filter on it, but the severity is INFO so ``has_errors``
        # / CI pipelines aren't flooded by the common case.
        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        cs = _collisions(slide)
        assert len(cs) == 1
        assert cs[0].kind == "matched"
        assert cs[0].severity == LintSeverity.INFO
        assert cs[0].score >= 0.85

    def it_runs_group_suppression_before_scoring(self):
        # A grouped pair must never be scored — the ``score`` /
        # ``kind`` fields are meaningless for an intentional layered
        # group, so the issue is dropped entirely.
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        slide.lint_group("kpi-card-1", a, b)
        assert _collisions(slide) == []

    def it_includes_kind_and_score_in_summary_output(self):
        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        slide.shapes.add_shape(1, Inches(1.5), Inches(1.5), Inches(2), Inches(2))
        summary = slide.lint().summary()
        assert "kind=" in summary
        assert "score=" in summary


class DescribeEffectBleedGeometry:
    """Opt-in effect-bleed-aware geometry on OffSlide / ShapeCollision."""

    def _slide_dims(self, slide):
        return (
            slide.part.package.presentation_part.presentation.slide_width,
            slide.part.package.presentation_part.presentation.slide_height,
        )

    def it_does_not_fire_off_slide_when_bleed_disabled(self):
        # Shape sits flush against the right edge; shadow blur extends
        # past the slide.  Without the flag the linter only sees the
        # raw bbox and stays quiet.
        _, slide = _new_blank_slide()
        slide_w, _slide_h = self._slide_dims(slide)
        s = slide.shapes.add_shape(
            1, slide_w - Inches(2), Inches(1), Inches(2), Inches(2)
        )
        s.shadow.blur_radius = Emu(914400)  # 1" blur
        off = [i for i in slide.lint().issues if isinstance(i, OffSlide)]
        assert off == []

    def it_fires_OffSlideShadow_when_bleed_enabled(self):
        _, slide = _new_blank_slide()
        slide_w, _slide_h = self._slide_dims(slide)
        s = slide.shapes.add_shape(
            1, slide_w - Inches(2), Inches(1), Inches(2), Inches(2)
        )
        s.shadow.blur_radius = Emu(914400)
        report = slide.lint(include_effect_bleed=True)
        bleed = [i for i in report.issues if isinstance(i, OffSlideShadow)]
        assert len(bleed) >= 1
        assert any(i.code == "OffSlideShadow" for i in bleed)

    def it_does_not_fire_collision_when_bleed_disabled(self):
        _, slide = _new_blank_slide()
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        # b is well clear of a's raw bbox.
        b = slide.shapes.add_shape(1, Inches(4), Inches(1), Inches(2), Inches(2))
        a.shadow.blur_radius = Emu(914400 * 4)  # 4" blur — pushes into b
        b.shadow.blur_radius = Emu(914400 * 4)
        # Default lint sees no collision.
        assert _collisions(slide) == []

    def it_fires_ShapeCollisionShadow_when_bleed_enabled(self):
        _, slide = _new_blank_slide()
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        b = slide.shapes.add_shape(1, Inches(4), Inches(1), Inches(2), Inches(2))
        a.shadow.blur_radius = Emu(914400 * 4)
        b.shadow.blur_radius = Emu(914400 * 4)
        report = slide.lint(include_effect_bleed=True)
        bleed = [i for i in report.issues if isinstance(i, ShapeCollisionShadow)]
        assert len(bleed) == 1
        assert bleed[0].code == "ShapeCollisionShadow"

    def it_treats_GraphicFrame_as_no_bleed_regardless_of_flag(self):
        # Charts / tables (GraphicFrame) expose ``shape.shadow == None``
        # since 2.1.1 — the bleed helper must handle that gracefully
        # and fall back to the raw bbox.
        from power_pptx.shapes.base import BaseShape
        from power_pptx.lint import _effective_bbox, _shape_bbox

        class _FakeGraphicFrame:
            name = "tbl"
            left = Emu(914400)
            top = Emu(914400)
            width = Emu(914400)
            height = Emu(914400)
            shadow = None

        fake = _FakeGraphicFrame()
        assert _effective_bbox(fake) == _shape_bbox(fake)  # type: ignore[arg-type]
        # And it must not blow up when threaded through lint().
        _ = BaseShape  # silence unused-import lint

    def it_uses_a_shadow_specific_message_for_OffSlideShadow(self):
        # The bleed-only variant must not reuse OffSlide's "extends
        # beyond the … edge" wording, since the raw bbox is on-slide.
        _, slide = _new_blank_slide()
        slide_w, _slide_h = self._slide_dims(slide)
        s = slide.shapes.add_shape(
            1, slide_w - Inches(2), Inches(1), Inches(2), Inches(2)
        )
        s.shadow.blur_radius = Emu(914400)
        report = slide.lint(include_effect_bleed=True)
        bleed = [i for i in report.issues if isinstance(i, OffSlideShadow)]
        assert bleed, "expected at least one OffSlideShadow"
        msg = bleed[0].message
        assert "shadow bleed" in msg
        assert "raw bbox is on-slide" in msg

    def it_uses_a_shadow_specific_message_for_ShapeCollisionShadow(self):
        # Same — the raw bboxes don't overlap, only the inflated ones
        # do, so "Shapes … overlap …" would mislead.
        _, slide = _new_blank_slide()
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        b = slide.shapes.add_shape(1, Inches(4), Inches(1), Inches(2), Inches(2))
        a.shadow.blur_radius = Emu(914400 * 4)
        b.shadow.blur_radius = Emu(914400 * 4)
        report = slide.lint(include_effect_bleed=True)
        bleed = [i for i in report.issues if isinstance(i, ShapeCollisionShadow)]
        assert bleed, "expected at least one ShapeCollisionShadow"
        msg = bleed[0].message
        assert "shadow bleed" in msg
        assert "raw bboxes do not" in msg

    def it_preserves_include_effect_bleed_through_auto_fix_refresh(self):
        # Regression: ``auto_fix()`` refreshes ``report.issues`` by
        # calling ``slide.lint()``.  If the original report was built
        # under ``include_effect_bleed=True`` the refresh must use the
        # same mode — otherwise bleed-only issues silently disappear
        # from the residual punch list as soon as any other fix runs.
        _, slide = _new_blank_slide()
        slide_w, _slide_h = self._slide_dims(slide)
        # Bleed-only OffSlide on shape A.
        a = slide.shapes.add_shape(
            1, slide_w - Inches(2), Inches(0.5), Inches(2), Inches(2)
        )
        a.shadow.blur_radius = Emu(914400)
        # Off-grid drift offender (auto-fixable) so a fix actually fires
        # and triggers the refresh.  (It used to sit 30000 EMU off the
        # column, inside the tight tolerance, so no fix fired at all.)
        for i in range(4):
            slide.shapes.add_shape(
                1, Inches(6), Inches(0.5 + i * 1.0), Inches(1), Inches(0.5)
            )
        slide.shapes.add_shape(
            1, Inches(6) + 64000, Inches(5), Inches(1), Inches(0.5)
        )

        report = slide.lint(include_effect_bleed=True)
        assert any(isinstance(i, OffSlideShadow) for i in report.issues)
        # snaps the drift offender; triggers refresh
        assert report.auto_fix(fix_grid_drift=True)
        # Bleed-only OffSlideShadow must survive the refresh.
        assert any(isinstance(i, OffSlideShadow) for i in report.issues)

    def it_silences_OffSlideShadow_via_lint_skip_without_silencing_real_OffSlide(self):
        _, slide = _new_blank_slide()
        slide_w, slide_h = self._slide_dims(slide)
        # Shape A: bleed-only OffSlide (raw bbox inside, shadow past edge).
        a = slide.shapes.add_shape(
            1, slide_w - Inches(2), Inches(1), Inches(2), Inches(2)
        )
        a.shadow.blur_radius = Emu(914400)
        # Shape B: real OffSlide (raw bbox already past the bottom edge).
        b = slide.shapes.add_shape(
            1, Inches(1), slide_h - Inches(1), Inches(2), Inches(2)
        )
        # Skip the bleed-only variant on the bleed shape.
        a.lint_skip = {"OffSlideShadow"}
        report = slide.lint(include_effect_bleed=True)
        codes = {i.code for i in report.issues}
        assert "OffSlide" in codes  # b's real off-slide still fires
        assert "OffSlideShadow" not in codes  # a's bleed silenced


class DescribeNamePrefixGroups:
    """Shapes with dotted names ('card.bg', 'card.label') auto-group."""

    def it_treats_a_dotted_name_prefix_as_a_lint_group(self):
        _, slide = _new_blank_slide()
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(3), Inches(2))
        b = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(3), Inches(2))
        a.name = "card.bg"
        b.name = "card.label"
        # No explicit `lint_group` set, but the dotted prefix matches —
        # the collision should be suppressed.
        report = slide.lint()
        codes = [i.code for i in report.issues]
        assert "ShapeCollision" not in codes

    def it_still_flags_when_prefixes_differ(self):
        _, slide = _new_blank_slide()
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(3), Inches(2))
        b = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(3), Inches(2))
        a.name = "card.bg"
        b.name = "panel.bg"
        report = slide.lint()
        codes = [i.code for i in report.issues]
        assert "ShapeCollision" in codes

    def it_lets_an_empty_explicit_tag_opt_out(self):
        _, slide = _new_blank_slide()
        a = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(3), Inches(2))
        b = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(3), Inches(2))
        a.name = "card.bg"
        b.name = "card.label"
        a.lint_group = ""  # opt out of the implicit group
        report = slide.lint()
        codes = [i.code for i in report.issues]
        assert "ShapeCollision" in codes


class DescribeLintDisable:
    """`lint_slide(slide, disable=[...], min_severity=...)`."""

    def it_drops_disabled_codes(self):
        _, slide = _new_blank_slide()
        # Off-slide shape: would normally fire OffSlide.
        slide.shapes.add_shape(1, Inches(-2), Inches(-2), Inches(1), Inches(1))
        report = slide.lint(disable=["OffSlide"])
        assert all(i.code != "OffSlide" for i in report.issues)

    def it_filters_below_min_severity(self):
        _, slide = _new_blank_slide()
        # Two identical rectangles → 'matched' kind, INFO severity.
        slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        baseline = slide.lint(min_severity="info").issues
        warning_only = slide.lint(min_severity="warning").issues
        assert any(i.severity == LintSeverity.INFO for i in baseline)
        assert all(i.severity != LintSeverity.INFO for i in warning_only)

    def it_rejects_invalid_min_severity(self):
        _, slide = _new_blank_slide()
        with pytest.raises(ValueError, match="min_severity"):
            slide.lint(min_severity="bogus")


class DescribeAutoFixSizeClamp:
    """Auto-fix shrinks oversize shapes before nudging them on-slide."""

    def it_clamps_a_shape_wider_than_the_slide(self):
        prs, slide = _new_blank_slide()
        slide_w = prs.slide_width
        slide_h = prs.slide_height
        # 50-inch wide shape — wider than any standard slide.
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(50), Inches(2))
        report = slide.lint()
        report.auto_fix()
        assert int(s.width) <= int(slide_w)
        assert int(s.left) + int(s.width) <= int(slide_w)
        assert int(s.height) <= int(slide_h)


class DescribeFingerprints:
    """Stable digests for CI baselining."""

    def it_is_stable_across_lint_calls(self):
        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(-2), Inches(-2), Inches(1), Inches(1))
        a = slide.lint().fingerprints()
        b = slide.lint().fingerprints()
        assert a == b
        assert all(len(fp) == 12 for fp in a)

    def it_differs_between_distinct_issues(self):
        _, slide = _new_blank_slide()
        s1 = slide.shapes.add_shape(1, Inches(-2), Inches(-2), Inches(1), Inches(1))
        s2 = slide.shapes.add_shape(1, Inches(-3), Inches(-3), Inches(1), Inches(1))
        s1.name = "shape-A"
        s2.name = "shape-B"
        fps = slide.lint().fingerprints()
        assert len(fps) == len(set(fps))


class DescribeMachineReadableOutput:
    """``LintIssue.to_dict`` / ``SlideLintReport.to_dict`` / ``to_json``."""

    def it_serializes_an_issue_to_a_jsonable_dict(self):
        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(15), Inches(10), Inches(2), Inches(1))
        issue = next(i for i in slide.lint().issues if isinstance(i, OffSlide))

        d = issue.to_dict()

        assert d["code"] == "OffSlide"
        assert d["severity"] == "error"
        assert d["shapes"] == ["Rectangle 1"]
        # subclass-specific field is carried through automatically
        assert d["side"] in {"right", "bottom"}

    def it_includes_collision_scoring_fields(self):
        _, slide = _new_blank_slide()
        _add_overlapping_rects(slide, 2)
        issue = _collisions(slide)[0]

        d = issue.to_dict()

        assert d["code"] == "ShapeCollision"
        assert "intersection_area" in d
        assert "score" in d
        assert "kind" in d
        # the (group_a, group_b) tuple is normalized to a list for JSON
        assert isinstance(d["groups"], list)

    def it_serializes_the_report_to_json(self):
        import json

        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(15), Inches(10), Inches(2), Inches(1))
        report = slide.lint()

        payload = json.loads(report.to_json())

        assert payload["has_errors"] is True
        assert payload["issue_count"] == len(report.issues)
        assert isinstance(payload["issues"], list)
        assert payload["issues"][0]["code"] == "OffSlide"

    def it_serializes_a_clean_slide_to_an_empty_report(self):
        import json

        _, slide = _new_blank_slide()
        payload = json.loads(slide.lint().to_json())

        assert payload == {"has_errors": False, "issue_count": 0, "issues": []}


class DescribeSarifExport:
    """``SlideLintReport.to_sarif`` / ``lint_report_to_sarif``."""

    def it_emits_a_valid_sarif_v2_1_0_document(self):
        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(15), Inches(10), Inches(2), Inches(1))
        report = slide.lint()

        sarif = report.to_sarif()

        assert sarif["version"] == "2.1.0"
        assert "$schema" in sarif
        assert isinstance(sarif["runs"], list)
        assert len(sarif["runs"]) == 1
        driver = sarif["runs"][0]["tool"]["driver"]
        assert driver["name"] == "power-pptx-lint"
        assert isinstance(driver["rules"], list)

    def it_has_one_result_per_issue_with_mapped_levels(self):
        _, slide = _new_blank_slide()
        # OffSlide → ERROR → "error".
        slide.shapes.add_shape(1, Inches(15), Inches(10), Inches(2), Inches(1))
        report = slide.lint()

        results = report.to_sarif()["runs"][0]["results"]

        assert len(results) == len(report.issues)
        # Every result level must be one of the three SARIF levels we map to.
        assert all(r["level"] in {"error", "warning", "note"} for r in results)
        off_slide = next(r for r in results if r["ruleId"] == "OffSlide")
        assert off_slide["level"] == "error"
        assert off_slide["message"]["text"]
        # Locations name the offending shape.
        names = [
            loc["logicalLocations"][0]["name"]
            for loc in off_slide["locations"]
        ]
        assert "Rectangle 1" in names

    def it_derives_rules_from_the_issue_codes(self):
        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(15), Inches(10), Inches(2), Inches(1))
        report = slide.lint()

        rules = report.to_sarif()["runs"][0]["tool"]["driver"]["rules"]
        rule_ids = {r["id"] for r in rules}
        result_rule_ids = {
            r["ruleId"] for r in report.to_sarif()["runs"][0]["results"]
        }
        # Every result references a declared rule.
        assert result_rule_ids <= rule_ids

    def it_is_json_serializable(self):
        import json

        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(15), Inches(10), Inches(2), Inches(1))
        report = slide.lint()

        text = json.dumps(report.to_sarif())
        assert json.loads(text)["version"] == "2.1.0"
        # The convenience JSON helper agrees with json.dumps(to_sarif()).
        assert json.loads(report.to_sarif_json())["version"] == "2.1.0"

    def it_records_slide_index_when_supplied(self):
        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(15), Inches(10), Inches(2), Inches(1))
        report = slide.lint()

        results = report.to_sarif(slide_index=3)["runs"][0]["results"]
        assert results
        assert all(r["properties"]["slideIndex"] == 3 for r in results)

    def it_aggregates_a_whole_deck_with_slide_indices(self):
        from power_pptx.lint import lint_report_to_sarif

        prs = Presentation()
        reports = []
        for _ in range(3):
            s = prs.slides.add_slide(prs.slide_layouts[6])
            s.shapes.add_shape(1, Inches(15), Inches(10), Inches(2), Inches(1))
            reports.append(s.lint())

        sarif = lint_report_to_sarif(reports)

        assert sarif["version"] == "2.1.0"
        results = sarif["runs"][0]["results"]
        # Every slide that had an issue is represented.
        indices = {r["properties"]["slideIndex"] for r in results}
        assert indices == {0, 1, 2}

    def it_accepts_a_single_report(self):
        from power_pptx.lint import lint_report_to_sarif

        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(15), Inches(10), Inches(2), Inches(1))
        report = slide.lint()

        sarif = lint_report_to_sarif(report)
        assert sarif["runs"][0]["results"][0]["properties"]["slideIndex"] == 0

    def it_emits_a_well_formed_empty_run_for_a_clean_slide(self):
        _, slide = _new_blank_slide()
        sarif = slide.lint().to_sarif()
        assert sarif["version"] == "2.1.0"
        assert sarif["runs"][0]["results"] == []
        assert sarif["runs"][0]["tool"]["driver"]["rules"] == []


class DescribeBaselineDiff:
    """``SlideLintReport.diff`` / ``diff_detail`` for CI baselining."""

    def it_returns_empty_when_identical(self):
        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(-2), Inches(-2), Inches(1), Inches(1))
        baseline = slide.lint()
        current = slide.lint()
        assert current.diff(baseline) == []

    def it_returns_only_newly_introduced_issues(self):
        _, slide = _new_blank_slide()
        s1 = slide.shapes.add_shape(1, Inches(-2), Inches(-2), Inches(1), Inches(1))
        s1.name = "first-off-slide"
        baseline = slide.lint()

        # Introduce a second, distinct off-slide shape.
        s2 = slide.shapes.add_shape(1, Inches(-5), Inches(-5), Inches(1), Inches(1))
        s2.name = "second-off-slide"
        current = slide.lint()

        new_issues = current.diff(baseline)
        # Only the new shape's issues appear; the pre-existing one does not.
        assert new_issues
        new_shape_names = {
            s.name for issue in new_issues for s in issue.shapes
        }
        assert new_shape_names == {"second-off-slide"}

    def it_ignores_issues_that_only_moved(self):
        # A shape already off-slide that is nudged (still off-slide) keeps
        # the same fingerprint, so diff() must not report it as new.
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(-2), Inches(-2), Inches(1), Inches(1))
        s.name = "drifter"
        baseline = slide.lint()
        s.left = Inches(-3)  # still off the left edge
        current = slide.lint()
        assert current.diff(baseline) == []

    def it_reports_added_and_fixed_in_detail(self):
        _, slide = _new_blank_slide()
        s1 = slide.shapes.add_shape(1, Inches(-2), Inches(-2), Inches(1), Inches(1))
        s1.name = "to-be-fixed"
        baseline = slide.lint()

        # Fix the first shape, add a different problem.
        s1.left = Inches(1)
        s1.top = Inches(1)
        s2 = slide.shapes.add_shape(1, Inches(-5), Inches(-5), Inches(1), Inches(1))
        s2.name = "brand-new"
        current = slide.lint()

        detail = current.diff_detail(baseline)
        added_names = {s.name for i in detail["added"] for s in i.shapes}
        fixed_names = {s.name for i in detail["fixed"] for s in i.shapes}
        assert "brand-new" in added_names
        assert "to-be-fixed" in fixed_names


class DescribeLintExtensionsRoundTrip:
    """A deck carrying lint metadata still saves and reopens cleanly."""

    def it_round_trips_a_small_deck_unchanged(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shape = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        shape.text_frame.text = "Hello"

        # Building SARIF / diff must not mutate the deck.
        slide.lint().to_sarif()
        slide.lint().diff(slide.lint())

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        reopened = Presentation(buf)
        assert len(reopened.slides) == 1
        names = [s.name for s in reopened.slides[0].shapes]
        assert any("Rectangle" in n for n in names)


# ---------------------------------------------------------------------------
# Relationship model — declaring intentional overlaps (ROADMAP).
# ---------------------------------------------------------------------------


def _layer_violations(slide):
    return [i for i in slide.lint().issues if isinstance(i, LayerOrderViolation)]


def _has_extLst(shape):
    return "extLst" in shape._element.xml


class DescribeShapeOverlapAllowance:
    """``allow_overlap_with`` / ``disallow_overlap_with`` / ``overlap_allowances``."""

    def it_defaults_to_an_empty_set(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        assert s.overlap_allowances == frozenset()

    def it_records_the_other_shapes_id(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.allow_overlap_with(b)
        assert a.overlap_allowances == frozenset({b.shape_id})
        # The declaration is one-sided to *write* — nothing lands on b.
        assert b.overlap_allowances == frozenset()

    def it_accumulates_across_repeated_calls(self):
        _, slide = _new_blank_slide()
        a, b, c = _add_overlapping_rects(slide, 3)
        a.allow_overlap_with(b)
        a.allow_overlap_with(c)
        assert a.overlap_allowances == frozenset({b.shape_id, c.shape_id})

    def it_accepts_several_shapes_in_one_call(self):
        _, slide = _new_blank_slide()
        a, b, c = _add_overlapping_rects(slide, 3)
        a.allow_overlap_with(b, c)
        assert a.overlap_allowances == frozenset({b.shape_id, c.shape_id})

    def it_is_idempotent(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.allow_overlap_with(b)
        a.allow_overlap_with(b)
        assert a.overlap_allowances == frozenset({b.shape_id})

    def it_accepts_zero_shapes_as_a_no_op(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.allow_overlap_with(b)
        a.allow_overlap_with()  # must not raise, must not clear
        assert a.overlap_allowances == frozenset({b.shape_id})

    def it_revokes_a_single_pair(self):
        _, slide = _new_blank_slide()
        a, b, c = _add_overlapping_rects(slide, 3)
        a.allow_overlap_with(b, c)
        a.disallow_overlap_with(c)
        assert a.overlap_allowances == frozenset({b.shape_id})

    def it_treats_revoking_an_ungranted_pair_as_a_no_op(self):
        _, slide = _new_blank_slide()
        a, b, c = _add_overlapping_rects(slide, 3)
        a.allow_overlap_with(b)
        a.disallow_overlap_with(c)  # never granted — must not raise
        a.disallow_overlap_with(c)  # ...and stay a no-op when repeated
        assert a.overlap_allowances == frozenset({b.shape_id})

    def it_rejects_a_self_reference(self):
        _, slide = _new_blank_slide()
        a, _ = _add_overlapping_rects(slide, 2)
        with pytest.raises(ValueError):
            a.allow_overlap_with(a)
        assert a.overlap_allowances == frozenset()

    def it_rejects_an_object_with_no_shape_id(self):
        _, slide = _new_blank_slide()
        a, _ = _add_overlapping_rects(slide, 2)
        with pytest.raises(ValueError):
            a.allow_overlap_with(object())  # type: ignore[arg-type]

    def it_round_trips_ids_through_the_setter(self):
        _, slide = _new_blank_slide()
        a, b, c = _add_overlapping_rects(slide, 3)
        a.overlap_allowances = [b.shape_id, c.shape_id]
        assert a.overlap_allowances == frozenset({b.shape_id, c.shape_id})

    def it_replaces_rather_than_accumulates_on_assignment(self):
        _, slide = _new_blank_slide()
        a, b, c = _add_overlapping_rects(slide, 3)
        a.allow_overlap_with(b)
        a.overlap_allowances = {c.shape_id}
        assert a.overlap_allowances == frozenset({c.shape_id})

    def it_clears_when_assigned_an_empty_iterable(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.allow_overlap_with(b)
        a.overlap_allowances = ()
        assert a.overlap_allowances == frozenset()

    def it_clears_when_assigned_None(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.allow_overlap_with(b)
        a.overlap_allowances = None
        assert a.overlap_allowances == frozenset()

    def it_rejects_a_non_iterable_value(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        with pytest.raises(TypeError):
            a.overlap_allowances = b.shape_id  # a bare int is a classic slip

    def it_rejects_a_str_or_bytes_value(self):
        # str/bytes are iterable but iterating them yields characters, which
        # would silently produce a garbage (or empty) allowance set.
        _, slide = _new_blank_slide()
        a, _ = _add_overlapping_rects(slide, 2)
        with pytest.raises(TypeError):
            a.overlap_allowances = "3"
        with pytest.raises(TypeError):
            a.overlap_allowances = b"3"

    def it_rejects_non_integer_entries(self):
        _, slide = _new_blank_slide()
        a, _ = _add_overlapping_rects(slide, 2)
        with pytest.raises(TypeError):
            a.overlap_allowances = ["3"]
        with pytest.raises(TypeError):
            a.overlap_allowances = [3.0]
        with pytest.raises(TypeError):
            a.overlap_allowances = [None]

    def it_rejects_bool_entries_despite_bool_subclassing_int(self):
        _, slide = _new_blank_slide()
        a, _ = _add_overlapping_rects(slide, 2)
        with pytest.raises(TypeError):
            a.overlap_allowances = [True]

    def it_writes_metadata_via_extLst_not_a_custom_attribute(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.allow_overlap_with(b)
        cNvPr = a._element._nvXxPr.cNvPr
        assert _LEGACY_LINT_GROUP_ATTR not in cNvPr.attrib
        ext = _find_lint_ext(cNvPr)
        assert ext is not None
        assert ext.get("uri") == _LINT_EXT_URI


class DescribeCollisionAllowanceSuppression:
    """``ShapeCollision`` honours pairwise ``allow_overlap_with`` declarations."""

    def it_warns_about_an_undeclared_overlap(self):
        _, slide = _new_blank_slide()
        _add_overlapping_rects(slide, 2)
        assert len(_collisions(slide)) == 1

    def it_suppresses_the_collision_when_declared(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        assert len(_collisions(slide)) == 1
        a.allow_overlap_with(b)
        assert _collisions(slide) == []

    def it_reads_the_declaration_symmetrically(self):
        # Declaring from either end suppresses; the designer shouldn't have
        # to guess which shape "owns" the relationship.
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        b.allow_overlap_with(a)
        assert _collisions(slide) == []

    def it_stays_suppressed_when_both_sides_vouch(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.allow_overlap_with(b)
        b.allow_overlap_with(a)
        assert _collisions(slide) == []

    def it_unsuppresses_when_the_only_allowance_is_revoked(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.allow_overlap_with(b)
        assert _collisions(slide) == []
        a.disallow_overlap_with(b)
        assert len(_collisions(slide)) == 1

    def it_stays_suppressed_after_a_one_sided_revoke(self):
        # ``disallow_overlap_with`` only clears the allowance recorded on the
        # shape it is called on — the other side's vouch still stands.
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.allow_overlap_with(b)
        b.allow_overlap_with(a)
        a.disallow_overlap_with(b)
        assert _collisions(slide) == []
        b.disallow_overlap_with(a)
        assert len(_collisions(slide)) == 1

    def it_suppresses_only_the_declared_pair(self):
        # An allowance is pair-scoped, unlike a lint_group: a's clearance to
        # overlap b says nothing about a third shape.
        _, slide = _new_blank_slide()
        a, b, c = _add_overlapping_rects(slide, 3)
        assert len(_collisions(slide)) == 3
        a.allow_overlap_with(b)
        remaining = _collisions(slide)
        assert len(remaining) == 2
        pairs = {tuple(sorted((i.shapes[0].name, i.shapes[1].name))) for i in remaining}
        assert pairs == {
            tuple(sorted((a.name, c.name))),
            tuple(sorted((b.name, c.name))),
        }

    def it_suppresses_every_declared_pair(self):
        _, slide = _new_blank_slide()
        a, b, c = _add_overlapping_rects(slide, 3)
        a.allow_overlap_with(b, c)
        b.allow_overlap_with(c)
        assert _collisions(slide) == []

    def it_ignores_an_allowance_naming_an_unrelated_id(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.overlap_allowances = {9999}
        assert len(_collisions(slide)) == 1


class DescribeShapeLayerHints:
    """Per-shape ``layer`` / ``layer_above`` z-order intent declarations."""

    def it_defaults_to_None(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        assert s.layer is None
        assert s.layer_above is None

    def it_round_trips_string_values(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.layer = "badge"
        s.layer_above = "card"
        assert s.layer == "badge"
        assert s.layer_above == "card"

    def it_keeps_the_two_names_independent(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.layer = "badge"
        s.layer_above = "card"
        s.layer = None
        assert s.layer is None
        assert s.layer_above == "card"

    def it_strips_surrounding_whitespace(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.layer = "  card  "
        s.layer_above = "\tpanel\n"
        assert s.layer == "card"
        assert s.layer_above == "panel"

    def it_normalises_a_blank_name_to_None(self):
        # A layer literally named "   " is never what the caller meant.
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.layer = "card"
        s.layer = "   "
        assert s.layer is None
        s.layer_above = "card"
        s.layer_above = ""
        assert s.layer_above is None

    def it_rejects_a_non_string_name(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        with pytest.raises(TypeError):
            s.layer = 5
        with pytest.raises(TypeError):
            s.layer_above = 5
        with pytest.raises(TypeError):
            s.layer = ["card"]

    def it_allows_a_layer_name_to_be_shared_by_many_shapes(self):
        # Unlike lint_group, a layer names a stratum of the design rather
        # than one cluster, so re-use is legitimate.
        _, slide = _new_blank_slide()
        a, b, c = _add_overlapping_rects(slide, 3)
        for s in (a, b, c):
            s.layer = "card"
        assert [s.layer for s in (a, b, c)] == ["card", "card", "card"]

    def it_writes_metadata_via_extLst_not_a_custom_attribute(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.layer = "card"
        cNvPr = s._element._nvXxPr.cNvPr
        assert _LEGACY_LINT_GROUP_ATTR not in cNvPr.attrib
        ext = _find_lint_ext(cNvPr)
        assert ext is not None
        assert ext.get("uri") == _LINT_EXT_URI


class DescribeLayerOrderViolationCheck:
    """``layer`` / ``layer_above`` suppression and the contradicted case."""

    def it_suppresses_a_collision_consistent_with_the_declaration(self):
        # ``under`` is added first, so ``over`` is painted on top of it —
        # exactly what ``over.layer_above`` asserts.
        _, slide = _new_blank_slide()
        under, over = _add_overlapping_rects(slide, 2)
        under.layer = "card"
        over.layer_above = "card"
        assert _collisions(slide) == []
        assert _layer_violations(slide) == []

    def it_reports_a_violation_when_the_z_order_contradicts_it(self):
        # ``over`` claims to sit above the "card" layer but is added first,
        # so it is actually painted underneath ``under``.
        _, slide = _new_blank_slide()
        over, under = _add_overlapping_rects(slide, 2)
        over.layer_above = "card"
        under.layer = "card"
        violations = _layer_violations(slide)
        assert len(violations) == 1
        assert violations[0].code == "LayerOrderViolation"
        assert violations[0].severity is LintSeverity.ERROR
        assert violations[0].layer == "card"
        assert violations[0].shapes == (over, under)

    def it_still_reports_the_underlying_collision_when_contradicted(self):
        # Deliberate: a contradicted declaration is not an intent marker, so
        # the pair must not be silently dropped from the collision report.
        _, slide = _new_blank_slide()
        over, under = _add_overlapping_rects(slide, 2)
        over.layer_above = "card"
        under.layer = "card"
        assert len(_collisions(slide)) == 1

    def it_reports_no_violation_for_shapes_that_do_not_overlap(self):
        # A layer declaration between shapes that never touch is inert.
        _, slide = _new_blank_slide()
        over = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(1), Inches(1))
        under = slide.shapes.add_shape(1, Inches(5), Inches(4), Inches(1), Inches(1))
        over.layer_above = "card"
        under.layer = "card"
        assert _layer_violations(slide) == []
        assert _collisions(slide) == []

    def it_reports_no_violation_when_only_layer_above_is_declared(self):
        _, slide = _new_blank_slide()
        over, _under = _add_overlapping_rects(slide, 2)
        over.layer_above = "card"
        assert _layer_violations(slide) == []
        assert len(_collisions(slide)) == 1

    def it_reports_no_violation_when_the_layer_names_do_not_match(self):
        _, slide = _new_blank_slide()
        over, under = _add_overlapping_rects(slide, 2)
        over.layer_above = "card"
        under.layer = "panel"
        assert _layer_violations(slide) == []
        assert len(_collisions(slide)) == 1

    def it_reports_nothing_when_no_shape_declares_a_layer(self):
        _, slide = _new_blank_slide()
        _add_overlapping_rects(slide, 2)
        assert _layer_violations(slide) == []

    def it_reports_one_violation_per_contradicted_pair(self):
        _, slide = _new_blank_slide()
        over, under_a, under_b = _add_overlapping_rects(slide, 3)
        over.layer_above = "card"
        under_a.layer = "card"
        under_b.layer = "card"
        assert len(_layer_violations(slide)) == 2

    def it_can_be_silenced_per_shape_via_lint_skip(self):
        _, slide = _new_blank_slide()
        over, under = _add_overlapping_rects(slide, 2)
        over.layer_above = "card"
        under.layer = "card"
        over.lint_skip = {"LayerOrderViolation"}
        under.lint_skip = {"LayerOrderViolation"}
        assert _layer_violations(slide) == []


class DescribeLintExtensionPruning:
    """Clearing lint metadata must leave neither residue nor collateral damage."""

    def it_leaves_no_extLst_after_clearing_an_allowance(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.allow_overlap_with(b)
        assert _has_extLst(a)
        a.disallow_overlap_with(b)
        assert not _has_extLst(a)
        assert _find_lint_ext(a._element._nvXxPr.cNvPr) is None

    def it_leaves_no_extLst_after_assigning_an_empty_allowance_set(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.allow_overlap_with(b)
        a.overlap_allowances = ()
        assert not _has_extLst(a)

    def it_leaves_no_extLst_after_clearing_both_layer_names(self):
        _, slide = _new_blank_slide()
        s = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        s.layer = "card"
        s.layer_above = "panel"
        assert _has_extLst(s)
        s.layer = None
        s.layer_above = None
        assert not _has_extLst(s)
        assert _find_lint_ext(s._element._nvXxPr.cNvPr) is None

    def it_leaves_no_extLst_after_clearing_every_lint_setting(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.lint_group = "card-1"
        a.lint_skip = {"MinFontSize"}
        a.layer = "card"
        a.layer_above = "panel"
        a.allow_overlap_with(b)
        a.lint_group = None
        a.lint_skip = set()
        a.layer = None
        a.layer_above = None
        a.overlap_allowances = ()
        assert not _has_extLst(a)

    def it_preserves_siblings_when_clearing_the_layer(self):
        # Same bug class ``_clear_lint_group`` guards against: all five
        # settings share one ``<a:ext>``, so a clear must remove only its
        # own node.
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.lint_group = "card-1"
        a.lint_skip = {"MinFontSize"}
        a.allow_overlap_with(b)
        a.layer = "card"
        a.layer_above = "panel"
        a.layer = None
        a.layer_above = None
        assert a.lint_group == "card-1"
        assert a.lint_skip == frozenset({"MinFontSize"})
        assert a.overlap_allowances == frozenset({b.shape_id})

    def it_preserves_siblings_when_clearing_the_allowances(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.lint_group = "card-1"
        a.lint_skip = {"MinFontSize"}
        a.layer = "card"
        a.layer_above = "panel"
        a.allow_overlap_with(b)
        a.overlap_allowances = ()
        assert a.lint_group == "card-1"
        assert a.lint_skip == frozenset({"MinFontSize"})
        assert (a.layer, a.layer_above) == ("card", "panel")

    def it_preserves_the_new_fields_when_clearing_lint_group(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.lint_group = "card-1"
        a.layer = "card"
        a.layer_above = "panel"
        a.allow_overlap_with(b)
        a.lint_group = None
        assert a.lint_group is None
        assert (a.layer, a.layer_above) == ("card", "panel")
        assert a.overlap_allowances == frozenset({b.shape_id})

    def it_preserves_the_new_fields_when_clearing_lint_skip(self):
        _, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.lint_skip = {"MinFontSize"}
        a.layer = "card"
        a.allow_overlap_with(b)
        a.lint_skip = set()
        assert a.lint_skip == frozenset()
        assert a.layer == "card"
        assert a.overlap_allowances == frozenset({b.shape_id})


class DescribeRelationshipModelRoundTrip:
    """All five lint settings survive a save/reopen cycle together."""

    def it_persists_every_setting_through_save_and_load(self):
        prs, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.lint_group = "card-1"
        a.lint_skip = {"MinFontSize"}
        a.layer = "card"
        a.layer_above = "panel"
        a.allow_overlap_with(b)
        b_id = b.shape_id

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        a2, b2 = list(Presentation(buf).slides[0].shapes)

        assert a2.lint_group == "card-1"
        assert a2.lint_skip == frozenset({"MinFontSize"})
        assert a2.layer == "card"
        assert a2.layer_above == "panel"
        assert a2.overlap_allowances == frozenset({b_id})
        assert b2.shape_id == b_id

    def it_still_suppresses_the_collision_after_a_reload(self):
        prs, slide = _new_blank_slide()
        a, b = _add_overlapping_rects(slide, 2)
        a.allow_overlap_with(b)
        assert _collisions(slide) == []

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        reloaded = Presentation(buf).slides[0]
        assert _collisions(reloaded) == []

    def it_still_suppresses_a_layered_collision_after_a_reload(self):
        prs, slide = _new_blank_slide()
        under, over = _add_overlapping_rects(slide, 2)
        under.layer = "card"
        over.layer_above = "card"
        assert _collisions(slide) == []

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        reloaded = Presentation(buf).slides[0]
        assert _collisions(reloaded) == []
        assert _layer_violations(reloaded) == []

    def it_still_reports_a_layer_violation_after_a_reload(self):
        prs, slide = _new_blank_slide()
        over, under = _add_overlapping_rects(slide, 2)
        over.layer_above = "card"
        under.layer = "card"

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        reloaded = Presentation(buf).slides[0]
        violations = _layer_violations(reloaded)
        assert len(violations) == 1
        assert violations[0].severity is LintSeverity.ERROR
        assert len(_collisions(reloaded)) == 1


class DescribeAutoFixLayerOrder:
    """``auto_fix()`` restacks a shape whose ``layer_above`` is contradicted."""

    @staticmethod
    def _contradicted_pair(slide):
        over, under = _add_overlapping_rects(slide, 2)
        over.name = "badge"
        under.name = "card"
        over.layer_above = "card"
        under.layer = "card"
        return over, under

    def it_restacks_the_declaring_shape_above_its_layer(self):
        _, slide = _new_blank_slide()
        self._contradicted_pair(slide)
        assert [s.name for s in slide.shapes] == ["badge", "card"]
        slide.lint().auto_fix()
        assert [s.name for s in slide.shapes] == ["card", "badge"]

    def it_returns_a_description_of_the_restack(self):
        _, slide = _new_blank_slide()
        self._contradicted_pair(slide)
        fixes = slide.lint().auto_fix()
        assert len(fixes) == 1
        assert "badge" in fixes[0]
        assert "card" in fixes[0]
        assert "Restacked" in fixes[0]

    def it_drops_the_violation_from_the_refreshed_issues(self):
        # auto_fix() refreshes ``report.issues`` in place, so the residual
        # punch list needs no second lint() call.
        _, slide = _new_blank_slide()
        self._contradicted_pair(slide)
        report = slide.lint()
        assert len(_layer_violations(slide)) == 1
        report.auto_fix()
        assert [i for i in report.issues if isinstance(i, LayerOrderViolation)] == []
        # ...and the collision goes with it: the restack makes the layer
        # declaration consistent, which is itself an intent marker.
        assert report.issues == []

    def it_preserves_the_shape_count(self):
        # ``addnext`` *moves* the element. A copy-then-insert would leave a
        # duplicate behind (and a duplicate shape id, which PowerPoint
        # reports as a repair).
        _, slide = _new_blank_slide()
        self._contradicted_pair(slide)
        slide.lint().auto_fix()
        names = [s.name for s in slide.shapes]
        assert len(names) == 2
        assert sorted(names) == ["badge", "card"]
        assert len({s.shape_id for s in slide.shapes}) == 2

    def it_leaves_the_slide_untouched_on_a_dry_run(self):
        _, slide = _new_blank_slide()
        self._contradicted_pair(slide)
        report = slide.lint()
        fixes = report.auto_fix(dry_run=True)
        assert len(fixes) == 1
        assert "Restacked" in fixes[0]
        assert [s.name for s in slide.shapes] == ["badge", "card"]
        # The issue list is not refreshed either — nothing changed.
        assert len([i for i in report.issues if isinstance(i, LayerOrderViolation)]) == 1

    def it_restacks_each_shape_at_most_once_per_pass(self):
        # One badge declaring layer_above="card" over *two* "card" shapes
        # yields two violations; the ``restacked`` guard keeps the pass to a
        # single move so interacting declarations can't ping-pong.
        _, slide = _new_blank_slide()
        badge, card_a, card_b = _add_overlapping_rects(slide, 3)
        badge.name = "badge"
        card_a.name = "cardA"
        card_b.name = "cardB"
        badge.layer_above = "card"
        card_a.layer = "card"
        card_b.layer = "card"
        report = slide.lint()
        assert len([i for i in report.issues if isinstance(i, LayerOrderViolation)]) == 2
        fixes = report.auto_fix()
        assert len(fixes) == 1
        assert [s.name for s in slide.shapes] == ["cardA", "badge", "cardB"]
        assert len(slide.shapes) == 3

    def it_skips_a_pair_that_is_not_sibling_level(self):
        # A cross-container pair (one shape inside a group, one outside) has
        # no single ordering to fix — skip it rather than crash.
        prs, slide = _new_blank_slide()
        group = slide.shapes.add_group_shape()
        inner = group.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(2))
        inner.name = "inner"
        outer = slide.shapes.add_shape(1, Inches(1.5), Inches(1.5), Inches(2), Inches(2))
        outer.name = "outer"
        inner.layer_above = "card"
        outer.layer = "card"

        report = SlideLintReport(slide, [LayerOrderViolation(inner, outer, "card")])
        assert report.auto_fix() == []
        assert [s.name for s in slide.shapes] == [group.name, "outer"]
        assert [s.name for s in group.shapes] == ["inner"]

    def it_is_reached_through_slide_tidy_by_default(self):
        _, slide = _new_blank_slide()
        self._contradicted_pair(slide)
        fixes = slide.tidy()
        assert any("Restacked" in f for f in fixes)
        assert [s.name for s in slide.shapes] == ["card", "badge"]

    def it_leaves_the_order_alone_when_tidy_opts_out(self):
        _, slide = _new_blank_slide()
        self._contradicted_pair(slide)
        fixes = slide.tidy(fix_layer_order=False)
        assert not any("Restacked" in f for f in fixes)
        assert [s.name for s in slide.shapes] == ["badge", "card"]

    def it_still_fixes_off_slide_when_layer_order_is_opted_out(self):
        # ``fix_layer_order=False`` works by disabling the rule in lint(),
        # so it must not disturb the other tidy fixes.
        _, slide = _new_blank_slide()
        self._contradicted_pair(slide)
        stray = slide.shapes.add_shape(1, Inches(-3), Inches(-3), Inches(1), Inches(1))
        stray.name = "stray"
        slide.tidy(fix_layer_order=False)
        assert int(stray.left) >= 0
        assert int(stray.top) >= 0
        assert [s.name for s in slide.shapes][:2] == ["badge", "card"]


class DescribeLayerOrderViolationReporting:
    """Fingerprint and SARIF plumbing for ``LayerOrderViolation``."""

    @staticmethod
    def _contradicted_slide():
        _, slide = _new_blank_slide()
        over, under = _add_overlapping_rects(slide, 2)
        over.name = "badge"
        under.name = "card"
        over.layer_above = "card"
        under.layer = "card"
        return slide

    def it_fingerprints_the_violation_stably_across_runs(self):
        slide = self._contradicted_slide()
        first = slide.lint().fingerprints()
        second = slide.lint().fingerprints()
        assert first == second
        assert len(first) == len(slide.lint().issues)

    def it_distinguishes_violations_by_layer_name(self):
        # ``layer`` is part of the classifying-field tuple, so two
        # otherwise-identical violations on different layers differ.
        slide_a = self._contradicted_slide()
        fp_a = set(slide_a.lint().fingerprints())

        _, slide_b = _new_blank_slide()
        over, under = _add_overlapping_rects(slide_b, 2)
        over.name = "badge"
        under.name = "card"
        over.layer_above = "panel"
        under.layer = "panel"
        fp_b = set(slide_b.lint().fingerprints())

        assert fp_a != fp_b

    def it_emits_a_sarif_rule_with_a_short_description(self):
        slide = self._contradicted_slide()
        sarif = slide.lint().to_sarif()
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        by_id = {r["id"]: r for r in rules}
        assert "LayerOrderViolation" in by_id
        assert by_id["LayerOrderViolation"]["shortDescription"]["text"].strip()

    def it_reports_the_violation_as_a_sarif_error_result(self):
        slide = self._contradicted_slide()
        sarif = slide.lint().to_sarif()
        results = [r for r in sarif["runs"][0]["results"] if r["ruleId"] == "LayerOrderViolation"]
        assert len(results) == 1
        assert results[0]["level"] == "error"


class DescribeCrossSlideOverlapAllowance:
    """An allowance may only name a shape on the same slide.

    Shape ids are unique within a slide, not across a deck, so an id
    borrowed from another slide either collides with this shape's own id
    (reading as a bogus self-reference) or silently matches an unrelated
    shape here and suppresses a collision that was real.
    """

    def _two_slides(self):
        from power_pptx import Presentation
        from power_pptx.util import Inches

        prs = Presentation()
        s1 = prs.slides.add_slide(prs.slide_layouts[6])
        s2 = prs.slides.add_slide(prs.slide_layouts[6])
        p = s1.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(2))
        q = s1.shapes.add_textbox(Inches(2), Inches(1), Inches(3), Inches(2))
        far = s2.shapes.add_textbox(Inches(1), Inches(1), Inches(1), Inches(1))
        other = s2.shapes.add_textbox(Inches(5), Inches(4), Inches(1), Inches(1))
        return s1, p, q, far, other

    def it_rejects_a_target_whose_id_collides_with_the_source(self):
        import pytest

        _, p, _, far, _ = self._two_slides()
        assert far.shape_id == p.shape_id  # the id collision that misled

        with pytest.raises(ValueError, match="different slide"):
            p.allow_overlap_with(far)

    def it_rejects_a_target_whose_id_collides_with_a_sibling(self):
        import pytest

        _, p, q, _, other = self._two_slides()
        assert other.shape_id == q.shape_id  # would have suppressed p/q

        with pytest.raises(ValueError, match="different slide"):
            p.allow_overlap_with(other)

    def it_does_not_suppress_a_real_collision_via_a_cross_slide_id(self):
        import pytest

        s1, p, _, _, other = self._two_slides()
        before = [i.code for i in s1.lint().issues if i.code == "ShapeCollision"]
        assert before  # the p/q overlap is genuinely reported

        with pytest.raises(ValueError):
            p.allow_overlap_with(other)

        after = [i.code for i in s1.lint().issues if i.code == "ShapeCollision"]
        assert after == before

    def it_rejects_a_cross_slide_target_on_revoke_too(self):
        import pytest

        _, p, _, _, other = self._two_slides()
        with pytest.raises(ValueError, match="different slide"):
            p.disallow_overlap_with(other)

    def it_still_accepts_a_shape_on_the_same_slide(self):
        s1, p, q, _, _ = self._two_slides()
        p.allow_overlap_with(q)

        assert q.shape_id in p.overlap_allowances
        assert not [i for i in s1.lint().issues if i.code == "ShapeCollision"]

    def it_still_accepts_a_group_member_on_the_same_slide(self):
        from power_pptx.util import Inches

        s1, p, _, _, _ = self._two_slides()
        group = s1.shapes.add_group_shape()
        inner = group.shapes.add_textbox(
            Inches(1), Inches(1), Inches(1), Inches(1)
        )

        p.allow_overlap_with(inner)

        assert inner.shape_id in p.overlap_allowances


class DescribeAllowanceCleanupOnDelete:
    """Deleting a shape must not leave allowances pointing at its id.

    Shape ids are recycled: the allocator hands out ``max(existing) + 1``,
    so deleting the highest-id shape frees its id for the next shape added
    after a save/reopen. A leftover allowance would then match that
    unrelated newcomer and silently suppress a real collision.
    """

    def _overlapping_pair(self):
        from power_pptx import Presentation
        from power_pptx.util import Inches

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(2))
        b = slide.shapes.add_textbox(Inches(2), Inches(1), Inches(3), Inches(2))
        a.allow_overlap_with(b)
        return prs, slide, a, b

    def it_drops_the_deleted_shapes_id_from_allowances(self):
        _, _, a, b = self._overlapping_pair()
        assert b.shape_id in a.overlap_allowances

        b.delete()

        assert a.overlap_allowances == frozenset()

    def it_keeps_allowances_naming_other_shapes(self):
        from power_pptx.util import Inches

        _, slide, a, b = self._overlapping_pair()
        other = slide.shapes.add_textbox(
            Inches(6), Inches(1), Inches(1), Inches(1)
        )
        a.allow_overlap_with(other)

        b.delete()

        assert a.overlap_allowances == frozenset({other.shape_id})

    def it_purges_allowances_held_by_shapes_inside_groups(self):
        from power_pptx.util import Inches

        _, slide, _, b = self._overlapping_pair()
        group = slide.shapes.add_group_shape()
        inner = group.shapes.add_textbox(
            Inches(1), Inches(1), Inches(1), Inches(1)
        )
        inner.allow_overlap_with(b)

        b.delete()

        assert inner.overlap_allowances == frozenset()

    def it_does_not_suppress_a_collision_with_a_shape_reusing_the_id(self):
        import io

        from power_pptx import Presentation
        from power_pptx.util import Inches

        prs, _, _, b = self._overlapping_pair()
        deleted_id = b.shape_id
        b.delete()

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        slide = Presentation(buf).slides[0]

        # The allocator recycles the freed id for the next shape added.
        newcomer = slide.shapes.add_textbox(
            Inches(2), Inches(1), Inches(3), Inches(2)
        )
        assert newcomer.shape_id == deleted_id

        codes = [i.code for i in slide.lint().issues if i.code == "ShapeCollision"]
        assert codes, "a real collision must not be suppressed by a stale allowance"


class DescribeAllowanceCleanupOnGroupDelete:
    """Deleting a group must purge allowances naming its members too.

    Removing a group's element removes everything nested inside it, so
    every descendant id goes stale at once -- not just the group's own.
    """

    def _slide_with_grouped_shape(self):
        from power_pptx import Presentation
        from power_pptx.util import Inches

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(2))
        group = slide.shapes.add_group_shape()
        inner = group.shapes.add_textbox(
            Inches(2), Inches(1), Inches(3), Inches(2)
        )
        a.allow_overlap_with(inner)
        return prs, slide, a, group, inner

    def it_purges_a_group_members_id(self):
        _, _, a, group, inner = self._slide_with_grouped_shape()
        assert inner.shape_id in a.overlap_allowances

        group.delete()

        assert a.overlap_allowances == frozenset()

    def it_purges_ids_nested_more_than_one_level_deep(self):
        from power_pptx import Presentation
        from power_pptx.util import Inches

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        a = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
        outer = slide.shapes.add_group_shape()
        middle = outer.shapes.add_group_shape()
        deep = middle.shapes.add_textbox(
            Inches(2), Inches(1), Inches(2), Inches(1)
        )
        a.allow_overlap_with(deep)

        outer.delete()

        assert a.overlap_allowances == frozenset()

    def it_keeps_allowances_naming_shapes_outside_the_group(self):
        from power_pptx.util import Inches

        _, slide, a, group, _ = self._slide_with_grouped_shape()
        survivor = slide.shapes.add_textbox(
            Inches(6), Inches(1), Inches(1), Inches(1)
        )
        a.allow_overlap_with(survivor)

        group.delete()

        assert a.overlap_allowances == frozenset({survivor.shape_id})

    def it_does_not_suppress_a_collision_with_a_shape_reusing_a_member_id(self):
        import io

        from power_pptx import Presentation
        from power_pptx.util import Inches

        prs, _, _, group, inner = self._slide_with_grouped_shape()
        stale_id = inner.shape_id
        group.delete()

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        slide = Presentation(buf).slides[0]

        # Burn the group's own freed id first so the next shape lands on
        # the member id that used to be allowed.
        slide.shapes.add_textbox(Inches(7), Inches(4), Inches(0.5), Inches(0.5))
        newcomer = slide.shapes.add_textbox(
            Inches(2), Inches(1), Inches(3), Inches(2)
        )
        assert newcomer.shape_id == stale_id

        codes = [i.code for i in slide.lint().issues if i.code == "ShapeCollision"]
        assert codes, "a real collision must not be suppressed by a stale member id"


class DescribeRaggedEdgeCheck:
    """Side-by-side filled panels should end on one bottom line."""

    @staticmethod
    def _panel(slide, left, top, width, height):
        from power_pptx.enum.shapes import MSO_SHAPE

        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height)
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        return shape

    @staticmethod
    def _ragged(slide):
        return [i for i in slide.lint().issues if i.code == "RaggedEdge"]

    def it_flags_a_panel_that_ends_short_of_its_neighbour(self):
        _, slide = _new_blank_slide()
        self._panel(slide, 0.5, 1, 4, 5)
        self._panel(slide, 5, 1, 4, 2)
        short = self._panel(slide, 5, 3.25, 4, 2)

        issues = self._ragged(slide)

        assert [i.shapes for i in issues] == [(short,)]
        assert issues[0].severity is LintSeverity.WARNING
        assert issues[0].gap_emu == Inches(0.75)
        assert issues[0].to_dict()["gap_emu"] == Inches(0.75)

    def it_tolerates_sub_point_differences(self):
        _, slide = _new_blank_slide()
        self._panel(slide, 0.5, 1, 4, 5)
        right = self._panel(slide, 5, 1, 4, 5)
        right.height = right.height - Pt(1)

        assert self._ragged(slide) == []

    def it_ignores_a_panel_with_something_beneath_it(self):
        _, slide = _new_blank_slide()
        self._panel(slide, 0.5, 1, 4, 5)
        self._panel(slide, 5, 1, 4, 3)
        slide.shapes.add_textbox(Inches(5), Inches(4.5), Inches(4), Inches(0.5))

        assert self._ragged(slide) == []

    def it_ignores_nested_panels(self):
        _, slide = _new_blank_slide()
        self._panel(slide, 0.5, 1, 9, 5)
        self._panel(slide, 1, 1.5, 3, 1)

        assert self._ragged(slide) == []

    def it_ignores_panels_in_a_different_band(self):
        _, slide = _new_blank_slide()
        self._panel(slide, 0.5, 0.5, 3, 1)
        self._panel(slide, 5, 3, 4, 3)
        self._panel(slide, 0.5, 4, 4, 2)

        assert self._ragged(slide) == []

    def it_can_be_disabled_like_any_rule(self):
        _, slide = _new_blank_slide()
        self._panel(slide, 0.5, 1, 4, 5)
        self._panel(slide, 5, 1, 4, 2)

        assert not [i for i in slide.lint(disable=["RaggedEdge"]).issues if i.code == "RaggedEdge"]
        rules = slide.lint().to_sarif()["runs"][0]["tool"]["driver"]["rules"]
        assert any(rule["id"] == "RaggedEdge" for rule in rules)


class DescribeRaggedEdgeBadges:
    def it_ignores_a_badge_beside_a_taller_card(self):
        from power_pptx.enum.shapes import MSO_SHAPE

        _, slide = _new_blank_slide()
        for left, height in ((0.5, 3.0), (5.0, 0.35)):
            shape = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(1), Inches(3), Inches(height)
            )
            shape.fill.solid()
            shape.fill.fore_color.rgb = RGBColor(0xED, 0xEA, 0xFF)

        assert [i for i in slide.lint().issues if i.code == "RaggedEdge"] == []


class DescribeRaggedEdgeRows:
    @staticmethod
    def _panel(slide, left, top, width, height):
        from power_pptx.enum.shapes import MSO_SHAPE

        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height)
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        return shape

    @staticmethod
    def _ragged(slide):
        return [i for i in slide.lint().issues if i.code == "RaggedEdge"]

    def it_ignores_a_card_that_does_not_start_level_with_the_sidebar(self):
        _, slide = _new_blank_slide()
        self._panel(slide, 0.3, 0.3, 2.5, 6.9)
        self._panel(slide, 3.2, 2.0, 4, 2)

        assert self._ragged(slide) == []

    def it_ignores_a_card_far_from_the_tall_panel(self):
        _, slide = _new_blank_slide()
        self._panel(slide, 0.3, 1, 2, 5)
        self._panel(slide, 6.5, 1, 3, 2)

        assert self._ragged(slide) == []

    def it_flags_the_last_card_of_a_stack_that_starts_level(self):
        _, slide = _new_blank_slide()
        self._panel(slide, 0.5, 1, 4, 5)
        self._panel(slide, 4.75, 1, 4, 1.5)
        short = self._panel(slide, 4.75, 2.75, 4, 1.5)

        assert [i.shapes for i in self._ragged(slide)] == [(short,)]


class DescribeRaggedEdgePerRow:
    def it_judges_each_row_against_its_own_bottom(self):
        _, slide = _new_blank_slide()
        panel = DescribeRaggedEdgeRows._panel
        panel(slide, 0.5, 0.5, 4, 2.5)
        short = panel(slide, 4.75, 0.5, 4, 1.5)
        panel(slide, 0.5, 3.5, 4, 3.5)
        panel(slide, 4.75, 3.5, 4, 3.5)

        issues = [i for i in slide.lint().issues if i.code == "RaggedEdge"]

        assert [i.shapes for i in issues] == [(short,)]
        assert issues[0].gap_emu == Inches(1)


class DescribeLintScaling:
    """Linting a busy slide must not do per-pair work for shapes that never touch.

    These count calls rather than time anything, so a loaded machine cannot
    make them flaky: the number of shapes is doubled and the work must double
    with it, not quadruple.
    """

    @staticmethod
    def _grid(count, coloured=False):
        """`count` small text boxes laid out in rows of 20, none overlapping."""
        _, slide = _new_blank_slide()
        for n in range(count):
            left, top = Inches(0.2 + (n % 20) * 0.45), Inches(0.2 + (n // 20) * 0.3)
            box = slide.shapes.add_textbox(left, top, Inches(0.4), Inches(0.25))
            box.text_frame.text = "ab"
            run = box.text_frame.paragraphs[0].runs[0]
            run.font.size = Pt(6)
            if coloured:
                run.font.color.rgb = RGBColor(0x22, 0x22, 0x22)
        return slide

    @staticmethod
    def _count_calls(monkeypatch, name):
        import power_pptx.lint as lint_module

        calls = []
        original = getattr(lint_module, name)

        def counting(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(lint_module, name, counting)
        return calls

    @pytest.mark.parametrize("count", [40, 80])
    def it_reads_each_shapes_lint_metadata_once(self, monkeypatch, count):
        slide = self._grid(count)
        calls = self._count_calls(monkeypatch, "_shape_cNvPr")

        slide.lint()

        assert len(calls) == count

    @pytest.mark.parametrize("count", [40, 80])
    def it_measures_each_shapes_box_once(self, monkeypatch, count):
        slide = self._grid(count, coloured=True)
        calls = self._count_calls(monkeypatch, "_shape_frame")

        slide.lint()

        # One per shape, plus the layout's three footer placeholders.
        assert len(calls) == count + 3

    @pytest.mark.parametrize("count", [40, 80])
    def it_only_scores_pairs_of_shapes_that_overlap(self, monkeypatch, count):
        slide = self._grid(count)
        overlapping = slide.shapes.add_shape(1, Inches(0.2), Inches(0.2), Inches(0.5), Inches(0.5))
        calls = self._count_calls(monkeypatch, "_bbox_overlap")

        collisions = _collisions(slide)

        # The rectangle covers four boxes of the grid; nothing else touches.
        assert len(calls) == 4
        assert [c.shapes[1] for c in collisions] == [overlapping] * 4

    def it_finds_the_same_pairs_as_comparing_every_pair(self):
        from power_pptx.lint import _bbox_overlap, _overlapping_pairs

        rng = random.Random(7)
        boxes = []
        for _ in range(120):
            left, top = rng.randrange(0, 900), rng.randrange(0, 700)
            boxes.append((left, top, left + rng.randrange(0, 200), top + rng.randrange(0, 150)))

        brute_force = [
            (i, j)
            for i in range(len(boxes))
            for j in range(i + 1, len(boxes))
            if _bbox_overlap(boxes[i], boxes[j])[0] > 0
        ]

        assert _overlapping_pairs(boxes) == brute_force

    def it_does_not_evaluate_a_disabled_rule(self, monkeypatch):
        import power_pptx.lint as lint_module

        slide = self._grid(8, coloured=True)

        def must_not_run(*args, **kwargs):
            raise AssertionError("a disabled rule was evaluated")

        monkeypatch.setattr(lint_module, "_check_low_contrast", must_not_run)
        monkeypatch.setattr(lint_module, "_check_collisions", must_not_run)
        monkeypatch.setattr(lint_module, "_check_text_overflow", must_not_run)

        report = slide.lint(
            disable=["LowContrast", "ShapeCollision", "ShapeCollisionShadow", "TextOverflow"]
        )

        assert {i.code for i in report.issues} == {"MinFontSize"}

    def it_does_not_evaluate_rules_below_min_severity(self, monkeypatch):
        import power_pptx.lint as lint_module

        slide = self._grid(8, coloured=True)

        def must_not_run(*args, **kwargs):
            raise AssertionError("a rule that cannot reach min_severity was evaluated")

        for name in (
            "_check_min_font_size",
            "_check_low_contrast",
            "_check_collisions",
            "_check_off_grid_drift",
            "_check_z_order_anomalies",
            "_check_ragged_edges",
        ):
            monkeypatch.setattr(lint_module, name, must_not_run)

        assert slide.lint(min_severity="error").issues == []


# ---------------------------------------------------------------------------
# TextOverflow measurement
# ---------------------------------------------------------------------------

_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")

_SENTENCE = "Revenue grew faster than forecast across every region this quarter"


@pytest.fixture
def outfit():
    """Measure with the bundled Outfit face, whatever fonts the machine has."""
    from power_pptx.text import clear_registered_fonts, register_font_dir

    clear_registered_fonts()
    register_font_dir(_FONTS_DIR)
    yield "Outfit"
    clear_registered_fonts()


def _overflows(slide):
    return [i for i in slide.lint().issues if isinstance(i, TextOverflow)]


def _fixed_textbox(slide, left=1, top=1, width=4, height=1):
    """A wrapping text box whose size is fixed (no auto-size)."""
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    box.text_frame.word_wrap = True
    box.text_frame.auto_size = MSO_AUTO_SIZE.NONE
    return box


def _set_font(text_frame, family, size_pt=None):
    for paragraph in text_frame.paragraphs:
        for run in paragraph.runs:
            run.font.name = family
            if size_pt is not None:
                run.font.size = Pt(size_pt)


class DescribeTextOverflowAgreesWithFitText:
    """A frame ``fit_text`` has sized fits, and lint must say so."""

    def it_does_not_flag_frames_fit_text_has_sized(self, outfit):
        rng = random.Random(1)
        words = ["revenue", "growth", "margin", "outlook", "customer", "retention"]
        words += ["pipeline", "forecast", "quarterly", "regional", "platform", "adoption"]
        fitted = 0
        for _ in range(12):
            _, slide = _new_blank_slide()
            box = slide.shapes.add_textbox(
                Inches(1), Inches(1), Inches(rng.uniform(2, 6)), Inches(rng.uniform(0.6, 3))
            )
            box.text_frame.word_wrap = True
            box.text_frame.text = " ".join(rng.choice(words) for _ in range(rng.randint(6, 60)))
            try:
                box.text_frame.fit_text(font_family=outfit, max_size=40)
            except ValueError:
                continue
            fitted += 1

            assert _overflows(slide) == []

        assert fitted >= 8

    def it_agrees_when_fit_text_also_sets_the_line_spacing(self, outfit):
        _, slide = _new_blank_slide()
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1.5))
        box.text_frame.text = " ".join([_SENTENCE] * 2)
        box.text_frame.fit_text(font_family=outfit, max_size=40, line_spacing=1.0)

        assert _overflows(slide) == []

    def it_leaves_the_fitted_frame_alone_when_tidying(self, outfit):
        _, slide = _new_blank_slide()
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(2))
        box.text_frame.text = " ".join([_SENTENCE] * 2)
        box.text_frame.fit_text(font_family=outfit, max_size=60)
        before = box.text_frame.paragraphs[0].runs[0].font.size

        fixes = slide.tidy()

        assert fixes == []
        assert box.text_frame.auto_size == MSO_AUTO_SIZE.NONE
        assert box.text_frame.paragraphs[0].runs[0].font.size == before

    def it_agrees_with_a_box_sized_by_measure_text(self, outfit):
        # measure_text, and the native components built on it, size boxes with
        # the same line model lint applies, so a box the engine sized is never
        # reported, and one line more than it was sized for always is.
        from power_pptx.text import measure_text

        text = "Revenue grew faster than forecast"
        m = measure_text(text, Inches(2.5), size_pt=20, font_family=outfit, line_spacing=1.2)
        assert len(m.lines) == 2
        _, slide = _new_blank_slide()
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(2.5), m.height)
        box.text_frame.word_wrap = True
        box.text_frame.auto_size = MSO_AUTO_SIZE.NONE
        for side in ("left", "top", "right", "bottom"):
            setattr(box.text_frame, f"margin_{side}", 0)
        box.text_frame.text = text
        box.text_frame.paragraphs[0].line_spacing = 1.2
        _set_font(box.text_frame, outfit, 20)

        assert _overflows(slide) == []

        box.text_frame.text = text + " in every region"
        _set_font(box.text_frame, outfit, 20)
        assert len(_overflows(slide)) == 1

    def it_uses_the_fonts_own_line_height_in_a_table_cell(self, outfit):
        # In a table cell a line is the taller of 1.2 em and the font's own
        # ascent plus descent, as the engine measures it with in_table=True.
        # Outfit's own line height is about 1.26 em.
        import power_pptx.lint as lint_module
        from power_pptx.text.fonts import find_font_file

        font_file = find_font_file(outfit, False, False)

        assert lint_module._line_em(font_file) == pytest.approx(1.2)
        assert lint_module._line_em(font_file, in_table=True) > 1.25

    def it_still_flags_the_same_text_one_size_too_large(self, outfit):
        _, slide = _new_blank_slide()
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        box.text_frame.text = " ".join([_SENTENCE] * 2)
        size = box.text_frame.fit_text(font_family=outfit, max_size=60)
        _set_font(box.text_frame, outfit, size + 2)

        assert len(_overflows(slide)) == 1


class DescribeTextOverflowMeasurement:
    """Each run is measured at its effective size and typeface."""

    def it_measures_every_run_not_just_the_first(self, outfit):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide)
        paragraph = box.text_frame.paragraphs[0]
        note = paragraph.add_run()
        note.text = "Note: "
        note.font.size = Pt(8)
        note.font.name = outfit
        body = paragraph.add_run()
        body.text = _SENTENCE
        body.font.size = Pt(40)
        body.font.name = outfit

        issues = _overflows(slide)

        assert len(issues) == 1
        assert issues[0].severity == LintSeverity.ERROR
        assert issues[0].ratio > 3

    def it_measures_every_paragraph_not_just_the_first(self, outfit):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide)
        text_frame = box.text_frame
        text_frame.text = "Eyebrow"
        _set_font(text_frame, outfit, 9)
        run = text_frame.add_paragraph().add_run()
        run.text = "Revenue grew faster than forecast across every region"
        run.font.size = Pt(36)
        run.font.name = outfit

        assert len(_overflows(slide)) == 1

    def it_uses_the_size_set_on_the_paragraph_font(self, outfit):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide)
        box.text_frame.text = _SENTENCE
        box.text_frame.paragraphs[0].font.size = Pt(40)
        box.text_frame.paragraphs[0].font.name = outfit

        assert len(_overflows(slide)) == 1

    def it_uses_the_size_a_placeholder_inherits(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[5])  # Title Only
        title = slide.shapes.title
        title.text_frame.text = " ".join([_SENTENCE] * 3)
        title.text_frame.auto_size = MSO_AUTO_SIZE.NONE

        # 44pt inherited from the master title style: several lines too many.
        issues = _overflows(slide)

        assert [i.shapes for i in issues] == [(title,)]
        assert issues[0].ratio > 2

    def it_wraps_text_that_has_no_spaces(self, outfit):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide)
        box.text_frame.text = (
            "四半期の売上高は、すべての地域で予測を上回るペースで成長しました。"
            "企業向け更新と高いサービス付帯率が牽引しました。"
        )
        _set_font(box.text_frame, outfit, 18)

        # 58 full-width characters at 18pt need four lines; three fit.
        issues = _overflows(slide)

        assert len(issues) == 1
        assert issues[0].ratio == pytest.approx(4 / 3, rel=0.02)

    def it_breaks_an_overlong_word_instead_of_calling_it_unfittable(self, outfit):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide, width=3, height=2)
        box.text_frame.text = "https://example.com/reports/2026/q4/regional-performance"
        _set_font(box.text_frame, outfit, 14)

        assert _overflows(slide) == []

    def it_looks_inside_groups(self, outfit):
        _, slide = _new_blank_slide()
        group = slide.shapes.add_group_shape()
        box = group.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(0.5))
        box.text_frame.word_wrap = True
        box.text_frame.auto_size = MSO_AUTO_SIZE.NONE
        box.text_frame.text = " ".join([_SENTENCE] * 2)
        _set_font(box.text_frame, outfit, 24)

        issues = _overflows(slide)

        assert len(issues) == 1
        assert issues[0].shapes[0].name == box.name
        assert issues[0].severity == LintSeverity.ERROR

    def it_reports_a_table_row_too_short_for_its_text(self, outfit):
        _, slide = _new_blank_slide()
        frame = slide.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(3), Inches(0.8))
        cell = frame.table.cell(1, 0)
        cell.text = " ".join([_SENTENCE] * 3)
        _set_font(cell.text_frame, outfit, 18)

        issues = _overflows(slide)

        assert len(issues) == 1
        assert issues[0].shapes == (frame,)
        assert (issues[0].row, issues[0].col) == (1, 0)
        # Rows grow to fit when rendered, so this is stale geometry, not lost text.
        assert issues[0].severity == LintSeverity.WARNING
        assert "row 1" in issues[0].message

    def it_respects_the_text_frame_insets(self, outfit):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide, width=3, height=1)
        box.text_frame.text = "Revenue grew faster than forecast across every region"
        _set_font(box.text_frame, outfit, 18)
        assert _overflows(slide) == []

        box.text_frame.margin_top = box.text_frame.margin_bottom = Inches(0.25)

        assert len(_overflows(slide)) == 1

    def it_respects_exact_line_spacing(self, outfit):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide, width=6, height=1)
        box.text_frame.text = "One\nTwo\nThree"
        _set_font(box.text_frame, outfit, 12)
        assert _overflows(slide) == []

        for paragraph in box.text_frame.paragraphs:
            paragraph.line_spacing = Pt(30)

        issues = _overflows(slide)
        assert len(issues) == 1
        assert issues[0].overflow_pt == pytest.approx(90 - 64.8, abs=0.5)

    def it_reports_a_line_too_wide_when_word_wrap_is_off(self, outfit):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide, width=2, height=1)
        box.text_frame.word_wrap = False
        box.text_frame.text = _SENTENCE
        _set_font(box.text_frame, outfit, 18)

        issues = _overflows(slide)

        assert len(issues) == 1
        assert issues[0].dimension == "width"
        assert issues[0].ratio > 2

    def it_does_not_flag_a_short_uppercase_label(self, outfit):
        _, slide = _new_blank_slide()
        pill = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(1.3), Inches(0.3))
        pill.text_frame.text = "MOST POPULAR"
        _set_font(pill.text_frame, outfit, 9)

        assert _overflows(slide) == []

    def it_measures_an_uninstalled_font_without_warning(self):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide)
        box.text_frame.text = " ".join([_SENTENCE] * 4)
        _set_font(box.text_frame, "No Such Typeface", 24)

        # pytest turns warnings into errors: a FontMetricsWarning would fail here.
        issues = _overflows(slide)

        assert len(issues) == 1
        assert issues[0].estimated is True
        assert "'No Such Typeface' is not installed" in issues[0].message

    def it_says_how_far_the_text_overflows(self, outfit):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide, width=6, height=1)
        box.text_frame.text = "One\nTwo\nThree\nFour"
        _set_font(box.text_frame, outfit, 20)

        issue = _overflows(slide)[0]

        # Four 24pt lines in a 64.8pt frame (1in less the 0.05in insets).
        assert issue.dimension == "height"
        assert issue.ratio == pytest.approx(96 / 64.8, rel=0.01)
        assert issue.overflow_pt == pytest.approx(96 - 64.8, abs=0.5)
        assert issue.to_dict()["overflow_pt"] == issue.overflow_pt


def _long_text(sentences=3):
    return " ".join([_SENTENCE] * sentences)


def _codes(issues):
    return sorted((i.code, i.severity.value) for i in issues)


class DescribeTextOverflowOnAutoSizeFrames:
    """``add_text`` / ``add_textbox`` write ``<a:spAutoFit/>`` and resize nothing.

    The stored box is stale until a renderer lays the text out, so lint has to
    measure these frames and check the box they will really occupy.
    """

    def it_reports_a_default_text_box_that_will_grow_off_the_slide(self, outfit):
        from power_pptx import BBox

        _, slide = _new_blank_slide()
        box = slide.shapes.add_text(
            BBox.from_inches(1, 6.4, 3, 0.6), text=_long_text(), size_pt=24, font=outfit
        )
        assert box.text_frame.auto_size == MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT

        issues = slide.lint().issues

        # The overflow itself is repaired by the renderer (warning); the box
        # it grows into crossing the slide edge is not (error).
        assert _codes(issues) == [("OffSlide", "error"), ("TextOverflow", "warning")]
        off_slide = next(i for i in issues if isinstance(i, OffSlide))
        assert off_slide.side == "bottom"
        overflow = next(i for i in issues if isinstance(i, TextOverflow))
        assert overflow.auto_size == "SHAPE_TO_FIT_TEXT"

    def it_grows_the_box_down_from_a_top_anchor(self, outfit):
        _, slide = _new_blank_slide()
        box = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(3), Inches(0.5))
        box.text_frame.word_wrap = True
        box.text_frame.text = _long_text(2)
        _set_font(box.text_frame, outfit, 18)
        below = slide.shapes.add_shape(1, Inches(1), Inches(2), Inches(3), Inches(1))

        issues = slide.lint().issues

        # Stored boxes do not touch; the grown text box covers the rectangle.
        assert int(box.top) + int(box.height) < int(below.top)
        collisions = [i for i in issues if isinstance(i, ShapeCollision)]
        assert [c.shapes for c in collisions] == [(box, below)]
        assert not any(isinstance(i, OffSlide) for i in issues)

    def it_grows_a_bottom_anchored_box_upwards(self, outfit):
        from power_pptx.enum.text import MSO_ANCHOR

        _, slide = _new_blank_slide()
        box = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(3), Inches(0.5))
        box.text_frame.word_wrap = True
        box.text_frame.vertical_anchor = MSO_ANCHOR.BOTTOM
        box.text_frame.text = _long_text(2)
        _set_font(box.text_frame, outfit, 18)

        sides = [i.side for i in slide.lint().issues if isinstance(i, OffSlide)]

        assert sides == ["top"]

    def it_reports_a_line_that_will_grow_past_the_edge_with_wrap_off(self, outfit):
        _, slide = _new_blank_slide()
        box = slide.shapes.add_textbox(Inches(6), Inches(1), Inches(2), Inches(0.5))
        box.text_frame.text = _SENTENCE
        _set_font(box.text_frame, outfit, 24)
        assert box.text_frame.word_wrap is False

        issues = slide.lint().issues

        assert _codes(issues) == [("OffSlide", "error"), ("TextOverflow", "warning")]
        assert next(i for i in issues if isinstance(i, TextOverflow)).dimension == "width"

    def it_does_not_report_a_box_that_already_fits(self, outfit):
        _, slide = _new_blank_slide()
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        box.text_frame.text = "Short"
        _set_font(box.text_frame, outfit, 18)

        assert slide.lint().issues == []

    def it_warns_when_shrink_on_overflow_has_not_shrunk_anything(self, outfit):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide)
        box.text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        box.text_frame.text = _long_text()
        _set_font(box.text_frame, outfit, 24)

        issues = _overflows(slide)

        assert len(issues) == 1
        assert issues[0].severity == LintSeverity.WARNING
        assert issues[0].auto_size == "TEXT_TO_FIT_SHAPE"

    def it_measures_at_the_font_scale_a_shrunk_frame_stores(self, outfit):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide)
        box.text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        box.text_frame.text = _long_text(1)
        _set_font(box.text_frame, outfit, 24)
        assert len(_overflows(slide)) == 1
        norm = box.text_frame._bodyPr.normAutofit

        norm.set("fontScale", "55000")

        assert _overflows(slide) == []

    def it_reports_a_title_placeholder_that_inherits_shrink_on_overflow(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[5])  # Title Only
        title = slide.shapes.title
        title.text_frame.text = _long_text()

        issues = _overflows(slide)

        # The master's title bodyPr carries <a:normAutofit/>.
        assert len(issues) == 1
        assert issues[0].severity == LintSeverity.WARNING
        assert issues[0].auto_size == "TEXT_TO_FIT_SHAPE"

    def it_does_not_fail_lint_on_save_for_an_overflow_the_renderer_repairs(
        self, outfit, tmp_path
    ):
        prs, slide = _new_blank_slide()
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(0.5))
        box.text_frame.word_wrap = True
        box.text_frame.text = _long_text(1)
        _set_font(box.text_frame, outfit, 18)
        assert _overflows(slide)[0].severity == LintSeverity.WARNING
        prs.lint_on_save = "raise"

        prs.save(str(tmp_path / "deck.pptx"))


def _assert_fits(slide):
    assert _overflows(slide) == []


class DescribeAutoFixTextOverflowFitsTheText:
    """``auto_fix`` leaves text that fits, and never a state lint cannot see."""

    def it_stores_the_font_scale_that_makes_the_text_fit(self, outfit):
        from power_pptx.lint import _measure_text_body, _shape_text_target, _TextEnv

        _, slide = _new_blank_slide()
        box = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(3), Inches(1))
        box.text_frame.text = _long_text(1)
        _set_font(box.text_frame, outfit, 24)
        assert box.text_frame.auto_size is None
        report = slide.lint()

        fixes = report.auto_fix()

        assert len(fixes) == 1
        assert "font scale" in fixes[0]
        assert box.text_frame.auto_size == MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        scale = box.text_frame._bodyPr.normAutofit.get("fontScale")
        assert scale is not None
        assert 25000 <= int(scale) < 100000
        assert [i for i in report.issues if isinstance(i, TextOverflow)] == []
        # Measured at the stored scale, the text really does fit the frame.
        env = _TextEnv(slide)
        target = _shape_text_target(env, box)
        measure = _measure_text_body(
            env, target.tx_body, target.body, target.levels, target.width, target.height
        )
        assert measure.text_h <= measure.avail_h

    def it_does_not_leave_a_bare_shrink_setting_that_shrinks_nothing(self, outfit):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide)
        box.text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        box.text_frame.text = _long_text(1)
        _set_font(box.text_frame, outfit, 24)

        slide.tidy()

        assert box.text_frame._bodyPr.normAutofit.get("fontScale") is not None
        _assert_fits(slide)

    def it_reduces_the_sizes_of_a_frame_set_to_no_autofit(self, outfit):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide, width=4, height=1.5)
        box.text_frame.text = _long_text(2)
        _set_font(box.text_frame, outfit, 28)

        fixes = slide.tidy()

        assert "Reduced the font sizes" in fixes[0]
        # The author's explicit "no auto-fit" is kept; the sizes changed.
        assert box.text_frame.auto_size == MSO_AUTO_SIZE.NONE
        size = box.text_frame.paragraphs[0].runs[0].font.size
        assert size < Pt(28)
        _assert_fits(slide)

    def it_resizes_a_shape_set_to_fit_its_text(self, outfit):
        _, slide = _new_blank_slide()
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(0.5))
        box.text_frame.word_wrap = True
        box.text_frame.text = _long_text(1)
        _set_font(box.text_frame, outfit, 18)

        fixes = slide.tidy()

        assert fixes[0].startswith("Resized 'TextBox 1' to fit its text")
        assert box.height > Inches(0.5)
        assert box.text_frame.auto_size == MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT
        assert slide.lint().issues == []

    def it_resizes_then_moves_a_box_that_grows_off_the_slide(self, outfit):
        from power_pptx import BBox

        _, slide = _new_blank_slide()
        box = slide.shapes.add_text(
            BBox.from_inches(1, 6.4, 3, 0.6), text=_long_text(), size_pt=18, font=outfit
        )

        slide.tidy()

        assert int(box.top) + int(box.height) <= int(Inches(7.5))
        assert slide.lint().issues == []

    def it_grows_a_table_row_to_fit_its_text(self, outfit):
        _, slide = _new_blank_slide()
        frame = slide.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(3), Inches(0.8))
        cell = frame.table.cell(1, 0)
        cell.text = _long_text(2)
        _set_font(cell.text_frame, outfit, 14)
        before = frame.table.rows[1].height

        fixes = slide.tidy()

        assert fixes[0].startswith("Grew row 1")
        assert frame.table.rows[1].height > before
        assert frame.height == sum(row.height for row in frame.table.rows)
        _assert_fits(slide)

    def it_leaves_text_alone_that_would_have_to_become_illegible(self, outfit):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide, width=1, height=0.3)
        box.text_frame.text = _long_text(4)
        _set_font(box.text_frame, outfit, 24)
        before = box._element.xml

        fixes = slide.tidy()

        assert fixes == []
        assert box._element.xml == before
        assert len(_overflows(slide)) == 1

    def it_previews_without_changing_anything(self, outfit):
        _, slide = _new_blank_slide()
        box = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(3), Inches(1))
        box.text_frame.text = _long_text(1)
        _set_font(box.text_frame, outfit, 24)
        before = slide._element.xml

        fixes = slide.lint().auto_fix(dry_run=True)

        assert len(fixes) == 1
        assert slide._element.xml == before


def _off_slide_sides(slide):
    return sorted(i.side for i in slide.lint().issues if isinstance(i, OffSlide))


def _inches(shape):
    return tuple(round(int(v) / 914400, 3) for v in (shape.left, shape.top, shape.width, shape.height))


class DescribeRotatedGeometry:
    """A rotated shape covers its rotated extent, not its stored frame."""

    def it_does_not_report_a_rotated_shape_that_is_on_the_slide(self):
        _, slide = _new_blank_slide()
        # Stored frame starts an inch left of the slide; turned 90° the bar
        # covers x 0.25"–0.75", y 1.75"–4.75".
        bar = slide.shapes.add_shape(1, Inches(-1), Inches(3), Inches(3), Inches(0.5))
        bar.rotation = 90

        assert _off_slide_sides(slide) == []
        assert slide.tidy() == []
        assert _inches(bar) == (-1.0, 3.0, 3.0, 0.5)

    def it_reports_a_rotated_shape_whose_extent_leaves_the_slide(self):
        _, slide = _new_blank_slide()
        # Centre (5", 6.9"); turned 90° it spans y 4.9"–8.9", past the 7.5" edge.
        bar = slide.shapes.add_shape(1, Inches(3), Inches(6.5), Inches(4), Inches(0.8))
        bar.rotation = 90

        assert _off_slide_sides(slide) == ["bottom"]

    def it_moves_a_rotated_shape_by_its_rotated_extent(self):
        _, slide = _new_blank_slide()
        bar = slide.shapes.add_shape(1, Inches(8.5), Inches(3), Inches(3), Inches(0.5))
        bar.rotation = 90  # covers x 9.75"–10.25"

        slide.tidy()

        # Moved a quarter inch, not the 1.5" the unrotated frame suggests.
        assert _inches(bar) == (8.25, 3.0, 3.0, 0.5)
        assert _off_slide_sides(slide) == []

    def it_uses_the_extent_of_an_arbitrary_angle(self):
        from power_pptx.lint import _rotated_extent

        box = _rotated_extent((0, 0, 400, 200), 45)

        half_diagonal = 300 / math.sqrt(2)
        assert box == (
            math.floor(200 - half_diagonal),
            math.floor(100 - half_diagonal),
            math.ceil(200 + half_diagonal),
            math.ceil(100 + half_diagonal),
        )

    def it_finds_collisions_with_the_rotated_extent(self):
        _, slide = _new_blank_slide()
        bar = slide.shapes.add_shape(1, Inches(1), Inches(3), Inches(4), Inches(0.5))
        bar.rotation = 90  # covers x 2.75"–3.25", y 1.25"–5.25"
        above = slide.shapes.add_shape(1, Inches(2.5), Inches(1), Inches(1), Inches(1))

        collisions = _collisions(slide)

        assert [c.shapes for c in collisions] == [(bar, above)]


class DescribeOffSlideShrinkKeepsProportions:
    """A picture or group larger than the slide is scaled, not squashed."""

    @staticmethod
    def _png(width, height):
        from PIL import Image

        data = io.BytesIO()
        Image.new("RGB", (width, height), "#336699").save(data, format="PNG")
        data.seek(0)
        return data

    def it_scales_a_picture_proportionally(self):
        _, slide = _new_blank_slide()
        picture = slide.shapes.add_picture(self._png(1600, 400), Inches(-1), Inches(1), Inches(14))
        assert picture.width / picture.height == pytest.approx(4.0)

        slide.tidy()

        assert int(picture.width) <= int(Inches(10))
        assert picture.width / picture.height == pytest.approx(4.0, rel=1e-4)
        assert _off_slide_sides(slide) == []

    def it_scales_a_group_proportionally(self):
        _, slide = _new_blank_slide()
        group = slide.shapes.add_group_shape()
        group.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        group.shapes.add_shape(1, Inches(9), Inches(1), Inches(3), Inches(1))
        aspect = group.width / group.height

        slide.tidy()

        assert int(group.width) <= int(Inches(10))
        assert group.width / group.height == pytest.approx(aspect, rel=1e-4)
        assert _off_slide_sides(slide) == []

    def it_still_shortens_only_the_long_axis_of_a_plain_shape(self):
        _, slide = _new_blank_slide()
        bar = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(50), Inches(2))

        slide.tidy()

        assert _inches(bar) == (0.0, 1.0, 10.0, 2.0)


class DescribeGridSnapping:
    """Grid snapping must not pull shapes off an alignment they really have."""

    @staticmethod
    def _bar_chart():
        """Eight bars on one 5" baseline whose tops step 0.04" apart."""
        _, slide = _new_blank_slide()
        bars = []
        for n, value in enumerate(range(41, 49)):
            height = Inches(value * 0.04)
            bar = slide.shapes.add_shape(1, Inches(1 + n), Inches(5) - height, Inches(0.6), height)
            bars.append(bar)
        return slide, bars

    def it_does_not_chain_a_staircase_of_edges_into_one_grid_line(self):
        from power_pptx.lint import _cluster_edges

        steps = [int(Inches(3) + n * Inches(0.04)) for n in range(8)]

        clusters = _cluster_edges(steps, int(Inches(0.05)))

        assert max(n for _, n in clusters) == 2

    def it_leaves_bars_that_share_a_baseline_alone(self):
        slide, bars = self._bar_chart()
        before = [(_inches(bar)) for bar in bars]

        drift = [i for i in slide.lint().issues if isinstance(i, OffGridDrift)]
        slide.tidy(fix_grid_drift=True)

        assert drift == []
        assert [_inches(bar) for bar in bars] == before

    def it_skips_a_shape_whose_opposite_edge_is_on_a_grid_line(self):
        _, slide = _new_blank_slide()
        for n in range(4):
            slide.shapes.add_shape(1, Inches(1), Inches(0.5 + n), Inches(2), Inches(0.5))
        # Left edge 0.07" off the column, but right-aligned with the others.
        label = slide.shapes.add_shape(
            1, Inches(1) + 64000, Inches(5), Inches(2) - 64000, Inches(0.5)
        )

        drift = [i for i in slide.lint().issues if isinstance(i, OffGridDrift)]

        assert label not in [i.shapes[0] for i in drift]

    def it_does_not_snap_by_default_just_as_tidy_does_not(self):
        _, slide = _new_blank_slide()
        for n in range(4):
            slide.shapes.add_shape(1, Inches(6), Inches(0.5 + n), Inches(1), Inches(0.5))
        drifted = slide.shapes.add_shape(1, Inches(6) + 64000, Inches(5), Inches(1), Inches(0.5))
        report = slide.lint()
        assert any(isinstance(i, OffGridDrift) for i in report.issues)

        fixes = report.auto_fix()

        assert fixes == []
        assert int(drifted.left) == int(Inches(6)) + 64000
        assert report.auto_fix(fix_grid_drift=True)
        assert int(drifted.left) == int(Inches(6))


class DescribeConnectorCollisions:
    """A connector collides with what its line runs into, not its bounding box."""

    def it_ignores_a_shape_the_diagonal_passes_well_clear_of(self):
        from power_pptx.enum.shapes import MSO_CONNECTOR

        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
        slide.shapes.add_shape(1, Inches(6), Inches(4), Inches(2), Inches(1))
        slide.shapes.add_shape(1, Inches(4.5), Inches(1), Inches(1.2), Inches(1.3))
        # From A's bottom-right to B's top-left; 0.7" below C at C's left edge.
        slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Inches(3), Inches(2), Inches(6), Inches(4)
        )

        assert _collisions(slide) == []

    def it_reports_a_shape_the_line_runs_through(self):
        from power_pptx.enum.shapes import MSO_CONNECTOR

        _, slide = _new_blank_slide()
        box = slide.shapes.add_shape(1, Inches(4), Inches(2.5), Inches(1), Inches(1))
        line = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Inches(3), Inches(2), Inches(6), Inches(4)
        )

        assert [c.shapes for c in _collisions(slide)] == [(box, line)]

    def it_follows_the_flip_of_a_connector_drawn_right_to_left(self):
        from power_pptx.enum.shapes import MSO_CONNECTOR

        _, slide = _new_blank_slide()
        # Rising line from (3", 4") to (6", 2"): clear of a box at its top-left
        # corner, through one in the middle.
        corner = slide.shapes.add_shape(1, Inches(3), Inches(2), Inches(0.8), Inches(0.8))
        line = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Inches(3), Inches(4), Inches(6), Inches(2)
        )

        assert _collisions(slide) == []

        middle = slide.shapes.add_shape(1, Inches(4.25), Inches(2.75), Inches(0.5), Inches(0.5))

        assert [c.shapes for c in _collisions(slide)] == [(line, middle)]
        assert corner.name not in {s.name for c in _collisions(slide) for s in c.shapes}

    def it_ignores_connectors_whose_lines_do_not_cross(self):
        from power_pptx.enum.shapes import MSO_CONNECTOR

        _, slide = _new_blank_slide()
        slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Inches(1), Inches(1), Inches(4), Inches(4)
        )
        slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Inches(2), Inches(1), Inches(5), Inches(4)
        )

        assert _collisions(slide) == []


class DescribeZOrderAnomalyIntent:
    def it_ignores_a_translucent_scrim_over_a_photo(self):
        _, slide = _new_blank_slide()
        photo = slide.shapes.add_picture(
            DescribeOffSlideShrinkKeepsProportions._png(400, 300),
            Inches(1),
            Inches(1),
            Inches(4),
            Inches(3),
        )
        scrim = slide.shapes.add_shape(1, Inches(0.5), Inches(0.5), Inches(6), Inches(4))
        scrim.fill.solid()
        scrim.fill.fore_color.rgb = RGBColor(0, 0, 0)
        scrim.fill.fore_color.alpha = 0.35

        anomalies = [i for i in slide.lint().issues if isinstance(i, ZOrderAnomaly)]

        assert anomalies == []
        assert photo.name

    def it_honours_a_shared_lint_group(self):
        _, slide = _new_blank_slide()
        small = slide.shapes.add_textbox(Inches(2), Inches(2), Inches(1), Inches(1))
        small.text_frame.text = "under"
        cover = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(4), Inches(4))
        cover.fill.solid()
        cover.fill.fore_color.rgb = RGBColor(0, 0, 255)
        assert any(isinstance(i, ZOrderAnomaly) for i in slide.lint().issues)

        slide.lint_group("hero", small, cover)

        assert not any(isinstance(i, ZOrderAnomaly) for i in slide.lint().issues)


class DescribeLintIsReadOnly:
    def it_does_not_change_the_deck(self):
        from tests.test_accessibility import foreign_deck, slide_snapshot

        prs, before = foreign_deck()

        for slide in prs.slides:
            slide.lint()
            slide.lint(include_effect_bleed=True)

        assert slide_snapshot(prs) == before

    def it_does_not_change_the_deck_when_previewing_fixes(self):
        from tests.test_accessibility import foreign_deck, slide_snapshot

        prs, before = foreign_deck()
        slide = prs.slides[0]
        slide.shapes.add_shape(1, Inches(9), Inches(1), Inches(3), Inches(1)).text = " ".join(
            [_SENTENCE] * 3
        )
        before = slide_snapshot(prs)

        assert slide.lint().auto_fix(dry_run=True)
        assert slide_snapshot(prs) == before


class DescribeMalformedGeometry:
    def it_reports_a_negative_width_instead_of_crashing(self):
        _, slide = _new_blank_slide()
        panel = slide.shapes.add_shape(5, Inches(1), Inches(1), Inches(3), Inches(2))
        panel.fill.solid()
        panel.fill.fore_color.rgb = RGBColor(0x20, 0x40, 0x60)
        slide.shapes.add_shape(5, Inches(5), Inches(1), Inches(3), Inches(3)).fill.solid()
        panel._element.spPr.xfrm.ext.set("cx", str(-int(Inches(3))))

        issues = slide.lint().issues

        geometry = [i for i in issues if i.code == "InvalidGeometry"]
        assert [(i.shapes[0].name, i.dimension) for i in geometry] == [(panel.name, "width")]
        assert geometry[0].severity == LintSeverity.ERROR
        assert geometry[0].value_emu == -int(Inches(3))
        assert slide.tidy() == []


# ---------------------------------------------------------------------------
# Characterisation: behaviour on the less travelled paths of the linter
# ---------------------------------------------------------------------------


def _style(size=18.0, spacing=0.0, caps=False):
    from power_pptx.lint import _RunStyle

    return _RunStyle(size=size, font_file=None, spacing=spacing, caps=caps, line_em=1.2)


def _qn(tag):
    from power_pptx.oxml.ns import qn

    return qn(tag)


def _measure(slide, shape):
    from power_pptx.lint import _measure_text_body, _shape_text_target, _TextEnv

    env = _TextEnv(slide)
    target = _shape_text_target(env, shape)
    return _measure_text_body(
        env, target.tx_body, target.body, target.levels, target.width, target.height
    )


class _Unreadable:
    """A shape-like object whose every attribute read fails."""

    def __getattr__(self, name):
        raise RuntimeError(name)


class DescribeConnectorPathGeometry:
    def it_routes_an_elbow_connector_through_its_adjustment_point(self):
        from lxml import etree

        from power_pptx.enum.shapes import MSO_CONNECTOR
        from power_pptx.lint import _connector_path

        _, slide = _new_blank_slide()
        elbow = slide.shapes.add_connector(
            MSO_CONNECTOR.ELBOW, Inches(1), Inches(1), Inches(5), Inches(3)
        )
        geom = elbow._element.spPr.find(_qn("a:prstGeom"))
        etree.SubElement(geom.find(_qn("a:avLst")), _qn("a:gd"), name="adj1", fmla="val 25000")

        path = _connector_path(elbow)

        one, two, three, five = (int(Inches(v)) for v in (1, 2, 3, 5))
        assert path == [
            ((one, one), (two, one)),
            ((two, one), (two, three)),
            ((two, three), (five, three)),
        ]

    def it_takes_the_midpoint_when_the_adjustment_is_unreadable(self):
        from lxml import etree

        from power_pptx.enum.shapes import MSO_CONNECTOR
        from power_pptx.lint import _connector_path

        _, slide = _new_blank_slide()
        curve = slide.shapes.add_connector(
            MSO_CONNECTOR.CURVE, Inches(5), Inches(1), Inches(1), Inches(3)
        )
        geom = curve._element.spPr.find(_qn("a:prstGeom"))
        etree.SubElement(geom.find(_qn("a:avLst")), _qn("a:gd"), name="adj1", fmla="val x")

        path = _connector_path(curve)

        assert [start for start, _ in path] == [
            (int(Inches(5)), int(Inches(1))),
            (int(Inches(3)), int(Inches(1))),
            (int(Inches(3)), int(Inches(3))),
        ]

    def it_draws_a_two_segment_bend(self):
        from power_pptx.enum.shapes import MSO_CONNECTOR
        from power_pptx.lint import _connector_path

        _, slide = _new_blank_slide()
        bend = slide.shapes.add_connector(
            MSO_CONNECTOR.ELBOW, Inches(1), Inches(3), Inches(4), Inches(1)
        )
        bend._element.spPr.find(_qn("a:prstGeom")).set("prst", "bentConnector2")

        path = _connector_path(bend)

        one, three, four = (int(Inches(v)) for v in (1, 3, 4))
        assert path == [((one, three), (four, three)), ((four, three), (four, one))]

    def but_it_has_no_path_for_an_unknown_bend_or_a_rotated_connector(self):
        from power_pptx.enum.shapes import MSO_CONNECTOR
        from power_pptx.lint import _connector_path

        _, slide = _new_blank_slide()
        odd = slide.shapes.add_connector(
            MSO_CONNECTOR.ELBOW, Inches(1), Inches(1), Inches(4), Inches(3)
        )
        odd._element.spPr.find(_qn("a:prstGeom")).set("prst", "bentConnector4")
        turned = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Inches(1), Inches(1), Inches(4), Inches(3)
        )
        turned.rotation = 30

        assert _connector_path(odd) is None
        assert _connector_path(turned) is None

    def and_it_has_no_path_for_a_negative_extent_or_an_unreadable_shape(self):
        from power_pptx.enum.shapes import MSO_CONNECTOR
        from power_pptx.lint import _connector_path

        _, slide = _new_blank_slide()
        line = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Inches(1), Inches(1), Inches(4), Inches(3)
        )
        line._element.spPr.xfrm.ext.set("cx", str(-int(Inches(3))))

        assert _connector_path(line) is None
        assert _connector_path(_Unreadable()) is None  # pyright: ignore[reportArgumentType]


class DescribeTextLayoutUnits:
    def it_breaks_on_either_side_of_each_wide_character(self):
        from power_pptx.lint import _text_atoms

        atoms = _text_atoms([("ab ABC漢字DEF  gh", _style())])

        assert [[text for text, _ in pieces] for _, _, _, pieces in atoms] == [
            ["ab"],
            ["ABC"],
            ["漢"],
            ["字"],
            ["DEF"],
            ["gh"],
        ]
        # Only an atom that follows whitespace owes a space before it.
        spaces = [space for _, _, space, _ in atoms]
        assert spaces[0] == 0.0
        assert spaces[1] > 0.0
        assert spaces[2:5] == [0.0, 0.0, 0.0]
        assert spaces[5] == spaces[1]

    def it_keeps_a_word_that_changes_style_as_one_atom(self):
        from power_pptx.lint import _text_atoms

        small, large = _style(10), _style(30)

        atoms = _text_atoms([("Rev", small), ("enue", large), (" up", small)])

        assert [[text for text, _ in pieces] for _, _, _, pieces in atoms] == [
            ["Rev", "enue"],
            ["up"],
        ]
        assert atoms[0][1] == pytest.approx(36.0)

    def it_measures_a_line_that_cannot_wrap_run_by_run(self):
        from power_pptx.lint import _ref_space_width, _text_width, _wrap_fragments

        style = _style()
        space = _ref_space_width(None) * style.size / 100

        lines = _wrap_fragments(
            [("Alpha", style), ("  ", style), ("beta", style), (" gamma", style)],
            1.0,
            1.0,
            False,
        )

        expected = _text_width("Alpha", style) + space + _text_width("beta", style)
        expected += space + _text_width("gamma", style)
        assert lines == [(pytest.approx(expected), pytest.approx(21.6))]

    def but_a_line_with_no_visible_text_has_no_lines(self):
        from power_pptx.lint import _wrap_fragments

        assert _wrap_fragments([("   ", _style()), ("", _style())], 1.0, 1.0, False) == []
        assert _wrap_fragments([("   ", _style())], 100.0, 100.0, True) == []

    def it_measures_an_unwrapped_line_of_whitespace_as_an_empty_line(self):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide, width=4, height=2)
        box.text_frame.word_wrap = False
        box.text_frame.text = "Alpha\v   \vbeta"
        _set_font(box.text_frame, "Inter", 20)

        measure = _measure(slide, box)

        # The blank line is as tall as the break that ends it, which has the
        # default 18pt size: _set_font only sizes the runs.
        assert measure.lines == 3
        assert measure.text_h == pytest.approx((24 + 21.6 + 24) * 12700)


class DescribeTextSourceResolution:
    def it_uses_the_sizes_a_frames_own_list_style_sets(self):
        from lxml import etree

        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide, width=3, height=1)
        box.text_frame.text = _SENTENCE
        lst = box._element.txBody.find(_qn("a:lstStyle"))
        level = etree.SubElement(lst, _qn("a:lvl1pPr"))
        etree.SubElement(level, _qn("a:defRPr"), sz="4000")
        assert _overflows(slide) != []

        lst.remove(level)

        assert _overflows(slide) == []

    def it_reads_only_the_frames_own_sources_for_a_shape_it_cannot_ask(self):
        from power_pptx.lint import _TextEnv

        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide)
        env = _TextEnv(slide)
        tx_body = box._element.txBody

        body_prs, levels = env.sources(_Unreadable(), tx_body)  # pyright: ignore

        assert body_prs == [tx_body.find(_qn("a:bodyPr"))]
        assert levels == [env.default_style()]

    def it_stops_at_a_base_placeholder_it_cannot_read(self):
        from power_pptx.lint import _TextEnv

        class Placeholder:
            is_placeholder = True

            def __init__(self, element):
                self._element = element

            @property
            def _base_placeholder(self):
                raise KeyError("layout placeholder")

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        title = slide.shapes.title
        title.text_frame.text = "Title"
        env = _TextEnv(slide)

        _, levels = env.sources(Placeholder(title._element), title._element.txBody)  # pyright: ignore

        assert levels == [env.master_style("title"), env.default_style()]

    def it_skips_a_base_placeholder_that_has_no_text_body(self):
        from copy import deepcopy

        from power_pptx.lint import _TextEnv

        class Base:
            is_placeholder = True

            def __init__(self, element, base):
                self._element = element
                self._base_placeholder = base

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        title = slide.shapes.title
        title.text_frame.text = "Title"
        master_title = title._base_placeholder._base_placeholder
        bare = deepcopy(title._base_placeholder._element)
        bare.remove(bare.txBody)
        shape = Base(title._element, Base(bare, master_title))
        env = _TextEnv(slide)

        body_prs, levels = env.sources(shape, title._element.txBody)  # pyright: ignore

        assert body_prs == [
            title._element.txBody.find(_qn("a:bodyPr")),
            master_title._element.txBody.find(_qn("a:bodyPr")),
        ]
        assert levels[-2:] == [env.master_style("title"), env.default_style()]


class DescribeUniformTextDetection:
    def it_treats_a_frame_with_one_whole_point_style_as_fit_text_output(self):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide)
        box.text_frame.text = _SENTENCE
        _set_font(box.text_frame, "Inter", 18)

        assert _measure(slide, box).uniform == ("Inter", False, False, 18, None)

    @pytest.mark.parametrize("attr", [("spc", "200"), ("cap", "all")])
    def but_not_one_with_letter_spacing_or_capitals(self, attr):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide)
        box.text_frame.text = _SENTENCE
        _set_font(box.text_frame, "Inter", 18)
        box.text_frame.paragraphs[0].runs[0]._r.get_or_add_rPr().set(*attr)

        assert _measure(slide, box).uniform is None


class DescribeTableRowMeasurementEdges:
    def it_has_nothing_to_measure_in_a_shape_that_is_not_a_table(self):
        from power_pptx.chart.data import CategoryChartData
        from power_pptx.enum.chart import XL_CHART_TYPE
        from power_pptx.lint import _table_row_needs, _TextEnv

        _, slide = _new_blank_slide()
        box = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(1), Inches(1))
        data = CategoryChartData()
        data.categories = ["a", "b"]
        data.add_series("s", (1, 2))
        chart = slide.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1), Inches(4), Inches(3), data
        )

        assert _table_row_needs(_TextEnv(slide), box) == []
        assert _table_row_needs(_TextEnv(slide), chart) == []

    def it_skips_a_row_whose_height_is_unreadable(self, outfit):
        _, slide = _new_blank_slide()
        frame = slide.shapes.add_table(2, 1, Inches(1), Inches(1), Inches(2), Inches(0.6))
        for row in range(2):
            frame.table.cell(row, 0).text = _long_text(2)
            _set_font(frame.table.cell(row, 0).text_frame, outfit, 14)
        frame.table._tbl.tr_lst[0].set("h", "tall")

        issues = _overflows(slide)

        assert [(i.row, i.col) for i in issues] == [(1, 0)]

    def it_treats_a_cell_with_unreadable_merge_attributes_as_merged(self, outfit):
        _, slide = _new_blank_slide()
        frame = slide.shapes.add_table(1, 2, Inches(1), Inches(1), Inches(4), Inches(0.3))
        for col in range(2):
            frame.table.cell(0, col).text = _long_text(2)
            _set_font(frame.table.cell(0, col).text_frame, outfit, 14)
        frame.table.cell(0, 0)._tc.set("gridSpan", "wide")

        issues = _overflows(slide)

        # The unreadable cell is skipped and counts as one grid column.
        assert [(i.row, i.col) for i in issues] == [(0, 1)]


class DescribeAutoFixWhenTheIssueIsStale:
    """``auto_fix`` re-measures, so an issue the slide no longer has fixes nothing."""

    @staticmethod
    def _overflowing_box(slide, outfit):
        box = _fixed_textbox(slide)
        box.text_frame.text = _long_text(3)
        _set_font(box.text_frame, outfit, 24)
        return box

    def it_leaves_a_frame_whose_text_now_fits(self, outfit):
        _, slide = _new_blank_slide()
        box = self._overflowing_box(slide, outfit)
        report = slide.lint()
        assert _codes(report.issues) == [("TextOverflow", "error")]
        box.text_frame.text = "Short"
        before = box._element.xml

        assert report.auto_fix() == []
        assert box._element.xml == before

    def it_leaves_a_frame_whose_text_is_gone(self, outfit):
        _, slide = _new_blank_slide()
        box = self._overflowing_box(slide, outfit)
        report = slide.lint()
        box.text_frame.text = ""

        assert report.auto_fix() == []

    def it_leaves_a_shape_whose_text_frame_is_gone(self, outfit):
        _, slide = _new_blank_slide()
        box = self._overflowing_box(slide, outfit)
        report = slide.lint()
        box._element.remove(box._element.txBody)

        assert report.auto_fix() == []

    def it_leaves_a_table_row_that_now_fits_or_is_gone(self, outfit):
        _, slide = _new_blank_slide()
        frame = slide.shapes.add_table(2, 1, Inches(1), Inches(1), Inches(3), Inches(0.6))
        frame.table.cell(1, 0).text = _long_text(3)
        _set_font(frame.table.cell(1, 0).text_frame, outfit, 14)
        report = slide.lint()
        assert [i.row for i in report.issues if isinstance(i, TextOverflow)] == [1]
        frame.table.cell(1, 0).text = "ok"
        _set_font(frame.table.cell(1, 0).text_frame, outfit, 8)

        assert report.auto_fix() == []

        frame.table.cell(1, 0).text = _long_text(3)
        _set_font(frame.table.cell(1, 0).text_frame, outfit, 14)
        report = slide.lint()
        assert [i.row for i in report.issues if isinstance(i, TextOverflow)] == [1]
        tbl = frame.table._tbl
        tbl.remove(tbl.tr_lst[1])

        assert report.auto_fix() == []


class DescribeAutoFixLimits:
    def it_will_not_bake_a_size_below_one_point(self, outfit):
        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide, width=3, height=0.6)
        box.text_frame.text = _long_text(1)
        _set_font(box.text_frame, outfit, 20)
        tiny = box.text_frame.paragraphs[0].add_run()
        tiny.text = " fine print"
        tiny.font.size = Pt(1.5)
        tiny.font.name = outfit
        assert "TextOverflow" in {i.code for i in slide.lint().issues}
        before = box._element.xml

        assert slide.tidy() == []
        assert box._element.xml == before

    def it_cannot_store_a_font_scale_on_a_frame_without_body_properties(self, outfit):
        _, slide = _new_blank_slide()
        box = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(3), Inches(1))
        box.text_frame.text = _long_text(1)
        _set_font(box.text_frame, outfit, 24)
        tx_body = box._element.txBody
        tx_body.remove(tx_body.find(_qn("a:bodyPr")))
        assert _codes(slide.lint().issues) == [("TextOverflow", "error")]

        assert slide.tidy() == []

    def it_does_not_move_a_shape_with_a_negative_extent(self):
        _, slide = _new_blank_slide()
        bar = slide.shapes.add_shape(1, Inches(-1), Inches(1), Inches(3), Inches(1))
        bar._element.spPr.xfrm.ext.set("cx", str(-int(Inches(3))))
        report = slide.lint()
        assert {i.code for i in report.issues} == {"InvalidGeometry", "OffSlide"}

        assert report.auto_fix() == []
        assert int(bar.left) == -int(Inches(1))

    def it_snaps_a_drifted_top_edge_onto_the_grid(self):
        _, slide = _new_blank_slide()
        for n in range(4):
            slide.shapes.add_shape(1, Inches(0.5 + 2 * n), Inches(3), Inches(1), Inches(0.5))
        drifted = slide.shapes.add_shape(1, Inches(8.5), Inches(3) + 70000, Inches(1), Inches(1))
        report = slide.lint()
        assert [(i.axis, i.shapes[0]) for i in report.issues if isinstance(i, OffGridDrift)] == [
            ("top", drifted)
        ]

        fixes = report.auto_fix(fix_grid_drift=True)

        assert fixes == [
            f"Snapped '{drifted.name}' top edge from {int(Inches(3)) + 70000} to "
            f"{int(Inches(3))} EMU (grid)."
        ]
        assert int(drifted.top) == int(Inches(3))

    def it_previews_a_grid_snap_without_moving_the_shape(self):
        _, slide = _new_blank_slide()
        for n in range(4):
            slide.shapes.add_shape(1, Inches(0.5 + 2 * n), Inches(3), Inches(1), Inches(0.5))
        drifted = slide.shapes.add_shape(1, Inches(8.5), Inches(3) + 70000, Inches(1), Inches(1))

        fixes = slide.lint().auto_fix(dry_run=True, fix_grid_drift=True)

        assert len(fixes) == 1
        assert int(drifted.top) == int(Inches(3)) + 70000


class DescribeMinFontSizeEdges:
    def it_ignores_a_shape_it_cannot_read(self):
        from power_pptx.lint import _check_min_font_size

        assert _check_min_font_size(_Unreadable()) == []  # pyright: ignore[reportArgumentType]

    def it_ignores_runs_without_a_size_of_their_own(self):
        _, slide = _new_blank_slide()
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
        box.text_frame.text = "inherits its size"
        box.text_frame.paragraphs[0].runs[0]._r.get_or_add_rPr().set("sz", "0")

        assert [i for i in slide.lint().issues if isinstance(i, MinFontSize)] == []


class DescribeContrastBackdropEdges:
    @staticmethod
    def _label(slide, rgb, left=2, top=2):
        box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(2), Inches(0.5))
        box.text_frame.text = "Label"
        box.text_frame.paragraphs[0].runs[0].font.color.rgb = RGBColor(*rgb)
        return box

    def it_does_not_judge_text_on_its_own_gradient_fill(self):
        _, slide = _new_blank_slide()
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        label = self._label(slide, (0xF8, 0xF8, 0xF8))
        assert [type(i) for i in slide.lint().issues] == [LowContrast]

        label.fill.gradient()

        assert slide.lint().issues == []

    def it_looks_past_a_card_whose_shadow_alone_reaches_the_text(self):
        _, slide = _new_blank_slide()
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        card = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(3), Inches(0.9))
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(0, 0, 0)
        card.shadow.blur_radius = Pt(40)
        below = self._label(slide, (0xF8, 0xF8, 0xF8), left=1, top=2.05)
        beside = self._label(slide, (0xF8, 0xF8, 0xF8), left=4.05, top=1)

        report = slide.lint(include_effect_bleed=True, disable=["ShapeCollisionShadow"])

        assert [(type(i), i.shapes) for i in report.issues] == [
            (LowContrast, (below,)),
            (LowContrast, (beside,)),
        ]


class DescribeLintSkipInsideGroups:
    def it_silences_an_issue_on_a_shape_inside_a_group(self, outfit):
        _, slide = _new_blank_slide()
        group = slide.shapes.add_group_shape()
        box = group.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(0.5))
        box.text_frame.word_wrap = True
        box.text_frame.auto_size = MSO_AUTO_SIZE.NONE
        box.text_frame.text = _long_text(2)
        _set_font(box.text_frame, outfit, 24)
        assert len(_overflows(slide)) == 1

        box.lint_skip = {"TextOverflow"}

        assert _overflows(slide) == []


class DescribeMinSeverityMember:
    def it_accepts_a_severity_member_as_the_threshold(self):
        _, slide = _new_blank_slide()
        slide.shapes.add_shape(1, Inches(-1), Inches(1), Inches(1), Inches(1))
        label = slide.shapes.add_textbox(Inches(5), Inches(5), Inches(2), Inches(1))
        label.text_frame.text = "x"
        label.text_frame.paragraphs[0].runs[0].font.size = Pt(6)

        warnings = slide.lint(min_severity=LintSeverity.WARNING).issues
        errors = slide.lint(min_severity=LintSeverity.ERROR).issues

        assert [i.code for i in warnings] == ["OffSlide", "MinFontSize"]
        assert [i.code for i in errors] == ["OffSlide"]


_HYPHENATED = (
    "Our state-of-the-art end-to-end platform gives cross-functional teams self-service "
    "year-over-year reporting with best-in-class customer-facing dashboards"
)
_KINSOKU = (
    "四半期の売上高は、すべての地域で予測を上回るペースで成長しました。「企業向け更新」と"
    "高いサービス付帯率が牽引しました。ちょっとしたニュースです。"
)


class DescribeTextOverflowBreaksLinesLikeTheEngine:
    """Lint wraps a line where ``fit_text`` and ``measure_text`` wrap it."""

    @staticmethod
    def _lines(text, width_in, font, size_pt=18):
        """``(lint's line count, the engine's)`` for `text` in a frame `width_in` wide."""
        from power_pptx.text import measure_text

        _, slide = _new_blank_slide()
        box = _fixed_textbox(slide, width=width_in, height=6)
        for side in ("left", "top", "right", "bottom"):
            setattr(box.text_frame, f"margin_{side}", 0)
        box.text_frame.text = text
        _set_font(box.text_frame, font, size_pt)
        engine = measure_text(
            text, Inches(width_in), size_pt=size_pt, font_family=font, break_long_words=True
        )
        return _measure(slide, box).lines, len(engine.lines)

    @pytest.mark.parametrize("width_in", [1.3, 1.7, 2.1, 2.6, 3.2])
    def it_breaks_after_a_hyphen(self, outfit, width_in):
        lint_lines, engine_lines = self._lines(_HYPHENATED, width_in, outfit)

        assert lint_lines == engine_lines

    @pytest.mark.parametrize("width_in", [1.0, 1.4, 2.0, 2.3])
    def it_breaks_a_path_that_starts_the_paragraph_after_its_slashes(self, outfit, width_in):
        url = "https://example.com/reports/2026/q4/regional/summary/index.html"

        lint_lines, engine_lines = self._lines(url, width_in, outfit)

        assert lint_lines == engine_lines

    @pytest.mark.parametrize(
        ("text", "width_in"),
        [
            ("Full details at https://example.com/reports/2026/q4", 1.5),
            ("Full details at https://example.com/reports/2026/q4", 2.2),
            ("Details:\vhttps://example.com/reports/2026/q4/regional/summary", 1.4),
        ],
    )
    def but_it_cuts_a_path_near_a_space_where_the_box_ends(self, outfit, text, width_in):
        # LibreOffice keeps such a path whole on the next line, cutting it at
        # the edge of the box rather than after one of its slashes.
        lint_lines, engine_lines = self._lines(text, width_in, outfit)

        assert lint_lines == engine_lines

    @pytest.mark.parametrize("width_in", [1.1, 1.9, 2.7, 3.4])
    def it_keeps_closing_punctuation_off_the_start_of_a_line(self, outfit, width_in):
        lint_lines, engine_lines = self._lines(_KINSOKU, width_in, outfit)

        assert lint_lines == engine_lines

    def it_keeps_words_joined_by_a_no_break_space_together(self, outfit):
        text = " ".join(["Delivered in Q4 2026"] * 6)

        lint_lines, engine_lines = self._lines(text, 2.0, outfit)

        assert lint_lines == engine_lines

    def it_does_not_report_a_frame_fit_text_sized_for_hyphenated_text(self, outfit):
        flagged = 0
        for width_in, height_in in [(1.6, 1.2), (2.2, 0.9), (3.0, 1.4), (2.6, 2.0), (1.9, 2.4)]:
            _, slide = _new_blank_slide()
            box = slide.shapes.add_textbox(
                Inches(1), Inches(1), Inches(width_in), Inches(height_in)
            )
            box.text_frame.word_wrap = True
            box.text_frame.text = _HYPHENATED
            box.text_frame.fit_text(font_family=outfit, max_size=40)
            flagged += len(_overflows(slide))

        assert flagged == 0
