"""Unit-test suite for `power_pptx.lint`."""

from __future__ import annotations

import io

import pytest

from power_pptx import Presentation
from power_pptx.dml.color import RGBColor
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
        # and triggers the refresh.
        for i in range(4):
            slide.shapes.add_shape(
                1, Inches(6), Inches(0.5 + i * 1.0), Inches(1), Inches(0.5)
            )
        slide.shapes.add_shape(
            1, Inches(6) + 30000, Inches(5), Inches(1), Inches(0.5)
        )

        report = slide.lint(include_effect_bleed=True)
        assert any(isinstance(i, OffSlideShadow) for i in report.issues)
        report.auto_fix()  # snaps the drift offender; triggers refresh
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
