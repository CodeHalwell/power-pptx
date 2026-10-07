"""Tests for the recipe-dispatch / interpolation / YAML path of from_spec."""

from __future__ import annotations

import textwrap

import pytest

from power_pptx.compose import from_spec, from_yaml
from power_pptx.dml.color import RGBColor
from power_pptx.enum.shapes import MSO_SHAPE_TYPE


class DescribeRecipeDispatch:
    """Recipe-named layouts route to the styled recipes module."""

    def it_routes_kpi_layout_to_kpi_slide_recipe(self):
        prs = from_spec(
            {
                "slides": [
                    {
                        "layout": "kpi",
                        "title": "Run-rate",
                        "kpis": [
                            {"label": "ARR", "value": "$182M", "delta": 0.27},
                        ],
                    }
                ],
            }
        )
        slide = prs.slides[0]
        # Recipe creates an autoshape card; the legacy placeholder
        # path for kpi_grid would only place text in the title.
        autoshapes = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE]
        assert autoshapes, "expected at least one card autoshape"

    def it_routes_chart_layout(self):
        prs = from_spec(
            {
                "slides": [
                    {
                        "layout": "chart",
                        "title": "Rev",
                        "chart_type": "line",
                        "categories": ["Q1", "Q2"],
                        "series": [{"name": "ARR", "values": [10, 20]}],
                    }
                ],
            }
        )
        slide = prs.slides[0]
        assert any(s.shape_type == MSO_SHAPE_TYPE.CHART for s in slide.shapes)

    def it_validates_required_keys_for_a_recipe(self):
        with pytest.raises(ValueError, match="missing"):
            from_spec(
                {
                    "slides": [{"layout": "kpi", "title": "x"}],  # no `kpis`
                }
            )

    def it_threads_spec_level_tokens_to_each_recipe(self):
        prs = from_spec(
            {
                "tokens": {"preset": "modern_light"},
                "slides": [
                    {
                        "layout": "kpi",
                        "title": "Run-rate",
                        "kpis": [{"label": "ARR", "value": "$182M"}],
                    }
                ],
            }
        )
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
        prs = from_spec(
            {
                "vars": {"company": {"name": "ACME"}},
                "slides": [{"layout": "title", "title": "{{company.name}}"}],
            }
        )
        assert any(
            "ACME" in p.text
            for sh in prs.slides[0].shapes
            if sh.has_text_frame
            for p in sh.text_frame.paragraphs
        )

    def it_raises_on_unknown_variable(self):
        with pytest.raises(KeyError, match="not found"):
            from_spec(
                {
                    "vars": {},
                    "slides": [{"layout": "title", "title": "{{missing}}"}],
                }
            )


class DescribeFromYaml:
    """Loading a deck spec from a YAML file."""

    def it_loads_a_yaml_deck(self, tmp_path):
        yaml_path = tmp_path / "deck.yml"
        yaml_path.write_text(
            textwrap.dedent("""\
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
        """)
        )
        prs = from_yaml(str(yaml_path))
        assert len(prs.slides) == 2

    def it_threads_vars_into_yaml(self, tmp_path):
        yaml_path = tmp_path / "deck.yml"
        yaml_path.write_text(
            textwrap.dedent("""\
            slides:
              - layout: title
                title: "{{company}} {{quarter}}"
        """)
        )
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
        prs = from_spec(
            {
                "slides": [
                    {
                        "layout": "figure",
                        "title": "From file",
                        "figure": str(png_path),
                    }
                ],
            }
        )
        assert len(prs.slides) == 1


class DescribeTokenSpecResolution:
    def it_loads_a_preset_via_tokens_dict(self):
        prs = from_spec(
            {
                "tokens": {"preset": "modern_dark"},
                "slides": [{"layout": "title", "title": "x"}],
            }
        )
        assert len(prs.slides) == 1

    def it_layers_overrides_on_a_preset(self):
        prs = from_spec(
            {
                "tokens": {
                    "preset": "modern_light",
                    "overrides": {"palette.primary": "#FF6600"},
                },
                "slides": [{"layout": "title_recipe", "title": "x"}],
            }
        )
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
        prs = from_spec(
            {
                "theme": {"preset": "modern_dark"},
                "slides": [
                    {
                        "layout": "kpi",
                        "title": "Run-rate",
                        "kpis": [{"label": "ARR", "value": "$182M"}],
                    }
                ],
            }
        )
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
        prs = from_spec(
            {
                "tokens": {"preset": "modern_light"},
                "theme": {"preset": "modern_dark"},
                "slides": [
                    {
                        "layout": "title_recipe",
                        "title": "Hello",
                    }
                ],
            }
        )
        assert len(prs.slides) == 1


class DescribeTokensAcceptsDesignTokens:
    """``tokens`` may be a pre-built ``DesignTokens`` instance."""

    def it_accepts_a_DesignTokens_instance_directly(self):
        # See IMPROVEMENTS item 8 — previously rejected with
        # "'tokens' must be a mapping".
        from power_pptx.design.tokens import DesignTokens

        tokens = DesignTokens.from_preset("modern_light")
        prs = from_spec(
            {
                "tokens": tokens,
                "slides": [
                    {
                        "layout": "title_recipe",
                        "title": "Hello",
                    }
                ],
            }
        )
        assert len(prs.slides) == 1


class DescribeSlideSize:
    """``slide_size`` resizes the deck to the named shorthand or explicit pair."""

    def it_resizes_to_16_9_widescreen(self):
        from power_pptx.util import Inches

        prs = from_spec(
            {
                "slide_size": "16:9",
                "slides": [{"layout": "blank"}],
            }
        )
        assert prs.slide_width == Inches(13.333)
        assert prs.slide_height == Inches(7.5)

    def it_resizes_from_an_inches_pair(self):
        from power_pptx.util import Inches

        prs = from_spec(
            {
                "slide_size": (12, 9),
                "slides": [{"layout": "blank"}],
            }
        )
        assert prs.slide_width == Inches(12)
        assert prs.slide_height == Inches(9)

    def it_resizes_from_a_width_height_mapping(self):
        from power_pptx.util import Inches

        prs = from_spec(
            {
                "slide_size": {"width": 13.333, "height": 7.5},
                "slides": [{"layout": "blank"}],
            }
        )
        assert prs.slide_width == Inches(13.333)
        assert prs.slide_height == Inches(7.5)

    def it_rejects_unknown_named_sizes(self):
        with pytest.raises(ValueError, match="Unknown slide_size"):
            from_spec(
                {
                    "slide_size": "ultra-wide",
                    "slides": [{"layout": "blank"}],
                }
            )


class DescribeLegacyLayoutTokenUpgrade:
    """When tokens are present, the legacy ``title`` / ``bullets`` aliases
    are silently upgraded to their recipe counterparts so the user's
    palette / typography is actually applied (IMPROVEMENTS item 9)."""

    def it_upgrades_title_to_title_recipe_when_tokens_are_present(self):
        prs = from_spec(
            {
                "tokens": {"preset": "modern_dark"},
                "slides": [{"layout": "title", "title": "Hello"}],
            }
        )
        slide = prs.slides[0]
        # The recipe path uses ``add_textbox`` (no placeholders), the
        # legacy path uses the host template's Title-Slide layout (which
        # always has at least one placeholder).
        assert len(slide.placeholders) == 0

    def it_does_not_upgrade_when_no_tokens_are_supplied(self):
        prs = from_spec(
            {
                "slides": [{"layout": "title", "title": "Hello"}],
            }
        )
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

        prs = from_spec(
            {
                "slides": [
                    {
                        "layout": "blank",
                        "shapes": [
                            {
                                "name": "note",
                                "left": 1,
                                "top": 2,
                                "width": 3,
                                "height": 0.5,
                                "text": "Hello",
                            }
                        ],
                    }
                ],
            }
        )
        shape = prs.slides[0].shapes[0]
        assert shape.name == "note"
        assert shape.left == Inches(1)
        assert shape.top == Inches(2)
        assert shape.width == Inches(3)
        assert shape.height == Inches(0.5)
        assert shape.text_frame.text == "Hello"

    def it_adds_an_autoshape_by_mso_shape_name(self):
        prs = from_spec(
            {
                "slides": [
                    {
                        "layout": "blank",
                        "shapes": [
                            {
                                "shape": "rounded_rectangle",
                                "left": 1,
                                "top": 1,
                                "width": 2,
                                "height": 1,
                            }
                        ],
                    }
                ],
            }
        )
        shape = prs.slides[0].shapes[0]
        assert shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE

    def it_adds_shapes_on_top_of_a_recipe_slide(self):
        # ``shapes`` is handled by the dispatcher, so it must not reach
        # the recipe as an unknown kwarg.
        prs = from_spec(
            {
                "slides": [
                    {
                        "layout": "kpi",
                        "title": "Run-rate",
                        "kpis": [{"label": "ARR", "value": "$182M"}],
                        "shapes": [
                            {
                                "name": "stamp",
                                "left": 0.2,
                                "top": 0.2,
                                "width": 1,
                                "height": 0.4,
                                "text": "DRAFT",
                            }
                        ],
                    }
                ],
            }
        )
        assert any(s.name == "stamp" for s in prs.slides[0].shapes)

    def it_interpolates_vars_inside_a_shape_entry(self):
        prs = from_spec(
            {
                "vars": {"label": "DRAFT"},
                "slides": [
                    {
                        "layout": "blank",
                        "shapes": [
                            {
                                "left": 1,
                                "top": 1,
                                "width": 2,
                                "height": 1,
                                "text": "{{label}}",
                            }
                        ],
                    }
                ],
            }
        )
        assert prs.slides[0].shapes[0].text_frame.text == "DRAFT"

    def it_rejects_an_unknown_shape_entry_key(self):
        with pytest.raises(ValueError, match=r"did you mean 'lint_group'\?"):
            from_spec(
                {
                    "slides": [
                        {
                            "layout": "blank",
                            "shapes": [
                                {
                                    "left": 1,
                                    "top": 1,
                                    "width": 2,
                                    "height": 1,
                                    "lint_groupp": "card",
                                }
                            ],
                        }
                    ],
                }
            )

    def it_rejects_a_shape_entry_missing_geometry(self):
        with pytest.raises(ValueError, match=r"missing \['height'\]"):
            from_spec(
                {
                    "slides": [
                        {
                            "layout": "blank",
                            "shapes": [{"left": 1, "top": 1, "width": 2}],
                        }
                    ],
                }
            )

    def it_rejects_an_unknown_shape_type(self):
        with pytest.raises(ValueError, match=r"unknown shape type 'rectangel'"):
            from_spec(
                {
                    "slides": [
                        {
                            "layout": "blank",
                            "shapes": [
                                {
                                    "shape": "rectangel",
                                    "left": 1,
                                    "top": 1,
                                    "width": 2,
                                    "height": 1,
                                }
                            ],
                        }
                    ],
                }
            )

    def it_rejects_a_non_list_shapes_value(self):
        with pytest.raises(ValueError, match="'shapes' must be a list"):
            from_spec(
                {
                    "slides": [{"layout": "blank", "shapes": {"left": 1}}],
                }
            )


class DescribeShapeLintIntentFields:
    """``lint_group`` / ``layer`` / ``layer_above`` / ``allow_overlap_with``
    declare an intentional overlap at spec-authoring time (ROADMAP Phase 2,
    "Relationship model")."""

    def it_round_trips_lint_group(self):
        prs = from_spec(
            {
                "slides": [
                    {
                        "layout": "blank",
                        "shapes": [
                            {
                                "name": "card",
                                "left": 1,
                                "top": 1,
                                "width": 2,
                                "height": 1,
                                "lint_group": "kpi-card-1",
                            }
                        ],
                    }
                ],
            }
        )
        assert prs.slides[0].shapes[0].lint_group == "kpi-card-1"

    def it_round_trips_layer_and_layer_above(self):
        prs = from_spec(
            {
                "slides": [
                    {
                        "layout": "blank",
                        "shapes": [
                            {
                                "name": "card",
                                "left": 1,
                                "top": 1,
                                "width": 3,
                                "height": 2,
                                "layer": "card",
                            },
                            {
                                "name": "badge",
                                "left": 3,
                                "top": 1,
                                "width": 1,
                                "height": 1,
                                "layer_above": "card",
                            },
                        ],
                    }
                ],
            }
        )
        card, badge = prs.slides[0].shapes
        assert card.layer == "card"
        assert card.layer_above is None
        assert badge.layer is None
        assert badge.layer_above == "card"

    def it_resolves_allow_overlap_with_by_spec_name(self):
        prs = from_spec(
            {
                "slides": [
                    {
                        "layout": "blank",
                        "shapes": [
                            {"name": "card", "left": 1, "top": 1, "width": 3, "height": 2},
                            {
                                "name": "badge",
                                "left": 2.5,
                                "top": 1,
                                "width": 3,
                                "height": 2,
                                "allow_overlap_with": "card",
                            },
                        ],
                    }
                ],
            }
        )
        card, badge = prs.slides[0].shapes
        assert badge.overlap_allowances == frozenset({card.shape_id})

    def it_resolves_a_forward_reference(self):
        # ``card`` is declared *after* the shape that names it — ids only
        # exist once every shape on the slide has been created, so
        # resolution runs as a second pass.
        prs = from_spec(
            {
                "slides": [
                    {
                        "layout": "blank",
                        "shapes": [
                            {
                                "name": "badge",
                                "left": 2.5,
                                "top": 1,
                                "width": 3,
                                "height": 2,
                                "allow_overlap_with": "card",
                            },
                            {"name": "card", "left": 1, "top": 1, "width": 3, "height": 2},
                        ],
                    }
                ],
            }
        )
        badge, card = prs.slides[0].shapes
        assert badge.overlap_allowances == frozenset({card.shape_id})

    def it_accepts_a_list_of_allow_overlap_with_names(self):
        prs = from_spec(
            {
                "slides": [
                    {
                        "layout": "blank",
                        "shapes": [
                            {"name": "a", "left": 1, "top": 1, "width": 2, "height": 1},
                            {"name": "b", "left": 2, "top": 1, "width": 2, "height": 1},
                            {
                                "name": "c",
                                "left": 1.5,
                                "top": 1,
                                "width": 2,
                                "height": 1,
                                "allow_overlap_with": ["a", "b"],
                            },
                        ],
                    }
                ],
            }
        )
        a, b, c = prs.slides[0].shapes
        assert c.overlap_allowances == frozenset({a.shape_id, b.shape_id})

    def it_rejects_an_unknown_allow_overlap_with_name(self):
        with pytest.raises(
            ValueError,
            match=r"names unknown shape 'carrd' \(did you mean 'card'\?\)",
        ):
            from_spec(
                {
                    "slides": [
                        {
                            "layout": "blank",
                            "shapes": [
                                {"name": "card", "left": 1, "top": 1, "width": 2, "height": 1},
                                {
                                    "name": "badge",
                                    "left": 2,
                                    "top": 1,
                                    "width": 2,
                                    "height": 1,
                                    "allow_overlap_with": "carrd",
                                },
                            ],
                        }
                    ],
                }
            )

    def it_names_the_slide_in_an_unresolved_reference_error(self):
        with pytest.raises(ValueError, match=r"slides\[1\]\.shapes\[0\]"):
            from_spec(
                {
                    "slides": [
                        {"layout": "blank"},
                        {
                            "layout": "blank",
                            "shapes": [
                                {
                                    "name": "badge",
                                    "left": 1,
                                    "top": 1,
                                    "width": 2,
                                    "height": 1,
                                    "allow_overlap_with": "nowhere",
                                }
                            ],
                        },
                    ],
                }
            )

    def it_rejects_a_cross_slide_allow_overlap_with_reference(self):
        # Shape ids are only unique within a slide, so an allowance can
        # never span slides.
        with pytest.raises(ValueError, match=r"is defined on slides \[0\]"):
            from_spec(
                {
                    "slides": [
                        {
                            "layout": "blank",
                            "shapes": [
                                {"name": "card", "left": 1, "top": 1, "width": 2, "height": 1}
                            ],
                        },
                        {
                            "layout": "blank",
                            "shapes": [
                                {
                                    "name": "badge",
                                    "left": 1,
                                    "top": 1,
                                    "width": 2,
                                    "height": 1,
                                    "allow_overlap_with": "card",
                                }
                            ],
                        },
                    ],
                }
            )

    def it_rejects_a_forward_cross_slide_reference_too(self):
        with pytest.raises(ValueError, match=r"is defined on slides \[1\]"):
            from_spec(
                {
                    "slides": [
                        {
                            "layout": "blank",
                            "shapes": [
                                {
                                    "name": "badge",
                                    "left": 1,
                                    "top": 1,
                                    "width": 2,
                                    "height": 1,
                                    "allow_overlap_with": "card",
                                }
                            ],
                        },
                        {
                            "layout": "blank",
                            "shapes": [
                                {"name": "card", "left": 1, "top": 1, "width": 2, "height": 1}
                            ],
                        },
                    ],
                }
            )

    def it_rejects_a_self_reference(self):
        with pytest.raises(ValueError, match="names this shape itself"):
            from_spec(
                {
                    "slides": [
                        {
                            "layout": "blank",
                            "shapes": [
                                {
                                    "name": "card",
                                    "left": 1,
                                    "top": 1,
                                    "width": 2,
                                    "height": 1,
                                    "allow_overlap_with": "card",
                                }
                            ],
                        }
                    ],
                }
            )

    def it_rejects_duplicate_shape_names_on_one_slide(self):
        with pytest.raises(ValueError, match="duplicate shape name 'card'"):
            from_spec(
                {
                    "slides": [
                        {
                            "layout": "blank",
                            "shapes": [
                                {"name": "card", "left": 1, "top": 1, "width": 2, "height": 1},
                                {"name": "card", "left": 3, "top": 1, "width": 2, "height": 1},
                            ],
                        }
                    ],
                }
            )

    def it_reports_where_a_lint_intent_value_was_rejected(self):
        # Validation stays the shape property's job; the spec layer only
        # adds the location so a bad value is findable in a long spec.
        with pytest.raises(ValueError, match=r"slides\[0\]\.shapes\[0\]: 'lint_group'"):
            from_spec(
                {
                    "slides": [
                        {
                            "layout": "blank",
                            "shapes": [
                                {
                                    "left": 1,
                                    "top": 1,
                                    "width": 2,
                                    "height": 1,
                                    "lint_group": 5,
                                }
                            ],
                        }
                    ],
                }
            )

    def it_rejects_a_non_string_allow_overlap_with_value(self):
        with pytest.raises(ValueError, match="must be a shape name or a list"):
            from_spec(
                {
                    "slides": [
                        {
                            "layout": "blank",
                            "shapes": [
                                {
                                    "name": "card",
                                    "left": 1,
                                    "top": 1,
                                    "width": 2,
                                    "height": 1,
                                    "allow_overlap_with": 7,
                                }
                            ],
                        }
                    ],
                }
            )


class DescribeSpecDeclaredOverlapSuppression:
    """End-to-end: a spec-declared overlap silences the ShapeCollision the
    same spec produces without the declaration."""

    @staticmethod
    def _overlapping_spec(**declarations):
        """Two equally-sized rectangles overlapping by half their area."""
        first = {
            "name": "left_card",
            "shape": "rectangle",
            "left": 1,
            "top": 1,
            "width": 3,
            "height": 2,
        }
        second = {
            "name": "right_card",
            "shape": "rectangle",
            "left": 2.5,
            "top": 1,
            "width": 3,
            "height": 2,
        }
        first.update(declarations.get("first", {}))
        second.update(declarations.get("second", {}))
        return {"slides": [{"layout": "blank", "shapes": [first, second]}]}

    @staticmethod
    def _collisions(prs):
        from power_pptx.lint import ShapeCollision

        return [i for i in prs.slides[0].lint().issues if isinstance(i, ShapeCollision)]

    def it_reports_the_collision_without_a_declaration(self):
        prs = from_spec(self._overlapping_spec())
        assert self._collisions(prs), "expected an undeclared overlap to collide"

    def it_suppresses_the_collision_via_allow_overlap_with(self):
        prs = from_spec(self._overlapping_spec(second={"allow_overlap_with": "left_card"}))
        assert self._collisions(prs) == []

    def it_suppresses_the_collision_via_a_shared_lint_group(self):
        prs = from_spec(
            self._overlapping_spec(
                first={"lint_group": "hero"},
                second={"lint_group": "hero"},
            )
        )
        assert self._collisions(prs) == []

    def it_suppresses_the_collision_via_layer_hints(self):
        prs = from_spec(
            self._overlapping_spec(
                first={"layer": "card"},
                second={"layer_above": "card"},
            )
        )
        assert self._collisions(prs) == []

    def it_reports_a_layer_order_violation_for_the_reversed_z_order(self):
        # The shape drawn *first* (underneath) claims to sit on top.
        from power_pptx.lint import LayerOrderViolation

        prs = from_spec(
            self._overlapping_spec(
                first={"layer_above": "card"},
                second={"layer": "card"},
            )
        )
        issues = prs.slides[0].lint().issues
        assert any(isinstance(i, LayerOrderViolation) for i in issues)


# ---------------------------------------------------------------------------
# Spec validation: tokens, unknown keys, wrong-shaped content, kpi_grid,
# interpolation.  Helpers first.
# ---------------------------------------------------------------------------

_VIBRANT_PRIMARY = RGBColor(0xFF, 0x33, 0x66)
_MODERN_LIGHT_PRIMARY = RGBColor(0x3B, 0x5B, 0xDB)


def _slide_texts(slide):
    """Text of every text-bearing shape on *slide*, in z-order."""
    return [sh.text_frame.text for sh in slide.shapes if sh.has_text_frame]


def _first_run_rgb(slide):
    """Colour of the first non-empty run on *slide* (the title, for recipes)."""
    for sh in slide.shapes:
        if not sh.has_text_frame:
            continue
        for p in sh.text_frame.paragraphs:
            for r in p.runs:
                if r.text:
                    return r.font.color.rgb
    return None


class DescribeSlideLevelTokens:
    """A slide's own ``tokens`` replace the deck-level set for that slide."""

    _KPI = {"layout": "kpi", "title": "T", "kpis": [{"label": "A", "value": "1"}]}

    def it_resolves_a_slide_level_tokens_mapping(self):
        prs = from_spec(
            {
                "tokens": {"preset": "modern_light"},
                "slides": [{**self._KPI, "tokens": {"preset": "vibrant"}}],
            }
        )
        # ``vibrant``'s primary, not ``modern_light``'s.
        assert _first_run_rgb(prs.slides[0]) == _VIBRANT_PRIMARY

    def it_keeps_the_deck_level_tokens_on_slides_without_their_own(self):
        prs = from_spec(
            {
                "tokens": {"preset": "modern_light"},
                "slides": [{**self._KPI, "tokens": {"preset": "vibrant"}}, dict(self._KPI)],
            }
        )
        assert _first_run_rgb(prs.slides[0]) == _VIBRANT_PRIMARY
        assert _first_run_rgb(prs.slides[1]) == _MODERN_LIGHT_PRIMARY

    def it_applies_slide_level_tokens_when_the_deck_has_none(self):
        prs = from_spec({"slides": [{**self._KPI, "tokens": {"preset": "vibrant"}}]})
        assert _first_run_rgb(prs.slides[0]) == _VIBRANT_PRIMARY

    def it_accepts_a_prebuilt_DesignTokens_instance_on_a_slide(self):
        from power_pptx.design.tokens import DesignTokens

        tokens = DesignTokens.from_preset("vibrant")
        prs = from_spec({"slides": [{**self._KPI, "tokens": tokens}]})
        assert _first_run_rgb(prs.slides[0]) == _VIBRANT_PRIMARY

    def it_lets_a_slide_opt_out_of_the_deck_tokens_with_null(self):
        prs = from_spec(
            {
                "tokens": {"preset": "modern_light"},
                "slides": [{**self._KPI, "tokens": None}],
            }
        )
        assert _first_run_rgb(prs.slides[0]) is None

    def it_upgrades_a_legacy_title_when_only_the_slide_has_tokens(self):
        prs = from_spec(
            {"slides": [{"layout": "title", "title": "Hello", "tokens": {"preset": "vibrant"}}]}
        )
        slide = prs.slides[0]
        # Recipe path (no template placeholders), styled by the slide's tokens.
        assert len(slide.placeholders) == 0
        assert _first_run_rgb(slide) == _VIBRANT_PRIMARY

    def it_locates_a_bad_slide_level_tokens_value(self):
        with pytest.raises(ValueError, match=r"slides\[1\].*Unknown preset 'nope'"):
            from_spec(
                {
                    "slides": [
                        {"layout": "blank"},
                        {**self._KPI, "tokens": {"preset": "nope"}},
                    ]
                }
            )


class DescribeTokenSpecValidation:
    """A tokens spec must say what it means; nothing in it is silently dropped."""

    def it_rejects_extra_keys_beside_a_preset(self):
        spec = {
            "tokens": {"preset": "modern_light", "palette": {"primary": "#FF0000"}},
            "slides": [],
        }
        with pytest.raises(
            ValueError, match=r"unexpected keys 'palette' beside 'preset'.*overrides"
        ):
            from_spec(spec)

    def it_rejects_extra_keys_beside_a_yaml_path(self, tmp_path):
        brand = tmp_path / "brand.yml"
        brand.write_text("palette:\n  primary: '#112233'\n")
        spec = {"tokens": {"yaml": str(brand), "typography": {}}, "slides": []}
        with pytest.raises(ValueError, match=r"unexpected keys 'typography' beside 'yaml'"):
            from_spec(spec)

    def it_layers_overrides_on_a_yaml_base(self, tmp_path):
        brand = tmp_path / "brand.yml"
        brand.write_text("palette:\n  primary: '#112233'\n  neutral: '#445566'\n")
        prs = from_spec(
            {
                "tokens": {"yaml": str(brand), "overrides": {"palette.primary": "#FF0000"}},
                "slides": [{"layout": "title_recipe", "title": "x"}],
            }
        )
        assert _first_run_rgb(prs.slides[0]) == RGBColor(0xFF, 0x00, 0x00)

    def it_rejects_a_preset_together_with_a_yaml_path(self):
        spec = {"tokens": {"preset": "vibrant", "yaml": "brand.yml"}, "slides": []}
        with pytest.raises(ValueError, match=r"either 'preset' or 'yaml', not both"):
            from_spec(spec)

    def it_rejects_overrides_without_a_base(self):
        spec = {"tokens": {"overrides": {"palette.primary": "#FF0000"}}, "slides": []}
        with pytest.raises(ValueError, match=r"'overrides'.*'preset'.*'yaml'"):
            from_spec(spec)

    def it_rejects_non_mapping_overrides(self):
        spec = {"tokens": {"preset": "vibrant", "overrides": "palette.primary=red"}, "slides": []}
        with pytest.raises(ValueError, match=r"'overrides' must be a mapping"):
            from_spec(spec)

    def it_rejects_a_non_mapping_palette_with_a_value_error(self):
        # The shape the docs used to show for ``theme``.
        spec = {"theme": {"palette": "modern_blue", "fonts": "inter"}, "slides": []}
        with pytest.raises(ValueError, match=r"tokens\.palette must be a mapping"):
            from_spec(spec)

    def it_names_the_token_when_a_font_size_has_no_unit(self):
        spec = {
            "tokens": {"typography": {"heading": {"family": "Inter", "size": 36}}},
            "slides": [],
        }
        with pytest.raises(ValueError, match=r"tokens\.typography\.heading\.size"):
            from_spec(spec)

    def it_names_the_token_when_a_radius_has_no_unit(self):
        spec = {"tokens": {"radii": {"md": 8}}, "slides": []}
        with pytest.raises(ValueError, match=r"tokens\.radii\.md.*use a float for points"):
            from_spec(spec)

    def it_accepts_json_style_list_colours(self):
        prs = from_spec(
            {
                "tokens": {"palette": {"primary": [51, 51, 51]}},
                "slides": [{"layout": "title_recipe", "title": "x"}],
            }
        )
        assert _first_run_rgb(prs.slides[0]) == RGBColor(51, 51, 51)

    def it_accepts_float_sizes_as_points(self):
        prs = from_spec(
            {
                "tokens": {
                    "typography": {"heading": {"family": "Inter", "size": 36.0}},
                    "radii": {"md": 8.0},
                },
                "slides": [{"layout": "title_recipe", "title": "x"}],
            }
        )
        run = prs.slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
        assert run.font.size.pt == 36.0


class DescribeLegacyLayoutKeyValidation:
    """Placeholder-based layouts reject the keys they never read."""

    def it_rejects_unknown_keys_on_the_title_layout(self):
        spec = {
            "slides": [{"layout": "title", "title": "Hello", "subtitlz": "typo", "bogus_key": 1}]
        }
        with pytest.raises(
            ValueError,
            match=(
                r"slides\[0\]: layout 'title': unknown spec keys "
                r"'bogus_key'; 'subtitlz' \(did you mean 'subtitle'\?\)"
            ),
        ):
            from_spec(spec)

    def it_names_the_slide_holding_the_bad_key(self):
        spec = {
            "slides": [
                {"layout": "title", "title": "A"},
                {"layout": "bullets", "title": "B", "bulets": ["x"]},
            ]
        }
        with pytest.raises(
            ValueError,
            match=(
                r"slides\[1\]: layout 'bullets': unknown spec keys "
                r"'bulets' \(did you mean 'bullets'"
            ),
        ):
            from_spec(spec)

    def it_lists_the_accepted_keys(self):
        with pytest.raises(
            ValueError, match=r"Accepted: \['layout', 'shapes', 'subtitle', 'title'"
        ):
            from_spec({"slides": [{"layout": "title", "title": "T", "nope": 1}]})

    @pytest.mark.parametrize(
        ("layout", "content"),
        [
            ("title", {"title": "T", "subtitle": "S"}),
            ("bullets", {"title": "T", "bullets": ["a", "b"]}),
            ("section", {"title": "T", "subtitle": "S"}),
            ("section", {"title": "T", "text": "S"}),
            ("two_column", {"title": "T", "left": "L", "right": "R"}),
            ("two_column", {"title": "T", "content_left": "L", "content_right": "R"}),
            ("comparison_layout", {"title": "T", "left": "L", "right": "R"}),
            ("kpi_grid", {"title": "T", "kpis": [{"label": "A", "value": "1"}]}),
            ("title_only", {"title": "T"}),
            ("blank", {}),
            ("caption", {"title": "T"}),
            ("picture", {"title": "T"}),
        ],
    )
    def it_accepts_every_key_the_layout_reads(self, layout, content):
        slide = {
            "layout": layout,
            **content,
            "transition": "fade",
            "shapes": [{"left": 1, "top": 1, "width": 1, "height": 1}],
        }
        assert len(from_spec({"slides": [slide]}).slides) == 1

    @pytest.mark.parametrize(
        ("layout", "key"),
        [
            ("title", "bullets"),
            ("bullets", "subtitle"),
            ("section", "bullets"),
            ("two_column", "subtitle"),
            ("comparison_layout", "text"),
            ("kpi_grid", "bullets"),
            ("title_only", "text"),
            ("blank", "bullets"),
            ("caption", "caption"),
            ("picture", "subtitle"),
        ],
    )
    def it_rejects_a_key_the_layout_never_reads(self, layout, key):
        with pytest.raises(
            ValueError,
            match=rf"slides\[0\]: layout '{layout}': unknown spec keys '{key}'",
        ):
            from_spec({"slides": [{"layout": layout, key: "x"}]})

    def it_rejects_slide_level_tokens_on_a_layout_that_ignores_tokens(self):
        spec = {"slides": [{"layout": "section", "title": "S", "tokens": {"preset": "vibrant"}}]}
        with pytest.raises(ValueError, match=r"layout 'section': unknown spec keys 'tokens'"):
            from_spec(spec)

    def it_treats_a_null_slide_level_tokens_value_as_nothing_to_apply(self):
        spec = {"slides": [{"layout": "section", "title": "S", "tokens": None}]}
        assert len(from_spec(spec).slides) == 1

    def it_points_a_template_layout_name_at_the_alias_that_reads_more(self):
        # "Title Slide" is the template's own name for what the "title" alias
        # fills; the name reaches only the title placeholder.
        with pytest.raises(
            ValueError,
            match=(
                r"layout 'title slide': unknown spec keys 'subtitle'.*"
                r"alias 'title' also reads \['subtitle'\]"
            ),
        ):
            from_spec({"slides": [{"layout": "Title Slide", "title": "T", "subtitle": "S"}]})

    def it_still_builds_a_slide_from_a_template_layout_name(self):
        prs = from_spec({"slides": [{"layout": "Title Slide", "title": "T"}]})
        assert prs.slides[0].slide_layout.name == "Title Slide"

    def it_locates_recipe_layout_errors_too(self):
        with pytest.raises(ValueError, match=r"slides\[1\]: layout 'kpi': unknown spec keys"):
            from_spec(
                {
                    "slides": [
                        {"layout": "blank"},
                        {"layout": "kpi", "title": "T", "kpis": [], "subtitlz": "x"},
                    ]
                }
            )
        with pytest.raises(ValueError, match=r"slides\[1\]: layout 'kpi' requires keys"):
            from_spec({"slides": [{"layout": "blank"}, {"layout": "kpi", "title": "T"}]})

    def it_locates_an_unknown_layout(self):
        with pytest.raises(ValueError, match=r"slides\[1\]: Unknown layout 'titel'"):
            from_spec({"slides": [{"layout": "blank"}, {"layout": "titel"}]})


class DescribePictureLayout:
    """The ``picture`` layout fills its picture and caption placeholders."""

    @staticmethod
    def _png(tmp_path):
        from PIL import Image

        path = tmp_path / "pic.png"
        Image.new("RGB", (8, 6), "red").save(path)
        return str(path)

    @staticmethod
    def _pictures(slide):
        return [ph for ph in slide.placeholders if hasattr(ph, "image")]

    def it_inserts_the_image_into_the_picture_placeholder(self, tmp_path):
        prs = from_spec(
            {"slides": [{"layout": "picture", "title": "P", "image": self._png(tmp_path)}]}
        )
        pictures = self._pictures(prs.slides[0])
        assert len(pictures) == 1
        assert pictures[0].image.size == (8, 6)

    def it_puts_the_caption_in_the_caption_placeholder(self, tmp_path):
        prs = from_spec(
            {
                "slides": [
                    {
                        "layout": "picture",
                        "title": "P",
                        "image": self._png(tmp_path),
                        "caption": "A caption",
                    }
                ]
            }
        )
        captions = [ph for ph in prs.slides[0].placeholders if ph.placeholder_format.idx == 2]
        assert [ph.text for ph in captions] == ["A caption"]

    def it_leaves_the_picture_placeholder_empty_without_an_image(self):
        prs = from_spec({"slides": [{"layout": "picture", "title": "P"}]})
        assert self._pictures(prs.slides[0]) == []


class DescribeWrongShapedSlides:
    """Content of the wrong type fails up front, naming ``slides[i].<key>``."""

    @pytest.mark.parametrize(
        ("slide", "pattern"),
        [
            pytest.param(
                "title",
                r"slides\[0\]: each slide must be a mapping.*'str'",
                id="slide-is-a-string",
            ),
            pytest.param(
                None,
                r"slides\[0\]: each slide must be a mapping.*'NoneType'",
                id="slide-is-none",
            ),
            pytest.param(
                {"layout": 5},
                r"slides\[0\]\.layout: must be a string.*'int'",
                id="layout-is-an-int",
            ),
            pytest.param(
                {"layout": "kpi", "title": "T", "kpis": {"label": "A", "value": "1"}},
                r"slides\[0\]\.kpis: must be a list of mappings.*'dict'",
                id="kpis-is-a-dict",
            ),
            pytest.param(
                {"layout": "kpi", "title": "T", "kpis": "ARR"},
                r"slides\[0\]\.kpis: must be a list of mappings.*'str'",
                id="kpis-is-a-string",
            ),
            pytest.param(
                {"layout": "kpi", "title": "T", "kpis": [{"label": "A"}, "B"]},
                r"slides\[0\]\.kpis\[1\]: each entry must be a mapping.*'str'",
                id="a-kpi-is-a-string",
            ),
            pytest.param(
                {"layout": "kpi_grid", "title": "T", "kpis": ["A"]},
                r"slides\[0\]\.kpis\[0\]: each entry must be a mapping",
                id="kpi-grid-entry-is-a-string",
            ),
            pytest.param(
                {"layout": "kpi_grid", "title": "T", "kpis": "A"},
                r"slides\[0\]\.kpis: must be a list of mappings",
                id="kpi-grid-kpis-is-a-string",
            ),
            pytest.param(
                {"layout": "timeline", "title": "T", "milestones": "Q1"},
                r"slides\[0\]\.milestones: must be a list of mappings.*'str'",
                id="milestones-is-a-string",
            ),
            pytest.param(
                {
                    "layout": "chart",
                    "title": "T",
                    "categories": ["a"],
                    "series": {"name": "s", "values": [1]},
                },
                r"slides\[0\]\.series: must be a list of mappings.*'dict'",
                id="series-is-a-dict",
            ),
            pytest.param(
                {
                    "layout": "chart",
                    "title": "T",
                    "categories": "Q1Q2",
                    "series": [{"name": "s", "values": [1]}],
                },
                r"slides\[0\]\.categories: must be a list.*'str'",
                id="categories-is-a-string",
            ),
            pytest.param(
                {
                    "layout": "chart",
                    "title": "T",
                    "categories": ["a", "b"],
                    "series": [{"name": "s", "values": "12"}],
                },
                r"slides\[0\]\.series\[0\]\.values: must be a list.*'str'",
                id="series-values-is-a-string",
            ),
            pytest.param(
                {
                    "layout": "comparison",
                    "title": "T",
                    "left_heading": "L",
                    "right_heading": "R",
                    "rows": ["a", "b"],
                },
                r"slides\[0\]\.rows\[0\]: each entry must be a mapping.*'str'",
                id="comparison-rows-are-strings",
            ),
            pytest.param(
                {"layout": "table", "title": "T", "columns": ["a", "b"], "rows": ["ab"]},
                r"slides\[0\]\.rows\[0\]: must be a list.*'str'",
                id="table-row-is-a-string",
            ),
            pytest.param(
                {"layout": "table", "title": "T", "columns": "ab", "rows": [["a", "b"]]},
                r"slides\[0\]\.columns: must be a list.*'str'",
                id="table-columns-is-a-string",
            ),
            pytest.param(
                {"layout": "bullets_recipe", "title": "T", "bullets": "one bullet"},
                r"slides\[0\]\.bullets: must be a list.*'str'",
                id="recipe-bullets-is-a-string",
            ),
            pytest.param(
                {"layout": "bullets", "title": "T", "bullets": "one bullet"},
                r"slides\[0\]\.bullets: must be a list.*'str'",
                id="legacy-bullets-is-a-string",
            ),
            pytest.param(
                {"layout": "bullets", "title": "T", "bullets": {"a": 1}},
                r"slides\[0\]\.bullets: must be a list.*'dict'",
                id="legacy-bullets-is-a-dict",
            ),
            pytest.param(
                {"layout": "title", "title": 2026},
                r"slides\[0\]\.title: must be a string.*'int'",
                id="title-is-an-int",
            ),
            pytest.param(
                {"layout": "title", "title": "T", "subtitle": 2026},
                r"slides\[0\]\.subtitle: must be a string.*'int'",
                id="subtitle-is-an-int",
            ),
            pytest.param(
                {"layout": "title", "title": "T", "transition": 5},
                r"slides\[0\]\.transition: must be a string.*'int'",
                id="transition-is-an-int",
            ),
            pytest.param(
                {"layout": "code", "title": "T", "code": ["a", "b"]},
                r"slides\[0\]\.code: must be a string.*'list'",
                id="code-is-a-list",
            ),
        ],
    )
    def it_rejects_content_of_the_wrong_shape_with_its_location(self, slide, pattern):
        with pytest.raises(ValueError, match=pattern):
            from_spec({"slides": [slide]})

    def it_reports_the_index_of_the_offending_slide(self):
        spec = {
            "slides": [
                {"layout": "blank"},
                {"layout": "blank"},
                {"layout": "kpi", "title": "T", "kpis": "oops"},
            ]
        }
        with pytest.raises(ValueError, match=r"slides\[2\]\.kpis"):
            from_spec(spec)

    def it_does_not_wrap_a_bare_string_into_a_one_item_list(self):
        # Decision: raise rather than silently wrap, so the author learns the
        # field is a list (the old behaviour was one bullet per character).
        with pytest.raises(ValueError, match="must be a list"):
            from_spec(
                {
                    "tokens": {"preset": "modern_light"},
                    "slides": [{"layout": "bullets", "title": "T", "bullets": "a single string"}],
                }
            )

    def it_still_accepts_tuples_for_list_fields(self):
        prs = from_spec(
            {
                "slides": [
                    {"layout": "bullets", "title": "T", "bullets": ("a", "b")},
                    {"layout": "kpi", "title": "T", "kpis": ({"label": "A", "value": "1"},)},
                ]
            }
        )
        assert len(prs.slides) == 2

    @pytest.mark.parametrize("layout", [None, ""])
    def it_still_treats_a_missing_layout_as_blank(self, layout):
        prs = from_spec({"slides": [{"layout": layout}, {}]})
        assert [s.slide_layout.name for s in prs.slides] == ["Blank", "Blank"]

    @pytest.mark.parametrize("transition", [None, False, ""])
    def it_still_treats_a_falsy_transition_as_none(self, transition):
        prs = from_spec({"slides": [{"layout": "title", "title": "T", "transition": transition}]})
        assert len(prs.slides) == 1
