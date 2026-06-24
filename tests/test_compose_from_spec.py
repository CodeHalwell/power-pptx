"""Tests for the recipe-dispatch / interpolation / YAML path of from_spec."""

from __future__ import annotations

import textwrap

import pytest

from power_pptx.compose import from_spec, from_yaml
from power_pptx.enum.shapes import MSO_SHAPE_TYPE


class DescribeRecipeDispatch:
    """Recipe-named layouts route to the styled recipes module."""

    def it_routes_kpi_layout_to_kpi_slide_recipe(self):
        prs = from_spec({
            "slides": [{
                "layout": "kpi",
                "title": "Run-rate",
                "kpis": [
                    {"label": "ARR", "value": "$182M", "delta": 0.27},
                ],
            }],
        })
        slide = prs.slides[0]
        # Recipe creates an autoshape card; the legacy placeholder
        # path for kpi_grid would only place text in the title.
        autoshapes = [
            s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
        ]
        assert autoshapes, "expected at least one card autoshape"

    def it_routes_chart_layout(self):
        prs = from_spec({
            "slides": [{
                "layout": "chart",
                "title": "Rev",
                "chart_type": "line",
                "categories": ["Q1", "Q2"],
                "series": [{"name": "ARR", "values": [10, 20]}],
            }],
        })
        slide = prs.slides[0]
        assert any(s.shape_type == MSO_SHAPE_TYPE.CHART for s in slide.shapes)

    def it_validates_required_keys_for_a_recipe(self):
        with pytest.raises(ValueError, match="missing"):
            from_spec({
                "slides": [{"layout": "kpi", "title": "x"}],  # no `kpis`
            })

    def it_threads_spec_level_tokens_to_each_recipe(self):
        prs = from_spec({
            "tokens": {"preset": "modern_light"},
            "slides": [{
                "layout": "kpi",
                "title": "Run-rate",
                "kpis": [{"label": "ARR", "value": "$182M"}],
            }],
        })
        # Token presence is observable via the title color reflecting
        # the preset's primary palette slot.
        slide = prs.slides[0]
        runs = []
        for sh in slide.shapes:
            if not sh.has_text_frame:
                continue
            for p in sh.text_frame.paragraphs:
                runs.extend(p.runs)
        # First non-empty run is the title.
        title_rgb = next(r.font.color.rgb for r in runs if r.text)
        assert title_rgb is not None


class DescribeInterpolation:
    """`{{name}}` substitutes from `vars`."""

    def it_substitutes_a_simple_variable(self):
        prs = from_spec(
            {
                "vars": {"q": "Q4"},
                "slides": [{"layout": "title", "title": "{{q}} Review"}],
            }
        )
        # Title placeholder has the substituted text.
        assert any(
            "Q4 Review" in p.text
            for sh in prs.slides[0].shapes
            if sh.has_text_frame
            for p in sh.text_frame.paragraphs
        )

    def it_kwarg_vars_override_spec_vars(self):
        prs = from_spec(
            {
                "vars": {"q": "Q3"},
                "slides": [{"layout": "title", "title": "{{q}}"}],
            },
            vars={"q": "Q4"},
        )
        assert any(
            "Q4" in p.text
            for sh in prs.slides[0].shapes
            if sh.has_text_frame
            for p in sh.text_frame.paragraphs
        )

    def it_supports_dotted_paths(self):
        prs = from_spec({
            "vars": {"company": {"name": "ACME"}},
            "slides": [{"layout": "title", "title": "{{company.name}}"}],
        })
        assert any(
            "ACME" in p.text
            for sh in prs.slides[0].shapes
            if sh.has_text_frame
            for p in sh.text_frame.paragraphs
        )

    def it_raises_on_unknown_variable(self):
        with pytest.raises(KeyError, match="not found"):
            from_spec({
                "vars": {},
                "slides": [{"layout": "title", "title": "{{missing}}"}],
            })


class DescribeFromYaml:
    """Loading a deck spec from a YAML file."""

    def it_loads_a_yaml_deck(self, tmp_path):
        yaml_path = tmp_path / "deck.yml"
        yaml_path.write_text(textwrap.dedent("""\
            tokens:
              preset: modern_light
            slides:
              - layout: title
                title: Hello
                subtitle: World
              - layout: kpi
                title: Metrics
                kpis:
                  - label: ARR
                    value: $182M
                    delta: 0.27
        """))
        prs = from_yaml(str(yaml_path))
        assert len(prs.slides) == 2

    def it_threads_vars_into_yaml(self, tmp_path):
        yaml_path = tmp_path / "deck.yml"
        yaml_path.write_text(textwrap.dedent("""\
            slides:
              - layout: title
                title: "{{company}} {{quarter}}"
        """))
        prs = from_yaml(str(yaml_path), vars={"company": "ACME", "quarter": "Q4"})
        assert any(
            "ACME Q4" in p.text
            for sh in prs.slides[0].shapes
            if sh.has_text_frame
            for p in sh.text_frame.paragraphs
        )


class DescribeFigureLayoutDispatch:
    """`{"layout": "figure", "figure": <path>}` routes to figure_slide."""

    def it_routes_a_raster_image_path(self, tmp_path):
        # 1×1 PNG so add_picture's image-format detection succeeds.
        png_path = tmp_path / "thumb.png"
        png_path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08"
            b"\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9c"
            b"c\xfc\xff\xff?\x03\x00\x07\x06\x02\xff\xa3\x9d\x9a\xed"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        prs = from_spec({
            "slides": [{
                "layout": "figure",
                "title": "From file",
                "figure": str(png_path),
            }],
        })
        assert len(prs.slides) == 1


class DescribeTokenSpecResolution:
    def it_loads_a_preset_via_tokens_dict(self):
        prs = from_spec({
            "tokens": {"preset": "modern_dark"},
            "slides": [{"layout": "title", "title": "x"}],
        })
        assert len(prs.slides) == 1

    def it_layers_overrides_on_a_preset(self):
        prs = from_spec({
            "tokens": {
                "preset": "modern_light",
                "overrides": {"palette.primary": "#FF6600"},
            },
            "slides": [{"layout": "title_recipe", "title": "x"}],
        })
        assert len(prs.slides) == 1


class DescribeRecipeKwargValidation:
    """Recipe layouts in `from_spec` reject unknown kwargs (fail-closed)."""

    def it_rejects_a_typo_in_a_recipe_kwarg(self):
        from power_pptx.compose.from_spec import from_spec

        spec = {
            "slides": [
                {
                    "layout": "kpi",
                    "title": "Q4",
                    "kpis": [{"value": "1", "label": "x"}],
                    # Typo: should have been "subtitle"
                    "subtitlz": "Q4 results",
                }
            ]
        }
        with pytest.raises(ValueError, match="unknown spec keys"):
            from_spec(spec)

    def it_accepts_known_recipe_kwargs(self):
        from power_pptx.compose.from_spec import from_spec

        spec = {
            "slides": [
                {
                    "layout": "kpi",
                    "title": "Q4",
                    "kpis": [{"value": "1", "label": "x"}],
                    # transition is a recipe-accepted kwarg
                    "transition": "fade",
                }
            ]
        }
        prs = from_spec(spec)
        assert len(prs.slides) == 1


class DescribeComparisonLayoutAlias:
    """`comparison` routes to the recipe; `comparison_layout` to placeholder."""

    def it_routes_comparison_to_the_recipe(self):
        from power_pptx.compose.from_spec import from_spec

        spec = {
            "slides": [
                {
                    "layout": "comparison",
                    "title": "Side by side",
                    "left_heading": "Before",
                    "right_heading": "After",
                    "rows": [{"left": "5s", "right": "1s"}],
                }
            ]
        }
        prs = from_spec(spec)
        assert len(prs.slides) == 1


class DescribeComparisonLayoutPlaceholders:
    """`comparison_layout` (the placeholder-based opt-in) populates left/right."""

    def it_populates_left_and_right_placeholders(self):
        from power_pptx.compose.from_spec import from_spec

        spec = {
            "slides": [
                {
                    "layout": "comparison_layout",
                    "title": "A vs B",
                    "left": "Faster",
                    "right": "Cheaper",
                }
            ]
        }
        prs = from_spec(spec)
        slide = prs.slides[0]
        # Find any placeholder containing the strings — the exact placeholder
        # idx layout is template-dependent, but the values must land somewhere.
        texts = [ph.text for ph in slide.placeholders]
        assert any("Faster" in t for t in texts)
        assert any("Cheaper" in t for t in texts)


class DescribeThemeAlias:
    """``theme`` is a friendly alias for ``tokens`` when the latter is absent."""

    def it_treats_theme_as_tokens_when_tokens_is_absent(self):
        # See IMPROVEMENTS item 8 — the ``theme`` key used to validate but
        # was silently ignored by ``_resolve_tokens``.
        prs = from_spec({
            "theme": {"preset": "modern_dark"},
            "slides": [{
                "layout": "kpi",
                "title": "Run-rate",
                "kpis": [{"label": "ARR", "value": "$182M"}],
            }],
        })
        slide = prs.slides[0]
        # ``modern_dark`` preset's primary is ``#7C5CFF``; the recipe pins
        # the title colour to that, so the title run reflects the preset.
        from power_pptx.dml.color import RGBColor

        title_rgb = None
        for sh in slide.shapes:
            if not sh.has_text_frame:
                continue
            for p in sh.text_frame.paragraphs:
                for r in p.runs:
                    if r.text:
                        title_rgb = r.font.color.rgb
                        break
                if title_rgb:
                    break
            if title_rgb:
                break
        assert title_rgb == RGBColor(0x7C, 0x5C, 0xFF)

    def it_prefers_tokens_over_theme_when_both_are_set(self):
        # ``tokens`` wins so both spec dialects can coexist in mixed files
        # without surprising the caller.
        prs = from_spec({
            "tokens": {"preset": "modern_light"},
            "theme":  {"preset": "modern_dark"},
            "slides": [{
                "layout": "title_recipe",
                "title": "Hello",
            }],
        })
        assert len(prs.slides) == 1


class DescribeTokensAcceptsDesignTokens:
    """``tokens`` may be a pre-built ``DesignTokens`` instance."""

    def it_accepts_a_DesignTokens_instance_directly(self):
        # See IMPROVEMENTS item 8 — previously rejected with
        # "'tokens' must be a mapping".
        from power_pptx.design.tokens import DesignTokens

        tokens = DesignTokens.from_preset("modern_light")
        prs = from_spec({
            "tokens": tokens,
            "slides": [{
                "layout": "title_recipe",
                "title": "Hello",
            }],
        })
        assert len(prs.slides) == 1


class DescribeSlideSize:
    """``slide_size`` resizes the deck to the named shorthand or explicit pair."""

    def it_resizes_to_16_9_widescreen(self):
        from power_pptx.util import Inches

        prs = from_spec({
            "slide_size": "16:9",
            "slides": [{"layout": "blank"}],
        })
        assert prs.slide_width == Inches(13.333)
        assert prs.slide_height == Inches(7.5)

    def it_resizes_from_an_inches_pair(self):
        from power_pptx.util import Inches

        prs = from_spec({
            "slide_size": (12, 9),
            "slides": [{"layout": "blank"}],
        })
        assert prs.slide_width == Inches(12)
        assert prs.slide_height == Inches(9)

    def it_resizes_from_a_width_height_mapping(self):
        from power_pptx.util import Inches

        prs = from_spec({
            "slide_size": {"width": 13.333, "height": 7.5},
            "slides": [{"layout": "blank"}],
        })
        assert prs.slide_width == Inches(13.333)
        assert prs.slide_height == Inches(7.5)

    def it_rejects_unknown_named_sizes(self):
        with pytest.raises(ValueError, match="Unknown slide_size"):
            from_spec({
                "slide_size": "ultra-wide",
                "slides": [{"layout": "blank"}],
            })


class DescribeLegacyLayoutTokenUpgrade:
    """When tokens are present, the legacy ``title`` / ``bullets`` aliases
    are silently upgraded to their recipe counterparts so the user's
    palette / typography is actually applied (IMPROVEMENTS item 9)."""

    def it_upgrades_title_to_title_recipe_when_tokens_are_present(self):
        prs = from_spec({
            "tokens": {"preset": "modern_dark"},
            "slides": [{"layout": "title", "title": "Hello"}],
        })
        slide = prs.slides[0]
        # The recipe path uses ``add_textbox`` (no placeholders), the
        # legacy path uses the host template's Title-Slide layout (which
        # always has at least one placeholder).
        assert len(slide.placeholders) == 0

    def it_does_not_upgrade_when_no_tokens_are_supplied(self):
        prs = from_spec({
            "slides": [{"layout": "title", "title": "Hello"}],
        })
        slide = prs.slides[0]
        # Legacy path keeps the placeholder layout.
        assert len(slide.placeholders) > 0


class DescribeDidYouMeanHints:
    """Typo'd spec keys / values get a closest-match suggestion."""

    def it_suggests_the_closest_top_level_key(self):
        with pytest.raises(ValueError, match=r"did you mean 'slides'\?"):
            from_spec({"slidez": []})

    def it_suggests_the_closest_recipe_kwarg(self):
        spec = {
            "slides": [
                {
                    "layout": "kpi",
                    "title": "Q4",
                    "kpis": [{"value": "1", "label": "x"}],
                    "titel": "typo",
                }
            ]
        }
        with pytest.raises(ValueError, match=r"did you mean 'title'\?"):
            from_spec(spec)

    def it_suggests_the_closest_transition(self):
        with pytest.raises(ValueError, match=r"did you mean 'fade'\?"):
            from_spec({"slides": [{"layout": "blank", "transition": "fadee"}]})

    def it_suggests_the_closest_slide_size(self):
        with pytest.raises(ValueError, match=r"did you mean 'widescreen'\?"):
            from_spec({"slide_size": "widescreeen", "slides": []})

    def it_omits_the_hint_when_nothing_is_close(self):
        # A wildly different key has no close match: no "did you mean" suffix.
        with pytest.raises(ValueError, match="Unknown spec keys") as exc:
            from_spec({"zzzzzzzz": 1})
        assert "did you mean" not in str(exc.value)
