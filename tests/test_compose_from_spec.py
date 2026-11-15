"""Tests for the recipe-dispatch / interpolation / YAML path of from_spec."""

from __future__ import annotations

import textwrap

import pytest

from power_pptx.compose import SpecError, from_spec, from_yaml
from power_pptx.enum.shapes import MSO_SHAPE_TYPE


def _slide_text(slide) -> str:
    """All text on *slide*, one text frame per line."""
    return "\n".join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame)


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
        # A ValueError, as the docstring promises (it used to be a KeyError),
        # naming where in the spec the marker is.
        with pytest.raises(ValueError, match="not found") as exc:
            from_spec({
                "vars": {},
                "slides": [{"layout": "title", "title": "{{missing}}"}],
            })
        assert isinstance(exc.value, SpecError)
        assert exc.value.path == "slides[0].title"
        assert not isinstance(exc.value, KeyError)

    def it_suggests_the_closest_variable_name(self):
        with pytest.raises(SpecError, match=r"did you mean 'company'\?"):
            from_spec({
                "vars": {"company": "ACME"},
                "slides": [{"layout": "title", "title": "{{compny}}"}],
            })

    @pytest.mark.parametrize(
        "code",
        [
            "Hello {{ name }}!",                       # Jinja / Mustache
            "print(f'{{literal}}')",                   # an escaped f-string brace
            "run: echo ${{ github.sha }}",             # GitHub Actions
            '{{ .Values.image | default "nginx" }}',   # Go template
        ],
    )
    def it_leaves_text_alone_when_no_vars_are_declared(self, code):
        prs = from_spec({"slides": [{"layout": "code", "title": "Snippet", "code": code}]})
        assert code in _slide_text(prs.slides[0])

    def it_interpolates_when_only_the_vars_argument_is_given(self):
        prs = from_spec(
            {"slides": [{"layout": "title", "title": "{{q}} Review"}]}, vars={"q": "Q4"}
        )
        assert "Q4 Review" in _slide_text(prs.slides[0])

    def it_treats_backslash_brace_brace_as_a_literal(self):
        prs = from_spec({
            "vars": {"company": "ACME"},
            "slides": [{
                "layout": "code",
                "title": "{{company}} templates",
                "code": "Hello \\{{ name }}! from \\{{company}} / {{company}}",
            }],
        })
        text = _slide_text(prs.slides[0])
        assert "ACME templates" in text
        assert "Hello {{ name }}! from {{company}} / ACME" in text

    def it_can_be_switched_off_for_the_whole_spec(self):
        prs = from_spec({
            "vars": {"company": "ACME"},
            "interpolate": False,
            "slides": [{"layout": "title", "title": "{{company}} {{ other }}"}],
        })
        assert "{{company}} {{ other }}" in _slide_text(prs.slides[0])

    def it_can_be_switched_off_for_one_slide(self):
        prs = from_spec({
            "vars": {"company": "ACME"},
            "slides": [
                {"layout": "title", "title": "{{company}} Review"},
                {
                    "layout": "code",
                    "title": "Workflow",
                    "code": "run: echo ${{ github.sha }} \\{{",
                    "interpolate": False,
                },
            ],
        })
        assert "ACME Review" in _slide_text(prs.slides[0])
        # Untouched: neither substituted nor unescaped.
        assert "run: echo ${{ github.sha }} \\{{" in _slide_text(prs.slides[1])

    @pytest.mark.parametrize("where", ["spec", "slide"])
    def it_rejects_a_non_boolean_interpolate_flag(self, where):
        spec = {"slides": [{"layout": "blank"}]}
        (spec if where == "spec" else spec["slides"][0])["interpolate"] = "no"
        with pytest.raises(SpecError, match="interpolate: expected true or false"):
            from_spec(spec)


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

        title_rgb = DescribeSlideLevelTokens._title_rgb(slide)
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

    def it_accepts_every_transition_kind_by_its_lower_case_name(self):
        from power_pptx.enum.presentation import MSO_TRANSITION_TYPE

        for kind in MSO_TRANSITION_TYPE:
            prs = from_spec({"slides": [{"layout": "blank", "transition": kind.name.lower()}]})

            assert prs.slides[0].transition.kind == kind

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


# ---------------------------------------------------------------------------
# Errors: every problem with a spec's content is a located SpecError
# ---------------------------------------------------------------------------

_KPI = {"layout": "kpi", "title": "Metrics", "kpis": [{"label": "ARR", "value": "1"}]}


def _png(path):
    from PIL import Image

    Image.new("RGB", (8, 8), "#3366cc").save(path)
    return path


class DescribeSpecErrors:
    """Failures caused by a slide's content are ``ValueError``s naming the
    slide and the offending key, chained from whatever was raised underneath."""

    @pytest.mark.parametrize(
        ("slide", "path", "message"),
        [
            # Each of these used to escape as the raw exception named here.
            (  # AttributeError: 'str' object has no attribute 'get'
                {"layout": "kpi", "title": "x", "kpis": ["ARR"]},
                "slides[1].kpis[0]",
                "expected a mapping like",
            ),
            (  # KeyError: 0
                {"layout": "table", "title": "x", "columns": ["a", "b"], "rows": [{"a": 1}]},
                "slides[1].rows[0]",
                "expected a list of cell values",
            ),
            (  # IndexError
                {"layout": "section_divider", "title": "x", "progress": [3]},
                "slides[1].progress",
                r"expected \[current, total\]",
            ),
            (  # TypeError from re
                {"layout": "quote", "quote": "x", "attribution": 5},
                "slides[1].attribution",
                "expected a string; got int 5",
            ),
            (
                {"layout": "title_recipe", "title": 5},
                "slides[1].title",
                "expected a string; got int 5",
            ),
            (  # AttributeError: 'int' object has no attribute 'splitlines'
                {"layout": "code", "title": "x", "code": 5},
                "slides[1].code",
                "expected a string",
            ),
            (  # AttributeError: 'str' object has no attribute 'get'
                {"layout": "timeline", "title": "x", "milestones": ["Q1", "Q2"]},
                "slides[1].milestones[0]",
                "expected a mapping like",
            ),
            (
                {"layout": "comparison", "title": "x", "left_heading": "a",
                 "right_heading": "b", "rows": [["x", "y"]]},
                "slides[1].rows[0]",
                "expected a mapping like",
            ),
            (
                {"layout": "chart", "title": "x", "categories": ["a"], "series": ["s"]},
                "slides[1].series[0]",
                "expected a mapping like",
            ),
            (  # AttributeError: 'list' object has no attribute 'get'
                {"layout": "table", "title": "x", "columns": ["a"], "rows": [[1]],
                 "totals": [1]},
                "slides[1].totals",
                "expected a mapping",
            ),
            (  # AttributeError: 'int' object has no attribute 'lower'
                {"layout": "blank", "transition": 3},
                "slides[1].transition",
                "expected a transition name",
            ),
            (  # FileNotFoundError
                {"layout": "image_hero", "title": "x", "image": "/no/such/image.png"},
                "slides[1].image",
                "file not found: '/no/such/image.png'",
            ),
            (  # AttributeError: 'int' object has no attribute 'seek'
                {"layout": "image_hero", "title": "x", "image": 5},
                "slides[1].image",
                "expected a path to an image file",
            ),
            (  # FileNotFoundError: 'hello world'
                {"layout": "figure", "title": "x", "figure": "hello world"},
                "slides[1].figure",
                "file not found: 'hello world'",
            ),
            (  # TypeError
                {"layout": "figure", "title": "x", "figure": 5},
                "slides[1].figure",
                "expected SVG or HTML markup",
            ),
            (
                {"layout": "figure", "title": "x", "figure": "<svg/>", "figure_format": "jpg"},
                "slides[1].figure_format",
                r"expected one of \['auto', 'svg', 'png'\]",
            ),
        ],
    )
    def it_names_the_slide_and_the_offending_key(self, slide, path, message):
        with pytest.raises(ValueError, match=message) as exc:
            from_spec({"slides": [{"layout": "blank"}, slide]})
        assert isinstance(exc.value, SpecError)
        assert exc.value.path == path
        assert str(exc.value).startswith(f"{path}: ")

    @pytest.mark.parametrize(
        ("spec", "path", "message"),
        [
            ({"slides": [], "lint": ["raise"]}, "lint", "lint must be one of"),  # TypeError
            ({"slides": [], "lint": "rais"}, "lint", r"did you mean 'raise'\?"),
            ({"slides": [], "template": 5}, "template", "expected a path"),  # AttributeError
            ({"slides": [], "template": "/no/such.pptx"}, "template", "file not found"),
            ({"slides": [], "vars": ["a"]}, "vars", "must be a mapping"),
            ({"slides": [], "slide_size": [0, 5]}, "slide_size", "between 1 and 56 inches"),
            ({"slides": [], "slide_size": [float("nan"), 5]}, "slide_size", "finite number"),
        ],
    )
    def it_locates_a_bad_top_level_value(self, spec, path, message):
        with pytest.raises(ValueError, match=message) as exc:
            from_spec(spec)
        assert isinstance(exc.value, SpecError)
        assert exc.value.path == path

    def it_rejects_a_template_that_is_not_a_presentation(self, tmp_path):
        bogus = tmp_path / "notes.pptx"
        bogus.write_text("not a zip", encoding="utf-8")
        with pytest.raises(SpecError, match="template: cannot open") as exc:
            from_spec({"template": str(bogus), "slides": []})
        assert exc.value.__cause__ is not None

    def it_chains_the_original_exception(self, tmp_path):
        not_an_image = tmp_path / "notes.txt"
        not_an_image.write_text("plain text", encoding="utf-8")
        with pytest.raises(SpecError, match="cannot read") as exc:
            from_spec({
                "slides": [{"layout": "image_hero", "title": "x", "image": str(not_an_image)}],
            })
        assert exc.value.path == "slides[0].image"
        assert isinstance(exc.value.__cause__, OSError)

    def it_locates_an_unexpected_failure_inside_a_recipe(self, monkeypatch):
        from power_pptx.design import recipes

        def broken(prs, **kwargs):
            raise KeyError("boom")

        monkeypatch.setattr(recipes, "quote_slide", broken)
        with pytest.raises(SpecError) as exc:
            from_spec({"slides": [_KPI, {"layout": "quote", "quote": "x"}]})
        assert exc.value.path == "slides[1]"
        assert "layout 'quote' could not be built (KeyError: 'boom')" in str(exc.value)
        assert isinstance(exc.value.__cause__, KeyError)

    def it_prefixes_a_recipe_value_error_with_the_slide(self):
        with pytest.raises(SpecError, match=r"^slides\[1\]: timeline_slide requires"):
            from_spec({
                "slides": [_KPI, {"layout": "timeline", "title": "x", "milestones": []}],
            })

    def it_lets_a_missing_optional_dependency_through_unchanged(self, monkeypatch):
        from power_pptx.design import recipes
        from power_pptx.design.figures import FigureBackendUnavailable

        def unavailable(prs, **kwargs):
            raise FigureBackendUnavailable("install the renderer")

        monkeypatch.setattr(recipes, "figure_slide", unavailable)
        with pytest.raises(ImportError, match="install the renderer"):
            from_spec({"slides": [{"layout": "figure", "title": "x", "figure": "<p>x</p>"}]})

    def it_treats_a_null_required_key_as_missing(self):
        with pytest.raises(SpecError, match=r"requires keys \['title'\]; missing \['title'\]"):
            from_spec({"slides": [{"layout": "title_recipe", "title": None}]})

    def it_treats_a_null_optional_key_as_absent(self):
        prs = from_spec({
            "slides": [{
                "layout": "title_recipe", "title": "Hello", "subtitle": None, "transition": None,
            }],
        })
        assert _slide_text(prs.slides[0]) == "Hello"

    def it_survives_keys_that_are_not_strings(self):
        with pytest.raises(SpecError, match="Unknown spec keys: 1"):
            from_spec({1: 2, "slides": []})
        with pytest.raises(SpecError, match=r"slides\[0\].*unknown spec keys 1"):
            from_spec({"slides": [{"layout": "blank", 1: 2}]})


class DescribeSlideLevelTokens:
    """A slide's ``tokens`` goes through the same resolver as the deck's."""

    @staticmethod
    def _title_rgb(slide):
        return next(
            r.font.color.rgb
            for sh in slide.shapes if sh.has_text_frame
            for p in sh.text_frame.paragraphs
            for r in p.runs if r.text
        )

    def it_accepts_a_preset_on_one_slide(self):
        # Used to raise AttributeError: 'dict' object has no attribute 'palette'.
        from power_pptx.dml.color import RGBColor

        prs = from_spec({
            "tokens": {"preset": "modern_light"},
            "slides": [_KPI, {**_KPI, "tokens": {"preset": "modern_dark"}}],
        })
        assert self._title_rgb(prs.slides[0]) == RGBColor(0x3B, 0x5B, 0xDB)
        assert self._title_rgb(prs.slides[1]) == RGBColor(0x7C, 0x5C, 0xFF)

    def it_layers_sections_and_overrides_over_the_deck_tokens(self):
        from power_pptx.dml.color import RGBColor
        from power_pptx.util import Pt

        prs = from_spec({
            "tokens": {"preset": "modern_light"},
            "slides": [
                {**_KPI, "tokens": {"palette": {"primary": "#FF0000"}}},
                {**_KPI, "tokens": {"overrides": {"typography.heading.size": 20}}},
            ],
        })
        assert self._title_rgb(prs.slides[0]) == RGBColor(0xFF, 0, 0)
        # The deck's fonts and remaining colours still apply.
        fonts = [
            r.font
            for slide in prs.slides
            for sh in slide.shapes if sh.has_text_frame
            for p in sh.text_frame.paragraphs
            for r in p.runs if r.text
        ]
        assert {f.name for f in fonts} == {"Inter"}
        title_font = next(
            r.font
            for sh in prs.slides[1].shapes if sh.has_text_frame
            for p in sh.text_frame.paragraphs
            for r in p.runs if r.text
        )
        assert title_font.size == Pt(20)
        assert title_font.color.rgb == RGBColor(0x3B, 0x5B, 0xDB)

    def it_upgrades_a_legacy_layout_that_carries_its_own_tokens(self):
        prs = from_spec({
            "slides": [{"layout": "title", "title": "Hi", "tokens": {"preset": "modern_dark"}}],
        })
        assert len(prs.slides[0].placeholders) == 0

    def it_lets_a_slide_opt_out_with_null(self):
        prs = from_spec({
            "tokens": {"preset": "modern_dark"},
            "slides": [{**_KPI, "tokens": None}],
        })
        # No palette → the recipe leaves the title colour to the theme.
        assert self._title_rgb(prs.slides[0]) is None

    def it_names_the_slide_in_a_token_error(self):
        with pytest.raises(SpecError, match=r"slides\[0\]\.tokens: unknown token keys 'palete'"):
            from_spec({"slides": [{**_KPI, "tokens": {"palete": {}}}]})

    def it_rejects_tokens_on_a_placeholder_layout(self):
        with pytest.raises(SpecError, match="'tokens' only styles recipe layouts"):
            from_spec({
                "slides": [{"layout": "section", "title": "x", "tokens": {"preset": "vibrant"}}],
            })


# ---------------------------------------------------------------------------
# Content that used to be dropped or mangled
# ---------------------------------------------------------------------------


class DescribeTokenSpecKeys:
    """Nothing in a ``tokens`` mapping is silently ignored."""

    @staticmethod
    def _title_rgb(prs):
        return DescribeSlideLevelTokens._title_rgb(prs.slides[0])

    def it_applies_sections_next_to_a_preset_as_overrides(self):
        from power_pptx.dml.color import RGBColor
        from power_pptx.util import Pt

        prs = from_spec({
            "tokens": {
                "preset": "modern_light",
                "palette": {"primary": "#FF0000"},
                "typography": {"heading": {"size": 20}},
            },
            "slides": [{"layout": "title", "title": "x"}],
        })
        assert self._title_rgb(prs) == RGBColor(0xFF, 0, 0)
        font = next(
            r.font
            for sh in prs.slides[0].shapes if sh.has_text_frame
            for p in sh.text_frame.paragraphs
            for r in p.runs if r.text
        )
        # The size changed; the preset's family and weight did not.
        assert (font.size, font.name, font.bold) == (Pt(20), "Inter", True)

    def it_applies_overrides_to_a_yaml_brand_file(self, tmp_path):
        pytest.importorskip("yaml")
        from power_pptx.dml.color import RGBColor

        brand = tmp_path / "brand.yml"
        brand.write_text("palette:\n  primary: '#112233'\n", encoding="utf-8")
        plain = from_spec({
            "tokens": {"yaml": str(brand)},
            "slides": [{"layout": "title", "title": "x"}],
        })
        assert self._title_rgb(plain) == RGBColor(0x11, 0x22, 0x33)
        overridden = from_spec({
            "tokens": {"yaml": str(brand), "overrides": {"palette.primary": "#FF0000"}},
            "slides": [{"layout": "title", "title": "x"}],
        })
        assert self._title_rgb(overridden) == RGBColor(0xFF, 0, 0)

    def it_merges_a_yaml_brand_file_over_a_preset(self, tmp_path):
        pytest.importorskip("yaml")
        from power_pptx.compose.from_spec import _resolve_tokens
        from power_pptx.dml.color import RGBColor

        brand = tmp_path / "brand.yml"
        brand.write_text("palette:\n  primary: '#112233'\n", encoding="utf-8")
        tokens = _resolve_tokens({"preset": "modern_light", "yaml": str(brand)})
        assert tokens.palette["primary"] == RGBColor(0x11, 0x22, 0x33)
        assert tokens.palette["muted"] == RGBColor(0x7B, 0x87, 0x94)  # from the preset

    def it_applies_overrides_to_inline_tokens(self):
        from power_pptx.compose.from_spec import _resolve_tokens
        from power_pptx.dml.color import RGBColor

        tokens = _resolve_tokens({
            "palette": {"primary": "#000000"},
            "overrides": {"palette.primary": "#00FF00"},
        })
        assert tokens.palette["primary"] == RGBColor(0, 0xFF, 0)

    def it_rejects_an_unknown_token_key(self):
        with pytest.raises(
            SpecError, match=r"tokens: unknown token keys 'palete' \(did you mean 'palette'\?\)"
        ):
            from_spec({
                "tokens": {"palete": {"primary": "#FF0000"}},
                "slides": [{"layout": "title", "title": "x"}],
            })

    def it_names_the_alias_key_when_theme_is_used(self):
        with pytest.raises(SpecError, match=r"^theme: unknown token keys 'fonts'"):
            from_spec({"theme": {"fonts": {}}, "slides": []})

    def it_joins_the_token_path_onto_the_spec_key(self):
        with pytest.raises(SpecError, match=r"^tokens\.palette\.primary: hex color string"):
            from_spec({"tokens": {"palette": {"primary": "red"}}, "slides": []})
        with pytest.raises(SpecError, match=r"^tokens\.typography\.heading\.size: cannot coerce"):
            from_spec({
                "tokens": {"typography": {"heading": {"family": "Inter", "size": "36"}}},
                "slides": [],
            })

    def it_builds_a_deck_from_integer_point_sizes(self):
        # ``json.loads`` yields ``36`` (an int): once 36 EMU, a 0.003pt font
        # that crashed with "value must be in range 100 to 400000".
        import json

        from power_pptx.util import Pt

        spec = json.loads(
            '{"tokens": {"typography": {"heading": {"family": "Inter", "size": 36}}},'
            ' "slides": [{"layout": "title", "title": "x"}]}'
        )
        prs = from_spec(spec)
        font = next(
            r.font
            for sh in prs.slides[0].shapes if sh.has_text_frame
            for p in sh.text_frame.paragraphs
            for r in p.runs if r.text
        )
        assert font.size == Pt(36)

    def it_hints_at_the_mapping_form_for_a_bare_preset_name(self):
        with pytest.raises(SpecError, match=r'write \{"preset": \'modern_light\'\}'):
            from_spec({"tokens": "modern_light", "slides": []})


class DescribeLegacyContentPlacement:
    """A placeholder layout places what it is given or says why it cannot."""

    @pytest.mark.parametrize(
        "slide", [{"title": "Important headline"}, {"layout": "blank", "title": "x"}]
    )
    def it_rejects_a_title_the_layout_has_no_placeholder_for(self, slide):
        with pytest.raises(SpecError, match="has no title placeholder") as exc:
            from_spec({"slides": [slide]})
        assert exc.value.path == "slides[0].title"

    def it_says_when_the_blank_layout_was_only_the_default(self):
        with pytest.raises(SpecError, match="this slide has no 'layout' key"):
            from_spec({"slides": [{"title": "Important headline"}]})

    @pytest.mark.parametrize("title", [2026, ["a", "b"], {"text": "x"}, True])
    def it_rejects_a_title_that_is_not_a_string(self, title):
        # ``suppress(AttributeError)`` used to leave the placeholder empty.
        with pytest.raises(SpecError, match=r"slides\[0\]\.title: expected a string"):
            from_spec({"slides": [{"layout": "title", "title": title}]})

    def it_rejects_a_subtitle_that_is_not_a_string(self):
        with pytest.raises(SpecError, match=r"slides\[0\]\.subtitle: expected a string"):
            from_spec({"slides": [{"layout": "title", "title": "x", "subtitle": 5}]})

    def it_reports_a_placeholder_the_template_layout_lacks(self, tmp_path):
        from power_pptx import Presentation

        template = Presentation()
        layout = template.slide_layouts.get_by_name("Title Slide")
        subtitle = next(p for p in layout.placeholders if p.placeholder_format.idx == 1)
        subtitle._element.getparent().remove(subtitle._element)
        path = tmp_path / "no-subtitle.pptx"
        template.save(str(path))
        with pytest.raises(SpecError, match="has no text placeholder for 'subtitle'") as exc:
            from_spec({
                "template": str(path),
                "slides": [{"layout": "title", "title": "x", "subtitle": "would be lost"}],
            })
        assert exc.value.path == "slides[0].subtitle"

    def it_fills_both_columns_of_two_column_with_text_or_bullets(self):
        prs = from_spec({
            "slides": [{
                "layout": "two_column", "title": "x",
                "left": ["a", {"text": "b", "level": 1}], "right": "plain",
            }],
        })
        left, right = (
            next(p for p in prs.slides[0].placeholders if p.placeholder_format.idx == idx)
            for idx in (1, 2)
        )
        assert [(p.text, p.level) for p in left.text_frame.paragraphs] == [("a", 0), ("b", 1)]
        assert right.text_frame.text == "plain"

    def it_puts_comparison_content_under_the_matching_heading(self):
        # ``right`` used to land in the *left* column's content placeholder.
        prs = from_spec({
            "slides": [{
                "layout": "comparison_layout", "title": "A vs B",
                "left_heading": "Before", "left": "Slow",
                "right_heading": "After", "right": "Fast",
            }],
        })
        text = {
            p.placeholder_format.idx: p.text_frame.text for p in prs.slides[0].placeholders
        }
        assert (text[1], text[2], text[3], text[4]) == ("Before", "Slow", "After", "Fast")
        by_idx = {p.placeholder_format.idx: p for p in prs.slides[0].placeholders}
        assert by_idx[4].left > by_idx[2].left

    def it_rejects_two_keys_for_the_same_placeholder(self):
        with pytest.raises(SpecError, match="'left' and 'content_left' fill the same placeholder"):
            from_spec({
                "slides": [{"layout": "two_column", "title": "x", "left": "a",
                            "content_left": "b"}],
            })


class DescribeBullets:
    """``bullets`` is a list of strings or ``{"text", "level"}`` mappings."""

    @pytest.mark.parametrize("tokens", [None, {"preset": "modern_light"}])
    def it_rejects_a_string_instead_of_rendering_one_character_per_line(self, tokens):
        spec = {"slides": [{"layout": "bullets", "title": "x", "bullets": "one two"}]}
        if tokens:
            spec["tokens"] = tokens
        with pytest.raises(SpecError, match="wrap it in a list") as exc:
            from_spec(spec)
        assert exc.value.path == "slides[0].bullets"

    @pytest.mark.parametrize("tokens", [None, {"preset": "modern_light"}])
    def it_renders_a_structured_bullet_as_its_text(self, tokens):
        # Used to render the repr: {'text': 'Top', 'level': 0}.
        spec = {
            "slides": [{
                "layout": "bullets", "title": "x",
                "bullets": [{"text": "Top", "level": 0}, {"text": "Second"}, "Third"],
            }],
        }
        if tokens:
            spec["tokens"] = tokens
        text = _slide_text(from_spec(spec).slides[0])
        assert "Top" in text
        assert "Second" in text
        assert "Third" in text
        assert "{" not in text

    def it_indents_by_level_in_the_placeholder_layout(self):
        prs = from_spec({
            "slides": [{
                "layout": "bullets", "title": "x",
                "bullets": ["Top", {"text": "Nested", "level": 1}, {"text": "Deep", "level": 2}],
            }],
        })
        body = next(p for p in prs.slides[0].placeholders if p.placeholder_format.idx == 1)
        assert [(p.text, p.level) for p in body.text_frame.paragraphs] == [
            ("Top", 0), ("Nested", 1), ("Deep", 2),
        ]

    def it_says_the_styled_recipe_cannot_nest(self):
        with pytest.raises(SpecError, match="draws a flat list") as exc:
            from_spec({
                "tokens": {"preset": "modern_light"},
                "slides": [{
                    "layout": "bullets", "title": "x",
                    "bullets": ["Top", {"text": "Nested", "level": 1}],
                }],
            })
        assert exc.value.path == "slides[0].bullets[1].level"

    @pytest.mark.parametrize(
        ("item", "path", "message"),
        [
            (["nested a", "nested b"], "slides[0].bullets[1]", "a nested list is not a sub-list"),
            (3, "slides[0].bullets[1]", "expected a string or a"),
            ({"txt": "x"}, "slides[0].bullets[1]", r"'txt' \(did you mean 'text'\?\)"),
            ({"level": 1}, "slides[0].bullets[1]", "needs a 'text' string"),
            ({"text": "x", "level": "1"}, "slides[0].bullets[1].level", "whole number from 0"),
            ({"text": "x", "level": 9}, "slides[0].bullets[1].level", "whole number from 0"),
            ({"text": 5}, "slides[0].bullets[1].text", "expected a string"),
        ],
    )
    def it_rejects_a_malformed_item(self, item, path, message):
        with pytest.raises(SpecError, match=message) as exc:
            from_spec({"slides": [{"layout": "bullets", "title": "x", "bullets": ["ok", item]}]})
        assert exc.value.path == path


class DescribeRecipeValueShapes:
    def it_rejects_a_table_row_longer_than_the_columns(self):
        # The extra cell used to be dropped without a word.
        with pytest.raises(SpecError, match="has 3 cells but the table has 2 columns") as exc:
            from_spec({
                "slides": [{
                    "layout": "table", "title": "T", "columns": ["Region", "Rev"],
                    "rows": [["APAC", "1"], ["EMEA", "4.2", "IMPORTANT NOTE"]],
                }],
            })
        assert exc.value.path == "slides[0].rows[1]"

    def it_still_pads_a_short_table_row(self):
        prs = from_spec({
            "slides": [{
                "layout": "table", "title": "T", "columns": ["Region", "Rev"],
                "rows": [["APAC"], ["EMEA", 4.2]],
            }],
        })
        table = next(s.table for s in prs.slides[0].shapes if getattr(s, "has_table", False))
        assert [[c.text for c in row.cells] for row in table.rows] == [
            ["Region", "Rev"], ["APAC", ""], ["EMEA", "4.2"],
        ]

    @pytest.mark.parametrize(
        ("key", "value", "message"),
        [
            ("columns", "ab", "expected a list of labels"),
            ("columns", [], "at least one column heading"),
            ("columns", [["a"]], "expected a label"),
            ("rows", [1, 2], "expected a list of cell values"),
            ("rows", "ab", "expected a list of rows"),
            ("rows", [[{"a": 1}]], "expected a cell value"),
            ("widths", ["50%", "50%"], "expected a finite number"),
            ("aligns", [1], "expected a string"),
            ("banded", "yes", "expected true or false"),
        ],
    )
    def it_rejects_a_wrong_shaped_table_value(self, key, value, message):
        slide = {"layout": "table", "title": "T", "columns": ["a", "b"], "rows": [[1, 2]]}
        slide[key] = value
        with pytest.raises(SpecError, match=message) as exc:
            from_spec({"slides": [slide]})
        assert exc.value.path.startswith(f"slides[0].{key}")

    def it_rejects_an_unknown_chart_palette(self):
        # ``except Exception: pass`` in the recipe used to swallow the typo.
        chart = {"layout": "chart", "title": "Rev", "categories": ["Q1"],
                 "series": [{"name": "A", "values": [1]}]}
        with pytest.raises(
            SpecError, match=r"unknown chart palette 'modren' \(did you mean 'modern'\?\)"
        ) as exc:
            from_spec({"slides": [{**chart, "chart_palette": "modren"}]})
        assert exc.value.path == "slides[0].chart_palette"
        with pytest.raises(SpecError, match="not a colour") as exc:
            from_spec({"slides": [{**chart, "chart_palette": ["#FF0000", "nope"]}]})
        assert exc.value.path == "slides[0].chart_palette[1]"
        with pytest.raises(SpecError, match="at least one colour"):
            from_spec({"slides": [{**chart, "chart_palette": []}]})

    @pytest.mark.parametrize("palette", ["modern", ["#FF0000", "00FF00"], [[1, 2, 3]]])
    def it_accepts_a_palette_name_or_a_list_of_colours(self, palette):
        prs = from_spec({
            "slides": [{
                "layout": "chart", "title": "Rev", "categories": ["Q1", "Q2"],
                "series": [{"name": "A", "values": [1, 2]}], "chart_palette": palette,
            }],
        })
        assert any(s.has_chart for s in prs.slides[0].shapes)

    @pytest.mark.parametrize("progress", ["3/7", 3, [3], [3, 7, 9], [1.5, 7], [0, 7], [8, 7]])
    def it_rejects_a_malformed_progress_pair(self, progress):
        with pytest.raises(SpecError, match="current") as exc:
            from_spec({
                "slides": [{"layout": "section_divider", "title": "x", "progress": progress}],
            })
        assert exc.value.path == "slides[0].progress"

    def it_accepts_a_json_progress_list(self):
        prs = from_spec({
            "slides": [{"layout": "section_divider", "title": "x", "progress": [3, 7]}],
        })
        assert len(prs.slides) == 1


class DescribeShapeGeometry:
    """Shape geometry from a spec is checked before anything is written."""

    @staticmethod
    def _spec(**box):
        entry = {"name": "card", "shape": "rectangle",
                 "left": 1, "top": 1, "width": 2, "height": 1}
        entry.update(box)
        return {"slides": [{"layout": "blank", "shapes": [entry]}]}

    @pytest.mark.parametrize(
        ("box", "key"),
        [
            ({"width": -2}, "width"),          # used to write cx="-1828800"
            ({"height": -0.01}, "height"),
            ({"width": 1e9}, "width"),
            ({"left": -1e9}, "left"),
            ({"top": 57}, "top"),
            ({"left": float("nan")}, "left"),
            ({"top": float("inf")}, "top"),
            ({"width": float("-inf")}, "width"),
        ],
    )
    def it_rejects_negative_absurd_or_non_finite_geometry(self, box, key):
        with pytest.raises(SpecError, match=rf"'{key}' of shape 'card' must be") as exc:
            from_spec(self._spec(**box))
        assert exc.value.path == f"slides[0].shapes[0].{key}"

    def it_checks_a_Length_too(self):
        from power_pptx.util import Inches

        with pytest.raises(SpecError, match="'width' of shape 'card' must be between 0 and 56"):
            from_spec(self._spec(width=Inches(-2)))

    def it_names_the_entry_when_the_shape_has_no_name(self):
        spec = self._spec(width=-2)
        del spec["slides"][0]["shapes"][0]["name"]
        with pytest.raises(SpecError, match=r"^slides\[0\]\.shapes\[0\]: 'width' must be between"):
            from_spec(spec)

    def it_still_allows_a_zero_size_and_a_small_bleed(self):
        from power_pptx.util import Inches

        prs = from_spec(self._spec(left=-0.25, top=0, width=0, height=0))
        shape = prs.slides[0].shapes[0]
        assert (shape.left, shape.width, shape.height) == (Inches(-0.25), 0, 0)

    def it_rejects_a_name_with_control_characters(self):
        with pytest.raises(SpecError, match="must not contain control characters"):
            from_spec(self._spec(name="a\x01b"))

    def it_reports_a_rejected_lint_intent_value_as_a_spec_error(self):
        # ``layer`` raises TypeError from the shape property; a spec author
        # gets the same located ValueError as for every other key.
        with pytest.raises(SpecError, match=r"slides\[0\]\.shapes\[0\]: 'layer'") as exc:
            from_spec(self._spec(layer=["a"]))
        assert exc.value.path == "slides[0].shapes[0].layer"
        assert isinstance(exc.value.__cause__, TypeError)


class DescribeLegacyKpiGrid:
    @staticmethod
    def _grid(count, **spec):
        kpis = [{"label": f"KPI {i}", "value": str(i), "delta": 0.1} for i in range(count)]
        return from_spec({"slides": [{"layout": "kpi_grid", "title": "Grid", "kpis": kpis}],
                          **spec})

    @pytest.mark.parametrize("count", [1, 3, 4, 5, 7, 8, 14])
    @pytest.mark.parametrize("slide_size", [None, "16:9"])
    def it_keeps_every_card_on_the_slide(self, count, slide_size):
        # Five KPIs on the default deck used to start at -0.9".
        from power_pptx.util import Inches

        prs = self._grid(count, **({"slide_size": slide_size} if slide_size else {}))
        cards = [s for s in prs.slides[0].shapes if not s.is_placeholder]
        assert len(cards) == 3 * count
        assert min(s.left for s in cards) >= Inches(0.5) - 1
        assert max(s.left + s.width for s in cards) <= prs.slide_width - Inches(0.5) + 1
        assert max(s.top + s.height for s in cards) <= prs.slide_height - Inches(0.5) + 1

    def it_leaves_a_small_grid_exactly_as_it_was(self):
        from power_pptx.util import Inches, Pt

        prs = self._grid(3)
        values = [s for s in prs.slides[0].shapes if not s.is_placeholder][::3]
        assert [s.left for s in values] == [Inches(1.5), Inches(3.9), Inches(6.3)]
        assert {s.width for s in values} == {Inches(2.2)}
        assert values[0].text_frame.paragraphs[0].runs[0].font.size == Pt(32)

    def it_says_when_the_grid_cannot_fit(self):
        with pytest.raises(SpecError, match=r"40 KPIs do not fit on this slide \(room for 14\)"):
            self._grid(40)

    def it_shows_a_string_delta_as_written(self):
        # ``float("+5%")`` used to raise a bare ValueError.
        prs = from_spec({
            "slides": [{"layout": "kpi_grid", "title": "x",
                        "kpis": [{"label": "a", "value": "1", "delta": "+5 pts"},
                                 {"label": "b", "value": "2", "delta": -0.25}]}],
        })
        text = _slide_text(prs.slides[0])
        assert "+5 pts" in text
        assert "-25%" in text

    @pytest.mark.parametrize(
        ("kpi", "path", "message"),
        [
            ("ARR", "slides[0].kpis[0]", "expected a mapping like"),
            ({"name": "ARR", "val": "1"}, "slides[0].kpis[0]", "unknown KPI keys"),
            ({"label": "a", "delta": [1]}, "slides[0].kpis[0].delta", "expected a number"),
            ({"label": ["a"]}, "slides[0].kpis[0].label", "expected text or a number"),
        ],
    )
    def it_rejects_a_malformed_kpi(self, kpi, path, message):
        with pytest.raises(SpecError, match=message) as exc:
            from_spec({"slides": [{"layout": "kpi_grid", "title": "x", "kpis": [kpi]}]})
        assert exc.value.path == path


class DescribeSlideSizeRescaling:
    """Changing the slide size rescales the template's masters and layouts."""

    def it_stretches_placeholder_layouts_to_the_new_width(self):
        # A 16:9 deck used to keep its placeholders in the left 9.5".
        from power_pptx.util import Inches

        prs = from_spec({
            "slide_size": "16:9",
            "slides": [{"layout": "bullets", "title": "Wide", "bullets": ["a"]},
                       {"layout": "two_column", "title": "Two", "left": "l", "right": "r"}],
        })
        title = prs.slides[0].shapes.title
        body = next(p for p in prs.slides[0].placeholders if p.placeholder_format.idx == 1)
        for placeholder in (title, body):
            assert placeholder.left == pytest.approx(Inches(0.5) * 13.333 / 10, abs=2)
            assert placeholder.left + placeholder.width == pytest.approx(
                prs.slide_width - Inches(0.5) * 13.333 / 10, abs=2
            )
        right = next(p for p in prs.slides[1].placeholders if p.placeholder_format.idx == 2)
        assert right.left > prs.slide_width / 2
        assert right.left + right.width <= prs.slide_width
        # Height did not change, so nothing moved vertically.
        from power_pptx import Presentation

        original = Presentation().slide_layouts.get_by_name("Title and Content")
        assert title.top == original.placeholders[0].top
        assert title.height == original.placeholders[0].height

    def it_leaves_geometry_alone_when_the_size_does_not_change(self):
        from power_pptx import Presentation
        from power_pptx.compose.from_spec import _apply_slide_size

        prs = Presentation()
        before = [(p.left, p.width) for p in prs.slide_layouts[1].placeholders]
        _apply_slide_size(prs, "4:3")
        assert [(p.left, p.width) for p in prs.slide_layouts[1].placeholders] == before

    def it_scales_both_axes_and_keeps_a_picture_in_proportion(self, tmp_path):
        from power_pptx import Presentation
        from power_pptx.compose.from_spec import _apply_slide_size
        from power_pptx.util import Inches

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
        picture = slide.shapes.add_picture(
            str(_png(tmp_path / "logo.png")), Inches(4), Inches(3), Inches(2), Inches(2)
        )
        _apply_slide_size(prs, (20, 7.5))
        assert (box.left, box.top, box.width, box.height) == (
            Inches(2), Inches(1), Inches(4), Inches(1)
        )
        # Twice as wide a slide: the picture keeps its size and shape, and
        # its centre moves from x=5" to x=10".
        assert (picture.width, picture.height) == (Inches(2), Inches(2))
        assert picture.left + picture.width // 2 == Inches(10)
        assert picture.top == Inches(3)


# ---------------------------------------------------------------------------
# What a spec may ask the process to do
# ---------------------------------------------------------------------------


def _figure_spec(figure="<p>hello</p>", **keys):
    return {"slides": [{"layout": "figure", "title": "Chart", "figure": figure, **keys}]}


@pytest.fixture
def embed_calls(monkeypatch):
    """Record the keyword arguments figure slides pass to the HTML embedder."""
    from power_pptx.design import figures

    calls = []

    def fake_add_html_figure(slide, html, left, top, width=None, height=None, **options):
        calls.append({"html": html, **options})

    monkeypatch.setattr(figures, "add_html_figure", fake_add_html_figure)
    return calls


class DescribeCaptureOptionsFromASpec:
    """A spec is data: it may tune a capture but never choose what gets run."""

    @pytest.mark.parametrize("key", ["html_options", "plotly_options"])
    @pytest.mark.parametrize("safe", [False, True])
    def it_refuses_to_take_the_browser_executable_from_a_spec(
        self, key, safe, tmp_path, embed_calls
    ):
        marker = tmp_path / "MARKER.txt"
        fake_browser = tmp_path / "fake_browser.sh"
        fake_browser.write_text(f"#!/bin/sh\necho launched > '{marker}'\n", encoding="utf-8")
        fake_browser.chmod(0o755)
        spec = _figure_spec(**{key: {"browser_path": str(fake_browser), "timeout_ms": 5000}})
        with pytest.raises(SpecError, match="cannot be set from a spec") as exc:
            from_spec(spec, safe=safe)
        assert exc.value.path == f"slides[0].{key}.browser_path"
        assert "POWER_PPTX_CHROMIUM" in str(exc.value)
        # Rejected before anything was launched or embedded.
        assert not marker.exists()
        assert embed_calls == []

    def it_keeps_browser_path_on_the_python_functions(self):
        import inspect

        from power_pptx.compose import from_html
        from power_pptx.design.figures import add_html_figure, add_plotly_figure

        for function in (add_html_figure, add_plotly_figure, from_html):
            assert "browser_path" in inspect.signature(function).parameters

    def it_forwards_the_other_capture_options(self, embed_calls):
        from_spec(_figure_spec(html_options={
            "selector": "#chart", "viewport": [640, 360], "omit_background": True,
        }))
        # -- `fit` is not a capture option: figure_slide passes its own
        # -- (default "contain") to every figure kind --
        assert embed_calls == [{
            "html": "<p>hello</p>", "selector": "#chart", "viewport": (640, 360),
            "omit_background": True, "fit": "contain",
        }]

    def it_rejects_an_unknown_capture_option(self):
        with pytest.raises(SpecError, match=r"'selectr' \(did you mean 'selector'\?\)") as exc:
            from_spec(_figure_spec(html_options={"selectr": "#chart"}))
        assert exc.value.path == "slides[0].html_options"
        with pytest.raises(SpecError, match="'format' is the slide's 'figure_format' key"):
            from_spec(_figure_spec(plotly_options={"format": "png"}))

    def it_rejects_capture_options_that_are_not_a_mapping(self):
        with pytest.raises(SpecError, match="expected a mapping of capture options"):
            from_spec(_figure_spec(html_options=["selector"]))


class DescribeSafeMode:
    """``safe=True`` is the mode for a spec written by a model or a user."""

    def it_captures_html_figures_without_network_access(self, embed_calls):
        from_spec(_figure_spec(), safe=True)
        from_spec(_figure_spec(html_options={"selector": "p"}), safe=True)
        from_spec(_figure_spec(html_options={"allow_network": False}), safe=True)
        assert [call["allow_network"] for call in embed_calls] == [False, False, False]
        assert embed_calls[1]["selector"] == "p"

    def it_leaves_network_access_to_the_caller_otherwise(self, embed_calls):
        from_spec(_figure_spec())
        from_spec(_figure_spec(html_options={"allow_network": False}))
        assert "allow_network" not in embed_calls[0]
        assert embed_calls[1]["allow_network"] is False

    def it_refuses_to_let_a_spec_turn_the_network_back_on(self, embed_calls):
        with pytest.raises(SpecError, match="cannot turn network access back on") as exc:
            from_spec(_figure_spec(html_options={"allow_network": True}), safe=True)
        assert exc.value.path == "slides[0].html_options.allow_network"
        assert embed_calls == []

    def it_passes_the_offline_setting_to_the_plotly_adapter_too(self, monkeypatch):
        from power_pptx.design import figures

        calls = []

        class Figure:
            def to_image(self, **kwargs):  # pragma: no cover - never rendered
                raise AssertionError

        def fake_add_plotly_figure(slide, figure, left, top, width=None, height=None, **options):
            calls.append(options)

        monkeypatch.setattr(figures, "add_plotly_figure", fake_add_plotly_figure)
        from_spec(_figure_spec(Figure()), safe=True)
        assert calls == [{"format": "auto", "allow_network": False}]

    @pytest.fixture
    def sandbox(self, tmp_path):
        """A base directory with assets in it, and the same assets outside it."""
        from power_pptx import Presentation

        base = tmp_path / "workspace"
        (base / "assets").mkdir(parents=True)
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        for folder in (base / "assets", outside):
            _png(folder / "hero.png")
            Presentation().save(str(folder / "template.pptx"))
            (folder / "brand.yml").write_text("palette:\n  primary: '#112233'\n", "utf-8")
            (folder / "page.html").write_text("<p>page</p>", encoding="utf-8")
        return base, outside

    @staticmethod
    def _spec_naming(key, path):
        path = str(path)
        if key == "template":
            return {"template": path, "slides": [{"layout": "blank"}]}
        if key == "tokens.yaml":
            return {"tokens": {"yaml": path}, "slides": [{"layout": "title", "title": "x"}]}
        if key == "image":
            return {"slides": [{"layout": "image_hero", "title": "x", "image": path}]}
        return _figure_spec(path)

    _KEYS = [
        ("template", "template.pptx", "template"),
        ("tokens.yaml", "brand.yml", "tokens.yaml"),
        ("image", "hero.png", "slides[0].image"),
        ("figure", "hero.png", "slides[0].figure"),
        ("figure", "page.html", "slides[0].figure"),
    ]

    @pytest.mark.parametrize(("key", "name", "path"), _KEYS)
    def it_rejects_a_file_outside_the_base_directory(self, key, name, path, sandbox, embed_calls):
        if key == "tokens.yaml":
            pytest.importorskip("yaml")
        base, outside = sandbox
        with pytest.raises(SpecError, match="is outside base_dir") as exc:
            from_spec(self._spec_naming(key, outside / name), safe=True, base_dir=base)
        assert exc.value.path == path
        assert embed_calls == []
        # The same spec is fine when the caller does not ask for safe mode.
        from_spec(self._spec_naming(key, outside / name))

    @pytest.mark.parametrize(("key", "name", "path"), _KEYS)
    def it_accepts_a_file_inside_the_base_directory(self, key, name, path, sandbox, embed_calls):
        if key == "tokens.yaml":
            pytest.importorskip("yaml")
        base, _outside = sandbox
        prs = from_spec(self._spec_naming(key, f"assets/{name}"), safe=True, base_dir=base)
        assert len(prs.slides) == 1
        prs = from_spec(
            self._spec_naming(key, base / "assets" / name), safe=True, base_dir=base
        )
        assert len(prs.slides) == 1

    @pytest.mark.parametrize("escape", ["../elsewhere/hero.png", "assets/../../elsewhere/hero.png"])
    def it_rejects_a_relative_path_that_climbs_out(self, escape, sandbox):
        base, _outside = sandbox
        with pytest.raises(SpecError, match="is outside base_dir"):
            from_spec(self._spec_naming("image", escape), safe=True, base_dir=base)

    def it_rejects_a_symlink_that_leads_out(self, sandbox):
        base, outside = sandbox
        try:
            (base / "assets" / "link.png").symlink_to(outside / "hero.png")
        except OSError:
            pytest.skip("symlinks are not available")
        with pytest.raises(SpecError, match="is outside base_dir") as exc:
            from_spec(self._spec_naming("image", "assets/link.png"), safe=True, base_dir=base)
        assert exc.value.path == "slides[0].image"

    def it_uses_the_working_directory_when_no_base_is_given(self, sandbox, monkeypatch):
        base, outside = sandbox
        monkeypatch.chdir(base)
        assert len(from_spec(self._spec_naming("image", "assets/hero.png"), safe=True).slides) == 1
        with pytest.raises(SpecError, match="is outside base_dir"):
            from_spec(self._spec_naming("image", outside / "hero.png"), safe=True)

    def it_resolves_relative_paths_against_base_dir_without_safe_mode(self, sandbox, monkeypatch):
        base, outside = sandbox
        monkeypatch.chdir(outside)
        (outside / "hero.png").unlink()
        prs = from_spec(self._spec_naming("image", "assets/hero.png"), base_dir=base)
        assert len(prs.slides) == 1
        with pytest.raises(SpecError, match="file not found: 'assets/hero.png'"):
            from_spec(self._spec_naming("image", "assets/hero.png"))

    def it_applies_to_a_yaml_spec_as_well(self, sandbox):
        pytest.importorskip("yaml")
        base, outside = sandbox
        deck = outside / "deck.yml"
        deck.write_text(
            f"slides:\n  - layout: image_hero\n    title: x\n    image: {outside / 'hero.png'}\n",
            encoding="utf-8",
        )
        with pytest.raises(SpecError, match="is outside base_dir"):
            from_yaml(str(deck), safe=True, base_dir=base)
        assert len(from_yaml(str(deck)).slides) == 1


# ---------------------------------------------------------------------------
# Exact messages and paths for checks no other test pins down
# ---------------------------------------------------------------------------


def _spec_error(spec, **kwargs):
    """Return the SpecError ``from_spec(spec, **kwargs)`` raises."""
    with pytest.raises(SpecError) as exc:
        from_spec(spec, **kwargs)
    return exc.value


def _shapes_spec(*entries):
    return {"slides": [{"layout": "blank", "shapes": list(entries)}]}


def _box(**entry):
    return {"left": 1, "top": 1, "width": 2, "height": 1, **entry}


class DescribeSpecStructureChecks:
    def it_rejects_a_slides_value_that_is_not_a_list(self):
        error = _spec_error({"slides": {"layout": "blank"}})
        assert (str(error), error.path) == ("'slides' must be a list", "slides")

    def it_rejects_a_slide_that_is_not_a_mapping(self):
        error = _spec_error({"slides": [{"layout": "blank"}, "blank"]})
        assert (str(error), error.path) == (
            "slides[1]: each slide must be a mapping", "slides[1]"
        )

    def it_rejects_a_layout_that_is_not_a_string(self):
        error = _spec_error({"slides": [{"layout": 3}]})
        assert (str(error), error.path) == (
            "slides[0].layout must be a string", "slides[0].layout"
        )

    @pytest.mark.parametrize(
        ("lint", "message"),
        [
            (["raise"], "lint must be one of ['off', 'raise', 'warn'], got ['raise']"),
            ("rase", "lint must be one of ['off', 'raise', 'warn'], got 'rase' "
                     "(did you mean 'raise'?)"),
        ],
    )
    def it_rejects_an_unknown_lint_mode(self, lint, message):
        error = _spec_error({"lint": lint, "slides": []})
        assert (str(error), error.path) == (message, "lint")

    def it_rejects_vars_that_are_not_a_mapping(self):
        error = _spec_error({"vars": ["a"], "slides": []})
        assert (str(error), error.path) == ("spec 'vars' must be a mapping", "vars")


class DescribeShapeEntryChecks:
    def it_rejects_an_entry_that_is_not_a_mapping(self):
        error = _spec_error(_shapes_spec("card"))
        assert str(error) == "slides[0].shapes[0]: each 'shapes' entry must be a mapping; got 'str'"
        assert error.path == "slides[0].shapes[0]"  # -- was "" --

    @pytest.mark.parametrize(("name", "shown"), [("  ", "'  '"), (5, "5")])
    def it_rejects_a_blank_or_non_string_name(self, name, shown):
        error = _spec_error(_shapes_spec(_box(name=name)))
        assert str(error) == (
            f"slides[0].shapes[0]: shape 'name' must be a non-empty string; got {shown}"
        )

    def it_rejects_a_shape_kind_that_is_not_a_string(self):
        error = _spec_error(_shapes_spec(_box(shape=3)))
        assert str(error) == (
            "slides[0].shapes[0]: 'shape' must be a string naming an MSO_SHAPE member "
            "or 'textbox'; got 'int'"
        )

    @pytest.mark.parametrize(
        ("value", "message"),
        [
            (True, "'width' of shape 'card' must be a number (inches) or Length; got bool: True"),
            ("2", "'width' of shape 'card' must be a number (inches) or Length; got 'str': '2'"),
        ],
    )
    def it_rejects_a_size_that_is_not_a_number(self, value, message):
        error = _spec_error(_shapes_spec(_box(name="card", width=value)))
        assert str(error) == f"slides[0].shapes[0]: {message}"
        assert error.path == "slides[0].shapes[0].width"

    def it_treats_the_textbox_kind_case_insensitively_and_stringifies_text(self):
        prs = from_spec(_shapes_spec(_box(shape=" TextBox ", text=42)))
        shape = prs.slides[0].shapes[0]
        assert shape.shape_type == MSO_SHAPE_TYPE.TEXT_BOX
        assert shape.text_frame.text == "42"

    @pytest.mark.parametrize(("ref", "shown"), [("", "''"), (3, "3")])
    def it_rejects_a_blank_or_non_string_overlap_name(self, ref, shown):
        error = _spec_error(
            _shapes_spec(_box(name="a"), _box(name="b", allow_overlap_with=["a", ref]))
        )
        assert str(error) == (
            "slides[0].shapes[1]: 'allow_overlap_with' entries must be non-empty shape "
            f"names; got {shown}"
        )
        assert error.path == "slides[0].shapes[1].allow_overlap_with"  # -- was "" --

    @pytest.mark.parametrize(
        ("shapes", "where", "key"),
        [
            ({"left": 1}, "slides[0]", "shapes"),
            (["card"], "slides[0].shapes[0]", None),
            ([_box(colour="red")], "slides[0].shapes[0]", None),
            ([{"left": 1, "top": 1, "width": 2}], "slides[0].shapes[0]", None),
            ([_box(name="  ")], "slides[0].shapes[0]", "name"),
            ([_box(name="a\x01b")], "slides[0].shapes[0]", "name"),
            ([_box(name="a"), _box(name="a")], "slides[0].shapes[1]", "name"),
            ([_box(shape=3)], "slides[0].shapes[0]", "shape"),
            ([_box(shape="rectangel")], "slides[0].shapes[0]", "shape"),
            ([_box(name="a", allow_overlap_with=7)], "slides[0].shapes[0]", "allow_overlap_with"),
            ([_box(name="a", allow_overlap_with="a")], "slides[0].shapes[0]",
             "allow_overlap_with"),
            ([_box(name="a"), _box(name="b", allow_overlap_with="carrd")], "slides[0].shapes[1]",
             "allow_overlap_with"),
        ],
        ids=[
            "not-a-list", "not-a-mapping", "unknown-key", "missing-key", "blank-name",
            "control-character", "duplicate-name", "kind-not-a-string", "unknown-kind",
            "overlap-not-a-name", "overlap-self", "overlap-unknown",
        ],
    )
    def it_gives_the_location_of_a_shape_entry_error_as_its_path(self, shapes, where, key):
        # -- the message always started with the location; `.path` used to be "" --
        error = _spec_error({"slides": [{"layout": "blank", "shapes": shapes}]})

        assert str(error).startswith(where + ": ")
        assert error.path == (where if key is None else "%s.%s" % (where, key))

    def it_gives_a_cross_slide_overlap_reference_its_path(self):
        error = _spec_error(
            {
                "slides": [
                    {"layout": "blank", "shapes": [_box(name="card")]},
                    {"layout": "blank", "shapes": [_box(name="b", allow_overlap_with="card")]},
                ]
            }
        )

        assert "is defined on slides [0]" in str(error)
        assert error.path == "slides[1].shapes[0].allow_overlap_with"

    def it_accepts_a_tuple_of_overlap_names(self):
        prs = from_spec(
            _shapes_spec(_box(name="a"), _box(name="b", allow_overlap_with=("a",)))
        )
        a, b = prs.slides[0].shapes
        assert b.overlap_allowances == frozenset({a.shape_id})


class DescribeLegacyKpiCards:
    @staticmethod
    def _cards(kpis):
        prs = from_spec({"slides": [{"layout": "kpi_grid", "title": "x", "kpis": kpis}]})
        return [s for s in prs.slides[0].shapes if not s.is_placeholder]

    def it_adds_no_cards_for_an_empty_list(self):
        assert self._cards([]) == []

    def it_shows_a_missing_label_or_value_as_empty_text(self):
        value, label = self._cards([{"value": 7}])
        assert (value.text_frame.text, label.text_frame.text) == ("7", "")

    def it_colours_a_delta_by_its_sign(self):
        from power_pptx.dml.color import RGBColor

        red, green = RGBColor(0xCC, 0x00, 0x00), RGBColor(0x00, 0x8A, 0x00)
        deltas = [0.1, 0, -0.25, "−3 pts", "–1", " -2", "+5"]
        cards = self._cards([{"label": "k", "value": "1", "delta": d} for d in deltas])
        shown = [
            (box.text_frame.text, box.text_frame.paragraphs[0].runs[0].font.color.rgb)
            for box in cards[2::3]
        ]
        assert shown == [
            ("+10%", green),
            ("+0%", green),
            ("-25%", red),
            ("−3 pts", red),
            ("–1", red),
            (" -2", red),
            ("+5", green),
        ]


class DescribeLengthCoercion:
    @pytest.mark.parametrize(
        ("bounds", "value", "message"),
        [
            ({"minimum": 0.0}, -1, "width must be at least 0 inches; got -1"),
            ({"maximum": 56.0}, 60, "width must be at most 56 inches; got 60"),
            (
                {"minimum": 0.0, "maximum": 56.0},
                60,
                "width must be between 0 and 56 inches; got 60",
            ),
        ],
    )
    def it_names_the_bounds_a_value_breaks(self, bounds, value, message):
        from power_pptx.compose.from_spec import _coerce_length

        with pytest.raises(SpecError) as exc:
            _coerce_length(value, "width", path="w", **bounds)
        assert (str(exc.value), exc.value.path) == (message, "w")

    def it_returns_numbers_as_inches_and_lengths_as_they_are(self):
        from power_pptx.compose.from_spec import _coerce_length
        from power_pptx.util import Emu, Inches

        assert _coerce_length(2, "width") == Inches(2)
        assert _coerce_length(Emu(5), "width", minimum=0.0) == Emu(5)
        assert _coerce_length(60, "width", minimum=0.0) == Inches(60)


class DescribeInterpolationPaths:
    _UNKNOWN = (
        "interpolation variable {name!r} not found in vars={names!r}. Write \\{{{{ for a "
        "literal '{{{{', or set \"interpolate\": false on the slide (or the whole spec) to "
        "switch substitution off"
    )

    def it_interpolates_inside_tuples(self):
        prs = from_spec({
            "vars": {"q": "Q1"},
            "slides": [{
                "layout": "chart",
                "title": "x",
                "categories": ("{{q}}", "Q2"),
                "series": [{"name": "a", "values": [1, 2]}],
            }],
        })
        chart = next(s.chart for s in prs.slides[0].shapes if s.has_chart)
        assert [c.label for c in chart.plots[0].categories] == ["Q1", "Q2"]

    def it_names_the_tuple_item_holding_an_unknown_variable(self):
        error = _spec_error({
            "vars": {"q": "Q1"},
            "slides": [{
                "layout": "chart",
                "title": "x",
                "categories": ("{{q}}", "{{z}}"),
                "series": [{"name": "a", "values": [1, 2]}],
            }],
        })
        assert error.path == "slides[0].categories[1]"
        assert str(error) == "slides[0].categories[1]: " + self._UNKNOWN.format(
            name="z", names=["q"]
        )

    def it_interpolates_a_top_level_key_under_its_own_name(self):
        error = _spec_error({"vars": {}, "template": "{{nope}}", "slides": []})
        assert error.path == "template"
        assert str(error) == "template: " + self._UNKNOWN.format(name="nope", names=[])

    def it_does_not_walk_a_dotted_name_through_a_string(self):
        error = _spec_error(
            {"vars": {"a": "s"}, "slides": [{"layout": "title", "title": "{{a.b}}"}]}
        )
        assert error.path == "slides[0].title"
        assert "variable 'a.b' not found in vars=['a']" in str(error)

    def it_keys_a_path_less_walk_on_the_mapping_keys(self):
        from power_pptx.compose.from_spec import _interpolate

        assert _interpolate({"a": ["{{x}}", 3, ("{{x}}",)]}, {"x": 1}) == {"a": ["1", 3, ("1",)]}
        with pytest.raises(SpecError) as exc:
            _interpolate({"a": {"b": "{{y}}"}}, {})
        assert exc.value.path == "a.b"


class DescribeTokenSectionChecks:
    def it_rejects_a_section_that_is_not_a_mapping(self):
        error = _spec_error(
            {"tokens": {"preset": "modern_light", "palette": ["#fff"]}, "slides": []}
        )
        assert (str(error), error.path) == (
            "tokens.palette: expected a mapping of token names to values; got list ['#fff']",
            "tokens.palette",
        )

    def it_skips_a_null_section(self):
        prs = from_spec({
            "tokens": {"preset": "modern_light", "palette": None},
            "slides": [{"layout": "title", "title": "x"}],
        })
        assert len(prs.slides) == 1

    def it_puts_a_colon_after_the_key_for_an_error_with_no_path_of_its_own(self):
        error = _spec_error({"tokens": {"preset": "nope"}, "slides": []})
        assert error.path == "tokens"
        assert str(error).startswith("tokens: Unknown preset 'nope'")
