"""Unit-test suite for `power_pptx.lint`."""

from __future__ import annotations

import io

import pytest

from power_pptx import Presentation
from power_pptx.dml.color import RGBColor
from power_pptx.lint import (
    LintSeverity,
    LowContrast,
    MasterPlaceholderCollision,
    MinFontSize,
    OffGridDrift,
    OffSlide,
    OffSlideShadow,
    ShapeCollision,
    ShapeCollisionShadow,
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
