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

    def it_fails_closed_on_an_unknown_layout_name(self):
        # An unrecognized layout used to silently produce a Blank slide; it
        # now raises with the closest valid layout suggested.
        with pytest.raises(ValueError, match=r"Unknown layout 'titel'.*did you mean 'title'"):
            from_spec({"slides": [{"layout": "titel", "title": "X"}]})

    def it_still_honors_an_explicit_blank_layout(self):
        # The deliberately-blank path keeps working — it is the escape hatch
        # now that unknown names raise.
        prs = from_spec({"slides": [{"layout": "blank"}]})
        assert len(prs.slides) == 1


class DescribeShapeEntries:
    """A slide's ``shapes`` list adds shapes on top of the layout."""

    def it_adds_a_named_textbox_from_a_shape_entry(self):
        from power_pptx.util import Inches

        prs = from_spec({
            "slides": [{
                "layout": "blank",
                "shapes": [{
                    "name": "note",
                    "left": 1,
                    "top": 2,
                    "width": 3,
                    "height": 0.5,
                    "text": "Hello",
                }],
            }],
        })
        shape = prs.slides[0].shapes[0]
        assert shape.name == "note"
        assert shape.left == Inches(1)
        assert shape.top == Inches(2)
        assert shape.width == Inches(3)
        assert shape.height == Inches(0.5)
        assert shape.text_frame.text == "Hello"

    def it_adds_an_autoshape_by_mso_shape_name(self):
        prs = from_spec({
            "slides": [{
                "layout": "blank",
                "shapes": [{
                    "shape": "rounded_rectangle",
                    "left": 1, "top": 1, "width": 2, "height": 1,
                }],
            }],
        })
        shape = prs.slides[0].shapes[0]
        assert shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE

    def it_adds_shapes_on_top_of_a_recipe_slide(self):
        # ``shapes`` is handled by the dispatcher, so it must not reach
        # the recipe as an unknown kwarg.
        prs = from_spec({
            "slides": [{
                "layout": "kpi",
                "title": "Run-rate",
                "kpis": [{"label": "ARR", "value": "$182M"}],
                "shapes": [{
                    "name": "stamp",
                    "left": 0.2, "top": 0.2, "width": 1, "height": 0.4,
                    "text": "DRAFT",
                }],
            }],
        })
        assert any(s.name == "stamp" for s in prs.slides[0].shapes)

    def it_interpolates_vars_inside_a_shape_entry(self):
        prs = from_spec({
            "vars": {"label": "DRAFT"},
            "slides": [{
                "layout": "blank",
                "shapes": [{
                    "left": 1, "top": 1, "width": 2, "height": 1,
                    "text": "{{label}}",
                }],
            }],
        })
        assert prs.slides[0].shapes[0].text_frame.text == "DRAFT"

    def it_rejects_an_unknown_shape_entry_key(self):
        with pytest.raises(ValueError, match=r"did you mean 'lint_group'\?"):
            from_spec({
                "slides": [{
                    "layout": "blank",
                    "shapes": [{
                        "left": 1, "top": 1, "width": 2, "height": 1,
                        "lint_groupp": "card",
                    }],
                }],
            })

    def it_rejects_a_shape_entry_missing_geometry(self):
        with pytest.raises(ValueError, match=r"missing \['height'\]"):
            from_spec({
                "slides": [{
                    "layout": "blank",
                    "shapes": [{"left": 1, "top": 1, "width": 2}],
                }],
            })

    def it_rejects_an_unknown_shape_type(self):
        with pytest.raises(ValueError, match=r"unknown shape type 'rectangel'"):
            from_spec({
                "slides": [{
                    "layout": "blank",
                    "shapes": [{
                        "shape": "rectangel",
                        "left": 1, "top": 1, "width": 2, "height": 1,
                    }],
                }],
            })

    def it_rejects_a_non_list_shapes_value(self):
        with pytest.raises(ValueError, match="'shapes' must be a list"):
            from_spec({
                "slides": [{"layout": "blank", "shapes": {"left": 1}}],
            })


class DescribeShapeLintIntentFields:
    """``lint_group`` / ``layer`` / ``layer_above`` / ``allow_overlap_with``
    declare an intentional overlap at spec-authoring time (ROADMAP Phase 2,
    "Relationship model")."""

    def it_round_trips_lint_group(self):
        prs = from_spec({
            "slides": [{
                "layout": "blank",
                "shapes": [{
                    "name": "card",
                    "left": 1, "top": 1, "width": 2, "height": 1,
                    "lint_group": "kpi-card-1",
                }],
            }],
        })
        assert prs.slides[0].shapes[0].lint_group == "kpi-card-1"

    def it_round_trips_layer_and_layer_above(self):
        prs = from_spec({
            "slides": [{
                "layout": "blank",
                "shapes": [
                    {"name": "card", "left": 1, "top": 1, "width": 3,
                     "height": 2, "layer": "card"},
                    {"name": "badge", "left": 3, "top": 1, "width": 1,
                     "height": 1, "layer_above": "card"},
                ],
            }],
        })
        card, badge = prs.slides[0].shapes
        assert card.layer == "card"
        assert card.layer_above is None
        assert badge.layer is None
        assert badge.layer_above == "card"

    def it_resolves_allow_overlap_with_by_spec_name(self):
        prs = from_spec({
            "slides": [{
                "layout": "blank",
                "shapes": [
                    {"name": "card", "left": 1, "top": 1, "width": 3,
                     "height": 2},
                    {"name": "badge", "left": 2.5, "top": 1, "width": 3,
                     "height": 2, "allow_overlap_with": "card"},
                ],
            }],
        })
        card, badge = prs.slides[0].shapes
        assert badge.overlap_allowances == frozenset({card.shape_id})

    def it_resolves_a_forward_reference(self):
        # ``card`` is declared *after* the shape that names it — ids only
        # exist once every shape on the slide has been created, so
        # resolution runs as a second pass.
        prs = from_spec({
            "slides": [{
                "layout": "blank",
                "shapes": [
                    {"name": "badge", "left": 2.5, "top": 1, "width": 3,
                     "height": 2, "allow_overlap_with": "card"},
                    {"name": "card", "left": 1, "top": 1, "width": 3,
                     "height": 2},
                ],
            }],
        })
        badge, card = prs.slides[0].shapes
        assert badge.overlap_allowances == frozenset({card.shape_id})

    def it_accepts_a_list_of_allow_overlap_with_names(self):
        prs = from_spec({
            "slides": [{
                "layout": "blank",
                "shapes": [
                    {"name": "a", "left": 1, "top": 1, "width": 2, "height": 1},
                    {"name": "b", "left": 2, "top": 1, "width": 2, "height": 1},
                    {"name": "c", "left": 1.5, "top": 1, "width": 2,
                     "height": 1, "allow_overlap_with": ["a", "b"]},
                ],
            }],
        })
        a, b, c = prs.slides[0].shapes
        assert c.overlap_allowances == frozenset({a.shape_id, b.shape_id})

    def it_rejects_an_unknown_allow_overlap_with_name(self):
        with pytest.raises(
            ValueError,
            match=r"names unknown shape 'carrd' \(did you mean 'card'\?\)",
        ):
            from_spec({
                "slides": [{
                    "layout": "blank",
                    "shapes": [
                        {"name": "card", "left": 1, "top": 1, "width": 2,
                         "height": 1},
                        {"name": "badge", "left": 2, "top": 1, "width": 2,
                         "height": 1, "allow_overlap_with": "carrd"},
                    ],
                }],
            })

    def it_names_the_slide_in_an_unresolved_reference_error(self):
        with pytest.raises(ValueError, match=r"slides\[1\]\.shapes\[0\]"):
            from_spec({
                "slides": [
                    {"layout": "blank"},
                    {
                        "layout": "blank",
                        "shapes": [{
                            "name": "badge", "left": 1, "top": 1,
                            "width": 2, "height": 1,
                            "allow_overlap_with": "nowhere",
                        }],
                    },
                ],
            })

    def it_rejects_a_cross_slide_allow_overlap_with_reference(self):
        # Shape ids are only unique within a slide, so an allowance can
        # never span slides.
        with pytest.raises(ValueError, match=r"is defined on slides \[0\]"):
            from_spec({
                "slides": [
                    {
                        "layout": "blank",
                        "shapes": [{"name": "card", "left": 1, "top": 1,
                                    "width": 2, "height": 1}],
                    },
                    {
                        "layout": "blank",
                        "shapes": [{
                            "name": "badge", "left": 1, "top": 1,
                            "width": 2, "height": 1,
                            "allow_overlap_with": "card",
                        }],
                    },
                ],
            })

    def it_rejects_a_forward_cross_slide_reference_too(self):
        with pytest.raises(ValueError, match=r"is defined on slides \[1\]"):
            from_spec({
                "slides": [
                    {
                        "layout": "blank",
                        "shapes": [{
                            "name": "badge", "left": 1, "top": 1,
                            "width": 2, "height": 1,
                            "allow_overlap_with": "card",
                        }],
                    },
                    {
                        "layout": "blank",
                        "shapes": [{"name": "card", "left": 1, "top": 1,
                                    "width": 2, "height": 1}],
                    },
                ],
            })

    def it_rejects_a_self_reference(self):
        with pytest.raises(ValueError, match="names this shape itself"):
            from_spec({
                "slides": [{
                    "layout": "blank",
                    "shapes": [{
                        "name": "card", "left": 1, "top": 1, "width": 2,
                        "height": 1, "allow_overlap_with": "card",
                    }],
                }],
            })

    def it_rejects_duplicate_shape_names_on_one_slide(self):
        with pytest.raises(ValueError, match="duplicate shape name 'card'"):
            from_spec({
                "slides": [{
                    "layout": "blank",
                    "shapes": [
                        {"name": "card", "left": 1, "top": 1, "width": 2,
                         "height": 1},
                        {"name": "card", "left": 3, "top": 1, "width": 2,
                         "height": 1},
                    ],
                }],
            })

    def it_reports_where_a_lint_intent_value_was_rejected(self):
        # Validation stays the shape property's job; the spec layer only
        # adds the location so a bad value is findable in a long spec.
        with pytest.raises(
            ValueError, match=r"slides\[0\]\.shapes\[0\]: 'lint_group'"
        ):
            from_spec({
                "slides": [{
                    "layout": "blank",
                    "shapes": [{
                        "left": 1, "top": 1, "width": 2, "height": 1,
                        "lint_group": 5,
                    }],
                }],
            })

    def it_rejects_a_non_string_allow_overlap_with_value(self):
        with pytest.raises(ValueError, match="must be a shape name or a list"):
            from_spec({
                "slides": [{
                    "layout": "blank",
                    "shapes": [{
                        "name": "card", "left": 1, "top": 1, "width": 2,
                        "height": 1, "allow_overlap_with": 7,
                    }],
                }],
            })


class DescribeSpecDeclaredOverlapSuppression:
    """End-to-end: a spec-declared overlap silences the ShapeCollision the
    same spec produces without the declaration."""

    @staticmethod
    def _overlapping_spec(**declarations):
        """Two equally-sized rectangles overlapping by half their area."""
        first = {"name": "left_card", "shape": "rectangle",
                 "left": 1, "top": 1, "width": 3, "height": 2}
        second = {"name": "right_card", "shape": "rectangle",
                  "left": 2.5, "top": 1, "width": 3, "height": 2}
        first.update(declarations.get("first", {}))
        second.update(declarations.get("second", {}))
        return {"slides": [{"layout": "blank", "shapes": [first, second]}]}

    @staticmethod
    def _collisions(prs):
        from power_pptx.lint import ShapeCollision

        return [
            i for i in prs.slides[0].lint().issues
            if isinstance(i, ShapeCollision)
        ]

    def it_reports_the_collision_without_a_declaration(self):
        prs = from_spec(self._overlapping_spec())
        assert self._collisions(prs), "expected an undeclared overlap to collide"

    def it_suppresses_the_collision_via_allow_overlap_with(self):
        prs = from_spec(
            self._overlapping_spec(second={"allow_overlap_with": "left_card"})
        )
        assert self._collisions(prs) == []

    def it_suppresses_the_collision_via_a_shared_lint_group(self):
        prs = from_spec(self._overlapping_spec(
            first={"lint_group": "hero"},
            second={"lint_group": "hero"},
        ))
        assert self._collisions(prs) == []

    def it_suppresses_the_collision_via_layer_hints(self):
        prs = from_spec(self._overlapping_spec(
            first={"layer": "card"},
            second={"layer_above": "card"},
        ))
        assert self._collisions(prs) == []

    def it_reports_a_layer_order_violation_for_the_reversed_z_order(self):
        # The shape drawn *first* (underneath) claims to sit on top.
        from power_pptx.lint import LayerOrderViolation

        prs = from_spec(self._overlapping_spec(
            first={"layer_above": "card"},
            second={"layer": "card"},
        ))
        issues = prs.slides[0].lint().issues
        assert any(isinstance(i, LayerOrderViolation) for i in issues)
