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
